"""Keep the legacy HTTP contract separate from SDK 2 stdio negotiation."""
from contextlib import asynccontextmanager
import http.client
import json
import os
from pathlib import Path

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
import pytest

import server
from tests.mcp_wire import HttpClient, ROOT, registry_golden, rpc
from tests.test_mcp_wire import GOLDEN, seed_library


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_sdk2_http_client_completes_list_and_call(tmp_path, mode):
    seed_library(tmp_path)
    evidence = {"mode": mode, "sdk": "2.3.0", "requests": []}

    async def check(url):
        async def trace(response):
            body = await response.aread()
            request = json.loads(response.request.content) if response.request.method == "POST" else None
            evidence["requests"].append({"method": response.request.method,
                "rpc_method": request.get("method") if request else None,
                "status": response.status_code, "body": json.loads(body) if body else None})

        async with httpx2.AsyncClient(headers={"X-Uoink-Token": HttpClient.TOKEN},
                                     trust_env=False, event_hooks={"response": [trace]}) as http:
            @asynccontextmanager
            async def transport():
                async with streamable_http_client(url, http_client=http) as (reads, writes):
                    yield reads, writes

            with anyio.fail_after(10):
                async with Client(transport(), mode=mode, read_timeout_seconds=5) as client:
                    evidence["protocol_version"] = client.protocol_version
                    listing = await client.list_tools()
                    assert [t.model_dump(by_alias=True, exclude_none=True) for t in listing.tools] == registry_golden(structured_results=True)
                    called = await client.call_tool("search_clips", {"query": "absent-m2-topic"})
                    assert called.is_error is False
                    assert called.structured_content == json.loads(GOLDEN["success"]["content"][0]["text"])
                    assert json.loads(called.content[0].text) == called.structured_content
                    evidence.update(tools=len(listing.tools), call=called.model_dump(by_alias=True, exclude_none=True))

    with HttpClient(tmp_path) as http:
        anyio.run(check, f"http://127.0.0.1:{http.port}/mcp/v1")
    assert evidence["protocol_version"] == "2025-11-25"
    assert evidence["tools"] == 92
    requests = evidence["requests"]
    assert requests[0]["rpc_method"] == ("server/discover" if mode == "auto" else "initialize")
    if mode == "auto":
        assert requests[0]["status"] == 200
        assert requests[0]["body"]["error"]["code"] == -32601
        assert requests[1]["rpc_method"] == "initialize"
    assert any(r["rpc_method"] == "notifications/initialized" and r["status"] == 202 and r["body"] is None for r in requests)
    destination = os.environ.get("M2_WIRE_EVIDENCE")
    if destination:
        path = Path(destination) / f"m4-sdk2-http-{mode}.json"
        assert path.resolve().is_relative_to(ROOT / "_scratch")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")


def test_http_body_guards_alias_token_and_domain_errors(tmp_path):
    seed_library(tmp_path)
    with HttpClient(tmp_path) as client:
        def post(raw, overrides=None):
            headers = {"Content-Type": "application/json", "X-Yoink-Token": client.TOKEN,
                       "Host": f"127.0.0.1:{client.port}"}
            headers.update(overrides or {})
            conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=5)
            try:
                conn.request("POST", "/mcp/v1", raw, headers)
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()

        for raw, headers, status in [
            (b'{', {}, 400), (b'[]', {}, 400), (b'\xff', {}, 400),
            (b'{"id":1,"id":2}', {}, 400), (b'{"x":NaN}', {}, 400),
            (b'{}', {"Content-Type": "text/plain"}, 415),
            (b'{}', {"Content-Length": "-1"}, 400),
            (b'{}', {"Content-Length": "bad"}, 400),
            (b'{}', {"Content-Length": str(server.MAX_BODY_BYTES + 1)}, 413),
        ]:
            code, body = post(raw, headers)
            assert code == status and body["ok"] is False
        assert post(json.dumps(rpc(1, "ping")).encode()) == (200, {"jsonrpc": "2.0", "id": 1, "result": {}})
        for params, code in [({}, -32602), ({"name": "search_clips", "arguments": []}, None)]:
            # [] historically becomes {}; preserve the adapter's existing rule.
            status, body = client.post(rpc(2, "tools/call", params))
            assert status == 200
            if code:
                assert body["error"]["code"] == code
            else:
                assert "result" in body
        for alias in (False, True):
            status, body = client.post(rpc(3, "tools/call", {"name": "get_playbook_input", "arguments": {}}),
                                      path="/mcp/v1/tools/call" if alias else "/mcp/v1")
            assert status == 200
            result = body["result"]
            assert result["isError"] is True
            assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
            assert result["structuredContent"] == json.loads(GOLDEN["invalid"]["content"][0]["text"])
