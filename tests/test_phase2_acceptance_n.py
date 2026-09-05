"""Run N: real adapters must consume dashboard capabilities and replay receipts.

Only disposable fixture databases are opened. HTTP probes run in process;
they retain token/origin checks but do not exercise sockets or Host validation.
"""
from __future__ import annotations

import pytest

import server
import uoink_mcp_tools as tools
from tests.test_library_adapters import mcp_call, post
from tests.test_phase2_acceptance_m import real_library  # noqa: F401


def invoke(transport, name, args):
    if transport == "registry":
        return tools.call_tool(name, args)
    if transport == "http":
        probe = post("/tools/" + name, args)
        assert probe.status == 200, probe.payload
        return probe.payload.get("result", probe.payload)
    probe = mcp_call(name, args)
    assert probe.status == 200, probe.payload
    return probe.payload["result"]["structuredContent"]


def mint(kind, operation):
    probe = post("/library/intent", {"kind": kind, "operation": operation, "confirmed": True},
                 headers={"Origin": f"http://127.0.0.1:{server.PORT}",
                          "Sec-Fetch-Site": "same-origin"})
    assert probe.status == 200 and probe.payload["ok"], probe.payload
    return {**operation, "user_intent_token": probe.payload["user_intent_token"]}


@pytest.mark.parametrize("transport", ["registry", "http", "rpc"])
@pytest.mark.parametrize("kind", ["pin", "undo"])
def test_dashboard_capability_consumption_and_receipt_replay(real_library, transport, kind):
    idx, svc, ctx = real_library
    operation = {"video_id": "fixture", "shelf_id": "s1", "action": "move",
                 "expected_projection_revision": 0, "operation_key": "move-n"}
    if kind == "undo":
        # Establish an independently valid undo target through the real service.
        pinned = svc.pin_shelf(ctx, mint("pin", operation))
        assert pinned["ok"], pinned
        operation = {"apply_id": pinned["apply_id"], "expected_projection_revision": 1,
                     "operation_key": "undo-n"}
    request = mint(kind, operation)
    tool = "pin_shelf" if kind == "pin" else "undo_library_apply"
    method = svc.pin_shelf if kind == "pin" else svc.undo_apply
    before = tuple(idx._conn.execute(
        "SELECT projection_revision,last_operation_sequence FROM library_meta").fetchone())
    first = invoke(transport, tool, request)
    after_first = tuple(idx._conn.execute(
        "SELECT projection_revision,last_operation_sequence FROM library_meta").fetchone())
    if not first["ok"]:
        assert after_first == before, "A refused capability must change no projection or receipt"
    # The same token, operation and dashboard session must work at the service,
    # whether this is the first successful execution or an identical replay.
    control = method(ctx, request)
    assert control["ok"], control
    replay = invoke(transport, tool, request)
    assert method(ctx, request) == control
    after = tuple(idx._conn.execute(
        "SELECT projection_revision,last_operation_sequence FROM library_meta").fetchone())
    assert after == (before[0] + 1, before[1] + 1)
    assert first == control == replay, {"first": first, "control": control, "replay": replay}


@pytest.mark.parametrize("transport", ["registry", "http", "rpc"])
def test_real_claim_submit_retry_and_preview(real_library, transport):
    idx, svc, ctx = real_library
    claimed = invoke(transport, "claim_library_work",
                     {"action": "claim", "run_id": "r1", "client_id": "test-client"})
    assert claimed["ok"] and len(claimed["work"]) == 1, claimed
    packet = claimed["work"][0]
    excerpt = packet["card"]["excerpts"][0]
    request = {key: packet[key] for key in (
        "work_id", "video_id", "attempt_token", "source_revision", "taxonomy_revision", "packet_hash")}
    request.update(client_id="test-client", submission_key="submit-n", schema_version=1,
                   usage={"status": "unavailable", "reason": "fixture; no model call"},
                   result={"outcome": "assigned", "memberships": [{
                       "shelf_id": "s1", "shelf_path": ["Tests"], "confidence": 0.8,
                       "evidence": {"basis": "packet", "kind": "timed_clip",
                                    "excerpt_id": excerpt["excerpt_id"],
                                    "card_hash": packet["card"]["card_hash"],
                                    "quote": "Source evidence."}}]})
    submitted = invoke(transport, "submit_library_result", request)
    assert submitted["ok"] and submitted["outcome"] == "accepted", submitted
    svc.clock = lambda: packet["lease_expires_ms"] + 1
    assert invoke(transport, "submit_library_result", request) == submitted
    changed = {**request, "usage": {"status": "unavailable", "reason": "changed"}}
    assert invoke(transport, "submit_library_result", changed)["error"]["code"] == "idempotency_conflict"
    preview = invoke(transport, "apply_reshelving",
                     {"mode": "preview", "run_id": "r1", "expected_projection_revision": 0})
    assert preview["ok"] and not preview["can_apply"], preview
    assert {reason["code"] for reason in preview["reasons"]} >= {
        "apply_disabled", "preview_approval_required"}
    assert not svc.librarian_apply_enabled
    assert idx._conn.execute("SELECT COUNT(*) FROM item_shelves").fetchone()[0] == 0


def test_real_preview_tracks_trusted_apply_setting(real_library, monkeypatch):
    idx, svc, ctx = real_library
    for setting, enabled in ((True, True), (False, False), ("true", False), (1, False)):
        monkeypatch.setattr(server, "_read_settings", lambda value=setting:
                            {"librarian_apply_enabled": value})
        preview = tools.call_tool("apply_reshelving",
                                  {"mode": "preview", "run_id": "r1", "expected_projection_revision": 0})
        assert preview["ok"], preview
        assert svc.librarian_apply_enabled is enabled
        assert ("apply_disabled" in {reason["code"] for reason in preview["reasons"]}) is not enabled
    assert idx._conn.execute("SELECT COUNT(*) FROM item_shelves").fetchone()[0] == 0
