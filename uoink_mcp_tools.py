"""Shared Uoink MCP tool registry.

Both transports use this module:

- uoink_mcp.py wraps it with the official MCP Python SDK over stdio.
- server.py wraps it with authenticated JSON-RPC HTTP endpoints.

The registry intentionally owns no extraction business logic. It binds to the
loaded server module and calls the same helpers used by Uoink's v1/v2 HTTP API.

v2.1 rename: the six brand-carrying tools were renamed yoink_* -> uoink_*.
``call_tool`` accepts the legacy names as deprecated aliases (resolved to the
canonical name + a one-shot DeprecationWarning to stderr) through Uoink v2.5;
they are removed in v3. See ``MCP_TOOL_ALIASES`` / ``_warn_deprecated_tool``.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


_backend = None

# Deprecated (Yoink-era) tool name -> canonical (Uoink) name. Old names keep
# working through Uoink v2.5 and are removed in v3. The 7 brand-neutral tools
# (get_job_status, cancel_job, analyze_comments, classify_hook, get_taxonomy,
# get_citation_map, find_mentions) are unchanged and absent here.
MCP_TOOL_ALIASES: dict[str, str] = {
    "yoink_video": "uoink_video",
    "yoink_playlist": "uoink_playlist",
    "list_recent_yoinks": "list_recent_uoinks",
    "search_yoinks": "search_uoinks",
    "get_yoink_corpus": "get_uoink_corpus",
    "get_yoink_health": "get_uoink_health",
}

# Dedupe so an agent calling a deprecated tool in a loop emits the warning
# once per process per tool rather than spamming stderr.
_warned_aliases: set[str] = set()
_warned_lock = threading.Lock()


def _warn_deprecated_tool(old_name: str, new_name: str) -> None:
    """Emit a one-shot DeprecationWarning to stderr when a legacy tool name is
    called. stdout is the JSON-RPC transport for the stdio MCP server, so the
    warning must go to stderr only."""
    with _warned_lock:
        if old_name in _warned_aliases:
            return
        _warned_aliases.add(old_name)
    message = (
        f"DeprecationWarning: MCP tool `{old_name}` is renamed to `{new_name}`.\n"
        f"The old name still works through Uoink v2.5 and is removed in v3.\n"
        f"Update your agent config to `{new_name}`. "
        f"Details: https://uoink.video/docs/v2-mcp"
    )
    # Raise a real DeprecationWarning (for programmatic warning filters) and
    # also write the message to stderr unconditionally, since DeprecationWarning
    # is hidden by Python's default filters outside __main__.
    warnings.warn(
        f"MCP tool `{old_name}` is renamed to `{new_name}`; "
        f"use `{new_name}` (removed in Uoink v3).",
        DeprecationWarning,
        stacklevel=3,
    )
    print(message, file=sys.stderr, flush=True)


def bind_backend(backend_module) -> None:
    global _backend
    _backend = backend_module


def _b():
    if _backend is None:
        raise RuntimeError("Uoink MCP backend is not bound")
    return _backend


class RateLimitExceeded(Exception):
    pass


class _RateLimiter:
    def __init__(self, max_calls: int, window_sec: float = 60.0):
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._lock = threading.Lock()
        self._calls: list[float] = []

    def check(self) -> None:
        now = time.monotonic()
        cutoff = now - self.window_sec
        with self._lock:
            kept = [t for t in self._calls if t > cutoff]
            if len(kept) >= self.max_calls:
                self._calls[:] = kept
                raise RateLimitExceeded(
                    f"rate limit exceeded: max {self.max_calls}/minute"
                )
            kept.append(now)
            self._calls[:] = kept


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    rate_limiter: _RateLimiter | None = None


def _ok(**fields) -> dict[str, Any]:
    return {"ok": True, **fields}


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def _limit_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = default
    return max(low, min(high, out))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _sidecar_path(folder: Path) -> Path:
    return folder / f"{folder.name}.json"


def _metadata_path(folder: Path) -> Path:
    return folder / "metadata.json"


def _read_sidecar(folder: Path) -> dict[str, Any]:
    return _read_json(_sidecar_path(folder))


def _read_metadata(folder: Path) -> dict[str, Any]:
    return _read_json(_metadata_path(folder))


def _iter_yoink_folders():
    """Walk DESKTOP_ROOT for yoink folders. Sprint 19.6 / Fix 5: skip the
    _yoink-trash/ subtree so a slug whose folder was just moved to trash
    does not resolve via the disk fallback in _find_yoink. Parity with
    server.py's _iter_corpus_folders, which had this guard already."""
    b = _b()
    root = b.DESKTOP_ROOT
    if not root.exists():
        return
    trash = root / "_yoink-trash"
    for folder in root.rglob("*"):
        if not folder.is_dir():
            continue
        if folder == trash or trash in folder.parents:
            continue
        corpus = b._resolve_corpus_path(folder)
        if corpus is not None:
            yield folder, corpus


