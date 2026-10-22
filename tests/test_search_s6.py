"""Pass 6 bounds and wire regressions, runnable against the pre-repair tree."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import sqlite3
import threading
from types import SimpleNamespace

import pytest

import corpus_contract
import corpus_provider
import index
import library_resources
import uoink_agent_runtime
import uoink_mcp_tools
from tests.test_semantic_search import db as semantic_db, ready
from tests.test_smarter_search import seed
from uoink_core import local_search as ls


@pytest.fixture
def dense(tmp_path):
    with index.Index.open(tmp_path / "index.db") as idx:
        with idx._conn:
            for n in range(256):
                vid = f"source{n:04}"
                texts = [("w3 " * (1 + (n + seq) % 23) + "w50 w400 YouTube evidence "
                          + "padding " * ((n * 7 + seq * 3) % 31)) for seq in range(60)]
                idx._conn.execute(
                    "INSERT INTO yoinks(video_id,slug,title,channel,platform,yoinked_at,corpus_path,sidecar_path) "
                    "VALUES (?,?,?,'Channel','youtube','2026-10-22','','')", (vid, vid, f"Source {n}"))
                idx._conn.execute("INSERT INTO yoinks_fts(video_id,content) VALUES (?,?)", (vid, "\n".join(texts)))
                idx._conn.executemany("INSERT INTO clips(video_id,seq,start,end,text) VALUES (?,?,?,?,?)",
                    [(vid, seq, seq * 30, seq * 30 + 30, text) for seq, text in enumerate(texts)])
        for n in range(256):
            idx.record_entities(f"source{n:04}", [{"name": "YouTube", "type": "product", "mentions": [
                {"timestamp": 999.0, "context": "w50 w400 YouTube evidence"}]}])
        yield idx


@contextmanager
def sql_work(idx):
    stats = {"steps": 0, "sql": []}
    def progress():
        stats["steps"] += 100
        return 0
    def install(db):
        db.set_progress_handler(progress, 100)
        db.set_trace_callback(lambda sql: stats["sql"].append(sql) if not sql.startswith("--") else None)
    original = getattr(idx, "search_read", None)
    if original is not None:
        @contextmanager
        def observed(**kwargs):
            with original(**kwargs) as db:
                install(db)
                yield db
        idx.search_read = observed
    install(idx._conn)
    try:
        yield stats
    finally:
        idx._conn.set_progress_handler(None, 0)
        idx._conn.set_trace_callback(None)
        if original is not None:
            idx.search_read = original


def test_common_library_query_bounds(dense):
    reader = library_resources.LibraryReader(dense, data_root=dense._path.parent)
    with sql_work(dense) as work:
        result = reader.search("w3 w50 w400", 5, mode="keyword")
    assert len(result["hits"]) == 5
    assert work["steps"] < 2_000_000, work["steps"]
    assert not any("covered_sources" in sql and "INTERSECT" in sql for sql in work["sql"])
    rankings = [sql for sql in work["sql"] if "bm25(clips_fts" in sql]
    assert rankings and all("scoped_clips" in sql for sql in rankings)
    assert all("search_source :" in sql for sql in rankings)
    assert any("ORDER BY yoinks_fts.rank LIMIT 32" in sql for sql in work["sql"])


def test_clip_source_key_is_private_and_tracks_writes(tmp_path):
    with index.Index.open(tmp_path / "index.db") as idx:
        seed(idx, "a-source", "Needle passage")
        seed(idx, "b-source", "Another passage")
        with idx._conn:
            idx._conn.execute("INSERT INTO clips(video_id,seq,start,end,text) VALUES ('a-source',0,0,30,'Needle passage')")
        key = "a-source".encode().hex()
        assert idx.search_clips("Needle", video_id="a-source")
        assert idx.search_clips(key) == []
        with idx._conn:
            idx._conn.execute("UPDATE clips SET video_id='b-source', text='Changed passage' WHERE video_id='a-source'")
        assert idx.search_clips("Needle", video_id="a-source") == []
        assert idx.search_clips("Changed", video_id="a-source") == []
        assert idx.search_clips("Changed", video_id="b-source")
        with idx._conn:
            idx._conn.execute("DELETE FROM clips WHERE video_id='b-source'")
        assert idx.search_clips("Changed", video_id="b-source") == []


def test_common_mention_work_is_bounded_by_page(dense):
    with sql_work(dense) as work:
        rows = dense.find_mentions("YouTube", 10)
    assert len(rows) == 10 and all(row["passage_verified"] for row in rows)
    assert work["steps"] < 45_000, work["steps"]
    plans = [row[3] for sql in work["sql"] if sql.startswith("WITH page_contexts")
             for row in dense._conn.execute("EXPLAIN QUERY PLAN " + sql)]
    assert any("SEARCH c USING INDEX" in row and "video_id=?" in row for row in plans), plans


@pytest.mark.parametrize("offset", [0, 20, 220])
def test_source_page_matches_exhaustive_order(dense, offset):
    prefix, params = index._fts_hits("yoinks_fts", "w3 w50", "forgiving", dense._YOINKS_BM25_WEIGHTS)
    expected = [r[0] for r in dense._conn.execute(prefix +
        "SELECT video_id FROM search_hits ORDER BY _score, video_id LIMIT 7 OFFSET ?", [*params, offset])]
    result = dense.search_yoinks_for_memory(q="w3 w50", limit=7, offset=offset, passages=False)
    assert result["total"] == 256
    assert [r["video_id"] for r in result["results"]] == expected


def test_four_library_queries_allow_capture_while_ranking(dense, monkeypatch):
    reader = library_resources.LibraryReader(dense, data_root=dense._path.parent)
    entered, release, captured = threading.Event(), threading.Event(), threading.Event()
    original = dense.search_clips
    def ranking(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(dense, "search_clips", ranking)
    def capture():
        with dense._lock:
            captured.set()
    with ThreadPoolExecutor(max_workers=5) as pool:
        calls = [pool.submit(reader.search, "w3 w50 w400", 5, mode="keyword") for _ in range(4)]
        try:
            assert entered.wait(2)
            writer = pool.submit(capture)
            available = captured.wait(.25)
        finally:
            release.set()
        results = [call.result(timeout=5) for call in calls]
        writer.result(timeout=5)
    assert available, "ranking held the capture lock"
    assert all(row["ok"] and len(row["hits"]) == 5 for row in results)


@pytest.mark.parametrize("verified", [True, False])
def test_mention_stored_timestamp_and_link_are_legacy_fields(dense, verified):
    dense.record_entities("source0000", [{"name": "YouTube", "type": "product", "mentions": [
        {"timestamp": 999.0, "context": "w50 w400 YouTube evidence" if verified else "An invented YouTube quote"}]}])
    row = dense.find_mentions("YouTube", 1)[0]
    assert row["timestamp"] == 999.0
    assert row["deep_link"] == "https://youtube.com/watch?v=source0000&t=999s"
    assert row["passage_verified"] is verified
    if verified:
        assert row["timestamp_seconds"] == 0
    else:
        assert "timestamp_seconds" not in row


def test_v1_default_has_full_total_and_pages_beyond_semantic_pool(dense):
    dense._local_search = SimpleNamespace(enabled=True, embedding_search=lambda *a, **k: [],
        status=lambda: {"acceptance": True, "paused": False, "state": "ready"})
    provider = corpus_provider.UoinkCorpusProvider(dense, dense._path.parent)
    result = provider.search(corpus_contract.SearchRequest.from_query({"q": ["w50"], "offset": ["220"], "limit": ["7"]}))
    assert result["page"]["total"] == 256
    assert len(result["items"]) == 7
    assert set(result) == {"items", "page"}


def test_v1_without_details_does_no_passage_work(dense, monkeypatch):
    monkeypatch.setattr(dense, "_search_passages", lambda *a: pytest.fail("v1 discarded passage work"))
    provider = corpus_provider.UoinkCorpusProvider(dense, dense._path.parent)
    assert provider.search(corpus_contract.SearchRequest(q="w50"))["items"]


@pytest.mark.parametrize("surface", ["search_uoinks", "search_clips"])
def test_public_score_preserves_underlying_order(dense, monkeypatch, surface):
    monkeypatch.setattr(uoink_mcp_tools, "_backend", SimpleNamespace(_get_index=lambda: dense))
    rows = getattr(uoink_mcp_tools, surface)({"query": "w3 w50", "mode": "keyword", "limit": 50})["results"]
    scores = [row["score"] for row in rows]
    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) > 1, scores


@pytest.mark.parametrize("wrapped", [True, False])
def test_stdio_does_not_retry_helper_deadline(tmp_path, monkeypatch, wrapped):
    error = {"ok": False, "error": {"code": "deadline_exceeded", "retryable": True}}
    backend = SimpleNamespace(DATA_ROOT=tmp_path,
        _call_http_registry_tool=lambda *a, **k: {"ok": True, "result": error} if wrapped else error)
    monkeypatch.setattr(ls.LocalSearch, "enabled_at", lambda root: True)
    result = uoink_agent_runtime.dispatch_search("search_library", {}, backend,
        lambda: pytest.fail("deadline was retried locally"), running=lambda: True)
    assert result == error


def test_stdio_does_not_retry_transport_timeout(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutError()
    backend = SimpleNamespace(DATA_ROOT=tmp_path, _call_http_registry_tool=timeout)
    monkeypatch.setattr(ls.LocalSearch, "enabled_at", lambda root: True)
    result = uoink_agent_runtime.dispatch_search("search_clips", {}, backend,
        lambda: pytest.fail("transport deadline was retried"), running=lambda: True)
    assert result["error"]["code"] == "deadline_exceeded"


def test_deadline_interrupt_is_not_query_rejection(dense, caplog):
    context = dense.search_read() if hasattr(dense, "search_read") else __import__('contextlib').nullcontext(dense._conn)
    with context as db:
        db.set_progress_handler(lambda: 1, 1)
        try:
            with pytest.raises(sqlite3.OperationalError, match="interrupted"):
                dense.search_clips("w3 w50", 20)
        finally:
            db.set_progress_handler(None, 0)
    assert "deadline exceeded" in caplog.text
    assert "query rejected" not in caplog.text and "rejected query" not in caplog.text


def test_semantic_query_falls_back_while_snapshot_refreshes(semantic_db, monkeypatch):
    idx, engine, _ = semantic_db
    seed(idx, "mars", "Mars rusty soil")
    ready(semantic_db)
    idx.record_entities("mars", [{"name": "Mars", "mentions": [{"context": "Mars"}]}])
    entered, release = threading.Event(), threading.Event()
    original = engine.sources._snapshot
    def slow_snapshot(**kwargs):
        entered.set()
        assert release.wait(3)
        return original(**kwargs)
    monkeypatch.setattr(engine.sources, "_snapshot", slow_snapshot)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(idx.search_mode, "rusty").result(timeout=1)
            assert result["search_mode"] == "keyword" and result["results"]
            assert entered.wait(1)
            again = pool.submit(idx.search_mode, "rusty").result(timeout=1)
            assert again["search_mode"] == "keyword"
    finally:
        release.set()
        worker = getattr(engine.sources, "_refresh_worker", None)
        if worker is not None:
            worker.join(5)
    monkeypatch.setattr(engine.sources, "_snapshot", original)
    assert idx.search_mode("rusty")["search_mode"] == "hybrid"
