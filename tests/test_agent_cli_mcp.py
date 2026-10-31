"""`uoink mcp` serves uoink_mcp.py's stdio server, with stdout kept for JSON-RPC.

Every child runs on a disposable isolated profile. The launcher test runs the
real PATH launchers from a fake install: cli\\uoink.cmd through `cmd /c` on
Windows, cli/uoink and the Mac Contents/Helpers/uoink elsewhere.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

import uoink_cli as cli
import uoink_mcp_tools as registry
from tests.mcp_wire import StdioClient, isolated_env

ROOT = Path(__file__).resolve().parents[1]
SUBCOMMAND = [sys.executable, "-B", "-P", str(ROOT / "uoink_cli.py"), "mcp"]


def test_help_documents_the_portable_command(capsys, monkeypatch):
    monkeypatch.setattr(cli, "serve_mcp", lambda: pytest.fail("help must not start the server"))
    with pytest.raises(SystemExit) as exited:
        cli.main(["mcp", "--help"])
    assert exited.value.code == 0
    text = capsys.readouterr().out
    assert '"command": "uoink", "args": ["mcp"]' in text and "UOINK_MCP_TOOLSET=core" in text
    assert '"command": "cmd", "args": ["/c", "uoink", "mcp"]' in text
    # The toolset stays the server's env var; the session has no text mode.
    for args in (["mcp", "extra"], ["mcp", "--toolset", "core"], ["mcp", "--text"]):
        assert cli.main(args) == 2
        output = capsys.readouterr()
        assert output.out == "" and output.err.startswith("uoink:")


@pytest.mark.parametrize("toolset", ["full", "core"])
def test_subcommand_serves_the_script_server(tmp_path, toolset):
    results = []
    for name, command in (("script", [sys.executable, "-B", "-P", str(ROOT / "uoink_mcp.py")]),
                          ("subcommand", SUBCOMMAND)):
        directory = tmp_path / name
        directory.mkdir()
        with StdioClient(command, directory, isolated_env(directory, toolset=toolset)) as client:
            results.append((client.initialize()["result"], client.request(2, "tools/list")["result"]))
    assert results[1] == results[0]
    assert tuple(tool["name"] for tool in results[1][1]["tools"]) == registry.stdio_tool_names(toolset)


def test_stdout_carries_only_json_rpc(tmp_path):
    # An unknown toolset warns before the session starts, and the tool call
    # runs backend code. Both must reach stderr, never the transport.
    with StdioClient(SUBCOMMAND, tmp_path, isolated_env(tmp_path, toolset="unknown")) as client:
        client.initialize()
        assert len(client.request(2, "tools/list")["result"]["tools"]) == len(registry.TOOL_REGISTRY)
        call = client.request(3, "tools/call", {"name": "list_recent_uoinks", "arguments": {"limit": 3}})
        assert json.loads(call["result"]["content"][0]["text"])["ok"] is True
        client.assert_quiet()
    assert client.proc.returncode == 0, client.stderr_lines[-6:]
    messages = [json.loads(line) for line in client.raw_stdout_lines]
    assert all(isinstance(m, dict) and m.get("jsonrpc") == "2.0" for m in messages)
    assert [m["id"] for m in messages if "id" in m] == [1, 2, 3] and messages[0]["id"] == 1
    assert any("unknown UOINK_MCP_TOOLSET" in line for line in client.stderr_lines)


LAUNCHERS = ([("cli/uoink.cmd", "Uoink/cli/uoink.cmd")] if os.name == "nt" else
             [("cli/uoink", "Uoink/cli/uoink"), ("installer/mac/cli.sh", "Uoink.app/Contents/Helpers/uoink")])


@pytest.mark.parametrize("source, installed", LAUNCHERS)
def test_subcommand_through_path_launcher(tmp_path, source, installed):
    launcher = tmp_path / installed
    mac = "Contents" in launcher.parts
    app = launcher.parents[1] / "Resources" if mac else launcher.parents[1]
    launcher.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / source, launcher)
    app.mkdir(exist_ok=True)
    # The installed CLI is this checkout's, run with the test interpreter's imports.
    (app / "uoink_cli.py").write_text(
        f"import runpy, sys\nsys.path[:0] = {[p for p in sys.path if p]!r}\n"
        f"runpy.run_path({str(ROOT / 'uoink_cli.py')!r}, run_name='__main__')\n", encoding="utf-8")
    bin_dir = launcher.parent
    junction = None
    if os.name == "nt":
        # Bundled python\python.exe: a junction to the base interpreter's folder.
        junction = app / "python"
        base = Path(getattr(sys, "_base_executable", sys.executable)).parent
        made = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(junction), str(base)],
                              capture_output=True, text=True)
        if made.returncode:
            pytest.skip("cannot create a directory junction: " + made.stdout + made.stderr)
        command = ["cmd", "/c", "uoink", "mcp"]
    else:
        python = app / ("Python/bin/python3" if mac else "python/bin/python3")
        python.parent.mkdir(parents=True)
        python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8")
        python.chmod(0o755)
        launcher.chmod(0o755)
        if mac:
            # Homebrew's binary stanza and the Mac guide both link the shim onto PATH.
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            (bin_dir / "uoink").symlink_to(launcher)
        command = ["uoink", "mcp"]
    env = isolated_env(tmp_path / "data")
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    try:
        with StdioClient(command, tmp_path, env) as client:
            assert client.initialize()["result"]["serverInfo"]["name"] == "uoink"
            tools = client.request(2, "tools/list")["result"]["tools"]
            assert tuple(tool["name"] for tool in tools) == registry.stdio_tool_names("full")
        assert client.proc.returncode == 0, client.stderr_lines[-6:]
    finally:
        if junction is not None:
            os.rmdir(junction)  # Removes only the junction, never the interpreter.
