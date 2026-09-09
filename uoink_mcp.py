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
making 29 stdio tools. AZ-5h owns the stdio write lifetime: budgeted
requests keep one admission through the real SDK JSON-RPC dump, then
release.
"""

from __future__ import annotations

import json
import sys
import time
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
    import anyio
    import anyio.lowlevel
    from mcp.server.fastmcp import FastMCP
    from mcp import types as mcp_types
except ImportError:
    print(
        "Uoink MCP requires the official MCP Python SDK. "
        "Install with: python -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)

# Enforce strict JSON decoding (reject duplicate keys) at raw stdio boundary
_orig_jsonrpc_validate_json = mcp_types.JSONRPCMessage.model_validate_json


def _strict_jsonrpc_validate_json(cls, json_data, *args, **kwargs):
    def _reject_pairs(pairs):
        seen = set()
        for k, v in pairs:
            if k in seen:
                raise ValueError(f"Duplicate JSON key: {k}")
            seen.add(k)
        return dict(pairs)

    if isinstance(json_data, (str, bytes)):
        json.loads(json_data, object_pairs_hook=_reject_pairs)
    return _orig_jsonrpc_validate_json(json_data, *args, **kwargs)


mcp_types.JSONRPCMessage.model_validate_json = classmethod(_strict_jsonrpc_validate_json)


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


# Phase 6 second increment (run BC-2): the cited export is a read on stored
# cues only. Only the arguments the caller supplied are forwarded, so the
# domain validator sees exactly the selector it was given (start/end or
# excerpt_id, optional revision pins) and refuses anything else before any
# storage access. Intercepted below like the Phase 4 tools.
@mcp.tool(
    name="export_cited_range",
    description=(
        "Read-only cited export of one stored transcript range (exact "
        "cue-aligned start/end, at most 120 s and 200 cues) or one current "
        "excerpt id from a saved item: verbatim stored text, per-cue speaker "
        "labels with provenance, overlapping chapters, safe source and seek "
        "links, source/media revisions and evidence refs. Nothing is fetched, "
        "transcribed or saved; refusals carry a next_step."
    ),
)
def export_cited_range(
    video_id: str,
    start: float | None = None,
    end: float | None = None,
    excerpt_id: str | None = None,
    source_revision: str | None = None,
    media_revision: str | None = None,
):
    args: dict = {"video_id": video_id}
    for key, value in (("start", start), ("end", end), ("excerpt_id", excerpt_id),
                       ("source_revision", source_revision), ("media_revision", media_revision)):
        if value is not None:
            args[key] = value
    return uoink_mcp_tools.call_tool("export_cited_range", args)


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

    def _bind_transport_handle_request() -> None:
        _orig_handle_request = low._handle_request

        async def _handle_request_with_transport_scope(
            message, req, session, lifespan_context, raise_exceptions=False,
        ):
            token = library_resources.bind_transport_scope(getattr(message, "request_id", None))
            try:
                scope = library_resources.current_transport_scope()
                if scope is not None and scope.refusal is not None:
                    response = _stdio_refusal_server_result(req, scope.refusal)
                    try:
                        await message.respond(response)
                    except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                        pass
                    return
                return await _orig_handle_request(
                    message, req, session, lifespan_context, raise_exceptions)
            finally:
                library_resources.reset_bound_transport_scope(token)

        low._handle_request = _handle_request_with_transport_scope

    handlers = getattr(low, "request_handlers", None)
    if not isinstance(handlers, dict):  # pragma: no cover -- SDK reshaped
        print("Uoink MCP: tool interception unavailable; Phase 4 tools use FastMCP's "
              "default result shape.", file=sys.stderr)
        _bind_transport_handle_request()
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
        start_time = time.monotonic()
        import library_analysis
        scope = library_resources.current_transport_scope()
        if scope is not None and scope.admitted_at is not None:
            start_time = scope.admitted_at

        def _deadline_result():
            envelope = library_analysis.error_envelope(
                "deadline_exceeded", "Service deadline exceeded during serialization")
            text = library_resources.render_tool_text(envelope)
            return mcp_types.ServerResult(mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=text)], isError=True))

        try:
            with library_analysis.adapter_admission():
                envelope = library_analysis.get_library_activity(args)
                if envelope.get("ok") is not True:
                    text = library_resources.render_tool_text(envelope)
                    if time.monotonic() - start_time > library_analysis.SERVICE_DEADLINE_SEC:
                        return _deadline_result()
                    return mcp_types.ServerResult(mcp_types.CallToolResult(
                        content=[mcp_types.TextContent(type="text", text=text)], isError=True))

                if time.monotonic() - start_time > library_analysis.SERVICE_DEADLINE_SEC:
                    return _deadline_result()

                text = library_resources.render_tool_text(envelope)
                is_error = envelope.get("ok") is not True
                payload = {"content": [{"type": "text", "text": text}], "isError": is_error}
                over_budget = library_resources.wire_bytes(payload) + 256 > limits["max_response_bytes"]
                # Charge final protocol serialization to the same admission/deadline.
                if time.monotonic() - start_time > library_analysis.SERVICE_DEADLINE_SEC:
                    return _deadline_result()
                if over_budget:
                    envelope = library_analysis.error_envelope(
                        "resource_too_large", "Requested document exceeds bounded response limits")
                    text, is_error = library_resources.render_tool_text(envelope), True
                return mcp_types.ServerResult(mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=text)], isError=is_error))
        except ResourceError as exc:
            envelope = library_analysis.error_envelope(
                exc.code, exc.message, details=exc.details or None)
            text, is_error = library_resources.render_tool_text(envelope), True
            return mcp_types.ServerResult(mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=text)], isError=is_error))

    def media_export_result(arguments):
        # Phase 6 (BC-2): the domain envelope is the tool text, isError
        # mirrors ok, and the actual wrapped response is measured against
        # the shared transport budget before it leaves the process. The
        # registry handler already admitted the request on the process
        # guard and charged its deadline; nothing is admitted twice here.
        args = arguments if arguments is not None else {}
        if not isinstance(args, dict):
            args = {}
        envelope = uoink_mcp_tools.call_tool("export_cited_range", args)
        if not isinstance(envelope, dict) or "ok" not in envelope:
            envelope = ResourceError("internal_error").envelope()
        text = library_resources.render_tool_text(envelope)
        is_error = envelope.get("ok") is not True
        payload = {"content": [{"type": "text", "text": text}], "isError": is_error}
        if library_resources.wire_bytes(payload) + 256 > limits["max_response_bytes"]:
            envelope = ResourceError("resource_too_large", details={
                "what": "export_cited_range", "next_step": "read_library_resource"}).envelope()
            text, is_error = library_resources.render_tool_text(envelope), True
        return mcp_types.ServerResult(mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)], isError=is_error))

    if fastmcp_call_tool is not None:
        async def _phase4_call_tool(req):
            if req.params.name in library_resources.TOOL_NAMES:
                return tool_result(req.params.name, req.params.arguments)
            if req.params.name == "get_library_activity":
                return activity_result(req.params.arguments)
            if req.params.name == "export_cited_range":
                return media_export_result(req.params.arguments)
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
                    if tool.name in ("get_library_activity", "export_cited_range"):
                        if tool.name in uoink_mcp_tools.TOOL_REGISTRY:
                            reg_spec = uoink_mcp_tools.TOOL_REGISTRY[tool.name]
                            tool.inputSchema = reg_spec.input_schema
                            tool.description = reg_spec.description
                        tool.annotations = mcp_types.ToolAnnotations(readOnlyHint=True, idempotentHint=True)
            except (AttributeError, TypeError, ValueError):  # pragma: no cover
                pass
            return result
        handlers[mcp_types.ListToolsRequest] = _phase4_list_tools

    _bind_transport_handle_request()


def _stdio_param(params, key: str):
    if params is None:
        return None
    if isinstance(params, dict):
        return params.get(key)
    return getattr(params, key, None)


def _stdio_refusal_server_result(req, exc):
    import library_analysis
    import library_resources
    tool_name = _stdio_param(getattr(req, "params", None), "name")
    method = getattr(req, "method", None)
    if method == "tools/call" or tool_name:
        if tool_name == library_resources.ACTIVITY_TOOL_NAME:
            envelope = library_analysis.error_envelope(
                exc.code, exc.message, details=exc.details or None)
        else:
            envelope = exc.envelope()
        text = library_resources.render_tool_text(envelope)
        return mcp_types.ServerResult(mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)], isError=True))
    code = -32602 if exc.code == "invalid_request" else (
        -32002 if exc.code in ("resource_not_found", "resource_deleted") else -32603)
    return mcp_types.ErrorData(code=code, message=exc.message, data=exc.envelope())


def _stdio_jsonrpc_is_error(root) -> bool:
    if isinstance(root, mcp_types.JSONRPCError):
        return True
    if isinstance(root, mcp_types.JSONRPCResponse) and isinstance(root.result, dict):
        return root.result.get("isError") is True
    return False


def _stdio_domain_tool_message(request_id, envelope):
    import library_resources
    text = library_resources.render_tool_text(envelope)
    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)], isError=True)
    dumped = result.model_dump(by_alias=True, mode="json", exclude_none=True)
    return mcp_types.JSONRPCMessage(
        mcp_types.JSONRPCResponse(jsonrpc="2.0", id=request_id, result=dumped))


def _stdio_domain_rpc_error_message(request_id, exc):
    code = -32602 if exc.code == "invalid_request" else (
        -32002 if exc.code in ("resource_not_found", "resource_deleted") else -32603)
    return mcp_types.JSONRPCMessage(mcp_types.JSONRPCError(
        jsonrpc="2.0",
        id=request_id,
        error=mcp_types.ErrorData(code=code, message=exc.message, data=exc.envelope()),
    ))


def _stdio_budget_refusal_message(scope, request_id, code: str):
    import library_analysis
    import library_resources
    if code == "deadline_exceeded":
        if scope.tool_name == library_resources.ACTIVITY_TOOL_NAME:
            envelope = library_analysis.error_envelope(
                "deadline_exceeded", "Service deadline exceeded during serialization")
        else:
            envelope = library_resources.ResourceError("deadline_exceeded").envelope()
        exc = library_resources.ResourceError("deadline_exceeded")
    else:
        if scope.tool_name == library_resources.ACTIVITY_TOOL_NAME:
            envelope = library_analysis.error_envelope(
                "resource_too_large", "Requested document exceeds bounded response limits")
        else:
            envelope = library_resources.ResourceError(
                "resource_too_large",
                details={"what": scope.tool_name or scope.method,
                         "next_step": "lower limit or read a smaller resource"},
            ).envelope()
        exc = library_resources.ResourceError("resource_too_large")
    if scope.method == "tools/call":
        return _stdio_domain_tool_message(request_id, envelope)
    return _stdio_domain_rpc_error_message(request_id, exc)


_STDIO_PROTOCOL_REJECTION_CODE = -32600
_STDIO_PROTOCOL_REJECTION_MESSAGE = "Inbound request exceeds protocol limits"


def _stdio_completed_frame_cap() -> int:
    import library_resources
    return int(library_resources.LIMITS["max_response_bytes"])


def _stdio_protocol_rejection_frame(request_id=None) -> str:
    """Fixed bounded JSON-RPC rejection. ``id`` is null when the inbound
    envelope cannot be accepted. The installed SDK type rejects ``id=None``."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": _STDIO_PROTOCOL_REJECTION_CODE,
                "message": _STDIO_PROTOCOL_REJECTION_MESSAGE,
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _stdio_line_utf8_len(line) -> int:
    if isinstance(line, bytes):
        return len(line.rstrip(b"\r\n"))
    text = line if isinstance(line, str) else str(line)
    return len(text.rstrip("\r\n").encode("utf-8"))


