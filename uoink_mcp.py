"""Uoink MCP stdio entry point.

Run with:

    python uoink_mcp.py

MCP clients launch this process and speak JSON-RPC over stdin/stdout. Keep
stdout reserved for the protocol; server.py logging is redirected to stderr
while importing the backend.

The default full toolset serves all 91 tools in TOOL_REGISTRY, with the same
names, descriptions, schemas, titles and annotations; three schemas with a
top-level oneOf are flattened for client compatibility (client_input_schema). UOINK_MCP_TOOLSET=core
serves the previous 35 tools. Those tools remain first, in their original
order, in full mode. Unknown toolset values warn on stderr and use full.

All handlers use the shared registry's consent and safety checks. No tools
are excluded from stdio. Dashboard intent minting is never an MCP tool;
discovery's in-memory, origin-bound intents cannot cross into this process,
so discovery requires the explicit agent-consent setting here. Library and
source intents use the same token-derived trusted session as HTTP.

Five resource templates and nine prompts remain available in both modes.
Bounded Library admission stays alive through the concrete SDK JSON-RPC
dump, write and flush. Other registry tools run on the
event loop one at a time, as in v3.9.1, because they share the Index
connection with Library reads; a long capture holds the session until it
returns. Paid discovery runs in a worker thread, as in v3.9.1.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Literal

if sys.platform == "darwin":
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

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

import uoink_install_isolation as _install_isolation  # noqa: E402
_install_isolation.apply_from_process()


try:
    import anyio
    import anyio.lowlevel
    from mcp.server import Server
    from mcp.server.caching import CACHEABLE_METHODS, CacheHint
    from mcp.shared.dispatcher import coerce_request_id
    from mcp import types as mcp_types
    from mcp.types.version import LATEST_MODERN_VERSION
except ImportError:
    print(
        "Uoink MCP requires the official MCP Python SDK. "
        "Install with: python -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)

class _InvalidStdioRequest(ValueError):
    """Valid JSON whose JSON-RPC envelope cannot be accepted."""


def parse_stdio_message(line):
    """Drop responses; reject ambiguous or oversized requests before SDK validation."""
    def reject_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    raw = json.loads(line, object_pairs_hook=reject_pairs,
                     parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Invalid number")))
    if (isinstance(raw, dict) and raw.get("jsonrpc") == "2.0" and
            "method" not in raw and ("result" in raw or "error" in raw)):
        # Responses, including null-ID errors, never call for another reply.
        logging.getLogger(__name__).debug("Ignoring inbound JSON-RPC response")
        return None
    if _stdio_inbound_line_rejection(line) is not None:
        raise _InvalidStdioRequest(_STDIO_PROTOCOL_REJECTION_MESSAGE)
    if not isinstance(raw, dict):
        if raw == []:
            raise _InvalidStdioRequest("Empty JSON-RPC batch")
        raise _InvalidStdioRequest("Expected a JSON-RPC object")
    if "id" in raw and (type(raw["id"]) not in (int, str)):
        raise _InvalidStdioRequest("Invalid request ID")
    try:
        return mcp_types.jsonrpc_message_adapter.validate_json(line, by_name=False)
    except ValueError as exc:
        raise _InvalidStdioRequest("Invalid JSON-RPC envelope") from exc


# server.py configures a stdout log handler at import time. MCP stdio uses
# stdout as the JSON-RPC transport, so bind that log handler to stderr instead.
_stdout = sys.stdout
try:
    sys.stdout = sys.stderr
    import server  # noqa: E402
finally:
    sys.stdout = _stdout

import uoink_mcp_tools  # noqa: E402
import uoink_usage  # noqa: E402


uoink_mcp_tools.bind_backend(server)

def _selected_toolset() -> str:
    value = os.environ.get("UOINK_MCP_TOOLSET", "full")
    if value not in ("full", "core"):
        print("Uoink MCP: unknown UOINK_MCP_TOOLSET; using full (expected full or core).",
              file=sys.stderr)
        return "full"
    return value


class RegistryMCP(Server):
    """Public low-level server with Uoink dispatch and transport settlement.

    Schemas pass through uoink_mcp_tools.client_input_schema so a client that
    rejects top-level oneOf (Claude Code, the Anthropic API) still sees every tool.
    """

    def create_initialization_options(self, notification_options=None, experimental_capabilities=None, extensions=None):
        return super().create_initialization_options(
            notification_options,
            {} if experimental_capabilities is None else experimental_capabilities,
            extensions)

    async def list_tools(self):
        names = uoink_mcp_tools.stdio_tool_names(STDIO_TOOLSET)
        registry = {tool["name"]: tool for tool in uoink_mcp_tools.list_tools()}
        return [mcp_types.Tool(**dict(registry[name], inputSchema=uoink_mcp_tools.client_input_schema(
            registry[name]["inputSchema"]))) for name in names]

    async def call_tool(self, name, arguments):
        if name not in uoink_mcp_tools.stdio_tool_names(STDIO_TOOLSET):
            envelope = {"ok": False, "error": "tool not found"}
        elif name in uoink_mcp_tools.DISCOVERY_TOOL_NAMES:
            # Paid discovery has its own 8 s/page timeout, not the 2 s
            # library-read deadline. Keep stdio responsive to other calls
            # and cancellation while the bounded worker finishes (as in v3.9.1).
            state = _active_stdio_request.get()
            if state is not None:
                # Peer cancellation cannot stop a paid worker thread. AnyIO
                # waits for that worker before the unanswered callback settles
                # the request, keeping its ID reserved throughout the work.
                envelope = await anyio.to_thread.run_sync(uoink_mcp_tools.call_tool, name, arguments)
            else:
                envelope = await asyncio.to_thread(uoink_mcp_tools.call_tool, name, arguments)
        else:
            # Registry handlers share one Index connection with the Library
            # read, prompt and resource handlers, and several read idx._conn
            # outside the Index lock. Run them on the event loop, one at a
            # time, exactly as the v3.9.1 FastMCP tools ran.
            envelope = _call_stdio_registry(name, arguments)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=json.dumps(
                envelope, ensure_ascii=False, allow_nan=False))],
            is_error=envelope.get("ok") is not True)

    async def run(self, read_stream, write_stream, initialization_options, raise_exceptions=False):
        """Own the public streams, including the alternate SDK stdio writer."""
        bounded = _bounded_stdio_writer_depth.get() > 0
        token = _stdio_requests.set({}) if not bounded else None
        usage_token = _stdio_usage_connection.set({}) if not bounded else None
        try:
            await super().run(
                # The bounded reader already prepares messages before queueing.
                read_stream if bounded else _InboundScopeStream(read_stream),
                write_stream if bounded else _SdkSettlementStream(write_stream),
                initialization_options, raise_exceptions=raise_exceptions)
        finally:
            if token is not None:
                _release_stdio_requests()
                _stdio_requests.reset(token)
                _stdio_usage_connection.reset(usage_token)



STDIO_TOOLSET = _selected_toolset()
mcp = RegistryMCP(
    "uoink",
    version=server.VERSION,
    cache_hints={method: CacheHint(ttl_ms=0, scope="private") for method in CACHEABLE_METHODS},
    instructions=(
        "Uoink turns videos, playlists, and podcast episodes into local "
        "AI-ready corpora. Use the tools to capture, transcribe, publish, "
        "search, inspect, and analyze saved uoinks."
    ) + server._platform.capability_notice(),
)
# Uoink owns telemetry policy; SDK package presence must not enable tracing.
mcp.middleware.clear()


# --------------------------------------------------------------------------
# Python convenience wrappers retained for existing callers. Live tool metadata
# and dispatch are generated from TOOL_REGISTRY. scripts/check_mcp_inventory.py
# checks the complete inventory against docs, the bundle and receipt pins.
# --------------------------------------------------------------------------
def uoink_video(url: str, interval: int = 30) -> dict:
    return uoink_mcp_tools.call_tool("uoink_video", {"url": url, "interval": interval})


def uoink_playlist(url: str, interval: int = 30) -> dict:
    return uoink_mcp_tools.call_tool("uoink_playlist", {"url": url, "interval": interval})


def get_job_status(job_id: str) -> dict:
    return uoink_mcp_tools.call_tool("get_job_status", {"job_id": job_id})


def cancel_job(job_id: str) -> dict:
    return uoink_mcp_tools.call_tool("cancel_job", {"job_id": job_id})


def list_recent_uoinks(limit: int = 20) -> dict:
    return uoink_mcp_tools.call_tool("list_recent_uoinks", {"limit": limit})


def search_uoinks(query: str, limit: int = 10, match: str = "forgiving", mode: str = "auto") -> dict:
    return uoink_mcp_tools.call_tool("search_uoinks", {"query": query, "limit": limit, "match": match, "mode": mode})


def search_clips(
    query: str,
    limit: int = 20,
    video_id: str | None = None,
    channel: str | None = None,
    match: str = "forgiving",
    mode: str = "auto",
) -> dict:
    args: dict = {"query": query, "limit": limit, "match": match, "mode": mode}
    if video_id:
        args["video_id"] = video_id
    if channel:
        args["channel"] = channel
    return uoink_mcp_tools.call_tool("search_clips", args)


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


def get_uoink_corpus(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("get_uoink_corpus", {"slug": slug})


def analyze_comments(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("analyze_comments", {"slug": slug})


def classify_hook(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("classify_hook", {"slug": slug})


def get_taxonomy(
    channel: str | None = None,
    hook_type: str | None = None,
    limit: int = 50,
) -> dict:
    return uoink_mcp_tools.call_tool(
        "get_taxonomy",
        {"channel": channel, "hook_type": hook_type, "limit": limit},
    )


def get_citation_map(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("get_citation_map", {"slug": slug})


def get_uoink_health(slug: str) -> dict:
    return uoink_mcp_tools.call_tool("get_uoink_health", {"slug": slug})


def find_mentions(entity: str, limit: int = 50, match: str = "forgiving") -> dict:
    return uoink_mcp_tools.call_tool(
        "find_mentions", {"entity": entity, "limit": limit, "match": match}
    )


def get_transcript_reliability(video_id: str) -> dict:
    return uoink_mcp_tools.call_tool(
        "get_transcript_reliability", {"video_id": video_id}
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


def list_podcast_feeds(enabled_only: bool = False) -> dict:
    return uoink_mcp_tools.call_tool(
        "list_podcast_feeds", {"enabled_only": enabled_only}
    )


def remove_podcast_feed(feed_id: int) -> dict:
    return uoink_mcp_tools.call_tool("remove_podcast_feed", {"feed_id": feed_id})


def poll_podcast_feed(feed_id: int) -> dict:
    return uoink_mcp_tools.call_tool("poll_podcast_feed", {"feed_id": feed_id})


def list_podcast_episodes(
    feed_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict:
    return uoink_mcp_tools.call_tool(
        "list_podcast_episodes",
        {"feed_id": feed_id, "status": status, "limit": limit},
    )


def download_podcast_episode(episode_id: int) -> dict:
    return uoink_mcp_tools.call_tool(
        "download_podcast_episode", {"episode_id": episode_id}
    )


def get_whisperx_status() -> dict:
    return uoink_mcp_tools.call_tool("get_whisperx_status", {})


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


def episode_to_corpus(episode_id: int) -> dict:
    return uoink_mcp_tools.call_tool(
        "episode_to_corpus", {"episode_id": episode_id}
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
# The three read tools are advertised from TOOL_REGISTRY and appear in
# tools/list with the full registry; their execution is intercepted
# on the low-level server so the domain envelope is returned as text with
# isError set from the envelope, never wrapped in the SDK's "Error executing
# tool" string. Resources and prompts use low-level handlers on
# the owned public Server so the curated list,
# the five templates, the nine prompts and the JSON-RPC error codes are ours:
# -32602 invalid parameters, -32002 missing or deleted resource, -32603 any
# other refusal, each carrying the domain envelope in error.data. The SDK
# advertises resources {subscribe:false, listChanged:false} and prompts
# {listChanged:false} only because these handlers exist; no notification is
# ever emitted. The raw stdio decoder and the HTTP /tools/* route both
# reject duplicate JSON keys before handlers receive parsed objects. Every reader is request-scoped on the process-wide guard (2 active,
# 60 admissions per minute, 2 s deadline). Nothing here writes to stdout.
# --------------------------------------------------------------------------
def search_library(query: str, limit: int = 5, match: str = "forgiving", mode: str = "auto"):
    return uoink_mcp_tools.call_tool("search_library", {"query": query, "limit": limit, "match": match, "mode": mode})


def get_library_item(video_id: str | None = None, slug: str | None = None):
    args: dict = {}
    if video_id is not None:
        args["video_id"] = video_id
    if slug is not None:
        args["slug"] = slug
    return uoink_mcp_tools.call_tool("get_library_item", args)


def read_library_resource(uri: str):
    return uoink_mcp_tools.call_tool("read_library_resource", {"uri": uri})


def get_playbook_input(
    playbook: Literal["outlier-posts", "transcript-intel", "comment-mining",
                      "creator-teardown", "repurpose-pack"],
    arguments: dict,
) -> dict:
    return uoink_mcp_tools.call_tool("get_playbook_input", {
        "playbook": playbook, "arguments": arguments,
    })


def discover_candidates(
    mode: Literal["creator", "keyword"],
    platform: Literal["tiktok", "instagram", "youtube", "youtube_shorts"],
    handle: str | None = None, channel_id: str | None = None,
    query: str | None = None, pages: int = 1, confirm_credits: int | None = None,
    user_intent_token: str | None = None,
) -> dict:
    return uoink_mcp_tools.call_tool("discover_candidates", {
        k: v for k, v in locals().items() if v is not None})


def queue_discovered(run_id: str, keys: list[str], user_intent_token: str | None = None) -> dict:
    return uoink_mcp_tools.call_tool("queue_discovered", {
        k: v for k, v in locals().items() if v is not None})


# Phase 4 second increment (run AV-2): brief generation belongs to the client.
# get_library_brief_input is a read; publish_library_brief is a local write
# under DATA_ROOT/reach/briefs. Both are intercepted below like the three read
# tools, so the domain envelope is the tool text.
def get_library_brief_input(date: str, run_id: str):
    return uoink_mcp_tools.call_tool("get_library_brief_input", {"date": date, "run_id": run_id})


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


def _helper_running() -> bool:
    from uoink_agent_runtime import helper_running
    return helper_running(server)


def _call_stdio_registry(name, arguments):
    from uoink_agent_runtime import call_tool
    return call_tool(name, arguments, server, running=_helper_running)

def _register_phase4_stdio() -> None:
    """Register the Library budget hooks; missing safety plumbing fails startup."""
    try:
        import library_prompts
        import library_resources
        import research_playbooks
    except ImportError as exc:
        raise RuntimeError("Uoink MCP: required Library modules unavailable; repair the installation.") from exc
    try:
        from mcp import types as mcp_types
        from mcp.shared.exceptions import MCPError
    except ImportError as exc:  # pragma: no cover -- SDK reshaped
        raise RuntimeError("Uoink MCP: cannot register required Library handlers.") from exc
    low = mcp

    ResourceError = library_resources.ResourceError
    limits = library_resources.LIMITS

    def reader():
        # Request-scoped: storage is bound inside the first admitted operation
        # (existing storage only, never created or recovered), and the
        # deadline runs from that admission through serialization (AV-1r D1,
        # D7). Construction opens nothing.
        return library_resources.make_reader(server)

    def work_service(active_reader):
        # Resolve only after admission. A fresh read must not initialize the
        # mutating work service or replay its journal to inspect a preview.
        def resolve():
            from library_work import LibraryPreviewReader
            existing = getattr(active_reader.index, "_library_work_service", None)
            if existing is not None:
                return existing
            return LibraryPreviewReader(active_reader.index,
                clock=lambda: int(active_reader.wall_time() * 1000))
        return library_prompts.DeferredService(
            resolve)

    def mcp_error(exc, ctx) -> MCPError:
        data = exc.envelope()
        if exc.code == "invalid_request":
            code = -32602
        elif exc.code in ("resource_not_found", "resource_deleted"):
            code = -32602 if ctx.protocol_version == LATEST_MODERN_VERSION else -32002
            if ctx.protocol_version == LATEST_MODERN_VERSION:
                data["uri"] = _stdio_param(ctx.params, "uri")
        else:
            code = -32603
        return MCPError(code=code, message=exc.message, data=data)

    async def _phase4_list_templates(ctx, params):
        return mcp_types.ListResourceTemplatesResult(resource_templates=[
            mcp_types.ResourceTemplate(**template) for template in library_resources.TEMPLATES])

    async def _phase4_list_resources(ctx, params):
        try:
            active = reader()
            entries = active.list_resources()
            resources = []
            for entry in entries:
                fields = {"uri": entry["uri"], "name": entry["name"],
                          "description": entry.get("description"), "mime_type": entry.get("mimeType")}
                if isinstance(entry.get("size"), int):
                    fields["size"] = entry["size"]
                resources.append(mcp_types.Resource(**fields))
            # The same request's deadline covers this serialization (D1).
            active.assert_within_deadline()
        except ResourceError as exc:
            raise mcp_error(exc, ctx) from None
        return mcp_types.ListResourcesResult(resources=resources)

    async def _phase4_read_resource(ctx, params):
        uri = params.uri
        try:
            active = reader()
            result = active.read(str(uri))
            contents = [mcp_types.TextResourceContents(uri=item["uri"], text=item["text"], mime_type=item["mimeType"])
                        for item in result["contents"]]
            active.assert_within_deadline()
        except ResourceError as exc:
            raise mcp_error(exc, ctx) from None
        return mcp_types.ReadResourceResult(contents=contents)

    async def _phase4_list_prompts(ctx, params):
        return mcp_types.ListPromptsResult(prompts=[mcp_types.Prompt(
            name=prompt["name"], description=prompt["description"],
            arguments=[mcp_types.PromptArgument(**argument) for argument in prompt["arguments"]],
        ) for prompt in (*library_prompts.PROMPTS, *research_playbooks.PLAYBOOKS)])

    async def _phase4_get_prompt(ctx, params):
        name, arguments = params.name, params.arguments
        try:
            active = reader()
            if name in {p["name"] for p in research_playbooks.PLAYBOOKS}:
                result = research_playbooks.get_prompt(active, name, arguments)
            else:
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
            raise mcp_error(exc, ctx) from None
        except Exception:
            raise mcp_error(ResourceError("internal_error"), ctx) from None
        return rendered

    def tool_result(name, arguments):
        active = reader()
        from uoink_agent_runtime import dispatch_search
        envelope = dispatch_search(name, arguments, server, lambda: library_resources.call_tool(
            name, arguments if arguments is not None else {}, active, client_identity="stdio"), running=_helper_running)
        if name == "publish_library_brief" and not server._platform.library_mirror_capability()["available"]:
            envelope["capabilities"] = server._platform.platform_capabilities()
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
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)], is_error=is_error)

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
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=text)], is_error=True)

        try:
            with library_analysis.adapter_admission():
                envelope = library_analysis.get_library_activity(args)
                if not server._platform.library_mirror_capability()["available"]:
                    envelope["capabilities"] = server._platform.platform_capabilities()
                if envelope.get("ok") is not True:
                    text = library_resources.render_tool_text(envelope)
                    if time.monotonic() - start_time > library_analysis.SERVICE_DEADLINE_SEC:
                        return _deadline_result()
                    return mcp_types.CallToolResult(
                        content=[mcp_types.TextContent(type="text", text=text)], is_error=True)

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
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=text)], is_error=is_error)
        except ResourceError as exc:
            envelope = library_analysis.error_envelope(
                exc.code, exc.message, details=exc.details or None)
            text, is_error = library_resources.render_tool_text(envelope), True
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=text)], is_error=is_error)

    def bounded_registry_result(name, arguments):
        # Bounded registry reads: the domain envelope is the tool text, isError
        # mirrors ok, and the actual wrapped response is measured against
        # the shared transport budget before it leaves the process. The
        # registry handler already admitted the request on the process
        # guard and charged its deadline; nothing is admitted twice here.
        args = arguments if arguments is not None else {}
        if not isinstance(args, dict):
            args = {}
        envelope = uoink_mcp_tools.call_tool(name, args)
        if not isinstance(envelope, dict) or "ok" not in envelope:
            envelope = ResourceError("internal_error").envelope()
        text = library_resources.render_tool_text(envelope)
        is_error = envelope.get("ok") is not True
        payload = {"content": [{"type": "text", "text": text}], "isError": is_error}
        if library_resources.wire_bytes(payload) + 256 > limits["max_response_bytes"]:
            envelope = ResourceError("resource_too_large", details={
                "what": name, "next_step": "read_library_resource"}).envelope()
            text, is_error = library_resources.render_tool_text(envelope), True
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)], is_error=is_error)

    async def _phase4_call_tool(ctx, params):
        name = params.name
        if name not in uoink_mcp_tools.stdio_tool_names(STDIO_TOOLSET):
            envelope = {"ok": False, "error": "tool not found"}
        elif name in library_resources.TOOL_NAMES:
            return tool_result(name, params.arguments)
        elif name == "get_library_activity":
            return activity_result(params.arguments)
        elif name in ("export_cited_range", "get_playbook_input"):
            return bounded_registry_result(name, params.arguments)
        else:
            return await mcp.call_tool(name, params.arguments)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=json.dumps(
                envelope, ensure_ascii=False, allow_nan=False))],
            is_error=envelope.get("ok") is not True)

    async def _phase4_list_tools(ctx, params):
        return mcp_types.ListToolsResult(tools=await mcp.list_tools())

    def scoped(handler):
        async def handle(ctx, params):
            state = _request_state(ctx.request_id)
            if state is not None:
                state.protocol_version = ctx.protocol_version
            token = library_resources.bind_transport_scope(ctx.request_id)
            request_token = _active_stdio_request.set(state)
            try:
                if state is not None and state.cancelled:
                    raise MCPError(code=-32600, message="Request cancelled")
                scope = library_resources.current_transport_scope()
                if scope is not None and scope.refusal is not None:
                    response = _stdio_refusal_server_result(ctx, scope.refusal)
                    if isinstance(response, mcp_types.ErrorData):
                        raise MCPError.from_error_data(response)
                    return response
                return await handler(ctx, params)
            finally:
                _active_stdio_request.reset(request_token)
                library_resources.reset_bound_transport_scope(token)
        return handle

    for method, params_type, handler in (
        ("tools/list", mcp_types.PaginatedRequestParams, _phase4_list_tools),
        ("tools/call", mcp_types.CallToolRequestParams, _phase4_call_tool),
        ("resources/templates/list", mcp_types.PaginatedRequestParams, _phase4_list_templates),
        ("resources/list", mcp_types.PaginatedRequestParams, _phase4_list_resources),
        ("resources/read", mcp_types.ReadResourceRequestParams, _phase4_read_resource),
        ("prompts/list", mcp_types.PaginatedRequestParams, _phase4_list_prompts),
        ("prompts/get", mcp_types.GetPromptRequestParams, _phase4_get_prompt),
    ):
        low.add_request_handler(method, params_type, scoped(handler))


def _stdio_param(params, key: str):
    if params is None:
        return None
    if isinstance(params, dict):
        return params.get(key)
    return getattr(params, key, None)


# The shipped writer owns admission through write and flush. The alternate
# public SDK writer can settle only at its concrete model_dump_json boundary.
_bounded_stdio_writer_depth = contextvars.ContextVar("uoink_bounded_stdio_writer_depth", default=0)
_stdio_requests = contextvars.ContextVar("uoink_stdio_requests", default=None)
_active_stdio_request = contextvars.ContextVar("uoink_active_stdio_request", default=None)
_stdio_usage_connection = contextvars.ContextVar("uoink_stdio_usage_connection", default=None)


def _count_inbound_usage(message):
    """Count inbound attempts before admission, as in SDK 1, without affecting RPCs."""
    try:
        connection = _stdio_usage_connection.get()
        if connection is not None and not connection.get("client_counted"):
            meta = _stdio_param(message.params, "_meta")
            legacy = message.method == "initialize"
            modern = _stdio_param(meta, mcp_types.PROTOCOL_VERSION_META_KEY) == LATEST_MODERN_VERSION
            if legacy or modern:
                client = (_stdio_param(message.params, "clientInfo") if legacy else
                          _stdio_param(meta, mcp_types.CLIENT_INFO_META_KEY))
                connection["client_counted"] = True
                uoink_usage.count("mcp_clients", _stdio_param(client, "name"))
    except Exception:
        pass  # Usage failures must never change a protocol response.
    try:
        if message.method == "tools/call":
            name = _stdio_param(message.params, "name")
            if name:
                uoink_usage.mcp_call(name, "stdio")
    except Exception:
        pass


class _StdioRequest:
    def __init__(self, message, scope):
        self.message = message
        self.method = message.method
        self.scope = scope
        self.protocol_version = None
        self.cancelled = False
        self.settled = False
        self.output_started = False

    def settle(self):
        import library_resources
        if self.settled:
            return
        self.settled = True
        if self.scope is not None:
            if library_resources.transport_scope(self.message.id) is self.scope:
                library_resources.finish_transport_request(self.message.id)
            else:
                self.scope.release()
        requests = _stdio_requests.get()
        key = coerce_request_id(self.message.id)
        if requests is not None and requests.get(key) is self:
            requests.pop(key)


def _request_state(request_id):
    return (_stdio_requests.get() or {}).get(coerce_request_id(request_id))


def _release_stdio_requests():
    for state in list((_stdio_requests.get() or {}).values()):
        state.settle()


def _begin_inbound_transport_scope(message):
    """Admit at input, before the runner can queue validation or handler work."""
    import library_resources
    if isinstance(message, mcp_types.JSONRPCNotification):
        if message.method == "notifications/cancelled":
            request_id = _stdio_param(message.params, "requestId")
            if type(request_id) not in (int, str):
                return None
            state = _request_state(request_id)
            if state is not None and not state.output_started:
                state.cancelled = True
                library_resources.mark_transport_cancelled(state.message.id)
        return None
    if not isinstance(message, mcp_types.JSONRPCRequest):
        return None
    requests = _stdio_requests.get()
    if requests is None:
        requests = {}
        _stdio_requests.set(requests)
    key = coerce_request_id(message.id)
    previous = requests.get(key)
    if previous is not None:
        return previous
    _count_inbound_usage(message)
    name = _stdio_param(message.params, "name") if message.method == "tools/call" else None
    if not isinstance(name, str):
        name = None  # Let SDK parameter validation refuse malformed names.
    scope = None
    if library_resources.is_budgeted_stdio_request(message.method, name):
        scope = library_resources.begin_transport_request(message.id, message.method, name)
    state = _StdioRequest(message, scope)
    requests[key] = state
    return state


def _prepare_inbound(session_message):
    from dataclasses import replace
    from mcp.shared.message import SessionMessage, ServerMessageMetadata
    if not isinstance(session_message, SessionMessage):
        return session_message
    state = _begin_inbound_transport_scope(session_message.message)
    if state is None:
        return session_message
    metadata = session_message.metadata
    if metadata is None:
        metadata = ServerMessageMetadata()
    if not isinstance(metadata, ServerMessageMetadata):
        raise TypeError("Expected server transport metadata")
    previous = metadata.on_request_unanswered

    async def unanswered():
        try:
            if previous is not None:
                await previous()
        finally:
            state.settle()

    return SessionMessage(session_message.message, replace(metadata, on_request_unanswered=unanswered))


class _InboundScopeStream:
    def __init__(self, stream):
        self._stream = stream

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration

    async def receive(self):
        return _prepare_inbound(await self._stream.receive())

    async def aclose(self):
        await self._stream.aclose()


def _check_serialized_frame(message, text, scope, state):
    """Measure the SDK's final, version-shaped frame, not a handler estimate."""
    request_id = getattr(message, "id", None)
    if scope is not None and not scope.cancel_requested and not _stdio_jsonrpc_is_error(message):
        code = None
        if scope.expired():
            code = "deadline_exceeded"
        elif len(text.encode("utf-8")) > _stdio_completed_frame_cap():
            code = "resource_too_large"
        if code:
            text = _stdio_budget_refusal_message(scope, request_id, code, state=state).model_dump_json(
                by_alias=True, exclude_none=True)
    return _stdio_enforce_completed_frame(
        text, request_id, scope, state=state,
        tool_inventory=state is not None and state.method == "tools/list")


