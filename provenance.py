"""Source provenance repair and write-time classification."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
import unicodedata

# One title limit for every source (notes, images, YouTube, podcasts, pages,
# X, Reddit, imports). Enforced at the single store boundary
# (index.upsert_yoink) and by the note/image builders.
MAX_TITLE_CHARS = 300
_ZWJ = "‍"


def _is_continuation(ch: str) -> bool:
    """True when ch must stay attached to the character before it."""
    cp = ord(ch)
    return (
        ch == _ZWJ
        or unicodedata.category(ch) in ("Mn", "Mc", "Me")
        or 0xFE00 <= cp <= 0xFE0F      # variation selectors
        or 0x1F3FB <= cp <= 0x1F3FF    # emoji skin tones
        or 0xE0020 <= cp <= 0xE007F    # emoji tag sequences
        or 0xDC00 <= cp <= 0xDFFF      # lone low surrogate
    )


def clamp_title(title, limit: int = MAX_TITLE_CHARS):
    """Cap a title at `limit` characters, ending with an ellipsis.

    Titles within the limit come back unchanged. Longer ones are cut at a
    grapheme-safe point (never inside a surrogate pair, a ZWJ emoji sequence,
    a combining-mark cluster or a flag pair), trailing whitespace is trimmed
    and one "…" is appended, so the result is never longer than `limit`.
    Non-strings pass through untouched."""
    if not isinstance(title, str) or len(title) <= limit:
        return title
    cut = max(limit - 1, 0)
    start = cut
    while cut > 0 and (
        _is_continuation(title[cut])
        or title[cut - 1] == _ZWJ
        or 0xD800 <= ord(title[cut - 1]) <= 0xDBFF
    ):
        cut -= 1
    # Regional indicators pair up into flags: don't split a pair.
    run = 0
    i = cut
    while i > 0 and 0x1F1E6 <= ord(title[i - 1]) <= 0x1F1FF:
        run += 1
        i -= 1
    if run % 2 == 1 and cut < len(title) and 0x1F1E6 <= ord(title[cut]) <= 0x1F1FF:
        cut -= 1
    if cut <= 0:
        cut = start  # one unbroken cluster longer than the limit: hard cut
    return title[:cut].rstrip() + "…"


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

    Explicit metadata kinds win, followed by sidecar kinds. Platform and URL cover legacy
    rows. The final ``video`` fallback matches Uoink's pre-platform corpus,
    which consisted only of YouTube captures.
    """
    metadata = _as_dict(metadata_json)
    sidecar_data = _as_dict(sidecar) or _sidecar_data(sidecar_path)

    for source in (metadata, sidecar_data):
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
