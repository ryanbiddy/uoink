"""C-01 (CRIT-1) -- the stdio MCP entry point boots and speaks the protocol.

Run: python tests/test_c01_mcp_stdio.py  (also collected by pytest tests/)

The installer bundles the embeddable Windows Python, whose ._pth locks
sys.path to the interpreter's directory and never adds the script's folder.
`python.exe uoink_mcp.py` therefore died on `ModuleNotFoundError: No module
named 'server'` on every install that ever existed (Claude Desktop: 22
crashes, 0 successes), while dev and CI interpreters silently added the
script dir and masked the bug.

This test re-creates the embeddable condition on any interpreter with
`python -P` (PYTHONSAFEPATH: script dir withheld from sys.path) and drives
the full client handshake over stdio:

    initialize -> notifications/initialized -> tools/list -> tools/call

Red on unpatched main: the subprocess exits 1 with the ModuleNotFoundError
before answering initialize. Green with the sys.path pin in uoink_mcp.py.

The subprocess gets an isolated data root (LOCALAPPDATA / XDG_DATA_HOME /
UOINK_OUTPUT_DIR pointed at a temp dir) so the check never touches a real
install's index or writes to the desktop.

Requires the `mcp` SDK (a runtime dependency of the entry point; CI's
stdlib-tests job installs it). Skips loudly if it's missing so a local run
without the SDK doesn't report false confidence.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import mcp  # noqa: F401
    HAVE_MCP_SDK = True
except ImportError:
    HAVE_MCP_SDK = False


CANONICAL_STDIO_TOOLS = {
    "uoink_video",
    "uoink_playlist",
    "get_job_status",
    "cancel_job",
    "list_recent_uoinks",
    "search_uoinks",
    "search_clips",          # run E (2026-09-04): Phase 1 clip tools on stdio
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
    "get_library_activity",
    # Phase 4 run AV-1 (contract phase4-v1-2026-09-08): bounded library reads.
    "search_library",
    "get_library_item",
    "read_library_resource",
    # Phase 4 run AV-2: client-run daily briefs (input is a read; publish is a local write).
    "get_library_brief_input",
    "publish_library_brief",
    # Phase 6 run BC-2 (contract phase6-v1): read-only cited range export.
    "export_cited_range",
}

REMOVED_STDIO_ALIASES = {
    "yoink_video",
    "yoink_playlist",
    "list_recent_yoinks",
    "search_yoinks",
    "get_yoink_corpus",
    "get_yoink_health",
}


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _skip(reason):
    print(f"SKIP: {reason}")
    if os.environ.get("PYTEST_CURRENT_TEST"):
        import pytest
        pytest.skip(reason)


class _StdioClient:
    """Minimal MCP stdio client: one request in flight, honest timeouts."""

    def __init__(self, cmd, cwd, env, timeout=120):
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8")
        self.deadline = time.time() + timeout
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(
            target=lambda: [self.lines.put(l) for l in self.proc.stdout],
            daemon=True).start()
        self.stderr_lines: list[str] = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self.stderr_lines.append(line.rstrip())

    def send(self, message):
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def wait_for(self, request_id):
        while time.time() < self.deadline:
            try:
                line = self.lines.get(timeout=0.5)
            except queue.Empty:
                if self.proc.poll() is not None:
                    tail = "\n".join(self.stderr_lines[-6:])
                    raise AssertionError(
                        f"MCP process exited {self.proc.returncode} before "
                        f"answering id={request_id}. stderr tail:\n{tail}")
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == request_id:
                return message
        raise AssertionError(f"timed out waiting for response id={request_id}")

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=15)
        except Exception:
            self.proc.kill()


def _isolated_env(tmp):
    env = dict(os.environ)
    # The parent pytest invocation needs the worktree on PYTHONPATH. The
    # embeddable-path regression must not let that rescue the child import.
    env.pop("PYTHONPATH", None)
    env["LOCALAPPDATA"] = tmp                      # Windows data root
    env["XDG_DATA_HOME"] = os.path.join(tmp, "xdg")  # Linux/mac data root
    env["UOINK_OUTPUT_DIR"] = os.path.join(tmp, "out")
    return env


def _assert_tool_metadata(tools):
    """Check the real wire response, including low-level list overrides."""
    import uoink_mcp_tools

    hints = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
    registry = {tool["name"]: tool for tool in uoink_mcp_tools.list_tools()}
    documented = {}
    for line in (ROOT / "docs" / "mcp-tool-annotations.md").read_text(
            encoding="utf-8").splitlines():
        if line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            documented[cells[0].strip("`")] = (
                cells[1], dict(zip(hints, (v == "true" for v in cells[2:6]))))
    _assert(set(documented) == CANONICAL_STDIO_TOOLS,
            "annotation table must cover every stdio tool")
    _assert(len(tools) == len(CANONICAL_STDIO_TOOLS),
            "tools/list must not duplicate tools")
    for tool in tools:
        name = tool["name"]
        _assert(isinstance(tool.get("title"), str) and tool["title"].strip(),
                f"{name}: missing human title")
        annotations = tool.get("annotations") or {}
        for hint in hints:
            _assert(type(annotations.get(hint)) is bool,
                    f"{name}: {hint} must be explicitly set")
        expected_title, expected_hints = documented[name]
        _assert(tool["title"] == expected_title, f"{name}: title differs from audit")
        _assert({key: annotations[key] for key in hints} == expected_hints,
                f"{name}: wire hints differ from audit: {annotations}")
        _assert(registry[name]["title"] == tool["title"],
                f"{name}: HTTP title differs from stdio")
        _assert(registry[name]["annotations"] == expected_hints,
                f"{name}: HTTP hints differ from stdio")
    print(f"ok  {len(tools)} live stdio titles and all four hints match HTTP and audit")


def test_stdio_handshake_under_embeddable_path_rules():
    if not HAVE_MCP_SDK:
        return _skip("mcp SDK not installed; pip install mcp to run the "
                     "C-01 regression check")
    with tempfile.TemporaryDirectory() as tmp:
        # -P == PYTHONSAFEPATH: withhold the script dir from sys.path, the
        # exact condition the bundled embeddable interpreter creates.
        client = _StdioClient(
            [sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
            cwd=tmp,  # NOT the repo dir: cwd must not rescue the import
            env=_isolated_env(tmp))
        try:
            client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05",
                                    "capabilities": {},
                                    "clientInfo": {"name": "c01-gate",
                                                   "version": "0"}}})
            init = client.wait_for(1)
            _assert("result" in init, f"initialize failed: {init}")
            _assert(init["result"]["serverInfo"]["name"] == "uoink",
                    f"server identity: {init['result'].get('serverInfo')}")
            product_version = (ROOT / "VERSION").read_text(
                encoding="utf-8").strip()
            _assert(init["result"]["serverInfo"]["version"] == product_version,
                    "initialize must report the Uoink product version, not "
                    f"the MCP SDK version: {init['result'].get('serverInfo')}")
            print("ok  initialize answers under -P (embeddable path rules)")

            client.send({"jsonrpc": "2.0",
                         "method": "notifications/initialized"})
            client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            tools = client.wait_for(2)
            names = [t["name"] for t in tools["result"]["tools"]]
            _assert(set(names) == CANONICAL_STDIO_TOOLS,
                    "stdio tool surface drift: "
                    f"missing={sorted(CANONICAL_STDIO_TOOLS - set(names))}, "
                    f"extra={sorted(set(names) - CANONICAL_STDIO_TOOLS)}")
            _assert(not REMOVED_STDIO_ALIASES.intersection(names),
                    f"removed aliases returned by tools/list: {names}")
            _assert_tool_metadata(tools["result"]["tools"])
            print(f"ok  tools/list returns exactly {len(names)} canonical tools")

            client.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "list_recent_uoinks",
                                    "arguments": {"limit": 3}}})
            call = client.wait_for(3)
            _assert("result" in call and not call["result"].get("isError"),
                    f"tools/call failed: {call}")
            body = json.loads(call["result"]["content"][0]["text"])
            _assert(body.get("ok") is True and body.get("yoinks") == [],
                    f"fresh isolated index must answer empty: {body}")
            print("ok  tools/call round-trips against the isolated index")
        finally:
            client.close()


def test_doctor_carries_the_selfcheck():
    """The gate's second half: doctor can never report green while the
    stdio path is dead. Static wiring check (running the full doctor spawns
    the subprocess again; the live path is covered above)."""
    server_src = (ROOT / "server.py").read_text(encoding="utf-8")
    _assert("def _mcp_stdio_selfcheck" in server_src,
            "doctor self-check function missing")
    _assert('"mcp_stdio": _mcp_stdio_selfcheck()' in server_src,
            "doctor_payload must include the mcp_stdio check")
    _assert('"-P"' in server_src.split("def _mcp_stdio_selfcheck", 1)[1][:2000],
            "self-check must recreate the embeddable condition with -P")
    print("ok  doctor payload carries mcp_stdio")


def test_entry_point_pins_the_app_dir():
    src = (ROOT / "uoink_mcp.py").read_text(encoding="utf-8")
    _assert("sys.path.insert(0, _APP_DIR)" in src,
            "uoink_mcp.py must pin its own folder onto sys.path (CRIT-1)")
    _assert(src.index("sys.path.insert") < src.index("import server"),
            "the pin must land before the server import")
    print("ok  entry point pins the app dir before importing server")


def test_removed_aliases_are_rejected_and_manifest_matches():
    import uoink_mcp_tools

    for name in REMOVED_STDIO_ALIASES:
        result = uoink_mcp_tools.call_tool(name, {})
        _assert(result == {"ok": False, "error": "tool not found"},
                f"removed alias still resolves: {name} -> {result}")

    manifest = json.loads(
        (ROOT / ".mcpb" / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_names = {tool["name"] for tool in manifest["tools"]}
    _assert(manifest_names == CANONICAL_STDIO_TOOLS,
            "MCPB manifest tool inventory drift: "
            f"missing={sorted(CANONICAL_STDIO_TOOLS - manifest_names)}, "
            f"extra={sorted(manifest_names - CANONICAL_STDIO_TOOLS)}")
    _assert(manifest["privacy_policies"] == ["https://uoink.app/privacy"],
            "MCPB must publish the privacy-policy link")
    # MCPB 0.4 uses a strict name/description tool schema: a title here would
    # invalidate the bundle. Live MCP titles are verified over stdio above.
    _assert(manifest["manifest_version"] == "0.4", "review the tool schema on upgrade")
    _assert(all(set(tool) == {"name", "description"} for tool in manifest["tools"]),
            "MCPB 0.4 tool entries must use only name and description")
    print(f"ok  removed aliases reject and MCPB lists the same {len(manifest_names)} tools")


def main():
    test_entry_point_pins_the_app_dir()
    test_doctor_carries_the_selfcheck()
    test_removed_aliases_are_rejected_and_manifest_matches()
    test_stdio_handshake_under_embeddable_path_rules()
    print("\nall green")


if __name__ == "__main__":
    main()