class _SdkOutboundSettlement:
    def model_dump_json(self, *args, **kwargs):
        state = self._uoink_frame_state
        scope = state.scope if state is not None else None
        kwargs["by_alias"] = True
        try:
            text = super().model_dump_json(*args, **kwargs)
            return _check_serialized_frame(self, text, scope, state)
        finally:
            if state is not None:
                state.settle()


class _SdkOutboundResponse(_SdkOutboundSettlement, mcp_types.JSONRPCResponse):
    pass


class _SdkOutboundError(_SdkOutboundSettlement, mcp_types.JSONRPCError):
    pass


class _SdkSettlementStream:
    """Attach serialization ownership only when a frame reaches the writer."""

    def __init__(self, stream):
        self._stream = stream

    async def send(self, session_message):
        from mcp.shared.message import SessionMessage
        message = session_message.message
        if isinstance(message, (mcp_types.JSONRPCResponse, mcp_types.JSONRPCError)):
            state = _request_state(message.id)
            if state is not None and state.cancelled:
                state.settle()
                return
            if isinstance(message, mcp_types.JSONRPCResponse):
                owned = _SdkOutboundResponse(jsonrpc="2.0", id=message.id, result=message.result)
            else:
                owned = _SdkOutboundError(jsonrpc="2.0", id=message.id, error=message.error)
            object.__setattr__(owned, "_uoink_frame_state", state)
            session_message = SessionMessage(owned, metadata=session_message.metadata)
        await self._stream.send(session_message)

    async def aclose(self):
        await self._stream.aclose()

    async def __aenter__(self):
        await self._stream.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self._stream.__aexit__(*args)


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
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)], is_error=True)
    code = -32602 if exc.code == "invalid_request" else (
        -32002 if exc.code in ("resource_not_found", "resource_deleted") else -32603)
    return mcp_types.ErrorData(code=code, message=exc.message, data=exc.envelope())


