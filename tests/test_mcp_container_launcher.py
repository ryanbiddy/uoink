"""The container launcher serves a fresh, empty library to directory inspectors.

Glama builds the image, starts scripts/run_mcp_container.py over stdio and lists
tools and resources. Bounded reads never create index.db (AV-1r D7), so before
the launcher created an empty library, resources/list on a fresh container
failed with -32603 library_unavailable (storage FileNotFoundError).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.mcp_wire import StdioClient, isolated_env

ROOT = Path(__file__).resolve().parents[1]


def test_fresh_container_lists_and_searches_empty_library(tmp_path: Path):
    env = isolated_env(tmp_path, port=18102)
    env["UOINK_CONTAINER_ROOT"] = str(tmp_path)
    client = StdioClient([sys.executable, "-B", str(ROOT / "scripts/run_mcp_container.py")],
                         cwd=tmp_path, env=env, timeout=60)
    try:
        client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                                "clientInfo": {"name": "container-inspector", "version": "1"}}})
        assert "result" in client.wait_for(1)
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert client.wait_for(2)["result"]["tools"]

        client.send({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        listed = client.wait_for(3)
        assert "error" not in listed, listed
        assert listed["result"]["resources"] == []

        client.send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "search_library", "arguments": {"query": "anything"}}})
        searched = client.wait_for(4)
        assert "error" not in searched and searched["result"]["isError"] is False, searched
        assert "library_unavailable" not in json.dumps(searched)
    finally:
        client.close()
    assert (tmp_path / "profile").is_dir()
    assert list(tmp_path.rglob("index.db"))
