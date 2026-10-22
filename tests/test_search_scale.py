"""Offline regression checks for Lane S pass 5 query work and wire contracts."""
from contextlib import contextmanager
import json
import re
import threading
from types import SimpleNamespace

import pytest

import corpus_contract
import index
import library_resources
import server
import uoink_agent_runtime
from tests.test_semantic_search import db, ready, request
from tests.test_smarter_search import seed
from uoink_core import local_search as ls


def count_snippets(idx):
    """Wrap real FTS snippets, whose xFindFunction overrides scalar mocks."""
    calls = []
    class ObservedConnection:
        def __init__(self, conn):
            self.conn = conn
        def execute(self, sql, *args):
            sql = re.sub(r"snippet\([^)]*\)", r"observe_snippet(\g<0>)", sql)
            return self.conn.execute(sql, *args)
        def __getattr__(self, name):
            return getattr(self.conn, name)
    original = idx.search_read
    @contextmanager
    def observed(**kwargs):
        with original(**kwargs) as conn:
            conn.create_function("observe_snippet", 1, lambda text: calls.append(text) or text)
            yield ObservedConnection(conn)
    idx.search_read = observed
    return calls


def trace_search(idx, statements):
    callback = lambda sql: statements.append(sql) if not sql.startswith("--") else None
    idx._conn.set_trace_callback(callback)
    original = idx.search_read
    @contextmanager
    def observed(**kwargs):
        with original(**kwargs) as conn:
            conn.set_trace_callback(callback)
            yield conn
    idx.search_read = observed


@pytest.fixture
def library(tmp_path):
    with index.Index.open(tmp_path / "index.db") as idx:
        with idx._conn:
            for number in range(80):
                vid = f"source{number:03}"
                idx._conn.execute("INSERT INTO yoinks(video_id, slug, title, channel, yoinked_at, corpus_path, sidecar_path) VALUES (?,?,?,?,?,'','')",
                                  (vid, vid, "Saved source", "Channel", "2026-10-21"))
                idx._conn.execute("INSERT INTO yoinks_fts(video_id, content) VALUES (?,?)",
                                  (vid, "Retention is about the viewer. " * 20))
                idx._conn.executemany("INSERT INTO clips(video_id, seq, start, end, text) VALUES (?,?,?,?,?)",
                                     [(vid, n, n * 30, n * 30 + 20, "Retention helps the viewer.") for n in range(12)])
        yield idx


@pytest.mark.parametrize("match", ["strict", "forgiving"])
@pytest.mark.parametrize("surface", ["search", "memory", "dashboard"])
def test_passage_queries_and_snippets_are_bounded_by_page(library, match, surface):
    statements = []
    trace_search(library, statements)
    # Count actual snippet invocations, not occurrences in SQL text. The old
    # materialized CTE invoked this for every candidate, including strict mode.
    snippets = count_snippets(library)
    if surface == "search":
        rows = library.search("retention", 7, match=match)
    elif surface == "memory":
        rows = library.search_yoinks_for_memory(q="retention", limit=7, offset=9, match=match)["results"]
    else:
        rows = server._library_search(library, q="retention", filters={}, kind=None, sort="relevance",
                                      limit=7, offset=9, match=match, mode="keyword")["results"]
    assert len(rows) == 7 and all(row["passage_verified"] for row in rows)
    clip_queries = [sql for sql in statements if sql.startswith("WITH clip_page")]
    assert len(clip_queries) == 1
    assert "scoped_clips" in clip_queries[0]
    assert len(snippets) == 7
    assert not any("SELECT content FROM yoinks_fts WHERE video_id=" in sql for sql in statements)


@pytest.mark.parametrize("match", ["strict", "forgiving"])
def test_grouped_clips_extract_only_returned_snippets(library, match):
    snippets = count_snippets(library)
    rows = library.search_clips("retention viewer", 4, match=match, group_sources=True)
    assert len(rows) == len({row["video_id"] for row in rows}) == 4
    assert len(snippets) == 4


