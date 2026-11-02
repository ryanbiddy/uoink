"""Fresh-process parser, descriptor, self-check and EOF evidence for M4."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from tests.mcp_wire import ROOT, StdioClient, isolated_env, initialize_request, rpc
from tests.test_mcp_wire import modern_params, save_evidence


def open_era(client, modern):
    if modern:
        assert "result" in client.request(1, "server/discover", modern_params())
    else:
        assert "result" in client.initialize()


@pytest.mark.parametrize("modern", [False, True])
def test_parser_recovers_and_eof_settles_without_polluted_stdout(tmp_path, modern):
    with StdioClient.launch(tmp_path) as client:
        open_era(client, modern)
        bad = [('', -32700, "Invalid JSON-RPC message"), ('{', -32700, "Invalid JSON-RPC message"),
               ('{"jsonrpc":"2.0","id":2,"id":3,"method":"ping"}', -32700, "Invalid JSON-RPC message"),
               *[(json.dumps({"jsonrpc": "2.0", "id": ident, "method": "ping"}),
                  -32600, "Invalid request ID") for ident in (None, True, 1.5, [], {})],
               ('[]', -32600, "Empty JSON-RPC batch"),
               ('[1]', -32600, "Expected a JSON-RPC object"),
               ('{"jsonrpc":"1.0","id":2,"method":"ping"}', -32600, "Invalid JSON-RPC envelope"),
               ('{"a":NaN}', -32700, "Invalid JSON-RPC message")]
        for line, code, message in bad:
            client.send_raw(line)
            reply = client.receive()
            assert reply.get("id") is None and reply["error"]["code"] == code
            assert reply["error"]["message"] == message
            assert len(client.transcript[-1]["line"].encode()) < 65536
        for ident in (None, True, [], {}, 1.5):
            client.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": ident}})
        for name in (None, [], {}, True):
            params = {"name": name, "arguments": {}}
            reply = client.request(98, "tools/call", modern_params(params) if modern else params)
            assert reply["error"]["code"] == -32602
        assert "result" in client.request(99, "tools/list", modern_params() if modern else {})
        client.assert_quiet()
        save_evidence(client, f"m4-parser-{'modern' if modern else 'legacy'}")
    assert client.proc.returncode == 0


@pytest.mark.parametrize("modern", [False, True])
def test_client_responses_are_silent_before_and_after_opening(tmp_path, modern):
    with StdioClient.launch(tmp_path) as client:
        for opened in (False, True):
            if opened:
                open_era(client, modern)
            for ident in (None, 1, "client-response"):
                for body in ({"result": {}}, {"error": {"code": -32600, "message": "client error"}},
                             {"result": {"padding": "x" * 65536}},
                             {"error": {"code": -32600, "message": "x" * 65536}}):
                    client.send({"jsonrpc": "2.0", "id": ident, **body})
        reply = client.request(99, "tools/list", modern_params() if modern else {})
        assert "result" in reply
        client.assert_quiet()
    assert client.proc.returncode == 0


def test_initialize_with_modern_metadata_selects_legacy(tmp_path):
    with StdioClient.launch(tmp_path) as client:
        request = initialize_request("2025-11-25")
        request["params"] = modern_params(request["params"])
        client.send(request)
        result = client.receive()["result"]
        assert result["protocolVersion"] == "2025-11-25"
        assert "resultType" not in result
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        listing = client.request(2, "tools/list")["result"]
        assert len(listing["tools"]) == 92 and "resultType" not in listing
        assert client.request(3, "tools/list", modern_params())["error"]["code"] == -32600
        assert client.request(4, "ping")["result"] == {}
        client.assert_quiet()
    assert client.proc.returncode == 0


def test_empty_process_input_exits_cleanly(tmp_path):
    with StdioClient.launch(tmp_path) as client:
        client.proc.stdin.close()
        assert client.proc.wait(10) == 0
    assert client.raw_stdout_lines == []


@pytest.mark.parametrize("modern", [False, True])
def test_python_native_and_child_output_miss_protocol_pipe(tmp_path, modern):
    command = [sys.executable, "-B", str(ROOT / "tests/mcp_sdk2_child.py"), "noise"]
    with StdioClient(command, tmp_path, isolated_env(tmp_path)) as client:
        open_era(client, modern)
        params = {"name": "get_library_item", "arguments": {}}
        response = client.request(2, "tools/call", modern_params(params) if modern else params)
        assert json.loads(response["result"]["content"][0]["text"]) == {"ok": True}
        client.assert_quiet()
        save_evidence(client, f"m4-output-{'modern' if modern else 'legacy'}")
    assert client.proc.returncode == 0
    diagnostics = "\n".join(client.stderr_lines)
    for text in ("M4 Python output", "M4 native CRT output", "M4 child output"):
        assert text in diagnostics
    if os.name == "nt":
        assert "M4 Win32 output" in diagnostics
    assert '{"m4_active": 0, "m4_scopes": 0}' in diagnostics
    assert '{"m4_releases": 1}' in diagnostics


@pytest.mark.parametrize("modern", [False, True])
def test_broken_pipe_exits_while_peer_keeps_stdin_open(tmp_path, modern):
    env = isolated_env(tmp_path)
    command = [sys.executable, "-B", str(ROOT / "tests/mcp_sdk2_child.py"), "broken"]
    proc = subprocess.Popen(command, cwd=tmp_path, env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    errors = []
    drainer = threading.Thread(target=lambda: errors.append(proc.stderr.read()), daemon=True)
    drainer.start()
    try:
        proc.stdout.close()
        opening = rpc(1, "server/discover", modern_params()) if modern else initialize_request("2025-11-25")
        proc.stdin.write((json.dumps(opening) + "\n").encode())
        proc.stdin.flush()
        try:
            proc.wait(timeout=12)  # Do not close stdin to rescue a blocked reader.
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
            drainer.join(2)
            pytest.fail(b"".join(errors).decode("utf-8", errors="replace"))
        assert proc.returncode != 0
        drainer.join(2)
        assert b'"m4_active": 0, "m4_scopes": 0' in b"".join(errors)
        assert b'"m4_releases": 0' in b"".join(errors)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(5)
        proc.stdin.close()
        proc.stderr.close()


@pytest.mark.parametrize("modern", [False, True])
def test_cancel_arriving_during_sql_wait_is_silent(tmp_path, modern):
    env = isolated_env(tmp_path)
    profile = Path(env["UOINK_ISOLATED_PROFILE"])
    command = [sys.executable, "-B", str(ROOT / "tests/mcp_sdk2_child.py"), "sql"]
    with StdioClient(command, tmp_path, env) as client:
        open_era(client, modern)
        params = {"name": "get_library_item", "arguments": {}}
        client.send(rpc(2, "tools/call", modern_params(params) if modern else params))
        deadline = time.monotonic() + 5
        while not (profile / "sql-wait").exists():
            assert time.monotonic() < deadline, client.stderr_lines
            time.sleep(0.005)
        client.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 2}})
        # The event loop is doing synchronous SQL; the notification waits at
        # input until that bounded work yields. It must beat prepared output.
        time.sleep(0.05)
        (profile / "release-sql").write_text("release", encoding="utf-8")
        client.send(rpc(3, "tools/list", modern_params() if modern else {}))
        assert client.receive()["id"] == 3
        client.assert_quiet()
        save_evidence(client, f"m4-sql-cancel-{'modern' if modern else 'legacy'}")
    assert client.proc.returncode == 0
    assert '{"m4_active": 0, "m4_scopes": 0}' in client.stderr_lines
    assert '{"m4_releases": 1}' in client.stderr_lines


@pytest.mark.parametrize("modern", [False, True])
def test_installed_selfcheck_reports_actual_protocol(tmp_path, modern):
    env = isolated_env(tmp_path)
    env["TEMP"] = env["TMP"] = str(tmp_path)
    name = "_mcp_modern_stdio_selfcheck" if modern else "_mcp_stdio_selfcheck"
    script = f"import json,server; print(json.dumps(server.{name}(timeout=15)))"
    child = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert child.returncode == 0, child.stderr
    evidence = json.loads(child.stdout)
    assert evidence["ok"] and evidence["tools"] == 92, evidence
    assert evidence["protocol_era"] == ("modern" if modern else "legacy")
    assert evidence["protocol_version"] == ("2026-07-28" if modern else "2024-11-05")
    assert evidence["opening_method"] == ("server/discover" if modern else "initialize")
    assert evidence["expected_serializer"] == "JSONRPCResponse.model_dump_json"
    assert evidence["expected_transport"] == "bounded_stdio_server"
    assert "serializer" not in evidence and "transport" not in evidence
    assert evidence["evidence"] == "JSON-RPC self-check"
    destination = os.environ.get("M2_WIRE_EVIDENCE")
    if destination:
        path = Path(destination) / f"m4-selfcheck-{'modern' if modern else 'legacy'}.json"
        assert path.resolve().is_relative_to(ROOT / "_scratch")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