def _yoink_summary(folder: Path, corpus: Path) -> dict[str, Any]:
    sidecar = _read_sidecar(folder)
    metadata = _read_metadata(folder)
    title = (
        sidecar.get("title")
        or metadata.get("title")
        or folder.name.replace("-", " ").title()
    )
    yoinked_at = sidecar.get("yoinked_at")
    if not yoinked_at:
        yoinked_at = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(corpus.stat().st_mtime)
        )
    return {
        "slug": folder.name,
        "title": title,
        "folder": str(folder),
        "yoinked_at": yoinked_at,
        "_mtime": corpus.stat().st_mtime,
        "_corpus": corpus,
    }


def _find_yoink(slug: str) -> tuple[Path, Path] | tuple[None, None]:
    """Resolve a yoink slug to (folder, corpus_path).

    Sprint 19.6 / Fix 5: the index is queried first (O(1) seek by slug),
    then -- only on a miss -- the pre-Sprint-19.6 disk-walk fallback runs
    so a corpus that exists on disk but has not been backfilled yet
    (or a folder dropped in by hand) still resolves. Every MCP tool that
    takes a slug benefits: get_yoink_corpus, get_citation_map,
    get_yoink_health, analyze_comments, classify_hook."""
    if not isinstance(slug, str) or not re.match(r"^[A-Za-z0-9_-]{1,160}$", slug):
        return None, None
    # Fast path: index lookup. get_by_slug filters deleted_at IS NULL so a
    # trashed yoink won't resolve here.
    try:
        row = _b()._get_index().get_by_slug(slug)
    except Exception:
        row = None
    if row:
        corpus_path = row.get("corpus_path") or ""
        if corpus_path:
            corpus = Path(corpus_path)
            if corpus.is_file():
                return corpus.parent, corpus
        # Indexed row missing on disk (folder moved/deleted outside the
        # extension) -- fall through to the walk so we don't return a
        # broken pointer.
    matches = []
    for folder, corpus in _iter_yoink_folders() or []:
        if folder.name == slug:
            matches.append((corpus.stat().st_mtime, folder, corpus))
    if not matches:
        return None, None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1], matches[0][2]


def _saved_key() -> str | None:
    return _b()._saved_anthropic_key()


def _comments_for_folder(folder: Path) -> list[dict[str, Any]]:
    comments = _read_sidecar(folder).get("comments")
    return comments if isinstance(comments, list) else []


def _hook_context_for_folder(folder: Path) -> dict[str, Any]:
    sidecar = _read_sidecar(folder)
    metadata = _read_metadata(folder)
    transcript = " ".join(
        str(item.get("text") or "")
        for item in (sidecar.get("transcript") or [])
        if isinstance(item, dict)
    )
    comments = _comments_for_folder(folder)
    top_comment = ""
    if comments and isinstance(comments[0], dict):
        top_comment = str(comments[0].get("text") or "")
    return {
        "video_id": sidecar.get("video_id") or metadata.get("id") or "",
        "title": sidecar.get("title") or metadata.get("title") or "",
        "description": metadata.get("description") or "",
        "channel": sidecar.get("channel") or metadata.get("channel") or metadata.get("uploader") or "",
        "transcript": transcript,
        "top_comment": top_comment,
    }


