"""Run E (2026-09-04): `search_clips` and `get_evidence_card` on stdio.

Transport parity: the two Phase 1 clip tools are now registered on the stdio
surface (23 -> 25), delegate to the same `uoink_mcp_tools` handlers the
HTTP/OpenAPI registry uses, accept the same parameter names, and every
lock-step inventory (docs, MCPB manifest, C-01 canonical set) agrees.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import index
import uoink_mcp
import uoink_mcp_tools as tools
from tests.test_c01_mcp_stdio import CANONICAL_STDIO_TOOLS

ROOT = Path(__file__).resolve().parents[1]
CLIP_TOOLS = {"search_clips", "get_evidence_card"}


def _stdio_tools() -> dict[str, object]:
    return {t.name: t for t in asyncio.run(uoink_mcp.mcp.list_tools())}


def test_clip_tools_are_on_stdio_and_the_count_is_32():
    stdio = _stdio_tools()
    assert CLIP_TOOLS.issubset(stdio)
    # 25 + three Phase 4 read tools + one Phase 5 activity tool + two Phase 4
    # brief tools + one Phase 6 cited export tool (run BC-2)
    assert len(stdio) == 32
    assert set(stdio) == CANONICAL_STDIO_TOOLS


def test_stdio_and_http_agree_on_parameter_names():
    stdio = _stdio_tools()
    for name in CLIP_TOOLS:
        http_props = set(tools.TOOL_REGISTRY[name].input_schema["properties"])
        stdio_props = set(stdio[name].inputSchema["properties"])
        assert stdio_props == http_props, name
    assert stdio["search_clips"].inputSchema["required"] == ["query"]
    assert "required" not in stdio["get_evidence_card"].inputSchema or \
        stdio["get_evidence_card"].inputSchema["required"] == []


def test_stdio_wrappers_delegate_to_the_shared_handlers(monkeypatch):
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(tools, "call_tool",
                        lambda name, args: calls.append((name, dict(args))) or {"ok": True})
    assert uoink_mcp.search_clips("harbor signal") == {"ok": True}
    assert uoink_mcp.search_clips("harbor signal", limit=5, video_id="v1", channel="c") == {"ok": True}
    assert uoink_mcp.get_evidence_card(slug="s") == {"ok": True}
    assert uoink_mcp.get_evidence_card(video_id="v1", profile="librarian", n_clips=3) == {"ok": True}
    assert calls == [
        ("search_clips", {"query": "harbor signal", "limit": 20}),
        ("search_clips", {"query": "harbor signal", "limit": 5, "video_id": "v1", "channel": "c"}),
        ("get_evidence_card", {"profile": "full", "slug": "s"}),
        ("get_evidence_card", {"profile": "librarian", "video_id": "v1", "n_clips": 3}),
    ]


def test_both_transports_return_the_same_shape_on_a_fixture(monkeypatch, tmp_path):
    idx = index.Index.open(tmp_path / "index.db")
    try:
        idx.upsert_yoink({
            "video_id": "vid-parity", "slug": "vid-parity", "title": "Parity",
            "channel": "Chan", "topic": "Topic", "hook_type": None,
            "yoinked_at": "2026-09-04T12:00:00",
            "corpus_path": str(tmp_path / "parity.md"),
            "sidecar_path": str(tmp_path / "parity.json"),
            "metadata_json": json.dumps({"url": "https://www.youtube.com/watch?v=vid-parity"}),
            "platform": "youtube", "source_type": "video",
        })
        idx.insert_citations("vid-parity", [{
            "kind": "transcript_chunk", "seq": 0,
            "timestamp_start": 12.0, "timestamp_end": 40.0,
            "text": "harbor signal explained in one sentence",
            "source_deep_link": "https://www.youtube.com/watch?v=vid-parity#t=12",
        }])
        idx.rebuild_clips()

        class FakeBackend:
            def _get_index(self):
                return idx

        monkeypatch.setattr(tools, "_b", lambda: FakeBackend())

        via_stdio = uoink_mcp.search_clips("harbor signal")
        via_http = tools.call_tool("search_clips", {"query": "harbor signal", "limit": 20})
        assert via_stdio == via_http
        assert via_stdio["ok"] is True and via_stdio["results"][0]["video_id"] == "vid-parity"

        card_stdio = uoink_mcp.get_evidence_card(video_id="vid-parity", profile="librarian")
        card_http = tools.call_tool("get_evidence_card",
                                    {"video_id": "vid-parity", "profile": "librarian"})
        assert card_stdio == card_http
        assert card_stdio["profile"] == "librarian"
        assert card_stdio["evidence_kind"] == "timed_clip"

        assert uoink_mcp.get_evidence_card() == {"ok": False, "error": "slug or video_id required"}
    finally:
        idx.close()


def test_lock_step_inventories_agree():
    src = (ROOT / "uoink_mcp.py").read_text(encoding="utf-8")
    decorators = len(re.findall(r"^\s*@mcp\.tool\b", src, re.M))
    doc = (ROOT / "docs" / "v2-mcp.md").read_text(encoding="utf-8")
    headings = re.findall(r"^### ([a-z][a-z_]+)$", doc, re.M)
    assert decorators == len(headings) == 32
    assert set(headings) == CANONICAL_STDIO_TOOLS
    assert "(HTTP/OpenAPI only)" not in doc
    manifest = json.loads((ROOT / ".mcpb" / "manifest.json").read_text(encoding="utf-8"))
    assert {t["name"] for t in manifest["tools"]} == CANONICAL_STDIO_TOOLS
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for text in (readme, changelog):
        counts = [int(m.group(1)) for m in
                  re.finditer(r"MCP server[^\n]*?\b(\d+)\s+tools\b", text, re.I)]
        # The first match is the current statement (README body, newest changelog
        # entry); older changelog entries keep their historical counts.
        assert counts and counts[0] == 32, counts