def _stdio_jsonrpc_is_error(root) -> bool:
    if isinstance(root, mcp_types.JSONRPCError):
        return True
    if isinstance(root, mcp_types.JSONRPCResponse) and isinstance(root.result, dict):
        return root.result.get("isError") is True
    return False


def _stdio_domain_tool_message(request_id, envelope, *, state=None):
    import library_resources
    text = library_resources.render_tool_text(envelope)
    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)], is_error=True)
    dumped = result.model_dump(by_alias=True, mode="json", exclude_none=True)
    if state is None:
        state = _request_state(request_id)
    if state is not None and state.protocol_version == LATEST_MODERN_VERSION:
        dumped["resultType"] = "complete"
        dumped["_meta"] = {mcp_types.SERVER_INFO_META_KEY: mcp.server_info_stamp}
    else:
        dumped.pop("resultType", None)
    return mcp_types.JSONRPCResponse(jsonrpc="2.0", id=request_id, result=dumped)


def _stdio_domain_rpc_error_message(request_id, exc):
    code = -32602 if exc.code == "invalid_request" else (
        -32002 if exc.code in ("resource_not_found", "resource_deleted") else -32603)
    return mcp_types.JSONRPCError(
        jsonrpc="2.0",
        id=request_id,
        error=mcp_types.ErrorData(code=code, message=exc.message, data=exc.envelope()),
    )


