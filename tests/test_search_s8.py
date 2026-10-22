"""Pass 8: bounded semantic work and legacy mention URL parsing, offline."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import index
import library_resources
from tests.test_local_search import vector
from tests.test_semantic_search import db as semantic_db, ready
from tests.test_smarter_search import db, seed
from uoink_core import local_search as ls


@pytest.mark.parametrize("state", ["missing", "stale"])
def test_vector_cache_falls_back_without_loading_or_inference(semantic_db, monkeypatch, state):
    idx, engine, _ = semantic_db
    seed(idx, "mars", "Mars rusty soil")
    ready(semantic_db)
    if state == "missing":
        engine.store._cache = None
    else:
        source, = engine.sources.snapshot()
        engine.store.replace(source, [vector(0)] * len(source.passages))
    monkeypatch.setattr(engine.store, "_connect", lambda: pytest.fail("query opened vector DB"))
    monkeypatch.setattr(engine.store, "refresh", lambda: pytest.fail("query rebuilt vectors"))
    monkeypatch.setattr(engine._model, "embed", lambda *a, **kw: pytest.fail("stale cache ran inference"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        page = pool.submit(idx.search_mode, "rusty").result(timeout=1)
        assert page["search_mode"] == "keyword" and page["fallback_reason"]
        assert page["results"][0]["video_id"] == "mars"
        reader = library_resources.LibraryReader(idx, data_root=engine.root)
        page = pool.submit(reader.search, "rusty").result(timeout=1)
        assert page["search_mode"] == "keyword" and page["fallback_reason"]
        assert page["hits"][0]["item_id"] == "mars"


def test_background_vector_rebuild_swaps_only_when_ready(semantic_db, monkeypatch):
    np = pytest.importorskip("numpy")
    idx, engine, _ = semantic_db
    seed(idx, "mars", "Mars rusty soil")
    ready(semantic_db)
    previous = engine.store._cache
    entered, release = threading.Event(), threading.Event()
    original = np.vstack
    workers = []

    def slow_matrix(*args, **kwargs):
        matrix = original(*args, **kwargs)
        workers.append(threading.current_thread().name)
        entered.set()
        assert release.wait(5)
        return matrix

    monkeypatch.setattr(np, "vstack", slow_matrix)
    try:
        seed(idx, "new", "New Mars rusty rocks")
        assert entered.wait(3)
        assert engine.store._cache is previous
        with pytest.raises(ls.SearchUnavailable, match="Vector snapshot"):
            engine.embedding_search("rusty")
        # Exercise the cache guard even if readiness was observed just before
        # the rebuild began. Ordinary indexing state also falls back.
        engine._set("ready")
        with ThreadPoolExecutor(max_workers=1) as pool:
            reader = library_resources.LibraryReader(idx, data_root=engine.root)
            page = pool.submit(reader.search, "rusty").result(timeout=1)
            assert page["search_mode"] == "keyword" and page["fallback_reason"]
            assert {hit["item_id"] for hit in page["hits"]} == {"mars", "new"}
    finally:
        release.set()
        assert engine.wait(5)
    assert workers == ["embeddinggemma-index"]
    assert engine.store._cache is not previous
    page = idx.search_embedding("rusty")
    assert page["search_mode"] == "semantic"
    assert {row["video_id"] for row in page["results"]} == {"mars", "new"}


@pytest.mark.parametrize("phase", ["search_mode", "embed"])
def test_slow_semantic_phase_falls_back_before_deadline(semantic_db, monkeypatch, phase):
    idx, engine, _ = semantic_db
    seed(idx, "mars", "Mars rusty soil")
    ready(semantic_db)
    target, name = (idx, "search_mode") if phase == "search_mode" else (engine._model, "embed")
    original = getattr(target, name)
    finished = threading.Event()
    calls = []
    keyword_calls = []
    keyword_search = idx.search
    monkeypatch.setattr(idx, "search", lambda *a, **kw:
                        keyword_calls.append(True) or keyword_search(*a, **kw))

    def slow(*args, **kwargs):
        calls.append(threading.current_thread().name)
        try:
            time.sleep(2.2)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(target, name, slow)
    try:
        reader = library_resources.LibraryReader(idx, data_root=engine.root)
        start = time.monotonic()
        page = reader.search("rusty", mode="hybrid")
        assert time.monotonic() - start < 2.0
        assert page["ok"] and page["search_mode"] == "keyword"
        assert "time" in page["fallback_reason"]
        assert page["hits"][0]["item_id"] == "mars"
        assert keyword_calls == [True]
        reader.assert_within_deadline()
        # An unfinished timed query cannot accumulate more semantic workers.
        again = library_resources.LibraryReader(idx, data_root=engine.root)
        start = time.monotonic()
        assert again.search("rusty")["search_mode"] == "keyword"
        assert time.monotonic() - start < 0.5
        assert len(calls) == 1
    finally:
        assert finished.wait(5)
        assert engine._query_lock.acquire(timeout=5)
        engine._query_lock.release()
    monkeypatch.setattr(target, name, original)
    assert reader.search("rusty")["search_mode"] == "hybrid"


def test_semantic_phase_skipped_with_less_than_600ms_left(semantic_db, monkeypatch):
    idx, engine, _ = semantic_db
    seed(idx, "mars", "Mars rusty soil")
    ready(semantic_db)
    reader = library_resources.LibraryReader(idx, data_root=engine.root, deadline_s=0.59)
    monkeypatch.setattr(idx, "search_mode", lambda *a, **kw: pytest.fail("semantic phase started"))
    page = reader.search("rusty", mode="semantic")
    assert page["ok"] and page["search_mode"] == "keyword"
    assert page["requested_mode"] == "semantic" and page["fallback_reason"]
    assert page["hits"][0]["item_id"] == "mars"
    reader.assert_within_deadline()


def test_semantic_fallback_preserves_strict_keyword_matching(semantic_db, monkeypatch):
    idx, engine, _ = semantic_db
    seed(idx, "complete", "Mars rusty soil")
    seed(idx, "partial", "Mars rusty rocks")
    ready(semantic_db)

    def unavailable(*args, **kwargs):
        raise ls.SearchUnavailable("fixture")

    monkeypatch.setattr(engine, "embedding_search", unavailable)
    reader = library_resources.LibraryReader(idx, data_root=engine.root)
    for mode in ("semantic", "hybrid"):
        page = reader.search("rusty soil", mode=mode, match="strict")
        assert page["search_mode"] == "keyword" and page["fallback_reason"]
        assert [hit["item_id"] for hit in page["hits"]] == ["complete"]


@pytest.mark.parametrize("match", ["strict", "forgiving"])
@pytest.mark.parametrize("metadata", [
    '{"url":"https://example.com/last","number":NaN}',
    '{"url":"https://example.com/last","number":Infinity}',
    '{"url":"https://example.com/last","number":-Infinity}',
    '{"url":"https://example.com/first","url":"https://example.com/last"}',
])
def test_mention_deep_link_uses_legacy_python_json_for_page_only(db, monkeypatch, match, metadata):
    for vid in ("older", "page"):
        row = seed(db, vid, "Mars rusty soil")
        row.update(platform="web", metadata_json=metadata)
        db.upsert_yoink(row, content="Mars rusty soil")
        db.record_entities(vid, [{"name": "Mars", "mentions": [{"timestamp": 31.8}]}])
    original = json.loads
    parsed = []

    def observe(value, *args, **kwargs):
        if value == metadata:
            parsed.append(value)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(index.json, "loads", observe)
    row, = db.find_mentions("Mars", limit=1, match=match)
    assert row["video_id"] == "page"
    assert row["deep_link"] == "https://example.com/last#t=31"
    assert "metadata_json" not in row and "_source_url" not in row
    assert parsed == [metadata]
