"""Shared Uoink MCP tool registry.

Both transports use this module:

- uoink_mcp.py wraps it with the official MCP Python SDK over stdio.
- server.py wraps it with authenticated JSON-RPC HTTP endpoints.

The registry intentionally owns no extraction business logic. It binds to the
loaded server module and calls the same helpers used by Uoink's v1/v2 HTTP API.

The six brand-carrying tools were renamed from yoink_* to uoink_* in v2.1.
Their compatibility window ended in v2.5; v3 accepts canonical tool names
only.
"""

from __future__ import annotations

import uoink_usage
from copy import deepcopy

import base64
import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


_backend = None


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
    annotations: dict[str, Any] | None = None
    title: str | None = None


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
    takes a slug benefits: get_uoink_corpus, get_citation_map,
    get_uoink_health, analyze_comments, classify_hook."""
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


@uoink_usage.capture(lambda args: {"youtube": "youtube", "twitter": "x"}.get(
    _b()._detect_platform_from_url(args.get("url", "")), "other"))
def uoink_video(args: dict[str, Any]) -> dict[str, Any]:
    import _platform
    b = _b()
    raw_url = args.get("url")
    if not isinstance(raw_url, str):
        return _err("url required")
    url = b._normalize_youtube_url(raw_url.strip())
    if not url:
        return _err("URL must be a youtube.com or youtu.be video link")
    interval = _limit_int(args.get("interval"), default=30, low=5, high=300)

    refusal = _platform.capability_refusal(_platform.media_capability())
    if refusal is not None:
        return refusal
    b.DESKTOP_ROOT.mkdir(parents=True, exist_ok=True)
    started_at = b._now_iso()
    title = None
    folder = None
    current_phase = "metadata"
    with b._manual_extraction_ownership(url) as ownership:
        try:
            ownership.raise_if_unavailable()
            if ownership.conflict:
                raise RuntimeError(ownership.conflict)
            if ownership.completed_while_waiting and ownership.reused:
                result = dict(ownership.reused)
                corpus_path = result.get("corpus_path")
                result["yoink_md"] = (
                    Path(corpus_path).read_text(encoding="utf-8") if corpus_path else "")
            else:
                metadata = b._fetch_metadata(url)
                title = metadata.get("title") or "Untitled"
                topic = b._classify_topic(metadata)
                # Same source-derived folder as /extract, so two videos with
                # the same title never share (or fight over) one folder.
                folder = b._video_capture_folder(
                    b.DESKTOP_ROOT / b._topic_folder_name(topic), url, metadata)

                def phase_cb(phase):
                    nonlocal current_phase
                    current_phase = phase

                result = b._run_extraction(
                    url, interval, folder, metadata=metadata, topic=topic,
                    phase_callback=phase_cb)
        except BaseException as e:
            msg = b.friendly_error(e)
            detail = b.machine_error_detail(e)
            b._record_single_extract_job(
                url,
                started_at,
                error=msg,
                error_detail=detail,
                failure_phase=b._failure_phase(e, current_phase),
                long_video_mode=b.LONG_VIDEO_MODE_FULL,
                title=title,
                folder=folder,
            )
            return _err(msg)

    folder_value = result.get("folder") or (
        str(Path(result["corpus_path"]).parent) if result.get("corpus_path") else None)
    if not folder_value:
        return _err("Uoink reused an earlier capture of this video but could not find its folder.")
    folder_path = Path(folder_value)
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
    import _platform
    b = _b()
    raw_url = args.get("url")
    if not isinstance(raw_url, str):
        return _err("playlist URL invalid")
    url = b._normalize_playlist_url(raw_url.strip())
    if not url:
        return _err("playlist URL invalid")
    interval = _limit_int(args.get("interval"), default=30, low=5, high=300)
    refusal = _platform.capability_refusal(_platform.media_capability())
    if refusal is not None:
        return refusal
    playlist, error, _status = b._fetch_playlist_preview(url)
    if error:
        return _err(error)
    job_id, _job = b._create_playlist_job(playlist, interval)
    return _ok(job_id=job_id)


def get_job_status(args: dict[str, Any]) -> dict[str, Any]:
    import uoink_supervisor
    recovery = uoink_supervisor.status()
    b = _b()
    job_id = args.get("job_id")
    if not isinstance(job_id, str) or not b._is_valid_job_id(job_id):
        return {**_err("job id invalid"), "helper_recovery": recovery}
    job = b._get_public_job(job_id)
    if not job:
        return {**_err("job not found"), "helper_recovery": recovery}
    return _ok(job=job, helper_recovery=recovery)


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
    # Compatibility contract: `yoinks` and `yoinked_at` are frozen legacy
    # wire keys. The product and all human-readable messages use Uoink.
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
    from uoink_core.search_service import MODES, metadata
    mode = args.get("mode", "auto")
    if mode not in MODES:
        return _err("mode must be auto, keyword, semantic or hybrid")
    # Sprint 15: FTS5 keyword search via the library index instead of
    # read_text()-ing every corpus file. Return shape unchanged
    # ({slug, title, snippet, score}); optional channel / hook_type filters.
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return _err("query required")
    match = args.get("match", "forgiving")
    if match not in ("forgiving", "strict"):
        return _err("match must be forgiving or strict")
    limit = _limit_int(args.get("limit"), default=10, low=1, high=50)
    channel = args.get("channel")
    channel = channel.strip() if isinstance(channel, str) and channel.strip() else None
    hook_type = args.get("hook_type")
    hook_type = hook_type.strip() if isinstance(hook_type, str) and hook_type.strip() else None
    idx = _b()._get_index()
    page = idx.search_mode(query, limit, mode=mode, match=match,
                           filters={"channel": channel, "hook_type": hook_type},
                           keyword=lambda count, offset, override: {"results": idx.search(
                               query, count, channel=channel, hook_type=hook_type, match=override or match, passages=False)})
    rows = page["results"]
    results = []
    for r in rows:
        score = r.get("_score")
        results.append({
            "video_id": r.get("video_id"),
            "slug": r.get("slug"),
            "title": r.get("title"),
            "snippet": (r.get("_snippet") or "").strip(),
            # FTS5 bm25 is lower-is-better; negate so a higher score means a
            # better match, matching the old term-count score's direction.
            "score": -score if isinstance(score, (int, float)) else 0.0,
            **({"passage": r["passage"]} if "passage" in r else {}),
            **{key: r[key] for key in ("source_id", "passage_id", "span", "timestamp_seconds", "passage_verified", "citation_reason") if key in r},
        })
    return _ok(results=results, **metadata(page))


def get_uoink_corpus(args: dict[str, Any]) -> dict[str, Any]:
    slug = args.get("slug")
    folder, corpus = _find_yoink(slug)
    if not folder or not corpus:
        return _err("uoink not found")
    try:
        md = corpus.read_text(encoding="utf-8")
    except OSError as e:
        return _err(f"corpus read failed: {e}")
    sidecar = _read_sidecar(folder)
    video_id = sidecar.get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        video_id = None
    source_url = sidecar.get("source_url") or sidecar.get("url")
    platform = sidecar.get("platform")
    source_type = sidecar.get("source_type")
    source_lower = source_url.lower() if isinstance(source_url, str) else ""
    is_youtube = (
        platform == "youtube"
        or "youtube.com/" in source_lower
        or "youtu.be/" in source_lower
        or (platform is None and source_type in (None, "video"))
    )
    video_url = (
        f"https://www.youtube.com/watch?v={video_id}"
        if video_id and is_youtube
        else None
    )
    # Sprint 15: include the citation map alongside the markdown. Optional
    # field -- markdown-only consumers are unaffected.
    citations: list[dict[str, Any]] = []
    if video_id:
        try:
            citations = _b()._get_index().get_citations(video_id)
        except Exception:
            citations = []
    extra: dict[str, Any] = {}
    # Context-layer item 3: for an image uoink, the corpus markdown carries the
    # caption + source, but the pixels live in the image file. Hand a vision-
    # capable MCP client an honest, reachable pointer to the file so it can read
    # and describe the image at query time: the absolute path (for a client with
    # local filesystem access) and a token-gated /file URL (the same route the
    # dashboard renders previews through). No cloud vision runs here.
    if (sidecar.get("source_type") == "image"
            and isinstance(sidecar.get("image_filename"), str)):
        from urllib.parse import quote
        image_path = folder / sidecar["image_filename"]
        if image_path.exists():
            extra["image"] = {
                "path": str(image_path),
                "file_url": "/file?path=" + quote(str(image_path)),
                "mime": sidecar.get("mime"),
                "caption": sidecar.get("caption"),
                "source_url": sidecar.get("source_url"),
                "width": sidecar.get("width"),
                "height": sidecar.get("height"),
            }
    return _ok(
        corpus_md=md,
        folder=str(folder),
        video_id=video_id,
        video_url=video_url,
        source_url=source_url,
        citations=citations,
        **extra,
    )


def get_citation_map(args: dict[str, Any]) -> dict[str, Any]:
    """Return the transcript + screenshot citation map for a saved yoink,
    each entry carrying a source-aware timestamp link."""
    slug = args.get("slug")
    folder, corpus = _find_yoink(slug)
    if not folder or not corpus:
        return _err("uoink not found")
    video_id = _read_sidecar(folder).get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        return _err("uoink has no video_id")
    transcript: list[dict[str, Any]] = []
    screenshots: list[dict[str, Any]] = []
    for r in _b()._get_index().get_citations(video_id):
        if r.get("kind") == "screenshot":
            screenshots.append({
                "seq": r.get("seq"),
                "timestamp": r.get("timestamp_start"),
                "file_path": r.get("file_path"),
                "source_url": r.get("source_url"),
                "deep_link": (r.get("source_deep_link")
                              or r.get("youtube_deep_link")),
            })
        else:
            transcript.append({
                "seq": r.get("seq"),
                "timestamp_start": r.get("timestamp_start"),
                "timestamp_end": r.get("timestamp_end"),
                "text": r.get("text"),
                "source_url": r.get("source_url"),
                "deep_link": (r.get("source_deep_link")
                              or r.get("youtube_deep_link")),
            })
    return _ok(
        video_id=video_id,
        transcript_citations=transcript,
        screenshot_citations=screenshots,
    )


# ---- living library phase 1: clips + evidence cards ------------------------
# Both tools read only from the index (clips.py derives clips from the
# citation map) and, like corpus-read contract v1, never expose a filesystem
# path: no corpus_path, sidecar_path, folder, or file_path in any response.

_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
from library_cards import build_card, read_corpus_head


def _clean_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def search_clips(args: dict[str, Any]) -> dict[str, Any]:
    """Full-text search over transcript windows with source timing and links."""
    from uoink_core.search_service import MODES, metadata
    mode = args.get("mode", "auto")
    if mode not in MODES:
        return _err("mode must be auto, keyword, semantic or hybrid")
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return _err("query required")
    match = args.get("match", "forgiving")
    if match not in ("forgiving", "strict"):
        return _err("match must be forgiving or strict")
    limit = _limit_int(args.get("limit"), default=20, low=1, high=50)
    video_id = _clean_text(args.get("video_id"))
    channel = _clean_text(args.get("channel"))
    page = _b()._get_index().search_mode(query, limit, mode=mode, clips_only=True,
                                        video_id=video_id, filters={"channel": channel}, match=match)
    rows = page["results"]
    results = []
    for r in rows:
        score = r.get("_score")
        results.append({
            "clip_id": r.get("clip_id"),
            "video_id": r.get("video_id"),
            "slug": r.get("slug"),
            "title": r.get("title"),
            "channel": r.get("channel"),
            "start": r.get("start"),
            "end": r.get("end"),
            "text": r.get("text"),
            "deep_link": r.get("source_deep_link"),
            "timing": r.get("timing", "unknown"),
            **{key: r[key] for key in ("passage", "source_id", "passage_id", "span", "timestamp_seconds", "passage_verified", "citation_reason") if key in r},
            # bm25 is lower-is-better; negate so higher means better, the
            # same direction search_uoinks reports.
            "score": -score if isinstance(score, (int, float)) else 0.0,
        })
    return _ok(results=results, **metadata(page))


def get_evidence_card(args: dict[str, Any]) -> dict[str, Any]:
    """One item's identity plus its most quotable clips, spread across the
    timeline, ready to cite. Resolves by slug or video_id."""
    slug = args.get("slug")
    video_id = args.get("video_id")
    if not slug and not video_id:
        return _err("slug or video_id required")
    idx = _b()._get_index()
    row = None
    # Same identifier grammar as _find_yoink: anything else never reaches
    # the index. get_by_slug already excludes soft-deleted rows.
    if isinstance(slug, str) and _SLUG_RE.match(slug):
        row = idx.get_by_slug(slug)
    if row is None and isinstance(video_id, str) and video_id.strip():
        candidate = idx.get_yoink(video_id.strip())
        if candidate and candidate.get("deleted_at") is None:
            row = candidate
    if not row:
        return _err("uoink not found")
    profile = args.get("profile", "full")
    n_clips = args.get("n_clips")
    if n_clips is not None:
        n_clips = _limit_int(n_clips, default=10, low=1, high=20)
    try:
        card = build_card(row, idx.get_clips(row["video_id"]),
                          corpus_text=read_corpus_head(row.get("corpus_path")),
                          profile=profile, n_clips=n_clips)
    except ValueError as exc:
        return _err(str(exc))
    return _ok(**card)


def get_uoink_health(args: dict[str, Any]) -> dict[str, Any]:
    """Return the per-section extraction health score for a saved uoink."""
    slug = args.get("slug")
    folder, corpus = _find_yoink(slug)
    if not folder or not corpus:
        return _err("uoink not found")
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
        return _err("no health data for this uoink")
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
    15-1440. Audio auto-ingest is a separate opt-in and defaults off."""
    server = _b()
    import podcasts as _pod
    feed_url = args.get("feed_url")
    if not isinstance(feed_url, str) or not feed_url.strip():
        return _err("feed_url (string) is required")
    interval = args.get("poll_interval_min") or 60
    auto_ingest = args.get("auto_ingest", False)
    if not isinstance(auto_ingest, bool):
        return _err("auto_ingest must be a boolean when provided")
    try:
        return _ok(feed=_pod.add_feed(server._get_index(),
                                        feed_url.strip(),
                                        poll_interval_min=int(interval),
                                        auto_ingest=auto_ingest))
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
    """Trigger the same feed-poll path used by the 30-second scheduler."""
    server = _b()
    try:
        feed_id = int(args.get("feed_id"))
    except (TypeError, ValueError):
        return _err("feed_id (integer) is required")
    try:
        return server._poll_podcast_feed_for_watch(feed_id)
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
    already has a non-zero file. The live transcription pipeline reads
    audio_local_path to feed WhisperX."""
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
    import _platform
    import whisper_runner as _wr
    settings = server._read_settings() or {}
    return _ok(
        whisperx_available=_wr.is_whisperx_available(),
        **({"media_capability": _platform.media_capability()}
           if _platform.sys.platform == "darwin" else {}),
        selected_model=settings.get("whisper_model") or "base",
        supported_models=list(_wr._MODELS),
        diarization_default=bool(settings.get("diarization_default")),
    )


def transcribe_podcast_episode(args: dict[str, Any]) -> dict[str, Any]:
    """Queue local WhisperX work and return a durable job id."""
    server = _b()
    import whisper_runner as _wr
    try:
        episode_id = int(args.get("episode_id"))
    except (TypeError, ValueError):
        return _err("episode_id (integer) is required")
    settings = server._read_settings() or {}
    model = _wr.normalize_model(
        args.get("model") or settings.get("whisper_model"))
    diarize = bool(args.get("diarize")
                     if args.get("diarize") is not None
                     else settings.get("diarization_default"))
    consent_given = bool(args.get("consent_given"))
    language = args.get("language")
    result, _status = server._queue_podcast_transcription(
        episode_id, model=model, language=language, diarize=diarize,
        consent_given=consent_given)
    return result


def episode_to_corpus(args: dict[str, Any]) -> dict[str, Any]:
    """Publish a completed podcast transcript into the shared corpus."""
    server = _b()
    import podcasts as _pod
    try:
        episode_id = int(args.get("episode_id"))
    except (TypeError, ValueError):
        return _err("episode_id (integer) is required")
    try:
        result = _pod.episode_to_corpus(
            server._get_index(), episode_id, data_root=server.DATA_ROOT)
        episode = _pod.get_episode(server._get_index(), episode_id) or {}
        server.maybe_toast(
            "Podcast added to Uoink",
            f"{episode.get('title') or 'The episode'} is ready in your library.")
        return result
    except (LookupError, FileNotFoundError, ValueError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"episode_to_corpus failed: {exc}")


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
    # Phase 3: subscription-linked playlists poll through the service's
    # due-time/lease gate and never enqueue from detection.
    refresh = getattr(server, "_refresh_source_via_service", None)
    try:
        return _mp.poll_playlist(server._get_index(), playlist_id,
                                    normalize_video_to_canonical_url=_vid_to_url,
                                    fetch_entries=server._fetch_monitored_playlist_entries,
                                    refresh=refresh if callable(refresh) else None)
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
def _writing_grounding(yoink_id, style_anchor_ids, hook_type_lens=None):
    server = _b()
    import writing_studio as _ws  # noqa: WPS433
    return _ws.assemble_grounding(
        server._get_index(), yoink_id,
        style_anchor_ids=style_anchor_ids,
        hook_type_lens=hook_type_lens)


def _writing_persist(yoink_id, kind, body_text, *, title=None, dek=None,
                       tags=None, style_anchor_ids=None, angle=None,
                       target_length=None, parent_id=None,
                       suppress_credit=False,
                       skip_voice_dna_this_time=False,
                       source_credit_line=None,
                       mode=None):
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
        mode=(mode or _ws.COMPUTE_MODE_AGENT),
        voice_dna_warnings_enabled=bool(
            settings.get("voice_dna_warnings_enabled", True)),
        skip_voice_dna_this_time=skip_voice_dna_this_time,
        suppress_credit=suppress_credit,
    )


# ---- Path C: BYO-key direct generation (Fix 4B) ---------------------------
# When no MCP agent is connected but the user saved an Anthropic key in
# Settings, the dashboard's Generate button asks the helper to do the LLM
# call itself (mode="byo_key") instead of returning grounding-only. Voice DNA
# (prepended to the system prompt), the non-suppressible creator credit, and
# native attribution all apply -- the persisted piece is indistinguishable
# from one an agent wrote, except mode is recorded as byo_key.
_BYO_SOURCE_CHAR_CAP = 8000


def _byo_source_text(server, yoink_row) -> str:
    """A capped slab of the source material for the prompt: the sidecar
    transcript when present, else the corpus markdown. Best-effort -- an
    empty string is fine (the model still has the title/channel)."""
    if not yoink_row:
        return ""
    from pathlib import Path as _Path
    sidecar_path = yoink_row.get("sidecar_path") or ""
    if sidecar_path and _Path(sidecar_path).exists():
        try:
            data = json.loads(_Path(sidecar_path).read_text(encoding="utf-8"))
            segs = data.get("transcript") or []
            text = " ".join(
                str(s.get("text") or "").strip()
                for s in segs if isinstance(s, dict))
            if text.strip():
                return text[:_BYO_SOURCE_CHAR_CAP]
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    corpus_path = yoink_row.get("corpus_path") or ""
    if corpus_path and _Path(corpus_path).exists():
        try:
            return _Path(corpus_path).read_text(
                encoding="utf-8")[:_BYO_SOURCE_CHAR_CAP]
        except OSError:
            pass
    return ""


def _byo_build_prompts(kind, grounding, *, angle, target_length, source_text):
    """System + user prompt for the BYO-key call. Voice DNA is prepended to
    the system prompt; the creator credit line is supplied so the model emits
    it verbatim (it's non-suppressible and persist_piece re-checks it)."""
    import writing_studio as _ws  # noqa: WPS433
    import voice_dna  # noqa: WPS433
    credit = (grounding.get("source_credit") or {}).get(kind) or ""
    anchors = grounding.get("style_anchors") or []
    anchor_block = "\n\n".join(
        f"Style anchor '{a.get('name')}':\n{(a.get('raw_text') or '').strip()}"
        for a in anchors if (a.get("raw_text") or "").strip())

    if kind == _ws.KIND_BLOG:
        kind_rules = (
            "Write a short blog post grounded in the source. Return ONLY a "
            "JSON object with keys: title (string), dek (one-sentence "
            "standfirst), body (markdown string), tags (array of <=5 short "
            "strings). Put the Source credit line verbatim at the end of the "
            "body.")
        length_hint = (f"Aim for about {target_length} words of body."
                       if target_length else "Keep it tight and skimmable.")
    elif kind == _ws.KIND_THREAD:
        kind_rules = (
            "Write an X/Twitter thread grounded in the source. Number each "
            "post. Keep every post under 280 characters. Put the credit line "
            "verbatim in the final post. Return plain text only.")
        length_hint = (f"Aim for about {target_length} total characters "
                       "across the thread."
                       if target_length else "3-6 posts is plenty.")
    else:  # tweet
        kind_rules = (
            "Write a single X/Twitter post grounded in the source, under 280 "
            "characters. Include the credit line verbatim. Return plain text "
            "only.")
        length_hint = ""

    base_system = (
        "You are helping a creator turn their own captured research (a "
        "'uoink') into a post in their voice. Ground every claim in the "
        "supplied source. Do not invent facts. " + kind_rules + "\n\n"
        f"Creator credit line (include verbatim, do not alter or omit):\n{credit}"
    )
    system = voice_dna.prepend_system_prompt(base_system)

    user_parts = []
    if angle:
        user_parts.append(f"Angle / lens to emphasize: {angle}")
    hook_lens = grounding.get("hook_lens") or {}
    if hook_lens.get("directive"):
        user_parts.append(
            f"Hook lens ({hook_lens.get('type')}): {hook_lens['directive']}")
    if length_hint:
        user_parts.append(length_hint)
    if anchor_block:
        user_parts.append("Match the tone of these style anchors:\n"
                          + anchor_block)
    src_yoink = grounding.get("source_yoink") or {}
    head = (f"Source title: {src_yoink.get('title') or 'Untitled'}\n"
            f"Source channel: {src_yoink.get('channel') or 'unknown'}")
    user_parts.append(head)
    user_parts.append("Source material:\n" + (source_text or "(no transcript "
                                              "available; use title + channel)"))
    return system, "\n\n".join(user_parts), credit


def _byo_fatal_warnings(text):
    import voice_dna  # noqa: WPS433
    return [
        warning for warning in voice_dna.scan(text)
        if warning.get("category") == "The Big One"
    ]


def _byo_shape_generation(kind, text, fallback_tags):
    import writing_studio as _ws  # noqa: WPS433
    title = dek = None
    tags = fallback_tags or []
    body_text = text
    if kind == _ws.KIND_BLOG:
        parsed = _byo_extract_json(text)
        if isinstance(parsed, dict) and parsed.get("body"):
            body_text = str(parsed.get("body") or "")
            title = parsed.get("title") or None
            dek = parsed.get("dek") or None
            if isinstance(parsed.get("tags"), list):
                tags = [str(t) for t in parsed["tags"]][:5]
    return body_text, title, dek, tags


def _byo_voice_text(body_text, title, dek):
    return "\n\n".join(
        str(part) for part in (title, dek, body_text) if part
    )


def _byo_call_anthropic(server, key, *, system, user, max_tokens):
    try:
        resp = server._anthropic_messages(
            key, system=system, user=user, max_tokens=max_tokens)
        return server._anthropic_text(resp), None
    except server.AnthropicAPIError as e:
        if getattr(e, "status", None) == 401:
            try:
                server._mark_anthropic_key_invalid()
            except Exception as mark_error:  # noqa: BLE001
                server.log.warning(
                    "Path C could not mark Anthropic key invalid: %s",
                    mark_error)
            return None, _err(
                "Anthropic rejected the saved API key. Update it in Settings "
                "and try again.")
        server.log.warning("Path C Anthropic generation failed: %s", e)
        if getattr(e, "status", None) == 429:
            return None, _err(
                "Anthropic is rate-limiting this request. Try again shortly.")
        return None, _err(
            "Anthropic couldn't generate this piece. Try again shortly.")
    except Exception as e:  # noqa: BLE001
        server.log.warning("Path C generation failed: %s", e)
        return None, _err(
            "Direct generation couldn't finish. Try again shortly.")


def _byo_generate(kind, args):
    """Run the BYO-key generation for one piece and persist it.

    Fatal Voice DNA output gets exactly one regeneration attempt before any
    persistence. A second fatal result is returned unsaved.
    """
    server = _b()
    import writing_studio as _ws  # noqa: WPS433

    try:
        key = server._saved_anthropic_key()
    except Exception as e:  # noqa: BLE001
        server.log.warning("Path C key lookup failed: %s", e)
        return _err(
            "Direct generation couldn't read the saved key. "
            "Nothing was saved.")
    if not key:
        return _err(
            "No AI agent connected and no Anthropic key saved. Connect an "
            "agent, or add an Anthropic API key in Settings to generate "
            "directly.")

    yoink_id = args.get("source_yoink_id") or args.get("yoink_id")
    if yoink_id is not None and not isinstance(yoink_id, str):
        return _err("source_yoink_id must be a string")
    style_anchor_ids = args.get("style_anchor_ids") or []
    if not isinstance(style_anchor_ids, list):
        return _err("style_anchor_ids must be a list")
    try:
        hook_type_lens = _ws.normalize_hook_lens(args.get("hook_type_lens"))
    except ValueError as e:
        return _err(str(e))

    # The dashboard's composer signals tweet-vs-thread via `output_mode`,
    # not `kind`. Such a thread still PERSISTS as a tweet-kind piece
    # (matching the composer convention -- it splits the body), but it must
    # be PROMPTED as a thread, else BYO thread mode yields a single tweet.
    output_mode = str(args.get("output_mode") or "").strip()
    prompt_kind = kind
    if kind == _ws.KIND_TWEET and output_mode == _ws.KIND_THREAD:
        prompt_kind = _ws.KIND_THREAD

    try:
        grounding = _writing_grounding(
            yoink_id, style_anchor_ids, hook_type_lens)
        yoink_row = (
            server._get_index().get_yoink(yoink_id) if yoink_id else None)
        source_text = _byo_source_text(server, yoink_row)
    except Exception as e:  # noqa: BLE001
        server.log.warning("Path C grounding failed: %s", e)
        return _err(
            "Direct generation couldn't prepare the source material. "
            "Nothing was saved.")
    target_length = (args.get("target_length_words")
                     if kind == _ws.KIND_BLOG
                     else args.get("target_length_chars"))
    try:
        system, user, credit = _byo_build_prompts(
            prompt_kind, grounding, angle=args.get("angle"),
            target_length=target_length, source_text=source_text)
    except Exception as e:  # noqa: BLE001
        server.log.warning("Path C prompt build failed: %s", e)
        return _err(
            "Direct generation couldn't prepare the writing prompt. "
            "Nothing was saved.")

    max_tokens = 2400 if kind == _ws.KIND_BLOG else 1200
    text, error = _byo_call_anthropic(
        server, key, system=system, user=user, max_tokens=max_tokens)
    if error:
        return error

    try:
        body_text, title, dek, tags = _byo_shape_generation(
            kind, text, args.get("tags") or [])
        fatal_warnings = _byo_fatal_warnings(
            _byo_voice_text(body_text, title, dek))
    except Exception as e:  # noqa: BLE001
        server.log.warning("Path C generated output parse failed: %s", e)
        return _err(
            "Direct generation returned an unreadable response. "
            "Nothing was saved.")
    regenerated_for_voice_dna = False
    if fatal_warnings:
        regenerated_for_voice_dna = True
        phrases = ", ".join(sorted({
            str(warning.get("phrase") or "fatal pattern")
            for warning in fatal_warnings
        }))
        retry_user = (
            "PREVIOUS ATTEMPT CONTAINED CANNED PHRASES: "
            f"{phrases}. Regenerate the output strictly avoiding these "
            "patterns.\n\n" + user
        )
        text, error = _byo_call_anthropic(
            server, key, system=system, user=retry_user, max_tokens=max_tokens)
        if error:
            return error
        try:
            body_text, title, dek, tags = _byo_shape_generation(
                kind, text, args.get("tags") or [])
            fatal_warnings = _byo_fatal_warnings(
                _byo_voice_text(body_text, title, dek))
        except Exception as e:  # noqa: BLE001
            server.log.warning("Path C retry output parse failed: %s", e)
            return _err(
                "Direct generation returned an unreadable response. "
                "Nothing was saved.")
        if fatal_warnings:
            return {
                "ok": False,
                "error": (
                    "Generation still violated a fatal canned-phrase rule after "
                    "one retry. Nothing was saved."
                ),
                "voice_warnings": fatal_warnings,
                "retry_recommended": True,
            }

    # Creator credit is non-suppressible. The model is told to include it, but
    # if it didn't, append it so the piece still ships with attribution (and
    # persist_piece's credit check passes).
    try:
        if credit and not _ws._check_credit_present(body_text, credit):
            body_text = body_text.rstrip() + "\n\n" + credit
    except Exception as e:  # noqa: BLE001
        server.log.warning("Path C generated output validation failed: %s", e)
        return _err(
            "Direct generation returned an unreadable response. "
            "Nothing was saved.")

    try:
        piece = _writing_persist(
            yoink_id, kind, body_text,
            title=title, dek=dek, tags=tags,
            style_anchor_ids=style_anchor_ids,
            angle=args.get("angle"),
            target_length=target_length,
            parent_id=args.get("parent_id"),
            skip_voice_dna_this_time=bool(
                args.get("skip_voice_dna_this_time")),
            source_credit_line=credit or args.get("source_credit_line"),
            mode=_ws.COMPUTE_MODE_BYO_KEY)
    except ValueError as e:
        server.log.warning("Path C generated piece failed validation: %s", e)
        return _err(
            "The generated piece failed validation. Nothing was saved.")
    except Exception as e:  # noqa: BLE001
        server.log.warning("Path C persist failed: %s", e)
        return _err(
            "The generated piece couldn't be saved. Nothing was changed.")

    piece["mode"] = "persisted"
    piece["compute_path"] = _ws.COMPUTE_MODE_BYO_KEY
    piece["generated_via"] = "byo_key"
    piece["voice_dna_regenerated"] = regenerated_for_voice_dna
    return _ok(**piece)


def _byo_extract_json(text):
    """Pull the first top-level JSON object out of a model response (it may be
    fenced or have prose around it). Returns None when there's nothing
    parseable."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)
        stripped = stripped[1] if len(stripped) > 1 else text
        if stripped.lstrip().startswith("json"):
            stripped = stripped.lstrip()[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(stripped[start:end + 1])
    except json.JSONDecodeError:
        return None


def _byo_requested(args) -> bool:
    """True when the caller asked the helper to generate server-side (Path C)
    rather than just return grounding for an agent to write."""
    if args.get("generate") in (True, "true", "1", 1):
        return True
    return args.get("compute_mode") == "byo_key"


def write_tweet(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Writing Studio (tweet/thread): two-phase. Phase 1 -- no
    `body` field -> returns grounding (source yoink + creator credit +
    style anchors + Voice DNA). Agent writes the tweet/thread using
    its own model, INCLUDING the credit line verbatim. Phase 2 --
    `body` present -> persists + scans + returns warnings (NEVER
    auto-blocks; see VOICE-DNA.md soft-warn policy)."""
    import writing_studio as _ws  # noqa: WPS433
    kind = args.get("kind") or _ws.KIND_TWEET
    if kind not in (_ws.KIND_TWEET, _ws.KIND_THREAD):
        return _err("kind must be tweet or thread")
    yoink_id = (args.get("source_yoink_id")
                 or args.get("yoink_id"))
    if yoink_id is not None and not isinstance(yoink_id, str):
        return _err("source_yoink_id must be a string")
    style_anchor_ids = args.get("style_anchor_ids") or []
    if not isinstance(style_anchor_ids, list):
        return _err("style_anchor_ids must be a list")
    try:
        hook_type_lens = _ws.normalize_hook_lens(args.get("hook_type_lens"))
    except ValueError as e:
        return _err(str(e))
    body_text = args.get("body")
    if body_text is None:
        # Path C (Fix 4B): no agent to write the body, but the caller asked
        # the helper to generate it directly with the user's Anthropic key.
        if _byo_requested(args):
            return _byo_generate(kind, args)
        return _ok(mode="grounding_only", kind=kind,
                    context=_writing_grounding(yoink_id, style_anchor_ids,
                                               hook_type_lens),
                    next=(f"Produce the {kind} body (with credit line "
                          "included verbatim) and re-call with `body`."))
    try:
        piece = _writing_persist(
            yoink_id, kind, body_text,
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
    if args.get("kind") not in (None, "", _ws.KIND_BLOG):
        return _err("kind must be blog")
    yoink_id = (args.get("source_yoink_id")
                 or args.get("yoink_id"))
    if yoink_id is not None and not isinstance(yoink_id, str):
        return _err("source_yoink_id must be a string")
    style_anchor_ids = args.get("style_anchor_ids") or []
    if not isinstance(style_anchor_ids, list):
        return _err("style_anchor_ids must be a list")
    try:
        hook_type_lens = _ws.normalize_hook_lens(args.get("hook_type_lens"))
    except ValueError as e:
        return _err(str(e))
    body_text = args.get("body")
    if body_text is None:
        if _byo_requested(args):  # Path C (Fix 4B)
            return _byo_generate(_ws.KIND_BLOG, args)
        return _ok(mode="grounding_only", kind=_ws.KIND_BLOG,
                    context=_writing_grounding(yoink_id, style_anchor_ids,
                                               hook_type_lens),
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


# ---- shared capture parity ------------------------------------
def uoink_url(args: dict[str, Any]) -> dict[str, Any]:
    """Capture any URL through the helper's existing /extract/any logic."""
    server = _b()
    raw_url = args.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return _err("url (string) is required")

    class RegistryCaptureHandler(server.Handler):
        def __init__(self):
            self.status = None
            self.payload = None

        def _send_json(self, status: int, payload: dict) -> dict:
            uoink_usage.capture_result(payload)
            self.status = status
            self.payload = payload
            return payload

    probe = RegistryCaptureHandler()
    try:
        server.Handler._handle_extract_any(probe, dict(args))
    except Exception as exc:
        return _err(f"uoink_url failed: {exc}")
    if isinstance(probe.payload, dict):
        return probe.payload
    return _err("uoink_url returned no result")


@uoink_usage.capture("note")
def uoink_note(args: dict[str, Any]) -> dict[str, Any]:
    """Persist a text note through the same builders as POST /notes."""
    server = _b()
    import notes as _notes  # noqa: WPS433

    note = _notes.build_note(
        text=args.get("text"), title=args.get("title"), author=args.get("author")
    )
    if not note.get("ok"):
        return note
    try:
        video_id = _notes.persist_note(
            server._get_index(),
            note,
            data_root=server.DESKTOP_ROOT,
            topic_classifier=server._classify_topic,
        )
    except Exception as exc:
        return _err(f"uoink_note failed: {exc}")
    if not video_id:
        return _err("couldn't save the note")
    return _ok(
        video_id=video_id,
        slug=note["slug"],
        title=note["title"],
        author=note["author"],
        source_type=_notes.SOURCE_TYPE,
        platform=_notes.PLATFORM,
    )


@uoink_usage.capture("image")
def uoink_image(args: dict[str, Any]) -> dict[str, Any]:
    """Persist a base64 PNG, JPEG, or WebP through POST /images logic."""
    server = _b()
    import images as _images  # noqa: WPS433

    encoded = args.get("image_base64")
    if not isinstance(encoded, str) or not encoded.strip():
        return _err("image_base64 (string) is required")
    encoded = encoded.strip()
    if encoded.lower().startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        return _err(f"image_base64 is invalid: {exc}")
    built = _images.build_image(
        image_bytes,
        mime=args.get("mime"),
        filename=args.get("filename"),
        caption=args.get("caption"),
        source_url=args.get("source_url"),
        author=args.get("author"),
    )
    if not built.get("ok"):
        return built
    try:
        video_id = _images.persist_image(
            server._get_index(),
            built,
            image_bytes,
            data_root=server.DESKTOP_ROOT,
            topic_classifier=server._classify_topic,
        )
    except Exception as exc:
        return _err(f"uoink_image failed: {exc}")
    if not video_id:
        return _err("couldn't save the image")
    return _ok(
        video_id=video_id,
        slug=built["slug"],
        title=built["title"],
        author=built["author"],
        source_type=_images.SOURCE_TYPE,
        platform=_images.PLATFORM,
    )


@uoink_usage.capture("x")
def uoink_x(args: dict[str, Any]) -> dict[str, Any]:
    """Capture an X post through the same extractor as POST /extract/x."""
    server = _b()
    import page_extractor as _pages  # noqa: WPS433
    import x_extractor as _x  # noqa: WPS433

    if not (server._read_settings() or {}).get("x_text_capture_enabled"):
        return {
            "ok": False,
            "code": "disabled",
            "error": (
                "X text capture is off. Set x_text_capture_enabled to true "
                "in settings to try it."
            ),
        }
    raw_url = args.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return _err("url (string) is required")
    result = _x.extract_x_thread(raw_url.strip())
    if not result.get("ok"):
        return result
    try:
        video_id = _pages.persist_page_yoink(
            server._get_index(),
            result,
            data_root=server.DESKTOP_ROOT,
            source_type=_x.SOURCE_TYPE,
            subfolder="X",
            slug_prefix="x",
            topic_classifier=server._classify_topic,
        )
    except Exception as exc:
        return _err(f"uoink_x failed: {exc}")
    if not video_id:
        return _err("couldn't save the X post")
    server._save_x_video_poster(video_id, result)
    return _ok(
        video_id=video_id,
        title=result["title"],
        tweets_captured=result.get("tweets_captured", 0),
        metadata=result.get("metadata", {}),
    )


# ---- v3.2 Universal Site Uoinking ------------------------------------
@uoink_usage.capture("page")
def uoink_page(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Universal Site Uoinking: capture an allowed page as a yoink.

    Body shape: {url, render_mode?='js'|'static', include_screenshot?,
                  follow_links_depth?}. Returns structured markdown +
    metadata + links + images + screenshot path (when Crawl4AI is
    available) + the resulting yoink video_id.

    LOCKED LOCAL-FIRST: Crawl4AI runs on-device (lazy import); stdlib
    fallback when Crawl4AI isn't installed. Allowlist gate enforced --
    add the host via add_allowed_site first if it's not seeded."""
    server = _b()
    import page_extractor as _pe  # noqa: WPS433
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return _err("url (string) is required")
    render_mode = (args.get("render_mode")
                    or _pe.RENDER_MODE_JS).strip().lower()
    include_screenshot = bool(args.get("include_screenshot", True))
    try:
        follow_depth = int(args.get("follow_links_depth", 0))
    except (TypeError, ValueError):
        return _err("follow_links_depth must be an integer")
    try:
        result = _pe.extract_page(
            server._get_index(), url.strip(),
            render_mode=render_mode,
            include_screenshot=include_screenshot,
            follow_links_depth=follow_depth,
            enforce_allowlist=True)
    except Exception as e:
        return _err(f"uoink_page failed: {e}")
    if not result.get("ok"):
        return result   # already has the error shape
    try:
        video_id = _pe.persist_page_yoink(
            server._get_index(), result,
            data_root=server.DESKTOP_ROOT)
        result["video_id"] = video_id
    except Exception:
        result["video_id"] = None
    return result


@uoink_usage.capture("reddit")
def uoink_reddit_thread(args: dict[str, Any]) -> dict[str, Any]:
    """v3.3 Reddit capture: fetch a thread via its public .json (no API key),
    flatten the comment tree (depth + score limited), and persist it as a
    yoink with source_type='reddit_thread'.

    Body shape: {url, depth_limit?=4, score_threshold?=2}. Returns the yoink
    video_id, title, and how many comments cleared the filters. Runs
    on-device; no allowlist gate (the .json fetch is its own path)."""
    server = _b()
    import reddit_extractor as _re  # noqa: WPS433
    import page_extractor as _pe  # noqa: WPS433
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return _err("url (string) is required")

    def _bounded(value, default, lo, hi):
        try:
            return max(lo, min(int(value), hi))
        except (TypeError, ValueError):
            return default

    depth = _bounded(args.get("depth_limit"), _re.DEFAULT_DEPTH_LIMIT, 0, 10)
    score = _bounded(args.get("score_threshold"),
                     _re.DEFAULT_SCORE_THRESHOLD, -100, 100000)
    result = _re.extract_reddit_thread(url.strip(), depth_limit=depth,
                                       score_threshold=score)
    if not result.get("ok"):
        return result  # already in {ok: False, error, code} shape
    try:
        result["video_id"] = _pe.persist_page_yoink(
            server._get_index(), result, data_root=server.DESKTOP_ROOT,
            source_type=_re.SOURCE_TYPE, subfolder="Reddit",
            slug_prefix="reddit")
    except Exception as e:
        return _err(f"captured the thread but couldn't save it: {e}")
    return result


def list_allowed_sites(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Universal Site: list the user's allowed sites. Default
    seeds (youtube.com, youtu.be, x.com, twitter.com) are pre-added by
    migration 0015."""
    server = _b()
    import page_extractor as _pe  # noqa: WPS433
    active_only = bool(args.get("active_only"))
    rows = _pe.list_allowed(server._get_index(),
                                active_only=active_only)
    return _ok(sites=rows, count=len(rows),
                default_seeds=list(_pe.DEFAULT_ALLOW_SEEDS))


def add_allowed_site(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Universal Site: add a hostname or wildcard pattern
    ('*.docs.example.com'). Idempotent on UNIQUE url_pattern."""
    server = _b()
    import page_extractor as _pe  # noqa: WPS433
    pattern = args.get("url_pattern") or args.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        return _err("url_pattern (string) is required")
    try:
        return _ok(site=_pe.add_allowed(
            server._get_index(), pattern.strip()))
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"add_allowed_site failed: {e}")


def remove_allowed_site(args: dict[str, Any]) -> dict[str, Any]:
    """v3.2 Universal Site: remove a hostname or wildcard pattern from
    the allowlist."""
    server = _b()
    import page_extractor as _pe  # noqa: WPS433
    pattern = args.get("url_pattern") or args.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        return _err("url_pattern (string) is required")
    try:
        removed = _pe.remove_allowed(
            server._get_index(), pattern.strip())
    except Exception as e:
        return _err(f"remove_allowed_site failed: {e}")
    return _ok(removed=removed, url_pattern=pattern.strip().lower())


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
    hook_type_lens = args.get("hook_type_lens")
    try:
        parent_id = int(parent) if parent is not None else None
    except (TypeError, ValueError):
        return _err("parent_script_id must be an integer")
    import writing_studio as _ws  # noqa: WPS433 -- shared hook-lens taxonomy
    try:
        hook_type_lens = _ws.normalize_hook_lens(args.get("hook_type_lens"))
    except ValueError as e:
        return _err(str(e))
    try:
        return _scripts_mod.generate_script(
            server._get_index(), workspace_id.strip(),
            script=script, mode=mode, parent_script_id=parent_id,
            hook_type_lens=hook_type_lens)
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
    """Find recorded entity names, carrying source spans and stored timing."""
    name = args.get("entity") or args.get("name")
    if not isinstance(name, str) or not name.strip():
        return _err("entity name (string) is required")
    match = args.get("match", "forgiving")
    if match not in ("forgiving", "strict"):
        return _err("match must be forgiving or strict")
    limit = _limit_int(args.get("limit"), default=50, low=1, high=200)
    # Index.find_mentions normalises the name itself, so the raw entity
    # string is passed straight through.
    rows = _b()._get_index().find_mentions(name.strip(), limit, match=match)
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
        return _err("uoink not found")
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
        return _err("uoink not found")
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
        return _err("uoink not found")
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


# ===========================================================================
# Living Library, Phase 2 stage 1 (run J, 2026-09-04): the six registry
# adapters for the Librarian work queue.
#
# Contract: docs/library/PHASE2-CONTRACT-2026-09-04.md (phase2-v1-2026-09-04).
# Frozen input schemas: docs/library/phase2-contract/tool-schemas.json. The
# schemas below ARE that file, embedded so an installed helper needs no
# checkout; tests/test_library_adapters.py fails the moment the two drift.
#
# Division of labour (contract, "Lease and submission semantics"):
#   * library_work.py (Astra) owns domain validation and every state
#     transition. It is reached through ONE seam, _library_service(), so the
#     adapters build and test against an injected stand-in until that module
#     lands, and so an installed helper without it answers an explicit
#     `service_unavailable` error instead of raising ImportError.
#   * These adapters check arguments against the frozen JSON Schema (the
#     input contract, identical on every transport), attach the trusted
#     request context (index handle, server clock, librarian_apply_enabled)
#     and return the service's result in the contract envelope. They add no
#     alternate domain validation and never call a model or the network.
#   * Both HTTP and full stdio expose these adapters. The frozen input
#     schemas and dashboard-intent requirements are identical on both.
# ===========================================================================

_library_log = logging.getLogger("uoink.library")

LIBRARY_CONTRACT_VERSION = "phase2-v1-2026-09-04"
LIBRARY_SCHEMA_VERSION = 1
LIBRARY_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
# User-intent capabilities minted by the dashboard confirmation route live
# five minutes (contract, "Pins and authoritative recovery").
LIBRARY_INTENT_TTL_MS = 5 * 60 * 1000
LIBRARY_TOOL_NAMES = (
    "list_library_work",
    "claim_library_work",
    "submit_library_result",
    "apply_reshelving",
    "pin_shelf",
    "undo_library_apply",
)
# Service method behind each (tool, discriminator). The claim tool's `action`
# and the apply tool's `mode` pick the method (contract, "Service surface and
# adapter returns"); the other four map one-to-one.
LIBRARY_SERVICE_METHODS: dict[tuple[str, str | None], str] = {
    ("list_library_work", None): "list_work",
    ("claim_library_work", "claim"): "claim_work",
    ("claim_library_work", "renew"): "renew_attempt",
    ("claim_library_work", "release"): "release_attempt",
    ("claim_library_work", "cancel"): "cancel_attempt",
    ("submit_library_result", None): "submit_result",
    ("apply_reshelving", "preview"): "preview_apply",
    ("apply_reshelving", "apply"): "apply_preview",
    ("pin_shelf", None): "pin_shelf",
    ("undo_library_apply", None): "undo_apply",
}
# The dashboard confirmation route asks the service to mint and store the
# user-intent capability (library_user_intents is a substrate table, and the
# service is its only writer). Not in the contract's function table; named
# here so the seam has exactly one place to adapt if Astra names it otherwise.
LIBRARY_INTENT_METHOD = "mint_user_intent"

# The `$defs` block is byte-identical in all six frozen schemas; one copy.
_LIBRARY_DEFS: dict[str, Any] = {
    "id": {"type": "string", "minLength": 1, "maxLength": 200},
    "client": {"type": "string", "minLength": 1, "maxLength": 64},
    "key": {"type": "string", "minLength": 1, "maxLength": 200},
    "hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "token": {"type": "string", "pattern": "^[A-Za-z0-9_-]{43,128}$"},
    "revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "evidence": {
        "type": "object",
        "properties": {
            "basis": {"type": "string", "enum": ["packet", "fetched_full"]},
            "kind": {"type": "string", "enum": ["timed_clip", "text_only"]},
            "excerpt_id": {"$ref": "#/$defs/hash"},
            "card_hash": {"$ref": "#/$defs/hash"},
            "quote": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
        "required": ["basis", "kind", "excerpt_id", "card_hash", "quote"],
        "additionalProperties": False,
    },
    "membership": {
        "type": "object",
        "properties": {
            "shelf_id": {"$ref": "#/$defs/id"},
            "shelf_path": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 100},
                "minItems": 1,
                "maxItems": 3,
            },
            "confidence": {"$ref": "#/$defs/confidence"},
            "evidence": {"$ref": "#/$defs/evidence"},
        },
        "required": ["shelf_id", "shelf_path", "confidence", "evidence"],
        "additionalProperties": False,
    },
    "result": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "outcome": {"const": "assigned"},
                    "memberships": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/membership"},
                        "minItems": 1,
                        "maxItems": 3,
                    },
                },
                "required": ["outcome", "memberships"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "outcome": {
                        "type": "string",
                        "enum": ["unmapped", "unsupported", "error"],
                    },
                    "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                },
                "required": ["outcome", "reason"],
                "additionalProperties": False,
            },
        ]
    },
    "usage": {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "status": {"const": "reported"},
                    "model": {"type": "string", "minLength": 1, "maxLength": 200},
                    "input_tokens": {"type": "integer", "minimum": 0, "maximum": 2147483647},
                    "output_tokens": {"type": "integer", "minimum": 0, "maximum": 2147483647},
                    "cache_read_tokens": {"type": "integer", "minimum": 0, "maximum": 2147483647},
                    "cache_create_tokens": {"type": "integer", "minimum": 0, "maximum": 2147483647},
                    "wall_time_ms": {"type": "integer", "minimum": 0, "maximum": 2147483647},
                },
                "required": ["status", "model", "input_tokens", "output_tokens", "wall_time_ms"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "status": {"const": "unavailable"},
                    "model": {"type": "string", "minLength": 1, "maxLength": 200},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                    "wall_time_ms": {"type": "integer", "minimum": 0, "maximum": 2147483647},
                },
                "required": ["status", "reason"],
                "additionalProperties": False,
            },
        ]
    },
}