@pytest.mark.parametrize("grouped", [False, True])
def test_clip_exact_title_priority_and_seq_ties(db, grouped):
    idx, _, _ = db
    seed(idx, "first", "retention " * 20, title="Unrelated", timed=True)
    seed(idx, "title", "Retention evidence", title="Retention", timed=True)
    assert idx.search_clips("retention", 1, group_sources=grouped)[0]["video_id"] == "title"
    # Insertion order and clip_id must not stand in for seq on equal scores.
    with idx._lock, idx._conn:
        idx._conn.execute("DELETE FROM clips WHERE video_id='title'")
        idx._conn.executemany("INSERT INTO clips(video_id, seq, start, end, text) VALUES ('title',?,?,?,?)",
                             [(9, 90, 99, "Retention evidence"), (1, 10, 19, "Retention evidence")])
    row = idx.search_clips("retention", 1, group_sources=grouped)[0]
    assert row["video_id"] == "title" and row["start"] == 10


@pytest.mark.parametrize("query", ["missing retention viewer", "retention viewer missing", "absent missing retention viewer"])
def test_partial_rank_stream_preserves_exhaustive_results_and_score_ties(library, monkeypatch, query):
    # The lowest source IDs and sequence numbers arrive last in the FTS tie.
    with library._conn:
        library._conn.execute("DELETE FROM clips")
        library._conn.executemany("INSERT INTO clips(video_id,seq,start,end,text) VALUES (?,?,?,?,?)",
            [(f"source{n:03}", seq, seq * 30, seq * 30 + 20, "Retention viewer")
             for n in reversed(range(80)) for seq in (9, 1)])
    streamed = library.search_clips(query, 7, group_sources=True)
    exhaustive = library.search_clips(query, 7, group_sources=True, _video_ids=sorted(library.all_video_ids()))
    assert [(row["clip_id"], row["_score"]) for row in streamed] == [
        (row["clip_id"], row["_score"]) for row in exhaustive]
    assert [row["video_id"] for row in streamed] == [f"source{n:03}" for n in range(7)]


def test_memory_page_counts_once_and_keeps_total_past_last_page(library):
    statements = []
    trace_search(library, statements)
    page = library.search_yoinks_for_memory(q="retention", limit=7, offset=10)
    assert page["total"] == 80 and len(page["results"]) == 7
    assert all("_total" not in row for row in page["results"])
    assert not any("SELECT COUNT(*) AS n FROM search_hits" in sql for sql in statements)
    assert library.search_yoinks_for_memory(q="retention", offset=100)["total"] == 80


def test_global_clip_rank_uses_covering_metadata_index(library):
    statements = []
    trace_search(library, statements)
    library.search_clips("retention", 5)
    library._conn.set_trace_callback(None)
    sql = next(sql for sql in statements if "idx_clips_search_metadata" in sql)
    plan = [row[3] for row in library._conn.execute("EXPLAIN QUERY PLAN " + sql)]
    assert any("COVERING INDEX idx_clips_search_metadata" in line for line in plan), plan


@pytest.mark.parametrize("query", ["retention", "missing retention viewer", "viewer retention", "Saved source"])
def test_source_score_bound_is_conservative(library, query):
    rows = library.search(query, 80)
    bound = library.source_score_lower_bound(query)
    assert all(bound <= row["_score"] for row in rows)


def test_library_skips_source_scan_only_when_clip_page_must_win(db, monkeypatch):
    idx, _, _ = db
    for number in range(10):
        vid = f"source{number:03}"
        seed(idx, vid, "Retention evidence", timed=True)
    with idx._conn:
        idx._conn.executemany("INSERT INTO clips(video_id,seq,text) VALUES (?,?,?)",
                              [(f"source{number:03}", n, "Unrelated filler")
                               for number in range(10) for n in range(1, 10)])
    original = idx.search
    calls = []
    monkeypatch.setattr(idx, "search", lambda *a, **k: calls.append(True) or original(*a, **k))
    reader = library_resources.LibraryReader(idx, data_root=idx._path.parent)
    page = reader.search("retention", 5, mode="keyword")
    assert len(page["hits"]) == 5 and not calls
    with idx._conn:
        idx._conn.execute("UPDATE yoinks SET title='Retention' WHERE video_id='source009'")
    page = reader.search("retention", 5, mode="keyword")
    assert calls and page["hits"][0]["item_id"] == "source009"