def _stdio_budget_refusal_message(scope, request_id, code: str, *, state=None):
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
        return _stdio_domain_tool_message(request_id, envelope, state=state)
    return _stdio_domain_rpc_error_message(request_id, exc)


_STDIO_PROTOCOL_REJECTION_CODE = -32600
_STDIO_PROTOCOL_REJECTION_MESSAGE = "Inbound request exceeds protocol limits"


def _stdio_completed_frame_cap() -> int:
    import library_resources
    return int(library_resources.LIMITS["max_response_bytes"])


def _stdio_protocol_rejection_frame(request_id=None, *, message=_STDIO_PROTOCOL_REJECTION_MESSAGE) -> str:
    return mcp_types.JSONRPCError(
        jsonrpc="2.0", id=request_id,
        error=mcp_types.ErrorData(code=_STDIO_PROTOCOL_REJECTION_CODE,
                                 message=message),
    ).model_dump_json(by_alias=True, exclude_none=False, exclude={"error": {"data"}})


def _stdio_parse_rejection_frame() -> str:
    return mcp_types.JSONRPCError(
        jsonrpc="2.0", id=None,
        error=mcp_types.ErrorData(code=-32700, message="Invalid JSON-RPC message"),
    ).model_dump_json(by_alias=True, exclude_none=False, exclude={"error": {"data"}})


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
    root = message
    if isinstance(root, mcp_types.JSONRPCNotification):
        return None
    request_id = getattr(root, "id", None)
    if _stdio_request_id_fits(request_id, _stdio_completed_frame_cap()):
        return None
    return _stdio_protocol_rejection_frame(None)


