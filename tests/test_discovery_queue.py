"""T6 acceptance: mocked provider, socket-free transports, tmp_path runs only."""
from __future__ import annotations

from tests.mcp_sdk import handler_for

import asyncio
import datetime as dt
import contextlib
import concurrent.futures
import json
import selectors
import socket
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import discovery_scrapecreators as sc
import index
import library_resources
import server
import uoink_mcp
import uoink_mcp_tools as tools
from mcp import types
from tests.test_discovery_scrapecreators import (
    ARGS, Probe, fixture, intent, no_network_or_real_credentials, reason, rig, run,
)


class _PollingSelector(selectors.DefaultSelector):
    def select(self, timeout=None):
        timeout = 0.01 if timeout is None else min(timeout, 0.01)
        if not self.get_map():
            # Windows select() rejects an empty set of file descriptors.
            time.sleep(timeout)
            return []
        return super().select(timeout)


class _SocketFreeEventLoop(asyncio.SelectorEventLoop):
    # Windows' asyncio socketpair would trip the network guard. Poll instead
    # of opening a wakeup socket; worker completions still reach the real loop.
    def __init__(self):
        super().__init__(_PollingSelector())

    def _make_self_pipe(self):
        pass

    def _write_to_self(self):
        pass

    def _close_self_pipe(self):
        pass


def _run_stdio(coroutine):
    with asyncio.Runner(loop_factory=_SocketFreeEventLoop) as runner:
        return runner.run(coroutine)


def test_full_stdio_credit_plan_and_refusal_equal_http(adapter):
    adapter.settings["scrapecreators_agent_calls_enabled"] = False
    plan = call("stdio", "discover_candidates", ARGS)
    assert plan == call("http", "discover_candidates", ARGS)
    assert plan["needs_confirmation"] is True
    args = {**ARGS, "confirm_credits": 1}
    refusal = call("stdio", "discover_candidates", args)
    assert refusal == call("http", "discover_candidates", args)
    assert reason(refusal) == "user_intent_required"
    assert adapter.calls == []


