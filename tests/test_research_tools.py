"""Research tools through the registry and backend, with no live helper."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest

import openapi_bridge
import research
import uoink_cli
import uoink_connect
import uoink_mcp_tools as tools
from tests.test_c01_mcp_stdio import CORE_STDIO_TOOLS
from tests.test_research_discovery import fixture


@pytest.fixture
def backend(tmp_path, monkeypatch):
    # Also safe when this file is run by itself, before server is imported.
    (tmp_path / "profile").mkdir()
    (tmp_path / "app").mkdir()
    monkeypatch.setenv("UOINK_ISOLATED_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setenv("UOINK_ISOLATED_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("UOINK_ISOLATED_PORT", "18123")
    monkeypatch.setenv("UOINK_OUTPUT_DIR", str(tmp_path / "output"))
    import server

    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(server, "_get_index", lambda: SimpleNamespace(
        search_mode=lambda *a, **k: {"results": []}, get_yoink=lambda video_id: None))
    monkeypatch.setattr(server._platform, "media_capability", lambda: {"available": True})
    monkeypatch.setattr(server, "_run_subprocess", lambda *a, **k: SimpleNamespace(stdout=json.dumps(fixture("ytsearch_evals.json"))))
    monkeypatch.setattr(research, "fetch_hn", lambda q, n: fixture("hn_search_evals.json"))
    monkeypatch.setattr(research, "fetch_itunes", lambda q, n: fixture("itunes_episodes.json"))
    monkeypatch.setattr(research, "fetch_hackertube", lambda: fixture("hackertube_list.json"))
    monkeypatch.setattr(research.time, "sleep", lambda n: None)
    def no_network(*args, **kwargs):
        pytest.fail("Research tool tests must not access the network")
    monkeypatch.setattr(research.urllib.request, "urlopen", no_network)
    monkeypatch.setattr(tools, "_backend", SimpleNamespace(
        _research_start=server._research_start, _research_discover=server._research_discover))
    for name in ("research_start", "research_discover"):
        monkeypatch.setattr(tools.TOOL_REGISTRY[name].rate_limiter, "_calls", [])
    return server


def test_start_discover_persist_and_merge(tmp_path, backend, monkeypatch):
    result = tools.call_tool("research_start", {"question": "  agent evals  "})
    assert result["ok"] and result["scope"]["question"] == "agent evals"
    assert result["needs_consent"] == ["youtube", "podcast", "hn", "hackertube"]
    assert "untrusted_content" in result
    run_id = result["run_id"]
    assert research.load_run(tmp_path, run_id)["candidates"] == []
    backend._write_settings({"research_network_sources": ["youtube"]})
    first = tools.call_tool("research_discover", {"run_id": run_id, "queries": ["agent evals"]})
    assert first["ok"] and len(first["candidates"]) == 5
    assert "untrusted_content" in first and first["capped_by_channel"] == 1
    stored = research.load_run(tmp_path, run_id)
    assert stored["candidates"] == first["candidates"]
    assert stored["discover_calls"][0]["queries"] == ["agent evals"]
    assert stored["discover_calls"][0]["timestamp"].endswith("Z")
    # A later search adds a source and HN signals without losing earlier candidates.
    backend._write_settings({"research_network_sources": ["hn"]})
    second = tools.call_tool("research_discover", {"run_id": run_id, "queries": ["evals talks"]})
    assert second["ok"] and not second["errors"]
    assert {c["key"] for c in first["candidates"]} <= {c["key"] for c in second["candidates"]}
    merged = next(c for c in second["candidates"] if c["key"] == "yt:evaltalk001")
    assert merged["signals"]["hn_points"] == 140
    assert merged["signals"]["found_by"] == [
        {"source": "youtube", "query": "agent evals"}, {"source": "hn", "query": "evals talks"}]
    assert len(research.load_run(tmp_path, run_id)["discover_calls"]) == 2
    assert not list((tmp_path / "research").glob("**/*.tmp"))


@pytest.mark.parametrize("name,args", [
    ("research_start", {"question": "evals", "research_network_sources": ["youtube"]}),
    ("research_start", {"question": "evals", "source_kinds": ["hn", "hn"]}),
    ("research_start", {"question": "x" * 501}),
    ("research_start", {"question": "evals", "max_sources": True}),
    ("research_start", {"question": "evals", "since": "2026-02-30"}),
    ("research_discover", {"run_id": "../outside", "queries": ["evals"]}),
    ("research_discover", {"run_id": "rr_20261103000000_aabbccdd", "queries": ["evals"] * 9}),
    ("research_discover", {"run_id": "rr_20261103000000_aabbccdd", "queries": [" "]}),
    ("research_discover", {"run_id": "rr_20261103000000_aabbccdd", "queries": ["x" * 201]}),
    ("research_discover", {"run_id": "rr_20261103000000_aabbccdd", "queries": ["evals"], "per_query": 21}),
    ("research_discover", {"run_id": "rr_20261103000000_aabbccdd", "queries": ["evals"], "consent": True}),
])
def test_invalid_schema_never_calls_backend(tmp_path, backend, monkeypatch, name, args):
    calls = []
    monkeypatch.setattr(tools._backend, "_" + name, lambda args: calls.append(args))
    result = tools.call_tool(name, args)
    assert result["ok"] is False and result["code"]
    assert calls == [] and not (tmp_path / "research").exists()


def test_missing_run_has_normal_error_envelope(backend):
    assert tools.call_tool("research_discover", {
        "run_id": "rr_20261103000000_aabbccdd", "queries": ["evals"]}) == {
        "ok": False, "error": "Research run not found.", "code": "not_found"}


def test_rate_limit_and_malformed_arguments_have_codes(backend, monkeypatch):
    assert tools.call_tool("research_start", ["invalid"])["code"] == "invalid_arguments"
    limiter = tools.TOOL_REGISTRY["research_start"].rate_limiter
    def limited():
        raise tools.RateLimitExceeded("rate limit exceeded")
    monkeypatch.setattr(limiter, "check", limited)
    assert tools.call_tool("research_start", {"question": "evals"})["code"] == "rate_limited"


def test_large_discovery_response_fits_wire_without_mutating_saved_pool(backend, monkeypatch):
    candidates = [{"key": f"pod:{n:012x}", "title": '"' * 500, "description": "evals " * 600}
                  for n in range(60)]
    result = {"ok": True, "run_id": "rr_20261103000000_aabbccdd", "candidates": candidates,
              "by_source": {"podcast": 60}, "skipped": [], "errors": [], "capped_by_channel": 0}
    monkeypatch.setattr(tools._backend, "_research_discover", lambda args: result)
    envelope = tools.call_tool("research_discover", {"run_id": result["run_id"], "queries": ["evals"]})
    assert 0 < len(envelope["candidates"]) < 60
    assert envelope["candidates"] == candidates[:len(envelope["candidates"])]
    assert len(candidates) == 60 and envelope["omitted_candidates"] == 60 - len(envelope["candidates"])
    wire = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{
        "type": "text", "text": json.dumps(envelope, ensure_ascii=False)}], "isError": False}}
    assert len(json.dumps(wire, ensure_ascii=False).encode("utf-8")) < 65536


def test_settings_normalization_and_http_route(backend, monkeypatch):
    assert backend._default_settings()["research_network_sources"] == []
    assert backend._normalize_settings({"research_network_sources": "youtube"})["research_network_sources"] == []
    assert backend._normalize_settings({"research_network_sources": ["hn", "hn", "library", "other", {}, "youtube"]})["research_network_sources"] == ["youtube", "hn"]
    handler = object.__new__(backend.Handler)
    responses = []
    monkeypatch.setattr(handler, "_send_json", lambda status, data: responses.append((status, data)))
    monkeypatch.setattr(backend, "_public_settings", lambda data=None: backend._normalize_settings(data))
    handler._handle_settings_post_locked({"research_network_sources": ["hn", "library", "hn", "reddit"]})
    assert responses[-1][0] == 200 and responses[-1][1]["ok"]
    assert backend._read_settings()["research_network_sources"] == ["hn", "reddit"]
    start = tools.call_tool("research_start", {"question": "evals", "source_kinds": ["hn", "youtube", "reddit"]})
    assert start["needs_consent"] == ["youtube"]
    handler._handle_settings_post_locked({"research_network_sources": "all"})
    assert responses[-1][0] == 400


def test_backend_search_shapes_metadata(backend, monkeypatch):
    calls = []
    def search(q, n, mode, passages):
        calls.append((q, n, mode, passages))
        return {"results": [{"video_id": "evaltalk001", "title": "evals", "channel": "Systems Forum",
            "metadata_json": json.dumps({"duration_seconds": 1800, "upload_date": "20261001",
                                         "url": "https://youtu.be/evaltalk001"})}]}
    monkeypatch.setattr(backend, "_get_index", lambda: SimpleNamespace(search_mode=search))
    rows = backend._research_library_search("evals", 4)
    assert calls == [("evals", 4, "auto", False)]
    candidate = research.parse_library(rows)[0]
    assert candidate["key"] == "yt:evaltalk001" and candidate["in_library"]
    assert candidate["published"] == "2026-10-01" and candidate["duration_s"] == 1800


def test_youtube_runner_and_unavailable_error(backend, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps(fixture("ytsearch_evals.json")))
    monkeypatch.setattr(backend, "_run_subprocess", run)
    assert backend._research_ytsearch("evals", 7)["entries"]
    assert calls[0][0] == [*backend.YTDLP_CMD, "--dump-single-json", "--flat-playlist", "--", "ytsearch7:evals"]
    assert calls[0][1]["timeout"] == backend.COMMENTS_TIMEOUT_SEC
    monkeypatch.setattr(backend._platform, "media_capability", lambda: {"available": False})
    with pytest.raises(research.ResearchError) as error:
        backend._research_ytsearch("evals", 7)
    assert error.value.code == "unavailable" and len(calls) == 1


def test_toolsets_schemas_annotations_and_connect(capsys):
    expected = ("research_start", "research_discover", "uoink_url")
    assert tools.stdio_tool_names("research") == expected == tools.RESEARCH_STDIO_TOOLS
    assert len(expected) <= 10
    assert tools.stdio_tool_names()[:35] == CORE_STDIO_TOOLS
    assert len(tools.stdio_tool_names()) == len(tools.TOOL_REGISTRY) == 94
    assert tuple(tools.TOOL_REGISTRY)[-2:] == expected[:2]
    assert tools.stdio_tool_names()[-2:] == expected[:2]
    for name, rate, world in (("research_start", 20, False), ("research_discover", 10, True)):
        spec = tools.TOOL_REGISTRY[name]
        assert spec.input_schema["additionalProperties"] is False
        assert spec.rate_limiter.max_calls == rate
        assert spec.annotations == {"readOnlyHint": False, "destructiveHint": False,
                                    "idempotentHint": False, "openWorldHint": world}
        assert name in tools.OUTPUT_SCHEMAS and name in tools.UNTRUSTED_CONTENT_TOOL_NAMES
    assert tools.STDIO_TOOLSETS == uoink_cli.TOOLSETS == ("full", "core", "search", "research")
    assert uoink_cli.main(["tools", "--toolset", "research"]) == 0
    assert tuple(t["name"] for t in json.loads(capsys.readouterr().out)["tools"]) == expected
    entry = uoink_connect.server_entry("cursor", Path("/example/app"), Path("/example/python"), toolset="research")
    assert entry["env"]["UOINK_MCP_TOOLSET"] == "research"
    assert openapi_bridge.build_well_known("http://127.0.0.1:18123", version="test", tool_count=94)["stdio_toolsets"] == {
        "full": 94, "core": 35, "search": 8, "research": 3}


def test_wire_inventory_refresh_only_allows_appending():
    from tests.update_mcp_wire_goldens import refresh_inventory
    original = {"tools": [{"name": "old", "description": "unchanged"}], "protocol": {"fixed": True}}
    added = {"name": "research_start"}
    updated = refresh_inventory(original, [*original["tools"], added])
    assert updated["protocol"] == original["protocol"] and len(original["tools"]) == 1
    for tools_list in ([], [added, *original["tools"]], [{"name": "old", "description": "changed"}], original["tools"] * 2):
        with pytest.raises(AssertionError):
            refresh_inventory(original, tools_list)


@pytest.mark.parametrize("name", ["research_start", "research_discover"])
@pytest.mark.parametrize("args", [None, False, 0, "", [], ["invalid"], "invalid"])
def test_research_handlers_reject_non_objects_without_backend(backend, monkeypatch, name, args):
    def forbidden(*args):
        pytest.fail("Invalid arguments must not reach the backend")
    monkeypatch.setattr(tools._backend, "_" + name, forbidden)
    assert tools.TOOL_REGISTRY[name].handler(args) == {
        "ok": False, "error": "arguments must be an object", "code": "invalid_arguments"}
    # The shared dispatcher normalizes falsy values, but required research
    # fields still fail validation; its behavior for other tools is unchanged.
    assert tools.call_tool(name, args)["code"] == "invalid_arguments"


@pytest.mark.parametrize("argument,expected", [
    ("ytsearch:q", True), ("ytsearch10:q", True), ("ytsearchdate:q", True),
    ("ytsearchdate10:q", True), ("ytsearch10:-q", True),
    ("https://www.youtube.com/watch?v=evaltalk001", True),
    ("https://youtu.be/evaltalk001", True), ("ytsearchabc:q", False),
    ("prefixytsearch10:q", False), ("https://example.org/ytsearch10:q", False),
])
def test_ytsearch_arguments_use_youtube_network_slot(backend, argument, expected):
    assert backend._is_youtube_ytdlp_call(
        [*backend.YTDLP_CMD, "--dump-single-json", "--flat-playlist", "--", argument]) is expected
    assert not backend._is_youtube_ytdlp_call(["unrelated-tool", argument])


@pytest.mark.parametrize("message,code", [
    ("HTTP Error 429: Too Many Requests", "rate_limited"),
    ("Sign in to confirm you're not a bot", "rate_limited"),
    ("Could not fetch search results", "fetch_failed"),
])
def test_youtube_errors_map_to_safe_codes(backend, monkeypatch, message, code):
    def broken(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr=message)
    monkeypatch.setattr(backend, "_run_subprocess", broken)
    with pytest.raises(research.ResearchError) as error:
        backend._research_ytsearch("evals", 7)
    assert error.value.code == code
    assert str(error.value) == "YouTube search could not complete."


def test_disjoint_discoveries_keep_the_full_pool_and_all_query_relevance(tmp_path, backend, monkeypatch):
    backend._write_settings({"research_network_sources": ["youtube"]})
    run_id = backend._research_start({"question": "talks", "source_kinds": ["youtube"],
                                       "max_sources": 1})["run_id"]
    def fetch(query, limit):
        return {"entries": [{"id": f"{query}{i:06d}", "title": query} for i in range(5)]}
    monkeypatch.setattr(backend, "_research_ytsearch", fetch)
    first = backend._research_discover({"run_id": run_id, "queries": ["alpha"]})
    assert len(first["candidates"]) == 2
    first_pool = research.load_run(tmp_path, run_id)["candidates_pool"]
    assert len(first_pool) == 5
    second = backend._research_discover({"run_id": run_id, "queries": ["bravo"]})
    stored = research.load_run(tmp_path, run_id)
    pool = stored["candidates_pool"]
    assert len(pool) == 10 and len(second["candidates"]) == 2
    assert {c["key"] for c in first_pool} <= {c["key"] for c in pool}
    assert all(c["score"] > 0 for c in pool)  # Both disjoint queries contribute.
    expected, _ = research.rank_candidates(pool, ["alpha", "bravo"], stored["scope"],
                                           now=research._utc())
    assert second["candidates"] == expected
    assert "candidates_pool" not in second
    assert [c["queries"] for c in stored["discover_calls"]] == [["alpha"], ["bravo"]]


def test_existing_library_marks_remote_matches_in_worker(tmp_path, backend, monkeypatch):
    import index

    idx = index.Index.open(tmp_path / "index.db")
    try:
        idx.upsert_yoink({"video_id": "evaltalk001", "title": "evals saved", "slug": "saved", "yoinked_at": "2026-10-01T10:00:00", "corpus_path": str(tmp_path / "c.md"), "sidecar_path": str(tmp_path / "s.json"), "source_type": "video", "platform": "youtube"})
        idx.upsert_yoink({"video_id": "evaltalk002", "title": "evals deleted", "slug": "deleted", "yoinked_at": "2026-10-01T10:00:00", "corpus_path": str(tmp_path / "c.md"), "sidecar_path": str(tmp_path / "s.json"), "source_type": "video", "platform": "youtube"})
        idx.soft_delete_yoink("evaltalk002")
        monkeypatch.setattr(backend, "_get_index", lambda: idx)
        backend._write_settings({"research_network_sources": ["youtube"]})
        run_id = backend._research_start({"question": "evals", "source_kinds": ["youtube"]})["run_id"]
        with ThreadPoolExecutor(max_workers=1) as worker:
            result = worker.submit(backend._research_discover, {"run_id": run_id, "queries": ["evals"]}).result(10)
            # Exercise the library search's snapshot/locked access from the worker too.
            local = worker.submit(backend._research_library_search, "evals", 10).result(10)
        assert result["ok"] and not result["errors"]
        pool = {c["key"]: c for c in research.load_run(tmp_path, run_id)["candidates_pool"]}
        assert pool["yt:evaltalk001"]["in_library"] is True
        assert pool["yt:evaltalk001"]["est_capture"] == "captions"
        assert pool["yt:evaltalk002"]["in_library"] is False
        assert pool["yt:evaltalk003"]["in_library"] is False
        assert {row["video_id"] for row in local} == {"evaltalk001"}
        assert "library" not in result["by_source"]
    finally:
        idx.close()


@pytest.mark.parametrize("field", ["enclosure_url", "audio_url", "episodeUrl", "url"])
def test_library_podcast_dedupes_with_itunes(tmp_path, backend, monkeypatch, field):
    episode = fixture("itunes_episodes.json")["results"][0]
    def search(*args, **kwargs):
        assert kwargs["passages"] is False
        return {"results": [{"video_id": "ep_saved_episode", "title": episode["trackName"],
                             "channel": episode["collectionName"],
                             "metadata_json": json.dumps({field: episode["episodeUrl"]})}]}
    monkeypatch.setattr(backend, "_get_index", lambda: SimpleNamespace(search_mode=search))
    backend._write_settings({"research_network_sources": ["podcast"]})
    run_id = backend._research_start({"question": "evals", "source_kinds": ["library", "podcast"]})["run_id"]
    result = backend._research_discover({"run_id": run_id, "queries": ["evals"]})
    assert not result["errors"] and len(result["candidates"]) == 2
    saved = next(c for c in result["candidates"] if c["url"] == episode["episodeUrl"])
    expected = research.parse_itunes_episodes({"results": [episode]})[0]
    assert saved["key"] == expected["key"] and saved["kind"] == "podcast"
    assert saved["in_library"] is True
    assert {f["source"] for f in saved["signals"]["found_by"]} == {"library", "podcast"}
    assert len(research.load_run(tmp_path, run_id)["candidates_pool"]) == 2


def test_fetch_releases_store_and_run_locks_and_allows_another_run(tmp_path, backend, monkeypatch):
    backend._write_settings({"research_network_sources": ["youtube"]})
    run_id = backend._research_start({"question": "evals", "source_kinds": ["youtube"]})["run_id"]
    def check_locks():
        assert research.RUN_LOCK.acquire(timeout=1), "fetch held the global store lock"
        try:
            merge_lock = research.run_lock(run_id)
        finally:
            research.RUN_LOCK.release()
        assert merge_lock.acquire(timeout=1), "fetch held the run's merge lock"
        try:
            return backend._research_start({"question": "another run", "source_kinds": []})
        finally:
            merge_lock.release()
    checked = []
    def fetch(query, limit):
        # RUN_LOCK is reentrant, so the probe must run on a different thread.
        with ThreadPoolExecutor(max_workers=1) as worker:
            checked.append(worker.submit(check_locks).result(3))
        return fixture("ytsearch_evals.json")
    monkeypatch.setattr(backend, "_research_ytsearch", fetch)
    result = backend._research_discover({"run_id": run_id, "queries": ["evals"]})
    assert not result["errors"] and len(checked) == 1
    assert checked[0]["ok"] and checked[0]["run_id"] != run_id
    assert len(research.list_runs(tmp_path)) == 2


def test_same_run_concurrent_fetches_merge_without_losing_candidates(tmp_path, backend, monkeypatch):
    backend._write_settings({"research_network_sources": ["youtube"]})
    run_id = backend._research_start({"question": "talks", "source_kinds": ["youtube"]})["run_id"]
    barrier = threading.Barrier(2)
    def fetch(query, limit):
        barrier.wait(timeout=3)  # Both fetches must start before either merges.
        return {"entries": [{"id": f"{query}000001", "title": query}]}
    monkeypatch.setattr(backend, "_research_ytsearch", fetch)
    with ThreadPoolExecutor(max_workers=2) as workers:
        pending = [workers.submit(backend._research_discover, {"run_id": run_id, "queries": [q]})
                   for q in ("alpha", "bravo")]
        results = [future.result(10) for future in pending]
    assert all(result["ok"] and not result["errors"] for result in results)
    stored = research.load_run(tmp_path, run_id)
    assert {c["key"] for c in stored["candidates_pool"]} == {"yt:alpha000001", "yt:bravo000001"}
    assert {call["queries"][0] for call in stored["discover_calls"]} == {"alpha", "bravo"}


@pytest.mark.parametrize("active_request", [False, True])
def test_stdio_research_discovery_keeps_event_loop_responsive(backend, monkeypatch, active_request):
    import uoink_mcp
    from tests.test_discovery_queue import _run_stdio

    monkeypatch.setattr(uoink_mcp, "STDIO_TOOLSET", "research")
    monkeypatch.setattr(tools, "_backend", backend)
    release = threading.Event()
    worker_threads = []
    async def exercise():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        def blocked(args):
            worker_threads.append(threading.get_ident())
            loop.call_soon_threadsafe(started.set)
            assert release.wait(3), "research worker was not released"
            return {"ok": True, "candidates": []}
        monkeypatch.setattr(backend, "_research_discover", blocked)
        token = uoink_mcp._active_stdio_request.set(object() if active_request else None)
        pending = asyncio.create_task(uoink_mcp.mcp.call_tool("research_discover", {
            "run_id": "rr_20261103000000_aabbccdd", "queries": ["evals"]}))
        try:
            await asyncio.wait_for(started.wait(), 1)
            assert len(worker_threads) == 1 and worker_threads[0] != threading.get_ident()
            assert not pending.done()
            listed = await asyncio.wait_for(uoink_mcp.mcp.list_tools(), 1)
            assert {tool.name for tool in listed} == {"research_start", "research_discover", "uoink_url"}
            assert not pending.done()
            release.set()
            response = await asyncio.wait_for(pending, 2)
            assert json.loads(response.content[0].text)["ok"] is True
        finally:
            release.set()
            await asyncio.gather(pending, return_exceptions=True)
            uoink_mcp._active_stdio_request.reset(token)
    _run_stdio(exercise())
