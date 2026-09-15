"""Run M checks against the real module seam; no FakeLibraryService.

Four checks reproduce the disconnected adapters on candidate f53adaf.
Use isolated environment roots as recorded in the acceptance report.
"""
from __future__ import annotations

import pytest

from index import Index
from library_work import RequestContext
import library_work
import server
import uoink_mcp_tools as tools
from tests.test_library_adapters import post, mcp_call


@pytest.fixture
def real_library(tmp_path, monkeypatch):
    idx = Index.open(tmp_path / "fixture.db")
    idx.upsert_yoink(dict(video_id="fixture", slug="fixture", title="Fixture", topic="Old",
                         yoinked_at="2026-09-04", corpus_path="", sidecar_path=""))
    with idx.write_transaction() as conn:
        conn.execute("INSERT INTO clips(video_id,seq,start,end,text) VALUES('fixture',0,0,10,'Source evidence.')")
    svc = idx.library_service()
    ctx = RequestContext(authenticated=True, client_id="test-client", session_id=server._library_session_hash(),
                         operator=True, local_user_confirmed=True)
    assert svc.approve_taxonomy(ctx, {"version_id": "v1", "nodes": [
        {"shelf_id": "s1", "path": ["Tests"], "definition": "Tests", "include": [], "exclude": []}]
    })["ok"]
    assert svc.prepare_run(ctx, {"run_id": "r1", "version_id": "v1", "video_ids": ["fixture"],
                                "prompt_hash": "0" * 64})["ok"]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_index_singleton", idx)
    monkeypatch.setattr(server, "_read_settings", lambda: {"librarian_apply_enabled": False})
    tools.bind_backend(server)
    tools.set_library_service(None)
    for limiter in tools._LIBRARY_RATE_LIMITERS.values():
        limiter._calls.clear()
    assert tools._library_service() is library_work
    try:
        yield idx, svc, ctx
    finally:
        tools.set_library_service(None)
        for limiter in tools._LIBRARY_RATE_LIMITERS.values():
            limiter._calls.clear()
        idx.close()


def test_real_registry_http_rpc_list_matches_service(real_library):
    idx, svc, ctx = real_library
    expected = svc.list_work(ctx, {"run_id": "r1"})
    assert expected["ok"] and expected["waiting_for_client"]
    direct = tools.call_tool("list_library_work", {"run_id": "r1"})
    http_payload = post("/tools/list_library_work", {"run_id": "r1"}).payload
    http = http_payload.get("result", http_payload)
    rpc = mcp_call("list_library_work", {"run_id": "r1"}).payload["result"]["structuredContent"]
    assert idx._conn.execute("SELECT COUNT(*) FROM item_shelves").fetchone()[0] == 0
    assert direct == http == rpc == expected, {"registry": direct, "http": http, "rpc": rpc, "expected": expected}


def test_real_registry_claim_reaches_service(real_library):
    idx, svc, ctx = real_library
    result = tools.call_tool("claim_library_work", {"action": "claim", "run_id": "r1", "client_id": "test-client"})
    assert result["ok"] and len(result["work"]) == 1, result


def test_real_health_reports_waiting_work(real_library):
    idx, svc, ctx = real_library
    assert svc.list_work(ctx, {})["waiting_for_client"] is True
    observed = server._library_health_payload()
    assert observed["status"] == "waiting_for_client" and observed["ready"] == 1, observed


def test_real_dashboard_intent_reaches_service(real_library):
    idx, svc, ctx = real_library
    operation = {"video_id": "fixture", "shelf_id": "s1", "action": "move",
                 "expected_projection_revision": 0, "operation_key": "move-1"}
    # Direct service control proves this same operation and session are valid.
    assert svc.mint_user_intent(ctx, {"kind": "pin", "operation": operation})["ok"]
    probe = post("/library/intent", {"kind": "pin", "operation": operation, "confirmed": True},
                 headers={"Origin": f"http://127.0.0.1:{server.PORT}", "Sec-Fetch-Site": "same-origin"})
    assert probe.status == 200
    assert probe.payload["ok"] and "user_intent_token" in probe.payload, probe.payload


def test_real_module_default_off_and_caller_privileges(real_library):
    idx, svc, ctx = real_library
    apply = tools.call_tool("apply_reshelving", {"mode": "apply", "preview_id": "unapproved",
        "expected_projection_revision": 0, "delta_hash": "0" * 64, "operation_key": "apply-1"})
    assert apply["error"]["code"] == "apply_disabled"
    assert not svc.librarian_apply_enabled
    for extra in ({"actor": "user"}, {"operator": True}, {"local_user_confirmed": True}):
        refused = tools.call_tool("list_library_work", extra)
        assert refused["error"]["code"] == "invalid_request"
    assert idx._conn.execute("SELECT COUNT(*) FROM item_shelves").fetchone()[0] == 0


def test_real_module_intent_auth_and_origin_guards(real_library):
    idx, svc, ctx = real_library
    operation = {"video_id": "fixture", "shelf_id": "s1", "action": "pin",
                 "expected_projection_revision": 0, "operation_key": "pin-1"}
    body = {"kind": "pin", "operation": operation, "confirmed": True}
    for headers in ({"X-Uoink-Token": "wrong"}, {"Origin": "https://example.invalid"},
                    {"Origin": f"http://127.0.0.1:{server.PORT}", "Sec-Fetch-Site": "cross-site"}):
        assert post("/library/intent", body, headers=headers).status == 403
    assert idx._conn.execute("SELECT COUNT(*) FROM library_user_intents").fetchone()[0] == 0