@pytest.fixture(autouse=True)
def network_guard(monkeypatch, no_network_or_real_credentials):
    def forbidden(*args, **kwargs):
        raise AssertionError("discovery queue tests must not use the network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.fixture
def adapter(rig, monkeypatch):
    monkeypatch.setattr(server, "TOKEN", "fixture-helper-token")
    monkeypatch.setattr(server, "_get_discovery_service", lambda: rig.service)
    monkeypatch.setattr(tools, "_backend", server)
    for name in tools.DISCOVERY_TOOL_NAMES:
        monkeypatch.setattr(tools.TOOL_REGISTRY[name].rate_limiter, "_calls", [])
    return rig


def call(transport, name, args, *, headers=None):
    if transport == "registry":
        return tools.call_tool(name, args)
    if transport == "stdio":
        handler = handler_for(uoink_mcp.mcp, "tools/call")
        result = _run_stdio(handler(types.CallToolRequest(
            method="tools/call", params=types.CallToolRequestParams(name=name, arguments=args))))
        envelope = json.loads(result.content[0].text)
        assert result.is_error is (envelope.get("ok") is not True)
        return envelope
    if transport == "http":
        probe = Probe("/mcp/v1/tools/call", {"id": 1, "params": {"name": name, "arguments": args}}, headers)
    else:
        probe = Probe("/tools/" + name, args, headers)
    probe.do_POST()
    assert probe.status == 200
    if transport == "http":
        return probe.payload["result"]["structuredContent"]
    return probe.payload["result"] if probe.payload.get("ok") is True else probe.payload


def picks(result, *keys):
    return {"run_id": result["run_id"], "keys": list(keys) or [result["candidates"][0]["key"]]}


def saved(adapter, result):
    return json.loads(adapter.service._run_path(result["run_id"]).read_text(encoding="utf-8"))


def capture(adapter, candidate, *, deleted=False):
    vid = candidate["video_id"]
    adapter.idx.upsert_yoink({"video_id": vid, "slug": vid, "title": "Saved",
                              "yoinked_at": "2026-10-15T12:00:00", "platform": "youtube",
                              "corpus_path": str(adapter.root / (vid + ".md")),
                              "sidecar_path": str(adapter.root / (vid + ".json"))})
    if deleted:
        adapter.conn.execute("UPDATE yoinks SET deleted_at='2026-10-15' WHERE video_id=?", (vid,))
        adapter.conn.commit()


@pytest.mark.parametrize("transport", ["registry", "stdio", "http", "openapi"])
def test_discovery_plan_agent_gate_and_queue_on_every_transport(adapter, transport):
    adapter.settings["scrapecreators_agent_calls_enabled"] = False
    plan = call(transport, "discover_candidates", ARGS)
    assert plan == {"ok": True, "needs_confirmation": True, "credits_planned": 1,
                    "credits_today": 0, "daily_cap": 25}
    assert reason(call(transport, "discover_candidates", {**ARGS, "confirm_credits": 1})) == "user_intent_required"
    assert adapter.calls == []
    adapter.settings["scrapecreators_agent_calls_enabled"] = True
    result = call(transport, "discover_candidates", {**ARGS, "confirm_credits": 1})
    assert result["ok"] and len(adapter.calls) == 1
    adapter.settings["scrapecreators_agent_calls_enabled"] = False
    assert reason(call(transport, "queue_discovered", picks(result))) == "user_intent_required"
    assert adapter.idx.list_pending() == []
    adapter.settings["scrapecreators_agent_calls_enabled"] = True
    queued = call(transport, "queue_discovered", picks(result))
    assert queued["ok"] and len(queued["queued"]) == 1 and queued["skipped"] == []
    row = adapter.idx.list_pending()[0]
    assert row["url"] == result["candidates"][0]["url"]
    assert row["interval_seconds"] == 30
    assert adapter.idx.next_pending(server._now_iso())["pending_id"] == row["pending_id"]
    candidate = saved(adapter, result)["candidates"][0]
    assert candidate["pending_id"] == row["pending_id"] and candidate["state"] == "queued"
    again = call(transport, "queue_discovered", picks(result))
    assert again["queued"] == [] and again["skipped"] == [{"key": candidate["key"], "reason": "already_queued"}]
    assert len(adapter.calls) == 1 and adapter.service._credits_today(adapter.idx) == 1


@pytest.mark.parametrize("name", ["discover_candidates", "queue_discovered"])
@pytest.mark.parametrize("cancel", [False, True])
def test_stdio_discovery_serves_other_requests_and_cancellation(adapter, monkeypatch, name, cancel):
    handlers = uoink_mcp.mcp
    release = threading.Event()
    expected = {"ok": True, "fixture": name}

    async def exercise():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()

        def blocked(*args, **kwargs):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(5), "discovery worker was not released"
            return expected

        monkeypatch.setattr(adapter.service, name, blocked)
        args = ARGS if name == "discover_candidates" else {"run_id": "fixture", "keys": ["a"]}
        pending = asyncio.create_task(handler_for(handlers, "tools/call")(types.CallToolRequest(
            method="tools/call", params=types.CallToolRequestParams(name=name, arguments=args))))
        try:
            await asyncio.wait_for(started.wait(), 1)
            assert not pending.done(), "discovery blocked the stdio event loop"
            result = await asyncio.wait_for(handler_for(handlers, "tools/list")(
                types.ListToolsRequest(method="tools/list")), 1)
            assert len(result.tools) == 91
            assert tools.DISCOVERY_TOOL_NAMES <= {tool.name for tool in result.tools}
            assert not pending.done()
            if cancel:
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(pending, 1)
            else:
                release.set()
                response = (await asyncio.wait_for(pending, 1))
                assert response.is_error is False
                assert json.loads(response.content[0].text) == expected
        finally:
            release.set()
            await asyncio.gather(pending, return_exceptions=True)

    _run_stdio(exercise())
    assert len(tools.TOOL_REGISTRY[name].rate_limiter._calls) == 1
    assert adapter.calls == []


@pytest.mark.parametrize("offset", [-7, -8])
def test_queue_is_due_immediately_in_pacific_time(adapter, monkeypatch, offset):
    # Simulate the host's local clock without changing the machine timezone.
    # Keep the real server._now_iso formatting used by the retry worker.
    local_zone = dt.timezone(dt.timedelta(hours=offset))
    class LocalClock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            aware = dt.datetime.fromtimestamp(adapter.clock(), tz or local_zone)
            return aware if tz else aware.replace(tzinfo=None)
    monkeypatch.setattr(server, "datetime", LocalClock)
    result = run(adapter)
    queued = call("registry", "queue_discovered", picks(result))
    due = adapter.idx.next_pending(server._now_iso())
    assert due is not None and due["pending_id"] == queued["queued"][0]["pending_id"]
    assert due["retry_after"] == server._now_iso()
    assert dt.datetime.fromisoformat(due["retry_after"]).tzinfo is None
    assert dt.datetime.fromisoformat(result["fetched_at"]).utcoffset() == dt.timedelta(0)


def read_run(adapter, run_id):
    probe = Probe("/discovery/runs/" + run_id)
    probe.command = "GET"
    probe.do_GET()
    assert probe.status == 200 and probe.payload["ok"]
    return probe.payload["run"]


@pytest.mark.parametrize("headers", [{"X-Uoink-Token": ""}, {"X-Uoink-Token": "wrong"},
                                     {"Host": "evil.example"}])
def test_run_get_requires_auth_before_read_or_reconciliation(adapter, monkeypatch, headers):
    result = run(adapter)
    reader = Mock(side_effect=AssertionError("unauthorized read"))
    monkeypatch.setattr(adapter.service, "read_run", reader)
    probe = Probe("/discovery/runs/" + result["run_id"], headers=headers)
    probe.command = "GET"
    probe.do_GET()
    assert probe.status == 403
    reader.assert_not_called()


@pytest.mark.parametrize("run_id,status,code", [("../outside", 400, "invalid_request"),
    ("", 400, "invalid_request"), ("20261016T120000000000Z-missing", 404, "resource_not_found")])
def test_run_get_validation_and_missing_receipts(adapter, run_id, status, code):
    probe = Probe("/discovery/runs/" + run_id)
    probe.command = "GET"
    probe.do_GET()
    assert probe.status == status and probe.payload["error"]["code"] == code
    assert adapter.calls == []


def test_run_get_can_read_a_failed_discovery_without_spending_or_agent_opt_in(adapter):
    adapter.replies[:] = [(429, {})]
    result = run(adapter)
    adapter.settings.update(scrapecreators_enabled=False, scrapecreators_agent_calls_enabled=False)
    adapter.backend._read_settings = Mock(side_effect=AssertionError("read must not check settings"))
    adapter.backend._get_saved_scrapecreators_key = Mock(side_effect=AssertionError("read must not read a key"))
    adapter.service.transport = Mock(side_effect=AssertionError("read must not send"))
    assert read_run(adapter, result["run_id"]) == result
    assert adapter.idx.list_pending() == [] and len(adapter.calls) == 1
    assert adapter.service._credits_today(adapter.idx) == 1


@pytest.mark.parametrize("bad", [ValueError("private failure"), {"ok": True, "bad": float("inf")},
                                 {"ok": True}, []])
def test_run_get_unexpected_errors_use_standard_envelope(adapter, monkeypatch, bad):
    reader = Mock(side_effect=bad) if isinstance(bad, Exception) else Mock(return_value=bad)
    monkeypatch.setattr(adapter.service, "read_run", reader)
    probe = Probe("/discovery/runs/fixture")
    probe.command = "GET"
    probe.do_GET()
    assert probe.status == 500 and probe.payload == library_resources.ResourceError("internal_error").envelope()


@pytest.mark.parametrize("transport", ["http", "openapi"])
@pytest.mark.parametrize("tool", ["discover_candidates", "queue_discovered"])
def test_dashboard_intent_is_bound_and_single_use(adapter, transport, tool):
    args = ARGS if tool == "discover_candidates" else picks(run(adapter))
    adapter.settings["scrapecreators_agent_calls_enabled"] = False
    adapter.replies[:] = [(200, fixture())]
    mint = Probe("/discovery/intent", {"confirmed": True, "operation": {"tool": tool, "arguments": args}})
    mint.do_POST()
    assert mint.status == 200 and mint.payload["ok"]
    submitted = {**args, "user_intent_token": mint.payload["user_intent_token"]}
    if tool == "discover_candidates":
        submitted["confirm_credits"] = 1
    before = len(adapter.calls)
    # A stdio client cannot use a dashboard token, even with agent spending on.
    assert reason(call("stdio", tool, submitted)) == "invalid_user_intent"
    for headers in ({"Origin": "chrome-extension://fixture"}, {"Origin": "http://localhost:" + str(server.PORT)}):
        assert reason(call(transport, tool, submitted, headers=headers)) == "invalid_user_intent"
    assert call(transport, tool, submitted)["ok"]
    assert reason(call(transport, tool, submitted)) == "invalid_user_intent"
    assert len(adapter.calls) == before + (tool == "discover_candidates")


@pytest.mark.parametrize("change", ["expired", "session", "picks"])
def test_queue_token_expiry_session_and_exact_picks(adapter, change, monkeypatch):
    result = run(adapter)
    args = picks(result)
    adapter.settings["scrapecreators_agent_calls_enabled"] = False
    token = intent(adapter, args, tool="queue_discovered")["user_intent_token"]
    session = "fixture-session"
    if change == "expired":
        adapter.clock.value += 300
    elif change == "session":
        session = "another-session"
    else:
        args["keys"] = ["different"]
    result = tools.call_tool("queue_discovered", {**args, "user_intent_token": token},
                             origin="http://127.0.0.1:5180", session_hash=session)
    assert reason(result) == "invalid_user_intent" and adapter.idx.list_pending() == []


def test_queue_skips_all_reasons_and_caps_at_ten(adapter):
    template = fixture()["videos"][0]
    adapter.replies[:] = [(200, {"videos": [{**template, "url": f"https://www.youtube.com/watch?v=fixture{n:04d}"}
                                           for n in range(12)]})]
    result = run(adapter)
    candidates = result["candidates"]
    capture(adapter, candidates[0])
    capture(adapter, candidates[3], deleted=True)
    existing = adapter.idx.enqueue_pending(candidates[1]["url"], 30, "2026-10-16")
    candidates[2]["url"] = "https://evil.example/private"
    adapter.service._save_run(result)
    assert reason(call("registry", "queue_discovered", picks(result, *[c["key"] for c in candidates[:11]]))) == "keys"
    assert len(adapter.idx.list_pending()) == 1
    selected = [c["key"] for c in candidates[:9]] + ["unknown"]
    queued = call("registry", "queue_discovered", picks(result, *selected))
    assert len(queued["queued"]) == 6
    assert {row["reason"] for row in queued["skipped"]} == {"in_library", "already_queued", "unsupported_url", "unknown_key"}
    updated = saved(adapter, result)["candidates"]
    assert updated[1]["pending_id"] == existing
    assert updated[3]["state"] == "queued" and not updated[3]["in_library"]
    assert len(adapter.calls) == 1


@pytest.mark.parametrize("terminal", ["failed", "cancelled", "purged"])
def test_queue_needs_no_provider_access_and_refreshes_terminal_states(adapter, terminal):
    result = run(adapter)
    adapter.settings.update(scrapecreators_enabled=False, scrapecreators_key_invalid=True,
                            scrapecreators_daily_credit_cap=1)
    adapter.backend._get_saved_scrapecreators_key = Mock(side_effect=AssertionError("queue must not read a key"))
    adapter.service.transport = Mock(side_effect=AssertionError("queue must not send"))
    queued = call("registry", "queue_discovered", picks(result))
    pending = queued["queued"][0]["pending_id"]
    if terminal == "cancelled":
        assert adapter.idx.cancel_pending(pending)
    else:
        adapter.idx.mark_pending_failed(pending, "synthetic", adapter.service._now().isoformat(), force_final=True)
        if terminal == "purged":
            adapter.conn.execute("DELETE FROM pending_yoinks WHERE pending_id=?", (pending,))
            adapter.conn.commit()
    adapter.settings["scrapecreators_agent_calls_enabled"] = False
    expected_state = {"failed": "failed", "cancelled": "cancelled", "purged": "unavailable"}[terminal]
    assert read_run(adapter, result["run_id"])["candidates"][0]["state"] == expected_state
    assert saved(adapter, result)["candidates"][0]["state"] == expected_state
    adapter.settings["scrapecreators_agent_calls_enabled"] = True
    retried = call("registry", "queue_discovered", picks(result))
    assert len(retried["queued"]) == 1 and retried["skipped"] == []
    retry_id = retried["queued"][0]["pending_id"]
    assert retry_id != pending
    updated = saved(adapter, result)["candidates"][0]
    assert updated["state"] == "queued" and updated["pending_id"] == retry_id
    assert call("registry", "queue_discovered", picks(result))["skipped"] == [
        {"key": updated["key"], "reason": "already_queued"}]
    capture(adapter, result["candidates"][0])
    adapter.idx.mark_pending_succeeded(retry_id, "fixture-job")
    adapter.settings["scrapecreators_agent_calls_enabled"] = False
    refreshed = read_run(adapter, result["run_id"])["candidates"][0]
    assert refreshed["state"] == "captured" and refreshed["in_library"]
    assert saved(adapter, result)["candidates"][0] == refreshed
    assert adapter.service._credits_today(adapter.idx) == 1


@pytest.mark.parametrize("state", ["deleted", "missing", "purged_success", "purged_failure", "publishing"])
def test_capture_unavailable_deleted_and_real_failure_are_distinct(adapter, state):
    result = run(adapter)
    pending = adapter.service.queue_discovered(picks(result))["queued"][0]["pending_id"]
    candidate = result["candidates"][0]
    if state == "publishing":
        adapter.conn.execute("UPDATE pending_yoinks SET status='publishing' WHERE pending_id=?", (pending,))
        expected = "queued"
    elif state == "purged_failure":
        adapter.idx.mark_pending_failed(pending, "fixture failure", "2026-10-17", force_final=True)
        assert read_run(adapter, result["run_id"])["candidates"][0]["state"] == "failed"
        expected = "failed"  # A recorded real failure remains known after purge.
    else:
        capture(adapter, candidate)
        adapter.idx.mark_pending_succeeded(pending, "fixture-job")
        assert read_run(adapter, result["run_id"])["candidates"][0]["state"] == "captured"
        if state == "deleted":
            adapter.conn.execute("UPDATE yoinks SET deleted_at='2026-10-17' WHERE video_id=?", (candidate["video_id"],))
            expected = "deleted"
        else:
            adapter.conn.execute("DELETE FROM yoinks WHERE video_id=?", (candidate["video_id"],))
            expected = "unavailable"
    if state in ("purged_success", "purged_failure"):
        adapter.conn.execute("DELETE FROM pending_yoinks WHERE pending_id=?", (pending,))
    adapter.conn.commit()
    refreshed = read_run(adapter, result["run_id"])["candidates"][0]
    assert refreshed["state"] == expected and refreshed["in_library"] is False
    assert refreshed["pending_id"] == pending
    assert saved(adapter, result)["candidates"][0] == refreshed
    assert len(adapter.calls) == 1


def test_discover_shows_previously_deleted_capture_before_queueing(adapter):
    first = run(adapter)
    capture(adapter, first["candidates"][0], deleted=True)
    adapter.replies[:] = [(200, fixture())]
    result = run(adapter)
    assert result["candidates"][0]["state"] == "deleted"
    assert result["candidates"][0]["in_library"] is False
    assert adapter.idx.list_pending() == []


def test_discovery_save_retry_route_returns_receipt_without_provider(adapter, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(sc, "_atomic_write_text", Mock(side_effect=OSError("disk full")))
        result = run(adapter)
    adapter.service.transport = Mock(side_effect=AssertionError("save route must not send"))
    probe = Probe("/discovery/runs/save", {"run_id": result["run_id"]})
    probe.do_POST()
    assert probe.status == 200 and probe.payload["ok"] is True
    assert probe.payload["run"]["candidates"] == result["candidates"]
    assert not probe.payload["run"].get("save_failed")
    assert len(adapter.calls) == 1


@pytest.mark.parametrize("headers", [{"X-Uoink-Token": "wrong"}, {"Origin": "https://evil.example"},
                                     {"Origin": "chrome-extension://fixture"}])
def test_discovery_save_retry_route_gates_before_storage(adapter, monkeypatch, headers):
    retry = Mock(side_effect=AssertionError("unauthorized save"))
    monkeypatch.setattr(adapter.service, "retry_save", retry)
    probe = Probe("/discovery/runs/save", {"run_id": "fixture"}, headers)
    probe.do_POST()
    assert probe.status == 403
    retry.assert_not_called()


@pytest.mark.parametrize("body", [{}, {"run_id": "../outside"}, {"run_id": []},
                                 {"run_id": "fixture", "candidates": []}])
def test_discovery_save_retry_rejects_client_data(adapter, body):
    probe = Probe("/discovery/runs/save", body)
    probe.do_POST()
    assert probe.status == 400 and probe.payload["error"]["code"] == "invalid_request"
    assert adapter.calls == []


@pytest.mark.parametrize("bad", [ValueError("private failure"), [],
                                 {"run_id": "fixture", "balance": float("nan")}])
def test_discovery_save_retry_unexpected_errors_are_redacted(adapter, monkeypatch, bad):
    retry = Mock(side_effect=bad) if isinstance(bad, Exception) else Mock(return_value=bad)
    monkeypatch.setattr(adapter.service, "retry_save", retry)
    probe = Probe("/discovery/runs/save", {"run_id": "fixture"})
    probe.do_POST()
    assert probe.status == 500
    assert probe.payload == library_resources.ResourceError("internal_error").envelope()


@pytest.mark.parametrize("terminal", [None, "failed", "cancelled"])
def test_concurrent_picks_and_cross_run_dedupe(adapter, terminal):
    first = run(adapter)
    adapter.replies[:] = [(200, fixture())]
    second = run(adapter)
    if terminal is not None:
        pending = adapter.service.queue_discovered(picks(first))["queued"][0]["pending_id"]
        if terminal == "failed":
            adapter.idx.mark_pending_failed(pending, "synthetic", adapter.service._now().isoformat(), force_final=True)
        else:
            assert adapter.idx.cancel_pending(pending)
    barrier = threading.Barrier(2)
    results = []
    def pick(result):
        barrier.wait(timeout=5)
        results.append(adapter.service.queue_discovered(picks(result)))
    workers = [threading.Thread(target=pick, args=(result,)) for result in (first, second)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(5)
        assert not worker.is_alive()
    assert all(r["ok"] for r in results)
    assert sum(len(r["queued"]) for r in results) == 1
    active = [row for row in adapter.idx.list_pending() if row["status"] in ("pending", "running")]
    assert len(active) == 1
    assert len(adapter.idx.list_pending(include_terminal=True)) == (1 if terminal is None else 2)
    assert saved(adapter, first)["candidates"][0]["pending_id"] == saved(adapter, second)["candidates"][0]["pending_id"]


def test_queue_dedupes_across_independent_index_connections(adapter, monkeypatch):
    first = run(adapter)
    adapter.replies[:] = [(200, fixture())]
    second = run(adapter)
    path = adapter.root / "shared-index.db"
    connections = [sqlite3.connect(path, check_same_thread=False) for _ in range(2)]
    try:
        adapter.conn.backup(connections[0])
        indexes, services = [], []
        barrier = threading.Barrier(2)
        for conn in connections:
            conn.row_factory = sqlite3.Row
            idx = index.Index(conn, path)
            indexes.append(idx)
            backend = SimpleNamespace(**vars(adapter.backend))
            backend._get_index = lambda idx=idx: idx
            service = sc.DiscoveryService(backend)
            refresh = service._refresh_candidates
            def interleave(idx, receipt, refresh=refresh, seen=[]):
                refresh(idx, receipt)
                if not seen:
                    seen.append(True)
                    # Both independent connections have observed no active row.
                    barrier.wait(timeout=5)
            monkeypatch.setattr(service, "_refresh_candidates", interleave)
            services.append(service)
        # Separate processes do not share the module's threading lock.
        monkeypatch.setattr(sc, "_queue_lock", contextlib.nullcontext())
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(service.queue_discovered, picks(receipt))
                       for service, receipt in zip(services, (first, second))]
            results = [future.result(timeout=10) for future in futures]
        assert all(result["ok"] for result in results)
        assert sum(len(result["queued"]) for result in results) == 1
        assert sum(len(result["skipped"]) for result in results) == 1
        active = indexes[0].list_pending()
        assert len(active) == 1
        for service, receipt in zip(services, (first, second)):
            refreshed = service.read_run(receipt["run_id"])
            assert refreshed["candidates"][0]["pending_id"] == active[0]["pending_id"]
            assert saved(adapter, receipt)["candidates"][0]["pending_id"] == active[0]["pending_id"]
        # Ordinary callers retain enqueue_pending's unconditional insert.
        assert indexes[0].enqueue_pending(active[0]["url"], 30, "2026-10-16") != active[0]["pending_id"]
    finally:
        for conn in connections:
            conn.close()


@pytest.mark.parametrize("name,args", [
    ("discover_candidates", {**ARGS, "pages": True}),
    ("discover_candidates", {"mode": "creator", "platform": "youtube"}),
    ("discover_candidates", {**ARGS, "extra": "unknown"}),
    ("queue_discovered", {"run_id": "fixture", "keys": []}),
    ("queue_discovered", {"run_id": "../outside", "keys": ["a"]}),
    ("queue_discovered", {"run_id": "fixture", "keys": ["a"], "extra": True}),
])
def test_discovery_http_schema_errors_are_400_before_dispatch(adapter, monkeypatch, name, args):
    expected = tools.call_tool(name, args)
    assert expected["error"]["code"] == "invalid_request"
    dispatch = Mock(side_effect=AssertionError("invalid input must not dispatch"))
    monkeypatch.setattr(tools, "call_tool", dispatch)
    probe = Probe("/tools/" + name, args)
    probe.do_POST()
    assert probe.status == 400 and probe.payload == expected
    dispatch.assert_not_called()
    assert adapter.calls == [] and adapter.idx.list_pending() == []


@pytest.mark.parametrize("args", [
    {}, {"playbook": "missing", "arguments": {}},
    {"playbook": "outlier-posts", "arguments": []},
    {"playbook": "outlier-posts", "arguments": {"author": 1}},
    {"playbook": "outlier-posts", "arguments": {"author": "fixture", "extra": True}},
    {"playbook": "outlier-posts", "arguments": {"author": "fixture"}, "extra": True},
])
def test_playbook_http_schema_errors_use_domain_envelope(adapter, monkeypatch, args):
    reader = Mock(side_effect=AssertionError("validation must not open library storage"))
    monkeypatch.setattr(server, "_get_index", reader)
    monkeypatch.setattr(server, "_get_existing_index", reader)
    expected = tools.call_tool("get_playbook_input", args)
    assert expected["error"]["code"] == "invalid_request"
    probe = Probe("/tools/get_playbook_input", args)
    probe.do_POST()
    assert probe.status == 400 and probe.payload == expected
    reader.assert_not_called()


@pytest.mark.parametrize("transport", ["registry", "stdio", "http", "openapi"])
def test_discovery_unexpected_errors_are_standard_and_redacted(adapter, transport, monkeypatch):
    monkeypatch.setattr(adapter.service, "discover_candidates", Mock(side_effect=ValueError("private exception")))
    result = call(transport, "discover_candidates", ARGS)
    assert result == library_resources.ResourceError("internal_error").envelope()
    for malformed in ({"ok": True, "bad": float("inf")}, [], {"ok": "yes"}):
        monkeypatch.setattr(adapter.service, "queue_discovered", lambda *a, **kw: malformed)
        assert call(transport, "queue_discovered", {"run_id": "fixture", "keys": ["a"]}) == result


@pytest.mark.parametrize("name,limit", [("discover_candidates", 6), ("queue_discovered", 30)])
def test_registry_limiters_return_standard_envelopes(adapter, name, limit):
    limiter = tools.TOOL_REGISTRY[name].rate_limiter
    assert limiter.max_calls == limit
    args = ARGS if name == "discover_candidates" else {"run_id": "fixture", "keys": ["a"]}
    for _ in range(limit):
        call("registry", name, args)
    assert call("stdio", name, args)["error"]["code"] == "rate_limited"
    assert adapter.calls == []


def test_queue_rejects_paths_and_bad_input_before_storage(adapter, monkeypatch):
    loader = Mock(side_effect=AssertionError("must not open a run"))
    monkeypatch.setattr(adapter.service, "_load_run", loader)
    for args in ({"run_id": "../outside", "keys": ["a"]}, {"run_id": "a", "keys": []},
                 {"run_id": "a", "keys": ["a"], "origin": "forged"}, [], None):
        assert tools.call_tool("queue_discovered", args)["error"]["code"] == "invalid_request"
    loader.assert_not_called()


def test_saved_run_limits_and_identity_are_checked_before_queue(adapter):
    result = run(adapter)
    path = adapter.service._run_path(result["run_id"])
    path.write_bytes(b" " * (sc.MAX_RUN_BYTES + 1))
    assert reason(adapter.service.queue_discovered(picks(result))) == "discovery_run_too_large"
    path.write_text(json.dumps({**result, "run_id": "different"}), encoding="utf-8")
    assert reason(adapter.service.queue_discovered(picks(result))) == "discovery_run_invalid"
    assert adapter.idx.list_pending() == []


def test_stdio_budget_owner_is_declared_without_entrypoint_mutation():
    assert "get_playbook_input" in library_resources.BUDGETED_STDIO_TOOLS
    # Discovery may take three 8-second requests; it has separate bounds.
    assert tools.DISCOVERY_TOOL_NAMES.isdisjoint(library_resources.BUDGETED_STDIO_TOOLS)
    source = Path(uoink_mcp.__file__).read_text(encoding="utf-8")
    assert "BUDGETED_STDIO_TOOLS |=" not in source
    assert "_research_transcript_result" not in source