@pytest.mark.parametrize("match", ["strict", "forgiving"])
def test_page_clip_plan_uses_video_index_and_one_bounded_fts_cursor(library, match):
    prefix, args = index._fts_hits("clips_fts", "retention viewer", match, video_ids=["source001", "source070"])
    plan = [row[3] for row in library._conn.execute("EXPLAIN QUERY PLAN " + prefix + "SELECT * FROM search_hits", args)]
    assert any("SEARCH clips USING" in line and "video_id=?" in line for line in plan), plan
    assert any("VIRTUAL TABLE" in line and "><" in line for line in plan), plan
    assert "snippet(" not in prefix
    assert not any("f.video_id=y.video_id" in line for line in plan)


@pytest.mark.parametrize("fails", [False, True])
def test_dashboard_hybrid_pool_and_fallback_materialize_only_final_page(library, monkeypatch, fails):
    snippets = count_snippets(library)
    def embedding_search(*args, **kwargs):
        if fails:
            raise RuntimeError("temporary")
        return []
    library._local_search = SimpleNamespace(enabled=True, embedding_search=embedding_search,
        status=lambda: {"acceptance": True, "paused": False, "state": "ready"})
    pages, statements = [], []
    original = library._search_passages
    monkeypatch.setattr(library, "_search_passages", lambda rows, *args: pages.append(len(rows)) or original(rows, *args))
    trace_search(library, statements)
    result = server._library_search(library, q="retention", filters={}, kind=None,
                                     sort="relevance", limit=5, offset=10, mode="hybrid")
    assert pages == [5]
    assert len(snippets) == 5
    assert len(result["results"]) == 5
    assert result["search_mode"] == ("keyword" if fails else "hybrid")
    assert sum(sql.startswith("WITH clip_page") for sql in statements) == 1
    assert sum("SELECT COUNT(*) AS n FROM" in sql for sql in statements) == 1


