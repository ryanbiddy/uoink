"""tests/test_phase4_stdio.py - Living Library Stdio MCP & Compatibility Tests (AV-1a).

Gates covered:
- P4-06 (Capabilities: advertised methods, 5 templates, 9 prompts, curated <= 41, 92 tools,
  no promised notifications/subscriptions, JSON-RPC error codes -32602, -32002, -32603)
- P4-13 stdio part (Installed compatibility: python -P embeddable rules, spaced paths, clean stdout,
  diagnostic stderr separation, restart resilience, missing storage handling)

Tests against the frozen module interface in docs/library/PHASE4-AV-BRIEF-2026-09-08.md:
- library_resources.LibraryReader, parse_uri, encode_key, ResourceError
- library_prompts.get_prompt
"""
from __future__ import annotations

from tests.mcp_sdk import handler_for

import hashlib
import json
import os
import sys
import tempfile
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
import research_playbooks
from tests.test_research_playbooks import library as playbook_library  # noqa: F401 -- fixture

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

# Phase 6 run BC-2 (contract phase6-v1): one read-only cited export tool.
NEW_PHASE6_EXPORT_TOOLS = {"export_cited_range"}
# 32 on stdio after BC-2: 31 + the Phase 6 export tool.
TOTAL_BC2_TOOLS = TOTAL_AV2_TOOLS | NEW_PHASE6_EXPORT_TOOLS
TOTAL_PLAYBOOK_TOOLS = TOTAL_BC2_TOOLS | {"get_playbook_input", "discover_candidates", "queue_discovered"}


from tests.mcp_wire import StdioClient as _StdioTestClient, isolated_env


def _make_isolated_env(tmp_path: Path) -> dict[str, str]:
    return isolated_env(tmp_path)


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
        """prompts/list returns the 4 frozen prompts plus exactly 5 playbooks."""
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
            prompts = resp["result"]["prompts"]
            prompt_names = {p["name"] for p in prompts}
            assert len(prompts) == 9
            assert prompt_names == {p["name"] for p in (*PROMPTS, *research_playbooks.PLAYBOOKS)}
        finally:
            client.close()

    def test_stdio_tools_list_carries_full_registry(self, tmp_path: Path):
        """tools/list contains every registry tool, including the bounded reads."""
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
            # The 3 read tools, the 2 brief tools and the export tool must be registered
            assert NEW_PHASE4_READ_TOOLS.issubset(names)
            assert NEW_PHASE4_BRIEF_TOOLS.issubset(names)
            assert NEW_PHASE6_EXPORT_TOOLS.issubset(names)
            assert names == set(__import__("uoink_mcp_tools").TOOL_REGISTRY)
            assert len(names) == 92
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