def uoink_video(args: dict[str, Any]) -> dict[str, Any]:
    b = _b()
    raw_url = args.get("url")
    if not isinstance(raw_url, str):
        return _err("url required")
    url = b._normalize_youtube_url(raw_url.strip())
    if not url:
        return _err("URL must be a youtube.com or youtu.be video link")
    interval = _limit_int(args.get("interval"), default=30, low=5, high=300)

    b.DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
    started_at = b._now_iso()
    title = None
    folder = None
    with b._extract_lock:
        try:
            metadata = b._fetch_metadata(url)
            title = metadata.get("title") or "Untitled"
            topic = b._classify_topic(metadata)
            folder = (
                b.DESKTOP_ROOT
                / b._topic_folder_name(topic)
                / (b.slugify(title) or "video")
            )
            result = b._run_extraction(url, interval, folder, metadata=metadata, topic=topic)
        except BaseException as e:
            msg = b.friendly_error(e)
            b._record_single_extract_job(
                url,
                started_at,
                error=msg,
                title=title,
                folder=folder,
            )
            return _err(msg)

    folder_path = Path(result["folder"])
    b._record_single_extract_job(url, started_at, result=result)
    screenshots = [
        str(p) for p in sorted((folder_path / "screenshots").glob("shot_*.jpg"))
    ]
    return _ok(
        slug=folder_path.name,
        folder=str(folder_path),
        corpus_md=result.get("yoink_md") or "",
        screenshots=screenshots,
    )


def uoink_playlist(args: dict[str, Any]) -> dict[str, Any]:
    b = _b()
    raw_url = args.get("url")
    if not isinstance(raw_url, str):
        return _err("playlist URL invalid")
    url = b._normalize_playlist_url(raw_url.strip())
    if not url:
        return _err("playlist URL invalid")
    interval = _limit_int(args.get("interval"), default=30, low=5, high=300)
    playlist, error, _status = b._fetch_playlist_preview(url)
    if error:
        return _err(error)
    job_id, _job = b._create_playlist_job(playlist, interval)
    return _ok(job_id=job_id)


def get_job_status(args: dict[str, Any]) -> dict[str, Any]:
    b = _b()
    job_id = args.get("job_id")
    if not isinstance(job_id, str) or not b._is_valid_job_id(job_id):
        return _err("job id invalid")
    job = b._get_public_job(job_id)
    if not job:
        return _err("job not found")
    return _ok(job=job)


def cancel_job(args: dict[str, Any]) -> dict[str, Any]:
    b = _b()
    job_id = args.get("job_id")
    if not isinstance(job_id, str) or not b._is_valid_job_id(job_id):
        return _err("job id invalid")
    job, error, _status = b._cancel_playlist_job(job_id)
    if error:
        return _err(error)
    return _ok(job=job)


def list_recent_uoinks(args: dict[str, Any]) -> dict[str, Any]:
    # Sprint 15: reads the SQLite library index instead of walking the
    # whole corpus tree on disk. Return shape unchanged.
    limit = _limit_int(args.get("limit"), default=20, low=1, high=100)
    yoinks = []
    for r in _b()._get_index().list_recent(limit):
        sidecar_path = r.get("sidecar_path") or ""
        yoinks.append({
            "slug": r.get("slug"),
            "title": r.get("title"),
            "folder": str(Path(sidecar_path).parent) if sidecar_path else None,
            "yoinked_at": r.get("yoinked_at"),
        })
    return _ok(yoinks=yoinks)


