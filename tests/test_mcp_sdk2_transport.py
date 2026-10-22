"""SDK 2 product boundaries beyond the unchanged SDK 1 domain goldens."""
import json
import sys

import anyio
import pytest
from mcp import types
from mcp.server import Server
from mcp.shared.message import SessionMessage

import uoink_mcp
from tests.mcp_wire import ROOT, StdioClient, isolated_env
from tests.test_mcp_wire import GOLDEN, modern_domain, modern_params


def test_server_uses_public_api_and_explicit_cache_and_telemetry_policy():
    assert isinstance(uoink_mcp.mcp, Server)
    assert uoink_mcp.mcp.middleware == []
    assert uoink_mcp.mcp.version == uoink_mcp.server.VERSION
    assert all(hint.ttl_ms == 0 and hint.scope == "private"
               for hint in uoink_mcp.mcp.cache_hints.values())


@pytest.mark.parametrize("entry", ["uoink_mcp.py", "yoink_mcp.py"])
@pytest.mark.parametrize("from_install", [False, True])
@pytest.mark.parametrize("modern", [False, True])
def test_both_script_entries_and_install_marker(tmp_path, entry, from_install, modern):
    import uoink_install_isolation as iso
    env = isolated_env(tmp_path)
    command = [sys.executable, "-B", "-P", str(ROOT / entry)]
    if from_install:
        with iso.bound_isolation(profile=tmp_path / "profile", app_dir=tmp_path / "app",
                                 port=int(env[iso.ENV_PORT])) as binding:
            iso.write_install_marker(tmp_path / "app", binding)
        command += ["--isolated-from-install-dir", str(tmp_path / "app")]
    with StdioClient(command, tmp_path, env) as client:
        if not modern:
            assert client.initialize()["result"]["serverInfo"] == {
                "name": "uoink", "version": uoink_mcp.server.VERSION}
        params = modern_params() if modern else None
        result = client.request(2, "tools/list", params)["result"]
        assert (modern_domain(result, cacheable=True) if modern else result)["tools"] == GOLDEN["tools"]
        params = {"name": "search_clips", "arguments": {"query": "absent-m2-topic"}}
        result = client.request(3, "tools/call", modern_params(params) if modern else params)["result"]
        assert (modern_domain(result) if modern else result) == GOLDEN["success"]
    assert client.proc.returncode == 0


def test_only_trusted_tools_list_method_gets_inventory_allowance():
    async def check():
        token = uoink_mcp._stdio_requests.set({})
        try:
            frames = []

            class Output:
                async def write(self, text):
                    frames.append(text)

                async def flush(self):
                    pass

            # Equal payloads with different trusted request methods must have
            # different caps. The tool result's shape cannot grant an exception.
            result = {"tools": [{"name": "x" * 70000}]}
            for request_id, method in [(1, "tools/list"), (2, "tools/call")]:
                uoink_mcp._begin_inbound_transport_scope(types.JSONRPCRequest(
                    jsonrpc="2.0", id=request_id, method=method,
                    params={"name": "search_clips", "arguments": {}} if method == "tools/call" else None))
                await uoink_mcp._deliver_bounded_outbound(SessionMessage(types.JSONRPCResponse(
                    jsonrpc="2.0", id=request_id, result=result)), Output())
            assert json.loads(frames[0])["result"] == result
            assert 65536 < len(frames[0].encode()) <= 262145
            assert json.loads(frames[1])["error"]["code"] == -32600
            assert len(frames[1].encode()) <= 65537
            assert uoink_mcp._stdio_requests.get() == {}
        finally:
            uoink_mcp._release_stdio_requests()
            uoink_mcp._stdio_requests.reset(token)
    anyio.run(check)