def test_stdio_discovery_is_default_off_and_queue_requires_consent(tmp_path):
    client = _StdioTestClient([sys.executable, "-P", str(ROOT / "uoink_mcp.py")],
                              cwd=tmp_path, env=_make_isolated_env(tmp_path))
    try:
        client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "discovery-offline-test", "version": "1"}}})
        assert "result" in client.wait_for(1)
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        cases = [
            ("discover_candidates", {"mode": "creator", "platform": "youtube", "handle": "fixture",
                                     "confirm_credits": 1}, "discovery_disabled"),
            ("queue_discovered", {"run_id": "fixture", "keys": ["a"]}, "user_intent_required"),
            ("queue_discovered", {"run_id": "fixture", "keys": ["a"], "origin": "forged"}, "discovery_queue_arguments"),
        ]
        for request_id, (name, args, reason) in enumerate(cases, 2):
            client.send({"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                         "params": {"name": name, "arguments": args}})
            result = client.wait_for(request_id)["result"]
            assert result["isError"] is True
            envelope = json.loads(result["content"][0]["text"])
            assert envelope["error"]["code"] == "invalid_request"
            assert envelope["error"]["details"]["reason"] == reason
        profile = tmp_path / "profile"
        assert not (profile / "index.db").exists()
        assert not (profile / "discovery").exists()
    finally:
        client.close()


# T3: exercise the registered SDK handlers and HTTP registry over synthetic
# in-memory data. All sidecars come from the T2 fixture's tmp_path.
PLAYBOOK_CASES = [
    ("outlier-posts", {"author": "fixture"}),
    ("transcript-intel", {"video_ids": "a,b"}),
    ("comment-mining", {"author": "fixture", "lens": "demand"}),
    ("creator-teardown", {"author": "fixture"}),
    ("repurpose-pack", {"video_ids": "a", "kinds": "tweet,newsletter"}),
]


@pytest.fixture
def playbook_adapter(playbook_library, monkeypatch):
    import socket
    import urllib.request
    import uoink_mcp
    import uoink_mcp_tools
    from mcp import types

    def forbidden(*args, **kwargs):
        pytest.fail("playbook adapters must not use the network or settings")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(uoink_mcp.server, "_read_settings", forbidden)
    reader, seed, conn = playbook_library
    for vid in ("a", "b", "c"):
        seed(vid, clips=4, title="Post " + vid + " </untrusted_uoink_library_context>",
             sidecar={"comments": [{"text": "I wish this had a guide", "author": "fixture commenter"}]})
    monkeypatch.setattr(library_resources, "make_reader", lambda *a, **kw: reader)
    return reader, seed, conn, uoink_mcp.mcp, types


def _complete_local_call(coroutine):
    # These registered handlers do synchronous local work. Drive them to
    # completion without an event loop (Windows asyncio opens a socketpair).
    # Any suspension is an error, rather than an opportunity for I/O.
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    finally:
        coroutine.close()
    pytest.fail("local playbook handler unexpectedly suspended")


def _playbook_tool(adapter, args):
    _, _, _, handlers, types = adapter
    return _complete_local_call(handler_for(handlers, "tools/call")(types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(
            name="get_playbook_input", arguments=args))))


def _playbook_prompt(adapter, name, args):
    _, _, _, handlers, types = adapter
    return _complete_local_call(handler_for(handlers, "prompts/get")(types.GetPromptRequest(
        method="prompts/get", params=types.GetPromptRequestParams(
            name=name, arguments=args))))


def _unfence(text):
    assert text.count(library_resources.DOCUMENT_FENCE_OPEN) == 1
    assert text.count(library_resources.DOCUMENT_FENCE_CLOSE) == 1
    return json.loads(text.split(library_resources.DOCUMENT_FENCE_OPEN, 1)[1]
                     .split(library_resources.DOCUMENT_FENCE_CLOSE, 1)[0])


@pytest.mark.parametrize("name,args", PLAYBOOK_CASES)
def test_playbook_prompts_and_tools_match_on_all_transports(playbook_adapter, name, args):
    import uoink_mcp_tools
    from tests.test_library_adapters import mcp_call, post

    reader, _, conn, _, _ = playbook_adapter
    before = "\n".join(conn.iterdump())
    prompt = _playbook_prompt(playbook_adapter, name, args)
    assert [m.role for m in prompt.messages] == ["user", "user"]
    instruction, data = [m.content.text for m in prompt.messages]
    packet = _unfence(data)
    assert packet["prompt"] == name
    assert packet["contract_version"] == "playbooks-v1-2026-10-15"
    assert "Do not call capture" in instruction
    assert "Post a" not in instruction
    payload = {"playbook": name, "arguments": args}
    registry = uoink_mcp_tools.call_tool("get_playbook_input", payload)
    assert registry == {"ok": True, "playbook": name, "instruction": instruction,
                        "packet": packet, "packet_hash": packet["packet_hash"]}
    raw = json.dumps({"items": packet["items"], "refs": packet["refs"]},
                     ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert registry["packet_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    tool = _playbook_tool(playbook_adapter, payload)
    assert tool.is_error is False
    assert _unfence(tool.content[0].text) == registry
    http = mcp_call("get_playbook_input", payload)
    assert http.status == 200
    assert http.payload["result"]["isError"] is False
    assert json.loads(http.payload["result"]["content"][0]["text"]) == registry
    assert http.payload["result"]["structuredContent"] == registry
    direct = post("/tools/get_playbook_input", payload)
    assert direct.status == 200 and direct.payload == {"ok": True, "result": registry}
    assert "\n".join(conn.iterdump()) == before
    assert reader.guard._active == 0
    assert len(tool.model_dump_json().encode()) + 256 <= LIMITS["max_response_bytes"]


def test_playbook_wire_schema_hints_and_prompt_arguments(tmp_path):
    import uoink_mcp_tools
    from tests.test_c01_mcp_stdio import _assert_tool_metadata

    with _StdioTestClient.launch(tmp_path) as client:
        client.initialize()
        listed = client.request(2, "tools/list")["result"]["tools"]
        prompts = client.request(3, "prompts/list")["result"]["prompts"]
    assert len(listed) == 92
    assert len(uoink_mcp_tools.TOOL_REGISTRY) == 92
    _assert_tool_metadata(listed)
    tool = next(t for t in listed if t["name"] == "get_playbook_input")
    spec = uoink_mcp_tools.TOOL_REGISTRY[tool["name"]]
    assert tool["inputSchema"] == uoink_mcp_tools.client_input_schema(spec.input_schema, spec.name)
    assert tool["description"] == spec.description
    assert tool["inputSchema"]["required"] == ["playbook", "arguments"]
    assert tool["inputSchema"]["additionalProperties"] is False
    assert set(tool["inputSchema"]["properties"]["playbook"]["enum"]) == {p[0] for p in PLAYBOOK_CASES}
    assert tool["inputSchema"]["properties"]["arguments"]["type"] == "object"
    assert spec.annotations == {"readOnlyHint": True, "destructiveHint": False,
                                "idempotentHint": True, "openWorldHint": False}
    assert spec.rate_limiter is None
    assert len(PROMPTS) == 4
    assert len(prompts) == 9
    expected = [*PROMPTS, *research_playbooks.PLAYBOOKS]
    assert prompts == expected


@pytest.mark.parametrize("args", [
    {}, {"playbook": "outlier-posts"},
    {"playbook": "outlier-posts", "arguments": None},
    {"playbook": "outlier-posts", "arguments": []},
    {"playbook": "unknown", "arguments": {}},
    {"playbook": ["outlier-posts"], "arguments": {}},
    {"playbook": "outlier-posts", "arguments": {"author": ""}},
    {"playbook": "outlier-posts", "arguments": {"author": "fixture", "private-argument": "private-value"}},
    {"playbook": "outlier-posts", "arguments": {"author": "fixture"}, "private-argument": "private-value"},
    {"playbook": "transcript-intel", "arguments": {"video_ids": "a,b", "topic": "Quote"}},
    {"playbook": "comment-mining", "arguments": {"author": "fixture", "lens": "unknown"}},
    {"playbook": "repurpose-pack", "arguments": {"video_ids": "a,b,c,d,e,f"}},
])
def test_playbook_invalid_arguments_refuse_before_data_access(playbook_adapter, monkeypatch, args):
    import uoink_mcp_tools
    from tests.test_library_adapters import mcp_call

    def forbidden():
        pytest.fail("invalid playbook arguments reached storage")
    monkeypatch.setattr(playbook_adapter[0], "request", forbidden)
    expected = uoink_mcp_tools.call_tool("get_playbook_input", args)
    assert expected["ok"] is False
    assert expected["error"]["code"] == "invalid_request"
    assert expected["contract_version"] == CONTRACT_VERSION
    assert "private-" not in json.dumps(expected)
    tool = _playbook_tool(playbook_adapter, args)
    assert tool.is_error is True and json.loads(tool.content[0].text) == expected
    assert mcp_call("get_playbook_input", args).payload["result"]["structuredContent"] == expected


@pytest.mark.parametrize("args", [None, [], False, "not an object"])
def test_playbook_registry_rejects_non_object_arguments(playbook_adapter, args):
    import uoink_mcp_tools
    result = uoink_mcp_tools.call_tool("get_playbook_input", args)
    assert result["ok"] is False and result["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("name,args", PLAYBOOK_CASES)
def test_playbook_prompt_refusals_keep_domain_envelope(playbook_adapter, name, args):
    from mcp.shared.exceptions import MCPError
    with pytest.raises(MCPError) as exc:
        _playbook_prompt(playbook_adapter, name, {**args, "private-argument": "private-value"})
    assert exc.value.error.code == -32602
    assert exc.value.error.data["error"]["code"] == "invalid_request"
    assert "private-" not in json.dumps(exc.value.error.data)


@pytest.mark.parametrize("name,kind", [
    ("outlier-posts", "exception"), ("outlier-posts", "serialization"),
    ("transcript-intel", "exception"),
])
def test_playbook_unexpected_errors_are_sanitized_on_all_transports(playbook_adapter, monkeypatch, name, kind):
    import uoink_mcp_tools
    from mcp.shared.exceptions import MCPError
    from tests.test_library_adapters import mcp_call

    if kind == "exception":
        def fail(*args, **kwargs):
            raise ValueError("private source text must not escape")
        monkeypatch.setattr(research_playbooks, "_refresh", fail)
    else:
        refresh = research_playbooks._refresh

        def invalid_packet(body):
            # Corrupt the packet after numeric sanitization so strict JSON
            # serialization still raises even when metric baselines are safe.
            body["items"][0]["private source text must not escape"] = float("inf")
            return refresh(body)

        monkeypatch.setattr(research_playbooks, "_refresh", invalid_packet)
    payload = {"playbook": name, "arguments": {"author": "fixture"}}
    expected = ResourceError("internal_error").envelope()
    assert uoink_mcp_tools.call_tool("get_playbook_input", payload) == expected
    tool = _playbook_tool(playbook_adapter, payload)
    assert tool.is_error is True and json.loads(tool.content[0].text) == expected
    assert mcp_call("get_playbook_input", payload).payload["result"]["structuredContent"] == expected
    with pytest.raises(MCPError) as exc:
        _playbook_prompt(playbook_adapter, name, {"author": "fixture"})
    assert exc.value.error.code == -32603
    assert exc.value.error.data == expected


def test_playbook_tool_keeps_read_admission_through_sdk_dump(playbook_adapter, monkeypatch):
    import uoink_mcp

    reader, _, _, _, types = playbook_adapter
    monkeypatch.setattr(library_resources, "process_guard", lambda: reader.guard)
    request_id = "playbook-budget-test"
    request = types.JSONRPCRequest(
        jsonrpc="2.0", id=request_id, method="tools/call",
        params={"name": "get_playbook_input", "arguments": {
            "playbook": "outlier-posts", "arguments": {"author": "fixture"}}})
    uoink_mcp._begin_inbound_transport_scope(request)
    scope = library_resources.transport_scope(request_id)
    token = library_resources.bind_transport_scope(request_id)
    try:
        assert scope.owns_slot and reader.guard._active == 1
        result = _playbook_tool(playbook_adapter, request.params["arguments"])
        assert result.is_error is False
        assert reader.guard._active == 1
        from mcp.shared.message import SessionMessage
        frames = []

        class Sink:
            async def send(self, frame):
                frames.append(frame)

        _complete_local_call(uoink_mcp._SdkSettlementStream(Sink()).send(SessionMessage(
            types.JSONRPCResponse(jsonrpc="2.0", id=request_id,
                                  result=result.model_dump(by_alias=True, mode="json", exclude_none=True)))))
        message = frames[0].message
        scope.deadline_at = time.monotonic() - 1
        wire = json.loads(message.model_dump_json(by_alias=True, exclude_none=True))
        assert wire["result"]["isError"] is True
        assert json.loads(wire["result"]["content"][0]["text"])["error"]["code"] == "deadline_exceeded"
        assert library_resources.transport_scope(request_id) is None
        assert reader.guard._active == 0
    finally:
        library_resources.reset_bound_transport_scope(token)
        library_resources.finish_transport_request(request_id)


@pytest.mark.parametrize("refusal", ["rate_limited", "deadline_exceeded"])
@pytest.mark.parametrize("name", ["outlier-posts", "transcript-intel"])
def test_playbook_tool_uses_existing_reader_limits(playbook_adapter, refusal, name):
    import uoink_mcp_tools
    reader = playbook_adapter[0]
    reader.guard = library_resources.ReadGuard(max_active=1, admissions_per_minute=60)
    if refusal == "rate_limited":
        reader.guard.admit()
    else:
        reader.deadline_s = -1
    try:
        result = uoink_mcp_tools.call_tool("get_playbook_input", {
            "playbook": name, "arguments": {"author": "fixture"}})
        assert result["ok"] is False and result["error"]["code"] == refusal
    finally:
        if refusal == "rate_limited":
            reader.guard.release()
    assert reader.guard._active == 0


def test_playbook_tool_refuses_oversize_wrapped_response(playbook_adapter, monkeypatch):
    import uoink_mcp_tools
    monkeypatch.setattr(research_playbooks, "get_playbook_input", lambda *a, **kw: {
        "ok": True, "instruction": "x" * LIMITS["max_response_bytes"], "packet": {}})
    args = {"playbook": "outlier-posts", "arguments": {"author": "fixture"}}
    result = uoink_mcp_tools.call_tool("get_playbook_input", args)
    assert result["ok"] is False
    assert result["error"]["code"] == "resource_too_large"
    tool = _playbook_tool(playbook_adapter, args)
    assert tool.is_error is True
    assert json.loads(tool.content[0].text) == result


@pytest.mark.parametrize("deleted", [False, True])
def test_playbook_missing_or_deleted_capture_refuses(playbook_adapter, deleted):
    import uoink_mcp_tools
    if deleted:
        playbook_adapter[1]("absent", deleted=True)
    result = uoink_mcp_tools.call_tool("get_playbook_input", {
        "playbook": "transcript-intel", "arguments": {"video_ids": "absent"}})
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_request"
    assert result["error"]["details"]["reason"] == "unknown_or_deleted_video_ids"


@pytest.mark.parametrize("chapter_field", ["chapters", "source_chapters"])
@pytest.mark.parametrize("title", ["A long chapter title " * 10, "<>&`" * 50, "\U0001f600" * 200],
                         ids=["long", "escaped", "unicode"])
def test_playbook_large_transcript_chapters_shrink_before_exposure(playbook_adapter, chapter_field, title):
    import uoink_mcp_tools
    from tests.test_library_adapters import mcp_call

    seed = playbook_adapter[1]
    for number in range(8):
        seed("chapter-" + str(number), clips=8, sidecar={chapter_field: [
            {"title": title, "start": n * 10, "end": n * 10 + 10}
            for n in range(100)]})
    args = {"video_ids": ",".join("chapter-" + str(n) for n in range(8))}
    payload = {"playbook": "transcript-intel", "arguments": args}
    tool = _playbook_tool(playbook_adapter, payload)
    assert tool.is_error is False
    result = _unfence(tool.content[0].text)
    packet = result["packet"]
    coverage = packet["coverage"]
    assert coverage["dropped_for_budget"] > 0
    assert coverage["included"] == 8
    assert 0 < sum(len(item["chapters"]) for item in packet["items"]) < 800
    assert coverage["budget_drops"]["chapters"] == 800 - sum(len(i["chapters"]) for i in packet["items"])
    assert all(len(item["chapters"]) <= 12 for item in packet["items"])
    assert all(library_resources.wire_bytes(library_resources.render_document({"chapters": item["chapters"]}))
               <= 2048 for item in packet["items"])
    # The core deduplicates the opening clip from its six spread clips,
    # then includes the last: these equal-length fixtures select seven.
    assert all([clip["seq"] for clip in item["clips"]] == [0, 1, 2, 4, 5, 6, 7]
               for item in packet["items"])
    assert sum(coverage["budget_drops"].values()) == coverage["dropped_for_budget"]
    canonical = json.dumps({"items": packet["items"], "refs": packet["refs"]},
                           ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert result["packet_hash"] == packet["packet_hash"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert len(tool.model_dump_json().encode()) + 256 <= LIMITS["max_response_bytes"]
    assert uoink_mcp_tools.call_tool("get_playbook_input", payload) == result
    http = mcp_call("get_playbook_input", payload)
    assert http.status == 200 and http.payload["result"]["isError"] is False
    assert http.payload["result"]["structuredContent"] == result
    prompt = _playbook_prompt(playbook_adapter, "transcript-intel", args)
    assert _unfence(prompt.messages[1].content.text) == packet
    assert len(prompt.model_dump_json().encode()) + 256 <= LIMITS["max_response_bytes"]


@pytest.mark.parametrize("args", [{"video_ids": "a,b"}, {"author": "fixture"}, {"topic": "Quote"}])
def test_playbook_small_transcript_packet_matches_unchanged_core(playbook_adapter, args):
    import uoink_mcp_tools

    reader, seed, _, _, _ = playbook_adapter
    seed("a", sidecar={"source_chapters": [
        {"title": "Opening <chapter>", "start_time": 0, "end_time": 30},
        {"title": "Next chapter", "start_time": 30, "end_time": 90},
    ]})
    seed("b", sidecar={"chapters": [
        {"title": "Legacy chapter", "start": 0, "end": 30},
    ]})
    expected = research_playbooks.get_playbook_input(reader, "transcript-intel", args)
    assert expected["packet"]["coverage"]["included"] > 0
    assert expected["packet"]["coverage"]["dropped_for_budget"] == 0
    assert uoink_mcp_tools.call_tool("get_playbook_input", {
        "playbook": "transcript-intel", "arguments": args}) == expected
    assert _unfence(_playbook_prompt(playbook_adapter, "transcript-intel", args)
                   .messages[1].content.text) == expected["packet"]


def test_playbook_transcript_error_and_safety_checks_precede_chapter_trimming(playbook_adapter):
    import uoink_mcp_tools
    from mcp.shared.exceptions import MCPError
    from tests.test_library_adapters import mcp_call

    reader, seed, _, _, _ = playbook_adapter
    # This unsafe path sits past the adapter's chapter count limit. Trimming
    # must not bypass the core's check of the original selected source fields.
    seed("a", sidecar={"chapters": [{"title": "Chapter"}] * 12 + [
        {"title": str(reader.data_root / "private-file.txt")}]})
    args = {"video_ids": "a"}
    with pytest.raises(ResourceError) as core_error:
        research_playbooks.get_playbook_input(reader, "transcript-intel", args)
    expected = core_error.value.envelope()
    payload = {"playbook": "transcript-intel", "arguments": args}
    assert uoink_mcp_tools.call_tool("get_playbook_input", payload) == expected
    tool = _playbook_tool(playbook_adapter, payload)
    assert tool.is_error is True and json.loads(tool.content[0].text) == expected
    assert mcp_call("get_playbook_input", payload).payload["result"]["structuredContent"] == expected
    with pytest.raises(MCPError) as prompt_error:
        _playbook_prompt(playbook_adapter, "transcript-intel", args)
    assert prompt_error.value.error.data == expected
    assert reader.guard._active == 0


def test_playbook_chapter_count_cap_reports_all_omissions(playbook_adapter):
    import uoink_mcp_tools

    playbook_adapter[1]("a", sidecar={"chapters": [
        {"title": "Chapter", "start": number, "end": number + 1}
        for number in range(150)]})
    result = uoink_mcp_tools.call_tool("get_playbook_input", {
        "playbook": "transcript-intel", "arguments": {"video_ids": "a"}})
    assert result["ok"] is True
    packet = result["packet"]
    assert len(packet["items"][0]["chapters"]) == 12
    assert packet["coverage"]["budget_drops"] == {"chapters": 138}
    assert packet["coverage"]["dropped_for_budget"] == 138
