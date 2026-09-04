"""Source provenance repair and write-time classification."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


_KIND_ALIASES = {
    "video": "video",
    "podcast": "episode",
    "episode": "episode",
    "x_post": "x_thread",
    "x_thread": "x_thread",
    "x_article": "x_article",
    "page": "page",
    "reddit": "reddit_thread",
    "reddit_thread": "reddit_thread",
    "note": "note",
    "image": "image",
    "short_video": "short_video",
}

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_X_HOSTS = {
    "x.com", "www.x.com", "mobile.x.com",
    "twitter.com", "www.twitter.com", "mobile.twitter.com",
}
_REDDIT_HOSTS = {
    "reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com",
}
_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com"}
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _canonical_kind(value) -> str | None:
    kind = str(value or "").strip().lower()
    return _KIND_ALIASES.get(kind)


def _sidecar_data(path) -> dict:
    if not path:
        return {}
    try:
        sidecar_path = Path(path)
        if not sidecar_path.is_file():
            return {}
        return _as_dict(sidecar_path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _source_url(metadata: dict, sidecar: dict) -> str:
    for source in (metadata, sidecar):
        for key in ("url", "source_url", "webpage_url", "original_url"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def derive_source_type(*, platform=None, metadata_json=None,
                       sidecar_path=None, sidecar=None) -> str:
    """Derive one canonical source type from stored provenance clues.

    Explicit sidecar/metadata kinds win. Platform and URL cover normal legacy
    rows. The final ``video`` fallback matches Uoink's pre-platform corpus,
    which consisted only of YouTube captures.
    """
    metadata = _as_dict(metadata_json)
    sidecar_data = _as_dict(sidecar) or _sidecar_data(sidecar_path)

    for source in (sidecar_data, metadata):
        for key in ("source_type", "kind", "type"):
            kind = _canonical_kind(source.get(key))
            if kind:
                return kind

    source_url = _source_url(metadata, sidecar_data)
    try:
        parsed = urlparse(source_url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
    except ValueError:
        host = ""
        path = ""

    platform_name = str(
        platform or metadata.get("platform") or sidecar_data.get("platform") or ""
    ).strip().lower()
    if platform_name == "twitter":
        platform_name = "x"
    elif platform_name == "generic":
        platform_name = "web"

    if platform_name == "note":
        return "note"
    if platform_name == "image":
        return "image"
    if platform_name == "podcast":
        return "episode"
    if platform_name in {"tiktok", "instagram"}:
        return "short_video"
    if platform_name == "x":
        return "x_article" if "/i/article/" in path else "x_thread"
    if platform_name == "reddit":
        return "reddit_thread"
    if platform_name == "youtube":
        return "short_video" if path.startswith("/shorts/") else "video"
    if platform_name == "web":
        return "page"

    if host in _YOUTUBE_HOSTS:
        return "short_video" if path.startswith("/shorts/") else "video"
    if host in _X_HOSTS:
        return "x_article" if "/i/article/" in path else "x_thread"
    if host in _REDDIT_HOSTS:
        return "reddit_thread"
    if host in _TIKTOK_HOSTS or host in _INSTAGRAM_HOSTS:
        return "short_video"
    if host:
        return "page"
    return "video"


def backfill_source_types(idx, *, dry_run: bool = False) -> dict:
    """Fill missing source types idempotently and return measured counts."""
    columns = {
        row[1] for row in idx._conn.execute("PRAGMA table_info(yoinks)").fetchall()
    }
    if "source_type" not in columns:
        return {
            "before_null": 0,
            "after_null": 0,
            "updated": 0,
            "dry_run": dry_run,
            "by_source_type": {},
        }

    with idx._lock:
        rows = idx._conn.execute(
            "SELECT video_id, platform, metadata_json, sidecar_path "
            "FROM yoinks WHERE source_type IS NULL OR trim(source_type)=''"
        ).fetchall()
    updates = []
    counts = Counter()
    for raw in rows:
        row = dict(raw)
        source_type = derive_source_type(
            platform=row.get("platform"),
            metadata_json=row.get("metadata_json"),
            sidecar_path=row.get("sidecar_path"),
        )
        updates.append((source_type, row["video_id"]))
        counts[source_type] += 1

    if updates and not dry_run:
        with idx.write_transaction() as conn:
            conn.executemany(
                "UPDATE yoinks SET source_type=? "
                "WHERE video_id=? AND (source_type IS NULL OR trim(source_type)='')",
                updates,
            )

    after_null = len(rows) if dry_run else 0
    if not dry_run:
        with idx._lock:
            after_null = int(idx._conn.execute(
                "SELECT COUNT(*) FROM yoinks "
                "WHERE source_type IS NULL OR trim(source_type)=''"
            ).fetchone()[0])
    return {
        "before_null": len(rows),
        "after_null": after_null,
        "updated": len(updates) if not dry_run else 0,
        "would_update": len(updates),
        "dry_run": dry_run,
        "by_source_type": dict(sorted(counts.items())),
    }