def _stdio_enforce_completed_frame(text: str, request_id, scope, *, tool_inventory=False, state=None) -> str:
    """Bound success, typed errors, and replacement refusals to the wire cap."""
    import library_resources
    # The full registry's exact JSON schemas exceed the Library data cap.
    # Only server-generated tools/list metadata gets this larger bound;
    # requests and tool/resource results keep their existing 64 KiB limit.
    cap = 256 * 1024 if tool_inventory and scope is None else _stdio_completed_frame_cap()
    if len(text.encode("utf-8")) <= cap:
        return text
    if request_id is not None and _stdio_request_id_fits(request_id, cap):
        if scope is not None:
            repl = _stdio_budget_refusal_message(
                scope, request_id, "resource_too_large", state=state
            ).model_dump_json(by_alias=True, exclude_none=True)
        else:
            repl = _stdio_protocol_rejection_frame(request_id)
        if len(repl.encode("utf-8")) <= cap:
            return repl
    return _stdio_protocol_rejection_frame(None)


async def _deliver_bounded_outbound(session_message, stdout) -> None:
    """Hold the exact admission through concrete serialization, write and flush."""
    import library_resources
    message = session_message.message
    request_id = getattr(message, "id", None)
    state = _request_state(request_id)
    scope = state.scope if state is not None else library_resources.transport_scope(request_id)
    try:
        if (state is not None and state.cancelled) or (scope is not None and scope.cancel_requested):
            return
        text = message.model_dump_json(by_alias=True, exclude_none=True)
        text = _check_serialized_frame(message, text, scope, state)
        # Let input already waiting on the event loop cancel prepared output.
        # Once write starts bytes may have escaped, so cancellation is too late.
        await anyio.lowlevel.checkpoint()
        if (state is not None and state.cancelled) or (scope is not None and scope.cancel_requested):
            return
        if state is not None:
            state.output_started = True
        await stdout.write(text + "\n")
        await stdout.flush()
    finally:
        if state is not None:
            state.settle()
        elif scope is not None:
            library_resources.finish_transport_request(request_id)


