"""MCP inventory, consent parity, scheduling and offline startup (current release)."""
from __future__ import annotations

from tests.mcp_sdk import handler_for

import asyncio
from dataclasses import replace
import json
import os
import runpy
import sys
import threading

import pytest
from uoink_mcp_tools import without_descriptions
from mcp import types

import index
import openapi_bridge
import server
import uoink_mcp
import uoink_mcp_tools as tools
from tests.test_c01_mcp_stdio import CORE_STDIO_TOOLS, ROOT, _StdioClient, _isolated_env
from tests.mcp_wire import StdioClient
from tests.test_discovery_queue import _run_stdio
from tests.test_library_adapters import mcp_call, post, valid_pin_operation


def call(name, args):
    handler = handler_for(uoink_mcp.mcp, "tools/call")
    result = _run_stdio(handler(types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(name=name, arguments=args))))
    body = json.loads(result.content[0].text)
    assert result.is_error is (body.get("ok") is not True)
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
            "clientInfo": {"name": "release-smoke", "version": "1"}}})
        assert client.wait_for(1)["result"]["serverInfo"]["version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = client.wait_for(2)["result"]["tools"]
        names = [t["name"] for t in listed]
        assert len(names) == count and tuple(names[:35]) == CORE_STDIO_TOOLS
        assert tuple(names) == tools.stdio_tool_names("core" if mode == "core" else "full")
        for tool in listed:
            spec = tools.TOOL_REGISTRY[tool["name"]]
            assert tool["inputSchema"] == tools.client_input_schema(spec.input_schema, tool["name"])
            assert tool["description"] == spec.description
            assert "outputSchema" not in tool, "Stdio preserves its text-only result contract"
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
                if name in tools.OUTPUT_SCHEMAS:
                    import jsonschema
                    jsonschema.validate(body, tools.OUTPUT_SCHEMAS[name])
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


def test_registry_handlers_run_on_the_event_loop_like_v391(monkeypatch):
    # Registry handlers share one Index connection with the Library read,
    # prompt and resource handlers, which run on the event loop. A worker
    # thread would let them interleave, so non-discovery handlers run on the
    # loop thread, one at a time, as the v3.9.1 FastMCP tools did.
    seen = {}

    def page(args):
        seen["page"] = threading.get_ident()
        return {"ok": True}

    monkeypatch.setitem(tools.TOOL_REGISTRY, "uoink_page",
                        replace(tools.TOOL_REGISTRY["uoink_page"], handler=page, rate_limiter=None))
    handler = handler_for(uoink_mcp.mcp, "tools/call")

    async def exercise():
        seen["loop"] = threading.get_ident()
        response = await handler(types.CallToolRequest(
            method="tools/call", params=types.CallToolRequestParams(name="uoink_page", arguments={})))
        assert not response.is_error
    _run_stdio(exercise())
    assert seen["page"] == seen["loop"]


def test_public_manifest_advertises_full_default():
    manifest = openapi_bridge.build_well_known("http://example.invalid", version="3.10.0", tool_count=91)
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
    from types import SimpleNamespace
    # This is the legacy PID-file/mtime contract. Darwin has a full native
    # identity record, covered separately below on every test host.
    import uoink_agent_runtime
    legacy = SimpleNamespace(platform="win32" if os.name == "nt" else "linux")
    monkeypatch.setattr(uoink_mcp, "sys", legacy)
    # 3.10 moved the resident check into uoink_agent_runtime.helper_running.
    monkeypatch.setattr(uoink_agent_runtime, "sys", legacy)
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


@pytest.mark.parametrize("state,reused,expected", [
    ("alive", False, True), ("dead", False, False),
    ("unknown", False, False), ("alive", True, False),
])
def test_darwin_resident_requires_native_original_identity(tmp_path, monkeypatch, state, reused, expected):
    import json
    import sys
    from types import SimpleNamespace
    import _platform
    import uoink_agent_runtime
    monkeypatch.setattr(uoink_mcp, "sys", SimpleNamespace(platform="darwin"))
    # 3.10 moved the resident check into uoink_agent_runtime.helper_running.
    monkeypatch.setattr(uoink_agent_runtime, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(uoink_mcp._install_isolation, "current_binding", lambda: None)
    monkeypatch.setattr(server, "HERE", tmp_path)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    script = tmp_path / "server.py"
    script.write_text("# fixture")
    (tmp_path / "runtime-identity.json").write_text(json.dumps({
        "pid": 77, "created_ms": 1700000000123.456,
        "executable": sys.executable, "script": str(script)}))
    monkeypatch.setattr(_platform, "darwin_observe", lambda *a, **k:
                        _platform.DarwinProcessObservation(state,
                            1700000000123456 + int(reused), sys.executable))
    assert uoink_mcp._helper_running() is expected


FLATTENED = {"claim_library_work", "apply_reshelving", "set_source_consent"}


@pytest.mark.parametrize("path", ["/mcp/v1", "/mcp/v1/tools/list"])
def test_http_and_stdio_list_identical_client_schemas(local_backend, monkeypatch, path, tmp_path):
    monkeypatch.setenv("UOINK_MCP_TOOLSET", "full")
    frozen = json.dumps(tools.list_tools(), sort_keys=True)
    http = post(path, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert http.status == 200
    listed = http.payload["result"]["tools"]
    with StdioClient.launch(tmp_path) as client:
        client.initialize()
        stdio = client.request(2, "tools/list")["result"]["tools"]
    fields = ("name", "description", "inputSchema")
    assert [{k: t[k] for k in fields} for t in listed] == [
        {k: t[k] for k in fields} for t in stdio]
    assert len(listed) == len(tools.TOOL_REGISTRY) == 91
    changed = set()
    for tool in listed:
        schema = tool["inputSchema"]
        assert schema.get("type") == "object", tool["name"]
        assert not {"oneOf", "anyOf", "allOf", "not"} & set(schema), tool["name"]
        spec = tools.TOOL_REGISTRY[tool["name"]]
        assert schema == tools.client_input_schema(spec.input_schema, tool["name"])
        if without_descriptions(schema) != without_descriptions(spec.input_schema):
            changed.add(tool["name"])
    assert changed == FLATTENED
    assert json.dumps(tools.list_tools(), sort_keys=True) == frozen


@pytest.mark.parametrize("name,args", [
    ("apply_reshelving", {"mode": "apply", "expected_projection_revision": 1}),
    ("claim_library_work", {"action": "renew", "run_id": "r", "client_id": "c"}),
    ("claim_library_work", {"action": "claim", "run_id": "r", "client_id": "c", "work_id": "w"}),
    ("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "on",
                            "expected_revision": 0, "operation_key": "fixture", "user_intent_token": "A" * 43}),
    ("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "off",
                            "expected_revision": 0, "expected_cursor_revision": 0,
                            "operation_key": "fixture", "user_intent_token": "A" * 43}),
])
@pytest.mark.parametrize("path", ["/mcp/v1", "/mcp/v1/tools/call"])
def test_http_flattening_preserves_frozen_schema_refusals(local_backend, name, args, path):
    expected = call(name, args)
    # Phase 3's frozen source contract calls this validation_error; preserve
    # it as well as Phase 2's invalid_request, including message/details.
    code = "validation_error" if name == "set_source_consent" else "invalid_request"
    assert expected["ok"] is False and expected["error"]["code"] == code
    http = post(path, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})
    assert http.status == 200
    result = http.payload["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == json.loads(result["content"][0]["text"]) == expected


def test_listed_schemas_have_no_top_level_combinators(tmp_path):
    # The Anthropic API rejects top-level oneOf/anyOf/allOf, and Claude Code
    # then shows none of the server's tools (seen with the 3.9.2 build).
    with StdioClient.launch(tmp_path) as client:
        client.initialize()
        listed = client.request(2, "tools/list")["result"]["tools"]
    changed = set()
    for tool in listed:
        schema = tool["inputSchema"]
        assert schema.get("type") == "object", tool["name"]
        assert not {"oneOf", "anyOf", "allOf", "not"} & set(schema), tool["name"]
        if without_descriptions(schema) != without_descriptions(tools.TOOL_REGISTRY[tool["name"]].input_schema):
            changed.add(tool["name"])
    assert changed == FLATTENED


def test_flattened_schemas_keep_every_variant_field_and_defs():
    for name in FLATTENED:
        frozen = tools.TOOL_REGISTRY[name].input_schema
        flat = tools.client_input_schema(frozen)
        assert flat.get("$defs") == frozen.get("$defs")
        fields = set(frozen.get("properties", {}))
        for branch in frozen.get("oneOf", []):
            fields |= set(branch.get("properties", {}))
        assert set(flat["properties"]) == fields, name
        # Only fields every variant requires are advertised as required.
        for field in flat.get("required", []):
            assert field in frozen.get("required", []) or all(
                field in b.get("required", []) for b in frozen["oneOf"]), (name, field)
    flat = tools.client_input_schema(tools.TOOL_REGISTRY["apply_reshelving"].input_schema)
    assert flat["properties"]["mode"] == {"anyOf": [
        {"const": "preview", "default": "preview"}, {"const": "apply"}]}
    assert flat["required"] == ["expected_projection_revision"]


def test_flattened_schema_does_not_loosen_server_validation():
    # The advertised union would allow apply mode without its preview fields;
    # the handler still validates the frozen oneOf and refuses it.
    body = call("apply_reshelving", {"mode": "apply", "expected_projection_revision": 1})
    assert body["error"]["code"] == "invalid_request" and body["error"]["details"]["field"] == "preview_id"
    body = call("claim_library_work", {"action": "renew", "run_id": "r", "client_id": "c"})
    assert body["error"]["code"] == "invalid_request" and body["error"]["details"]["field"] == "work_id"
