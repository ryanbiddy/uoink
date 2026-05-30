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


def classify_facets(args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 S1: persist agent-classified facets + tags for one video. Model-
    agnostic -- the calling agent does the LLM work; this MCP tool only
    validates against the enums and writes to the row. The server fills in
    performance_tier (channel-relative percentile) and length_bucket (from
    duration metadata) if the agent didn't supply them. Zero outbound calls."""
    video_id = (args.get("video_id") or "").strip()
    if not video_id:
        return _err("video_id required")
    server = _b()
    body = {k: args.get(k) for k in (
        "format", "performance_tier", "production_style", "length_bucket",
        "topic", "hook_type", "tags",
    )}
    clean, err = server._validate_facets(body)
    if err:
        return _err(err)
    tags = clean.pop("__tags", None)
    idx = server._get_index()
    if "performance_tier" not in clean or "length_bucket" not in clean:
        row = idx._conn.execute(
            "SELECT channel, metadata_json FROM yoinks WHERE video_id=?",
            (video_id,)).fetchone()
        if row:
            try:
                meta = json.loads(row["metadata_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}
            if "performance_tier" not in clean and row["channel"]:
                tier = server._perf_tier(
                    idx.channel_view_counts(row["channel"]),
                    meta.get("views") or meta.get("view_count"))
                if tier:
                    clean["performance_tier"] = tier
            if "length_bucket" not in clean:
                lb = server._length_bucket_from_seconds(
                    meta.get("duration_seconds") or meta.get("duration"))
                if lb:
                    clean["length_bucket"] = lb
    facets_set = idx.set_facets(video_id, **clean)
    tags_added = idx.add_tags(video_id, tags or [], source="agent") if tags else 0
    return _ok(video_id=video_id, facets_set=facets_set,
               tags_added=tags_added, facets=clean)


def query_by_facets(args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 S1: filter yoinks by facet values. All filters AND-combined."""
    idx = _b()._get_index()
    rows = idx.query_by_facets(
        format=args.get("format"),
        performance_tier=args.get("performance_tier"),
        hook_type=args.get("hook_type"),
        topic=args.get("topic"),
        length_bucket=args.get("length_bucket"),
        tag=args.get("tag"),
        limit=int(args.get("limit") or 50),
    )
    return _ok(yoinks=rows, count=len(rows))


def get_facet_taxonomy(_args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 S1: enum lists for filter chips and validation. Pure constants."""
    server = _b()
    hooks = getattr(server, "HOOK_TYPES", None)
    return _ok(
        format=list(server.FORMAT_ENUM),
        performance_tier=list(server.PERF_TIER_ENUM),
        length_bucket=list(server.LENGTH_BUCKET_ENUM),
        hook=sorted(hooks.keys()) if isinstance(hooks, dict) else list(hooks or []),
    )


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


def get_user_taste(_args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 S4 taste memory: return the consolidated TASTE.md content +
    path. Lazily regenerated if absent. No model, no outbound."""
    server = _b()
    import memory_layer as _ml
    try:
        vault = (server._read_settings().get("obsidian_vault_path") or "") or None
    except Exception:
        vault = None
    try:
        res = _ml.read_taste(server._get_index(), server.DATA_ROOT,
                              vault_path=vault)
    except Exception as e:
        return _err(f"read_taste failed: {e}")
    return _ok(**res)


def get_user_role(_args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 P2: report the user's persisted role + the resolved
    dashboard emphasis (primary/secondary chip order + default sort).
    Read-only; no model, no outbound."""
    server = _b()
    try:
        data = server._read_settings() or {}
        role = server._normalize_role(data.get("role"))
        emphasis = server._role_facet_emphasis(role)
    except Exception as e:
        return _err(f"get_user_role failed: {e}")
    return _ok(role=role, emphasis=emphasis,
                supported_roles=list(server._ROLE_ENUM))


def set_user_role(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 P2: persist the user's role choice. One of creator /
    researcher / marketer / mixed. The dashboard reads this on load
    via GET /role/emphasis to reshape its Library default + filter
    chips."""
    server = _b()
    role = args.get("role")
    if not isinstance(role, str):
        return _err("role (string) is required")
    norm = role.strip().lower()
    if norm not in server._ROLE_ENUM:
        return _err(f"role must be one of {list(server._ROLE_ENUM)}")
    try:
        data = server._read_settings() or {}
        data["role"] = norm
        server._write_settings(data)
    except Exception as e:
        return _err(f"set_user_role failed: {e}")
    return _ok(role=norm, emphasis=server._role_facet_emphasis(norm))


def check_live_status(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1: probe a URL's live state without extracting.

    Returns one of the bounded states: not_live | live | upcoming |
    post_live | was_live. Useful before queueing so the agent can pick
    between immediate extraction and 'wait for the broadcast to end'."""
    server = _b()
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return _err("url (string) is required")
    canonical, _platform = server._normalize_video_url(url.strip())
    if not canonical:
        canonical, _platform = server._normalize_any_url(url.strip())
    if not canonical:
        return _err("url is not a valid http(s) video URL")
    try:
        metadata = server._fetch_metadata(canonical)
    except Exception as e:
        return _err(f"yt-dlp could not fetch: {e}")
    state = server._detect_live_state(metadata)
    return _ok(url=canonical, live_state=state,
                title=metadata.get("title"),
                supported_states=list(server._LIVE_STATES))


# ---- v3.1 podcast feeds + episodes ----------------------------------
def add_podcast_feed(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 podcast: register an RSS feed URL. Idempotent -- existing
    URL returns the same row. Default poll interval 60 min, range
    15-1440."""
    server = _b()
    import podcasts as _pod
    feed_url = args.get("feed_url")
    if not isinstance(feed_url, str) or not feed_url.strip():
        return _err("feed_url (string) is required")
    interval = args.get("poll_interval_min") or 60
    try:
        return _ok(feed=_pod.add_feed(server._get_index(),
                                        feed_url.strip(),
                                        poll_interval_min=int(interval)))
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"add_podcast_feed failed: {e}")


def list_podcast_feeds(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 podcast: list registered RSS feeds newest-first."""
    server = _b()
    import podcasts as _pod
    enabled_only = bool(args.get("enabled_only"))
    try:
        rows = _pod.list_feeds(server._get_index(),
                                  enabled_only=enabled_only)
    except Exception as e:
        return _err(f"list_podcast_feeds failed: {e}")
    return _ok(feeds=rows, count=len(rows))


def remove_podcast_feed(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 podcast: delete a feed + cascade its episodes."""
    server = _b()
    import podcasts as _pod
    try:
        feed_id = int(args.get("feed_id"))
    except (TypeError, ValueError):
        return _err("feed_id (integer) is required")
    try:
        removed = _pod.remove_feed(server._get_index(), feed_id)
    except Exception as e:
        return _err(f"remove_podcast_feed failed: {e}")
    return _ok(removed=removed)


def poll_podcast_feed(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 podcast: trigger one feed poll. Returns the parsed result.

    This is the on-demand path; a background poller would call the same
    function on a schedule (left for a follow-up that needs a thread)."""
    server = _b()
    import podcasts as _pod
    try:
        feed_id = int(args.get("feed_id"))
    except (TypeError, ValueError):
        return _err("feed_id (integer) is required")
    try:
        return _pod.poll_feed(server._get_index(), feed_id)
    except Exception as e:
        return _err(f"poll_podcast_feed failed: {e}")


def list_podcast_episodes(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 podcast: list episodes. Optional feed_id + status filters."""
    server = _b()
    import podcasts as _pod
    feed_id = args.get("feed_id")
    try:
        feed_id_i = int(feed_id) if feed_id is not None else None
    except (TypeError, ValueError):
        return _err("feed_id must be an integer when provided")
    status = args.get("status")
    if status is not None and not isinstance(status, str):
        return _err("status must be a string when provided")
    limit = _limit_int(args.get("limit"), default=100, low=1, high=1000)
    try:
        rows = _pod.list_episodes(server._get_index(),
                                     feed_id=feed_id_i,
                                     status=status, limit=limit)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"list_podcast_episodes failed: {e}")
    return _ok(episodes=rows, count=len(rows))


def download_podcast_episode(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 podcast: download an episode's MP3 via yt-dlp + ffmpeg.

    Synchronous. Returns when the file lands at
    <data_root>/Podcasts/<feed-slug>/<episode-slug>.mp3 or yt-dlp
    errors. Idempotent -- skips re-download when the canonical path
    already has a non-zero file. The transcription pipeline (next
    PR in CC's queue) reads audio_local_path to feed WhisperX."""
    server = _b()
    import podcasts as _pod
    try:
        episode_id = int(args.get("episode_id"))
    except (TypeError, ValueError):
        return _err("episode_id (integer) is required")
    try:
        return _pod.download_episode_audio(
            server._get_index(), episode_id,
            data_root=server.DATA_ROOT)
    except Exception as e:
        return _err(f"download_podcast_episode failed: {e}")


def get_whisperx_status(_args: dict[str, Any]) -> dict[str, Any]:
    """v3.1: report whether the WhisperX runtime is importable + the
    currently-selected model. Used by agents to decide whether to
    surface a 'still need to install whisperx' affordance before
    queueing a transcribe call."""
    server = _b()
    import whisper_runner as _wr
    settings = server._read_settings() or {}
    return _ok(
        whisperx_available=_wr.is_whisperx_available(),
        selected_model=settings.get("whisper_model") or "base",
        supported_models=list(_wr._MODELS),
        diarization_default=bool(settings.get("diarization_default")),
    )


def transcribe_podcast_episode(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 podcast: run WhisperX on a downloaded podcast episode.

    Synchronous. The audio at episode.audio_local_path is the input;
    transcript JSON lands next to it. Returns the structured
    transcript metadata or:
      - 'whisperx runtime not installed' err when the runtime isn't
        importable.
      - consent_required=True when the user hasn't agreed to the
        first-time model download yet (200 MB - 2 GB). Re-issue with
        consent_given=True after the dashboard prompt records the
        opt-in."""
    server = _b()
    import whisper_runner as _wr
    import podcasts as _pod
    try:
        episode_id = int(args.get("episode_id"))
    except (TypeError, ValueError):
        return _err("episode_id (integer) is required")
    episode = _pod.get_episode(server._get_index(), episode_id)
    if episode is None:
        return _err("episode not found")
    if not episode.get("audio_local_path"):
        return _err("episode has no audio_local_path -- "
                     "download_podcast_episode first")
    if not _wr.is_whisperx_available():
        return _err("whisperx runtime not installed; "
                     "use the Setup page to install (consent-gated dep).")
    settings = server._read_settings() or {}
    model = _wr.normalize_model(
        args.get("model") or settings.get("whisper_model"))
    diarize = bool(args.get("diarize")
                     if args.get("diarize") is not None
                     else settings.get("diarization_default"))
    consent_given = bool(args.get("consent_given"))
    language = args.get("language")
    _wr.update_episode_transcript_state(
        server._get_index(), episode_id,
        status=_wr.STATUS_RUNNING, model_used=model)
    from pathlib import Path as _P
    try:
        transcript = _wr.transcribe_audio(
            _P(episode["audio_local_path"]),
            data_root=server.DATA_ROOT,
            model_size=model, language=language,
            diarize=diarize, consent_given=consent_given)
    except PermissionError as e:
        _wr.update_episode_transcript_state(
            server._get_index(), episode_id,
            status=_wr.STATUS_QUEUED, error=str(e))
        return {"ok": False, "consent_required": True,
                "model": model, "error": str(e)}
    except Exception as e:
        _wr.update_episode_transcript_state(
            server._get_index(), episode_id,
            status=_wr.STATUS_FAILED, error=str(e))
        return _err(f"transcribe failed: {e}")
    out_path = _wr.write_transcript(
        transcript, audio_path=_P(episode["audio_local_path"]))
    _wr.update_episode_transcript_state(
        server._get_index(), episode_id,
        status=_wr.STATUS_DONE, transcript_path=out_path,
        model_used=model,
        diarization_ran=transcript.get("diarization_ran", False))
    return _ok(episode_id=episode_id,
                transcript_path=str(out_path),
                model=transcript["model"],
                language=transcript["language"],
                segments=len(transcript["segments"]),
                diarization_ran=transcript["diarization_ran"])


# ---- v3.1 mobile playlist monitor ------------------------------------
def add_monitored_playlist(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 mobile bridge: register a YouTube playlist URL to monitor.
    Idempotent on UNIQUE playlist_url. poll_interval_min default 5,
    range 1-1440."""
    server = _b()
    import mobile_playlists as _mp
    url = args.get("playlist_url")
    if not isinstance(url, str) or not url.strip():
        return _err("playlist_url (string) is required")
    name = args.get("name")
    interval = args.get("poll_interval_min") or 5
    try:
        return _ok(playlist=_mp.add_playlist(
            server._get_index(), url.strip(),
            name=name, poll_interval_min=int(interval),
            normalize_playlist_url=server._normalize_playlist_url))
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"add_monitored_playlist failed: {e}")


def list_monitored_playlists(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 mobile bridge: list registered playlists newest-first."""
    server = _b()
    import mobile_playlists as _mp
    enabled_only = bool(args.get("enabled_only"))
    try:
        rows = _mp.list_playlists(server._get_index(),
                                     enabled_only=enabled_only)
    except Exception as e:
        return _err(f"list_monitored_playlists failed: {e}")
    return _ok(playlists=rows, count=len(rows))


def remove_monitored_playlist(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 mobile bridge: delete a playlist + cascade its discovery
    events."""
    server = _b()
    import mobile_playlists as _mp
    try:
        playlist_id = int(args.get("playlist_id"))
    except (TypeError, ValueError):
        return _err("playlist_id (integer) is required")
    try:
        removed = _mp.remove_playlist(server._get_index(), playlist_id)
    except Exception as e:
        return _err(f"remove_monitored_playlist failed: {e}")
    return _ok(removed=removed)


def poll_monitored_playlist(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 mobile bridge: trigger one poll. yt-dlp --flat-playlist +
    diff against last_seen_video_ids + auto-queue new videos via the
    existing pending_yoinks retry worker. Returns the new[] discovery
    list so the dashboard can show it under a 'from mobile playlist'
    label."""
    server = _b()
    import mobile_playlists as _mp
    try:
        playlist_id = int(args.get("playlist_id"))
    except (TypeError, ValueError):
        return _err("playlist_id (integer) is required")
    def _vid_to_url(vid: str) -> str | None:
        if not vid:
            return None
        return server._normalize_youtube_url(
            f"https://www.youtube.com/watch?v={vid}")
    try:
        return _mp.poll_playlist(server._get_index(), playlist_id,
                                    normalize_video_to_canonical_url=_vid_to_url)
    except Exception as e:
        return _err(f"poll_monitored_playlist failed: {e}")


def list_monitored_playlist_events(args: dict[str, Any]) -> dict[str, Any]:
    """v3.1 mobile bridge: list per-discovery events.
    Optional filters: playlist_id, status (discovered | queued |
    extracted | failed)."""
    server = _b()
    import mobile_playlists as _mp
    playlist_id = args.get("playlist_id")
    try:
        pid = int(playlist_id) if playlist_id is not None else None
    except (TypeError, ValueError):
        return _err("playlist_id must be an integer when provided")
    status = args.get("status")
    if status is not None and not isinstance(status, str):
        return _err("status must be a string when provided")
    limit = _limit_int(args.get("limit"), default=200, low=1, high=1000)
    try:
        rows = _mp.list_events(server._get_index(),
                                  playlist_id=pid, status=status,
                                  limit=limit)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"list_monitored_playlist_events failed: {e}")
    return _ok(events=rows, count=len(rows))


# ---- v3.2 Writing Studio --------------------------------------------
def _writing_grounding(yoink_id, style_anchor_ids):
    server = _b()
    import writing_studio as _ws  # noqa: WPS433
    return _ws.assemble_grounding(
        server._get_index(), yoink_id,
        style_anchor_ids=style_anchor_ids)


def _writing_persist(yoink_id, kind, body_text, *, title=None, dek=None,
                       tags=None, style_anchor_ids=None, angle=None,
                       target_length=None, parent_id=None,
                       suppress_credit=False,
                       skip_voice_dna_this_time=False,
                       source_credit_line=None):
    server = _b()
    import writing_studio as _ws  # noqa: WPS433
    settings = server._read_settings() or {}
    yoink_row = (server._get_index().get_yoink(yoink_id)
                  if yoink_id else None)
    credit = source_credit_line or _ws.build_credit_line(yoink_row, kind=kind)
    return _ws.persist_piece(
        server._get_index(), yoink_id=yoink_id, kind=kind,
        body=body_text, title=title, dek=dek, tags=tags,
        source_credit_line=credit,
        style_anchor_ids=style_anchor_ids,
        angle=angle, target_length=target_length,
        parent_id=parent_id,
        voice_dna_warnings_enabled=bool(
            settings.get("voice_dna_warnings_enabled", True)),
        skip_voice_dna_this_time=skip_voice_dna_this_time,
        suppress_credit=suppress_credit,
    )


def write_tweet(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Writing Studio (tweet/thread): two-phase. Phase 1 -- no
    `body` field -> returns grounding (source yoink + creator credit +
    style anchors + Voice DNA). Agent writes the tweet/thread using
    its own model, INCLUDING the credit line verbatim. Phase 2 --
    `body` present -> persists + scans + returns warnings (NEVER
    auto-blocks; see VOICE-DNA.md soft-warn policy)."""
    import writing_studio as _ws  # noqa: WPS433
    yoink_id = (args.get("source_yoink_id")
                 or args.get("yoink_id"))
    if yoink_id is not None and not isinstance(yoink_id, str):
        return _err("source_yoink_id must be a string")
    style_anchor_ids = args.get("style_anchor_ids") or []
    if not isinstance(style_anchor_ids, list):
        return _err("style_anchor_ids must be a list")
    body_text = args.get("body")
    if body_text is None:
        return _ok(mode="grounding_only", kind=_ws.KIND_TWEET,
                    context=_writing_grounding(yoink_id, style_anchor_ids),
                    next=("Produce the tweet body (with credit line "
                          "included verbatim) and re-call with `body`."))
    try:
        piece = _writing_persist(
            yoink_id, _ws.KIND_TWEET, body_text,
            tags=args.get("tags") or [],
            style_anchor_ids=style_anchor_ids,
            angle=args.get("angle"),
            target_length=args.get("target_length_chars"),
            parent_id=args.get("parent_id"),
            suppress_credit=bool(args.get("suppress_credit")),
            skip_voice_dna_this_time=bool(
                args.get("skip_voice_dna_this_time")),
            source_credit_line=args.get("source_credit_line"))
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"write_tweet failed: {e}")
    # piece already carries 'mode' from persist_piece (compute mode:
    # agent|byo_key). Override it to the phase indicator 'persisted'
    # before returning so the dashboard can distinguish grounding_only
    # from persisted without poking at the kind field.
    piece["mode"] = "persisted"
    return _ok(**piece)


def write_blog(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Writing Studio (blog): same two-phase contract as
    write_tweet. Phase 2 also accepts `title`, `dek`, `tags`."""
    import writing_studio as _ws  # noqa: WPS433
    yoink_id = (args.get("source_yoink_id")
                 or args.get("yoink_id"))
    if yoink_id is not None and not isinstance(yoink_id, str):
        return _err("source_yoink_id must be a string")
    style_anchor_ids = args.get("style_anchor_ids") or []
    if not isinstance(style_anchor_ids, list):
        return _err("style_anchor_ids must be a list")
    body_text = args.get("body")
    if body_text is None:
        return _ok(mode="grounding_only", kind=_ws.KIND_BLOG,
                    context=_writing_grounding(yoink_id, style_anchor_ids),
                    next=("Produce the blog (title, dek, body markdown, "
                          "tags) with the Source section included and "
                          "re-call with `body` and friends."))
    try:
        piece = _writing_persist(
            yoink_id, _ws.KIND_BLOG, body_text,
            title=args.get("title"), dek=args.get("dek"),
            tags=args.get("tags") or [],
            style_anchor_ids=style_anchor_ids,
            angle=args.get("angle"),
            target_length=args.get("target_length_words"),
            parent_id=args.get("parent_id"),
            suppress_credit=bool(args.get("suppress_credit")),
            skip_voice_dna_this_time=bool(
                args.get("skip_voice_dna_this_time")),
            source_credit_line=args.get("source_credit_line"))
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"write_blog failed: {e}")
    piece["mode"] = "persisted"
    return _ok(**piece)


def list_writing_pieces(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Writing Studio: list pieces newest-first. Optional `kind`
    + `yoink_id` filters."""
    server = _b()
    import writing_studio as _ws  # noqa: WPS433
    kind = args.get("kind")
    yoink_id = args.get("yoink_id")
    limit = _limit_int(args.get("limit"), default=100, low=1, high=500)
    try:
        rows = _ws.list_pieces(
            server._get_index(), kind=kind, yoink_id=yoink_id, limit=limit)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"list_writing_pieces failed: {e}")
    return _ok(pieces=rows, count=len(rows))


def get_writing_piece(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Writing Studio: fetch one piece by id."""
    server = _b()
    import writing_studio as _ws  # noqa: WPS433
    try:
        piece_id = int(args.get("id") or args.get("piece_id"))
    except (TypeError, ValueError):
        return _err("piece id (integer) is required")
    piece = _ws.get_piece(server._get_index(), piece_id)
    if piece is None:
        return _err("piece not found")
    return _ok(piece=piece)


def add_style_anchor(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Writing Studio: add a Substack-style voice anchor (URL or
    raw text). Cap at 10 per Ryan's locked answer #4."""
    server = _b()
    import writing_studio as _ws  # noqa: WPS433
    try:
        url_fetcher = (server.Handler._writing_url_fetcher
                        if False else None)  # MCP path doesn't have a Handler instance
    except Exception:
        url_fetcher = None
    # The MCP call doesn't have a Handler instance, so we resolve the
    # extractor directly. Falls back to None if Universal Site PR isn't
    # in main yet (anchor still saves with raw_text=NULL for URLs).
    url_fetcher = globals().get("_extract_page_to_prose_fn")
    if url_fetcher is None:
        url_fetcher = getattr(server, "_extract_page_to_prose", None)
    try:
        row = _ws.add_style_anchor(
            server._get_index(),
            name=args.get("name"),
            source_type=(args.get("source_type") or "").strip(),
            source_value=args.get("source_value"),
            url_to_prose=url_fetcher)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"add_style_anchor failed: {e}")
    return _ok(anchor=row)


def list_style_anchors(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Writing Studio: list style anchors with their active flag."""
    server = _b()
    import writing_studio as _ws  # noqa: WPS433
    active_only = bool(args.get("active_only"))
    rows = _ws.list_style_anchors(
        server._get_index(), active_only=active_only)
    return _ok(anchors=rows, count=len(rows), cap=_ws.STYLE_ANCHOR_CAP)


def remove_style_anchor(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Writing Studio: delete a style anchor."""
    server = _b()
    import writing_studio as _ws  # noqa: WPS433
    try:
        anchor_id = int(args.get("anchor_id") or args.get("id"))
    except (TypeError, ValueError):
        return _err("anchor_id (integer) is required")
    try:
        removed = _ws.remove_style_anchor(
            server._get_index(), anchor_id)
    except Exception as e:
        return _err(f"remove_style_anchor failed: {e}")
    return _ok(removed=removed, id=anchor_id)


def get_user_memory(_args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 S4 user memory: return the free-form USER.md content + path.
    Skeleton is seeded on first read so an agent always gets a starting
    point. No model, no outbound."""
    server = _b()
    import memory_layer as _ml
    try:
        res = _ml.read_user(server.DATA_ROOT)
    except Exception as e:
        return _err(f"read_user failed: {e}")
    return _ok(**res)


def update_user_taste(args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 S4 taste anchors: replace one TASTE anchor section
    (preferred_hooks | preferred_formats | avoid) and re-consolidate
    TASTE.md. Anchors persist in the memory_layer SQLite table so the
    consolidator can fold them on every regenerate."""
    section = args.get("section")
    content = args.get("content")
    server = _b()
    import memory_layer as _ml
    if section not in _ml.ANCHOR_SECTIONS:
        return _err(f"section must be one of {list(_ml.ANCHOR_SECTIONS)}")
    if not isinstance(content, str):
        return _err("content (string) is required")
    try:
        vault = (server._read_settings().get("obsidian_vault_path") or "") or None
    except Exception:
        vault = None
    try:
        res = _ml.update_user_taste(server._get_index(), server.DATA_ROOT,
                                     section, content, vault_path=vault)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"update_user_taste failed: {e}")
    return _ok(**res)


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


def analyze_self_channel(args: dict[str, Any]) -> dict[str, Any]:
    """v2.5 P3 your-channel mode: return the aggregated self-analysis
    payload -- hook evolution, format evolution, performance trend, top
    performers. `handle` is optional; when present, the analysis is
    restricted to that one channel. Pure local read."""
    server = _b()
    import channels as _channels_mod
    handle = args.get("handle")
    if handle is not None and not isinstance(handle, str):
        return _err("handle must be a string when provided")
    try:
        top_n = _limit_int(args.get("limit"), default=10, low=1, high=100)
    except Exception:
        top_n = 10
    try:
        result = _channels_mod.self_analysis(
            server._get_index(), handle=handle, top_n=top_n)
    except Exception as e:
        return _err(f"self_analysis failed: {e}")
    return result


def assemble_workspace(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P4 build workspace: pull a corpus slice ranked by S1 facets + S2
    engagement + optional self-channel + optional S4 taste anchors. Pure
    local read. If `workspace_id` is provided, the assembled video_id list
    is persisted onto the workspace row; otherwise the slice is returned
    standalone for inspection."""
    server = _b()
    import workspaces as _ws
    try:
        return _ws.assemble_workspace(
            server._get_index(),
            format=args.get("format"),
            topic=args.get("topic"),
            hook_target=args.get("hook_target"),
            your_channel=args.get("your_channel"),
            n_examples=int(args.get("n_examples") or 10),
            workspace_id=args.get("workspace_id"))
    except Exception as e:
        return _err(f"assemble_workspace failed: {e}")


def critique_against_corpus(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P4 critique tool. Two-phase contract:
      1. Call WITHOUT `findings` to retrieve the assembled context
         (workspace, corpus slice, audience questions, taste anchors).
         The calling agent does the LLM analysis on that context.
      2. Call WITH `findings` (a structured dict) to persist the agent's
         analysis to the workspace's critique log."""
    server = _b()
    import workspaces as _ws
    workspace_id = args.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        return _err("workspace_id (string) is required")
    draft_text = args.get("draft_text")
    if not isinstance(draft_text, str):
        return _err("draft_text (string) is required")
    findings = args.get("findings")
    mode = args.get("mode") or _ws.COMPUTE_MODE_AGENT
    try:
        return _ws.critique_against_corpus(
            server._get_index(), workspace_id.strip(),
            draft_text=draft_text, findings=findings, mode=mode)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"critique_against_corpus failed: {e}")


def list_workspaces(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P4: list workspaces newest-first."""
    server = _b()
    import workspaces as _ws
    try:
        limit = _limit_int(args.get("limit"), default=50, low=1, high=500)
    except Exception:
        limit = 50
    try:
        rows = _ws.list_workspaces(server._get_index(), limit=limit)
    except Exception as e:
        return _err(f"list_workspaces failed: {e}")
    return _ok(workspaces=rows, count=len(rows))


def get_workspace(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P4: fetch one workspace + its critique log."""
    server = _b()
    import workspaces as _ws
    workspace_id = args.get("id") or args.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        return _err("workspace id (string) is required")
    try:
        ws = _ws.get_workspace(server._get_index(), workspace_id.strip())
    except Exception as e:
        return _err(f"get_workspace failed: {e}")
    if ws is None:
        return _err("workspace not found")
    try:
        crit = _ws.critique_log_for(server._get_index(), workspace_id.strip())
    except Exception:
        crit = []
    return _ok(workspace=ws, critique_log=crit)


def extract_claims(args: dict[str, Any]) -> dict[str, Any]:
    """v3 A2 (Loki-inspired): persist agent-extracted claims for a video.

    LOCKED FRAMING: the calling agent does the LLM decomposition; this tool
    validates against bounded enums + writes the structure. Claims arrive
    as a list of {claim_text, check_worthiness?, context?}. Status is
    'extracted' until a /verify call lands evidence on a claim. This tool
    NEVER returns a truth verdict -- it surfaces checkable claims so the
    user can decide which to verify."""
    server = _b()
    import claims as _claims_mod
    video_id = args.get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        return _err("video_id (string) is required")
    claims_list = args.get("claims") or []
    if not isinstance(claims_list, list):
        return _err("claims must be a list of objects")
    mode = args.get("mode") or _claims_mod.COMPUTE_MODE_AGENT
    try:
        return _claims_mod.extract_claims(server._get_index(),
                                            video_id.strip(),
                                            claims=claims_list, mode=mode)
    except Exception as e:
        return _err(f"extract_claims failed: {e}")


def verify_claim(args: dict[str, Any]) -> dict[str, Any]:
    """v3 A2 (Loki-inspired): record evidence for one extracted claim.

    LOCKED FRAMING: alignment_signal MUST be one of
    `supports | contradicts | mixed | inconclusive`. NEVER 'true' /
    'false' / 'lie' / 'verified-as-X'. The user judges the verdict from
    the surfaced evidence + signal."""
    server = _b()
    import claims as _claims_mod
    try:
        claim_id = int(args.get("claim_id"))
    except (TypeError, ValueError):
        return _err("claim_id (integer) is required")
    evidence = args.get("evidence") or []
    if not isinstance(evidence, list):
        return _err("evidence must be a list")
    mode = args.get("mode") or _claims_mod.COMPUTE_MODE_AGENT
    try:
        return _claims_mod.verify_claim(server._get_index(), claim_id,
                                          evidence=evidence, mode=mode)
    except Exception as e:
        return _err(f"verify_claim failed: {e}")


def list_claims(args: dict[str, Any]) -> dict[str, Any]:
    """v3 A2: list extracted claims, optionally filtered by video_id and
    status (extracted | verified | not-attempted)."""
    server = _b()
    import claims as _claims_mod
    video_id = args.get("video_id")
    if video_id is not None and not isinstance(video_id, str):
        return _err("video_id must be a string when provided")
    status = args.get("status")
    if status is not None and not isinstance(status, str):
        return _err("status must be a string when provided")
    limit = _limit_int(args.get("limit"), default=200, low=1, high=1000)
    try:
        rows = _claims_mod.list_claims(server._get_index(),
                                         video_id=video_id, status=status,
                                         limit=limit)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"list_claims failed: {e}")
    return _ok(claims=rows, count=len(rows))


def get_claim(args: dict[str, Any]) -> dict[str, Any]:
    """v3 A2: fetch one claim by id, including stored evidence."""
    server = _b()
    import claims as _claims_mod
    try:
        claim_id = int(args.get("id") or args.get("claim_id"))
    except (TypeError, ValueError):
        return _err("claim id (integer) is required")
    try:
        row = _claims_mod.get_claim(server._get_index(), claim_id)
    except Exception as e:
        return _err(f"get_claim failed: {e}")
    if row is None:
        return _err("claim not found")
    return _ok(claim=row)


def generate_script(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P5 script studio: two-phase generator.

    Phase 1 (no `script`): return grounding context (workspace +
    assembled corpus + taste anchors). Calling agent writes the script
    using its own model -- locked compute policy.

    Phase 2 (`script` is a structured object): persist it. Returns the
    new script row id + version."""
    server = _b()
    import scripts as _scripts_mod
    workspace_id = args.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        return _err("workspace_id (string) is required")
    script = args.get("script")
    mode = args.get("mode") or _scripts_mod.COMPUTE_MODE_AGENT
    parent = args.get("parent_script_id")
    try:
        parent_id = int(parent) if parent is not None else None
    except (TypeError, ValueError):
        return _err("parent_script_id must be an integer")
    try:
        return _scripts_mod.generate_script(
            server._get_index(), workspace_id.strip(),
            script=script, mode=mode, parent_script_id=parent_id)
    except Exception as e:
        return _err(f"generate_script failed: {e}")


def revise_script(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P5: revise an existing script grounded in critique findings.
    Two-phase like generate_script -- without `revised_script` payload
    returns the previous script + grounding context; with payload it
    persists as a new version (parent_script_id chained)."""
    server = _b()
    import scripts as _scripts_mod
    try:
        script_id = int(args.get("script_id"))
    except (TypeError, ValueError):
        return _err("script_id (integer) is required")
    crit = args.get("critique_findings")
    target = args.get("revision_target")
    revised = args.get("revised_script")
    mode = args.get("mode") or _scripts_mod.COMPUTE_MODE_AGENT
    try:
        return _scripts_mod.revise_script(
            server._get_index(), script_id,
            critique_findings=crit, revision_target=target,
            revised_script=revised, mode=mode)
    except Exception as e:
        return _err(f"revise_script failed: {e}")


def get_shot_list(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P5: derive (and persist) a default shot list for a script
    based on its beats + the parent workspace's format. Overwrites any
    prior shot_list on the row -- the calling agent can also supply
    shot_list directly in generate_script to bypass this heuristic."""
    server = _b()
    import scripts as _scripts_mod
    try:
        script_id = int(args.get("script_id"))
    except (TypeError, ValueError):
        return _err("script_id (integer) is required")
    try:
        return _scripts_mod.derive_shot_list(server._get_index(), script_id)
    except Exception as e:
        return _err(f"get_shot_list failed: {e}")


def list_scripts(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P5: list scripts newest-first. Filter by workspace_id."""
    server = _b()
    import scripts as _scripts_mod
    workspace_id = args.get("workspace_id")
    if workspace_id is not None and not isinstance(workspace_id, str):
        return _err("workspace_id must be a string when provided")
    limit = _limit_int(args.get("limit"), default=50, low=1, high=500)
    try:
        rows = _scripts_mod.list_scripts(
            server._get_index(), workspace_id=workspace_id, limit=limit)
    except Exception as e:
        return _err(f"list_scripts failed: {e}")
    return _ok(scripts=rows, count=len(rows))


def get_script(args: dict[str, Any]) -> dict[str, Any]:
    """v3 P5: fetch one script by id including beats + shot_list +
    source_yoinks citations."""
    server = _b()
    import scripts as _scripts_mod
    try:
        script_id = int(args.get("id") or args.get("script_id"))
    except (TypeError, ValueError):
        return _err("script id (integer) is required")
    try:
        row = _scripts_mod.get_script(server._get_index(), script_id)
    except Exception as e:
        return _err(f"get_script failed: {e}")
    if row is None:
        return _err("script not found")
    return _ok(script=row)


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


def get_transcript_reliability(args: dict[str, Any]) -> dict[str, Any]:
    """Return stored transcript reliability spans for a video_id.

    Detection is computed by the helper via POST /reliability/<video_id>/compute
    or automatically when the user opts in. The MCP tool is read-only so an
    agent cannot unexpectedly download a local Whisper model.
    """
    video_id = args.get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        return _err("video_id required")
    folder, _row = _b()._folder_for_video_id(video_id.strip())
    if not folder:
        return _err("yoink not found")
    reliability = _read_sidecar(folder).get("reliability")
    if not isinstance(reliability, dict):
        reliability = {"status": "not_computed", "spans": [], "span_count": 0}
    return _ok(video_id=video_id.strip(), reliability=reliability)


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
    "analyze_self_channel": ToolSpec(
        name="analyze_self_channel",
        description=(
            "v2.5 P3 your-channel mode: aggregate the user's own saved "
            "videos (those tagged is_self via channel-name recognition) "
            "into hook evolution, format evolution, performance trend by "
            "month, and a top-performers list. Pass `handle` to scope to "
            "one of the user's registered channels; omit for the union "
            "across every registered channel. `limit` caps the "
            "top_performers list (default 10, max 100). Pure local read."
        ),
        input_schema=_schema({
            "handle": {
                "type": "string",
                "description": "User channel handle (with or without @). Optional.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 10,
            },
        }, []),
        handler=analyze_self_channel,
        rate_limiter=_RateLimiter(30),
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
    "get_user_role": ToolSpec(
        name="get_user_role",
        description=(
            "v3.1 P2: report the user's persisted role (creator | "
            "researcher | marketer | mixed) + the dashboard emphasis "
            "(primary/secondary chip order + default sort) the helper "
            "computes from it. Read-only."
        ),
        input_schema=_schema({}, []),
        handler=get_user_role,
        rate_limiter=_RateLimiter(60),
    ),
    "set_user_role": ToolSpec(
        name="set_user_role",
        description=(
            "v3.1 P2: persist the user's role choice. Drives Library "
            "default sort + filter-chip emphasis on the dashboard. "
            "Bounded enum -- one of creator | researcher | marketer | "
            "mixed."
        ),
        input_schema=_schema({
            "role": {
                "type": "string",
                "enum": ["creator", "researcher", "marketer", "mixed"],
            },
        }, ["role"]),
        handler=set_user_role,
        rate_limiter=_RateLimiter(30),
    ),
    "check_live_status": ToolSpec(
        name="check_live_status",
        description=(
            "v3.1: probe a URL to find out if it is a live broadcast "
            "without extracting. Returns one of: not_live | live | "
            "upcoming | post_live | was_live. The agent uses this to "
            "decide between immediate extraction and 'wait until the "
            "broadcast ends' (the helper's live_stream_behavior "
            "setting handles the latter for /extract; this tool is "
            "the read-only probe path)."
        ),
        input_schema=_schema({
            "url": {"type": "string"},
        }, ["url"]),
        handler=check_live_status,
        rate_limiter=_RateLimiter(30),
    ),
    "add_podcast_feed": ToolSpec(
        name="add_podcast_feed",
        description=(
            "v3.1 podcast: register an RSS feed URL. Idempotent -- "
            "existing URL returns the same row. poll_interval_min "
            "default 60, range 15-1440."
        ),
        input_schema=_schema({
            "feed_url": {"type": "string"},
            "poll_interval_min": {"type": "integer",
                                    "minimum": 15, "maximum": 1440,
                                    "default": 60},
        }, ["feed_url"]),
        handler=add_podcast_feed,
        rate_limiter=_RateLimiter(30),
    ),
    "list_podcast_feeds": ToolSpec(
        name="list_podcast_feeds",
        description="v3.1 podcast: list registered RSS feeds newest-first.",
        input_schema=_schema({
            "enabled_only": {"type": "boolean", "default": False},
        }, []),
        handler=list_podcast_feeds,
        rate_limiter=_RateLimiter(60),
    ),
    "remove_podcast_feed": ToolSpec(
        name="remove_podcast_feed",
        description=(
            "v3.1 podcast: delete a feed + cascade its episodes."
        ),
        input_schema=_schema({
            "feed_id": {"type": "integer"},
        }, ["feed_id"]),
        handler=remove_podcast_feed,
        rate_limiter=_RateLimiter(30),
    ),
    "poll_podcast_feed": ToolSpec(
        name="poll_podcast_feed",
        description=(
            "v3.1 podcast: trigger one feed poll (HTTP GET + RSS/Atom "
            "parse + upsert episodes). Conditional GET via ETag/"
            "If-Modified-Since on subsequent polls so daily-news "
            "podcasts don't re-download an unchanged feed body."
        ),
        input_schema=_schema({
            "feed_id": {"type": "integer"},
        }, ["feed_id"]),
        handler=poll_podcast_feed,
        rate_limiter=_RateLimiter(30),
    ),
    "list_podcast_episodes": ToolSpec(
        name="list_podcast_episodes",
        description=(
            "v3.1 podcast: list episodes. Optional feed_id + status "
            "filters (new | queued | downloaded | transcribed | "
            "ignored). Newest published first."
        ),
        input_schema=_schema({
            "feed_id": {"type": "integer"},
            "status": {"type": "string",
                        "enum": ["new", "queued", "downloaded",
                                 "transcribed", "ignored"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000,
                       "default": 100},
        }, []),
        handler=list_podcast_episodes,
        rate_limiter=_RateLimiter(60),
    ),
    "download_podcast_episode": ToolSpec(
        name="download_podcast_episode",
        description=(
            "v3.1 podcast: download an episode's MP3 via yt-dlp + "
            "ffmpeg. Synchronous. Returns when the file lands at "
            "<data_root>/Podcasts/<feed-slug>/<episode-slug>.mp3 or "
            "yt-dlp errors. Idempotent -- skips re-download when the "
            "canonical path already has a non-zero file."
        ),
        input_schema=_schema({
            "episode_id": {"type": "integer"},
        }, ["episode_id"]),
        handler=download_podcast_episode,
        rate_limiter=_RateLimiter(10),
    ),
    "get_whisperx_status": ToolSpec(
        name="get_whisperx_status",
        description=(
            "v3.1: report whether the WhisperX runtime is importable + "
            "the currently-selected model size + the diarization "
            "default. Agents call this before transcribe to decide "
            "whether to surface an install prompt to the user."
        ),
        input_schema=_schema({}, []),
        handler=get_whisperx_status,
        rate_limiter=_RateLimiter(60),
    ),
    "transcribe_podcast_episode": ToolSpec(
        name="transcribe_podcast_episode",
        description=(
            "v3.1 podcast: run WhisperX on a downloaded episode. "
            "Synchronous. Reads audio_local_path; writes the JSON "
            "transcript next to the MP3. Returns the structured "
            "transcript metadata, OR consent_required=True when the "
            "first-time model download (200 MB - 2 GB) needs the user "
            "to opt in (re-issue with consent_given=True after the "
            "dashboard prompt records the opt-in), OR a runtime-not-"
            "installed error when whisperx isn't importable."
        ),
        input_schema=_schema({
            "episode_id": {"type": "integer"},
            "model": {"type": "string",
                       "enum": ["tiny", "base", "small", "medium", "large"]},
            "language": {"type": "string"},
            "diarize": {"type": "boolean"},
            "consent_given": {"type": "boolean"},
        }, ["episode_id"]),
        handler=transcribe_podcast_episode,
        rate_limiter=_RateLimiter(5),
    ),
    "add_monitored_playlist": ToolSpec(
        name="add_monitored_playlist",
        description=(
            "v3.1 mobile bridge: register a YouTube playlist URL to "
            "monitor for auto-uoinks. Idempotent on UNIQUE "
            "playlist_url. poll_interval_min default 5, range 1-1440."
        ),
        input_schema=_schema({
            "playlist_url": {"type": "string"},
            "name": {"type": "string"},
            "poll_interval_min": {"type": "integer", "minimum": 1,
                                    "maximum": 1440, "default": 5},
        }, ["playlist_url"]),
        handler=add_monitored_playlist,
        rate_limiter=_RateLimiter(30),
    ),
    "list_monitored_playlists": ToolSpec(
        name="list_monitored_playlists",
        description=("v3.1 mobile bridge: list registered playlists "
                      "newest-first."),
        input_schema=_schema({
            "enabled_only": {"type": "boolean", "default": False},
        }, []),
        handler=list_monitored_playlists,
        rate_limiter=_RateLimiter(60),
    ),
    "remove_monitored_playlist": ToolSpec(
        name="remove_monitored_playlist",
        description=("v3.1 mobile bridge: delete a playlist + cascade "
                      "its discovery events."),
        input_schema=_schema({
            "playlist_id": {"type": "integer"},
        }, ["playlist_id"]),
        handler=remove_monitored_playlist,
        rate_limiter=_RateLimiter(30),
    ),
    "poll_monitored_playlist": ToolSpec(
        name="poll_monitored_playlist",
        description=(
            "v3.1 mobile bridge: poll one playlist (yt-dlp "
            "--flat-playlist) + diff against last_seen_video_ids + "
            "auto-queue new videos via the existing pending_yoinks "
            "retry worker. Returns the new[] discovery list so the "
            "dashboard can show it under a 'from mobile playlist' "
            "label distinct from rate-limit retries."
        ),
        input_schema=_schema({
            "playlist_id": {"type": "integer"},
        }, ["playlist_id"]),
        handler=poll_monitored_playlist,
        rate_limiter=_RateLimiter(20),
    ),
    "list_monitored_playlist_events": ToolSpec(
        name="list_monitored_playlist_events",
        description=(
            "v3.1 mobile bridge: list per-discovery events. Optional "
            "filters: playlist_id, status (discovered | queued | "
            "extracted | failed). Newest first."
        ),
        input_schema=_schema({
            "playlist_id": {"type": "integer"},
            "status": {"type": "string",
                        "enum": ["discovered", "queued",
                                 "extracted", "failed"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000,
                       "default": 200},
        }, []),
        handler=list_monitored_playlist_events,
        rate_limiter=_RateLimiter(60),
    ),
    "get_user_taste": ToolSpec(
        name="get_user_taste",
        description=(
            "v2.5 S4 taste memory: return the consolidated TASTE.md "
            "(preferred hooks/formats, avoid list, top performance "
            "anchors). Generated from engagement events + persisted "
            "taste anchors. Read-only, no arguments."
        ),
        input_schema=_schema({}, []),
        handler=get_user_taste,
        rate_limiter=_RateLimiter(60),
    ),
    "get_user_memory": ToolSpec(
        name="get_user_memory",
        description=(
            "v2.5 S4 user memory: return the user's free-form USER.md "
            "notes (Channels I admire, My channel(s), Topics, Workflow "
            "notes). Hand-edited markdown -- the consolidator never "
            "overwrites this file. No arguments."
        ),
        input_schema=_schema({}, []),
        handler=get_user_memory,
        rate_limiter=_RateLimiter(60),
    ),
    "update_user_taste": ToolSpec(
        name="update_user_taste",
        description=(
            "v2.5 S4 taste anchors: set one taste anchor section "
            "(preferred_hooks | preferred_formats | avoid) and "
            "re-consolidate TASTE.md. `content` is markdown that "
            "replaces the section body verbatim -- bullets recommended."
        ),
        input_schema=_schema({
            "section": {
                "type": "string",
                "enum": ["preferred_hooks", "preferred_formats", "avoid"],
            },
            "content": {"type": "string"},
        }, ["section", "content"]),
        handler=update_user_taste,
        rate_limiter=_RateLimiter(30),
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
    "classify_facets": ToolSpec(
        name="classify_facets",
        description=(
            "Persist agent-classified facets + free-form tags for a video. "
            "Model-agnostic: the calling agent does the LLM work using its "
            "own model; this tool validates against bounded enums and writes "
            "to the row. The server fills performance_tier (channel-relative) "
            "and length_bucket (from duration) if you don't pass them."
        ),
        input_schema=_schema({
            "video_id": {"type": "string"},
            "format": {"type": "string",
                       "enum": ["one_shot", "talking_head", "tutorial", "listicle",
                                "narrative", "vlog", "interview",
                                "screen_recording", "broll_heavy"]},
            "performance_tier": {"type": "string",
                                 "enum": ["over", "average", "under"]},
            "length_bucket": {"type": "string",
                              "enum": ["short", "medium", "long", "deep"]},
            "production_style": {"type": "string", "maxLength": 64},
            "topic": {"type": "string", "maxLength": 64},
            "hook_type": {"type": "string", "maxLength": 64},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 32},
        }, ["video_id"]),
        handler=classify_facets,
        rate_limiter=_RateLimiter(120),
    ),
    "query_by_facets": ToolSpec(
        name="query_by_facets",
        description=(
            "Filter saved yoinks by facet values (format / performance_tier / "
            "hook_type / topic / length_bucket / tag). All filters "
            "AND-combined; newest first."
        ),
        input_schema=_schema({
            "format": {"type": "string"},
            "performance_tier": {"type": "string"},
            "hook_type": {"type": "string"},
            "topic": {"type": "string"},
            "length_bucket": {"type": "string"},
            "tag": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
        }, []),
        handler=query_by_facets,
        rate_limiter=_RateLimiter(60),
    ),
    "get_facet_taxonomy": ToolSpec(
        name="get_facet_taxonomy",
        description="Enum lists for the v2.5 facet axes (used for filter chips).",
        input_schema=_schema({}, []),
        handler=get_facet_taxonomy,
        rate_limiter=_RateLimiter(60),
    ),
    "get_transcript_reliability": ToolSpec(
        name="get_transcript_reliability",
        description=(
            "Return stored transcript reliability spans for a saved uoink by "
            "YouTube video_id. Read-only; computation is triggered by the "
            "helper endpoint or the user's auto-check setting."
        ),
        input_schema=_schema({
            "video_id": {
                "type": "string",
                "description": "YouTube video ID for the saved uoink.",
            },
        }, ["video_id"]),
        handler=get_transcript_reliability,
        rate_limiter=_RateLimiter(60),
    ),
    "assemble_workspace": ToolSpec(
        name="assemble_workspace",
        description=(
            "v3 P4 build workspace: pull a corpus slice for planning a "
            "video. Ranks yoinks by S1 facets (format match), performance "
            "tier (over > average > under), and S2 engagement value_score. "
            "Returns the slice + audience questions from comments + "
            "optional self-channel snapshot (if your_channel is set) + "
            "optional taste anchors (if S4 memory layer is available). "
            "Pure local read; the calling agent does any LLM analysis "
            "downstream. If `workspace_id` is provided the slice is "
            "persisted onto that row."
        ),
        input_schema=_schema({
            "format": {"type": "string"},
            "topic": {"type": "string"},
            "hook_target": {"type": "string"},
            "your_channel": {"type": "string"},
            "n_examples": {"type": "integer", "minimum": 1, "maximum": 100,
                             "default": 10},
            "workspace_id": {"type": "string"},
        }, []),
        handler=assemble_workspace,
        rate_limiter=_RateLimiter(30),
    ),
    "critique_against_corpus": ToolSpec(
        name="critique_against_corpus",
        description=(
            "v3 P4 critique tool. Two-phase: call WITHOUT `findings` to "
            "retrieve the assembled context (corpus slice + audience "
            "questions + taste anchors) -- the agent does the LLM "
            "analysis on that context. Call WITH `findings` (structured "
            "JSON object with hook_strength, structural_deviation, "
            "pacing_issues, missing_audience_hooks per ROADMAP P4) to "
            "persist the analysis to the workspace's critique log. "
            "Model-agnostic default; BYO-key mode accepted but not yet "
            "implemented on-server."
        ),
        input_schema=_schema({
            "workspace_id": {"type": "string"},
            "draft_text": {"type": "string"},
            "findings": {"type": "object"},
            "mode": {"type": "string", "enum": ["agent", "byo_key"]},
        }, ["workspace_id", "draft_text"]),
        handler=critique_against_corpus,
        rate_limiter=_RateLimiter(30),
    ),
    "list_workspaces": ToolSpec(
        name="list_workspaces",
        description=(
            "v3 P4: list build workspaces newest-first. Read-only."
        ),
        input_schema=_schema({
            "limit": {"type": "integer", "minimum": 1, "maximum": 500,
                       "default": 50},
        }, []),
        handler=list_workspaces,
        rate_limiter=_RateLimiter(60),
    ),
    "get_workspace": ToolSpec(
        name="get_workspace",
        description=(
            "v3 P4: fetch one workspace + its full critique log (every "
            "draft + findings combination the agent has persisted)."
        ),
        input_schema=_schema({
            "id": {"type": "string"},
            "workspace_id": {"type": "string"},
        }, []),
        handler=get_workspace,
        rate_limiter=_RateLimiter(60),
    ),
    "extract_claims": ToolSpec(
        name="extract_claims",
        description=(
            "v3 A2 (Loki-inspired): persist agent-extracted claims for "
            "a video. LOCKED FRAMING -- the calling agent does the LLM "
            "decomposition; this tool validates + writes. Each claim is "
            "{claim_text, check_worthiness? (0.0-1.0), context?}. NEVER "
            "auto-asserts truth verdicts -- surfaces checkable claims "
            "so the user can decide which to verify."
        ),
        input_schema=_schema({
            "video_id": {"type": "string"},
            "claims": {"type": "array", "items": {"type": "object"}},
            "mode": {"type": "string", "enum": ["agent", "byo_key"]},
        }, ["video_id", "claims"]),
        handler=extract_claims,
        rate_limiter=_RateLimiter(30),
    ),
    "verify_claim": ToolSpec(
        name="verify_claim",
        description=(
            "v3 A2: record evidence for one extracted claim. "
            "alignment_signal MUST be one of supports / contradicts / "
            "mixed / inconclusive. NEVER 'true' / 'false' / 'lie'. The "
            "user judges the verdict from the surfaced evidence."
        ),
        input_schema=_schema({
            "claim_id": {"type": "integer"},
            "evidence": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "Each: {source_url, quote, alignment_signal}. "
                    "alignment_signal enum is locked."
                ),
            },
            "mode": {"type": "string", "enum": ["agent", "byo_key"]},
        }, ["claim_id", "evidence"]),
        handler=verify_claim,
        rate_limiter=_RateLimiter(30),
    ),
    "list_claims": ToolSpec(
        name="list_claims",
        description=(
            "v3 A2: list extracted claims. Filter by video_id and/or "
            "status (extracted | verified | not-attempted)."
        ),
        input_schema=_schema({
            "video_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["extracted", "verified", "not-attempted"],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000,
                       "default": 200},
        }, []),
        handler=list_claims,
        rate_limiter=_RateLimiter(60),
    ),
    "get_claim": ToolSpec(
        name="get_claim",
        description="v3 A2: fetch one claim by id, with stored evidence.",
        input_schema=_schema({
            "id": {"type": "integer"},
            "claim_id": {"type": "integer"},
        }, []),
        handler=get_claim,
        rate_limiter=_RateLimiter(60),
    ),
    "generate_script": ToolSpec(
        name="generate_script",
        description=(
            "v3 P5 script studio: two-phase generator. Call WITHOUT "
            "`script` payload to retrieve grounding context (workspace "
            "metadata + assembled corpus slice + audience questions + "
            "optional taste anchors + optional self-channel snapshot). "
            "The calling agent does the writing using its own model. "
            "Call WITH `script` (a structured object with hook + beats "
            "+ body + cta + source_yoinks citations) to persist as a "
            "new versioned row. parent_script_id chains revisions."
        ),
        input_schema=_schema({
            "workspace_id": {"type": "string"},
            "script": {"type": "object"},
            "mode": {"type": "string", "enum": ["agent", "byo_key"]},
            "parent_script_id": {"type": "integer"},
        }, ["workspace_id"]),
        handler=generate_script,
        rate_limiter=_RateLimiter(30),
    ),
    "revise_script": ToolSpec(
        name="revise_script",
        description=(
            "v3 P5: revise an existing script grounded in critique "
            "findings. Two-phase like generate_script -- without "
            "`revised_script` returns previous + grounding for the "
            "agent to act on; with `revised_script` persists as a new "
            "version (parent_script_id auto-set to the prior id)."
        ),
        input_schema=_schema({
            "script_id": {"type": "integer"},
            "critique_findings": {"type": "object"},
            "revision_target": {"type": "string"},
            "revised_script": {"type": "object"},
            "mode": {"type": "string", "enum": ["agent", "byo_key"]},
        }, ["script_id"]),
        handler=revise_script,
        rate_limiter=_RateLimiter(30),
    ),
    "get_shot_list": ToolSpec(
        name="get_shot_list",
        description=(
            "v3 P5: derive (and persist) a default shot list from a "
            "script's beats + the parent workspace's S1 format facet. "
            "Per-beat row with format-specific cue suggestions. The "
            "calling agent can override by supplying shot_list directly "
            "in generate_script."
        ),
        input_schema=_schema({
            "script_id": {"type": "integer"},
        }, ["script_id"]),
        handler=get_shot_list,
        rate_limiter=_RateLimiter(60),
    ),
    "list_scripts": ToolSpec(
        name="list_scripts",
        description=(
            "v3 P5: list scripts newest-first. Optional workspace_id "
            "filter scopes to one workspace's history."
        ),
        input_schema=_schema({
            "workspace_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500,
                       "default": 50},
        }, []),
        handler=list_scripts,
        rate_limiter=_RateLimiter(60),
    ),
    "get_script": ToolSpec(
        name="get_script",
        description="v3 P5: fetch one script by id.",
        input_schema=_schema({
            "id": {"type": "integer"},
            "script_id": {"type": "integer"},
        }, []),
        handler=get_script,
        rate_limiter=_RateLimiter(60),
    ),
    # v3.2 Writing Studio (7 tools)
    "write_tweet": ToolSpec(
        name="write_tweet",
        description=(
            "v3.2 Writing Studio: two-phase tweet/thread generator. "
            "Phase 1 (no `body`) returns grounding (source yoink + "
            "creator credit + style anchors + Voice DNA prompt). "
            "Phase 2 (`body` present) persists + scans for Voice DNA "
            "violations + returns structured warnings (soft warn -- "
            "NEVER auto-blocks). Creator credit is required in the body."
        ),
        input_schema=_schema({
            "source_yoink_id": {"type": "string"},
            "angle": {"type": "string"},
            "target_length_chars": {"type": "integer"},
            "style_anchor_ids": {"type": "array",
                                   "items": {"type": "integer"}},
            "body": {"type": "string"},
            "source_credit_line": {"type": "string"},
            "skip_voice_dna_this_time": {"type": "boolean"},
            "suppress_credit": {"type": "boolean",
                                  "description": "Reject (400). Locked: "
                                  "credit is non-suppressible."},
            "tags": {"type": "array", "items": {"type": "string"}},
            "parent_id": {"type": "integer"},
        }, []),
        handler=write_tweet,
        rate_limiter=_RateLimiter(20),
    ),
    "write_blog": ToolSpec(
        name="write_blog",
        description=(
            "v3.2 Writing Studio: two-phase blog generator. Same shape "
            "as write_tweet but Phase 2 accepts title, dek, tags, and "
            "expects markdown body with a Source section. Soft-warn "
            "Voice DNA scan; creator credit non-suppressible."
        ),
        input_schema=_schema({
            "source_yoink_id": {"type": "string"},
            "angle": {"type": "string"},
            "target_length_words": {"type": "integer"},
            "style_anchor_ids": {"type": "array",
                                   "items": {"type": "integer"}},
            "body": {"type": "string"},
            "title": {"type": "string"},
            "dek": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "source_credit_line": {"type": "string"},
            "skip_voice_dna_this_time": {"type": "boolean"},
            "suppress_credit": {"type": "boolean"},
            "parent_id": {"type": "integer"},
        }, []),
        handler=write_blog,
        rate_limiter=_RateLimiter(10),
    ),
    "list_writing_pieces": ToolSpec(
        name="list_writing_pieces",
        description=(
            "v3.2 Writing Studio: list generated pieces newest-first. "
            "Optional `kind` (tweet|thread|blog) + `yoink_id` filters."
        ),
        input_schema=_schema({
            "kind": {"type": "string",
                      "enum": ["tweet", "thread", "blog"]},
            "yoink_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500,
                       "default": 100},
        }, []),
        handler=list_writing_pieces,
        rate_limiter=_RateLimiter(60),
    ),
    "get_writing_piece": ToolSpec(
        name="get_writing_piece",
        description="v3.2 Writing Studio: fetch one piece by id.",
        input_schema=_schema({
            "id": {"type": "integer"},
            "piece_id": {"type": "integer"},
        }, []),
        handler=get_writing_piece,
        rate_limiter=_RateLimiter(60),
    ),
    "add_style_anchor": ToolSpec(
        name="add_style_anchor",
        description=(
            "v3.2 Writing Studio: add a Substack-style voice anchor "
            "(URL or raw pasted text). User names each. Cap at 10 -- "
            "returns 422-shaped error when exceeded. URL ingestion "
            "extracts prose via the helper's page extractor (Universal "
            "Site PR); falls back to NULL raw_text when the extractor "
            "isn't bound yet."
        ),
        input_schema=_schema({
            "name": {"type": "string"},
            "source_type": {"type": "string",
                              "enum": ["url", "text"]},
            "source_value": {"type": "string"},
        }, ["name", "source_type", "source_value"]),
        handler=add_style_anchor,
        rate_limiter=_RateLimiter(30),
    ),
    "list_style_anchors": ToolSpec(
        name="list_style_anchors",
        description=("v3.2 Writing Studio: list style anchors + their "
                      "active flag + the helper's 10-anchor cap."),
        input_schema=_schema({
            "active_only": {"type": "boolean", "default": False},
        }, []),
        handler=list_style_anchors,
        rate_limiter=_RateLimiter(60),
    ),
    "remove_style_anchor": ToolSpec(
        name="remove_style_anchor",
        description="v3.2 Writing Studio: delete a style anchor.",
        input_schema=_schema({
            "anchor_id": {"type": "integer"},
            "id": {"type": "integer"},
        }, []),
        handler=remove_style_anchor,
        rate_limiter=_RateLimiter(30),
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
