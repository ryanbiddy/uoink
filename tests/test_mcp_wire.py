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
        if schema != tools.TOOL_REGISTRY[tool["name"]].input_schema:
            changed.add(tool["name"])
    assert changed == {"claim_library_work", "apply_reshelving", "set_source_consent"}
    return {"full": full, "core": core}


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
            # SDK 1 reports unknown typed methods as invalid params on stdio.
            assert client.request(9, "m2/unknown") == {
                "jsonrpc": "2.0", "id": 9, "error": GOLDEN["unknown_stdio"]}
            assert client.request(10, "ping") == {"jsonrpc": "2.0", "id": 10, "result": {}}
            client.assert_quiet()
        finally:
            save_evidence(client, f"legacy-{version}-{toolset}")
    assert client.proc.returncode == 0


BAD_LINES = {
    "malformed": "{",
    "duplicate_keys": '{"jsonrpc":"2.0","id":2,"method":"ping","method":"tools/list"}',
    "null_id": '{"jsonrpc":"2.0","id":null,"method":"ping"}',
    "oversized": '{"jsonrpc":"2.0","id":2,"method":"ping","params":{"padding":"' + "x" * 65536 + '"}}',
}


@pytest.mark.parametrize("version", LEGACY_VERSIONS)
@pytest.mark.parametrize("case", BAD_LINES)
def test_sdk1_stdio_invalid_line_golden_and_connection_survives(tmp_path, version, case):
    # These are observations, not desired SDK 2 error semantics. In SDK 1,
    # malformed/duplicate JSON produces a log notification, while null id is
    # parsed as a notification and ignored. M3 must review any change here.
    with StdioClient.launch(tmp_path) as client:
        try:
            assert "result" in client.initialize(version)
            client.send_raw(BAD_LINES[case])
            if case in ("malformed", "duplicate_keys"):
                assert client.receive() == GOLDEN["parser_notification"]
            elif case == "oversized":
                refusal = client.receive()
                assert refusal == GOLDEN["oversized"]
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
                "jsonrpc": "2.0", "id": 2, "result": {"tools": inventory["full"]}})
            call = rpc(3, "tools/call", {"name": "search_clips", "arguments": {"query": "absent-m2-topic"}})
            expected = dict(GOLDEN["success"], structuredContent={"ok": True, "results": []})
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


@pytest.mark.xfail(run=False, strict=True, reason="SDK 1 has no dual-era runner; enabled by M3")
@pytest.mark.parametrize("transcript", MODERN, ids=lambda row: row["name"])
def test_modern_2026_07_28_wire_transcript(tmp_path, transcript, inventory):
    # Pending test data only. Not executed or counted as acceptance in M2.
    with StdioClient.launch(tmp_path) as client:
        for exchange in transcript["exchanges"]:
            client.send(exchange["request"])
            reply = client.wait_for(exchange["request"]["id"])
            assert "result" in reply
            result = reply["result"]
            assert result["resultType"] == "complete"
            assert result["ttlMs"] == 0 and result["cacheScope"] == "private"
            if exchange["request"]["method"] == "tools/list":
                assert result["tools"] == inventory["full"]
