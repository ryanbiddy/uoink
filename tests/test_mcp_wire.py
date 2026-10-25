"""M2: SDK 1 product boundary goldens, independent of SDK Python models.

The registry is re-derived on every run and must match the checked-in golden
before either transport is compared. A changed registry cannot silently update
the baseline. Regenerate intentionally with tests/update_mcp_wire_goldens.py.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest
from uoink_mcp_tools import without_descriptions

from tests.mcp_wire import (
    ROOT, LEGACY_VERSIONS, HttpClient, StdioClient, initialize_request, registry_golden, rpc,
)
from tests.mcp_wire_fixtures import seed_library

FIXTURES = Path(__file__).parent / "fixtures/mcp_wire"
GOLDEN = json.loads((FIXTURES / "sdk1.json").read_text(encoding="utf-8"))
MODERN = json.loads((FIXTURES / "modern-2026-07-28.json").read_text(encoding="utf-8"))


def expected_initialize(transport, version):
    import _platform
    result = copy.deepcopy(GOLDEN[transport + "_initialize"])
    result["protocolVersion"] = version
    result["serverInfo"]["version"] = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    result["instructions"] += _platform.capability_notice()
    return result


def save_evidence(client, name):
    directory = os.environ.get("M2_WIRE_EVIDENCE")
    if directory:
        path = Path(directory).resolve() / (name + ".jsonl")
        assert path.is_relative_to(ROOT / "_scratch")
        if isinstance(client, StdioClient):
            client.save(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                    for row in client.transcript), encoding="utf-8")


@pytest.fixture(scope="module")
def inventory():
    import uoink_mcp_tools as tools
    frozen = copy.deepcopy(tools.list_tools())
    full, core = registry_golden(), registry_golden("core")
    assert full == GOLDEN["tools"]
    assert core == full[:35]
    assert len(full) == 91 and len(core) == 35
    assert tools.list_tools() == frozen
    changed = set()
    for tool in full:
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert not {"oneOf", "anyOf", "allOf", "not"} & schema.keys()
        assert all(type(tool["annotations"][hint]) is bool for hint in (
            "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"))
        if without_descriptions(schema) != without_descriptions(tools.TOOL_REGISTRY[tool["name"]].input_schema):
            changed.add(tool["name"])
    assert changed == {"claim_library_work", "apply_reshelving", "set_source_consent"}
    http = registry_golden(structured_results=True)
    assert [{k: v for k, v in t.items() if k != "outputSchema"} for t in http] == full
    return {"full": full, "core": core, "http": http}


@pytest.mark.parametrize("version", LEGACY_VERSIONS)
@pytest.mark.parametrize("toolset", ["full", "core"])
def test_legacy_stdio_wire_golden(tmp_path, version, toolset, inventory):
    uri = seed_library(tmp_path)
    assert uri == GOLDEN["resource"]["contents"][0]["uri"]
    with StdioClient.launch(tmp_path, toolset=toolset) as client:
        try:
            assert client.initialize(version) == {
                "jsonrpc": "2.0", "id": 1, "result": expected_initialize("stdio", version)}
            client.assert_quiet()
            listed = client.request(2, "tools/list")
            assert listed == {"jsonrpc": "2.0", "id": 2, "result": {"tools": inventory[toolset]}}
            # This inventory exceeds the ordinary 64 KiB result allowance.
            if toolset == "full":
                assert 65536 < len(client.raw_stdout_lines[-1].encode("utf-8")) <= 256 * 1024 + 1
            cases = [
                ("templates", "resources/templates/list", None),
                ("prompts", "prompts/list", None),
                ("resource", "resources/read", {"uri": uri}),
                ("prompt", "prompts/get", {"name": "consult-library",
                                           "arguments": {"topic": "absent-m2-topic"}}),
                ("success", "tools/call", {"name": "search_clips", "arguments": {"query": "absent-m2-topic"}}),
                ("invalid", "tools/call", {"name": "get_playbook_input", "arguments": {}}),
            ]
            for request_id, (label, method, params) in enumerate(cases, 3):
                assert client.request(request_id, method, params) == {
                    "jsonrpc": "2.0", "id": request_id, "result": GOLDEN[label]}
            assert len(GOLDEN["templates"]["resourceTemplates"]) == 5
            assert len(GOLDEN["prompts"]["prompts"]) == 9
            for label, ok in (("success", True), ("invalid", False)):
                result = GOLDEN[label]
                assert "structuredContent" not in result
                assert result["isError"] is not ok
                assert json.loads(result["content"][0]["text"])["ok"] is ok
            # Deliberate SDK 2 change: proper JSON-RPC method-not-found.
            assert client.request(9, "m2/unknown") == {
                "jsonrpc": "2.0", "id": 9, "error": {
                    "code": -32601, "message": "Method not found", "data": "m2/unknown"}}
            assert client.request(10, "ping") == {"jsonrpc": "2.0", "id": 10, "result": {}}
            client.assert_quiet()
        finally:
            save_evidence(client, f"legacy-{version}-{toolset}")
    assert client.proc.returncode == 0


BAD_LINES = {
    "malformed": "{",
    "duplicate_keys": '{"jsonrpc":"2.0","id":2,"method":"ping","method":"tools/list"}',
    "null_id": '{"jsonrpc":"2.0","id":null,"method":"ping"}',
    "bool_id": '{"jsonrpc":"2.0","id":true,"method":"ping"}',
    "float_id": '{"jsonrpc":"2.0","id":1.5,"method":"ping"}',
    "batch": '[]',
    "oversized": '{"jsonrpc":"2.0","id":2,"method":"ping","params":{"padding":"' + "x" * 65536 + '"}}',
}


@pytest.mark.parametrize("version", LEGACY_VERSIONS)
@pytest.mark.parametrize("case", BAD_LINES)
def test_stdio_invalid_line_refusal_and_connection_survives(tmp_path, version, case):
    # Deliberate SDK 2 boundary change: explicit bounded parse/invalid-request
    # refusals replace logging and silent dropping at the product boundary.
    with StdioClient.launch(tmp_path) as client:
        try:
            assert "result" in client.initialize(version)
            client.send_raw(BAD_LINES[case])
            if case in ("malformed", "duplicate_keys"):
                assert client.receive() == {"jsonrpc": "2.0", "id": None, "error": {
                    "code": -32700, "message": "Invalid JSON-RPC message"}}
            else:
                refusal = client.receive()
                message = ("Inbound request exceeds protocol limits" if case == "oversized" else
                           "Empty JSON-RPC batch" if case == "batch" else "Invalid request ID")
                assert refusal == {"jsonrpc": "2.0", "id": None, "error": {
                    "code": -32600, "message": message}}
                assert len(json.dumps(refusal).encode()) <= 65536
            client.send(rpc(99, "ping"))
            # receive(), rather than wait_for(), also catches an extra response
            # to the null ID instead of silently parking it in the client.
            assert client.receive() == {"jsonrpc": "2.0", "id": 99, "result": {}}
            client.assert_quiet()
        finally:
            save_evidence(client, f"parser-{version}-{case}")
    assert client.proc.returncode == 0


@pytest.mark.parametrize("version", LEGACY_VERSIONS)
@pytest.mark.parametrize("aliases", [False, True])
def test_legacy_http_wire_golden(tmp_path, version, aliases, inventory):
    seed_library(tmp_path)
    path = lambda method: "/mcp/v1/" + method if aliases else "/mcp/v1"
    with HttpClient(tmp_path) as client:
        try:
            assert client.post(initialize_request(version), path=path("initialize")) == (200, {
                "jsonrpc": "2.0", "id": 1, "result": expected_initialize("http", version)})
            assert client.post({"jsonrpc": "2.0", "method": "notifications/initialized"}) == (202, None)
            assert client.post(rpc(2, "tools/list"), path=path("tools/list")) == (200, {
                "jsonrpc": "2.0", "id": 2, "result": {"tools": inventory["http"]}})
            call = rpc(3, "tools/call", {"name": "search_clips", "arguments": {"query": "absent-m2-topic"}})
            expected = dict(GOLDEN["success"], structuredContent=json.loads(
                GOLDEN["success"]["content"][0]["text"]))
            assert client.post(call, path=path("tools/call")) == (200, {
                "jsonrpc": "2.0", "id": 3, "result": expected})
            assert json.loads(expected["content"][0]["text"]) == expected["structuredContent"]
            for token in (None, "wrong-synthetic-token"):
                assert client.post(call, token=token) == (403, GOLDEN["http_token_refusal"])
            for host in ("attacker.invalid", "127.0.0.1:1"):
                assert client.post(call, host=host) == (403, GOLDEN["http_host_refusal"])
            assert client.post(rpc(4, "m2/unknown")) == (200, {
                "jsonrpc": "2.0", "id": 4, "error": GOLDEN["unknown_http"]})
        finally:
            save_evidence(client, f"http-{version}-{'aliases' if aliases else 'rpc'}")
    assert client.child.proc.returncode == 0


@pytest.mark.parametrize("toolset", ["full", "core"])
@pytest.mark.parametrize("transcript", MODERN, ids=lambda row: row["name"])
def test_modern_2026_07_28_wire_transcript(tmp_path, transcript, inventory, toolset):
    uri = seed_library(tmp_path)
    with StdioClient.launch(tmp_path, toolset=toolset) as client:
        try:
            for exchange in transcript["exchanges"]:
                request = exchange["request"]
                client.send(request)
                result = client.wait_for(request["id"])["result"]
                method = request["method"]
                domain = modern_domain(result, cacheable=method in ("tools/list", "server/discover"))
                if method == "tools/list":
                    assert domain == {"tools": inventory[toolset]}
                elif method == "tools/call":
                    assert domain == GOLDEN["success"]
                else:
                    init = expected_initialize("stdio", "2025-11-25")
                    caps = dict(init["capabilities"])
                    caps.pop("experimental")
                    assert domain == {"supportedVersions": ["2026-07-28"],
                                      "capabilities": caps, "instructions": init["instructions"]}
            cases = [
                ("templates", "resources/templates/list", {}),
                ("prompts", "prompts/list", {}),
                ("resource", "resources/read", {"uri": uri}),
                ("prompt", "prompts/get", {"name": "consult-library", "arguments": {"topic": "absent-m2-topic"}}),
                ("invalid", "tools/call", {"name": "get_playbook_input", "arguments": {}}),
            ]
            for request_id, (label, method, params) in enumerate(cases, 10):
                result = client.request(request_id, method, modern_params(params))["result"]
                assert modern_domain(result, cacheable=method in (
                    "resources/templates/list", "resources/read", "prompts/list")) == GOLDEN[label]
            client.assert_quiet()
        finally:
            save_evidence(client, f"modern-{transcript['name']}-{toolset}")
    assert client.proc.returncode == 0


def modern_params(params=None, *, version="2026-07-28"):
    return dict(params or {}, _meta={
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientCapabilities": {}})


def modern_domain(result, *, cacheable=False):
    domain = dict(result)
    assert domain.pop("resultType") == "complete"
    assert domain.pop("_meta") == {"io.modelcontextprotocol/serverInfo": {
        "name": "uoink", "version": (ROOT / "VERSION").read_text().strip()}}
    if cacheable:
        assert domain.pop("ttlMs") == 0
        assert domain.pop("cacheScope") == "private"
    else:
        assert "ttlMs" not in domain and "cacheScope" not in domain
    return domain


@pytest.mark.parametrize("modern", [False, True])
def test_protocol_errors_preserve_connection(tmp_path, modern):
    uri = seed_library(tmp_path).replace("/bTItd2lyZQ/", "/bWlzc2luZw/")
    with StdioClient.launch(tmp_path) as client:
        if modern:
            # An unsupported opening version still selects the modern era.
            unsupported = client.request(1, "tools/list", modern_params(version="2099-01-01"))
            assert unsupported["error"]["code"] == -32022
            assert unsupported["error"]["data"] == {"requested": "2099-01-01", "supported": ["2026-07-28"]}
        else:
            assert client.initialize("2099-01-01")["result"] == expected_initialize("stdio", "2025-11-25")
        wrap = modern_params if modern else lambda params: params
        cases = [
            ("m3/unknown", {}, -32601),
            ("tools/call", {"name": "search_clips", "arguments": []}, -32602),
            ("tools/call", {"arguments": {}}, -32602),
            ("resources/read", {}, -32602),
        ]
        for request_id, (method, params, code) in enumerate(cases, 10):
            assert client.request(request_id, method, wrap(params))["error"]["code"] == code
            if modern:
                healthy = client.request(request_id + 100, "tools/list", wrap({}))["result"]
                assert modern_domain(healthy, cacheable=True)["tools"] == GOLDEN["tools"]
            else:
                assert client.request(request_id + 100, "ping")["result"] == {}
        missing = client.request(30, "resources/read", wrap({"uri": uri}))["error"]
        assert missing["code"] == (-32602 if modern else -32002)
        assert missing["data"]["error"]["code"] == "resource_not_found"
        if modern:
            assert missing["data"]["uri"] == uri
            malformed = [None, {}, {"_meta": {}}, {"_meta": []},
                         {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
                         {"_meta": {"io.modelcontextprotocol/protocolVersion": 1,
                                    "io.modelcontextprotocol/clientCapabilities": {}}},
                         {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                                    "io.modelcontextprotocol/clientCapabilities": []}}]
            for request_id, params in enumerate(malformed, 40):
                assert client.request(request_id, "tools/list", params)["error"]["code"] == -32602
            switched = client.request(50, "initialize", initialize_request("2025-11-25")["params"])
            assert switched["error"]["code"] == -32022
        else:
            assert client.request(50, "tools/list", modern_params())["error"]["code"] == -32600
        result = client.request(60, "tools/call", wrap({"name": "search_clips", "arguments": {"query": "absent-m2-topic"}}))["result"]
        assert (modern_domain(result) if modern else result) == GOLDEN["success"]
        client.assert_quiet()
        save_evidence(client, f"errors-{'modern' if modern else 'legacy'}")
    assert client.proc.returncode == 0
