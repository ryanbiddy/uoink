"""3.9.2 stdio inventory, consent parity, scheduling and offline startup."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
import runpy
import sys
import threading

import pytest
from mcp import types

import index
import openapi_bridge
import server
import uoink_mcp
import uoink_mcp_tools as tools
from tests.test_c01_mcp_stdio import CORE_STDIO_TOOLS, ROOT, _StdioClient, _isolated_env
from tests.test_discovery_queue import _run_stdio
from tests.test_library_adapters import mcp_call, valid_pin_operation


def call(name, args):
    handler = uoink_mcp.mcp._mcp_server.request_handlers[types.CallToolRequest]
    result = _run_stdio(handler(types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(name=name, arguments=args)))).root
    body = json.loads(result.content[0].text)
    assert result.isError is (body.get("ok") is not True)
    return body


@pytest.mark.parametrize("mode,count", [("default", 91), ("full", 91), ("core", 35), ("unknown", 91)])
def test_real_stdio_toolsets_and_helper_down(tmp_path, mode, count):
    env = _isolated_env(str(tmp_path))
    if mode == "default":
        env.pop("UOINK_MCP_TOOLSET", None)
    else:
        env["UOINK_MCP_TOOLSET"] = mode
    client = _StdioClient([sys.executable, str(ROOT / "uoink_mcp.py")], ROOT, env)
    try:
        client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "release-392-smoke", "version": "1"}}})
        assert client.wait_for(1)["result"]["serverInfo"]["version"] == "3.9.2"
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = client.wait_for(2)["result"]["tools"]
        names = [t["name"] for t in listed]
        assert len(names) == count and tuple(names[:35]) == CORE_STDIO_TOOLS
        assert tuple(names) == tools.stdio_tool_names("core" if mode == "core" else "full")
        for tool in listed:
            spec = tools.TOOL_REGISTRY[tool["name"]]
            assert tool["inputSchema"] == spec.input_schema
            assert tool["description"] == spec.description
        client.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "poll_monitored_playlist", "arguments": {"playlist_id": 1}}})
        result = client.wait_for(3)["result"]
        assert result["isError"] is True
        error = json.loads(result["content"][0]["text"])["error"]
        assert error == "tool not found" if mode == "core" else "Open Uoink first" in error
        if mode == "unknown":
            assert any("unknown UOINK_MCP_TOOLSET" in line for line in client.stderr_lines)
        if mode == "full":
            # Exercise each newly exposed handler in a fresh stdio process with
            # no helper. Local operations use disposable storage; network tools
            # receive no URL and refuse before any fetch or credential use.
            fixture_args = {
                "uoink_note": {"text": "Offline release fixture", "title": "Fixture"},
                "uoink_image": {"image_base64": "invalid base64"},
                "set_user_role": {"role": "researcher"},
                "update_user_taste": {"section": "avoid", "content": "Fixture"},
                "add_allowed_site": {"url_pattern": "example.invalid"},
                "remove_allowed_site": {"url_pattern": "example.invalid"},
            }
            local_successes = {
                "get_schema_version", "get_user_role", "set_user_role",
                "list_sources", "list_monitored_playlists", "list_monitored_playlist_events",
                "get_user_taste", "get_user_memory", "update_user_taste", "get_facet_taxonomy",
                "assemble_workspace", "list_workspaces", "list_claims", "list_scripts",
                "list_writing_pieces", "list_style_anchors", "uoink_note",
                "list_allowed_sites", "add_allowed_site", "remove_allowed_site",
            }
            for request_id, name in enumerate((n for n in names if n not in CORE_STDIO_TOOLS), 4):
                client.send({"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                             "params": {"name": name, "arguments": fixture_args.get(name, {})}})
                response = client.wait_for(request_id)
                assert "result" in response, (name, response)
                body = json.loads(response["result"]["content"][0]["text"])
                assert type(body.get("ok")) is bool, (name, body)
                if name in local_successes:
                    assert body["ok"] is True, (name, body)
                if body["ok"] is False:
                    error = body["error"]
                    if isinstance(error, dict):
                        assert error["code"] != "internal_error", (name, body)
                    else:
                        assert "tool failed:" not in error and "has no attribute" not in error, (name, body)
            print("helper-down smoke: all 56 new handlers answered; local writes used the temp profile")
        print(f"stdio smoke: mode={mode}, tools={count}, core-prefix=35, schemas=exact, helper-down=actionable")
    finally:
        client.close()


@pytest.fixture
def local_backend(tmp_path, monkeypatch):
    idx = index.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "TOKEN", "synthetic-release-test-session")
    monkeypatch.setattr(tools, "_backend", server)
    for limiter in tools._LIBRARY_RATE_LIMITERS.values():
        monkeypatch.setattr(limiter, "_calls", [])
    yield idx
    idx.close()


@pytest.mark.parametrize("token", [None, "A" * 43])
def test_dashboard_intent_refusal_matches_http(local_backend, token):
    args = valid_pin_operation()
    if token is not None:
        args["user_intent_token"] = token
    stdio = call("pin_shelf", args)
    http = mcp_call("pin_shelf", args).payload["result"]["structuredContent"]
    assert stdio == http and stdio["ok"] is False
    assert stdio["error"]["code"] in {"invalid_request", "invalid_user_intent", "user_intent_required"}


def test_library_apply_stays_off_on_stdio_and_http(local_backend):
    args = {"mode": "apply", "preview_id": "fixture", "expected_projection_revision": 0,
            "delta_hash": "a" * 64, "operation_key": "fixture-apply"}
    stdio = call("apply_reshelving", args)
    http = mcp_call("apply_reshelving", args).payload["result"]["structuredContent"]
    assert stdio == http and stdio["error"]["code"] == "apply_disabled"


def _tool_request(name):
    return types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(name=name, arguments={}))


def test_new_long_tool_keeps_stdio_responsive_and_serializes_handlers(monkeypatch):
    # Handlers share one Index connection, so registry calls run one at a
    # time; tools/list still answers while a long capture holds the slot.
    entered, release = threading.Event(), threading.Event()
    ran = []

    def capture(args):
        entered.set()
        assert release.wait(5)
        return {"ok": True}

    def taxonomy(args):
        ran.append("taxonomy")
        return {"ok": True}

    monkeypatch.setitem(tools.TOOL_REGISTRY, "uoink_page",
                        replace(tools.TOOL_REGISTRY["uoink_page"], handler=capture, rate_limiter=None))
    monkeypatch.setitem(tools.TOOL_REGISTRY, "get_facet_taxonomy",
                        replace(tools.TOOL_REGISTRY["get_facet_taxonomy"], handler=taxonomy))
    handlers = uoink_mcp.mcp._mcp_server.request_handlers
    handler = handlers[types.CallToolRequest]

    async def exercise():
        pending = asyncio.create_task(handler(_tool_request("uoink_page")))
        try:
            while not entered.is_set():
                await asyncio.sleep(.01)
            listed = await asyncio.wait_for(handlers[types.ListToolsRequest](
                types.ListToolsRequest(method="tools/list")), 1)
            assert len(listed.root.tools) == 91 and not pending.done()
            queued = asyncio.create_task(handler(_tool_request("get_facet_taxonomy")))
            await asyncio.sleep(.2)
            assert not queued.done() and ran == []
        finally:
            release.set()
            await pending
        response = await asyncio.wait_for(queued, 5)
        assert not response.root.isError and ran == ["taxonomy"]
    _run_stdio(exercise())


def test_cancelled_queued_call_never_starts(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    ran = []

    def capture(args):
        entered.set()
        assert release.wait(5)
        return {"ok": True}

    def tweet(args):
        ran.append("write_tweet")
        return {"ok": True}

    monkeypatch.setitem(tools.TOOL_REGISTRY, "uoink_page",
                        replace(tools.TOOL_REGISTRY["uoink_page"], handler=capture, rate_limiter=None))
    monkeypatch.setitem(tools.TOOL_REGISTRY, "write_tweet",
                        replace(tools.TOOL_REGISTRY["write_tweet"], handler=tweet, rate_limiter=None))
    handler = uoink_mcp.mcp._mcp_server.request_handlers[types.CallToolRequest]

    async def exercise():
        pending = asyncio.create_task(handler(_tool_request("uoink_page")))
        try:
            while not entered.is_set():
                await asyncio.sleep(.01)
            queued = asyncio.create_task(handler(_tool_request("write_tweet")))
            await asyncio.sleep(.2)
            queued.cancel()
            with pytest.raises(asyncio.CancelledError):
                await queued
        finally:
            release.set()
            await pending
        # Give the abandoned worker thread time to take the slot and see the flag.
        for _ in range(50):
            if not uoink_mcp._REGISTRY_CALL_LOCK.locked():
                break
            await asyncio.sleep(.02)
        await asyncio.sleep(.1)
        assert ran == []
    _run_stdio(exercise())


def test_public_manifest_advertises_full_default():
    manifest = openapi_bridge.build_well_known("http://example.invalid", version="3.9.2", tool_count=91)
    assert manifest["transports"] == ["stdio", "http"]
    assert manifest["stdio_tool_count"] == 91
    assert manifest["stdio_toolsets"] == {"full": 91, "core": 35}


def test_inventory_checker_fails_closed_on_missing_tool(monkeypatch):
    check = runpy.run_path(str(ROOT / "scripts/check_mcp_inventory.py"))["check"]
    monkeypatch.setattr(tools, "TOOL_REGISTRY", {
        name: spec for name, spec in tools.TOOL_REGISTRY.items() if name != "uoink_note"})
    with pytest.raises(AssertionError):
        check()


@pytest.mark.parametrize("state,reused,expected", [
    ("alive", False, True), ("dead", False, False),
    ("unknown", False, False), ("alive", True, False),
])
def test_resident_helper_pid_requires_live_original_process(tmp_path, monkeypatch, state, reused, expected):
    iso = uoink_mcp._install_isolation
    monkeypatch.setattr(iso, "current_binding", lambda: None)
    monkeypatch.setattr(server, "HERE", tmp_path)
    pid_path = tmp_path / "server.pid"
    pid_path.write_text("77", encoding="utf-8")
    created_ms = pid_path.stat().st_mtime_ns // 1_000_000 + (1000 if reused else -1000)
    executable = str(tmp_path / "python.exe")
    monkeypatch.setattr(iso, "current_process_executable", lambda: executable)
    monkeypatch.setattr(iso, "_process_executable", lambda pid: executable)
    monkeypatch.setattr(iso, "_pid_liveness", lambda pid, created: state)
    if os.name == "nt":
        monkeypatch.setattr(iso, "_windows_open_process", lambda pid, access: (1, 0))
        monkeypatch.setattr(iso, "_windows_process_created_ms", lambda handle: created_ms)
        monkeypatch.setattr(iso, "_windows_close_handle", lambda handle: None)
    else:
        monkeypatch.setattr(iso, "_posix_process_created_ms", lambda pid: created_ms)
    assert uoink_mcp._helper_running() is expected
