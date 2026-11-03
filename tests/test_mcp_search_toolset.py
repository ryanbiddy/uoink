"""The opt-in 8-tool `search` toolset: registry, stdio, CLI and connect recipes."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

import openapi_bridge
import uoink_cli as cli
import uoink_connect as connect
import uoink_mcp_tools as tools
from tests.test_c01_mcp_stdio import ROOT, _StdioClient, _isolated_env

SEARCH = ("uoink_url", "search_library", "get_library_item", "read_library_resource",
          "search_clips", "get_citation_map", "list_recent_uoinks", "uoink_note")


def test_search_inventory_is_small_known_and_leaves_other_sets_alone():
    names = tools.stdio_tool_names("search")
    assert names == SEARCH == tools.SEARCH_STDIO_TOOLS
    assert len(set(names)) == 8 and set(names) <= tools.TOOL_REGISTRY.keys()
    # Read and cite tools are read-only; the two capture tools are the only writers.
    writers = {n for n in names if not tools.TOOL_REGISTRY[n].annotations["readOnlyHint"]}
    assert writers == {"uoink_url", "uoink_note"}
    # Adding a toolset must not reorder or shrink the frozen ones.
    assert tools.stdio_tool_names("core") == tools.CORE_STDIO_TOOLS
    assert len(tools.stdio_tool_names()) == len(tools.TOOL_REGISTRY) == 92
    assert tools.STDIO_TOOLSETS == cli.TOOLSETS == ("full", "core", "search")


def test_well_known_reports_the_search_count():
    doc = openapi_bridge.build_well_known("http://127.0.0.1:18150", version="x", tool_count=92)
    assert doc["stdio_toolsets"]["search"] == len(tools.SEARCH_STDIO_TOOLS)


def test_real_stdio_serves_only_search_tools(tmp_path):
    env = _isolated_env(str(tmp_path))
    env["UOINK_MCP_TOOLSET"] = "search"
    client = _StdioClient([sys.executable, str(ROOT / "uoink_mcp.py")], ROOT, env)
    try:
        client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "search-toolset", "version": "1"}}})
        client.wait_for(1)
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = client.wait_for(2)["result"]["tools"]
        assert tuple(t["name"] for t in listed) == SEARCH
        assert all(t["description"] == tools.TOOL_REGISTRY[t["name"]].description for t in listed)
        # A core tool outside the set is refused, not silently run.
        client.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "cancel_job", "arguments": {"job_id": "x"}}})
        result = client.wait_for(3)["result"]
        assert result["isError"] is True
        assert json.loads(result["content"][0]["text"])["error"] == "tool not found"
        assert not any("unknown UOINK_MCP_TOOLSET" in line for line in client.stderr_lines)
    finally:
        client.close()


def test_cli_lists_the_search_toolset(capsys):
    assert cli.main(["tools", "--toolset", "search"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert tuple(item["name"] for item in listed["tools"]) == SEARCH


def _entry(client, toolset):
    app, python = Path(ROOT), Path(sys.executable)
    return connect.server_entry(client, app, python, (), toolset)


def test_connect_defaults_are_unchanged():
    assert "UOINK_MCP_TOOLSET" not in _entry("claude-desktop", None)["env"]
    assert _entry("cursor", None)["env"]["UOINK_MCP_TOOLSET"] == "core"
    # Choosing full for Cursor drops the variable instead of writing the default.
    assert "UOINK_MCP_TOOLSET" not in _entry("cursor", "full")["env"]


@pytest.mark.parametrize("client", ["cursor", "claude-desktop", "codex", "vscode"])
def test_connect_toolset_flag_reaches_every_entry(client, capsys, monkeypatch):
    if sys.platform not in connect.CLIENTS[client].platforms:
        pytest.skip("no recipe on this platform")
    monkeypatch.setattr(connect, "python_command", lambda _: Path(sys.executable))
    assert cli.main(["connect", client, "--toolset", "search"]) == 0
    out = capsys.readouterr().out
    if connect.CLIENTS[client].format == "toml":
        assert 'UOINK_MCP_TOOLSET = "search"' in out
    else:
        data = json.loads(out)
        entry = next(iter(data.values()))["uoink"]
        assert entry["env"]["UOINK_MCP_TOOLSET"] == "search"
        assert entry["env"]["PYTHONUTF8"] == "1"


def test_claude_code_command_carries_the_toolset(capsys, monkeypatch):
    monkeypatch.setattr(connect, "python_command", lambda _: Path(sys.executable))
    assert cli.main(["connect", "claude-code"]) == 0
    default = capsys.readouterr().out
    assert "-e PYTHONIOENCODING=utf-8 -e PYTHONUTF8=1 --transport stdio uoink --" in default
    assert "UOINK_MCP_TOOLSET" not in default
    assert cli.main(["connect", "claude-code", "--toolset", "search"]) == 0
    assert "-e UOINK_MCP_TOOLSET=search --transport stdio" in capsys.readouterr().out


def test_cursor_deeplink_with_search_toolset(capsys, monkeypatch):
    monkeypatch.setattr(connect, "python_command", lambda _: Path(sys.executable))
    assert cli.main(["connect", "cursor", "--deeplink", "--toolset", "search"]) == 0
    query = parse_qs(urlsplit(capsys.readouterr().out.strip()).query)
    entry = json.loads(base64.b64decode(query["config"][0]).decode("utf-8"))
    assert entry["env"]["UOINK_MCP_TOOLSET"] == "search"


def test_connect_rejects_unknown_toolset(capsys):
    assert cli.main(["connect", "cursor", "--toolset", "tiny"]) == 2