def search_uoinks(args: dict[str, Any]) -> dict[str, Any]:
    # Sprint 15: FTS5 keyword search via the library index instead of
    # read_text()-ing every corpus file. Return shape unchanged
    # ({slug, title, snippet, score}); optional channel / hook_type filters.
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return _err("query required")
    limit = _limit_int(args.get("limit"), default=10, low=1, high=50)
    channel = args.get("channel")
    channel = channel.strip() if isinstance(channel, str) and channel.strip() else None
    hook_type = args.get("hook_type")
    hook_type = hook_type.strip() if isinstance(hook_type, str) and hook_type.strip() else None
    rows = _b()._get_index().search(query, limit, channel=channel, hook_type=hook_type)
    results = []
    for r in rows:
        score = r.get("_score")
        results.append({
            "slug": r.get("slug"),
            "title": r.get("title"),
            "snippet": (r.get("_snippet") or "").strip(),
            # FTS5 bm25 is lower-is-better; negate so a higher score means a
            # better match, matching the old term-count score's direction.
            "score": round(-score, 4) if isinstance(score, (int, float)) else 0.0,
        })
    return _ok(results=results)


def get_uoink_corpus(args: dict[str, Any]) -> dict[str, Any]:
    slug = args.get("slug")
    folder, corpus = _find_yoink(slug)
    if not folder or not corpus:
        return _err("yoink not found")
    try:
        md = corpus.read_text(encoding="utf-8")
    except OSError as e:
        return _err(f"corpus read failed: {e}")
    sidecar = _read_sidecar(folder)
    video_id = sidecar.get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        video_id = None
    video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else None
    # Sprint 15: include the citation map alongside the markdown. Optional
    # field -- markdown-only consumers are unaffected.
    citations: list[dict[str, Any]] = []
    if video_id:
        try:
            citations = _b()._get_index().get_citations(video_id)
        except Exception:
            citations = []
    return _ok(
        corpus_md=md,
        folder=str(folder),
        video_id=video_id,
        video_url=video_url,
        citations=citations,
    )


def get_citation_map(args: dict[str, Any]) -> dict[str, Any]:
    """Return the transcript + screenshot citation map for a saved yoink,
    each entry carrying a timestamped YouTube deep link."""
    slug = args.get("slug")
    folder, corpus = _find_yoink(slug)
    if not folder or not corpus:
        return _err("yoink not found")
    video_id = _read_sidecar(folder).get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        return _err("yoink has no video_id")
    transcript: list[dict[str, Any]] = []
    screenshots: list[dict[str, Any]] = []
    for r in _b()._get_index().get_citations(video_id):
        if r.get("kind") == "screenshot":
            screenshots.append({
                "seq": r.get("seq"),
                "timestamp": r.get("timestamp_start"),
                "file_path": r.get("file_path"),
                "deep_link": r.get("youtube_deep_link"),
            })
        else:
            transcript.append({
                "seq": r.get("seq"),
                "timestamp_start": r.get("timestamp_start"),
                "timestamp_end": r.get("timestamp_end"),
                "text": r.get("text"),
                "deep_link": r.get("youtube_deep_link"),
            })
    return _ok(
        video_id=video_id,
        transcript_citations=transcript,
        screenshot_citations=screenshots,
    )


def get_uoink_health(args: dict[str, Any]) -> dict[str, Any]:
    """Return the per-section extraction health score for a saved uoink."""
    slug = args.get("slug")
    folder, corpus = _find_yoink(slug)
    if not folder or not corpus:
        return _err("yoink not found")
    sidecar = _read_sidecar(folder)
    video_id = sidecar.get("video_id")
    health = None
    if isinstance(video_id, str) and video_id.strip():
        try:
            health = _b()._get_index().get_health(video_id)
        except Exception:
            health = None
    if health is None:
        # Fall back to the sidecar's own snapshot if the index lacks a row.
        health = sidecar.get("health")
    if not isinstance(health, dict):
        return _err("no health data for this yoink")
    return _ok(video_id=video_id or None, health=health)


