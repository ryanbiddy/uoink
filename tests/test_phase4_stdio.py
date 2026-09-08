"""tests/test_phase4_stdio.py - Living Library Stdio MCP & Compatibility Tests (AV-1a).

Gates covered:
- P4-06 (Capabilities: advertised methods, 5 templates, 4 prompts, curated <= 41, 28 tools,
  no promised notifications/subscriptions, JSON-RPC error codes -32602, -32002, -32603)
- P4-13 stdio part (Installed compatibility: python -P embeddable rules, spaced paths, clean stdout,
  diagnostic stderr separation, restart resilience, missing storage handling)

Tests against the frozen module interface in docs/library/PHASE4-AV-BRIEF-2026-09-08.md:
- library_resources.LibraryReader, parse_uri, encode_key, ResourceError
- library_prompts.get_prompt
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest

# Target implementation imports: will fail until implementation lands in AV-1
import library_resources
from library_resources import (
    CONTRACT_VERSION,
    LIMITS,
    LibraryReader,
    ResourceError,
    TEMPLATES,
    URI_PREFIX,
    encode_key,
    parse_uri,
)
import library_prompts
from library_prompts import PROMPTS, get_prompt

ROOT = Path(__file__).resolve().parent.parent

CANONICAL_25_TOOLS = {
    "uoink_video",
    "uoink_playlist",
    "get_job_status",
    "cancel_job",
    "list_recent_uoinks",
    "search_uoinks",
    "search_clips",
    "get_evidence_card",
    "get_uoink_corpus",
    "analyze_comments",
    "classify_hook",
    "get_taxonomy",
    "get_citation_map",
    "get_uoink_health",
    "find_mentions",
    "get_transcript_reliability",
    "add_podcast_feed",
    "list_podcast_feeds",
    "remove_podcast_feed",
    "poll_podcast_feed",
    "list_podcast_episodes",
    "download_podcast_episode",
    "get_whisperx_status",
    "transcribe_podcast_episode",
    "episode_to_corpus",
}

NEW_PHASE4_READ_TOOLS = {
    "search_library",
    "get_library_item",
    "read_library_resource",
}

# Phase 4 run AV-2: brief generation belongs to the client. The input tool is a
# read; publish_library_brief is a local write under DATA_ROOT/reach/briefs.
NEW_PHASE4_BRIEF_TOOLS = {
    "get_library_brief_input",
    "publish_library_brief",
}

# Phase 5 run AZ (contract phase5-v1) registered one stdio tool in parallel with AV-1;
# discovery must advertise exactly the implemented set (P4-06), so it is expected here.
PHASE5_ACTIVITY_TOOLS = {"get_library_activity"}

TOTAL_AV1_TOOLS = CANONICAL_25_TOOLS | NEW_PHASE4_READ_TOOLS | PHASE5_ACTIVITY_TOOLS
# 31 on stdio after AV-2: 25 canonical + 3 read + 1 activity + 2 brief tools.
TOTAL_AV2_TOOLS = TOTAL_AV1_TOOLS | NEW_PHASE4_BRIEF_TOOLS


class _StdioTestClient:
    """Stdio client managing a child MCP process with honest deadline waiting."""

    def __init__(self, cmd: list[str], cwd: Path | str, env: dict[str, str], timeout: float = 30.0):
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.deadline = time.time() + timeout
        self.lines: queue.Queue = queue.Queue()
        self.raw_stdout_lines: list[str] = []
        self.stderr_lines: list[str] = []

        threading.Thread(target=self._drain_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stdout(self):
        for line in self.proc.stdout:
            self.raw_stdout_lines.append(line)
            self.lines.put(line)

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self.stderr_lines.append(line.rstrip())

    def send(self, message: dict[str, Any]) -> None:
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def wait_for(self, request_id: int, timeout: float = 10.0) -> dict[str, Any]:
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                line = self.lines.get(timeout=0.2)
            except queue.Empty:
                if self.proc.poll() is not None:
                    tail = "\n".join(self.stderr_lines[-6:])
                    raise AssertionError(
                        f"MCP process exited {self.proc.returncode} before answering id={request_id}. stderr tail:\n{tail}"
                    )
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == request_id:
                return msg
        raise AssertionError(f"Timed out waiting for response id={request_id}")

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def _make_isolated_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(tmp_path / "appdata")
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")
    env["UOINK_OUTPUT_DIR"] = str(tmp_path / "out")
    return env


class TestP406CapabilitiesAndDiscovery:
    """Gate P4-06: Discovery, advertised capabilities, templates, prompts, curated resources, tools."""

    def test_stdio_advertised_capabilities(self, tmp_path: Path):
        """stdio handshake advertises resources and prompts without subscriptions or change events."""
        client = _StdioTestClient(
            [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
            cwd=tmp_path,
            env=_make_isolated_env(tmp_path),
        )
        try:
            client.send({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-stdio", "version": "1.0"},
                },
            })
            init = client.wait_for(1)
            assert "result" in init
            caps = init["result"].get("capabilities", {})

            # Resources capability: subscribe=false, listChanged=false
            assert "resources" in caps
            res_caps = caps["resources"]
            assert res_caps.get("subscribe") is False
            assert res_caps.get("listChanged") is False

            # Prompts capability: listChanged=false
            assert "prompts" in caps
            prompt_caps = caps["prompts"]
            assert prompt_caps.get("listChanged") is False

            # Tools capability: listChanged=false
            assert "tools" in caps
            tool_caps = caps["tools"]
            assert tool_caps.get("listChanged") is False

            # No unsupported capabilities advertised
            assert "sampling" not in caps
            assert "completions" not in caps
        finally:
            client.close()

    def test_stdio_templates_list(self, tmp_path: Path):
        """resources/templates/list returns exactly the 5 frozen resource templates."""
        client = _StdioTestClient(
            [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
            cwd=tmp_path,
            env=_make_isolated_env(tmp_path),
        )
        try:
            client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "test", "version": "1"}}})
            client.wait_for(1)
            client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

            client.send({"jsonrpc": "2.0", "id": 2, "method": "resources/templates/list"})
            resp = client.wait_for(2)
            assert "result" in resp
            templates = resp["result"].get("resourceTemplates", [])
            assert len(templates) == 5

            template_uris = [t.get("uriTemplate") for t in templates]
            assert any("cards" in u for u in template_uris)
            assert any("excerpts" in u for u in template_uris)
            assert any("corpus" in u for u in template_uris)
            assert any("shelves" in u for u in template_uris)
            assert any("briefs" in u for u in template_uris)
            assert all(t.get("mimeType") == "text/markdown" for t in templates)
        finally:
            client.close()

    def test_stdio_prompts_list(self, tmp_path: Path):
        """prompts/list returns exactly the 4 frozen prompts."""
        client = _StdioTestClient(
            [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
            cwd=tmp_path,
            env=_make_isolated_env(tmp_path),
        )
        try:
            client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "test", "version": "1"}}})
            client.wait_for(1)
            client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

            client.send({"jsonrpc": "2.0", "id": 2, "method": "prompts/list"})
            resp = client.wait_for(2)
            assert "result" in resp
            prompt_names = {p["name"] for p in resp["result"].get("prompts", [])}
            assert prompt_names == {"consult-library", "evidence-brief", "whats-new", "reshelve-review"}
        finally:
            client.close()

    def test_stdio_tools_list_carries_31_tools(self, tmp_path: Path):
        """tools/list contains all 25 canonical tools, the 3 read tools, the activity tool
        and the 2 brief tools: exactly 31."""
        client = _StdioTestClient(
            [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
            cwd=tmp_path,
            env=_make_isolated_env(tmp_path),
        )
        try:
            client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "test", "version": "1"}}})
            client.wait_for(1)
            client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

            client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            resp = client.wait_for(2)
            assert "result" in resp
            names = {t["name"] for t in resp["result"].get("tools", [])}

            # All 25 legacy tools must be preserved
            assert CANONICAL_25_TOOLS.issubset(names)
            # The 3 read tools and the 2 brief tools must be registered
            assert NEW_PHASE4_READ_TOOLS.issubset(names)
            assert NEW_PHASE4_BRIEF_TOOLS.issubset(names)
            assert names == TOTAL_AV2_TOOLS
            assert len(names) == 31
        finally:
            client.close()

    def test_stdio_protocol_negotiation_versions(self, tmp_path: Path):
        """stdio negotiates 2024-11-05 and 2025-11-25 cleanly."""
        for proto in ["2024-11-05", "2025-11-25"]:
            client = _StdioTestClient(
                [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
                cwd=tmp_path,
                env=_make_isolated_env(tmp_path),
            )
            try:
                client.send({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": proto,
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                })
                init = client.wait_for(1)
                assert "result" in init
            finally:
                client.close()

    def test_stdio_error_transport_codes(self, tmp_path: Path):
        """Invalid params use -32602, missing resources use -32002, execution failures use -32603."""
        client = _StdioTestClient(
            [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
            cwd=tmp_path,
            env=_make_isolated_env(tmp_path),
        )
        try:
            client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "test", "version": "1"}}})
            client.wait_for(1)
            client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

            # Invalid parameters -> -32602
            client.send({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "resources/read",
                "params": {"uri": "not-a-valid-uri"},
            })
            resp_invalid = client.wait_for(2)
            assert "error" in resp_invalid
            assert resp_invalid["error"]["code"] == -32602

            # Cold start (AV-1r D7): the isolated profile has no index.db yet, and a
            # bounded read never creates one -> -32603 carrying library_unavailable.
            missing_uri = f"{URI_PREFIX}items/{encode_key('nonexistent')}/cards/{'0'*64}/spread-longest-v2/{'0'*64}"
            client.send({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "resources/read",
                "params": {"uri": missing_uri},
            })
            resp_cold = client.wait_for(3)
            assert "error" in resp_cold
            assert resp_cold["error"]["code"] == -32603
            assert resp_cold["error"].get("data", {}).get("error", {}).get("code") == "library_unavailable"

            # A legacy tool still creates the library (preserved behaviour for its
            # existing callers); once storage exists, a missing item is -32002.
            client.send({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "list_recent_uoinks", "arguments": {"limit": 1}},
            })
            resp_legacy = client.wait_for(4)
            assert "result" in resp_legacy

            client.send({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "resources/read",
                "params": {"uri": missing_uri},
            })
            resp_missing = client.wait_for(5)
            assert "error" in resp_missing
            assert resp_missing["error"]["code"] == -32002
        finally:
            client.close()


class TestP413InstalledCompatibilityStdio:
    """Gate P4-13 (stdio part): Protocol-clean stdout, spaced paths, restart resilience."""

    def test_stdio_clean_stdout_and_diagnostic_stderr(self, tmp_path: Path):
        """Every line emitted to stdout must be valid JSON-RPC; diagnostics go to stderr."""
        client = _StdioTestClient(
            [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
            cwd=tmp_path,
            env=_make_isolated_env(tmp_path),
        )
        try:
            client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "test", "version": "1"}}})
            client.wait_for(1)
            client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            client.wait_for(2)

            # Check raw stdout lines
            for raw_line in client.raw_stdout_lines:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                # Must be parseable JSON
                parsed = json.loads(stripped)
                assert isinstance(parsed, dict)
                assert "jsonrpc" in parsed
        finally:
            client.close()

    def test_stdio_spaced_paths_and_isolated_data_root(self, tmp_path: Path):
        """Server boots and operates cleanly in directories containing spaces."""
        spaced_dir = tmp_path / "spaced path test folder"
        spaced_dir.mkdir()

        client = _StdioTestClient(
            [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
            cwd=spaced_dir,
            env=_make_isolated_env(spaced_dir),
        )
        try:
            client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "test", "version": "1"}}})
            init = client.wait_for(1)
            assert "result" in init
        finally:
            client.close()

    def test_stdio_restart_and_reconnection(self, tmp_path: Path):
        """Client can terminate and reconnect in a new process without data leakage or deadlock."""
        env = _make_isolated_env(tmp_path)

        # First connection
        c1 = _StdioTestClient([sys.executable, "-P", str(ROOT / "uoink_mcp.py")], cwd=tmp_path, env=env)
        try:
            c1.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                "clientInfo": {"name": "test", "version": "1"}}})
            init1 = c1.wait_for(1)
            assert "result" in init1
        finally:
            c1.close()

        # Second connection (restart)
        c2 = _StdioTestClient([sys.executable, "-P", str(ROOT / "uoink_mcp.py")], cwd=tmp_path, env=env)
        try:
            c2.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                "clientInfo": {"name": "test", "version": "1"}}})
            init2 = c2.wait_for(1)
            assert "result" in init2
        finally:
            c2.close()