def _library_schema(body: dict[str, Any]) -> dict[str, Any]:
    return {"$schema": LIBRARY_JSON_SCHEMA_DIALECT, "$defs": _LIBRARY_DEFS, **body}


LIBRARY_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "list_library_work": _library_schema({
        "type": "object",
        "properties": {
            "run_id": {"$ref": "#/$defs/id"},
            "state": {
                "type": "string",
                "enum": ["all", "ready", "leased", "accepted", "unmapped",
                         "unsupported", "blocked", "cancelled"],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            "cursor": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": [],
        "additionalProperties": False,
    }),
    "claim_library_work": _library_schema({
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "action": {"const": "claim"},
                    "run_id": {"$ref": "#/$defs/id"},
                    "client_id": {"$ref": "#/$defs/client"},
                    "max_items": {"type": "integer", "minimum": 1, "maximum": 12, "default": 12},
                    "lease_seconds": {"type": "integer", "minimum": 60, "maximum": 900, "default": 900},
                },
                "required": ["action", "run_id", "client_id"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "action": {"const": "renew"},
                    "work_id": {"$ref": "#/$defs/id"},
                    "client_id": {"$ref": "#/$defs/client"},
                    "attempt_token": {"$ref": "#/$defs/token"},
                    "lease_seconds": {"type": "integer", "minimum": 60, "maximum": 900},
                },
                "required": ["action", "work_id", "client_id", "attempt_token", "lease_seconds"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["release", "cancel"]},
                    "work_id": {"$ref": "#/$defs/id"},
                    "client_id": {"$ref": "#/$defs/client"},
                    "attempt_token": {"$ref": "#/$defs/token"},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                },
                "required": ["action", "work_id", "client_id", "attempt_token", "reason"],
                "additionalProperties": False,
            },
        ]
    }),
    "submit_library_result": _library_schema({
        "type": "object",
        "properties": {
            "work_id": {"$ref": "#/$defs/id"},
            "client_id": {"$ref": "#/$defs/client"},
            "attempt_token": {"$ref": "#/$defs/token"},
            "submission_key": {"$ref": "#/$defs/key"},
            "schema_version": {"const": 1},
            "video_id": {"$ref": "#/$defs/id"},
            "source_revision": {"$ref": "#/$defs/hash"},
            "taxonomy_revision": {"$ref": "#/$defs/hash"},
            "packet_hash": {"$ref": "#/$defs/hash"},
            "result": {"$ref": "#/$defs/result"},
            "usage": {"$ref": "#/$defs/usage"},
        },
        "required": ["work_id", "client_id", "attempt_token", "submission_key",
                     "schema_version", "video_id", "source_revision",
                     "taxonomy_revision", "packet_hash", "result", "usage"],
        "additionalProperties": False,
    }),
    "apply_reshelving": _library_schema({
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "mode": {"const": "preview", "default": "preview"},
                    "run_id": {"$ref": "#/$defs/id"},
                    "expected_projection_revision": {"$ref": "#/$defs/revision"},
                    "activate_version": {"type": "boolean", "default": False},
                },
                "required": ["run_id", "expected_projection_revision"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "mode": {"const": "apply"},
                    "preview_id": {"$ref": "#/$defs/id"},
                    "expected_projection_revision": {"$ref": "#/$defs/revision"},
                    "delta_hash": {"$ref": "#/$defs/hash"},
                    "operation_key": {"$ref": "#/$defs/key"},
                },
                "required": ["mode", "preview_id", "expected_projection_revision",
                             "delta_hash", "operation_key"],
                "additionalProperties": False,
            },
        ]
    }),
    "pin_shelf": _library_schema({
        "type": "object",
        "properties": {
            "video_id": {"$ref": "#/$defs/id"},
            "shelf_id": {"$ref": "#/$defs/id"},
            "action": {"type": "string", "enum": ["pin", "unpin", "move"]},
            "expected_projection_revision": {"$ref": "#/$defs/revision"},
            "operation_key": {"$ref": "#/$defs/key"},
            "user_intent_token": {"$ref": "#/$defs/token"},
            "reason": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["video_id", "shelf_id", "action", "expected_projection_revision",
                     "operation_key", "user_intent_token"],
        "additionalProperties": False,
    }),
    "undo_library_apply": _library_schema({
        "type": "object",
        "properties": {
            "apply_id": {"$ref": "#/$defs/id"},
            "expected_projection_revision": {"$ref": "#/$defs/revision"},
            "operation_key": {"$ref": "#/$defs/key"},
            "user_intent_token": {"$ref": "#/$defs/token"},
        },
        "required": ["apply_id", "expected_projection_revision", "operation_key",
                     "user_intent_token"],
        "additionalProperties": False,
    }),
}


