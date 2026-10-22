"""Lane S integration: isolated storage, real index writes, fake offline model."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

import corpus_contract
import corpus_provider
import index
import library_resources
import server
import uoink_mcp
import uoink_mcp_tools as tools
from tests.test_library_adapters import Probe
from tests.test_local_search import FakeModel, install
from tests.test_smarter_search import seed
from uoink_core import local_search as ls

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(tmp_path, monkeypatch):
    data = b"offline model fixture"
    monkeypatch.setattr(ls, "MODEL_FILES", (("onnx/model_quantized.onnx", len(data), hashlib.sha256(data).hexdigest()),))
    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_local_search_singleton", None)
        monkeypatch.setattr(server, "_check_memory_search_rate_limit", lambda: True)
        monkeypatch.setattr(tools, "_backend", server)
        engine = server._get_local_search()
        engine.model_factory = FakeModel
        yield idx, engine, data
        engine.pause()


def ready(db):
    idx, engine, data = db
    install(engine.manager, data)
    engine.start()
    assert engine.wait(5)
    assert engine.status()["state"] == "ready"
    return idx, engine


def request(method, path, body=None, **headers):
    probe = Probe(method, path, body, headers={"Host": "127.0.0.1:15180", **headers})
    probe.server = SimpleNamespace(server_address=("127.0.0.1", 15180))
    probe._reject_bad_host = lambda: server.Handler._reject_bad_host(probe)
    getattr(server.Handler, "do_" + method)(probe)
    return probe


@pytest.mark.parametrize("method,path", [("GET", "/search/status"), ("POST", "/search/terms"),
    ("POST", "/search/model"), ("POST", "/search/start"), ("POST", "/search/pause"), ("DELETE", "/search/model")])
def test_routes_token_host_origin_and_no_side_effects(db, method, path):
    _, engine, _ = db
    for headers in ({"X-Uoink-Token": "bad"}, {"Host": "evil.example:15180"}, {"Origin": "https://evil.example"}):
        response = request(method, path, {}, **headers)
        assert response.status == 403
        assert engine.manager.acceptance() is None
        assert engine._worker is None


def test_terms_order_requires_current_version_and_literal_true(db, monkeypatch):
    _, engine, _ = db
    calls = []
    monkeypatch.setattr(engine, "_launch", lambda: calls.append("launch"))
    assert request("POST", "/search/model", {}).status == 400
    for body in ({}, {"accepted": 1, "terms_version": ls.TERMS_VERSION},
                 {"accepted": "true", "terms_version": ls.TERMS_VERSION},
                 {"accepted": True, "terms_version": "old"}):
        assert request("POST", "/search/terms", body).status == 400
    assert calls == [] and not engine.enabled
    assert request("POST", "/search/terms", {"accepted": True, "terms_version": ls.TERMS_VERSION}).status == 200
    assert calls == [] and not engine.enabled
    assert request("POST", "/search/model", {}).status == 200
    assert calls == ["launch"] and engine.enabled


def test_singleton_is_lazy_and_profile_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_local_search_singleton", None)
    monkeypatch.setattr(server, "_get_index", lambda: pytest.fail("off must not open an index"))
    server._resume_local_search()
    assert server._local_search_singleton is None
    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        engine = server._get_local_search()
        assert engine is server._get_local_search() is idx._local_search
        assert engine.root == tmp_path.resolve()
        assert engine._worker is None and not engine.store.path.exists()
        assert engine.manager.acceptance() is None


def test_resume_restarts_an_incomplete_download_only_after_acceptance(db, monkeypatch):
    _, engine, _ = db
    launches = []
    monkeypatch.setattr(engine, "_launch", lambda: launches.append(True))
    assert request("POST", "/search/start", {}).status == 400
    assert not launches
    engine.accept_terms(accepted=True, terms_version=ls.TERMS_VERSION)
    engine._paused = True
    assert request("POST", "/search/start", {}).status == 200
    assert launches == [True] and engine._download and not engine._paused


def test_restart_resumes_only_persisted_opt_in(db, monkeypatch):
    idx, engine = ready(db)
    assert ls.LocalSearch.enabled_at(idx._path.parent)
    calls = []
    monkeypatch.setattr(engine, "start", lambda: calls.append("start"))
    server._resume_local_search()
    assert calls == ["start"]
    engine.manager.terms_path.unlink()
    server._resume_local_search()
    assert calls == ["start"]


@pytest.mark.parametrize("state,paused,expected", [("not_installed", False, "keyword"),
    ("indexing", False, "keyword"), ("verifying", False, "keyword"), ("ready", True, "keyword"),
    ("ready", False, "hybrid")])
def test_auto_mode_readiness_and_requested_fallback(db, state, paused, expected):
    idx, engine, _ = db
    seed(idx, "mars", "Mars has rusty red soil")
    ready(db)
    engine._set(state)
    engine._paused = paused
    result = idx.search_mode("rusty", mode="auto")
    assert result["search_mode"] == expected
    explicit = idx.search_mode("rusty", mode="semantic")
    assert explicit["search_mode"] == ("semantic" if expected == "hybrid" else "keyword")
    assert bool(explicit["fallback_reason"]) == (expected == "keyword")


def test_off_and_any_semantic_failure_keep_keyword_results(db, monkeypatch):
    idx, engine, _ = db
    seed(idx, "mars", "Mars has rusty red soil")
    assert idx.search_mode("rusty")["search_mode"] == "keyword"
    assert not engine.enabled and engine._worker is None
    ready(db)
    def broken(*args, **kwargs):
        raise RuntimeError("private corpus text must not leak")
    monkeypatch.setattr(engine, "embedding_search", broken)
    for mode in ("auto", "semantic", "hybrid"):
        result = tools.search_uoinks({"query": "rusty", "mode": mode})
        assert result["search_mode"] == "keyword" and result["results"][0]["video_id"] == "mars"
        assert result["fallback_reason"] and "private" not in result["fallback_reason"]
    monkeypatch.setattr(engine, "status", broken)
    assert idx.search_mode("rusty")["search_mode"] == "keyword"


def test_incremental_capture_edit_citations_delete_restore_and_publication(db):
    idx, engine = ready(db)
    seed(idx, "mars", "Mars has rusty red soil", timed=True)
    assert engine.wait(5)
    original = engine.store.fingerprints()["mars"]
    idx.insert_citations("mars", [{"kind": "transcript_chunk", "seq": 0, "text": "Rust covers Mars",
                                   "timestamp_start": 31, "timestamp_end": 40}])
    assert engine.wait(5)
    assert engine.store.fingerprints()["mars"] != original
    hit = idx.search_embedding("rust")["results"][0]
    assert hit["timestamp_seconds"] == hit["passage"]["start"] == 31
    idx.insert_citations("mars", [])
    assert engine.wait(5)
    assert idx.search_embedding("rust")["results"][0]["span"]["kind"] == "text"
    idx.soft_delete_yoink("mars")
    assert engine.wait(5) and engine.store.fingerprints() == {}
    idx.restore_yoink("mars")
    assert engine.wait(5) and "mars" in engine.store.fingerprints()
    # Publication notification must precede the no-library-runs early return.
    calls = []
    idx._source_change_callback = calls.append
    idx._invalidate_after_publication("mars")
    assert calls == ["mars"]
    idx.set_local_search(engine)
    idx.delete_yoink("mars")
    assert engine.wait(5) and engine.store.fingerprints() == {}


def test_callback_runs_after_commit_outside_lock_and_failure_cannot_lose_capture(db):
    idx, _, _ = db
    def callback(identity):
        assert not idx._lock._is_owned()
        assert not idx._conn.in_transaction
        assert idx.get_yoink(identity)
        raise RuntimeError("fixture")
    idx._source_change_callback = callback
    seed(idx, "safe", "saved source")
    assert idx.has_yoink("safe")


def test_hybrid_citations_filters_and_individual_clips(db):
    idx, engine, _ = db
    seed(idx, "mars", "Mars has rusty soil", timed=True)
    seed(idx, "bread", "Bread rises in the oven")
    seed(idx, "exact", "opening prose", title="rusty")
    ready(db)
    result = idx.search_hybrid("rusty")
    assert result["search_mode"] == "hybrid"
    assert result["results"][0]["video_id"] == "exact"
    timed = next(row for row in result["results"] if row["video_id"] == "mars")
    assert timed["source_id"] == timed["passage"]["video_id"] == "mars"
    assert timed["span"]["clip_id"] == idx.get_clips("mars")[0]["clip_id"]
    assert timed["timestamp_seconds"] == 12.5
    prose = next(row for row in result["results"] if row["video_id"] == "bread")
    assert "Bread rises in the oven"[prose["span"]["char_start"]:prose["span"]["char_end"]] == prose["passage"]["text"]
    assert {r["video_id"] for r in idx.search_mode("rust", filters={"source_type": "note"})["results"]} == {"bread", "exact"}
    clips = tools.search_clips({"query": "rust", "mode": "semantic", "video_id": "mars"})
    assert clips["search_mode"] == "semantic" and clips["results"][0]["clip_id"] == timed["span"]["clip_id"]
    reader = library_resources.LibraryReader(idx, data_root=idx._path.parent)
    library = reader.search("rusty", mode="hybrid")
    assert library["search_mode"] == "hybrid" and library["hits"][0]["item_id"] == "exact"
    for hit in library["hits"]:
        assert hit["source_revision"] and hit["passage"]
        assert reader.read(hit["uris"]["excerpt"])["contents"]


def test_source_cache_invalidates_for_own_and_other_connection_writes(db):
    import sqlite3
    idx, engine, _ = db
    seed(idx, "mars", "Mars rusty soil")
    first = engine.sources.snapshot()[0]
    assert engine.sources.snapshot()[0] is first
    assert engine.sources.snapshot(filters={"source_type": "note"})[0] is first
    row = idx.get_yoink("mars")
    idx.upsert_yoink(row, content="Fresh Mars passage")
    changed = engine.sources.snapshot()[0]
    assert changed.fingerprint != first.fingerprint
    with sqlite3.connect(idx._path) as other:
        other.execute("UPDATE yoinks SET deleted_at='2026-10-22' WHERE video_id='mars'")
    assert engine.sources.snapshot() == []


def test_semantic_clip_mode_keeps_multiple_clips_per_source(db):
    idx, _, _ = db
    seed(idx, "mars", "Mars rusty soil", timed=True)
    idx.insert_citations("mars", [
        {"kind": "transcript_chunk", "seq": 0, "text": "Mars has rusty soil", "timestamp_start": 0, "timestamp_end": 20},
        {"kind": "transcript_chunk", "seq": 1, "text": "Rust also covers Mars rocks", "timestamp_start": 200, "timestamp_end": 220}])
    ready(db)
    stored = idx.get_clips("mars")
    assert len(stored) == 2
    for mode in ("semantic", "hybrid"):
        result = tools.search_clips({"query": "rust", "mode": mode})
        assert {row["clip_id"] for row in result["results"]} == {row["clip_id"] for row in stored}


def test_removal_keeps_main_index_and_turns_off_restart(db):
    idx, engine, _ = db
    seed(idx, "mars", "Mars rusty soil")
    ready(db)
    response = request("DELETE", "/search/model")
    assert response.status == 200 and not response.payload["enabled"]
    assert not engine.manager.directory.exists() and not engine.store.path.exists()
    assert engine.manager.acceptance() is None and not ls.LocalSearch.enabled_at(engine.root)
    assert idx.search_mode("rusty")["results"][0]["video_id"] == "mars"


def test_stdio_search_uses_helper_and_falls_back_without_loading_model(db, monkeypatch):
    import uoink_agent_runtime as runtime
    idx, engine = ready(db)
    calls = []
    remote = {"ok": True, "search_mode": "hybrid", "results": []}
    monkeypatch.setattr(server, "_call_http_registry_tool", lambda *args, **kwargs: calls.append(args) or {"ok": True, "result": remote})
    local = lambda: {"ok": True, "results": [], "search_mode": "keyword"}
    for tool in ("search_library", "search_uoinks", "search_clips"):
        assert runtime.dispatch_search(tool, {"query": "rust"}, server, local, running=lambda: True) is remote
    assert len(calls) == 3
    result = runtime.dispatch_search("search_uoinks", {"query": "rust"}, server, local, running=lambda: False)
    assert result["search_mode"] == "keyword" and "helper is unavailable" in result["fallback_reason"]
    runtime.dispatch_search("search_uoinks", {"query": "rust", "mode": "keyword"}, server, local,
                            running=lambda: pytest.fail("keyword must stay local"))
    assert len(calls) == 3
    assert idx._local_search is engine


@pytest.mark.parametrize("mode", ["auto", "keyword", "semantic", "hybrid"])
def test_http_modes_and_corpus_additive_shape(db, mode):
    idx, _, _ = db
    seed(idx, "mars", "Mars rusty soil")
    ready(db)
    response = request("GET", "/memory/search?q=rusty&mode=" + mode)
    assert response.status == 200, response.payload
    expected = "hybrid" if mode == "auto" else mode
    assert response.payload["search_mode"] == expected
    request_data = corpus_contract.SearchRequest.from_query({"q": "rusty", "mode": mode, "search_details": "true"})
    data = corpus_provider.UoinkCorpusProvider(idx, idx._path.parent).search(request_data)
    corpus_contract.validate_data("search", data, search_details=True)
    assert data["search_mode"] == expected and data["items"][0]["passage"]


@pytest.mark.parametrize("name", ["search_library", "search_uoinks", "search_clips"])
def test_optional_mode_in_flat_stdio_schema_and_wrappers(name, monkeypatch):
    schema = tools.TOOL_REGISTRY[name].input_schema
    assert schema["required"] == ["query"]
    assert schema["properties"]["mode"]["enum"] == ["auto", "keyword", "semantic", "hybrid"]
    assert schema["properties"]["mode"]["default"] == "auto"
    assert tools.client_input_schema(schema) == schema
    calls = []
    monkeypatch.setattr(tools, "call_tool", lambda name, args: calls.append(args) or {})
    getattr(uoink_mcp, name)("rusty", mode="hybrid")
    assert calls[0]["mode"] == "hybrid"


def test_verified_and_acceptance_refuse_file_symlinks(tmp_path, monkeypatch):
    manager = ls.ModelManager(tmp_path)
    target = tmp_path / "model.bin"
    target.write_bytes(b"model")
    manager.accept_terms(accepted=True, terms_version=ls.TERMS_VERSION)
    assert manager.acceptance()
    # Exercise refusal even on Windows machines without symlink privilege.
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self in (target, manager.terms_path) or original(self))
    assert not ls.verified(target, 5, hashlib.sha256(b"model").hexdigest())
    assert manager.acceptance() is None


def test_real_file_symlinks_refused(tmp_path):
    manager = ls.ModelManager(tmp_path)
    record = manager.accept_terms(accepted=True, terms_version=ls.TERMS_VERSION)
    manager.terms_path.unlink()
    real = tmp_path / "real.json"
    real.write_text(json.dumps(record))
    try:
        manager.terms_path.symlink_to(real)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable; refusal also covered without privilege")
    assert manager.acceptance() is None
    assert not ls.verified(manager.terms_path, real.stat().st_size, hashlib.sha256(real.read_bytes()).hexdigest())


def test_packaging_rejects_model_state_and_includes_notices(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/mac"))
    import build_bundle
    paths = build_bundle.payload_files()
    assert Path("uoink_core/local_search.py") in paths
    for name in ("EmbeddingGemma-NOTICE.md", "Gemma-Terms-of-Use.txt", "Gemma-Prohibited-Use-Policy.txt"):
        assert Path("third-party-notices") / name in paths
        for script in ("build.ps1", "installer/uoink.iss", "scripts/gen_third_party_notices.py"):
            assert name in (ROOT / script).read_text(encoding="utf-8")
    for name in ("models/embeddinggemma-300m-onnx-q8-v1/tokenizer.json", "model_quantized.onnx_data",
                 "embeddinggemma-terms.json", "search-vectors.db-wal", "search-settings.json"):
        with pytest.raises(ValueError):
            build_bundle.assert_search_payload([Path(name)])
    for script in ("build.ps1", "scripts/build-mcpb.ps1"):
        assert "assert-search-payload.ps1" in (ROOT / script).read_text(encoding="utf-8")
    if sys.platform == "win32":
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/assert-search-payload.ps1"), "-Root", str(tmp_path)]
        assert subprocess.run(command, capture_output=True).returncode == 0
        (tmp_path / "search-vectors.db").write_bytes(b"private fixture")
        assert subprocess.run(command, capture_output=True).returncode != 0