def test_snapshot_scans_fts_once_and_does_not_hold_capture_lock(library, monkeypatch):
    statements = []
    original_snapshot = library.detached_snapshot
    @contextmanager
    def observed():
        with original_snapshot() as conn:
            conn.set_trace_callback(lambda sql: statements.append(sql) if not sql.startswith("--") else None)
            yield conn
    monkeypatch.setattr(library, "detached_snapshot", observed)
    entered, release, wrote = threading.Event(), threading.Event(), threading.Event()
    original_source = ls.Source
    def hold_source(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original_source(*args, **kwargs)
    monkeypatch.setattr(ls, "Source", hold_source)
    reader = ls.IndexSources(library)
    errors = []
    def snapshot():
        try:
            reader.snapshot()
        except Exception as error:
            errors.append(error)
    worker = threading.Thread(target=snapshot)
    worker.start()
    def capture():
        with library._lock, library._conn:
            library._conn.execute("UPDATE yoinks SET title='Captured during snapshot' WHERE video_id='source001'")
        wrote.set()
    writer = threading.Thread(target=capture)
    try:
        assert entered.wait(3)
        writer.start()
        assert wrote.wait(1), "snapshot held Index._lock and blocked a capture"
    finally:
        release.set()
        worker.join(3)
        if writer.ident is not None:
            writer.join(3)
    assert not errors
    assert sum("SELECT video_id, content FROM yoinks_fts" in sql for sql in statements) == 1
    assert not any("JOIN yoinks_fts" in sql for sql in statements)
    assert next(s for s in reader.snapshot() if s.source_id == "source001").title == "Captured during snapshot"


def test_library_semantic_work_does_not_inherit_capture_lock(db, monkeypatch):
    idx, engine, _ = db
    seed(idx, "mars", "Mars rusty soil")
    ready(db)
    entered, release, wrote = threading.Event(), threading.Event(), threading.Event()
    def embed(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return []
    monkeypatch.setattr(engine, "embedding_search", embed)
    reader = library_resources.LibraryReader(idx, data_root=idx._path.parent)
    results = []
    worker = threading.Thread(target=lambda: results.append(reader.search("rusty")))
    def capture():
        with idx._lock:
            wrote.set()
    writer = threading.Thread(target=capture)
    worker.start()
    try:
        assert entered.wait(2)
        writer.start()
        assert wrote.wait(0.5), "library wrapper held Index._lock across semantic work"
    finally:
        release.set()
        worker.join(3)
        if writer.ident is not None:
            writer.join(3)
    assert results and results[0]["search_mode"] == "hybrid"


def test_library_semantic_fallback_uses_keyword_candidates_once(db, monkeypatch):
    idx, engine, _ = db
    seed(idx, "mars", "Mars rusty soil", timed=True)
    ready(db)
    def fail(*args, **kwargs):
        raise RuntimeError("temporary")
    monkeypatch.setattr(engine, "embedding_search", fail)
    original = idx.search
    calls = []
    monkeypatch.setattr(idx, "search", lambda *a, **k: calls.append(True) or original(*a, **k))
    result = library_resources.LibraryReader(idx, data_root=idx._path.parent).search("rusty")
    assert result["search_mode"] == "keyword" and result["hits"]
    assert calls == [True]


def test_long_library_query_ranks_sources_and_fetches_clips_once(library):
    statements = []
    trace_search(library, statements)
    query = "retention viewer pacing editing thumbnails narrative audience hook"
    result = library_resources.LibraryReader(library, data_root=library._path.parent).search(query, 5, mode="keyword")
    assert len(result["hits"]) == 5
    assert sum("ORDER BY yoinks_fts.rank" in sql and " OR " in sql for sql in statements) == 1
    assert sum(sql.startswith("WITH clip_page") for sql in statements) == 1


def test_find_mentions_batches_content_and_requires_entity_in_the_passage(db):
    idx, _, _ = db
    for vid, content, timed in [("wrong", "A shared context without the entity.", True),
                                ("text", "Lunar Lander is the source context.", False),
                                ("clip", "Lunar Lander is the source context.", True)]:
        seed(idx, vid, content, timed=timed)
        idx.record_entities(vid, [{"name": "Lunar Lander", "type": "topic",
                                   "mentions": [{"timestamp": 999, "context": content}]}])
    statements = []
    trace_search(idx, statements)
    rows = {row["video_id"]: row for row in idx.find_mentions("Lunar Lander", 200)}
    assert rows["wrong"]["passage_verified"] is False and rows["wrong"]["citation_reason"]
    assert rows["wrong"]["timestamp"] == 999 and "timestamp_seconds" not in rows["wrong"]
    assert rows["wrong"]["deep_link"].endswith("&t=999s")
    assert rows["text"]["passage_verified"] is True and rows["text"]["timestamp"] == 999
    assert rows["text"]["timestamp_seconds"] is None
    assert rows["clip"]["passage_verified"] is True and rows["clip"]["timestamp_seconds"] == 12.5
    assert sum(sql.startswith("SELECT video_id, content FROM yoinks_fts") for sql in statements) == 1
    # Quotes naming the entity can stop at their first matching clip. Other
    # annotations use a second batch to find a clip containing the entity.
    assert 1 <= sum(sql.startswith("WITH page_contexts") for sql in statements) <= 2


def test_mention_name_is_ranked_once_before_expanding_rows(library):
    for vid in sorted(library.all_video_ids()):
        library.record_entities(vid, [{"name": "Lunar Lander", "type": "topic",
                                      "mentions": [{"context": "Not quoted"}]}])
    calls = []
    with library.search_read() as conn:
        conn.create_function("entity_keyword_score", 2,
            lambda name, query: calls.append(name) or index._entity_keyword_score(name, query))
        assert len(library.find_mentions("Lunar Lander", 80)) == 80
    assert len(calls) <= 2


@pytest.mark.parametrize("promote", [False, True])
def test_pure_name_keys_stay_cached_after_capture_promotes_a_reader(library, monkeypatch, promote):
    calls = []
    title_key, entity_score = index._search_title_key, index._entity_keyword_score
    monkeypatch.setattr(index, "_search_title_key", lambda title: calls.append("title") or title_key(title))
    monkeypatch.setattr(index, "_entity_keyword_score", lambda name, query: calls.append("entity") or entity_score(name, query))
    with index.Index.open_existing(library._path) as reader:
        if promote:
            reader.initialize_for_write()
        for _ in range(2):
            row = reader._conn.execute("SELECT search_title_key(?), entity_keyword_score(?, ?)",
                                       ("Lunar Lander", "Lunar Lander", "lander")).fetchone()
            assert tuple(row) == ("lunarlander", 1)
    assert calls == ["title", "entity"]


@pytest.mark.parametrize("name", ["search_library", "search_uoinks", "search_clips"])
def test_stdio_consumes_actual_tools_http_envelope(db, monkeypatch, name):
    idx, _, _ = db
    seed(idx, "mars", "Mars rusty soil", timed=True)
    ready(db)
    monkeypatch.setattr(server, "_get_existing_index", lambda **kwargs: idx)
    def remote(tool, args, *, timeout):
        assert timeout >= 2.0
        response = request("POST", "/tools/" + tool, args)
        assert response.status == 200
        assert response.payload["ok"] and response.payload["result"]["search_mode"] == "hybrid"
        return response.payload
    monkeypatch.setattr(server, "_call_http_registry_tool", remote)
    result = uoink_agent_runtime.dispatch_search(name, {"query": "rusty"}, server,
                                                lambda: pytest.fail("unwrapped result was discarded"), running=lambda: True)
    assert result["search_mode"] == "hybrid" and not result["fallback_reason"]


ITEM_KEYS = b'["author","captured_at","credit","duration_seconds","facets","id","platform","preview","source_type","source_url","title"]'
def key_bytes(value):
    return json.dumps(sorted(value), separators=(",", ":")).encode()


@pytest.mark.parametrize("query", ["", "?q=rusty", "?q=rusty&mode=hybrid", "?q=rusty&search_details=false"])
def test_v1_http_keys_remain_byte_for_byte_exact(db, query):
    idx, _, _ = db
    seed(idx, "mars", "Mars rusty soil")
    ready(db)
    response = request("GET", "/api/corpus/v1/search" + query)
    assert response.status == 200
    data = response.payload["data"]
    assert key_bytes(data) == b'["items","page"]'
    assert key_bytes(data["items"][0]) == ITEM_KEYS
    corpus_contract.validate_data("search", data)
    detail = request("GET", "/api/corpus/v1/items/mars").payload["data"]
    assert key_bytes(detail["item"]) == ITEM_KEYS
    for key in ("source_id", "passage_verified", "citation_reason", "passage", "span", "timestamp_seconds", "passage_id"):
        with pytest.raises(corpus_contract.ContractError):
            corpus_contract.validate_item_ref({**detail["item"], key: None})
    for key in ("search_mode", "requested_mode", "fallback_reason"):
        with pytest.raises(corpus_contract.ContractError):
            corpus_contract.validate_data("search", {**data, key: None})


def test_corpus_details_require_explicit_opt_in_and_browse_has_no_citations(db):
    idx, _, _ = db
    seed(idx, "mars", "Mars rusty soil")
    ready(db)
    detail = request("GET", "/api/corpus/v1/search?q=rusty&search_details=true").payload["data"]
    assert detail["search_mode"] == "keyword" and detail["items"][0]["passage_verified"]
    corpus_contract.validate_data("search", detail, search_details=True)
    browse = request("GET", "/api/corpus/v1/search?search_details=true").payload["data"]
    assert key_bytes(browse["items"][0]) == ITEM_KEYS
    for row in idx.search_mode(None)["results"]:
        assert not any(key in row for key in ("passage_verified", "citation_reason", "source_id"))
    with pytest.raises(corpus_contract.ContractError):
        corpus_contract.SearchRequest.from_query({"search_details": "yes"})


def test_rebuild_clips_notifies_vectors(db):
    idx, _, _ = db
    seed(idx, "mars", "Mars rusty soil", timed=True)
    changed = []
    idx._source_change_callback = changed.append
    idx.rebuild_clips()
    assert changed == ["mars"]


def test_pause_survives_helper_restart_and_incremental_totals_cover_library(db, monkeypatch):
    idx, engine, _ = db
    seed(idx, "mars", "Mars rusty soil")
    seed(idx, "bread", "Bread recipe")
    ready(db)
    seed(idx, "mars", "Mars updated rusty soil")
    assert engine.wait(5)
    assert engine.status()["done"] == engine.status()["total"] == 2
    engine.pause()
    restarted = ls.LocalSearch(engine.root, idx)
    assert restarted.status()["paused"] is True
    monkeypatch.setattr(server, "_get_local_search", lambda: restarted)
    monkeypatch.setattr(restarted, "start", lambda: pytest.fail("persisted pause was lost"))
    server._resume_local_search()


@pytest.mark.parametrize("action", ["pause", "remove"])
def test_capture_callback_does_not_wait_for_control_join(db, action):
    idx, engine, _ = db
    seed(idx, "mars", "Mars rusty soil")
    ready(db)
    entered, release, updated = threading.Event(), threading.Event(), threading.Event()
    original = engine._model.embed
    def slow_embed(*args, **kwargs):
        entered.set()
        assert release.wait(4)
        return original(*args, **kwargs)
    engine._model.embed = slow_embed
    seed(idx, "mars", "Changed Mars rusty soil")
    assert entered.wait(3)
    controller = threading.Thread(target=getattr(engine, action))
    controller.start()
    def capture():
        engine.update_source("queued")
        updated.set()
    writer = threading.Thread(target=capture)
    try:
        assert engine._stop.wait(3)
        writer.start()
        assert updated.wait(0.5), "capture waited for the model worker join"
        if action == "pause":
            assert "queued" in engine._pending
    finally:
        release.set()
        controller.join(5)
        writer.join(5)
        engine.wait(5)


def test_transient_embedding_failure_retries_with_backoff(db, monkeypatch):
    idx, engine, _ = db
    seed(idx, "mars", "Mars rusty soil")
    ready(db)
    now = [100.0]
    monkeypatch.setattr(ls.time, "monotonic", lambda: now[0])
    original = engine._model.embed
    calls = []
    def fail(*args, **kwargs):
        calls.append(True)
        raise RuntimeError("transient private message")
    monkeypatch.setattr(engine._model, "embed", fail)
    assert idx.search_mode("rusty")["search_mode"] == "keyword"
    assert engine.status()["state"] == "retrying"
    now[0] += 0.5
    assert idx.search_mode("rusty")["search_mode"] == "keyword" and len(calls) == 1
    now[0] += 0.6
    assert idx.search_mode("rusty")["search_mode"] == "keyword" and len(calls) == 2
    now[0] += 1.5
    assert idx.search_mode("rusty")["search_mode"] == "keyword" and len(calls) == 2
    monkeypatch.setattr(engine._model, "embed", original)
    now[0] += 0.6
    assert idx.search_mode("rusty")["search_mode"] == "hybrid"
    assert engine.status()["state"] == "ready"


def test_search_status_has_its_own_rate_budget(db, monkeypatch):
    monkeypatch.setattr(server, "_check_memory_search_rate_limit", lambda: False)
    monkeypatch.setattr(server, "_search_status_request_times", [])
    assert all(request("GET", "/search/status").status == 200 for _ in range(180))
    assert request("GET", "/search/status").status == 429
    assert request("GET", "/memory/search?q=rusty").status == 429
