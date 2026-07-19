"""Uoink MCP stdio entry point.

Run with:

    python uoink_mcp.py

MCP clients launch this process and speak JSON-RPC over stdin/stdout. Keep
stdout reserved for the protocol; server.py logging is redirected to stderr
while importing the backend.

The stdio surface is exactly the 14 canonical tools below. The six Yoink-era
aliases completed their deprecation window in Uoink v2.5 and are not
registered in v3. See docs/v2-mcp.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

# CRIT-1 (C-01): the installer bundles the embeddable Windows Python, whose
# ._pth locks sys.path to the interpreter's own directory and never adds the
# script's folder. Every MCP client launch therefore died on
# `ModuleNotFoundError: No module named 'server'` before this line existed
# (Claude Desktop: 22 crashes, 0 successes). Pin the app dir (this file's
# folder) onto sys.path before importing anything that lives beside us.
# tests/test_c01_mcp_stdio.py re-creates the embeddable condition with
# `python -P` and drives the full initialize->tools/list->tools/call
# handshake; `--doctor` runs the same self-check on the installed copy.
_APP_DIR = str(Path(__file__).resolve().parent)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)


try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "Uoink MCP requires the official MCP Python SDK. "
        "Install with: python -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)


# server.py configures a stdout log handler at import time. MCP stdio uses
# stdout as the JSON-RPC transport, so bind that log handler to stderr instead.
_stdout = sys.stdout
try:
    sys.stdout = sys.stderr
    import server  # noqa: E402
finally:
    sys.stdout = _stdout

import uoink_mcp_tools  # noqa: E402


uoink_mcp_tools.bind_backend(server)

mcp = FastMCP(
    "uoink",
    instructions=(
        "Uoink turns YouTube videos and playlists into local AI-ready corpora. "
        "Use the tools to extract, search, inspect, and analyze saved uoinks."
    ),
)


# --------------------------------------------------------------------------
# Canonical tools (14). The CI doc-accuracy + backend-static jobs count these
# @mcp.tool decorators against the ### headings in docs/v2-mcp.md, so keep the
# decorator count and the documented tool count in lock-step.
# --------------------------------------------------------------------------
@mcp.tool(
    name="uoink_video",
    description="Extract a single YouTube video into a Uoink corpus.",
)
def uoink_video(url: str, interval: int = 30) -> dict:
    return uoink_mcp_tools.call_tool("uoink_video", {"url": url, "interval": interval})


@mcp.tool(
    name="uoink_playlist",
    description="Start asynchronous extraction for a YouTube playlist.",
)
def uoink_playlist(url: str, interval: int = 30) -> dict:
    return uoink_mcp_tools.call_tool("uoink_playlist", {"url": url, "interval": interval})


@mcp.tool(
    name="get_job_status",
    description="Return the full status object for an async Uoink job.",
)
def get_job_status(job_id: str) -> dict:
    return uoink_mcp_tools.call_tool("get_job_status", {"job_id": job_id})


@mcp.tool(
    name="cancel_job",
    description="Cancel an async Uoink job and leave partial outputs on disk.",
)
def cancel_job(job_id: str) -> dict:
    return uoink_mcp_tools.call_tool("cancel_job", {"job_id": job_id})


@mcp.tool(name="list_recent_uoinks", description="List recent saved Uoink corpora.")
def list_recent_uoinks(limit: int = 20) -> dict:
    return uoink_mcp_tools.call_tool("list_recent_uoinks", {"limit": limit})


@mcp.tool(
    name="search_uoinks",
    description="Keyword search across saved Uoink markdown corpora.",
)
def search_uoinks(query: str, limit: int = 10) -> dict:
    return uoink_mcp_tools.call_tool("search_uoinks", {"query": query, "limit": limit})


@mcp.tool(
    name="get_uoink_corpus",
    description="Return the full markdown corpus for a saved uoink by slug.",
)
def get_uoink_corpus(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("get_uoink_corpus", {"slug": slug})


@mcp.tool(
    name="analyze_comments",
    description=(
        "Run Comment Intelligence on an existing uoink using the configured "
        "Anthropic key."
    ),
)
def analyze_comments(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("analyze_comments", {"slug": slug})


@mcp.tool(
    name="classify_hook",
    description="Classify the hook type for an existing uoink.",
)
def classify_hook(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("classify_hook", {"slug": slug})


@mcp.tool(
    name="get_taxonomy",
    description=(
        "Return captured Hook Type taxonomy rows, optionally "
        "filtered by channel and hook_type."
    ),
)
def get_taxonomy(
    channel: str | None = None,
    hook_type: str | None = None,
    limit: int = 50,
) -> dict:
    return uoink_mcp_tools.call_tool(
        "get_taxonomy",
        {"channel": channel, "hook_type": hook_type, "limit": limit},
    )


@mcp.tool(
    name="get_citation_map",
    description=(
        "Return the transcript + screenshot citation map for a saved "
        "uoink, each entry with a timestamped YouTube deep link."
    ),
)
def get_citation_map(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("get_citation_map", {"slug": slug})


@mcp.tool(
    name="get_uoink_health",
    description="Return the per-section extraction health score for a saved uoink.",
)
def get_uoink_health(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("get_uoink_health", {"slug": slug})


@mcp.tool(
    name="find_mentions",
    description=(
        "Find every mention of an entity (person, tool, product, company, "
        "or topic) across saved uoinks, each with a timestamped YouTube "
        "deep link."
    ),
)
def find_mentions(entity: str, limit: int = 50) -> dict:
    return uoink_mcp_tools.call_tool(
        "find_mentions", {"entity": entity, "limit": limit}
    )


@mcp.tool(
    name="get_transcript_reliability",
    description="Return stored transcript reliability spans for a saved uoink.",
)
def get_transcript_reliability(video_id: str) -> dict:
    return uoink_mcp_tools.call_tool(
        "get_transcript_reliability", {"video_id": video_id}
    )

if __name__ == "__main__":
    # `uoink doctor` / dry-run support: `python uoink_mcp.py --doctor` and
    # `--migrate-dry-run` delegate to the server CLI (server is already
    # imported above) instead of starting the stdio transport.
    _argv = sys.argv[1:]
    if "--doctor" in _argv or "--migrate-dry-run" in _argv:
        raise SystemExit(server.run_cli(_argv))
    mcp.run(transport="stdio")