def _stdio_wire_streams(stdin, stdout):
    """Keep protocol descriptors private from Python, native code and children."""
    from contextlib import contextmanager
    from io import TextIOWrapper
    import queue
    import threading

    def rebind(fd):
        if sys.platform == "win32":
            import ctypes
            import msvcrt
            from ctypes import wintypes
            set_handle = ctypes.WinDLL("kernel32", use_last_error=True).SetStdHandle
            set_handle.argtypes = (wintypes.DWORD, wintypes.HANDLE)
            set_handle.restype = wintypes.BOOL
            if not set_handle(-10 if fd == 0 else -11, msvcrt.get_osfhandle(fd)):
                raise ctypes.WinError(ctypes.get_last_error())

    class Input:
        def __init__(self, file):
            self.file = file
            self.lock = threading.Lock()
            self.reading = False
            self.closed = False
            self.pending = queue.Queue()
            self.worker = threading.Thread(target=self.run, name="uoink-stdio-input", daemon=True)
            self.worker.start()

        def run(self):
            while (item := self.pending.get()) is not None:
                loop, future = item
                try:
                    value, error = self.readline(), None
                except Exception as exc:
                    value, error = None, exc

                def complete(value=value, error=error, future=future):
                    if not future.done():
                        if error is not None:
                            future.set_exception(error)
                        else:
                            future.set_result(value)
                try:
                    loop.call_soon_threadsafe(complete)
                except RuntimeError:  # The writer failed and the loop closed.
                    return

        def readline(self):
            with self.lock:
                if self.closed:
                    return ""
                self.reading = True
            try:
                return self.file.readline()
            finally:
                with self.lock:
                    self.reading = False
                    if self.closed:
                        self.file.close()

        def close(self):
            # A failed writer must not wait for a peer that keeps stdin open.
            # An abandoned reader owns its descriptor until readline returns.
            with self.lock:
                self.closed = True
                if not self.reading:
                    self.file.close()
            self.pending.put(None)

        def __aiter__(self):
            return self

        async def __anext__(self):
            # AnyIO's worker threads are non-daemon. An abandoned pipe read
            # would still hold interpreter shutdown when the output peer dies.
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self.pending.put((loop, future))
            line = await future
            if not line:
                raise StopAsyncIteration
            return line

    @contextmanager
    def streams():
        saved = []
        owned_input = owned_output = None
        try:
            for fd, explicit in ((0, stdin), (1, stdout)):
                if explicit is not None:
                    continue
                if fd == 1:
                    sys.stdout.flush()
                private = os.dup(fd)
                os.set_inheritable(private, False)
                saved.append((fd, private))
                diversion = os.open(os.devnull, os.O_RDONLY) if fd == 0 else os.dup(2)
                try:
                    os.dup2(diversion, fd)
                    rebind(fd)
                finally:
                    os.close(diversion)
                if fd == 0:
                    owned_input = Input(TextIOWrapper(os.fdopen(os.dup(private), "rb"),
                                                     encoding="utf-8", errors="replace"))
                else:
                    owned_output = TextIOWrapper(os.fdopen(os.dup(private), "wb"), encoding="utf-8")
            yield stdin if stdin is not None else owned_input, (
                stdout if stdout is not None else anyio.wrap_file(owned_output))
        finally:
            # Flush stray buffered print output while stdout still points at stderr.
            if any(fd == 1 for fd, _ in saved):
                sys.stdout.flush()
            for fd, private in reversed(saved):
                try:
                    os.dup2(private, fd)
                    rebind(fd)
                finally:
                    os.close(private)
            if owned_input is not None:
                owned_input.close()
            if owned_output is not None:
                try:
                    owned_output.close()
                except OSError:
                    # The original write/flush failure already owns shutdown.
                    pass

    return streams()


