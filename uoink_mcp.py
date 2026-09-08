"""Uoink MCP stdio entry point.

Run with:

    python uoink_mcp.py

MCP clients launch this process and speak JSON-RPC over stdin/stdout. Keep
stdout reserved for the protocol; server.py logging is redirected to stderr
while importing the backend.

The stdio surface is the 25 canonical tools below plus, since Phase 4 run
AV-1 (2026-09-08), the three bounded read tools `search_library`,
`get_library_item` and `read_library_resource`, the five library resource
templates and the four library prompts (contract phase4-v1-2026-09-08,
docs/library/PHASE4-CONTRACT-2026-09-08.md). The six Yoink-era aliases
completed their deprecation window in Uoink v2.5 and are not registered in
v3. Run E (2026-09-04) added the two Phase 1 clip tools, `search_clips` and
`get_evidence_card`, to stdio. See docs/v2-mcp.md.
Phase 5 run AZ (2026-09-08) added `get_library_activity` (contract phase5-v1),
making 29 stdio tools.
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
    from mcp import types as mcp_types
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
        "Uoink turns videos, playlists, and podcast episodes into local "
        "AI-ready corpora. Use the tools to capture, transcribe, publish, "
        "search, inspect, and analyze saved uoinks."
    ),
)
# FastMCP defaults initialize.serverInfo.version to the MCP SDK's version,
# which makes client logs identify the dependency rather than this product.
# The v1 SDK exposes the low-level server here; if a future SDK reshapes that
# internal, keep serving with its fallback identity instead of failing startup.
try:
    mcp._mcp_server.version = server.VERSION
except AttributeError:
    pass


# --------------------------------------------------------------------------
# Canonical tools (26). The CI doc-accuracy + backend-static jobs count these
# @mcp.tool decorators against the ### headings in docs/v2-mcp.md, so keep the
# decorator count and the documented tool count in lock-step (also
# tests/test_c01_mcp_stdio.py CANONICAL_STDIO_TOOLS and .mcpb/manifest.json).
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
    name="search_clips",
    description=(
        "Full-text search over transcript windows from saved uoinks; each hit "
        "carries a deep link to the moment. Use this to find the exact "
        "quotable passage; use search_uoinks to find whole items."
    ),
)
def search_clips(
    query: str,
    limit: int = 20,
    video_id: str | None = None,
    channel: str | None = None,
) -> dict:
    args: dict = {"query": query, "limit": limit}
    if video_id:
        args["video_id"] = video_id
    if channel:
        args["channel"] = channel
    return uoink_mcp_tools.call_tool("search_clips", args)


@mcp.tool(
    name="get_evidence_card",
    description=(
        "Return an evidence card for one saved uoink: metadata, source URL, "
        "a short summary hint, and its most quotable clips spread across the "
        "timeline, each with a deep link. Resolve by slug or video_id. "
        "profile 'full' (default) or 'librarian' (bounded)."
    ),
)
def get_evidence_card(
    slug: str | None = None,
    video_id: str | None = None,
    profile: str = "full",
    n_clips: int | None = None,
) -> dict:
    args: dict = {"profile": profile}
    if slug:
        args["slug"] = slug
    if video_id:
        args["video_id"] = video_id
    if n_clips is not None:
        args["n_clips"] = n_clips
    return uoink_mcp_tools.call_tool("get_evidence_card", args)


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
        "uoink, each entry with a source-aware timestamp link."
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
        "or topic) across saved uoinks, each with a source-aware timestamp "
        "link when the source has a public URL."
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


@mcp.tool(
    name="add_podcast_feed",
    description=("Register a podcast RSS or Atom feed for metadata watching, "
                 "with optional per-feed Auto-ingest."),
)
def add_podcast_feed(
    feed_url: str,
    poll_interval_min: int = 60,
    auto_ingest: bool = False,
) -> dict:
    return uoink_mcp_tools.call_tool(
        "add_podcast_feed",
        {"feed_url": feed_url, "poll_interval_min": poll_interval_min,
         "auto_ingest": auto_ingest},
    )


@mcp.tool(name="list_podcast_feeds", description="List registered podcast feeds.")
def list_podcast_feeds(enabled_only: bool = False) -> dict:
    return uoink_mcp_tools.call_tool(
        "list_podcast_feeds", {"enabled_only": enabled_only}
    )


@mcp.tool(
    name="remove_podcast_feed",
    description="Remove a podcast feed and its tracked episode rows.",
)
def remove_podcast_feed(feed_id: int) -> dict:
    return uoink_mcp_tools.call_tool("remove_podcast_feed", {"feed_id": feed_id})


@mcp.tool(
    name="poll_podcast_feed",
    description="Fetch one podcast feed now and retain newly discovered episodes.",
)
def poll_podcast_feed(feed_id: int) -> dict:
    return uoink_mcp_tools.call_tool("poll_podcast_feed", {"feed_id": feed_id})


@mcp.tool(
    name="list_podcast_episodes",
    description="List tracked podcast episodes with optional feed and status filters.",
)
def list_podcast_episodes(
    feed_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict:
    return uoink_mcp_tools.call_tool(
        "list_podcast_episodes",
        {"feed_id": feed_id, "status": status, "limit": limit},
    )


@mcp.tool(
    name="download_podcast_episode",
    description="Download one episode's MP3 locally with yt-dlp and ffmpeg.",
)
def download_podcast_episode(episode_id: int) -> dict:
    return uoink_mcp_tools.call_tool(
        "download_podcast_episode", {"episode_id": episode_id}
    )


@mcp.tool(
    name="get_whisperx_status",
    description="Report local WhisperX availability and supported models.",
)
def get_whisperx_status() -> dict:
    return uoink_mcp_tools.call_tool("get_whisperx_status", {})


@mcp.tool(
    name="transcribe_podcast_episode",
    description="Queue one local podcast transcription and return its durable job id.",
)
def transcribe_podcast_episode(
    episode_id: int,
    model: str = "base",
    language: str | None = None,
    diarize: bool = False,
    consent_given: bool = False,
) -> dict:
    return uoink_mcp_tools.call_tool(
        "transcribe_podcast_episode",
        {
            "episode_id": episode_id,
            "model": model,
            "language": language,
            "diarize": diarize,
            "consent_given": consent_given,
        },
    )


@mcp.tool(
    name="episode_to_corpus",
    description="Publish a completed podcast transcript into the local corpus.",
)
def episode_to_corpus(episode_id: int) -> dict:
    return uoink_mcp_tools.call_tool(
        "episode_to_corpus", {"episode_id": episode_id}
    )


@mcp.tool(
    name="get_library_activity",
    description="Report deterministic library activity, shelf churn, and source observations.",
    annotations=mcp_types.ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def get_library_activity(
    interval: dict,
    date_basis: str = "capture_time",
    detail: str | None = None,
    metric_id: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
    expected_revision: str | None = None,
) -> dict:
    payload: dict = {
        "interval": interval,
        "date_basis": date_basis,
    }
    if detail is not None:
        payload["detail"] = detail
    if metric_id is not None:
        payload["metric_id"] = metric_id
    if expected_revision is not None:
        payload["expected_revision"] = expected_revision
    if offset is not None:
        payload["offset"] = offset
    if limit is not None:
        payload["limit"] = limit
    return uoink_mcp_tools.call_tool("get_library_activity", payload)

# --------------------------------------------------------------------------
# Phase 4 (run AV-1, contract phase4-v1-2026-09-08): bounded library access.
#
# The three read tools are registered with @mcp.tool so they appear in
# tools/list next to the 25 canonical tools; their execution is intercepted
# on the low-level server so the domain envelope is returned as text with
# isError set from the envelope, never wrapped in the SDK's "Error executing
# tool" string. Resources and prompts use low-level handlers on
# mcp._mcp_server (replacing FastMCP's empty defaults) so the curated list,
# the five templates, the four prompts and the JSON-RPC error codes are ours:
# -32602 invalid parameters, -32002 missing or deleted resource, -32603 any
# other refusal, each carrying the domain envelope in error.data. The SDK
# advertises resources {subscribe:false, listChanged:false} and prompts
# {listChanged:false} only because these handlers exist; no notification is
# ever emitted. Duplicate JSON keys are not detectable here (the SDK hands
# handlers parsed objects); the HTTP /tools/* route rejects them from raw
# bytes. Every reader is request-scoped on the process-wide guard (2 active,
# 60 admissions per minute, 2 s deadline). Nothing here writes to stdout.
# --------------------------------------------------------------------------
@mcp.tool(
    name="search_library",
    description=(
        "Bounded clip-first search of the saved library (default 5, at most "
        "20 hits) with an item-text fallback for items without clips. Each "
        "hit carries the item id, source revision, safe title and link, "
        "evidence kind and timing, a 240-character preview and revision-bound "
        "card and excerpt URIs for read_library_resource. Results are "
        "bounded, not exhaustive; follow next_step when more retrieval is "
        "needed."
    ),
)
def search_library(query: str, limit: int = 5):
    return uoink_mcp_tools.call_tool("search_library", {"query": query, "limit": limit})


@mcp.tool(
    name="get_library_item",
    description=(
        "Resolve one saved item by video_id or slug (exactly one) and return "
        "its default Librarian evidence card unchanged plus canonical card, "
        "excerpt and initial corpus-chunk URIs. Bounded; use before quoting."
    ),
)
def get_library_item(video_id: str | None = None, slug: str | None = None):
    args: dict = {}
    if video_id is not None:
        args["video_id"] = video_id
    if slug is not None:
        args["slug"] = slug
    return uoink_mcp_tools.call_tool("get_library_item", args)


@mcp.tool(
    name="read_library_resource",
    description=(
        "Read one uoink://library/v1/ resource URI (card, excerpt, corpus "
        "chunk, shelf page or brief) with the same validation, contents and "
        "refusals as resources/read. Fallback for clients without native "
        "resource reads; identical text, one renderer."
    ),
)
def read_library_resource(uri: str):
    return uoink_mcp_tools.call_tool("read_library_resource", {"uri": uri})


# Phase 4 second increment (run AV-2): brief generation belongs to the client.
# get_library_brief_input is a read; publish_library_brief is a local write
# under DATA_ROOT/reach/briefs. Both are intercepted below like the three read
# tools, so the domain envelope is the tool text.
@mcp.tool(
    name="get_library_brief_input",
    description=(
        "Prepare bounded input for a client-run daily brief: for a UTC date "
        "and a Phase 2 run id, return job_key, input_hash, bound "
        "queue/run/projection revisions, capture and event counts, coverage, "
        "up to 20 work-status rows and up to 5 default Librarian cards (at "
        "most 24,576 bytes). Read only: no lease, no mutation. The client "
        "tracks its own report job."
    ),
)
def get_library_brief_input(date: str, run_id: str):
    return uoink_mcp_tools.call_tool("get_library_brief_input", {"date": date, "run_id": run_id})


@mcp.tool(
    name="publish_library_brief",
    description=(
        "Local write: persist one client-produced brief for a job prepared by "
        "get_library_brief_input. Validates the packet against current "
        "library data (stale_brief on change), binds every citation to "
        "supplied evidence, is idempotent on submission_key, and stores an "
        "immutable artifact under the local reach/briefs directory. Cannot "
        "apply labels or alter the assignment queue. Invoke only as part of "
        "the user's requested brief job."
    ),
)
def publish_library_brief(
    job_key: str,
    input_hash: str,
    input_packet: dict,
    submission_key: str,
    document: str,
    citations: list,
    usage: dict | None = None,
):
    return uoink_mcp_tools.call_tool("publish_library_brief", {
        "job_key": job_key, "input_hash": input_hash, "input_packet": input_packet,
        "submission_key": submission_key, "document": document, "citations": citations,
        "usage": usage,
    })


def _register_phase4_stdio() -> None:
    """Low-level resource, prompt and tool-execution handlers (see above).
    Any missing piece degrades to FastMCP's defaults with a stderr note
    rather than failing startup; the 25 canonical tools are untouched."""
    try:
        import library_prompts
        import library_resources
    except ImportError as exc:
        print(f"Uoink MCP: Phase 4 library modules unavailable ({exc}); "
              "resources and prompts are not served.", file=sys.stderr)
        return
    try:
        from mcp import types as mcp_types
        from mcp.shared.exceptions import McpError
    except ImportError as exc:  # pragma: no cover -- SDK reshaped
        print(f"Uoink MCP: cannot register Phase 4 handlers ({exc}).", file=sys.stderr)
        return
    try:
        from mcp.server.lowlevel.helper_types import ReadResourceContents
    except ImportError:  # pragma: no cover -- SDK reshaped; duck-typed by the decorator
        class ReadResourceContents:  # type: ignore[no-redef]
            def __init__(self, content, mime_type=None):
                self.content = content
                self.mime_type = mime_type

    low = getattr(mcp, "_mcp_server", None)
    if low is None:  # pragma: no cover -- SDK reshaped
        print("Uoink MCP: low-level server not exposed; Phase 4 handlers not registered.",
              file=sys.stderr)
        return

    ResourceError = library_resources.ResourceError
    limits = library_resources.LIMITS

    def reader():
        # Request-scoped: storage is bound inside the first admitted operation
        # (existing storage only, never created or recovered), and the
        # deadline runs from that admission through serialization (AV-1r D1,
        # D7). Construction opens nothing.
        return library_resources.make_reader(server)

    def work_service(active_reader):
        # Report-only: use the service only if the index already built one;
        # constructing it could run Phase 2 recovery, which is not a read.
        # Resolved after admission because the index is bound lazily.
        return library_prompts.DeferredService(
            lambda: getattr(active_reader.index, "_library_work_service", None))

    def mcp_error(exc) -> McpError:
        if exc.code == "invalid_request":
            code = -32602
        elif exc.code in ("resource_not_found", "resource_deleted"):
            code = -32002
        else:
            code = -32603
        return McpError(mcp_types.ErrorData(code=code, message=exc.message, data=exc.envelope()))

    @low.list_resource_templates()
    async def _phase4_list_templates():
        return [mcp_types.ResourceTemplate(**template) for template in library_resources.TEMPLATES]

    @low.list_resources()
    async def _phase4_list_resources():
        try:
            active = reader()
            entries = active.list_resources()
            resources = []
            for entry in entries:
                fields = {"uri": entry["uri"], "name": entry["name"],
                          "description": entry.get("description"), "mimeType": entry.get("mimeType")}
                if isinstance(entry.get("size"), int):
                    fields["size"] = entry["size"]
                resources.append(mcp_types.Resource(**fields))
            # The same request's deadline covers this serialization (D1).
            active.assert_within_deadline()
        except ResourceError as exc:
            raise mcp_error(exc) from None
        return resources

    @low.read_resource()
    async def _phase4_read_resource(uri):
        try:
            active = reader()
            result = active.read(str(uri))
            contents = [ReadResourceContents(content=item["text"], mime_type=item["mimeType"])
                        for item in result["contents"]]
            active.assert_within_deadline()
        except ResourceError as exc:
            raise mcp_error(exc) from None
        return contents

    @low.list_prompts()
    async def _phase4_list_prompts():
        return [mcp_types.Prompt(
            name=prompt["name"], description=prompt["description"],
            arguments=[mcp_types.PromptArgument(**argument) for argument in prompt["arguments"]],
        ) for prompt in library_prompts.PROMPTS]

    @low.get_prompt()
    async def _phase4_get_prompt(name, arguments):
        try:
            active = reader()
            result = library_prompts.get_prompt(active, work_service(active), name, arguments)
            rendered = mcp_types.GetPromptResult(
                description=result["description"],
                messages=[mcp_types.PromptMessage(
                    role=message["role"],
                    content=mcp_types.TextContent(type="text", text=message["content"]["text"]),
                ) for message in result["messages"]],
            )
            active.assert_within_deadline()
        except ResourceError as exc:
            raise mcp_error(exc) from None
        return rendered

    handlers = getattr(low, "request_handlers", None)
    if not isinstance(handlers, dict):  # pragma: no cover -- SDK reshaped
        print("Uoink MCP: tool interception unavailable; Phase 4 tools use FastMCP's "
              "default result shape.", file=sys.stderr)
        return
    fastmcp_call_tool = handlers.get(mcp_types.CallToolRequest)
    fastmcp_list_tools = handlers.get(mcp_types.ListToolsRequest)

    def tool_result(name, arguments):
        active = reader()
        envelope = library_resources.call_tool(name, arguments if arguments is not None else {}, active,
                                               client_identity="stdio")
        text = library_resources.render_tool_text(envelope)
        is_error = envelope.get("ok") is not True
        payload = {"content": [{"type": "text", "text": text}], "isError": is_error}
        if library_resources.wire_bytes(payload) + 256 > limits["max_response_bytes"]:
            envelope = ResourceError("resource_too_large", details={
                "what": name, "next_step": "lower limit or read a smaller resource"}).envelope()
            text, is_error = library_resources.render_tool_text(envelope), True
        try:
            # Rendering and the wire check are charged to the same request (D1).
            active.assert_within_deadline()
        except ResourceError as exc:
            text, is_error = library_resources.render_tool_text(exc.envelope()), True
        return mcp_types.ServerResult(mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)], isError=is_error))

    def activity_result(arguments):
        args = arguments if arguments is not None else {}
        try:
            import library_analysis
            envelope = library_analysis.get_library_activity(args)
            text = library_resources.render_tool_text(envelope)
            is_error = envelope.get("ok") is not True
            payload = {"content": [{"type": "text", "text": text}], "isError": is_error}
            if library_resources.wire_bytes(payload) + 256 > limits["max_response_bytes"]:
                envelope = ResourceError("resource_too_large", details={
                    "what": "get_library_activity", "next_step": "lower limit or read a smaller interval"}).envelope()
                text, is_error = library_resources.render_tool_text(envelope), True
            return mcp_types.ServerResult(mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=text)], isError=is_error))
        except ResourceError as exc:
            text, is_error = library_resources.render_tool_text(exc.envelope()), True
            return mcp_types.ServerResult(mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=text)], isError=is_error))

    if fastmcp_call_tool is not None:
        async def _phase4_call_tool(req):
            if req.params.name in library_resources.TOOL_NAMES:
                return tool_result(req.params.name, req.params.arguments)
            if req.params.name == "get_library_activity":
                return activity_result(req.params.arguments)
            return await fastmcp_call_tool(req)
        handlers[mcp_types.CallToolRequest] = _phase4_call_tool

    if fastmcp_list_tools is not None:
        async def _phase4_list_tools(req):
            result = await fastmcp_list_tools(req)
            try:
                for tool in result.root.tools:
                    if tool.name in library_resources.TOOL_SCHEMAS:
                        # Same strict schema and text as the HTTP registry.
                        tool.inputSchema = library_resources.TOOL_SCHEMAS[tool.name]
                        tool.description = library_resources.TOOL_DESCRIPTIONS[tool.name]
                    if tool.name == "get_library_activity":
                        tool.annotations = mcp_types.ToolAnnotations(readOnlyHint=True, idempotentHint=True)
            except (AttributeError, TypeError, ValueError):  # pragma: no cover
                pass
            return result
        handlers[mcp_types.ListToolsRequest] = _phase4_list_tools


_register_phase4_stdio()


if __name__ == "__main__":
    # `uoink doctor` / dry-run support: `python uoink_mcp.py --doctor` and
    # `--migrate-dry-run` delegate to the server CLI (server is already
    # imported above) instead of starting the stdio transport.
    _argv = sys.argv[1:]
    if "--doctor" in _argv or "--migrate-dry-run" in _argv:
        raise SystemExit(server.run_cli(_argv))
    mcp.run(transport="stdio")