def _stdio_request_id_fits(request_id, cap: int) -> bool:
    if request_id is None:
        return True
    try:
        frame = _stdio_protocol_rejection_frame(request_id)
    except (TypeError, ValueError, OverflowError):
        return False
    return len(frame.encode("utf-8")) <= cap


def _stdio_inbound_line_rejection(line) -> str | None:
    if _stdio_line_utf8_len(line) > _stdio_completed_frame_cap():
        return _stdio_protocol_rejection_frame(None)
    return None


def _stdio_request_id_rejection(message) -> str | None:
    root = message.root
    if isinstance(root, mcp_types.JSONRPCNotification):
        return None
    request_id = getattr(root, "id", None)
    if _stdio_request_id_fits(request_id, _stdio_completed_frame_cap()):
        return None
    return _stdio_protocol_rejection_frame(None)


def _stdio_enforce_completed_frame(text: str, request_id, scope) -> str:
    """Bound success, typed errors, and replacement refusals to the wire cap."""
    import library_resources
    cap = _stdio_completed_frame_cap()
    if len(text.encode("utf-8")) <= cap:
        return text
    if request_id is not None and _stdio_request_id_fits(request_id, cap):
        if scope is not None:
            repl = _stdio_budget_refusal_message(
                scope, request_id, "resource_too_large"
            ).model_dump_json(by_alias=True, exclude_none=True)
        else:
            repl = _stdio_protocol_rejection_frame(request_id)
        if len(repl.encode("utf-8")) <= cap:
            return repl
    return _stdio_protocol_rejection_frame(None)