def get_schema_version(_args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 substrate: data-shape version report (SQL migration + yoink row +
    sidecar JSON). No arguments. Used by cross-version aggregators to gate v2
    field assumptions."""
    server = _b()
    import index as _index_mod
    try:
        idx = server._get_index()
        sql_version = idx._conn.execute(
            "SELECT MAX(version) FROM schema_version").fetchone()[0]
    except Exception:
        sql_version = None
    return _ok(
        sql_migration=sql_version,
        yoink_schema=_index_mod.CURRENT_YOINK_SCHEMA,
        sidecar_schema=server.CURRENT_SIDECAR_SCHEMA,
        yoink_schema_supported=[1, _index_mod.CURRENT_YOINK_SCHEMA],
        sidecar_schema_supported=[1, server.CURRENT_SIDECAR_SCHEMA],
    )


def get_engagement_signal(args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 S2 engagement memory: report the time-decayed value_score + event
    counts for one video. Pure local read -- no model, no outbound."""
    video_id = args.get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        return _err("video_id (string) is required")
    server = _b()
    try:
        signal = server._get_index().engagement_signal(video_id.strip())
    except Exception as e:
        return _err(f"engagement_signal failed: {e}")
    return _ok(**signal)


def find_mentions(args: dict[str, Any]) -> dict[str, Any]:
    """Return every recorded mention of an entity across the library,
    newest first, each with a timestamped YouTube deep link (Sprint 16)."""
    name = args.get("entity") or args.get("name")
    if not isinstance(name, str) or not name.strip():
        return _err("entity name (string) is required")
    limit = _limit_int(args.get("limit"), default=50, low=1, high=200)
    # Index.find_mentions normalises the name itself, so the raw entity
    # string is passed straight through.
    rows = _b()._get_index().find_mentions(name.strip(), limit)
    return _ok(mentions=rows)


def analyze_comments_tool(args: dict[str, Any]) -> dict[str, Any]:
    b = _b()
    key = _saved_key()
    if not key:
        return _err("anthropic key not configured")
    slug = args.get("slug")
    folder, corpus = _find_yoink(slug)
    if not folder or not corpus:
        return _err("yoink not found")
    comments = _comments_for_folder(folder)
    if len(comments) < 5:
        return _err("not enough comments to analyze")
    try:
        analysis = b.analyze_comments(comments, api_key=key)
        b._replace_comment_intelligence_section(
            corpus, b._render_comment_intelligence(analysis)
        )
        b._update_sidecar_comment_intelligence(
            folder, status="fetched", analysis=analysis
        )
        return _ok(
            top_themes=analysis.get("top_themes") or [],
            mentioned_products=analysis.get("mentioned_products_tools") or [],
            notable_disagreements=analysis.get("notable_disagreements") or [],
        )
    except b.AnthropicAPIError as e:
        return _err(b._short_reason(e.reason))


def classify_hook(args: dict[str, Any]) -> dict[str, Any]:
    b = _b()
    key = _saved_key()
    if not key:
        return _err("anthropic key not configured")
    slug = args.get("slug")
    folder, corpus = _find_yoink(slug)
    if not folder or not corpus:
        return _err("yoink not found")
    try:
        context = _hook_context_for_folder(folder)
        analysis = b.analyze_hook_type(context, api_key=key)
        b._replace_hook_analysis_section(corpus, b._render_hook_analysis(analysis))
        b._update_sidecar_hook_type(
            folder,
            status="completed",
            hook_type=analysis.get("hook_type"),
            hook_explanation=analysis.get("hook_explanation"),
            confidence=analysis.get("confidence"),
        )
        b._append_hook_taxonomy(context, analysis)
        # Sprint 17 (A3): the response now carries the classifier's 1-5
        # confidence and how many past corrections were injected as
        # few-shot anchors. Both fields are additive -- pre-Sprint-17
        # consumers ignore them.
        return _ok(
            hook_type=analysis.get("hook_type"),
            hook_explanation=analysis.get("hook_explanation"),
            confidence=analysis.get("confidence"),
            similar_corrections_used=analysis.get("similar_corrections_used") or 0,
        )
    except b.AnthropicAPIError as e:
        return _err(b._short_reason(e.reason))


def get_taxonomy(args: dict[str, Any]) -> dict[str, Any]:
    b = _b()
    channel = args.get("channel")
    hook_type = args.get("hook_type")
    if channel is not None and not isinstance(channel, str):
        return _err("channel must be a string")
    if hook_type is not None:
        if not isinstance(hook_type, str):
            return _err("hook_type must be a string")
        hook_type = hook_type.strip().lower()
        if hook_type and hook_type not in b.HOOK_TYPES:
            return _err("hook_type invalid")
    limit = _limit_int(args.get("limit"), default=50, low=1, high=500)
    return _ok(
        taxonomy=b._query_taxonomy(
            channel=channel,
            hook_type=hook_type,
            limit=limit,
        )
    )


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "uoink_video": ToolSpec(
        name="uoink_video",
        description=(
            "Extract a single YouTube video into a Uoink corpus. Returns the "
            "saved folder, markdown corpus, and screenshot paths."
        ),
        input_schema=_schema({
            "url": {"type": "string", "description": "YouTube video URL."},
            "interval": {
                "type": "integer",
                "description": "Screenshot interval in seconds (5-300). Optional.",
                "minimum": 5,
                "maximum": 300,
                "default": 30,
            },
        }, ["url"]),
        handler=uoink_video,
        rate_limiter=_RateLimiter(5),
    ),
    "uoink_playlist": ToolSpec(
        name="uoink_playlist",
        description="Start asynchronous extraction for a YouTube playlist.",
        input_schema=_schema({
            "url": {"type": "string", "description": "YouTube playlist URL."},
            "interval": {
                "type": "integer",
                "description": "Screenshot interval in seconds (5-300). Optional.",
                "minimum": 5,
                "maximum": 300,
                "default": 30,
            },
        }, ["url"]),
        handler=uoink_playlist,
        rate_limiter=_RateLimiter(5),
    ),
    "get_job_status": ToolSpec(
        name="get_job_status",
        description="Return the full status object for an async Uoink job.",
        input_schema=_schema({
            "job_id": {"type": "string", "description": "Job ID from uoink_playlist."},
        }, ["job_id"]),
        handler=get_job_status,
    ),
    "cancel_job": ToolSpec(
        name="cancel_job",
        description="Cancel an async Uoink job and leave partial outputs on disk.",
        input_schema=_schema({
            "job_id": {"type": "string", "description": "Job ID to cancel."},
        }, ["job_id"]),
        handler=cancel_job,
    ),
    "list_recent_uoinks": ToolSpec(
        name="list_recent_uoinks",
        description="List recent saved Uoink corpora.",
        input_schema=_schema({
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        }),
        handler=list_recent_uoinks,
        # Read-only but walks the whole corpus tree on every call; cap so an
        # agent loop can't melt the disk. Cheaper than search, so higher cap.
        rate_limiter=_RateLimiter(60),
    ),
    "search_uoinks": ToolSpec(
        name="search_uoinks",
        description="Full-text search across saved Uoink corpora.",
        input_schema=_schema({
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            "channel": {
                "type": "string",
                "description": "Filter results to one channel. Optional.",
            },
            "hook_type": {
                "type": "string",
                "description": "Filter results to one hook type. Optional.",
            },
        }, ["query"]),
        handler=search_uoinks,
        # Backed by the SQLite FTS5 index; rate-limited anyway so an agent
        # loop can't hammer it.
        rate_limiter=_RateLimiter(30),
    ),
    "get_uoink_corpus": ToolSpec(
        name="get_uoink_corpus",
        description="Return the full markdown corpus for a saved uoink by slug.",
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=get_uoink_corpus,
    ),
    "analyze_comments": ToolSpec(
        name="analyze_comments",
        description=(
            "Run Comment Intelligence on an existing uoink and return themes, "
            "mentioned products/tools, and disagreements."
        ),
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=analyze_comments_tool,
        rate_limiter=_RateLimiter(10),
    ),
    "classify_hook": ToolSpec(
        name="classify_hook",
        description="Classify the hook type for an existing uoink.",
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=classify_hook,
        rate_limiter=_RateLimiter(10),
    ),
    "get_taxonomy": ToolSpec(
        name="get_taxonomy",
        description=(
            "Return captured Hook Type taxonomy rows, optionally filtered by "
            "channel and hook_type."
        ),
        input_schema=_schema({
            "channel": {
                "type": "string",
                "description": "Exact channel name to filter by. Optional.",
            },
            "hook_type": {
                "type": "string",
                "description": "Hook type to filter by. Optional.",
                "enum": [
                    "curiosity_gap",
                    "question",
                    "contrarian",
                    "story_open",
                    "promise_list",
                    "demo",
                    "authority",
                    "stakes",
                    "other",
                ],
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "default": 50,
            },
        }),
        handler=get_taxonomy,
    ),
    "get_citation_map": ToolSpec(
        name="get_citation_map",
        description=(
            "Return the transcript + screenshot citation map for a saved "
            "uoink, each entry with a timestamped YouTube deep link."
        ),
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=get_citation_map,
        rate_limiter=_RateLimiter(60),
    ),
    "get_uoink_health": ToolSpec(
        name="get_uoink_health",
        description="Return the per-section extraction health score for a saved uoink.",
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=get_uoink_health,
        rate_limiter=_RateLimiter(60),
    ),
    "find_mentions": ToolSpec(
        name="find_mentions",
        description=(
            "Find every place an entity (person, tool, product, company, "
            "or topic) is mentioned across saved uoinks, newest first, each "
            "with a timestamped YouTube deep link."
        ),
        input_schema=_schema({
            "entity": {
                "type": "string",
                "description": "Entity name to look up (case-insensitive).",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 50,
            },
        }, ["entity"]),
        handler=find_mentions,
        # Backed by the SQLite index; rate-limited so an agent loop can't
        # hammer it.
        rate_limiter=_RateLimiter(60),
    ),
    "get_schema_version": ToolSpec(
        name="get_schema_version",
        description=(
            "Report the data-shape versions Uoink writes + the supported "
            "read-range. v2.5 substrate: cross-version aggregators (Channel "
            "Decoder, Niche Corpus) check this before assuming v2 fields are "
            "present in older rows/sidecars. Read-only, no arguments."
        ),
        input_schema=_schema({}, []),
        handler=get_schema_version,
        rate_limiter=_RateLimiter(60),
    ),
    "get_engagement_signal": ToolSpec(
        name="get_engagement_signal",
        description=(
            "v2.5 S2 engagement memory: return the time-decayed value_score "
            "for one video plus per-event-type counts and last event "
            "timestamp. Events live entirely on the local SQLite index "
            "(zero outbound). Weights are documented in index.py "
            "(_ENGAGEMENT_WEIGHTS); decay half-life is 30 days."
        ),
        input_schema=_schema({
            "video_id": {
                "type": "string",
                "description": "YouTube video id (11 chars).",
            },
        }, ["video_id"]),
        handler=get_engagement_signal,
        rate_limiter=_RateLimiter(120),
    ),
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.input_schema,
        }
        for spec in TOOL_REGISTRY.values()
    ]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    # v2.1 alias window: map a legacy yoink_* name onto its canonical uoink_*
    # name and emit a one-shot deprecation warning to stderr. Both transports
    # (stdio MCP and HTTP JSON-RPC) route through here, so this is the single
    # place the deprecation is surfaced.
    canonical = MCP_TOOL_ALIASES.get(name)
    if canonical:
        _warn_deprecated_tool(name, canonical)
        name = canonical
    spec = TOOL_REGISTRY.get(name)
    if not spec:
        return _err("tool not found")
    args = arguments or {}
    if not isinstance(args, dict):
        return _err("arguments must be an object")
    try:
        if spec.rate_limiter:
            spec.rate_limiter.check()
        return spec.handler(args)
    except RateLimitExceeded as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"tool failed: {e}")
