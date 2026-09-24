"""Run O: session authority through real adapters and disposable databases.

HTTP probes retain token/origin checks but use no sockets and bypass Host
validation. These cases do not claim installed-client verification.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

import library_work
import server
import uoink_mcp_tools as tools
from tests.test_library_adapters import VALID, mcp_call, post
from tests.test_phase2_acceptance_m import real_library  # noqa: F401
from tests.test_phase2_acceptance_n import invoke, mint


def snapshot(idx):
    """Refusals must preserve the entire fixture, including intent consumption."""
    return tuple(idx._conn.iterdump())


def invalid_request(transport, name, args):
    if transport == "registry":
        result = tools.call_tool(name, args)
    elif transport == "http":
        probe = post("/tools/" + name, args)
        assert probe.status == 400, probe.payload
        result = probe.payload
    else:
        probe = mcp_call(name, args)
        assert probe.status == 200, probe.payload
        assert probe.payload["result"]["isError"] is True, probe.payload
        result = probe.payload["result"]["structuredContent"]
    assert result["error"]["code"] == "invalid_request", result


@pytest.mark.parametrize("transport", ["registry", "http", "rpc"])
@pytest.mark.parametrize("name", tools.LIBRARY_TOOL_NAMES)
def test_tool_json_cannot_choose_session_or_authority(real_library, transport, name):
    idx, svc, ctx = real_library
    args = next(args for tool, args in VALID if tool == name)
    assert tools.library_validate_arguments(name, args) is None
    before = snapshot(idx)
    for extra in (
        {"session_id": ctx.session_id}, {"session_hash": ctx.session_id},
        {"context": {"session_hash": ctx.session_id, "actor": "user"}},
        {"request_context": {"session_id": ctx.session_id}},
        {"actor": "user"}, {"operator": True}, {"local_user_confirmed": True},
        {"transport": "dashboard"}, {"authenticated": True},
    ):
        invalid_request(transport, name, {**args, **extra})
        assert snapshot(idx) == before, (transport, name, extra)


@pytest.mark.parametrize("transport", ["registry", "http", "rpc"])
@pytest.mark.parametrize("kind", ["pin", "undo"])
def test_rotation_orphans_intent_and_other_session_cannot_replay(
        real_library, monkeypatch, transport, kind):
    idx, svc, ctx = real_library
    operation = {"video_id": "fixture", "shelf_id": "s1", "action": "move",
                 "expected_projection_revision": 0, "operation_key": "move-o"}
    if kind == "undo":
        pinned = svc.pin_shelf(ctx, mint("pin", operation))
        assert pinned["ok"], pinned
        operation = {"apply_id": pinned["apply_id"], "expected_projection_revision": 1,
                     "operation_key": "undo-o"}
    name = "pin_shelf" if kind == "pin" else "undo_library_apply"
    method = svc.pin_shelf if kind == "pin" else svc.undo_apply
    request = mint(kind, operation)
    before = snapshot(idx)
    counters = tuple(idx._conn.execute(
        "SELECT projection_revision,last_operation_sequence FROM library_meta").fetchone())

    foreign = replace(ctx, session_id="other-session", operator=False, local_user_confirmed=False)
    assert method(foreign, request)["error"]["code"] == "invalid_user_intent"
    assert snapshot(idx) == before

    previous_token = server.TOKEN
    previous_session = server._library_session_hash()
    monkeypatch.setattr(server, "TOKEN", "run-o-rotated-fixture-token")
    assert server._library_session_hash() != previous_session
    if transport != "registry":
        path = "/tools/" + name if transport == "http" else "/mcp/v1"
        body = request if transport == "http" else {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": request}}
        assert post(path, body, headers={"X-Uoink-Token": previous_token}).status == 403
    assert invoke(transport, name, request)["error"]["code"] == "invalid_user_intent"
    for field in ("session_hash", "session_id"):
        invalid_request(transport, name, {**request, field: previous_session})
    assert snapshot(idx) == before

    # A fresh dashboard confirmation under the rotated token restores access.
    fresh = mint(kind, operation)
    receipt = invoke(transport, name, fresh)
    assert receipt["ok"], receipt
    assert invoke(transport, name, fresh) == receipt
    after = snapshot(idx)
    assert tuple(idx._conn.execute(
        "SELECT projection_revision,last_operation_sequence FROM library_meta").fetchone()) == (
            counters[0] + 1, counters[1] + 1)

    # The original intent stays unconsumed; the fresh one was consumed once.
    old_row = idx._conn.execute("SELECT consumed_by FROM library_user_intents WHERE token_hash=?",
                               (library_work.digest(request["user_intent_token"]),)).fetchone()
    new_row = idx._conn.execute("SELECT consumed_by FROM library_user_intents WHERE token_hash=?",
                               (library_work.digest(fresh["user_intent_token"]),)).fetchone()
    assert old_row[0] is None and new_row[0] is not None
    assert method(foreign, fresh)["error"]["code"] == "invalid_user_intent"
    monkeypatch.setattr(server, "TOKEN", "run-o-third-fixture-token")
    assert invoke(transport, name, fresh)["error"]["code"] == "invalid_user_intent"
    assert snapshot(idx) == after
    monkeypatch.setattr(server, "TOKEN", "run-o-rotated-fixture-token")
    assert invoke(transport, name, fresh) == receipt
    assert snapshot(idx) == after


@pytest.mark.parametrize("kind", ["pin", "undo"])
def test_dashboard_json_cannot_override_session(real_library, kind):
    idx, svc, ctx = real_library
    operation = {"video_id": "fixture", "shelf_id": "s1", "action": "move",
                 "expected_projection_revision": 0, "operation_key": "dashboard-o"}
    if kind == "undo":
        pinned = svc.pin_shelf(ctx, mint("pin", operation))
        assert pinned["ok"], pinned
        operation = {"apply_id": pinned["apply_id"], "expected_projection_revision": 1,
                     "operation_key": "dashboard-undo-o"}
    before = snapshot(idx)
    body = {"kind": kind, "operation": operation, "confirmed": True}
    for field in ("session_hash", "session_id", "context"):
        for request in ({**body, field: "foreign"},
                        {**body, "operation": {**operation, field: "foreign"}}):
            probe = post("/library/intent", request, headers={
                "Origin": f"http://127.0.0.1:{server.PORT}", "Sec-Fetch-Site": "same-origin"})
            assert probe.status == 400, probe.payload
            assert probe.payload["error"]["code"] == "invalid_request"
            assert snapshot(idx) == before


def test_real_dispatch_health_and_client_label_use_backend_session(real_library, monkeypatch):
    idx, svc, ctx = real_library
    seen = []
    original_list = library_work.list_work
    original_claim = library_work.claim_work

    def observe_list(index, context, args):
        seen.append(context)
        return original_list(index, context, args)

    def observe_claim(index, context, args):
        seen.append(context)
        return original_claim(index, context, args)

    monkeypatch.setattr(library_work, "list_work", observe_list)
    monkeypatch.setattr(library_work, "claim_work", observe_claim)
    tools._library_status_cache.clear()
    try:
        assert server._library_health_payload()["waiting_for_client"]
        assert seen[-1].operator and not seen[-1].local_user_confirmed
        assert seen[-1].session_id == server._library_session_hash()
        for transport in ("registry", "http", "rpc"):
            assert invoke(transport, "list_library_work", {})["ok"]
            assert seen[-1].session_id == server._library_session_hash()
            assert not seen[-1].operator and not seen[-1].local_user_confirmed
        claimed = invoke("http", "claim_library_work", {
            "action": "claim", "run_id": "r1", "client_id": "caller-chosen-label"})
        assert claimed["ok"] and len(claimed["work"]) == 1
        assert seen[-1].client_id == "caller-chosen-label"
        assert seen[-1].session_id == server._library_session_hash()
        assert not seen[-1].operator and not seen[-1].local_user_confirmed
    finally:
        tools._library_status_cache.clear()