def _begin_inbound_transport_scope(message) -> None:
    import library_resources
    root = message.root
    if isinstance(root, mcp_types.JSONRPCNotification):
        method = getattr(root, "method", "") or ""
        if method == "notifications/cancelled":
            request_id = _stdio_param(root.params, "requestId")
            if request_id is None:
                request_id = _stdio_param(root.params, "request_id")
            library_resources.mark_transport_cancelled(request_id)
        return
    if not isinstance(root, mcp_types.JSONRPCRequest):
        return
    tool_name = _stdio_param(root.params, "name") if root.method == "tools/call" else None
    if not library_resources.is_budgeted_stdio_request(root.method, tool_name):
        return
    library_resources.begin_transport_request(root.id, root.method, tool_name)


async def _deliver_bounded_outbound(session_message, stdout) -> None:
    """Serialize with the real SDK message, then check bytes and deadline."""
    import library_resources
    message = session_message.message
    root = message.root
    request_id = getattr(root, "id", None) if not isinstance(root, mcp_types.JSONRPCNotification) else None
    scope = library_resources.transport_scope(request_id)
    try:
        if (
            scope is not None
            and scope.cancel_requested
            and not _stdio_jsonrpc_is_error(root)
        ):
            return
        text = message.model_dump_json(by_alias=True, exclude_none=True)
        if (
            scope is not None
            and not scope.cancel_requested
            and not _stdio_jsonrpc_is_error(root)
        ):
            if scope.expired():
                text = _stdio_budget_refusal_message(
                    scope, request_id, "deadline_exceeded"
                ).model_dump_json(by_alias=True, exclude_none=True)
            elif len(text.encode("utf-8")) > library_resources.LIMITS["max_response_bytes"]:
                text = _stdio_budget_refusal_message(
                    scope, request_id, "resource_too_large"
                ).model_dump_json(by_alias=True, exclude_none=True)
        text = _stdio_enforce_completed_frame(text, request_id, scope)
        await stdout.write(text + "\n")
        await stdout.flush()
    finally:
        if request_id is not None:
            library_resources.finish_transport_request(request_id)


