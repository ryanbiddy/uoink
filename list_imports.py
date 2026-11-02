"""Import a list: queue every video from a list source for normal capture.

Supported sources (one pasted link each):

- HackerTube (https://hackertube.org, by Andrej Karpathy): a playlist
  (/p/<slug>), a topic category (/c/<id>), a topic area (/a/<id>), one video
  (/watch/<id>), or the whole collection best first ("top N by quality":
  the home page, /browse, or just the word "hackertube"). Fetched from the
  site's public JSON API at import time; nothing is bundled. The dataset is
  ODC-By 1.0, so every imported item keeps the credit line below.
- A Hacker News thread (news.ycombinator.com/item?id=N), read through the
  Algolia HN API, which returns the whole comment tree in one request.
- A Reddit thread, read through the same public .json Uoink's Reddit capture
  uses.
- A YouTube playlist (youtube.com/playlist?list=...), listed with yt-dlp's
  flat playlist mode, so a 2,000-episode playlist can be worked through 50 at
  a time with an offset.

This module owns parsing, previewing and the small import registry. The
capture itself goes through the helper's existing download queue
(pending_yoinks + the retry worker), which takes one video per pass, so a
50-video batch is throttled the same way every other queued capture is.

The registry (DATA_ROOT/list-imports.json) remembers where each queued video
came from: the source label, the list title, HackerTube's "why HN likes it"
note and the credit line. When the capture lands in the library the helper
calls ``apply_on_index`` to add a source tag, and the Library and For You read
the note back from here. No database migration is needed.

Parsers are pure functions over already-fetched JSON so tests run against
saved fixtures with no network.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, quote, urlencode, urlparse

log = logging.getLogger("uoink.list_imports")

SOURCE_HACKERTUBE = "hackertube"
SOURCE_HN = "hn_thread"
SOURCE_REDDIT = "reddit_thread"
SOURCE_PLAYLIST = "youtube_playlist"
SOURCES = (SOURCE_HACKERTUBE, SOURCE_HN, SOURCE_REDDIT, SOURCE_PLAYLIST)

SOURCE_LABELS = {
    SOURCE_HACKERTUBE: "HackerTube",
    SOURCE_HN: "HN thread",
    SOURCE_REDDIT: "Reddit thread",
    SOURCE_PLAYLIST: "YouTube playlist",
}
# Library tags (index.add_tags lower-cases them).
SOURCE_TAGS = {
    SOURCE_HACKERTUBE: "hackertube",
    SOURCE_HN: "hn thread",
    SOURCE_REDDIT: "reddit thread",
    SOURCE_PLAYLIST: "youtube playlist",
}
TAG_SOURCE = "list_import"

HACKERTUBE_ORIGIN = "https://hackertube.org"
HACKERTUBE_CREDIT = (
    "From HackerTube (hackertube.org), ODC-By 1.0. Built on the "
    "open-index/hacker-news dataset; Hacker News data by Y Combinator."
)
HN_ALGOLIA_ITEM = "https://hn.algolia.com/api/v1/items/{id}"

DEFAULT_LIMIT = 50
MAX_LIMIT = 50
MAX_OFFSET = 100_000
HACKERTUBE_PAGE_MAX = 100        # /api/list returns at most 100 rows
NOTE_MAX_CHARS = 400
FETCH_TIMEOUT_SEC = 20
FETCH_MAX_BYTES = 24 * 1024 * 1024
REGISTRY_ITEM_CAP = 5000
USER_AGENT = "uoink/1.0 (local corpus tool; +https://uoink.app)"

_YT_ID = r"[A-Za-z0-9_-]{11}"
_YT_ID_RE = re.compile(rf"^{_YT_ID}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")
_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
# YouTube video links in free text (HN comment HTML, Reddit Markdown).
_YT_LINK_RE = re.compile(
    r"(?<![A-Za-z0-9.-])(?:https?://)?(?:www\.|m\.|music\.)?"
    r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^\s\"'<>]*?&)?v=|shorts/|embed/|live/|v/)"
    r"|youtu\.be/)"
    rf"({_YT_ID})(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HT_QUERY_KEYS = ("sort", "dur", "gems", "type", "level", "life", "era")
_UNAVAILABLE_TITLES = {"[private video]", "[deleted video]"}


class ImportListError(ValueError):
    """A user-facing reason the pasted source could not be read."""

    def __init__(self, message: str, code: str = "unreadable"):
        super().__init__(message)
        self.code = code


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def clamp_limit(value: Any, default: int = DEFAULT_LIMIT) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(1, min(MAX_LIMIT, n))


def clamp_offset(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(MAX_OFFSET, n))


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _clean(value: Any, cap: int = NOTE_MAX_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= cap else text[: cap - 1].rstrip() + "…"


def _strip_html(text: str) -> str:
    text = re.sub(r"<p>", "\n", text or "", flags=re.I)
    return html.unescape(_HTML_TAG_RE.sub("", text))


# ---------------------------------------------------------------------------
# Source classification
# ---------------------------------------------------------------------------

def classify(text: str) -> dict:
    """Map pasted text to a source spec, or raise ImportListError.

    Returns {"kind", "url", ...kind specific fields}.
    """
    raw = (text or "").strip()
    if not raw:
        raise ImportListError("Paste a HackerTube, Hacker News, Reddit or YouTube playlist link.",
                              "empty")
    if raw.lower() in ("hackertube", "hackertube.org", "hackertube:top"):
        return {"kind": SOURCE_HACKERTUBE, "mode": "top", "params": {},
                "url": HACKERTUBE_ORIGIN + "/"}
    try:
        u = urlparse(raw if "://" in raw else "https://" + raw)
    except ValueError:
        raise ImportListError("That doesn't look like a link.", "invalid_url")
    if u.scheme not in ("http", "https"):
        raise ImportListError("That doesn't look like a link.", "invalid_url")
    host = (u.hostname or "").lower()
    path = u.path or "/"
    qs = parse_qs(u.query)

    if host in ("hackertube.org", "www.hackertube.org"):
        parts = [p for p in path.split("/") if p]
        if len(parts) == 2 and parts[0] in ("p", "c", "a", "watch"):
            ident = parts[1]
            if parts[0] == "watch":
                if not _YT_ID_RE.match(ident):
                    raise ImportListError("That HackerTube video link has no valid video id.",
                                          "invalid_url")
                return {"kind": SOURCE_HACKERTUBE, "mode": "video", "id": ident,
                        "url": f"{HACKERTUBE_ORIGIN}/watch/{ident}"}
            if not _SLUG_RE.match(ident):
                raise ImportListError("That HackerTube link has an id Uoink can't read.",
                                      "invalid_url")
            mode = {"p": "playlist", "c": "category", "a": "area"}[parts[0]]
            return {"kind": SOURCE_HACKERTUBE, "mode": mode, "id": ident,
                    "url": f"{HACKERTUBE_ORIGIN}/{parts[0]}/{ident}"}
        if not parts or parts == ["browse"]:
            params = {}
            for key in _HT_QUERY_KEYS:
                value = (qs.get(key) or [""])[0]
                if value and re.match(r"^[a-z0-9_-]{1,24}$", value):
                    params[key] = value
            suffix = ("?" + urlencode(params)) if params else ""
            return {"kind": SOURCE_HACKERTUBE, "mode": "top", "params": params,
                    "url": f"{HACKERTUBE_ORIGIN}/{'browse' if parts else ''}{suffix}"}
        raise ImportListError(
            "Uoink can import a HackerTube playlist, category, area, video or the "
            "whole collection. Paste one of those pages.", "unsupported")

    if host in ("news.ycombinator.com", "www.news.ycombinator.com"):
        item = (qs.get("id") or [""])[0]
        if path.rstrip("/") == "/item" and item.isdigit():
            return {"kind": SOURCE_HN, "id": int(item),
                    "url": f"https://news.ycombinator.com/item?id={int(item)}"}
        raise ImportListError("Paste a Hacker News thread link (news.ycombinator.com/item?id=...).",
                              "unsupported")

    if re.match(r"^(?:www\.|old\.|new\.|np\.)?reddit\.com$", host):
        if re.match(r"^/r/[^/]+/comments/[^/]+", path):
            base = re.sub(r"\.json$", "", path.rstrip("/"))
            return {"kind": SOURCE_REDDIT, "url": "https://www.reddit.com" + base + "/"}
        raise ImportListError("Paste a Reddit thread link (reddit.com/r/.../comments/...).",
                              "unsupported")

    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        list_id = (qs.get("list") or [""])[0]
        if list_id and _PLAYLIST_ID_RE.match(list_id) and path in ("/", "/playlist", "/watch"):
            return {"kind": SOURCE_PLAYLIST, "id": list_id,
                    "url": f"https://www.youtube.com/playlist?list={list_id}"}
        raise ImportListError(
            "That YouTube link is a single video. Paste it in Uoink anything, or paste a "
            "playlist link (youtube.com/playlist?list=...) here.", "unsupported")

    raise ImportListError(
        "Uoink can import HackerTube lists, Hacker News threads, Reddit threads and "
        "YouTube playlists.", "unsupported")


# ---------------------------------------------------------------------------
# Parsers (pure)
# ---------------------------------------------------------------------------

def extract_youtube_ids(text: str) -> list[str]:
    """YouTube video ids in order of first appearance. Handles HTML entity
    escaping (HN encodes '/' as &#x2F;) and &amp; in query strings."""
    clean = html.unescape(html.unescape(text or ""))
    seen: list[str] = []
    for m in _YT_LINK_RE.finditer(clean):
        vid = m.group(1)
        if vid not in seen:
            seen.append(vid)
    return seen


def _item(video_id: str, *, title: str = "", channel: str = "", note: str = "",
          duration: Any = None, quality: Any = None) -> dict:
    try:
        duration_s = int(float(duration)) if duration is not None else None
    except (TypeError, ValueError):
        duration_s = None
    try:
        q = float(quality) if quality is not None else None
    except (TypeError, ValueError):
        q = None
    return {
        "video_id": video_id,
        "url": watch_url(video_id),
        "title": _clean(title, 300),
        "channel": _clean(channel, 200),
        "note": _clean(note),
        "duration_seconds": duration_s,
        "quality_score": q,
    }


def parse_hackertube_videos(rows: Any) -> list[dict]:
    """HackerTube /api/list rows or /api/playlist videos -> items."""
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        vid = row.get("vid")
        if not isinstance(vid, str) or not _YT_ID_RE.match(vid) or vid in seen:
            continue
        seen.add(vid)
        out.append(_item(
            vid, title=row.get("title") or "", channel=row.get("channel") or "",
            note=row.get("why_hn") or row.get("note") or "",
            duration=row.get("duration_s"), quality=row.get("score")))
    return out


def parse_hackertube_playlist(payload: Any) -> tuple[str, list[dict]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("videos"), list):
        raise ImportListError("HackerTube didn't return that playlist.", "not_found")
    # A playlist row carries both why_hn and the curator's per-video note.
    # Keep HN's why first; it is the dataset field this import credits.
    return (str(payload.get("title") or payload.get("slug") or "HackerTube playlist"),
            parse_hackertube_videos(payload["videos"]))


def hackertube_name(browse: Any, mode: str, ident: str) -> str | None:
    """The display name of a category or area from /api/browse."""
    for area in browse if isinstance(browse, list) else []:
        if not isinstance(area, dict):
            continue
        if mode == "area" and area.get("id") == ident:
            return area.get("name")
        for cat in area.get("categories") or []:
            if mode == "category" and isinstance(cat, dict) and cat.get("id") == ident:
                return cat.get("name")
    return None


def parse_hn_thread(payload: Any) -> tuple[str, list[dict]]:
    """Algolia HN item tree -> (thread title, items in reading order)."""
    if not isinstance(payload, dict) or "id" not in payload:
        raise ImportListError("Hacker News didn't return that thread.", "not_found")
    title = str(payload.get("title") or f"HN item {payload.get('id')}")
    out: list[dict] = []
    seen: set[str] = set()

    def add(ids: Iterable[str], note: str) -> None:
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                out.append(_item(vid, note=note))

    add(extract_youtube_ids(payload.get("url") or ""),
        f"The link of the Hacker News thread “{_clean(title, 160)}”.")
    stack = [payload]
    while stack:
        node = stack.pop()
        text = node.get("text") or ""
        if node is not payload or text:
            ids = extract_youtube_ids(text)
            if ids:
                excerpt = _clean(_strip_html(text), 240)
                who = node.get("author") or "someone"
                add(ids, f"Shared by {who} on Hacker News: “{excerpt}”")
        children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        stack.extend(reversed(children))
    return title, out


def parse_reddit_thread(payload: Any) -> tuple[str, list[dict]]:
    """Reddit thread .json ([post listing, comment listing]) -> items."""
    if not isinstance(payload, list) or len(payload) < 2:
        raise ImportListError("Reddit didn't return that thread.", "not_found")
    try:
        post = payload[0]["data"]["children"][0]["data"]
    except (KeyError, IndexError, TypeError):
        raise ImportListError("Reddit didn't return that thread.", "not_found")
    title = str(post.get("title") or "Reddit thread")
    out: list[dict] = []
    seen: set[str] = set()

    def add(ids: Iterable[str], note: str) -> None:
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                out.append(_item(vid, note=note))

    sub = post.get("subreddit")
    where = f"r/{sub}" if sub else "Reddit"
    add(extract_youtube_ids(" ".join(str(post.get(k) or "") for k in
                                     ("url_overridden_by_dest", "url", "selftext"))),
        f"From the {where} post “{_clean(title, 160)}”.")

    def walk(children: Any) -> None:
        for child in children if isinstance(children, list) else []:
            if not isinstance(child, dict) or child.get("kind") != "t1":
                continue
            data = child.get("data") or {}
            body = str(data.get("body") or "")
            if body and body not in ("[deleted]", "[removed]"):
                ids = extract_youtube_ids(body)
                if ids:
                    who = data.get("author") or "someone"
                    add(ids, f"Shared by u/{who} in {where}: “{_clean(body, 240)}”")
            replies = data.get("replies")
            if isinstance(replies, dict):
                walk((replies.get("data") or {}).get("children"))

    try:
        walk(payload[1]["data"]["children"])
    except (KeyError, TypeError):
        pass
    return title, out


def parse_ytdlp_flat_playlist(payload: Any) -> tuple[str, list[dict], int | None]:
    """yt-dlp --flat-playlist --dump-single-json -> (title, items, total)."""
    if not isinstance(payload, dict):
        raise ImportListError("yt-dlp couldn't list that playlist.", "not_found")
    out: list[dict] = []
    seen: set[str] = set()
    for e in payload.get("entries") or []:
        if not isinstance(e, dict):
            continue
        vid = e.get("id")
        if not isinstance(vid, str) or not _YT_ID_RE.match(vid) or vid in seen:
            continue
        title = str(e.get("title") or "")
        if title.strip().lower() in _UNAVAILABLE_TITLES:
            continue
        seen.add(vid)
        out.append(_item(vid, title=title,
                         channel=e.get("channel") or e.get("uploader") or "",
                         duration=e.get("duration")))
    total = payload.get("playlist_count")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    return str(payload.get("title") or "YouTube playlist"), out, total


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def http_get_json(url: str, *, timeout: int = FETCH_TIMEOUT_SEC) -> Any:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
            raw = resp.read(FETCH_MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ImportListError("That list wasn't found (404).", "not_found")
        if e.code == 429:
            raise ImportListError("The site is rate-limiting. Wait a minute and try again.",
                                  "rate_limited")
        raise ImportListError(f"The site answered HTTP {e.code}.", "fetch_failed")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ImportListError(f"Couldn't reach the site: {reason}", "fetch_failed")
    if len(raw) > FETCH_MAX_BYTES:
        raise ImportListError("That list is too large to read.", "too_large")
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        raise ImportListError("The site didn't return JSON.", "fetch_failed")


def _slice(items: list[dict], offset: int, limit: int) -> list[dict]:
    return items[offset: offset + limit]


def fetch_source(spec: dict, *, offset: int, limit: int,
                 fetch_json: Callable[[str], Any] | None = None,
                 reddit_fetch: Callable[[str], Any] | None = None,
                 ytdlp_playlist: Callable[[str, int, int], Any] | None = None) -> dict:
    """Fetch one batch: {title, items, total, credit}. ``offset``/``limit``
    select the window; ``total`` is the full list size when known."""
    fetch_json = fetch_json or http_get_json
    kind = spec["kind"]
    if kind == SOURCE_HACKERTUBE:
        mode = spec["mode"]
        if mode == "playlist":
            title, items = parse_hackertube_playlist(fetch_json(
                f"{HACKERTUBE_ORIGIN}/api/playlist?slug={quote(spec['id'])}"))
            return {"title": title, "items": _slice(items, offset, limit),
                    "total": len(items), "credit": HACKERTUBE_CREDIT}
        if mode == "video":
            payload = fetch_json(f"{HACKERTUBE_ORIGIN}/api/video?vid={quote(spec['id'])}")
            row = payload.get("video") if isinstance(payload, dict) else None
            items = parse_hackertube_videos([row] if row else [])
            if not items:
                raise ImportListError("HackerTube doesn't list that video.", "not_found")
            return {"title": items[0]["title"] or "HackerTube video",
                    "items": _slice(items, offset, limit), "total": 1,
                    "credit": HACKERTUBE_CREDIT}
        params: dict[str, Any] = dict(spec.get("params") or {})
        title = "HackerTube, best first"
        total = None
        if mode in ("category", "area"):
            params["cat" if mode == "category" else "area"] = spec["id"]
            try:
                browse = fetch_json(f"{HACKERTUBE_ORIGIN}/api/browse")
            except ImportListError:
                browse = None
            name = hackertube_name(browse, mode, spec["id"])
            title = f"HackerTube: {name or spec['id']}"
            for area in browse if isinstance(browse, list) else []:
                if mode == "area" and area.get("id") == spec["id"]:
                    total = area.get("count")
                for cat in area.get("categories") or []:
                    if mode == "category" and cat.get("id") == spec["id"]:
                        total = cat.get("count")
        rows = fetch_json(f"{HACKERTUBE_ORIGIN}/api/list?" + urlencode(
            {**params, "offset": offset, "n": min(limit, HACKERTUBE_PAGE_MAX)}))
        items = parse_hackertube_videos(rows)[:limit]
        if total is None and len(items) < limit:
            total = offset + len(items)
        return {"title": title, "items": items,
                "total": int(total) if isinstance(total, (int, float)) else None,
                "credit": HACKERTUBE_CREDIT}
    if kind == SOURCE_HN:
        title, items = parse_hn_thread(fetch_json(HN_ALGOLIA_ITEM.format(id=spec["id"])))
        return {"title": title, "items": _slice(items, offset, limit),
                "total": len(items), "credit": None}
    if kind == SOURCE_REDDIT:
        if reddit_fetch is None:
            import reddit_extractor  # local: keeps this module importable alone
            reddit_fetch = reddit_extractor.fetch_thread_json
        try:
            payload = reddit_fetch(spec["url"])
        except ImportListError:
            raise
        except ValueError as e:
            raise ImportListError(str(e), "fetch_failed")
        title, items = parse_reddit_thread(payload)
        return {"title": title, "items": _slice(items, offset, limit),
                "total": len(items), "credit": None}
    if kind == SOURCE_PLAYLIST:
        if ytdlp_playlist is None:
            raise ImportListError("YouTube playlists need the local media tools.", "unavailable")
        payload = ytdlp_playlist(spec["url"], offset + 1, offset + limit)
        title, items, total = parse_ytdlp_flat_playlist(payload)
        return {"title": title, "items": items[:limit], "total": total, "credit": None}
    raise ImportListError("Unsupported list source.", "unsupported")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def build_preview(spec: dict, batch: dict, *, offset: int, limit: int,
                  in_library: Callable[[str], bool]) -> dict:
    items = []
    already = 0
    for it in batch["items"]:
        have = False
        try:
            have = bool(in_library(it["video_id"]))
        except Exception:
            have = False
        already += int(have)
        items.append({**it, "in_library": have})
    found = len(items)
    total = batch.get("total")
    end = offset + found
    has_more = (total is not None and end < total) or (total is None and found >= limit)
    kind = spec["kind"]
    new_count = found - already
    return {
        "ok": True,
        "source": {
            "kind": kind,
            "label": SOURCE_LABELS[kind],
            "title": batch.get("title") or SOURCE_LABELS[kind],
            "url": spec["url"],
            "credit": batch.get("credit"),
        },
        "offset": offset,
        "limit": limit,
        "total": total,
        "found": found,
        "already": already,
        "new": new_count,
        "has_more": bool(has_more and found > 0),
        "next_offset": end if (has_more and found > 0) else None,
        "message": preview_message(found, already, total=total, offset=offset),
        "videos": items,
    }


def preview_message(found: int, already: int, *, total: int | None = None,
                    offset: int = 0) -> str:
    if found == 0:
        return "Found no videos in this list." if offset == 0 else "No more videos in this list."
    noun = "video" if found == 1 else "videos"
    text = f"Found {found} {noun}"
    if total is not None and (total > found or offset):
        text += f" ({offset + 1}-{offset + found} of {total})"
    if already:
        text += f", {already} already in your library"
    return text + "."


# ---------------------------------------------------------------------------
# Registry (DATA_ROOT/list-imports.json)
# ---------------------------------------------------------------------------

_registry_lock = threading.Lock()
_cache: dict[str, Any] = {"path": None, "mtime": None, "data": None}


def registry_path(data_root: Path) -> Path:
    return Path(data_root) / "list-imports.json"


def _empty() -> dict:
    return {"version": 1, "items": {}, "imports": []}


def load_registry(data_root: Path) -> dict:
    path = registry_path(data_root)
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return _empty()
    if _cache["path"] == str(path) and _cache["mtime"] == mtime and _cache["data"] is not None:
        return _cache["data"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("list import registry unreadable; starting fresh view")
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        return _empty()
    data.setdefault("imports", [])
    _cache.update(path=str(path), mtime=mtime, data=data)
    return data


def _save_registry(data_root: Path, data: dict) -> None:
    path = registry_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    items = data.get("items") or {}
    if len(items) > REGISTRY_ITEM_CAP:
        keep = sorted(items.items(), key=lambda kv: kv[1].get("imported_at") or "",
                      reverse=True)[:REGISTRY_ITEM_CAP]
        data["items"] = dict(keep)
    data["imports"] = (data.get("imports") or [])[-200:]
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    _cache.update(path=None, mtime=None, data=None)


def record_import(data_root: Path, preview: dict, queued: list[dict]) -> dict:
    """Remember each queued video's origin. ``queued`` rows carry
    {video_id, title, channel, note, quality_score, pending_id}."""
    src = preview["source"]
    now = _now_iso()
    import_id = "imp_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    with _registry_lock:
        data = load_registry(data_root)
        data = json.loads(json.dumps(data))  # never mutate the cached copy
        for row in queued:
            prev = data["items"].get(row["video_id"]) or {}
            data["items"][row["video_id"]] = {
                "source": src["kind"],
                "label": src["label"],
                "tag": SOURCE_TAGS[src["kind"]],
                "list_title": src.get("title"),
                "list_url": src.get("url"),
                "note": row.get("note") or prev.get("note") or "",
                "credit": src.get("credit"),
                "title": row.get("title") or "",
                "channel": row.get("channel") or "",
                "quality_score": row.get("quality_score"),
                "pending_id": row.get("pending_id"),
                "import_id": import_id,
                "imported_at": now,
                "applied": bool(prev.get("applied")),
            }
        data["imports"].append({
            "id": import_id, "source": src["kind"], "title": src.get("title"),
            "url": src.get("url"), "offset": preview.get("offset"),
            "queued": len(queued), "at": now,
        })
        _save_registry(data_root, data)
    return {"import_id": import_id, "imported_at": now}


def lookup(data_root: Path, video_id: str) -> dict | None:
    if not video_id:
        return None
    item = load_registry(data_root)["items"].get(video_id)
    return dict(item) if isinstance(item, dict) else None


def public_origin(item: dict | None) -> dict | None:
    """The fields the Library, For You and MCP show for an imported item."""
    if not item:
        return None
    return {
        "source": item.get("source"),
        "label": item.get("label"),
        "list_title": item.get("list_title"),
        "list_url": item.get("list_url"),
        "note": item.get("note") or "",
        "credit": item.get("credit"),
    }


def imported_video_ids(data_root: Path) -> set[str]:
    return set(load_registry(data_root)["items"].keys())


def apply_on_index(idx, data_root: Path, video_id: str) -> bool:
    """Called after a capture is indexed: tag it with its list source once."""
    item = lookup(data_root, video_id)
    if not item or item.get("applied"):
        return False
    tags = [item.get("tag") or SOURCE_TAGS.get(item.get("source"), "imported")]
    idx.add_tags(video_id, tags, source=TAG_SOURCE)
    with _registry_lock:
        data = json.loads(json.dumps(load_registry(data_root)))
        if video_id in data["items"]:
            data["items"][video_id]["applied"] = True
            _save_registry(data_root, data)
    return True