def bounded_stdio_server(stdin=None, stdout=None):
    """Application stdio transport: SDK messages, product-owned write lifetime."""
    from contextlib import asynccontextmanager
    from mcp.shared.message import SessionMessage

    @asynccontextmanager
    async def transport():
        streams = _stdio_wire_streams(stdin, stdout)
        input_file, output_file = streams.__enter__()
        depth = _bounded_stdio_writer_depth.set(_bounded_stdio_writer_depth.get() + 1)
        requests = _stdio_requests.set({})
        usage_token = _stdio_usage_connection.set({})
        reads_send, reads = anyio.create_memory_object_stream(0)
        writes, writes_receive = anyio.create_memory_object_stream(0)

        async def stdin_reader():
            async with reads_send:
                async for line in input_file:
                    try:
                        message = parse_stdio_message(line)
                    except _InvalidStdioRequest as exc:
                        await writes.send(_stdio_protocol_rejection_frame(None, message=str(exc)))
                        continue
                    except (ValueError, TypeError, RecursionError):
                        # SDK 2 logs/drops exception objects. Refuse here so the
                        # peer receives an explicit bounded error and can recover.
                        await writes.send(_stdio_inbound_line_rejection(line) or _stdio_parse_rejection_frame())
                        continue
                    if message is None:
                        continue
                    refusal = _stdio_request_id_rejection(message)
                    if isinstance(message, mcp_types.JSONRPCRequest) and _request_state(message.id) is not None:
                        refusal = _stdio_protocol_rejection_frame(None, message="Duplicate in-flight request ID")
                    if refusal is not None:
                        await writes.send(refusal)
                        continue
                    await reads_send.send(_prepare_inbound(SessionMessage(message)))

        async def stdout_writer():
            async with writes_receive:
                async for item in writes_receive:
                    if isinstance(item, str):
                        await output_file.write(item + "\n")
                        await output_file.flush()
                    else:
                        await _deliver_bounded_outbound(item, output_file)

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(stdin_reader)
                group.start_soon(stdout_writer)
                yield reads, writes
                # Server.run closes writes; let queued output flush before exit.
        finally:
            _release_stdio_requests()
            _stdio_requests.reset(requests)
            _stdio_usage_connection.reset(usage_token)
            _bounded_stdio_writer_depth.reset(depth)
            streams.__exit__(None, None, None)

    return transport()


async def run_bounded_stdio_async() -> None:
    """Both script names enter the SDK's native dual-era runner here."""
    async with bounded_stdio_server() as (reads, writes):
        await mcp.run(reads, writes, mcp.create_initialization_options())


def main():
    argv = sys.argv[1:]
    if "--doctor" in argv or "--migrate-dry-run" in argv:
        raise SystemExit(server.run_cli(argv))
    anyio.run(run_bounded_stdio_async)


_register_phase4_stdio()


if __name__ == "__main__":
    main()