# ---- Frozen-schema validation (the input contract) --------------------------
# openapi_bridge.validate_arguments covers the small subset the older tools
# use and silently skips `$ref`, `oneOf`, `const`, `pattern`, `minLength` and
# `minItems`, all of which the frozen library schemas rely on. This validator
# executes exactly that subset -- nothing more general -- so every transport
# rejects the same malformed input with the same envelope before the service
# is asked anything. Booleans never satisfy integer/number, non-finite numbers
# never satisfy anything, and unknown fields are refused (contract, "Lease and
# submission semantics"). The service still validates recursively.

class LibrarySchemaError(ValueError):
    def __init__(self, field: str, reason: str):
        self.field = field or "request"
        self.reason = reason
        super().__init__(f"{self.field}: {reason}")


_LIBRARY_TYPE_LABELS = {
    "object": "an object",
    "array": "an array",
    "string": "a string",
    "integer": "an integer",
    "number": "a number",
    "boolean": "a boolean",
    "null": "null",
}


def _library_type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _library_json_equal(a: Any, b: Any) -> bool:
    """JSON equality: 1 != True, 1 == 1.0, otherwise same type and value."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def _library_resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    prefix = "#/$defs/"
    target = (root.get("$defs") or {}).get(ref[len(prefix):]) if ref.startswith(prefix) else None
    if not isinstance(target, dict):
        raise LibrarySchemaError("", f"unresolvable schema reference {ref}")
    return _library_resolve(target, root)


def _library_join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _library_branch_error(value: Any, branches: list, errors: list,
                          root: dict[str, Any], label: str) -> LibrarySchemaError:
    """When no oneOf branch matches, report the branch whose fixed
    discriminator (`action`, `mode`, `outcome`, `status`) the input selected,
    so the message names the field that is actually wrong. An input that
    omits the discriminator selects the branch whose discriminator has a
    default (apply_reshelving's preview branch)."""
    if isinstance(value, dict):
        defaulted: LibrarySchemaError | None = None
        for branch, error in zip(branches, errors):
            properties = _library_resolve(branch, root).get("properties") or {}
            for name, prop in properties.items():
                prop = _library_resolve(prop, root)
                if not ("const" in prop or "enum" in prop):
                    continue
                if name not in value:
                    if "default" in prop and defaulted is None:
                        defaulted = error
                    continue
                allowed = [prop["const"]] if "const" in prop else list(prop["enum"])
                if any(_library_json_equal(value[name], item) for item in allowed):
                    return error
        if defaulted is not None:
            return defaulted
    return LibrarySchemaError(label, "does not match any allowed shape")


def _library_validate(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> None:
    schema = _library_resolve(schema, root)
    label = path or "request"
    branches = schema.get("oneOf")
    if isinstance(branches, list):
        errors: list[LibrarySchemaError] = []
        matched = 0
        for branch in branches:
            try:
                _library_validate(value, branch, root, path)
            except LibrarySchemaError as exc:
                errors.append(exc)
            else:
                matched += 1
        if matched == 1:
            return
        if matched > 1:
            raise LibrarySchemaError(label, "matches more than one allowed shape")
        raise _library_branch_error(value, branches, errors, root, label)

    expected = schema.get("type")
    if isinstance(expected, str) and not _library_type_ok(value, expected):
        raise LibrarySchemaError(label, f"must be {_LIBRARY_TYPE_LABELS.get(expected, expected)}")
    if isinstance(value, float) and not math.isfinite(value):
        raise LibrarySchemaError(label, "must be a finite number")
    if "const" in schema and not _library_json_equal(value, schema["const"]):
        raise LibrarySchemaError(label, f"must be {json.dumps(schema['const'])}")
    enum = schema.get("enum")
    if isinstance(enum, list) and not any(_library_json_equal(value, item) for item in enum):
        raise LibrarySchemaError(label, "must be one of: " + ", ".join(json.dumps(item) for item in enum))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise LibrarySchemaError(label, f"must be at least {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise LibrarySchemaError(label, f"must be at most {maximum}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise LibrarySchemaError(label, f"must be at least {min_length} characters")
        if isinstance(max_length, int) and len(value) > max_length:
            raise LibrarySchemaError(label, f"must be at most {max_length} characters")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise LibrarySchemaError(label, f"must match {pattern}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise LibrarySchemaError(label, f"must contain at least {min_items} items")
        if isinstance(max_items, int) and len(value) > max_items:
            raise LibrarySchemaError(label, f"must contain at most {max_items} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _library_validate(item, item_schema, root, f"{label}[{index}]")

    if isinstance(value, dict):
        properties = schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        required = schema.get("required")
        if isinstance(required, list):
            for name in required:
                if name not in value:
                    raise LibrarySchemaError(_library_join(path, name), "is required")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    raise LibrarySchemaError(_library_join(path, str(name)), "is not an allowed field")
        for name, item in value.items():
            prop = properties.get(name)
            if isinstance(prop, dict):
                _library_validate(item, prop, root, _library_join(path, name))


def library_validate_arguments(tool_name: str, arguments: Any) -> LibrarySchemaError | None:
    """First input-contract violation of `arguments` against the frozen
    schema of one library tool, or None. Every transport routes through
    this before the service is called."""
    schema = LIBRARY_TOOL_SCHEMAS[tool_name]
    if not isinstance(arguments, dict):
        return LibrarySchemaError("", "must be an object")
    try:
        _library_validate(arguments, schema, schema, "")
    except LibrarySchemaError as exc:
        return exc
    return None


# ---- Envelope ---------------------------------------------------------------

def _library_ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, "schema_version": LIBRARY_SCHEMA_VERSION, **fields}


def _library_error(code: str, message: str, *, retryable: bool = False,
                   details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": LIBRARY_SCHEMA_VERSION,
        "error": {
            "code": code,
            "message": message,
            "retryable": bool(retryable),
            "details": dict(details) if isinstance(details, dict) else {},
        },
    }


def library_invalid_request(error: LibrarySchemaError) -> dict[str, Any]:
    return _library_error("invalid_request", str(error),
                          details={"field": error.field, "reason": error.reason})


def _library_service_unavailable(reason: str = "not_installed") -> dict[str, Any]:
    return _library_error(
        "service_unavailable",
        "The Librarian service (library_work) is not available in this helper "
        "build; no work was read or changed.",
        details={"module": "library_work", "reason": reason},
    )


def _library_normalize(result: Any, tool_name: str) -> dict[str, Any]:
    """Coerce a service return value into the contract envelope without
    rewriting its content. A malformed return is an internal error, never a
    fabricated success."""
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        _library_log.error("library %s: service returned a malformed response", tool_name)
        return _library_error("internal_error",
                              "The Librarian service returned a malformed response.",
                              details={"tool": tool_name})
    out = dict(result)
    out.setdefault("schema_version", LIBRARY_SCHEMA_VERSION)
    if out["ok"] is False:
        error = out.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            error = dict(error)
            error.setdefault("message", error["code"])
            error["retryable"] = bool(error.get("retryable", False))
            error["details"] = error["details"] if isinstance(error.get("details"), dict) else {}
        else:
            error = {
                "code": "service_error",
                "message": error if isinstance(error, str) else "The Librarian service refused the request.",
                "retryable": False,
                "details": {},
            }
        out["error"] = error
    return out


# ---- The seam ---------------------------------------------------------------

_LIBRARY_SERVICE_MISSING = object()
_LIBRARY_SERVICE_BROKEN = object()
_library_service_lock = threading.Lock()
_library_service_override: Any = None
_library_service_resolved: Any = None


def set_library_service(service: Any) -> None:
    """Inject the object the adapters call (tests use a deterministic
    in-memory stand-in; an integrator may wrap the real module). Passing
    None clears the override and forgets any cached import result."""
    global _library_service_override, _library_service_resolved
    with _library_service_lock:
        _library_service_override = service
        _library_service_resolved = None
        _library_status_cache.clear()


def _library_service() -> Any:
    """The one import seam for library_work.py. Returns the injected stand-in
    when set, else the module, else None when it is not installed (or its
    import failed, which is logged once)."""
    global _library_service_resolved
    with _library_service_lock:
        if _library_service_override is not None:
            return _library_service_override
        if _library_service_resolved is None:
            try:
                import library_work  # Astra's module; absent until integration.
            except ImportError:
                _library_service_resolved = _LIBRARY_SERVICE_MISSING
            except Exception:
                _library_log.exception("library_work import failed")
                _library_service_resolved = _LIBRARY_SERVICE_BROKEN
            else:
                _library_service_resolved = library_work
        if _library_service_resolved in (_LIBRARY_SERVICE_MISSING, _LIBRARY_SERVICE_BROKEN):
            return None
        return _library_service_resolved


def _library_service_reason() -> str:
    return "import_failed" if _library_service_resolved is _LIBRARY_SERVICE_BROKEN else "not_installed"


def _library_apply_enabled(backend: Any) -> bool:
    """librarian_apply_enabled from the helper's settings; default off, and
    off whenever the settings cannot be read."""
    reader = getattr(backend, "_read_settings", None)
    try:
        settings = reader() if callable(reader) else {}
    except Exception:
        _library_log.exception("library: settings unreadable; apply stays off")
        settings = {}
    return isinstance(settings, dict) and settings.get("librarian_apply_enabled") is True


def _library_context(transport: str, **extra: Any) -> dict[str, Any]:
    """The trusted request context the service receives beside the JSON
    arguments. Registry callers carry no user authority: only a
    user_intent_token minted by the dashboard route can grant it."""
    backend = _b()
    context: dict[str, Any] = {
        "contract_version": LIBRARY_CONTRACT_VERSION,
        "schema_version": LIBRARY_SCHEMA_VERSION,
        "transport": transport,
        "actor": "registry",
        "now_ms": int(time.time() * 1000),
        "apply_enabled": _library_apply_enabled(backend),
        "index": backend._get_index(),
        # Run N acceptance N-1: every transport authenticates with the same
        # per-install helper token, so the trusted session a dashboard-minted
        # capability binds to is the same session a tool call consumes it
        # under. Derived here from the backend, never from tool JSON.
        "session_hash": _library_trusted_session(backend),
    }
    context.update(extra)
    return context


def _library_trusted_session(backend: Any) -> str | None:
    """The helper's trusted session hash (server._library_session_hash), or
    None for a backend that has no token-derived session (test doubles)."""
    derive = getattr(backend, "_library_session_hash", None)
    if not callable(derive):
        return None
    try:
        value = derive()
    except Exception:
        _library_log.exception("library: trusted session unavailable")
        return None
    return value if isinstance(value, str) and value else None


def _library_context_or_none(transport: str, **extra: Any) -> dict[str, Any] | None:
    """_library_context, with an unopenable index logged and reported as None
    so no exception text (which can carry a local path) reaches a client."""
    try:
        return _library_context(transport, **extra)
    except Exception:
        _library_log.exception("library (%s): request context unavailable", transport)
        return None


_LIBRARY_RATE_LIMITERS: dict[str, _RateLimiter] = {
    # A claim/submit loop over a 548-item copy in batches of 12 submits in
    # bursts; the ceilings leave headroom for that while still bounding an
    # agent stuck in a retry loop. Preview/apply/pin/undo are human-paced.
    "list_library_work": _RateLimiter(60),
    "claim_library_work": _RateLimiter(60),
    "submit_library_result": _RateLimiter(120),
    "apply_reshelving": _RateLimiter(30),
    "pin_shelf": _RateLimiter(30),
    "undo_library_apply": _RateLimiter(30),
    "library_intent": _RateLimiter(30),
}


def _library_discriminator(tool_name: str, args: dict[str, Any]) -> str | None:
    if tool_name == "claim_library_work":
        return args.get("action")
    if tool_name == "apply_reshelving":
        return args.get("mode", "preview")
    return None


def _library_is_real_module(service: Any) -> bool:
    """True for Astra's library_work module (frozen surface: module-level
    ``fn(index, RequestContext, args)`` delegating to
    ``index.library_service()``); False for an injected stand-in, which keeps
    the test-only ``fn(args, context_dict)`` shape."""
    return hasattr(service, "RequestContext") and hasattr(service, "LibraryWorkService")


def _library_dispatch(service: Any, fn: Any, args: dict[str, Any],
                      context: dict[str, Any]) -> Any:
    """Run F/M acceptance M-1: the adapters were built against a stand-in
    whose methods took ``(arguments, context)``; the real module exports
    ``fn(index, context, args)`` and its endpoints require a
    ``library_work.RequestContext``. Translate the adapter's trusted dict
    context into that object and route the apply setting through the same
    service instance the endpoint will use."""
    if not _library_is_real_module(service):
        return fn(dict(args), context)
    index = context["index"]
    actor = context.get("actor", "registry")
    request_context = service.RequestContext(
        authenticated=True,
        client_id=args.get("client_id") if isinstance(args.get("client_id"), str) else None,
        session_id=context.get("session_hash") or f"{context.get('transport', 'registry')}",
        operator=(actor == "server"),
        local_user_confirmed=(actor == "user"),
    )
    # librarian_apply_enabled lives in the helper's settings; the service
    # instance re-checks it on its own transaction boundary, so keep the two
    # in step on every call rather than only at construction.
    index.library_service().librarian_apply_enabled = bool(context.get("apply_enabled"))
    return fn(index, request_context, dict(args))


def _library_invoke(method: str, args: dict[str, Any], context: dict[str, Any],
                    tool_name: str) -> dict[str, Any]:
    service = _library_service()
    if service is None:
        return _library_service_unavailable(_library_service_reason())
    fn = getattr(service, method, None)
    if not callable(fn):
        _library_log.error("library %s: service lacks %s", tool_name, method)
        return _library_error("service_unavailable",
                              f"The Librarian service does not implement {method}.",
                              details={"module": "library_work", "method": method})
    try:
        result = _library_dispatch(service, fn, args, context)
    except Exception:
        # Never echo the exception: it may carry SQL text or local paths.
        _library_log.exception("library %s (%s) raised", tool_name, method)
        return _library_error("internal_error",
                              "The Librarian service raised an unexpected error; "
                              "see the helper log.",
                              details={"tool": tool_name, "method": method})
    return _library_normalize(result, tool_name)


def _library_call(tool_name: str, args: dict[str, Any], *, transport: str = "registry") -> dict[str, Any]:
    """Common adapter path for the six tools on every transport: rate limit,
    frozen-schema check, default-off apply gate, trusted context, service."""
    try:
        _LIBRARY_RATE_LIMITERS[tool_name].check()
    except RateLimitExceeded as exc:
        return _library_error("rate_limited", str(exc), retryable=True,
                              details={"tool": tool_name})
    error = library_validate_arguments(tool_name, args)
    if error is not None:
        return library_invalid_request(error)
    method = LIBRARY_SERVICE_METHODS[(tool_name, _library_discriminator(tool_name, args))]
    if _library_service() is None:
        # Resolve the seam before touching the index: an unavailable service
        # must not open the database as a side effect of reporting itself.
        return _library_service_unavailable(_library_service_reason())
    context = _library_context_or_none(transport)
    if context is None:
        return _library_error("internal_error",
                              "The helper's index is unavailable; see the helper log.",
                              retryable=True, details={"tool": tool_name})
    if method == "apply_preview" and not context["apply_enabled"]:
        # Brief reservation 10 / contract "Preview, apply and churn":
        # librarian_apply_enabled=false is the shipping default and no client
        # field can lift it. Preview stays available. The service re-checks
        # context["apply_enabled"] on its own transaction boundary.
        return _library_error(
            "apply_disabled",
            "Applying labels is disabled on this helper "
            "(librarian_apply_enabled=false); preview remains available.",
            details={"setting": "librarian_apply_enabled"},
        )
    return _library_invoke(method, args, context, tool_name)


def list_library_work(args: dict[str, Any]) -> dict[str, Any]:
    return _library_call("list_library_work", args)


def claim_library_work(args: dict[str, Any]) -> dict[str, Any]:
    return _library_call("claim_library_work", args)


def submit_library_result(args: dict[str, Any]) -> dict[str, Any]:
    return _library_call("submit_library_result", args)


def apply_reshelving(args: dict[str, Any]) -> dict[str, Any]:
    return _library_call("apply_reshelving", args)


def pin_shelf(args: dict[str, Any]) -> dict[str, Any]:
    return _library_call("pin_shelf", args)


def undo_library_apply(args: dict[str, Any]) -> dict[str, Any]:
    return _library_call("undo_library_apply", args)


# ---- Dashboard user-intent confirmation -------------------------------------

def _library_intent_operation_schema(kind: str) -> dict[str, Any]:
    """The pin_shelf / undo_library_apply input schema minus the token the
    route is about to mint: the canonical operation the capability binds."""
    source = LIBRARY_TOOL_SCHEMAS["pin_shelf" if kind == "pin" else "undo_library_apply"]
    properties = {k: v for k, v in source["properties"].items() if k != "user_intent_token"}
    return _library_schema({
        "type": "object",
        "properties": properties,
        "required": [name for name in source["required"] if name != "user_intent_token"],
        "additionalProperties": False,
    })


LIBRARY_INTENT_REQUEST_SCHEMA: dict[str, Any] = _library_schema({
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["pin", "undo"]},
        "operation": {"type": "object"},
        # The dashboard sends this only from the confirmation control of a
        # displayed delta; it is a product confirmation, not a generic ack.
        "confirmed": {"const": True},
    },
    "required": ["kind", "operation", "confirmed"],
    "additionalProperties": False,
})


def library_mint_user_intent(body: Any, *, session_hash: str) -> dict[str, Any]:
    """Behind POST /library/intent (server.py owns auth, origin and rate
    limit). Validates the confirmation body and the canonical operation
    against the frozen schemas, then asks the service to mint, store and
    return the short-lived capability bound to that operation, the expected
    revision and the dashboard session."""
    try:
        _LIBRARY_RATE_LIMITERS["library_intent"].check()
    except RateLimitExceeded as exc:
        return _library_error("rate_limited", str(exc), retryable=True,
                              details={"route": "/library/intent"})
    if not isinstance(body, dict):
        return library_invalid_request(LibrarySchemaError("", "must be an object"))
    try:
        _library_validate(body, LIBRARY_INTENT_REQUEST_SCHEMA, LIBRARY_INTENT_REQUEST_SCHEMA, "")
        operation_schema = _library_intent_operation_schema(body["kind"])
        _library_validate(body["operation"], operation_schema, operation_schema, "operation")
    except LibrarySchemaError as exc:
        return library_invalid_request(exc)
    if not isinstance(session_hash, str) or len(session_hash) != 64:
        return _library_error("internal_error", "The dashboard session could not be identified.")
    if _library_service() is None:
        return _library_service_unavailable(_library_service_reason())
    context = _library_context_or_none(
        "dashboard",
        actor="user",
        session_hash=session_hash,
        intent_ttl_ms=LIBRARY_INTENT_TTL_MS,
    )
    if context is None:
        return _library_error("internal_error",
                              "The helper's index is unavailable; see the helper log.",
                              retryable=True, details={"route": "/library/intent"})
    request = {"kind": body["kind"], "operation": dict(body["operation"])}
    return _library_invoke(LIBRARY_INTENT_METHOD, request, context, "library_intent")


# ---- /health and dashboard status -------------------------------------------

_LIBRARY_STATUS_TTL_SEC = 5.0
_library_status_cache: dict[str, Any] = {}


def _library_count(counts: Any, key: str) -> int:
    """Counts by work state may arrive flat or nested under `work`; either
    way a missing state is zero."""
    if isinstance(counts, dict):
        value = counts.get(key)
        if value is None and isinstance(counts.get("work"), dict):
            value = counts["work"].get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


def _library_status_from_list(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("ok") is not True:
        code = None
        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            code = result["error"].get("code")
        return {"status": "error", "waiting_for_client": False, "ready": 0, "leased": 0,
                "run_revision": None, "recovery_state": None, "error_code": code}
    counts = result.get("counts")
    waiting = result.get("waiting_for_client") is True
    ready = _library_count(counts, "ready")
    leased = _library_count(counts, "leased")
    recovery = result.get("recovery_state")
    if recovery in ("pending", "conflict"):
        status = "recovery_pending"
    elif waiting:
        status = "waiting_for_client"
    elif leased:
        status = "collecting"
    else:
        status = "idle"
    revision = result.get("run_revision")
    return {
        "status": status,
        "waiting_for_client": waiting,
        "ready": ready,
        "leased": leased,
        "run_revision": revision if isinstance(revision, int) and not isinstance(revision, bool) else None,
        "recovery_state": recovery if isinstance(recovery, str) else None,
        "error_code": None,
    }


def library_status(index: Any, *, apply_enabled: bool, now: float | None = None) -> dict[str, Any]:
    """The `library` block of /health: whether staged work is waiting for a
    subscribed client (contract, "Dispatch boundaries"). Read-only, cached
    for a few seconds because /health is polled, and it never raises. The
    caller passes an already-open index handle; this function opens nothing."""
    now = time.monotonic() if now is None else now
    cached = _library_status_cache.get("payload")
    if cached is not None and now - _library_status_cache.get("at", -1e9) < _LIBRARY_STATUS_TTL_SEC:
        payload = dict(cached)
    else:
        service = _library_service()
        if service is None:
            payload = {"status": "unavailable", "waiting_for_client": False, "ready": 0,
                       "leased": 0, "run_revision": None, "recovery_state": None,
                       "error_code": None}
        else:
            context = {
                "contract_version": LIBRARY_CONTRACT_VERSION,
                "schema_version": LIBRARY_SCHEMA_VERSION,
                "transport": "health",
                "actor": "server",
                "now_ms": int(time.time() * 1000),
                "apply_enabled": bool(apply_enabled),
                "index": index,
                "session_hash": _library_trusted_session(_b()),
            }
            fn = getattr(service, "list_work", None)
            try:
                result = (_library_dispatch(service, fn, {"limit": 1}, context)
                          if callable(fn) else None)
            except Exception:
                _library_log.exception("library status: list_work raised")
                result = None
            payload = _library_status_from_list(result)
        _library_status_cache["payload"] = dict(payload)
        _library_status_cache["at"] = now
    payload["apply_enabled"] = bool(apply_enabled)
    payload["contract_version"] = LIBRARY_CONTRACT_VERSION
    return payload


# ===========================================================================
# Living Library, Phase 3 (run AM, 2026-09-07): the four standing-source
# registry adapters and the dashboard consent-intent seam.
#
# Contract: docs/library/PHASE3-CONTRACT-2026-09-07.md (phase3-v1-2026-09-07),
# "Registry and dashboard contract". The frozen input schemas live in
# source_subscriptions.TOOL_SCHEMAS (one copy, embedded so an installed helper
# needs no checkout); the adapters here only attach the trusted transport
# context and rate limits. Both HTTP (server.py /sources/*) and MCP call
# sources_call, so the same service, capability check and receipt apply.
#
# Capability check: set_source_consent carries a user_intent_token minted only
# by POST /sources/consent-intent (dashboard, origin-gated). Registry callers
# never mint tokens and never supply an actor string; the session a token
# binds to is the helper's trusted session hash (server._library_session_hash),
# derived here from the backend, never from tool JSON.
# ===========================================================================

SOURCES_CONTRACT_VERSION = "phase3-v1-2026-09-07"
SOURCES_TOOL_NAMES = ("list_sources", "register_source", "source_status", "set_source_consent")
_SOURCES_RATE_LIMITERS: dict[str, _RateLimiter] = {
    "list_sources": _RateLimiter(60),
    "register_source": _RateLimiter(30),
    "source_status": _RateLimiter(60),
    "set_source_consent": _RateLimiter(30),
    "sources_intent": _RateLimiter(30),
    "sources_route": _RateLimiter(30),
}
_sources_service_override: Any = None


def set_sources_service(service: Any) -> None:
    """Inject a service double for adapter tests; None restores the helper's."""
    global _sources_service_override
    _sources_service_override = service


def _sources_module() -> Any:
    import source_subscriptions  # noqa: WPS433
    return source_subscriptions


def _sources_service() -> Any:
    if _sources_service_override is not None:
        return _sources_service_override
    backend = _b()
    factory = getattr(backend, "_source_service", None)
    if not callable(factory):
        return None
    return factory()


def _sources_unavailable() -> dict[str, Any]:
    return _sources_module().error_envelope(
        "service_unavailable",
        "The standing-source service is not available in this helper build; "
        "no source was read or changed.", retryable=False)


def _sources_context(transport: str, *, actor: str = "registry",
                     session_hash: str | None = None) -> Any:
    """Trusted request context. Registry callers carry no user authority; the
    dashboard confirmation route alone sets local_user_confirmed."""
    mod = _sources_module()
    if session_hash is None:
        try:
            session_hash = _library_trusted_session(_b())
        except RuntimeError:
            session_hash = None  # no backend bound (adapter tests with a double)
    return mod.RequestContext(
        authenticated=True,
        session_id=session_hash or transport,
        operator=(actor == "server"),
        local_user_confirmed=(actor == "user"),
        transport=transport,
    )


def _sources_normalize(result: Any, tool_name: str) -> dict[str, Any]:
    mod = _sources_module()
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        _library_log.error("sources %s: service returned a malformed response", tool_name)
        return mod.error_envelope("internal_error", "The source service returned a malformed response.",
                                  details={"tool": tool_name})
    out = dict(result)
    out.setdefault("schema_version", mod.SCHEMA_VERSION)
    out.setdefault("contract_version", mod.CONTRACT_VERSION)
    return out


def sources_call(tool_name: str, args: Any, *, transport: str = "registry") -> dict[str, Any]:
    """Common adapter path for the four tools on every transport: rate limit,
    trusted context, service (which performs the strict schema validation and
    the capability check), contract envelope."""
    mod = _sources_module()
    if tool_name not in SOURCES_TOOL_NAMES:
        return mod.error_envelope("not_found", "Unknown source tool", details={"tool": tool_name})
    try:
        _SOURCES_RATE_LIMITERS[tool_name].check()
    except RateLimitExceeded as exc:
        return mod.error_envelope("rate_limited", str(exc), retryable=True, details={"tool": tool_name})
    if not isinstance(args, dict):
        return mod.error_envelope("validation_error", "Arguments must be an object")
    for forbidden in ("actor", "cap", "daily_cap", "back_catalog_cap", "adapter", "path", "now_ms"):
        if forbidden in args:
            # Contract: no client supplies caps, actor privileges, adapter
            # commands, source paths or clock values. Unknown fields are also
            # rejected by the schema; name the attempt explicitly.
            return mod.error_envelope("validation_error", "Unknown fields",
                                      details={"field": forbidden, "unknown": [forbidden]})
    service = _sources_service()
    if service is None:
        return _sources_unavailable()
    fn = getattr(service, tool_name, None)
    if not callable(fn):
        return _sources_unavailable()
    try:
        result = fn(_sources_context(transport), dict(args))
    except Exception:
        _library_log.exception("sources %s raised", tool_name)
        return mod.error_envelope("internal_error", "The source service raised; see the helper log.",
                                  details={"tool": tool_name})
    return _sources_normalize(result, tool_name)


def list_sources(args: dict[str, Any]) -> dict[str, Any]:
    return sources_call("list_sources", args)


def register_source(args: dict[str, Any]) -> dict[str, Any]:
    return sources_call("register_source", args)


def source_status(args: dict[str, Any]) -> dict[str, Any]:
    return sources_call("source_status", args)


def set_source_consent(args: dict[str, Any]) -> dict[str, Any]:
    return sources_call("set_source_consent", args)


def sources_mint_consent_intent(body: Any, *, session_hash: str) -> dict[str, Any]:
    """Behind POST /sources/consent-intent (server.py owns auth, origin and
    the strict decoder). Body: {"operation": <set_source_consent arguments
    without user_intent_token>}. The service validates the operation against
    the same schema minus the token, binds the request hash, source and
    cursor revisions and the session, and returns the token, expiry and a
    display summary."""
    mod = _sources_module()
    try:
        _SOURCES_RATE_LIMITERS["sources_intent"].check()
    except RateLimitExceeded as exc:
        return mod.error_envelope("rate_limited", str(exc), retryable=True,
                                  details={"route": "/sources/consent-intent"})
    if not isinstance(body, dict) or set(body) - {"operation", "confirmed"}:
        return mod.error_envelope("validation_error", "Expected {operation, confirmed}")
    if body.get("confirmed") is not True:
        # The dashboard sends this only from the source opt-in confirmation.
        return mod.error_envelope("user_intent_required", "Local confirmation is required")
    if not isinstance(session_hash, str) or len(session_hash) != 64:
        return mod.error_envelope("internal_error", "The dashboard session could not be identified.")
    service = _sources_service()
    if service is None:
        return _sources_unavailable()
    try:
        result = service.mint_consent_intent(
            _sources_context("dashboard", actor="user", session_hash=session_hash),
            {"operation": body.get("operation")})
    except Exception:
        _library_log.exception("sources consent intent raised")
        return mod.error_envelope("internal_error", "Consent intent minting failed; see the helper log.")
    return _sources_normalize(result, "sources_intent")


def sources_service_route(method: str, body: Any, *, session_hash: str) -> dict[str, Any]:
    """Existing-style dashboard routes (refresh, archive) on the same service.
    They carry local dashboard authority, not a registry tool's."""
    mod = _sources_module()
    if method not in ("refresh_source", "archive_source"):
        return mod.error_envelope("not_found", "Unknown source route", details={"method": method})
    try:
        _SOURCES_RATE_LIMITERS["sources_route"].check()
    except RateLimitExceeded as exc:
        return mod.error_envelope("rate_limited", str(exc), retryable=True, details={"route": method})
    if not isinstance(body, dict):
        return mod.error_envelope("validation_error", "Arguments must be an object")
    service = _sources_service()
    if service is None:
        return _sources_unavailable()
    try:
        result = getattr(service, method)(
            _sources_context("dashboard", actor="user", session_hash=session_hash), dict(body))
    except Exception:
        _library_log.exception("sources route %s raised", method)
        return mod.error_envelope("internal_error", "The source service raised; see the helper log.")
    return _sources_normalize(result, method)


def _sources_tool_schema(name: str) -> dict[str, Any]:
    """The frozen schema (contract JSON) for one registry tool. A helper build
    without source_subscriptions.py (packaging is run AN) still imports; the
    tool then answers service_unavailable."""
    try:
        return _sources_module().TOOL_SCHEMAS[name]
    except ImportError:  # pragma: no cover -- unpackaged build
        return {"type": "object", "additionalProperties": False}


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def get_library_activity(args: dict[str, Any]) -> dict[str, Any]:
    import library_analysis
    return library_analysis.handle_get_library_activity(args)

def _library_resources_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Phase 4 read tools (contract phase4-v1-2026-09-08, run AV-1). The
    shared reader lives in library_resources.py; a helper build without it
    still imports this registry and answers a domain refusal. Each call binds
    a request-scoped reader on the process guard; the reader never writes."""
    try:
        import library_resources as _lr  # noqa: WPS433 -- optional module
    except ImportError:
        return {
            "ok": False, "schema_version": 1, "contract_version": "phase4-v1-2026-09-08",
            "error": {"code": "feature_unavailable",
                      "message": "This feature is not available in this build.",
                      "retryable": False, "details": {"module": "library_resources"}},
        }
    return _lr.dispatch_tool(name, args, _b())


def _library_media_export(args: dict[str, Any]) -> dict[str, Any]:
    """Phase 6 export tool (contract phase6-v1, run BC-2). The read-only
    domain operation lives in library_media.py; exact input rejection runs
    before any storage access, admission and the 2 s deadline reuse the
    Phase 4 process guard, and only an existing index is ever bound."""
    try:
        import library_media as _lm  # noqa: WPS433 -- optional module
    except ImportError:
        return {
            "ok": False, "schema_version": 1, "contract_version": "phase6-v1",
            "error": {"code": "feature_unavailable",
                      "message": "This feature is not available in this build.",
                      "retryable": False, "details": {"module": "library_media"}},
        }
    return _lm.export_cited_range_tool(args, _b())


def _research_playbooks_call(args: Any) -> dict[str, Any]:
    """Local packets on the shared read guard; no raw exception crosses MCP."""
    import library_resources as _lr

    try:
        import research_playbooks

        args = _lr._strict_arguments(args, ("playbook", "arguments"),
                                     ("playbook", "arguments"))
        if not isinstance(args["arguments"], dict):
            raise _lr._invalid("arguments_not_object", field="arguments")
        reader = _lr.make_reader(_b())
        result = research_playbooks.get_playbook_input(
            reader, args["playbook"], args["arguments"])
        text = _lr.render_tool_text(result)
        _lr._check_wire({"content": [{"type": "text", "text": text}], "isError": False},
                        what="get_playbook_input", next_step="use fewer captures or a narrower scope")
        reader.assert_within_deadline()
        return result
    except ImportError:
        return _lr.ResourceError("feature_unavailable", details={
            "module": "research_playbooks"}).envelope()
    except _lr.ResourceError as exc:
        return exc.envelope()
    except Exception:
        # Exception text may contain local source data. Keep it out of both
        # the response and logs, including serialization errors (NaN/inf).
        return _lr.ResourceError("internal_error").envelope()


PLAYBOOK_INPUT_SCHEMA: dict[str, Any] = _schema({
    "playbook": {"type": "string", "enum": [
        "outlier-posts", "transcript-intel", "comment-mining",
        "creator-teardown", "repurpose-pack",
    ]},
    "arguments": {"type": "object", "description": (
        "The selected playbook's prompt arguments, with string values. "
        "Pass video_ids and kinds as comma-separated strings.")},
}, ["playbook", "arguments"])

PLAYBOOK_INPUT_DESCRIPTION = (
    "Prepare a bounded, cited research packet from the local library for "
    "outlier-posts, transcript-intel, comment-mining, creator-teardown or "
    "repurpose-pack. Returns instruction, packet and packet_hash; the client "
    "writes the report. No model, network, capture or settings changes."
)


DISCOVERY_TOOL_NAMES = frozenset({"discover_candidates", "queue_discovered"})
DISCOVER_CANDIDATES_DESCRIPTION = (
    "Plan or run one ScrapeCreators discovery search with your saved key. "
    "Off by default. Omit confirm_credits for a free plan; set it to the planned "
    "credits to spend. Requires discovery enabled, room under the daily cap, "
    "and agent discovery enabled or a dashboard intent. Saves normalized "
    "candidates locally; does not capture them or fetch thumbnails."
)
QUEUE_DISCOVERED_DESCRIPTION = (
    "Queue 1-10 saved discovery candidates for normal Uoink capture. Requires "
    "agent discovery enabled or a dashboard intent. Skips captured, queued, "
    "unsupported and unknown picks. No ScrapeCreators call or credits; the "
    "normal retry worker captures the selected URLs."
)
DISCOVER_CANDIDATES_SCHEMA = _schema({
    "mode": {"type": "string", "enum": ["creator", "keyword"]},
    "platform": {"type": "string", "enum": ["tiktok", "instagram", "youtube", "youtube_shorts"]},
    "handle": {"type": "string", "minLength": 1, "maxLength": 100},
    "channel_id": {"type": "string", "pattern": "^UC[A-Za-z0-9_-]{22}$"},
    "query": {"type": "string", "minLength": 1, "maxLength": 200},
    "pages": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
    "confirm_credits": {"type": "integer"},
    "user_intent_token": {"type": "string", "minLength": 1, "maxLength": 256},
}, ["mode", "platform"])
QUEUE_DISCOVERED_SCHEMA = _schema({
    "run_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,150}$"},
    "keys": {"type": "array", "minItems": 1, "maxItems": 10,
             "items": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,100}$"}},
    "user_intent_token": {"type": "string", "minLength": 1, "maxLength": 256},
}, ["run_id", "keys"])


def validate_research_arguments(name, args):
    """HTTP schema preflight using the domain validators, without data access."""
    import library_resources as _lr

    try:
        if name == "get_playbook_input":
            import research_playbooks

            args = _lr._strict_arguments(args, ("playbook", "arguments"),
                                         ("playbook", "arguments"))
            if not isinstance(args["arguments"], dict):
                raise _lr._invalid("arguments_not_object", field="arguments")
            research_playbooks._validate(_lr.LibraryReader(None, data_root=None),
                                         args["playbook"], args["arguments"])
        else:
            import discovery_scrapecreators as discovery

            validator = (discovery.validate_arguments if name == "discover_candidates"
                         else discovery.validate_queue_arguments)
            validator(args)
    except _lr.ResourceError as exc:
        return exc.envelope()
    except Exception:
        return _lr.ResourceError("internal_error").envelope()
    return None


def _discovery_call(name, args, *, origin="", session_hash=""):
    """Transport context is supplied by HTTP, never taken from tool arguments."""
    import library_resources as _lr

    try:
        TOOL_REGISTRY[name].rate_limiter.check()
        service = _b()._get_discovery_service()
        result = getattr(service, name)(args, origin=origin, session_hash=session_hash)
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise _lr.ResourceError("internal_error")
        # Check serialization here too, so neither transport exposes exceptions.
        json.dumps(result, ensure_ascii=False, allow_nan=False)
        return result
    except RateLimitExceeded:
        return _lr.ResourceError("rate_limited", details={"retry_after_ms": 60000}).envelope()
    except _lr.ResourceError as exc:
        return exc.envelope()
    except Exception:
        return _lr.ResourceError("internal_error").envelope()


EXPORT_CITED_RANGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string", "description": "Stable item id."},
        "start": {"type": "number", "minimum": 0,
                  "description": "Range start in seconds; must equal the first selected cue's start (with end)."},
        "end": {"type": "number", "minimum": 0,
                "description": "Range end in seconds; must equal the last selected cue's end (with start)."},
        "excerpt_id": {"type": "string", "description": "A current excerpt id (instead of start/end)."},
        "source_revision": {"type": "string", "description": "Optional pin; refuses revision_unavailable on change."},
        "media_revision": {"type": "string", "description": "Optional pin; refuses revision_unavailable on change."},
    },
    "required": ["video_id"],
    "additionalProperties": False,
}
EXPORT_CITED_RANGE_DESCRIPTION = (
    "Read-only cited export of one stored transcript range (exact cue-aligned "
    "start/end, at most 120 s and 200 cues) or one current excerpt id from a "
    "saved item: verbatim stored text, per-cue speaker labels with provenance, "
    "overlapping chapters, safe source and seek links, source/media revisions "
    "and evidence refs. Nothing is fetched, transcribed or saved; refusals "
    "carry a next_step."
)


# Stable v3.9.1 wire order. Keep these first for clients that cap tool counts.
CORE_STDIO_TOOLS = (
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
    "get_library_activity",
    "search_library",
    "get_library_item",
    "read_library_resource",
    "get_playbook_input",
    "discover_candidates",
    "queue_discovered",
    "get_library_brief_input",
    "publish_library_brief",
    "export_cited_range",
)


DESCRIPTIONS = {
    "uoink_video": "Capture one YouTube video into a saved Markdown corpus with screenshots. Use for a single video; use uoink_playlist for a batch or uoink_url for other supported video platforms and long-video modes. Runs synchronously and needs the local media runtime. Returns the saved corpus and file paths; failures can leave partial capture files. Recapturing a source can replace its saved corpus and metadata.",
    "uoink_playlist": "Start a background capture job for the videos in a YouTube playlist. Use for a one-time batch; use add_monitored_playlist for ongoing metadata monitoring or uoink_video for one video. Returns a job_id for get_job_status and cancel_job. Requires the local media runtime; the job can produce partial outputs before completion or cancellation. Recapturing a source can replace its saved corpus and metadata.",
    "get_job_status": "Read progress, per-item outcomes and errors for a saved capture or transcription job. Use after uoink_playlist or transcribe_podcast_episode returns a job_id; use cancel_job to request cancellation. Returns the current job object, or an error for an invalid or unknown identifier.",
    "cancel_job": "Request cancellation of a capture or transcription job while keeping partial outputs on disk. Use when the user wants work stopped; use get_job_status to inspect progress without cancelling. Returns the updated job object or an error for an unknown identifier. Cancellation does not delete captures already saved.",
    "list_recent_uoinks": "List the newest saved captures from the local index, with their slugs, titles, folders and capture times. Use to browse recent additions without a query; use search_uoinks for matching text or search_library for bounded citation-ready retrieval. Returns up to the requested number of items under the legacy yoinks key.",
    "search_uoinks": "Find whole saved items by text, with optional channel and hook filters. Use to select corpora; use search_clips for timed transcript windows, search_library for bounded revision-bound retrieval, or query_by_facets for exact stored labels. Returns ranked item snippets and search-mode metadata. Semantic modes depend on the local index and helper; unavailable semantic search falls back to keyword with a reason.",
    "search_clips": "Find transcript windows in saved items, with timing, source links and ranked snippets. Use to locate quotable passages; use search_uoinks for whole items or search_library for bounded clip-first results with resource URIs. Long source cues keep coarse timing and link to the cue start. Semantic modes can fall back to keyword; inspect the returned search-mode metadata and passage verification before quoting.",
    "get_evidence_card": "Build a saved item's evidence card with identity, summary hints and clips spread across its timeline. Use when you need a selectable card profile or clip count; use get_library_item for a bounded default Librarian card with revision-bound resource URIs. Supply at least one selector: a matching slug takes precedence, then video_id is tried. Missing items return an error; cards expose no local file paths.",
    "get_uoink_corpus": "Read a saved item's complete Markdown corpus, citation rows and available source or image pointers by slug. Use when you need the full local document; use get_library_item then read_library_resource for bounded chunks, or get_citation_map for citations alone. Returns an error if the corpus is missing or unreadable. Image pointers refer to saved pixels; this call performs no image interpretation.",
    "analyze_comments": "Analyze a saved capture's comments with Anthropic and replace its stored comment-intelligence section. Use to refresh themes, mentioned products and disagreements; use get_playbook_input with comment-mining for local evidence that your own agent analyzes. Requires a saved Anthropic key and at least five saved comments. Sends comment content to the provider and returns the resulting analysis lists.",
    "classify_hook": "Classify a saved capture's opening with Anthropic and replace its stored hook analysis. Use to run the classifier; use get_taxonomy to inspect saved classifications or classify_facets to store your own labels. Requires a saved Anthropic key and sends saved title, transcript and comment context to the provider. Returns the hook, explanation, confidence and correction count, and appends a taxonomy entry.",
    "get_taxonomy": "Read saved hook-classification rows, optionally restricted to a channel or hook. Use to inspect prior classifier results; use get_facet_taxonomy for allowed labels, classify_hook to run the classifier, or analyze_self_channel for own-channel trends. Returns a bounded taxonomy list without rerunning analysis.",
    "get_citation_map": "Read all stored transcript and screenshot citations for one saved capture. Use for citation timing and source links without the full corpus; use get_uoink_corpus for Markdown or export_cited_range for a bounded cue-aligned export. Returns separate transcript and screenshot lists with source-aware deep links where available. Requires a saved video_id in the item's sidecar; missing captures return an error.",
    "get_uoink_health": "Read the stored per-section extraction health of a saved capture. Use to diagnose missing or failed capture sections; use get_transcript_reliability for questionable transcript spans. Reads the index snapshot, falling back to the sidecar, and returns an error when no health data exists. It does not retry extraction or recompute health.",
    "find_mentions": "Find recorded entity-name mentions across saved items, with stored spans, timing and source links. Use for people, products, tools or topics already indexed as entities; use search_clips for arbitrary transcript text or search_uoinks for whole-item search. Ranks by name match with newest first on ties. Results are limited and do not extract new entities.",
    "get_transcript_reliability": "Read stored transcript-reliability spans for a saved item. Use to inspect suspect wording before quoting; use get_uoink_health for extraction-section health or export_cited_range for stored cue text. Returns status not_computed with empty spans when no reliability snapshot exists. Computation requires the helper endpoint or the user's auto-check setting; this read never downloads a model.",
    "add_podcast_feed": "Register a podcast RSS feed for ongoing metadata monitoring. Use for the podcast feed and episode workflow; use register_source for the general standing-source interface or list_podcast_feeds to find an existing feed. Returns the existing row for a duplicate URL. Audio auto-ingest is a separate explicit opt-in, off by default; standing capture still requires source consent through the dashboard.",
    "list_podcast_feeds": "List registered podcast feeds newest first, including their saved polling settings. Use to obtain a feed_id before polling or removal; use list_podcast_episodes to inspect episodes and list_sources for standing-source consent. Returns feeds and their count. This call reads saved registrations without fetching RSS.",
    "remove_podcast_feed": "Stop monitoring a registered podcast feed. Use after list_podcast_feeds identifies the feed; use set_source_consent to disable capture while retaining detection. A source-linked feed is archived and disabled; a legacy unlinked feed is deleted with its tracked episode rows. Returns whether a row was affected; already published corpora are not removed.",
    "poll_podcast_feed": "Refresh metadata for one registered podcast feed through the source-aware polling path. Use after add_podcast_feed when new episode observations are needed; use list_podcast_episodes to read cached episodes without a fetch. Managed sources honor detection due times and leases. Polling records observations; capture remains subject to separate source consent and scheduling. Returns the poll outcome or a feed error.",
    "list_podcast_episodes": "List tracked podcast episodes newest published first, optionally scoped to a feed or lifecycle state. Use to obtain episode IDs and check download or transcription state; use list_podcast_feeds for feed settings or poll_podcast_feed to refresh observations. Returns episodes and count from local storage without fetching audio.",
    "download_podcast_episode": "Download a tracked podcast episode's audio to its canonical local MP3. Use after list_podcast_episodes, before transcribe_podcast_episode; use episode_to_corpus only after a transcript exists. Requires yt-dlp and ffmpeg, and blocks until download finishes or fails. Reuses an existing nonempty canonical file and records its path on the episode.",
    "get_whisperx_status": "Inspect local WhisperX availability, the selected model and the diarization default. Use before transcribe_podcast_episode to identify missing runtime prerequisites; use get_job_status to monitor an already queued transcription. Returns availability and supported model settings without downloading a model or starting transcription.",
    "transcribe_podcast_episode": "Queue local WhisperX transcription for a downloaded podcast episode. Use after download_podcast_episode and get_whisperx_status; monitor the returned job with get_job_status, then publish with episode_to_corpus. A single worker writes or replaces the JSON transcript beside the audio. First-time model downloads require user consent: only reissue with consent_given after the dashboard records the opt-in. Missing runtime returns an error.",
    "episode_to_corpus": "Publish a completed podcast transcript as a searchable local corpus with source-aware citations. Use after transcribe_podcast_episode completes; use download_podcast_episode for audio acquisition. Writes deterministic Markdown and sidecar files, replaces the prior corpus/index snapshot and repairs partial previous attempts. Missing audio or transcript prerequisites return an error; success identifies the published item.",
    "get_library_activity": "Report saved-library capture activity, shelf churn and standing-source observations for a time interval. Use for counts and revision-bound drill-down; use get_library_brief_input for a daily writing packet or source_status for one source's observations. Start with a summary, then reuse its report_revision for detail pages. Returns deterministic metrics and evidence; stale detail revisions require a fresh summary.",
    "search_library": "Retrieve a bounded, clip-first selection of saved-library matches with revision-bound card and excerpt URIs. Use for citation-ready research; use search_uoinks for whole-item filters or search_clips for more transcript windows. Check passage_verified before quoting; citation_reason explains missing passages. Follow resource URIs with read_library_resource and next_step for more retrieval. Results are not exhaustive; search-mode metadata explains keyword fallback.",
    "get_library_item": "Resolve one saved item to its bounded default Librarian card and canonical card, excerpt and initial corpus-chunk URIs. Use before quoting or paging through evidence; use get_evidence_card for selectable profiles and clip counts, or get_uoink_corpus for the full local Markdown. Supply exactly one selector. Follow returned URIs with read_library_resource; missing or stale evidence produces a structured refusal.",
    "read_library_resource": "Read a bounded saved-library card, excerpt, corpus chunk, shelf page or brief from its uoink URI. Use as the tools-only equivalent of resources/read, after search_library or get_library_item supplies a URI. Use get_uoink_corpus for a full document instead of chunk paging. Validation, rendered contents and refusals match native resource reads; follow next_step on stale revisions or unavailable evidence.",
    "get_playbook_input": "Prepare cited local evidence and instructions for a client-written research report. Use for creator comparisons, transcript analysis, comment mining or repurposing; use analyze_self_channel for computed own-channel performance, search_library for ad hoc retrieval and get_library_brief_input for a dated operational brief. Returns instruction, packet and packet_hash within the library read budget. The client does the analysis; no model is called. Argument selectors depend on the selected playbook.",
    "discover_candidates": "Plan or run a ScrapeCreators search and save uncaptured candidates. Use to find new material; use search_library for saved evidence and queue_discovered to capture selected candidates. Off by default; requires a saved key, discovery enabled and daily credit room. Omit confirm_credits for a free plan, then confirm its exact cost. Spending requires agent discovery consent or a dashboard intent; stdio needs agent consent because dashboard intents are process-bound. No candidate is captured by this call.",
    "queue_discovered": "Enqueue selected saved discovery candidates for normal capture. Use after discover_candidates returns a run and candidate keys; use that tool again to search for new candidates. Requires agent discovery consent or a dashboard intent; stdio needs agent consent because dashboard intents are process-bound. Returns queued and skipped picks, skipping unknown, unsupported, captured or queued URLs. No ScrapeCreators credits are spent; the resident retry worker performs capture later.",
    "get_library_brief_input": "Prepare a dated library-status packet for a brief that the client writes. Use for a requested daily brief; use get_library_activity for direct metrics or get_playbook_input for topical research. Returns job_key, input_hash, bound revisions, counts, coverage, up to 20 work rows and five Librarian cards within 24,576 bytes. No work lease is acquired. Pass the unchanged packet to publish_library_brief after writing.",
    "publish_library_brief": "Save a client-written daily brief as an immutable local artifact. Use only for the user's requested brief job after get_library_brief_input; use read_library_resource to read a published brief. Validates the exact packet against current data and binds quotes to supplied evidence. An identical submission_key retry returns the saved result; stale_brief requires fresh input. Writes under reach/briefs without applying labels or changing the assignment queue.",
    "export_cited_range": "Export verbatim stored transcript cues with speaker provenance, overlapping chapters, safe links and evidence references. Use after search_clips identifies a passage; use get_citation_map for all citation rows or read_library_resource for an existing resource URI. Select exact cue-aligned bounds or a current excerpt, at most 120 seconds and 200 cues. Returns source/media revisions; refusals include next_step. It does not fetch media or recompute transcription.",
    "list_library_work": "List Librarian assignment counts and one cursor page of work for a run. Use to inspect readiness before claim_library_work; use get_library_activity for aggregate library metrics. Listing expires stale leases and can update work state. Returns run revision, work states, manifest dispositions and waiting-client status. The server does not perform the Librarian's model work.",
    "claim_library_work": "Lease Librarian evidence packets, or renew, release or cancel your current attempts. Use after list_library_work to acquire work; use submit_library_result to store an assignment. Claim returns up to twelve packets with attempt tokens. Renew/release/cancel require the work_id and attempt_token from that claim. Leases last 60-900 seconds, never beyond one hour from first claim; three attempts exhaust a row.",
    "submit_library_result": "Store a client's shelf-assignment result for one currently leased Librarian item. Use after claim_library_work; use apply_reshelving to preview accepted assignments as label changes. Copy the packet's identifiers and revision hashes unchanged, and quote its evidence. Submission stages results without changing current labels; an identical submission_key retry replays the recorded response. Report unavailable usage honestly instead of inventing zero usage.",
    "apply_reshelving": "Create a reshelving preview or apply an approved preview to current labels. Use after submit_library_result stages assignments; use pin_shelf for a user's individual shelf decision or undo_library_apply to reverse the latest apply. Preview needs a run and current projection revision; apply needs its preview_id, delta_hash and operation_key. Apply is disabled by default and stops at 15 percent churn without trusted human approval; expired or stale previews must be rebuilt.",
    "pin_shelf": "Record a user's pin, unpin or move decision for one item's shelf membership. Use for an explicit individual decision; use apply_reshelving for run-wide proposed changes. Requires a dashboard-minted user_intent_token tied to the exact operation and current projection revision; no actor string grants authority. The Librarian cannot override the resulting user decision. Retry the same operation_key only with identical arguments.",
    "undo_library_apply": "Reverse the latest applicable library apply by replaying its stored inverse as a new journal operation. Use to undo the apply that produced the current projection revision; use apply_reshelving for a new proposal or pin_shelf for one item's shelf choice. Requires a dashboard user_intent_token. The inverse is itself reversible; identical operation_key retries replay the receipt, and stale revisions are refused.",
    "list_sources": "List standing RSS, YouTube channel and playlist sources with consent, enrollment, daily allowance and detection health. Use to find source_id values and compare source states; use source_status for one source's observations or list_podcast_feeds/list_monitored_playlists for legacy feed and playlist IDs. Returns a keyset page from local storage. Pass its cursor unchanged to continue; no poll or capture starts.",
    "register_source": "Register a standing source for future metadata detection with capture consent off. Use for the general source workflow; use add_podcast_feed or add_monitored_playlist when you need their feed or playlist IDs. Creates a due detection cursor without an immediate network call; the resident scheduler polls later. Duplicates return the existing source unchanged with created=false. Enable capture separately through set_source_consent after dashboard confirmation.",
    "source_status": "Read one standing source's summary, observed-item page and all in-flight reservations. Use after list_sources for detailed capture and classification state; use set_source_consent to change capture permission. Returns saved observations without enrolling, polling or starting work. Continue item pages with the returned cursor; revisions in the summary are needed for consent changes.",
    "set_source_consent": "Enable or disable standing capture for a registered source after local confirmation. Use after register_source and source_status; use remove_podcast_feed or remove_monitored_playlist to stop their monitoring entirely. Requires current revisions and a dashboard-minted intent. Enabling permits at most 25 initial back-catalog items and 10 starts per UTC day; disabling releases unstarted reservations. Identical operation-key retries return the stored receipt; active captures are not cancelled by disabling.",
    "analyze_self_channel": "Summarize the user's saved own-channel videos into hook and format history, monthly performance trends and top performers. Use for own-channel planning; use get_playbook_input with creator-teardown for a chosen creator's research packet or get_engagement_signal for one item's local usage. Scope by a registered handle or omit it for all recognized own channels. Results reflect saved data, not live channel analytics.",
    "get_schema_version": "Report the local SQL migration, item and sidecar schema versions and supported read ranges. Use before interpreting older saved records in an integration; use get_uoink_health to diagnose a capture's contents. Returns null for the SQL version if it cannot be read. This is a storage compatibility check, not a migration request.",
    "get_user_role": "Read the saved user role and its resolved dashboard sort and filter emphasis. Use to inspect the current dashboard preference; use set_user_role to change it or get_user_taste for writing and content preferences. Returns the normalized role, emphasis and supported roles without changing settings.",
    "set_user_role": "Replace the saved user role that controls dashboard sort and filter emphasis. Use for the user's chosen working role; use get_user_role to inspect it or update_user_taste for content preferences. Returns the normalized role and computed emphasis. Other saved settings are retained.",
    "check_live_status": "Fetch video metadata to determine whether a broadcast is live, upcoming or finished. Use before deciding to capture now or wait; use uoink_video or uoink_url to capture, and get_job_status for an existing job. Requires the metadata-fetch runtime and network access. Returns the canonical URL, title and detected live state without starting extraction.",
    "add_monitored_playlist": "Register a YouTube playlist for ongoing metadata monitoring. Use for repeated observation; use uoink_playlist for a one-time capture batch or register_source for the general source interface. Returns the existing row for a duplicate URL. Managed playlists start with capture consent off and clamp polling to at least 15 minutes; capture requires separate source consent and the resident helper.",
    "list_monitored_playlists": "List registered playlist monitors newest first with saved monitoring settings. Use to obtain playlist_id before polling or removal; use list_monitored_playlist_events for discoveries and list_sources for standing-source consent. Returns playlists and count from local storage without fetching YouTube.",
    "remove_monitored_playlist": "Stop monitoring a registered playlist. Use after list_monitored_playlists identifies it; use set_source_consent to stop capture while keeping metadata detection. Source-linked playlists are archived and disabled; legacy unlinked playlists and their discovery events are deleted. Returns whether a row was affected. Saved captures remain available.",
    "poll_monitored_playlist": "Refresh observations for a registered playlist through its source-aware polling path. Use after list_monitored_playlists when fresh observations are needed; use list_monitored_playlist_events for cached discoveries. Stdio requires the resident Uoink helper. Managed sources honor due-time and lease gates, and detection does not enqueue captures; captures require separate source consent and reservations. Returns the poll outcome and observation summary.",
    "list_monitored_playlist_events": "List recorded playlist-discovery events newest first, optionally filtered by playlist or lifecycle state. Use to inspect what monitoring found; use poll_monitored_playlist to refresh observations or list_monitored_playlists for monitor settings. Returns saved events and count. Reading events does not enqueue or retry captures.",
    "get_user_taste": "Read consolidated TASTE.md preferences and performance anchors. Use for writing or example-selection context; use get_user_memory for hand-edited personal notes or update_user_taste to replace a preference section. If missing, regenerates the file from local engagement and anchors, including a configured vault mirror. Returns content and path without calling a model.",
    "get_user_memory": "Read the user's hand-edited USER.md notes about channels, topics and workflow. Use for personal context; use get_user_taste for consolidated content preferences. Creates a local skeleton on first read when absent, then returns content and path. Existing hand-edited text is preserved; the taste consolidator does not overwrite it.",
    "update_user_taste": "Replace one persisted taste-preference section and regenerate TASTE.md. Use for a user-requested preference change; use get_user_taste to inspect current preferences or get_user_memory for separate personal notes. The supplied Markdown replaces that section verbatim. Regeneration updates the local file and configured vault mirror; other preference sections remain intact.",
    "get_engagement_signal": "Read one saved item's time-decayed local engagement score, event counts and last-event time. Use to assess how the user has used an item; use analyze_self_channel for captured channel-performance trends or query_by_facets for stored performance labels. The score uses local interaction events with a 30-day half-life, not live social-network engagement.",
    "classify_facets": "Store your agent's facet classifications and tags on a saved item. Use after analyzing its evidence; use query_by_facets to retrieve labeled items or classify_hook for provider-run hook classification. Validates supplied labels, replaces those facet values and adds deduplicated tags. Missing performance tier and length bucket can be derived from saved metadata. Returns applied facets and tag counts; no model call runs here.",
    "query_by_facets": "List saved items matching all supplied facet and tag filters, newest first. Use for exact stored-label selection; use search_uoinks for text relevance, classify_facets to write labels, or get_facet_taxonomy to discover supported axes. Returns yoinks and count from local storage. Filters are AND-combined; omitted filters leave that axis unrestricted.",
    "get_facet_taxonomy": "Return supported format, performance-tier, length-bucket and hook label lists. Use before classify_facets or query_by_facets; use get_taxonomy for saved per-item hook-classification rows. These are the server's allowed label constants, not counts of labels present in the library.",
    "assemble_workspace": "Select and rank saved examples for planning a video, with audience questions and available taste or own-channel context. Use to assemble a corpus slice; use get_workspace to read a saved workspace or critique_against_corpus to review a draft. Ranking uses format, performance tier and local engagement. Supplying workspace_id replaces that workspace's selected-item list; omitting it only returns the slice. Your agent performs any subsequent model analysis.",
    "critique_against_corpus": "Prepare workspace grounding for a draft critique, or append your agent's findings to its critique log. Use after assemble_workspace; use get_workspace to read earlier critiques or revise_script to save a script revision. Omit findings to retrieve context, then submit your analysis with findings. Repeated submissions append log entries. Server-side BYO generation is not implemented; the agent performs the analysis.",
    "list_workspaces": "List saved video-planning workspaces newest first. Use to obtain a workspace ID for get_workspace, assemble_workspace or generate_script; use list_scripts for script-version history. Returns workspace rows and count. This tool does not create workspaces or assemble new examples.",
    "get_workspace": "Read one saved video-planning workspace and its full critique log. Use after list_workspaces; use assemble_workspace to select new examples or critique_against_corpus to append findings. Supply id or its workspace_id alias; id takes precedence. Returns workspace and critique_log, or an error if the workspace is missing.",
    "extract_claims": "Store checkable claims that your agent extracted from a saved item. Use after reading its evidence; use verify_claim to record supporting or conflicting evidence and list_claims to inspect existing claims. Appends claim rows in extracted state and returns their IDs. The agent performs decomposition; this tool does not determine truth. BYO model execution is not implemented.",
    "verify_claim": "Record your agent's evidence and alignment signals for an existing claim. Use after extract_claims; use get_claim to inspect evidence without changing it. Replaces the stored evidence and updates review status. Signals describe support, contradiction, mixed evidence or inconclusiveness, never a truth verdict; the user judges the claim. The agent performs research, and BYO model execution is not implemented.",
    "list_claims": "List saved checkable claims, optionally filtered by source item or review status. Use to select claim IDs for get_claim or verify_claim; use extract_claims to add claims. Returns claim rows and count. A verified status records that evidence was submitted, not that the claim is true.",
    "get_claim": "Read one saved claim with its recorded evidence and alignment signals. Use after list_claims; use verify_claim to replace its evidence. Supply id or its claim_id alias; id takes precedence. Returns the claim or a not-found error. Review status and alignment signals are evidence records, not automatic truth verdicts.",
    "generate_script": "Prepare workspace grounding for a video script, or save an agent-written script as a new version. Use for a new draft; use revise_script to revise an existing script or write_blog/write_tweet for prose pieces. Omit script to retrieve context, then submit your structured draft. The agent writes it; server-side BYO generation is not implemented. Returns grounding or the saved script ID and version.",
    "revise_script": "Prepare revision context for an existing video script, or save its replacement as a linked new version. Use after get_script or critique_against_corpus; use generate_script for a new draft. Without revised_script, returns the previous script and grounding; with it, persists a new row whose parent is the prior script. The agent performs rewriting; server-side BYO generation is not implemented.",
    "get_shot_list": "Derive and save a default shot list from a script's beats and its workspace format. Use when you want heuristic camera cues; use get_script to read the existing shot list without replacing it, or supply a custom shot_list through generate_script. This call overwrites the prior shot list and returns the generated rows. It does not run a model.",
    "list_scripts": "List saved video-script versions newest first, optionally within one workspace. Use to find a script ID for get_script or revise_script; use list_writing_pieces for tweet, thread and blog drafts. Returns script rows and count without generating or changing a draft.",
    "get_script": "Read a saved video-script version, including beats, shot list and source-item citations. Use after list_scripts; use revise_script for a new version or get_shot_list to regenerate camera cues. Supply id or its script_id alias; id takes precedence. Returns the script object or a not-found error.",
    "write_tweet": "Prepare grounding for a tweet or thread, or save a credited draft in the local Writing Studio. Use for short social drafts; use write_blog for articles or generate_script for video scripts. Without body, returns grounding unless direct generation is requested with the saved Anthropic key. With body, saves the agent's draft and returns soft Voice DNA warnings. Creator credit cannot be suppressed. Direct generation sends context to Anthropic and retries fatal phrase violations once before refusing to save; nothing is posted to a social account.",
    "write_blog": "Prepare grounding for a blog article, or save a credited Markdown draft in the local Writing Studio. Use for long prose; use write_tweet for tweets and threads or generate_script for video scripts. Without body, returns grounding unless direct generation is requested with the saved Anthropic key. With body, saves the agent's draft and returns soft Voice DNA warnings. Keep the required Source credit. Direct generation sends context to Anthropic and retries fatal phrase violations once before refusing to save; nothing is published to a website.",
    "list_writing_pieces": "List saved tweet, thread and blog drafts newest first, optionally filtered by kind or source item. Use to find a piece ID for get_writing_piece; use list_scripts for video-script versions. Returns pieces and count. The list contains local drafts, not posts fetched from social or publishing accounts.",
    "get_writing_piece": "Read one saved Writing Studio tweet, thread or blog draft. Use after list_writing_pieces; use write_tweet or write_blog to save another draft, or get_script for video scripts. Supply id or its piece_id alias; id takes precedence. Returns the piece object or a not-found error.",
    "add_style_anchor": "Save a named writing-style reference from pasted text or a URL. Use to guide later write_tweet/write_blog drafts; use list_style_anchors to select existing references. URL references fetch prose through the page extractor and can retain null raw_text if extraction fails. Returns the anchor; more than ten anchors is refused. Style references do not authorize copying source facts or suppressing creator credit.",
    "list_style_anchors": "List saved writing-style references with active flags and the configured ten-anchor cap. Use to select style_anchor_ids for write_tweet or write_blog; use add_style_anchor to save a reference or remove_style_anchor to delete one. Returns anchors and count without refetching URL contents.",
    "remove_style_anchor": "Delete a saved writing-style reference. Use after list_style_anchors identifies the reference; use add_style_anchor to save a replacement. Supply anchor_id or its id alias; anchor_id takes precedence. Returns the selected ID and whether it was removed. Previously saved writing pieces remain.",
    "uoink_url": "Capture a supported video URL through platform routing, with metadata/transcript fallback for other yt-dlp sites. Use for non-YouTube videos or long-video modes; use uoink_video for a single standard YouTube capture, uoink_page for webpage prose, uoink_x for X text chains, or uoink_reddit_thread for discussion comments. Requires the local media runtime. Saves a local corpus; generic fallback has no screenshots, comment fetch or hook classification. Recapturing a source can replace its saved corpus and metadata.",
    "uoink_note": "Save user-provided text as a local searchable note with title and attribution. Use for pasted ideas or prose without fetching a source; use uoink_page for a web article or uoink_image for pixels. Returns the saved item ID, slug and metadata. Empty or invalid notes are refused; title can be derived from the text.",
    "uoink_image": "Save supplied PNG, JPEG or WebP bytes as a local image corpus item with optional caption and attribution. Use for screenshots, diagrams or images; use uoink_note for text or uoink_page to fetch a webpage. Accepts strict base64 or a data URL and returns the saved item ID, slug and metadata. Invalid images are refused. No cloud OCR or vision service runs.",
    "uoink_x": "Capture an X post and its author's earlier chain as a local text corpus item. Use for post text; use uoink_url for an X video capture or uoink_page for general webpage prose. Requires x_text_capture_enabled and public source access. Returns the saved item ID, title, captured-tweet count and metadata; disabled capture or extraction failure returns an error. Recapturing a source can replace its saved corpus and metadata.",
    "uoink_page": "Fetch an allowed webpage as Markdown and save it as a local corpus item. Use for articles and documentation; use uoink_url for videos, uoink_x for post chains or uoink_reddit_thread for comments. Add an unlisted host with add_allowed_site only with user authorization. Crawl4AI renders locally when available; static fallback has no screenshot. Returns extracted content and metadata; video_id is null if extraction succeeded but persistence failed. Recapturing a source can replace its saved corpus and metadata.",
    "uoink_reddit_thread": "Capture a Reddit post and filtered comment tree as a local discussion corpus. Use when replies matter; use uoink_page for general webpage prose or uoink_url for video extraction. Fetches Reddit's public JSON without API credentials or the page allowlist, then saves nested replies with source_type reddit_thread. Returns captured content, comment counts and the saved item ID; fetch or save failures return an error. Recapturing a source can replace its saved corpus and metadata.",
    "list_allowed_sites": "List saved webpage-capture hostname patterns and their active state. Use before uoink_page to check access; use add_allowed_site or remove_allowed_site to change the allowlist. Returns sites, count and default seeds. Seeds can be removed like other entries; this call does not test reachability or fetch pages.",
    "add_allowed_site": "Add a hostname pattern to the webpage-capture allowlist. Use for a user-authorized uoink_page destination; use list_allowed_sites to inspect rules or remove_allowed_site to revoke one. Plain hosts include subdomains; wildcard patterns match their specified subdomains. Returns the saved rule and reuses an existing pattern unchanged. This grants future page access but does not capture a page.",
    "remove_allowed_site": "Remove a hostname pattern from the webpage-capture allowlist. Use to revoke a rule found by list_allowed_sites; use add_allowed_site to restore it. Returns the normalized pattern and whether a rule was removed. Saved captures remain, and overlapping rules can still allow the same host.",
}

# Existing constraints, enums and defaults remain authoritative. These strings
# document the client view without modifying the frozen validator schemas.
PARAMETERS = {
    "active_only": "Only return rows whose active flag is set; omit to include inactive rows.",
    "enabled_only": "Only return registrations with monitoring enabled; this does not imply capture consent.",
    "limit": "Maximum rows to return in this response; does not change stored data.",
    "video_id": "Stable saved-item identifier from a search or capture result; not necessarily a YouTube ID.",
    "yoink_id": "Stable source-item identifier from a capture or search result.",
    "source_yoink_id": "Saved item to ground the draft and creator credit; omit for a draft without a source item.",
    "slug": "Saved item's folder slug from list_recent_uoinks or search_uoinks.",
    "feed_id": "Integer feed ID returned by add_podcast_feed or list_podcast_feeds.",
    "episode_id": "Integer episode ID from list_podcast_episodes, not the feed ID.",
    "playlist_id": "Integer monitor ID from add_monitored_playlist or list_monitored_playlists.",
    "feed_url": "Public HTTP(S) RSS or Atom feed URL, not the podcast's homepage.",
    "playlist_url": "YouTube playlist URL containing its list identifier.",
    "poll_interval_min": "Requested interval between metadata checks, in minutes; not a capture deadline.",
    "auto_ingest": "Explicit podcast audio-ingest preference; false unless the user opted in. Standing-source capture consent is separate.",
    "query": "Nonempty search text to match against saved content.",
    "channel": "Saved channel name to restrict the results; omit for all channels.",
    "hook_type": "Stored opening-hook classification to write or match; see get_facet_taxonomy for hook labels.",
    "format": "Content format label, such as tutorial or talking_head; see get_facet_taxonomy.",
    "performance_tier": "Channel-relative performance label: over, average or under.",
    "length_bucket": "Duration bucket: short, medium, long or deep; see get_facet_taxonomy.",
    "production_style": "Free-form description of how the item was produced.",
    "topic": "Stored topic label used to classify or select examples.",
    "tag": "One saved tag that each returned item must have.",
    "tags": "Free-form labels to attach to the saved item or draft.",
    "job_id": "Job identifier returned by a capture or transcription queue operation.",
    "workspace_id": "Saved workspace identifier from list_workspaces or get_workspace.",
    "script_id": "Integer script-version ID from list_scripts, generate_script or revise_script.",
    "claim_id": "Integer claim ID from extract_claims or list_claims.",
    "piece_id": "Alias for id; use a saved writing-piece ID from list_writing_pieces.",
    "anchor_id": "Integer style-reference ID from list_style_anchors.",
    "name": "User-facing name for this saved registration or reference.",
    "title": "Display title for the saved content; omit to use the handler's derived/default title.",
    "author": "Attribution name supplied by the user; not an account to authenticate.",
    "text": "Nonempty note text to save, including any Markdown formatting.",
    "image_base64": "Base64-encoded PNG, JPEG or WebP bytes; a data URL prefix is also accepted.",
    "mime": "Image media type, such as image/png, image/jpeg or image/webp; omit for detection.",
    "filename": "Original image filename used as a naming hint, not a destination path.",
    "caption": "User-supplied image description stored with the item; no image analysis is performed.",
    "source_url": "Original source URL to store for attribution; this field does not fetch it.",
    "url_pattern": "Hostname or wildcard hostname pattern, without whitespace; for example example.com or *.docs.example.com.",
    "render_mode": "js requests local browser rendering when available; static requests HTML extraction.",
    "include_screenshot": "Request a page screenshot when the renderer supports it; static fallback has none.",
    "follow_links_depth": "Requested linked-page depth passed to the extractor; current capture does not recursively persist linked pages.",
    "depth_limit": "Maximum nested comment depth to retain; zero excludes deeper reply levels.",
    "score_threshold": "Minimum Reddit comment score to retain; lower values include less-upvoted comments.",
    "long_video_mode": "full runs normal extraction; lite requests the helper's reduced long-video capture path.",
    "role": "User's dashboard emphasis preference; changes sorting and filter-chip priority.",
    "section": "Taste-preference section whose saved Markdown body will be replaced.",
    "content": "Replacement Markdown for the selected taste section; existing text in that section is replaced.",
    "your_channel": "Registered own-channel handle used to add a self-analysis snapshot.",
    "hook_target": "Desired hook classification used to guide the workspace's example selection.",
    "n_examples": "Maximum saved examples to assemble for this planning context.",
    "draft_text": "Draft to critique against the workspace's saved examples.",
    "findings": "Agent-written critique object, for example hook_strength, structural_deviation, pacing_issues and missing_audience_hooks; omit to get grounding only.",
    "claims": "Agent-extracted objects with claim_text, optional check_worthiness from 0 to 1 and optional context object. Invalid entries are skipped and reported in errors.",
    "evidence": "Evidence objects with source_url, quote and alignment_signal (supports, contradicts, mixed or inconclusive). Existing evidence is replaced; quotes are stored up to 1024 characters.",
    "script": "Agent-written object with hook, beats, body, cta and source_yoinks citations; optional shot_list. Omit to retrieve grounding only.",
    "revised_script": "Replacement script object with the same fields as generate_script.script; omit for revision context only.",
    "parent_script_id": "Prior script-version ID to link as this version's parent; omit for an initial draft.",
    "critique_findings": "Agent-supplied findings to include in revision context; the server does not analyze them.",
    "revision_target": "Requested revision focus supplied to the agent alongside the previous script.",
    "mode": "Compute provenance label: agent or byo_key. The caller still supplies the analysis; this field alone does not run a provider model.",
    "angle": "Requested editorial focus for the draft's grounding or direct-generation prompt.",
    "target_length_chars": "Desired character length for the writing prompt; not a hard persistence limit.",
    "target_length_words": "Desired word length for the writing prompt; not a hard persistence limit.",
    "style_anchor_ids": "Saved style-reference IDs from list_style_anchors to include in writing context.",
    "body": "Agent-written draft text, including mandatory source credit; omit for grounding or explicitly requested direct generation.",
    "source_credit_line": "Exact creator-credit line to retain in the body; use the line supplied by grounding.",
    "skip_voice_dna_this_time": "Skip the Voice DNA check for this save; does not waive mandatory source credit.",
    "suppress_credit": "Must not be true: suppressing creator credit is rejected.",
    "parent_id": "Earlier writing-piece ID to link as this draft's parent version.",
    "dek": "Optional short subtitle beneath a blog title.",
    "source_type": "url fetches a style reference from the web; text stores the supplied prose directly.",
    "source_value": "HTTP(S) URL when source_type is url, or the pasted reference text when it is text.",
    "profile": "full includes the normal evidence card; librarian selects the smaller assignment-oriented card.",
    "n_clips": "Requested number of timeline-spread evidence clips; omit for the selected profile's default.",
    "model": "Local WhisperX model size; omit to use the saved model setting.",
    "language": "Whisper language code, such as en; omit for automatic language detection.",
    "diarize": "Request speaker diarization; omit to use the saved default and its runtime prerequisites.",
    "consent_given": "True only after the user opted in through the dashboard to the required first-time model download.",
    "run_id": "Librarian run identifier from list_library_work; omission selects the service's default run where allowed.",
    "cursor": "Opaque cursor from the previous response; pass unchanged to continue the same listing.",
    "state": "Work-state filter; all includes every state rather than only ready assignments.",
    "client_id": "Stable identifier for your Librarian client; use the same value through claim, renew and submit.",
    "max_items": "Maximum single-item packets to lease in this claim.",
    "lease_seconds": "Requested lease duration in seconds; renewal cannot extend past the attempt's absolute lifetime.",
    "work_id": "Work-row identifier returned by claim_library_work, distinct from the source item ID.",
    "attempt_token": "Opaque token for your current leased attempt; copy from claim_library_work and do not invent it.",
    "reason": "Human-readable explanation for the requested action or non-assignment outcome.",
    "submission_key": "Client-generated retry key; reuse only for an identical submission.",
    "schema_version": "Result contract version required by the claimed packet.",
    "source_revision": "Revision of the saved source evidence; copy from the packet or retrieval result to detect stale input.",
    "taxonomy_revision": "Taxonomy hash from the leased packet; copy unchanged into the submission.",
    "packet_hash": "Hash of the exact leased input packet; copy unchanged from claim_library_work.",
    "result": "Assignment outcome with evidenced shelf memberships, or unmapped/unsupported/error with a reason; conforms to the referenced result schema.",
    "usage": "Actual client model usage, or an explicit unavailable report when measurements are missing; never invent zero usage.",
    "expected_projection_revision": "Current label-projection revision from the library response; stale writes are refused.",
    "activate_version": "Whether the preview should activate this run's taxonomy version when applied.",
    "preview_id": "Unexpired preview identifier returned by apply_reshelving in preview mode.",
    "delta_hash": "Exact proposed-change hash returned with the preview; prevents applying a different delta.",
    "operation_key": "Client-generated key for an identical-operation retry; do not reuse it for different arguments.",
    "shelf_id": "Stable target shelf identifier from the library taxonomy or evidence packet.",
    "user_intent_token": "Operation-bound capability minted after local dashboard confirmation; agents cannot mint it or substitute an actor field.",
    "apply_id": "Journal apply identifier whose resulting projection revision is still current.",
    "source_id": "Standing-source identifier returned by register_source or list_sources.",
    "consent_state": "on enables consent-controlled standing captures; off releases unstarted reservations while retaining detection.",
    "include_archived": "Include archived registrations as well as current sources.",
    "display_name": "Human-readable source label; omit to use the source's default display name.",
    "item_limit": "Maximum observed items in this source-status page; reservations are returned separately.",
    "item_cursor": "Opaque observed-item cursor from the previous source_status response.",
    "expected_revision": "Current source revision from source_status; a changed source requires refreshing it.",
    "expected_cursor_revision": "Detection-cursor revision from source_status, required when enabling consent and forbidden when disabling it.",
    "playbook": "Research packet to prepare; its name selects the allowed arguments and required selectors.",
    "arguments": "String-valued playbook arguments: outlier-posts/creator-teardown require author (optional platform); outlier-posts also accepts since. transcript-intel needs exactly one of video_ids/topic/author (optional since). comment-mining needs video_ids or author and optional lens=voc/demand. repurpose-pack requires video_ids and optional kinds. IDs/kinds are comma-separated strings; ID caps are 8, 10 and 5 respectively. since is a UTC YYYY-MM-DD capture date, not future.",
    "platform": "Remote platform for the discovery search; the mode/platform pair must be supported.",
    "channel_id": "YouTube channel ID beginning UC, as an alternative to handle in creator mode only.",
    "pages": "Maximum discovery pages to request; each planned page consumes one confirmed credit.",
    "confirm_credits": "Exact credits_planned from the free plan; omit to request the plan without spending.",
    "keys": "Candidate keys from the selected discovery run; only these saved candidates are considered for capture.",
    "date": "UTC day for the operational brief, YYYY-MM-DD, not in the future.",
    "job_key": "Brief job_key returned by get_library_brief_input; copy unchanged.",
    "input_hash": "Brief input_hash returned by get_library_brief_input; copy unchanged.",
    "input_packet": "Exact unmodified packet returned by get_library_brief_input.",
    "document": "Client-written brief Markdown within the 8192-byte UTF-8 limit, with evidence-bound citations.",
    "citations": "Evidence citations carrying item_id, source_revision, card_hash, excerpt_id, quote, evidence_kind, start and end; copy identifiers from the input packet.",
    "uri": "Canonical uoink://library/v1/ resource URI returned by library retrieval; preserve its revision and paging components.",
    "media_revision": "Optional expected media snapshot revision; mismatches return revision_unavailable.",
    "excerpt_id": "Current excerpt identifier instead of explicit cue-aligned start and end bounds.",
    "offset": "Zero-based offset into the chosen detail collection, under the same report revision.",
    "metric_id": "Stable metric identifier from the summary; required when requesting evidence detail.",
    "detail": "Detail collection to page; omit for the summary and its report_revision.",
    "date_basis": "Use capture timestamps or original publication timestamps for the item report.",
}

OVERRIDES = {
    "search_uoinks": {"mode": "auto prefers hybrid when the local semantic index is ready, otherwise keyword; explicit semantic/hybrid can also fall back with a reason."},
    "search_clips": {"mode": "auto prefers hybrid when the local semantic index is ready, otherwise keyword; explicit semantic/hybrid can also fall back with a reason."},
    "search_library": {"mode": "auto prefers hybrid when the local semantic index is ready, otherwise keyword; explicit semantic/hybrid can also fall back with a reason."},
    "uoink_video": {"url": "YouTube watch or youtu.be video URL; playlists use uoink_playlist."},
    "uoink_playlist": {"url": "YouTube playlist URL with a list identifier; individual videos use uoink_video."},
    "uoink_url": {"url": "HTTP(S) video/source URL accepted by yt-dlp's supported extractors.", "interval": "Seconds between screenshots in the full media pipeline; ignored by metadata-only fallback."},
    "check_live_status": {"url": "Public HTTP(S) video URL whose metadata should be probed."},
    "uoink_page": {"url": "HTTP(S) webpage URL whose hostname matches an active page allowlist rule."},
    "uoink_x": {"url": "Public x.com or twitter.com status URL for the terminal post in the desired author chain."},
    "uoink_reddit_thread": {"url": "reddit.com/r/<sub>/comments/... thread URL."},
    "get_workspace": {"id": "Preferred workspace ID from list_workspaces; takes precedence over workspace_id."},
    "get_claim": {"id": "Preferred claim ID from list_claims; takes precedence over claim_id."},
    "get_script": {"id": "Preferred script-version ID from list_scripts; takes precedence over script_id."},
    "get_writing_piece": {"id": "Preferred writing-piece ID from list_writing_pieces; takes precedence over piece_id."},
    "remove_style_anchor": {"id": "Alias for anchor_id, used only when anchor_id is absent."},
    "discover_candidates": {
        "mode": "creator requires exactly one of handle/channel_id; keyword requires query and excludes both creator selectors.",
        "handle": "Creator handle, optionally prefixed @; use instead of channel_id in creator mode.",
        "query": "Remote keyword-search phrase; required only in keyword mode.",
        "user_intent_token": "Optional dashboard discovery intent bound to this process and operation. Stdio must use the enabled agent-discovery consent setting instead.",
    },
    "queue_discovered": {
        "run_id": "Saved discovery run_id returned by discover_candidates, not a Librarian run ID.",
        "user_intent_token": "Optional dashboard queue intent bound to this process and operation. Stdio must use the enabled agent-discovery consent setting instead.",
    },
    "analyze_self_channel": {"handle": "Registered own-channel handle, with or without @; omit for all recognized own channels."},
    "claim_library_work": {"action": "claim acquires packets; renew extends your lease; release returns your attempt; cancel cancels it. Non-claim actions require work_id and attempt_token."},
    "apply_reshelving": {"mode": "preview creates a proposal and requires run_id; apply requires preview_id, delta_hash and operation_key and must pass the local apply gate."},
    "pin_shelf": {"action": "pin protects this membership; unpin removes its pin; move records a user-directed placement on the target shelf."},
    "list_podcast_episodes": {"status": "Episode lifecycle filter: new, queued, downloaded, transcribed or ignored."},
    "list_monitored_playlist_events": {"status": "Discovery lifecycle filter: discovered, queued, extracted or failed."},
    "list_claims": {"status": "Review lifecycle filter; verified means evidence recorded, not proven true."},
    "list_writing_pieces": {"kind": "Saved draft format to include; omit to include tweet, thread and blog pieces."},
    "register_source": {"kind": "Source adapter: podcast RSS feed, YouTube channel or YouTube playlist.", "url": "Public HTTP(S) feed, channel or playlist URL matching kind; normalized into a stable source identity."},
    "list_sources": {"kind": "Only list sources using this feed, channel or playlist adapter."},
    "get_library_activity": {"expected_revision": "Summary report_revision required for detail pages; refresh the summary after a mismatch."},
    "get_library_brief_input": {"run_id": "Librarian assignment run ID whose work status belongs in the brief."},
    "publish_library_brief": {"usage": "Actual client-reported usage object, or null if unavailable; never invent zero measurements."},
}


def document_input_schema(schema, tool_name):
    """Add descriptions only to a fresh client schema; never alter constraints."""
    result = deepcopy(schema)
    overrides = OVERRIDES.get(tool_name, {})
    for name, prop in result.get("properties", {}).items():
        description = overrides.get(name) or PARAMETERS.get(name)
        if description:
            prop["description"] = description
    return result


def without_descriptions(value):
    """Compare validation contracts while ignoring documentation strings."""
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key == "description":
                continue
            if key in {"const", "enum", "default", "examples"}:
                # Literal data can contain a key named description. It is not
                # schema documentation and must remain part of the contract.
                result[key] = deepcopy(child)
            elif key in {"properties", "patternProperties", "$defs", "definitions",
                         "dependentSchemas", "dependencies"} and isinstance(child, dict):
                result[key] = {name: without_descriptions(schema) for name, schema in child.items()}
            else:
                result[key] = without_descriptions(child)
        return result
    if isinstance(value, list):
        return [without_descriptions(v) for v in value]
    return value


def _output(fields):
    """Document the existing JSON result envelope, including failure results."""
    return {
        "type": "object",
        "description": "JSON result envelope; ok distinguishes success from failure. HTTP returns it as structuredContent and JSON text.",
        "properties": {
            "ok": {"type": "boolean", "description": "True for a successful operation; false for a refusal or failure."},
            "error": {"type": ["string", "object"], "description": "Failure message or structured refusal with code and recovery details; present on failure."},
            **fields,
        },
        "required": ["ok"],
        "allOf": [{"if": {"properties": {"ok": {"const": True}}},
                   "then": {"required": list(fields)},
                   "else": {"required": ["error"]}}],
    }


def _field(kind, description, **extra):
    return {"type": kind, "description": description, **extra}


OUTPUT_SCHEMAS = {
    "uoink_video": _output({
        "slug": _field("string", "Saved capture's folder slug for later corpus reads."),
        "folder": _field("string", "Absolute local capture folder."),
        "corpus_md": _field("string", "Captured Markdown corpus."),
        "screenshots": _field("array", "Saved screenshot file paths.", items={"type": "string"}),
    }),
    "uoink_playlist": _output({"job_id": _field("string", "Asynchronous capture identifier for get_job_status or cancel_job.")}),
    "get_uoink_corpus": _output({
        "corpus_md": _field("string", "Complete saved Markdown document."),
        "folder": _field("string", "Absolute local folder holding the corpus."),
        "video_id": _field(["string", "null"], "Saved source-item identifier when available."),
        "video_url": _field(["string", "null"], "YouTube watch URL when the source is a YouTube item."),
        "source_url": _field(["string", "null"], "Original source URL from the sidecar."),
        "citations": _field("array", "Stored citation rows for this source; empty if unavailable.", items={"type": "object"}),
    }),
    "get_citation_map": _output({
        "video_id": _field("string", "Saved source identifier."),
        "transcript_citations": _field("array", "Transcript cue rows with seq, timestamp_start/end, text, source_url and deep_link.", items={"type": "object"}),
        "screenshot_citations": _field("array", "Screenshot rows with seq, timestamp, file_path, source_url and deep_link.", items={"type": "object"}),
    }),
    "get_uoink_health": _output({
        "video_id": _field(["string", "null"], "Saved source identifier if present."),
        "health": _field("object", "Stored extraction-health snapshot, including per-section outcomes."),
    }),
    "get_transcript_reliability": _output({
        "video_id": _field("string", "Requested saved item identifier."),
        "reliability": _field("object", "Stored status and suspect spans; absent computation returns not_computed with an empty spans list."),
    }),
    "get_schema_version": _output({
        "sql_migration": _field(["integer", "null"], "Highest applied SQL migration, or null if unreadable."),
        "yoink_schema": _field("integer", "Item-row schema version currently written."),
        "sidecar_schema": _field("integer", "Sidecar schema version currently written."),
        "yoink_schema_supported": _field("array", "Inclusive minimum and maximum supported item-row versions.", items={"type": "integer"}),
        "sidecar_schema_supported": _field("array", "Inclusive minimum and maximum supported sidecar versions.", items={"type": "integer"}),
    }),
    "get_user_role": _output({
        "role": _field("string", "Normalized persisted dashboard role."),
        "emphasis": _field("object", "Resolved dashboard filter-chip order and sort preference."),
        "supported_roles": _field("array", "Allowed dashboard role values.", items={"type": "string"}),
    }),
    "set_user_role": _output({
        "role": _field("string", "Normalized saved dashboard role."),
        "emphasis": _field("object", "Dashboard emphasis resolved from the new role."),
    }),
    "get_workspace": _output({
        "workspace": _field("object", "Saved workspace settings and selected source items."),
        "critique_log": _field("array", "Stored draft-and-findings history; empty when unavailable.", items={"type": "object"}),
    }),
    "extract_claims": _output({
        "video_id": _field("string", "Source item to which inserted claims belong."),
        "inserted_ids": _field("array", "IDs of successfully saved claims.", items={"type": "integer"}),
        "errors": _field("array", "Reasons individual invalid claims were skipped; success can include partial errors.", items={"type": "string"}),
        "mode": _field("string", "Caller-declared compute provenance."),
    }),
    "verify_claim": _output({
        "claim_id": _field("integer", "Claim whose evidence was replaced."),
        "evidence_count": _field("integer", "Number of stored evidence entries."),
        "mode": _field("string", "Caller-declared compute provenance; not a truth verdict."),
    }),
    "get_shot_list": _output({
        "script_id": _field("integer", "Script updated with the derived shot list."),
        "shot_list": _field("array", "One row per beat with scene number, label, suggested cues and notes.", items={"type": "object"}),
        "format": _field(["string", "null"], "Workspace format used for cue suggestions, if available."),
    }),
    "remove_style_anchor": _output({
        "removed": _field("boolean", "Whether the selected style reference was removed."),
        "id": _field("integer", "Selected style-reference identifier."),
    }),
    "remove_allowed_site": _output({
        "removed": _field("boolean", "Whether the specified allowlist row was deleted."),
        "url_pattern": _field("string", "Normalized lowercase pattern that was selected."),
    }),
}

# These handlers return a stable named collection and, where applicable, count.
for _name, _collection, _meaning, _count in (
    ("list_recent_uoinks", "yoinks", "Recent saved items with slug, title, folder and yoinked_at.", False),
    ("find_mentions", "mentions", "Indexed entity matches with stored spans, timing and source links.", False),
    ("get_taxonomy", "taxonomy", "Saved hook-classification rows matching the filters.", False),
    ("list_podcast_feeds", "feeds", "Registered podcast feed rows, newest first.", True),
    ("list_podcast_episodes", "episodes", "Tracked episode rows, newest published first.", True),
    ("list_monitored_playlists", "playlists", "Playlist monitor rows, newest first.", True),
    ("list_monitored_playlist_events", "events", "Saved playlist-discovery rows, newest first.", True),
    ("query_by_facets", "yoinks", "Saved item rows matching every supplied facet.", True),
    ("list_workspaces", "workspaces", "Saved planning workspace rows, newest first.", True),
    ("list_claims", "claims", "Stored claim rows, with evidence review state.", True),
    ("list_scripts", "scripts", "Saved script-version rows, newest first.", True),
    ("list_writing_pieces", "pieces", "Saved tweet, thread and blog draft rows, newest first.", True),
):
    _fields = {_collection: _field("array", _meaning, items={"type": "object"})}
    if _count:
        _fields["count"] = _field("integer", "Number of rows returned in this response, not a total across pages.")
    OUTPUT_SCHEMAS[_name] = _output(_fields)

for _name, _key, _meaning in (
    ("get_job_status", "job", "Current public job state, progress and per-item outcomes."),
    ("cancel_job", "job", "Public job state after cancellation was requested."),
    ("get_claim", "claim", "Saved claim with its recorded evidence and alignment signals."),
    ("get_script", "script", "Saved script version with beats, shot list and source citations."),
    ("get_writing_piece", "piece", "Saved Writing Studio draft and associated metadata."),
    ("add_style_anchor", "anchor", "Saved style reference; URL extraction can leave raw_text null."),
    ("add_podcast_feed", "feed", "New or existing podcast feed registration."),
    ("add_monitored_playlist", "playlist", "New or existing playlist monitor registration."),
    ("add_allowed_site", "site", "New or existing allowlist rule, unchanged on a duplicate."),
):
    OUTPUT_SCHEMAS[_name] = _output({_key: _field("object", _meaning)})

for _name in ("remove_podcast_feed", "remove_monitored_playlist"):
    OUTPUT_SCHEMAS[_name] = _output({"removed": _field("boolean", "Whether the registration was archived/disabled or deleted.")})


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "uoink_video": ToolSpec(
        name="uoink_video",
        title="Capture video",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["uoink_video"]
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
        title="Capture playlist",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=DESCRIPTIONS["uoink_playlist"],
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
        title="Get job status",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_job_status"],
        input_schema=_schema({
            "job_id": {"type": "string", "description": "Job ID from uoink_playlist."},
        }, ["job_id"]),
        handler=get_job_status,
    ),
    "cancel_job": ToolSpec(
        name="cancel_job",
        title="Cancel job",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["cancel_job"],
        input_schema=_schema({
            "job_id": {"type": "string", "description": "Job ID to cancel."},
        }, ["job_id"]),
        handler=cancel_job,
    ),
    "list_recent_uoinks": ToolSpec(
        name="list_recent_uoinks",
        title="List recent captures",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["list_recent_uoinks"],
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
        title="Search captures",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["search_uoinks"],
        input_schema=_schema({
            "mode": {"type": "string", "enum": ["auto", "keyword", "semantic", "hybrid"],
                      "default": "auto",
                      "description": "Auto uses hybrid when the local semantic index is ready, otherwise keyword."},
            "match": {"type": "string", "enum": ["forgiving", "strict"],
                      "default": "forgiving",
                      "description": "Forgiving matches useful words; strict requires every word."},
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
    "search_clips": ToolSpec(
        name="search_clips",
        title="Search transcript clips",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["search_clips"]
        ),
        input_schema=_schema({
            "mode": {"type": "string", "enum": ["auto", "keyword", "semantic", "hybrid"],
                      "default": "auto",
                      "description": "Auto uses hybrid when the local semantic index is ready, otherwise keyword."},
            "match": {"type": "string", "enum": ["forgiving", "strict"],
                      "default": "forgiving",
                      "description": "Forgiving matches useful words; strict requires every word."},
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            "video_id": {
                "type": "string",
                "description": "Restrict results to one item by video_id. Optional.",
            },
            "channel": {
                "type": "string",
                "description": "Filter results to one channel. Optional.",
            },
        }, ["query"]),
        handler=search_clips,
        rate_limiter=_RateLimiter(30),
    ),
    "get_evidence_card": ToolSpec(
        name="get_evidence_card",
        title="Get evidence card",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_evidence_card"]
        ),
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
            "video_id": {"type": "string", "description": "Alternative to slug."},
            "profile": {"type": "string", "enum": ["full", "librarian"], "default": "full"},
            "n_clips": {"type": "integer", "minimum": 1, "maximum": 20},
        }),
        handler=get_evidence_card,
        rate_limiter=_RateLimiter(30),
    ),
    # ---- Living Library work queue (Phase 2 stage 1; both MCP transports) ----
    # Rate limits live inside _library_call so a throttled caller still gets
    # the contract's error envelope rather than the plain string one.
    "list_library_work": ToolSpec(
        name="list_library_work",
        title="List library work",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_library_work"]
        ),
        input_schema=LIBRARY_TOOL_SCHEMAS["list_library_work"],
        handler=list_library_work,
    ),
    "claim_library_work": ToolSpec(
        name="claim_library_work",
        title="Claim library work",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["claim_library_work"]
        ),
        input_schema=LIBRARY_TOOL_SCHEMAS["claim_library_work"],
        handler=claim_library_work,
    ),
    "submit_library_result": ToolSpec(
        name="submit_library_result",
        title="Submit library result",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["submit_library_result"]
        ),
        input_schema=LIBRARY_TOOL_SCHEMAS["submit_library_result"],
        handler=submit_library_result,
    ),
    "apply_reshelving": ToolSpec(
        name="apply_reshelving",
        title="Apply reshelving",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["apply_reshelving"]
        ),
        input_schema=LIBRARY_TOOL_SCHEMAS["apply_reshelving"],
        handler=apply_reshelving,
    ),
    "pin_shelf": ToolSpec(
        name="pin_shelf",
        title="Pin library shelf",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["pin_shelf"]
        ),
        input_schema=LIBRARY_TOOL_SCHEMAS["pin_shelf"],
        handler=pin_shelf,
    ),
    "undo_library_apply": ToolSpec(
        name="undo_library_apply",
        title="Undo library apply",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["undo_library_apply"]
        ),
        input_schema=LIBRARY_TOOL_SCHEMAS["undo_library_apply"],
        handler=undo_library_apply,
    ),
    # ---- Living Library standing sources (Phase 3, run AM) ----
    # Rate limits and the capability check live inside sources_call so every
    # transport returns the contract's error envelope.
    "list_sources": ToolSpec(
        name="list_sources",
        title="List standing sources",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_sources"]
        ),
        input_schema=_sources_tool_schema("list_sources"),
        handler=list_sources,
    ),
    "register_source": ToolSpec(
        name="register_source",
        title="Register standing source",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["register_source"]
        ),
        input_schema=_sources_tool_schema("register_source"),
        handler=register_source,
    ),
    "source_status": ToolSpec(
        name="source_status",
        title="Get source status",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["source_status"]
        ),
        input_schema=_sources_tool_schema("source_status"),
        handler=source_status,
    ),
    "set_source_consent": ToolSpec(
        name="set_source_consent",
        title="Set source consent",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["set_source_consent"]
        ),
        input_schema=_sources_tool_schema("set_source_consent"),
        handler=set_source_consent,
    ),
    "get_uoink_corpus": ToolSpec(
        name="get_uoink_corpus",
        title="Get saved corpus",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_uoink_corpus"],
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=get_uoink_corpus,
    ),
    "analyze_comments": ToolSpec(
        name="analyze_comments",
        title="Analyze comments",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["analyze_comments"]
        ),
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=analyze_comments_tool,
        rate_limiter=_RateLimiter(10),
    ),
    "classify_hook": ToolSpec(
        name="classify_hook",
        title="Classify hook",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=DESCRIPTIONS["classify_hook"],
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=classify_hook,
        rate_limiter=_RateLimiter(10),
    ),
    "get_taxonomy": ToolSpec(
        name="get_taxonomy",
        title="Get hook taxonomy",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_taxonomy"]
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
        title="Get citation map",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_citation_map"]
        ),
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=get_citation_map,
        rate_limiter=_RateLimiter(60),
    ),
    "get_uoink_health": ToolSpec(
        name="get_uoink_health",
        title="Get capture health",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_uoink_health"],
        input_schema=_schema({
            "slug": {"type": "string", "description": "Folder slug of the saved uoink."},
        }, ["slug"]),
        handler=get_uoink_health,
        rate_limiter=_RateLimiter(60),
    ),
    "find_mentions": ToolSpec(
        name="find_mentions",
        title="Find entity mentions",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["find_mentions"]
        ),
        input_schema=_schema({
            "match": {"type": "string", "enum": ["forgiving", "strict"],
                      "default": "forgiving",
                      "description": "Forgiving matches entity name words; strict requires the exact normalized name."},
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
        title="Analyze own channel",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["analyze_self_channel"]
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
        title="Get storage schema version",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_schema_version"]
        ),
        input_schema=_schema({}, []),
        handler=get_schema_version,
        rate_limiter=_RateLimiter(60),
    ),
    "get_user_role": ToolSpec(
        name="get_user_role",
        title="Get user role",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_user_role"]
        ),
        input_schema=_schema({}, []),
        handler=get_user_role,
        rate_limiter=_RateLimiter(60),
    ),
    "set_user_role": ToolSpec(
        name="set_user_role",
        title="Set user role",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["set_user_role"]
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
        title="Check live video status",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["check_live_status"]
        ),
        input_schema=_schema({
            "url": {"type": "string"},
        }, ["url"]),
        handler=check_live_status,
        rate_limiter=_RateLimiter(30),
    ),
    "add_podcast_feed": ToolSpec(
        name="add_podcast_feed",
        title="Add podcast feed",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["add_podcast_feed"]
        ),
        input_schema=_schema({
            "feed_url": {"type": "string"},
            "poll_interval_min": {"type": "integer",
                                    "minimum": 15, "maximum": 1440,
                                    "default": 60},
            "auto_ingest": {"type": "boolean", "default": False},
        }, ["feed_url"]),
        handler=add_podcast_feed,
        rate_limiter=_RateLimiter(30),
    ),
    "list_podcast_feeds": ToolSpec(
        name="list_podcast_feeds",
        title="List podcast feeds",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["list_podcast_feeds"],
        input_schema=_schema({
            "enabled_only": {"type": "boolean", "default": False},
        }, []),
        handler=list_podcast_feeds,
        rate_limiter=_RateLimiter(60),
    ),
    "remove_podcast_feed": ToolSpec(
        name="remove_podcast_feed",
        title="Remove podcast feed",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["remove_podcast_feed"]
        ),
        input_schema=_schema({
            "feed_id": {"type": "integer"},
        }, ["feed_id"]),
        handler=remove_podcast_feed,
        rate_limiter=_RateLimiter(30),
    ),
    "poll_podcast_feed": ToolSpec(
        name="poll_podcast_feed",
        title="Poll podcast feed",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["poll_podcast_feed"]
        ),
        input_schema=_schema({
            "feed_id": {"type": "integer"},
        }, ["feed_id"]),
        handler=poll_podcast_feed,
        rate_limiter=_RateLimiter(30),
    ),
    "list_podcast_episodes": ToolSpec(
        name="list_podcast_episodes",
        title="List podcast episodes",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_podcast_episodes"]
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
        title="Download podcast audio",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["download_podcast_episode"]
        ),
        input_schema=_schema({
            "episode_id": {"type": "integer"},
        }, ["episode_id"]),
        handler=download_podcast_episode,
        rate_limiter=_RateLimiter(10),
    ),
    "get_whisperx_status": ToolSpec(
        name="get_whisperx_status",
        title="Get transcription status",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_whisperx_status"]
        ),
        input_schema=_schema({}, []),
        handler=get_whisperx_status,
        rate_limiter=_RateLimiter(60),
    ),
    "transcribe_podcast_episode": ToolSpec(
        name="transcribe_podcast_episode",
        title="Transcribe podcast episode",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["transcribe_podcast_episode"]
        ),
        input_schema=_schema({
            "episode_id": {"type": "integer"},
            "model": {"type": "string",
                       "enum": ["tiny", "base", "small", "medium", "large",
                                "large-v3-turbo"]},
            "language": {"type": "string"},
            "diarize": {"type": "boolean"},
            "consent_given": {"type": "boolean"},
        }, ["episode_id"]),
        handler=transcribe_podcast_episode,
        rate_limiter=_RateLimiter(5),
    ),
    "episode_to_corpus": ToolSpec(
        name="episode_to_corpus",
        title="Publish podcast corpus",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["episode_to_corpus"]
        ),
        input_schema=_schema({
            "episode_id": {"type": "integer"},
        }, ["episode_id"]),
        handler=episode_to_corpus,
        rate_limiter=_RateLimiter(30),
    ),
    "add_monitored_playlist": ToolSpec(
        name="add_monitored_playlist",
        title="Add monitored playlist",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["add_monitored_playlist"]
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
        title="List monitored playlists",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(DESCRIPTIONS["list_monitored_playlists"]),
        input_schema=_schema({
            "enabled_only": {"type": "boolean", "default": False},
        }, []),
        handler=list_monitored_playlists,
        rate_limiter=_RateLimiter(60),
    ),
    "remove_monitored_playlist": ToolSpec(
        name="remove_monitored_playlist",
        title="Remove monitored playlist",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(DESCRIPTIONS["remove_monitored_playlist"]),
        input_schema=_schema({
            "playlist_id": {"type": "integer"},
        }, ["playlist_id"]),
        handler=remove_monitored_playlist,
        rate_limiter=_RateLimiter(30),
    ),
    "poll_monitored_playlist": ToolSpec(
        name="poll_monitored_playlist",
        title="Poll monitored playlist",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["poll_monitored_playlist"]
        ),
        input_schema=_schema({
            "playlist_id": {"type": "integer"},
        }, ["playlist_id"]),
        handler=poll_monitored_playlist,
        rate_limiter=_RateLimiter(20),
    ),
    "list_monitored_playlist_events": ToolSpec(
        name="list_monitored_playlist_events",
        title="List playlist events",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_monitored_playlist_events"]
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
        title="Get taste memory",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_user_taste"]
        ),
        input_schema=_schema({}, []),
        handler=get_user_taste,
        rate_limiter=_RateLimiter(60),
    ),
    "get_user_memory": ToolSpec(
        name="get_user_memory",
        title="Get user memory",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_user_memory"]
        ),
        input_schema=_schema({}, []),
        handler=get_user_memory,
        rate_limiter=_RateLimiter(60),
    ),
    "update_user_taste": ToolSpec(
        name="update_user_taste",
        title="Update taste memory",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["update_user_taste"]
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
        title="Get engagement signal",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_engagement_signal"]
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
        title="Classify item facets",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["classify_facets"]
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
        title="Query item facets",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["query_by_facets"]
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
        title="Get facet taxonomy",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_facet_taxonomy"],
        input_schema=_schema({}, []),
        handler=get_facet_taxonomy,
        rate_limiter=_RateLimiter(60),
    ),
    "get_transcript_reliability": ToolSpec(
        name="get_transcript_reliability",
        title="Get transcript reliability",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_transcript_reliability"]
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
        title="Assemble workspace",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["assemble_workspace"]
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
        title="Critique against corpus",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["critique_against_corpus"]
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
        title="List workspaces",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_workspaces"]
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
        title="Get workspace",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_workspace"]
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
        title="Extract claims",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["extract_claims"]
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
        title="Record claim evidence",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["verify_claim"]
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
        title="List claims",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_claims"]
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
        title="Get claim",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_claim"],
        input_schema=_schema({
            "id": {"type": "integer"},
            "claim_id": {"type": "integer"},
        }, []),
        handler=get_claim,
        rate_limiter=_RateLimiter(60),
    ),
    "generate_script": ToolSpec(
        name="generate_script",
        title="Generate script",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["generate_script"]
        ),
        input_schema=_schema({
            "workspace_id": {"type": "string"},
            "script": {"type": "object"},
            "mode": {"type": "string", "enum": ["agent", "byo_key"]},
            "parent_script_id": {"type": "integer"},
            "hook_type_lens": {
                "type": "string",
                "enum": ["informative", "engagement_bait",
                         "disappointment_contrarian", "curiosity_gap",
                         "stakes", "success_case_study", "failure_lesson",
                         "question_open_loop", "frame_shift"],
                "description": "Optional hook lens that biases the script's "
                               "opening toward that style (generation intent)."},
        }, ["workspace_id"]),
        handler=generate_script,
        rate_limiter=_RateLimiter(30),
    ),
    "revise_script": ToolSpec(
        name="revise_script",
        title="Revise script",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["revise_script"]
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
        title="Generate and save shot list",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_shot_list"]
        ),
        input_schema=_schema({
            "script_id": {"type": "integer"},
        }, ["script_id"]),
        handler=get_shot_list,
        rate_limiter=_RateLimiter(60),
    ),
    "list_scripts": ToolSpec(
        name="list_scripts",
        title="List scripts",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_scripts"]
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
        title="Get script",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_script"],
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
        title="Write tweet or thread",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["write_tweet"]
        ),
        input_schema=_schema({
            "source_yoink_id": {"type": "string"},
            "angle": {"type": "string"},
            "target_length_chars": {"type": "integer"},
            "generate": {
                "type": "boolean",
                "description": "When true and body is absent, generate "
                               "directly with the saved Anthropic key."},
            "compute_mode": {
                "type": "string",
                "enum": ["agent", "byo_key"],
                "description": "Use byo_key to request direct generation."},
            "kind": {
                "type": "string",
                "enum": ["tweet", "thread"],
                "description": "Direct-generation output kind."},
            "output_mode": {
                "type": "string",
                "enum": ["tweet", "thread"],
                "description": "Composer output mode. thread prompts a "
                               "thread while persisting a tweet-kind piece "
                               "(the composer splits the body)."},
            "hook_type_lens": {
                "type": "string",
                "enum": ["informative", "engagement_bait",
                         "disappointment_contrarian", "curiosity_gap",
                         "stakes", "success_case_study", "failure_lesson",
                         "question_open_loop", "frame_shift"],
                "description": "Optional hook lens that biases the opening "
                               "toward that style (generation intent)."},
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
        title="Write blog",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["write_blog"]
        ),
        input_schema=_schema({
            "source_yoink_id": {"type": "string"},
            "angle": {"type": "string"},
            "target_length_words": {"type": "integer"},
            "generate": {
                "type": "boolean",
                "description": "When true and body is absent, generate "
                               "directly with the saved Anthropic key."},
            "compute_mode": {
                "type": "string",
                "enum": ["agent", "byo_key"],
                "description": "Use byo_key to request direct generation."},
            "kind": {
                "type": "string",
                "enum": ["blog"],
                "description": "Direct-generation output kind."},
            "hook_type_lens": {
                "type": "string",
                "enum": ["informative", "engagement_bait",
                         "disappointment_contrarian", "curiosity_gap",
                         "stakes", "success_case_study", "failure_lesson",
                         "question_open_loop", "frame_shift"],
                "description": "Optional hook lens that biases the opening "
                               "toward that style (generation intent)."},
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
        title="List writing pieces",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_writing_pieces"]
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
        title="Get writing piece",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_writing_piece"],
        input_schema=_schema({
            "id": {"type": "integer"},
            "piece_id": {"type": "integer"},
        }, []),
        handler=get_writing_piece,
        rate_limiter=_RateLimiter(60),
    ),
    "add_style_anchor": ToolSpec(
        name="add_style_anchor",
        title="Add style anchor",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["add_style_anchor"]
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
        title="List style anchors",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(DESCRIPTIONS["list_style_anchors"]),
        input_schema=_schema({
            "active_only": {"type": "boolean", "default": False},
        }, []),
        handler=list_style_anchors,
        rate_limiter=_RateLimiter(60),
    ),
    "remove_style_anchor": ToolSpec(
        name="remove_style_anchor",
        title="Remove style anchor",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["remove_style_anchor"],
        input_schema=_schema({
            "anchor_id": {"type": "integer"},
            "id": {"type": "integer"},
        }, []),
        handler=remove_style_anchor,
        rate_limiter=_RateLimiter(30),
    ),
    # Phase 0 shared capture parity (4 tools)
    "uoink_url": ToolSpec(
        name="uoink_url",
        title="Capture URL",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["uoink_url"]
        ),
        input_schema=_schema({
            "url": {"type": "string"},
            "interval": {"type": "integer", "minimum": 5, "maximum": 300,
                         "default": 30},
            "long_video_mode": {"type": "string", "enum": ["full", "lite"]},
        }, ["url"]),
        handler=uoink_url,
        rate_limiter=_RateLimiter(5),
    ),
    "uoink_note": ToolSpec(
        name="uoink_note",
        title="Save note",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=DESCRIPTIONS["uoink_note"],
        input_schema=_schema({
            "text": {"type": "string"},
            "title": {"type": "string"},
            "author": {"type": "string"},
        }, ["text"]),
        handler=uoink_note,
        rate_limiter=_RateLimiter(30),
    ),
    "uoink_image": ToolSpec(
        name="uoink_image",
        title="Save image",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": False, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["uoink_image"]
        ),
        input_schema=_schema({
            "image_base64": {"type": "string"},
            "mime": {"type": "string"},
            "filename": {"type": "string"},
            "caption": {"type": "string"},
            "source_url": {"type": "string"},
            "author": {"type": "string"},
        }, ["image_base64"]),
        handler=uoink_image,
        rate_limiter=_RateLimiter(10),
    ),
    "uoink_x": ToolSpec(
        name="uoink_x",
        title="Capture X post",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["uoink_x"]
        ),
        input_schema=_schema({
            "url": {"type": "string"},
        }, ["url"]),
        handler=uoink_x,
        rate_limiter=_RateLimiter(10),
    ),
    # v3.2 Universal Site Uoinking (4 tools)
    "uoink_page": ToolSpec(
        name="uoink_page",
        title="Capture web page",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["uoink_page"]
        ),
        input_schema=_schema({
            "url": {"type": "string"},
            "render_mode": {"type": "string",
                              "enum": ["js", "static"], "default": "js"},
            "include_screenshot": {"type": "boolean", "default": True},
            "follow_links_depth": {"type": "integer",
                                      "minimum": 0, "maximum": 1,
                                      "default": 0},
        }, ["url"]),
        handler=uoink_page,
        rate_limiter=_RateLimiter(15),
    ),
    "uoink_reddit_thread": ToolSpec(
        name="uoink_reddit_thread",
        title="Capture Reddit thread",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": False, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["uoink_reddit_thread"]
        ),
        input_schema=_schema({
            "url": {"type": "string",
                     "description": "reddit.com/r/<sub>/comments/... thread URL."},
            "depth_limit": {"type": "integer", "minimum": 0, "maximum": 10,
                              "default": 4,
                              "description": "How many reply levels to keep."},
            "score_threshold": {"type": "integer", "default": 2,
                                  "description": "Drop comments below this score."},
        }, ["url"]),
        handler=uoink_reddit_thread,
        rate_limiter=_RateLimiter(10),
    ),
    "list_allowed_sites": ToolSpec(
        name="list_allowed_sites",
        title="List allowed sites",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["list_allowed_sites"]
        ),
        input_schema=_schema({
            "active_only": {"type": "boolean", "default": False},
        }, []),
        handler=list_allowed_sites,
        rate_limiter=_RateLimiter(60),
    ),
    "add_allowed_site": ToolSpec(
        name="add_allowed_site",
        title="Add allowed site",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": True,
        },
        description=(
            DESCRIPTIONS["add_allowed_site"]
        ),
        input_schema=_schema({
            "url_pattern": {"type": "string"},
        }, ["url_pattern"]),
        handler=add_allowed_site,
        rate_limiter=_RateLimiter(30),
    ),
    "remove_allowed_site": ToolSpec(
        name="remove_allowed_site",
        title="Remove allowed site",
        annotations={
            "readOnlyHint": False, "destructiveHint": True,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["remove_allowed_site"]
        ),
        input_schema=_schema({
            "url_pattern": {"type": "string"},
        }, ["url_pattern"]),
        handler=remove_allowed_site,
        rate_limiter=_RateLimiter(30),
    ),
    "get_library_activity": ToolSpec(
        name="get_library_activity",
        title="Get library activity",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_library_activity"],
        input_schema=_schema({
            "interval": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Gregorian UTC timestamp YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.sssZ"},
                    "end": {"type": "string", "description": "Gregorian UTC timestamp YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.sssZ"},
                },
                "required": ["start", "end"],
                "additionalProperties": False,
                "description": "Half-open [start, end) query interval.",
            },
            "date_basis": {
                "type": "string",
                "enum": ["capture_time", "publication_time"],
                "default": "capture_time",
                "description": "Clock basis for item report.",
            },
            "detail": {
                "type": "string",
                "enum": ["creator_hints", "type_creator_hints", "shelves", "sources", "events", "evidence"],
                "description": "Optional detail collection selector.",
            },
            "metric_id": {
                "type": "string",
                "maxLength": 512,
                "description": "Stable metric ID (required for detail:evidence).",
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "maximum": 1000000,
                "description": "Pagination offset.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "Pagination limit.",
            },
            "expected_revision": {
                "type": "string",
                "description": "Summary report_revision (required for detail requests).",
            },
        }, ["interval"]),
        handler=get_library_activity,
        rate_limiter=None,
    ),
    # ---- Living Library Phase 4 bounded read tools (run AV-1) ----
    # Strictness, the 2 s deadline, the 60/minute and 2-active guard and every
    # refusal envelope live in library_resources.py (shared with stdio
    # resources and prompts); no registry rate limiter so a throttled caller
    # still receives the contract's `rate_limited` envelope.
    "search_library": ToolSpec(
        name="search_library",
        title="Search library",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["search_library"]
        ),
        input_schema=_schema({
            "mode": {"type": "string", "enum": ["auto", "keyword", "semantic", "hybrid"],
                      "default": "auto",
                      "description": "Auto uses hybrid when the local semantic index is ready, otherwise keyword."},
            "match": {"type": "string", "enum": ["forgiving", "strict"],
                      "default": "forgiving",
                      "description": "Forgiving matches useful words; strict requires every word."},
            "query": {"type": "string", "description": "Search text, at most 512 characters."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5,
                      "description": "Maximum hits, 1-20 (default 5)."},
        }, ["query"]),
        handler=lambda args: _library_resources_call("search_library", args),
    ),
    "get_library_item": ToolSpec(
        name="get_library_item",
        title="Get library item",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_library_item"]
        ),
        input_schema=_schema({
            "video_id": {"type": "string", "description": "Stable item id (exactly one selector)."},
            "slug": {"type": "string", "description": "Discovery alias (exactly one selector)."},
        }),
        handler=lambda args: _library_resources_call("get_library_item", args),
    ),
    "read_library_resource": ToolSpec(
        name="read_library_resource",
        title="Read library resource",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["read_library_resource"]
        ),
        input_schema=_schema({
            "uri": {"type": "string", "description": "A uoink://library/v1/... resource URI."},
        }, ["uri"]),
        handler=lambda args: _library_resources_call("read_library_resource", args),
    ),
    "get_playbook_input": ToolSpec(
        name="get_playbook_input",
        title="Prepare research playbook input",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["get_playbook_input"],
        input_schema=PLAYBOOK_INPUT_SCHEMA,
        handler=_research_playbooks_call,
    ),
    "discover_candidates": ToolSpec(
        name="discover_candidates", title="Discover capture candidates",
        annotations={"readOnlyHint": False, "destructiveHint": False,
                     "idempotentHint": False, "openWorldHint": True},
        description=DESCRIPTIONS["discover_candidates"],
        input_schema=DISCOVER_CANDIDATES_SCHEMA,
        handler=lambda args: _discovery_call("discover_candidates", args),
        rate_limiter=_RateLimiter(6),
    ),
    "queue_discovered": ToolSpec(
        name="queue_discovered", title="Queue discovered posts",
        annotations={"readOnlyHint": False, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": True},
        description=DESCRIPTIONS["queue_discovered"],
        input_schema=QUEUE_DISCOVERED_SCHEMA,
        handler=lambda args: _discovery_call("queue_discovered", args),
        rate_limiter=_RateLimiter(30),
    ),
    # ---- Living Library Phase 4 brief tools (run AV-2) ----
    # Brief generation belongs to the client: get_library_brief_input is a
    # read (no lease, no mutation); publish_library_brief is a LOCAL WRITE
    # under DATA_ROOT/reach/briefs (immutable artifact plus receipt). Both
    # live in library_briefs.py behind library_resources.dispatch_tool.
    "get_library_brief_input": ToolSpec(
        name="get_library_brief_input",
        title="Prepare library brief input",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["get_library_brief_input"]
        ),
        input_schema=_schema({
            "date": {"type": "string", "description": "UTC day, YYYY-MM-DD; not in the future."},
            "run_id": {"type": "string", "description": "Phase 2 run id (1-200 characters)."},
        }, ["date", "run_id"]),
        handler=lambda args: _library_resources_call("get_library_brief_input", args),
    ),
    "publish_library_brief": ToolSpec(
        name="publish_library_brief",
        title="Publish library brief",
        annotations={
            "readOnlyHint": False, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=(
            DESCRIPTIONS["publish_library_brief"]
        ),
        input_schema=_schema({
            "job_key": {"type": "string", "description": "job_key returned by get_library_brief_input."},
            "input_hash": {"type": "string", "description": "input_hash returned by get_library_brief_input."},
            "input_packet": {"type": "object",
                             "description": "The exact packet returned by get_library_brief_input."},
            "submission_key": {"type": "string",
                               "description": "Client idempotency key (1-200 characters, no whitespace)."},
            "document": {"type": "string", "description": "The brief, at most 8,192 UTF-8 bytes."},
            "citations": {
                "type": "array", "maxItems": 20, "items": {"type": "object"},
                "description": ("At most 20 citations: item_id, source_revision, card_hash, "
                                "excerpt_id, quote (1-500 code points), evidence_kind, start, end."),
            },
            "usage": {"type": ["object", "null"],
                      "description": "Client-reported usage, or null when unavailable (never zero)."},
        }, ["job_key", "input_hash", "input_packet", "submission_key", "document", "citations"]),
        handler=lambda args: _library_resources_call("publish_library_brief", args),
    ),
    # ---- Living Library Phase 6 cited export (run BC-2) ----
    # Read only: creates no evidence basis, acquisition permission or save
    # action. Strictness, the shared 2 s deadline/admission guard and every
    # refusal envelope live in library_media.py; no registry rate limiter so
    # a throttled caller still receives the contract's `rate_limited` envelope.
    "export_cited_range": ToolSpec(
        name="export_cited_range",
        title="Export cited transcript range",
        annotations={
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        },
        description=DESCRIPTIONS["export_cited_range"],
        input_schema=EXPORT_CITED_RANGE_SCHEMA,
        handler=_library_media_export,
    ),
}


def list_tools(*, structured_results: bool = True) -> list[dict[str, Any]]:
    tools = []
    for spec in TOOL_REGISTRY.values():
        item: dict[str, Any] = {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.input_schema,
        }
        if spec.annotations is not None:
            item["annotations"] = spec.annotations
        if spec.title is not None:
            item["title"] = spec.title
        if structured_results and spec.name in OUTPUT_SCHEMAS:
            item["outputSchema"] = OUTPUT_SCHEMAS[spec.name]
        tools.append(item)
    return tools


def call_tool(name: str, arguments: dict[str, Any] | None = None, *,
              origin: str = "", session_hash: str = "") -> dict[str, Any]:
    spec = TOOL_REGISTRY.get(name)
    if not spec:
        return _err("tool not found")
    if name in DISCOVERY_TOOL_NAMES:
        return _discovery_call(name, arguments, origin=origin, session_hash=session_hash)
    if name == "get_playbook_input":
        # Preserve malformed/falsy input for the strict domain validator.
        return spec.handler(arguments)
    args = arguments or {}
    if not isinstance(args, dict):
        return _err("arguments must be an object")
    try:
        if spec.rate_limiter:
            spec.rate_limiter.check()
        result = spec.handler(args)
        if name in {"get_library_activity", "publish_library_brief"}:
            import _platform
            if not _platform.library_mirror_capability()["available"]:
                result["capabilities"] = _platform.platform_capabilities()
        return result
    except RateLimitExceeded as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"tool failed: {e}")


def stdio_tool_names(toolset: str = "full") -> tuple[str, ...]:
    """Full registry, with the v3.9.1 prefix preserved; core is opt-in."""
    if len(CORE_STDIO_TOOLS) != 35 or len(set(CORE_STDIO_TOOLS)) != 35:
        raise RuntimeError("Invalid core stdio inventory")
    if not set(CORE_STDIO_TOOLS) <= TOOL_REGISTRY.keys():
        raise RuntimeError("Core stdio tool missing from registry")
    if toolset == "core":
        return CORE_STDIO_TOOLS
    return CORE_STDIO_TOOLS + tuple(name for name in TOOL_REGISTRY if name not in CORE_STDIO_TOOLS)


_SCHEMA_COMBINATORS = ("oneOf", "anyOf", "allOf")


def client_input_schema(schema: dict, tool_name: str | None = None) -> dict:
    """The input schema both stdio and HTTP advertise to MCP clients.

    The Anthropic API rejects tool input schemas with oneOf/anyOf/allOf at the
    top level, and Claude Code then shows none of the server's tools. Three
    frozen registry schemas (claim_library_work, apply_reshelving,
    set_source_consent) use a top-level oneOf. Advertise them as one object
    whose properties merge the variants. The handlers still validate every
    call against the exact registry schema, so nothing looser is accepted.
    """
    # Documentation is a copy of the client view. Frozen registry schemas
    # remain byte-for-byte inputs to the validators and contract snapshots.
    if tool_name is not None:
        return document_input_schema(client_input_schema(schema), tool_name)
    if schema.get("type") == "object" and not any(k in schema for k in _SCHEMA_COMBINATORS):
        return schema
    flat = {k: v for k, v in schema.items() if k not in _SCHEMA_COMBINATORS + ("not",)}
    flat["type"] = "object"
    properties = dict(schema.get("properties", {}))
    variants: dict[str, list] = {}
    required = set(schema.get("required", []))
    branch_required = None
    branches = []
    for key in _SCHEMA_COMBINATORS:
        for branch in schema.get(key, []):
            branches.append(branch)
            for name, sub in branch.get("properties", {}).items():
                variants.setdefault(name, [])
                if sub not in variants[name]:
                    variants[name].append(sub)
            names = set(branch.get("required", []))
            if key == "allOf":
                required |= names
            else:
                branch_required = names if branch_required is None else branch_required & names
    for name, subs in variants.items():
        if name not in properties:
            properties[name] = subs[0] if len(subs) == 1 else {"anyOf": subs}
    flat["properties"] = properties
    required |= branch_required or set()
    ordered = [n for n in schema.get("required", []) if n in required]
    ordered += sorted(required - set(ordered))
    if ordered:
        flat["required"] = ordered
    else:
        flat.pop("required", None)
    if ("additionalProperties" not in schema and branches
            and all(b.get("additionalProperties") is False for b in branches)):
        flat["additionalProperties"] = False
    return flat