def bounded_stdio_server(stdin=None, stdout=None):
    """Application stdio transport: SDK messages, product-owned write lifetime."""
    return _bounded_stdio_server(stdin, stdout)


def _bounded_stdio_server(stdin=None, stdout=None):
    from contextlib import asynccontextmanager
    from io import TextIOWrapper

    from mcp.shared.message import SessionMessage

    @asynccontextmanager
    async def _cm(stdin=stdin, stdout=stdout):
        import library_resources
        if not stdin:
            stdin = anyio.wrap_file(TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace"))
        if not stdout:
            stdout = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))

        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
        write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

        async def stdin_reader():
            try:
                async with read_stream_writer:
                    async for line in stdin:
                        inbound_refusal = _stdio_inbound_line_rejection(line)
                        if inbound_refusal is not None:
                            await write_stream.send(inbound_refusal)
                            continue
                        try:
                            message = mcp_types.JSONRPCMessage.model_validate_json(line)
                        except Exception as exc:
                            await read_stream_writer.send(exc)
                            continue
                        inbound_refusal = _stdio_request_id_rejection(message)
                        if inbound_refusal is not None:
                            await write_stream.send(inbound_refusal)
                            continue
                        _begin_inbound_transport_scope(message)
                        await read_stream_writer.send(SessionMessage(message))
            except anyio.ClosedResourceError:  # pragma: no cover
                await anyio.lowlevel.checkpoint()

        async def stdout_writer():
            try:
                async with write_stream_reader:
                    async for session_message in write_stream_reader:
                        if isinstance(session_message, str):
                            frame = session_message if session_message.endswith("\n") else session_message + "\n"
                            await stdout.write(frame)
                            await stdout.flush()
                            continue
                        await _deliver_bounded_outbound(session_message, stdout)
            except anyio.ClosedResourceError:  # pragma: no cover
                await anyio.lowlevel.checkpoint()
            finally:
                library_resources.release_all_transport_scopes()

        async with anyio.create_task_group() as tg:
            tg.start_soon(stdin_reader)
            tg.start_soon(stdout_writer)
            try:
                yield read_stream, write_stream
            finally:
                library_resources.release_all_transport_scopes()

    return _cm()


async def run_bounded_stdio_async() -> None:
    """Shipped stdio entry: bounded writer around the registered low-level server."""
    async with bounded_stdio_server() as (read_stream, write_stream):
        low = mcp._mcp_server
        await low.run(read_stream, write_stream, low.create_initialization_options())


_register_phase4_stdio()
mcp.run_stdio_async = run_bounded_stdio_async


if __name__ == "__main__":
    # `uoink doctor` / dry-run support: `python uoink_mcp.py --doctor` and
    # `--migrate-dry-run` delegate to the server CLI (server is already
    # imported above) instead of starting the stdio transport.
    _argv = sys.argv[1:]
    if "--doctor" in _argv or "--migrate-dry-run" in _argv:
        raise SystemExit(server.run_cli(_argv))
    mcp.run(transport="stdio")
