"""v3.1 podcast support -- RSS feed polling + episode tracking.

Per ROADMAP + PROMPT-V3.1: branding decision -- expand Uoink to cover
podcasts (one tool, one corpus). This module ships the RSS feed
registry + the polling pipeline that materialises new episodes. The
audio download + Whisper transcription layers land in subsequent PRs
in CC's queue (track B step 2 + step 3).

Compute (locked policy: model-agnostic + local-first):
- RSS XML parsing uses Python's stdlib xml.etree.ElementTree -- no
  new vendored dependency. Sticks to RSS 2.0 + Atom 1.0 element names
  (the two formats that cover 99%+ of feeds in the wild).
- Polling is a plain HTTP GET with conditional ETag / If-Modified-Since
  headers when the feed previously returned them, so a daily news
  podcast doesn't re-download an unchanged feed body on every poll.

The polling worker lives in server.py (consumes _maybe_poll_feeds);
this module owns the parse + persistence layer + helper functions.
Transport (HTTP + MCP) is owned by server.py + uoink_mcp_tools.py."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("uoink.podcasts")

# Bounded enum for the episode status flow. The dashboard renders
# 'new' as an unread chip; 'queued' once the user opts in to download
# (next PR); 'downloaded' + 'transcribed' as the audio + transcript
# pipeline progresses; 'ignored' if the user dismisses.
EPISODE_STATUS_NEW = "new"
EPISODE_STATUS_QUEUED = "queued"
EPISODE_STATUS_DOWNLOADED = "downloaded"
EPISODE_STATUS_TRANSCRIBED = "transcribed"
EPISODE_STATUS_IGNORED = "ignored"
_EPISODE_STATUSES = (
    EPISODE_STATUS_NEW, EPISODE_STATUS_QUEUED, EPISODE_STATUS_DOWNLOADED,
    EPISODE_STATUS_TRANSCRIBED, EPISODE_STATUS_IGNORED,
)

# Cap how many episodes we materialise per poll so a freshly-added feed
# with 800 back-episodes doesn't flood the dashboard. The user opts
# in via "load more" (a follow-up endpoint not in this PR).
_EPISODES_PER_POLL_CAP = 50

# Polite HTTP timeout for feed GETs. Most podcasts host on Libsyn /
# Megaphone / direct hosting; 8 seconds is generous for an XML body.
_FEED_FETCH_TIMEOUT_SEC = 8.0

# User-Agent so podcast hosts can see who's polling. Important for
# politeness + rate-limit tracking.
_FEED_USER_AGENT = "Uoink/3.1 (+https://uoink.video)"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _validate_feed_url(raw: str) -> str | None:
    """Conservative: http(s) only, valid host, non-empty path. We don't
    actually fetch here -- the caller calls poll_feed() which does the
    GET. The validator just blocks attacker-shaped inputs from reaching
    urlopen."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    # Reject dangerous schemes BEFORE the no-scheme branch below
    # promotes anything to https://. Belt-and-suspenders: urlparse alone
    # would pass `javascript:alert(1)` once it gets prefixed to
    # `https://javascript:alert(1)` (hostname=javascript looks valid).
    lower = raw.lower()
    for bad in ("javascript:", "data:", "vbscript:", "file:", "ftp:",
                 "mailto:", "blob:"):
        if lower.startswith(bad):
            return None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        u = urlparse(raw)
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    host = (u.hostname or "")
    if not host or len(host) > 253:
        return None
    return f"{u.scheme}://{host.lower()}" + (u.path or "/") + (
        f"?{u.query}" if u.query else "")


# ---- feed CRUD ----------------------------------------------------------
def add_feed(idx, feed_url: str, *, poll_interval_min: int = 60) -> dict:
    """Insert + return a fresh feed row. UNIQUE constraint on feed_url
    prevents duplicate registration. Returns an existing row's dict
    when the URL is already in the table -- idempotent add."""
    canonical = _validate_feed_url(feed_url)
    if not canonical:
        raise ValueError("feed_url must be a valid http(s) URL")
    interval = max(15, min(int(poll_interval_min or 60), 1440))
    with idx._lock:
        cur = idx._conn.execute(
            "INSERT OR IGNORE INTO podcast_feeds "
            "(feed_url, poll_interval_min, added_at) VALUES (?, ?, ?)",
            (canonical, interval, _now_iso()))
        if cur.rowcount == 0:
            # Already present; return that row.
            row = idx._conn.execute(
                "SELECT * FROM podcast_feeds WHERE feed_url=?",
                (canonical,)).fetchone()
            return dict(row) if row else {}
        feed_id = cur.lastrowid
    return get_feed(idx, feed_id) or {}


def get_feed(idx, feed_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM podcast_feeds WHERE id=?", (feed_id,)).fetchone()
    return dict(row) if row else None


def list_feeds(idx, *, enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM podcast_feeds"
    params: list = []
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY added_at DESC"
    rows = idx._conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def remove_feed(idx, feed_id: int) -> bool:
    """Delete a feed + its episodes (FK cascade)."""
    with idx._lock:
        cur = idx._conn.execute(
            "DELETE FROM podcast_feeds WHERE id=?", (feed_id,))
        return cur.rowcount > 0


def set_feed_enabled(idx, feed_id: int, enabled: bool) -> bool:
    with idx._lock:
        cur = idx._conn.execute(
            "UPDATE podcast_feeds SET enabled=? WHERE id=?",
            (1 if enabled else 0, feed_id))
        return cur.rowcount > 0


# ---- RSS / Atom parsing ------------------------------------------------
# Element names we look for. Namespaces vary between RSS 2.0 (no NS for
# core elements; iTunes NS for duration) and Atom 1.0 (full NS). Strip
# namespaces with .tag.split('}')[-1] when reading.
_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
_ATOM_NS = "http://www.w3.org/2005/Atom"


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _findtext(parent, *names) -> str | None:
    """Find the first matching child whose local-name is in `names`."""
    for child in parent:
        if _localname(child.tag) in names:
            text = (child.text or "").strip()
            return text or None
    return None


def _findattr(parent, name: str, *attrs) -> str | None:
    for child in parent:
        if _localname(child.tag) == name:
            for a in attrs:
                v = child.attrib.get(a)
                if v:
                    return v.strip()
    return None


def _parse_duration(s: str | None) -> int | None:
    """iTunes <itunes:duration> can be either seconds (e.g. '3600'),
    M:SS, or H:MM:SS. Returns int seconds, or None on parse failure."""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        if ":" not in s:
            return int(float(s))
        parts = [int(p) for p in s.split(":")]
    except (TypeError, ValueError):
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def parse_feed_body(body: bytes | str) -> dict:
    """Pure parse: bytes/string of RSS or Atom XML -> structured dict.

    Returns:
        {
          'feed': {'title': ..., 'description': ..., 'homepage': ...},
          'episodes': [
            {'guid': ..., 'title': ..., 'audio_url': ..., 'published_at': ...,
             'description': ..., 'duration_seconds': ...},
            ...
          ],
        }

    Raises ET.ParseError on malformed XML so the caller can surface a
    useful error to the user."""
    if isinstance(body, bytes):
        # ElementTree will sniff the XML declaration's encoding.
        root = ET.fromstring(body)
    else:
        root = ET.fromstring(body)

    feed_meta = {"title": None, "description": None, "homepage": None}
    episodes: list[dict] = []

    # RSS 2.0: <rss><channel><item>...
    # Atom 1.0: <feed><entry>...
    root_name = _localname(root.tag)
    if root_name == "rss":
        channels = [c for c in root if _localname(c.tag) == "channel"]
        channel = channels[0] if channels else None
        if channel is not None:
            feed_meta["title"] = _findtext(channel, "title")
            feed_meta["description"] = _findtext(channel, "description",
                                                    "subtitle")
            feed_meta["homepage"] = _findtext(channel, "link")
            for item in channel:
                if _localname(item.tag) != "item":
                    continue
                guid = _findtext(item, "guid") or _findtext(item, "link")
                if not guid:
                    continue
                audio = _findattr(item, "enclosure", "url")
                duration = _parse_duration(_findtext(item, "duration"))
                episodes.append({
                    "guid": guid,
                    "title": _findtext(item, "title"),
                    "audio_url": audio,
                    "duration_seconds": duration,
                    "published_at": _findtext(item, "pubDate", "published"),
                    "description": _findtext(item, "description", "summary"),
                })
    elif root_name == "feed":  # Atom
        feed_meta["title"] = _findtext(root, "title")
        feed_meta["description"] = _findtext(root, "subtitle", "summary")
        for child in root:
            if _localname(child.tag) == "link":
                href = child.attrib.get("href")
                rel = child.attrib.get("rel") or "alternate"
                if rel == "alternate" and href:
                    feed_meta["homepage"] = href
                    break
        for entry in root:
            if _localname(entry.tag) != "entry":
                continue
            guid = _findtext(entry, "id")
            if not guid:
                continue
            # Atom <link rel="enclosure" type="audio/...">
            audio = None
            for child in entry:
                if _localname(child.tag) == "link":
                    rel = child.attrib.get("rel") or ""
                    if rel == "enclosure":
                        audio = child.attrib.get("href")
                        break
            episodes.append({
                "guid": guid,
                "title": _findtext(entry, "title"),
                "audio_url": audio,
                "duration_seconds": None,
                "published_at": _findtext(entry, "published", "updated"),
                "description": _findtext(entry, "summary", "content"),
            })
    else:
        # Unknown root element -- not RSS, not Atom. Be defensive.
        raise ValueError(
            f"unrecognised feed root element: {root_name!r}")

    return {"feed": feed_meta,
            "episodes": episodes[:_EPISODES_PER_POLL_CAP]}


# ---- HTTP fetch with conditional GET -----------------------------------
def fetch_feed(feed_row: dict) -> tuple[bytes | None, dict | None]:
    """Conditional HTTP GET for a feed. Returns:
      (body, response_headers) on 200
      (None,  response_headers) on 304 Not Modified
      Raises urllib.error.URLError on network failure -- the caller
      surfaces the error onto the feed row.

    We send ETag / If-Modified-Since headers when previously seen.
    Reasonable headers + a tight timeout."""
    url = feed_row.get("feed_url")
    if not url:
        return None, None
    headers = {"User-Agent": _FEED_USER_AGENT,
                "Accept": "application/rss+xml,application/atom+xml,"
                          "application/xml,text/xml;q=0.9,*/*;q=0.5"}
    etag = feed_row.get("last_etag")
    last_mod = feed_row.get("last_modified")
    if etag:
        headers["If-None-Match"] = etag
    if last_mod:
        headers["If-Modified-Since"] = last_mod
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_FEED_FETCH_TIMEOUT_SEC) as resp:
            return resp.read(), dict(resp.headers.items())
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, dict(e.headers.items()) if e.headers else {}
        raise


# ---- end-to-end poll ----------------------------------------------------
def upsert_episodes(idx, feed_id: int, episodes: list[dict]) -> tuple[int, int]:
    """Insert new + return (inserted_count, already_seen_count)."""
    inserted = 0
    seen = 0
    now = _now_iso()
    with idx._lock:
        for ep in episodes:
            guid = (ep.get("guid") or "").strip()
            if not guid:
                continue
            cur = idx._conn.execute(
                "INSERT OR IGNORE INTO podcast_episodes "
                "(feed_id, guid, title, audio_url, duration_seconds, "
                " published_at, description, status, discovered_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)",
                (feed_id, guid, ep.get("title"), ep.get("audio_url"),
                 ep.get("duration_seconds"), ep.get("published_at"),
                 ep.get("description"), now))
            if cur.rowcount:
                inserted += 1
            else:
                seen += 1
    return inserted, seen


def record_feed_meta(idx, feed_id: int, *, title: str | None,
                      description: str | None, homepage: str | None,
                      etag: str | None, last_modified: str | None,
                      ok: bool, error: str | None = None) -> None:
    with idx._lock:
        if ok:
            idx._conn.execute(
                "UPDATE podcast_feeds SET "
                "  title = COALESCE(?, title), "
                "  description = COALESCE(?, description), "
                "  homepage = COALESCE(?, homepage), "
                "  last_polled_at = ?, "
                "  last_etag = COALESCE(?, last_etag), "
                "  last_modified = COALESCE(?, last_modified), "
                "  error_count = 0, last_error = NULL "
                "WHERE id = ?",
                (title, description, homepage, _now_iso(),
                 etag, last_modified, feed_id))
        else:
            idx._conn.execute(
                "UPDATE podcast_feeds SET "
                "  last_polled_at = ?, "
                "  error_count = error_count + 1, "
                "  last_error = ? "
                "WHERE id = ?",
                (_now_iso(), (error or "")[:512], feed_id))


def poll_feed(idx, feed_id: int) -> dict:
    """Fetch + parse + upsert episodes for one feed. Returns a structured
    result dict the endpoint can surface verbatim."""
    feed = get_feed(idx, feed_id)
    if feed is None:
        return {"ok": False, "error": f"feed not found: {feed_id}"}
    if not feed.get("enabled"):
        return {"ok": True, "feed_id": feed_id, "skipped": "disabled"}
    try:
        body, headers = fetch_feed(feed)
    except Exception as e:
        log.warning("podcast feed fetch failed (%s): %s",
                     feed.get("feed_url"), e)
        record_feed_meta(idx, feed_id, title=None, description=None,
                          homepage=None, etag=None, last_modified=None,
                          ok=False, error=str(e))
        return {"ok": False, "feed_id": feed_id, "error": str(e)}
    if body is None:
        # 304 Not Modified -- count as success but no new episodes.
        record_feed_meta(idx, feed_id, title=None, description=None,
                          homepage=None,
                          etag=(headers or {}).get("ETag"),
                          last_modified=(headers or {}).get("Last-Modified"),
                          ok=True)
        return {"ok": True, "feed_id": feed_id, "not_modified": True,
                "inserted": 0, "seen": 0}
    try:
        parsed = parse_feed_body(body)
    except (ET.ParseError, ValueError) as e:
        record_feed_meta(idx, feed_id, title=None, description=None,
                          homepage=None, etag=None, last_modified=None,
                          ok=False, error=f"parse: {e}")
        return {"ok": False, "feed_id": feed_id, "error": f"parse: {e}"}
    inserted, seen = upsert_episodes(idx, feed_id, parsed["episodes"])
    record_feed_meta(idx, feed_id,
                      title=parsed["feed"]["title"],
                      description=parsed["feed"]["description"],
                      homepage=parsed["feed"]["homepage"],
                      etag=(headers or {}).get("ETag"),
                      last_modified=(headers or {}).get("Last-Modified"),
                      ok=True)
    return {"ok": True, "feed_id": feed_id,
            "inserted": inserted, "seen": seen,
            "title": parsed["feed"]["title"]}


# ---- episode read paths ------------------------------------------------
def list_episodes(idx, *, feed_id: int | None = None,
                   status: str | None = None,
                   limit: int = 100) -> list[dict]:
    wheres: list[str] = []
    params: list = []
    if feed_id is not None:
        wheres.append("feed_id=?")
        params.append(feed_id)
    if status is not None:
        if status not in _EPISODE_STATUSES:
            raise ValueError(
                f"status must be one of {list(_EPISODE_STATUSES)}")
        wheres.append("status=?")
        params.append(status)
    where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
    params.append(max(1, min(int(limit), 1000)))
    rows = idx._conn.execute(
        "SELECT * FROM podcast_episodes" + where_sql +
        " ORDER BY published_at DESC NULLS LAST, id DESC LIMIT ?",
        params).fetchall()
    return [dict(r) for r in rows]


def get_episode(idx, episode_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM podcast_episodes WHERE id=?",
        (episode_id,)).fetchone()
    return dict(row) if row else None


def set_episode_status(idx, episode_id: int, status: str) -> bool:
    if status not in _EPISODE_STATUSES:
        raise ValueError(
            f"status must be one of {list(_EPISODE_STATUSES)}")
    with idx._lock:
        cur = idx._conn.execute(
            "UPDATE podcast_episodes SET status=? WHERE id=?",
            (status, episode_id))
        return cur.rowcount > 0


# ---- audio download pipeline ------------------------------------------
# v3.1 track B step 2. yt-dlp's audio extractor handles the
# enclosure URL + ffmpeg post-process. Output lands at
#   <data_root>/Podcasts/<feed-slug>/<episode-slug>.mp3
# so the user has a clear filesystem layout + Whisper has a single
# path to feed.

_SLUG_RE = re.compile(r"[^a-z0-9]+")
# Hard cap on the audio file size to guard against feeds advertising a
# 50 GB enclosure (rare, but happens with mis-set length tags). 2 GB
# is generous for any reasonable podcast episode.
_AUDIO_MAX_BYTES = 2 * 1024 * 1024 * 1024


def _slugify(text: str | None, *, fallback: str = "untitled") -> str:
    if not text:
        return fallback
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug[:80] or fallback


def _podcast_root(data_root: Path) -> Path:
    root = Path(data_root) / "Podcasts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _episode_audio_path(data_root: Path, feed_row: dict,
                         episode_row: dict) -> Path:
    feed_slug = _slugify(feed_row.get("title") or feed_row.get("feed_url"),
                          fallback=f"feed-{feed_row.get('id') or 0}")
    ep_slug = _slugify(episode_row.get("title"),
                        fallback=f"ep-{episode_row.get('id') or 0}")
    folder = _podcast_root(data_root) / feed_slug
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{ep_slug}.mp3"


def _record_audio_result(idx, episode_id: int, *,
                          local_path: str | None,
                          size_bytes: int | None,
                          error: str | None,
                          status: str) -> None:
    with idx._lock:
        idx._conn.execute(
            "UPDATE podcast_episodes SET "
            "  audio_local_path = COALESCE(?, audio_local_path), "
            "  audio_downloaded_at = ?, "
            "  audio_size_bytes = COALESCE(?, audio_size_bytes), "
            "  audio_download_error = ?, "
            "  status = ? "
            "WHERE id = ?",
            (local_path, _now_iso() if local_path else None,
             size_bytes, error, status, episode_id))


def download_episode_audio(idx, episode_id: int, *,
                            data_root: Path,
                            ytdlp_cmd: list[str] | None = None,
                            timeout_sec: int = 600) -> dict:
    """Download an episode's MP3 via yt-dlp + ffmpeg into the per-feed
    folder. Idempotent -- if the file already exists at the canonical
    path AND has non-zero size we mark status='downloaded' without
    re-downloading. Returns a structured result the endpoint surfaces."""
    episode = get_episode(idx, episode_id)
    if episode is None:
        return {"ok": False, "error": f"episode not found: {episode_id}"}
    feed = get_feed(idx, episode["feed_id"])
    if feed is None:
        return {"ok": False,
                "error": f"feed {episode['feed_id']} not found"}
    if not episode.get("audio_url"):
        return {"ok": False, "error": "episode has no audio_url"}

    out_path = _episode_audio_path(Path(data_root), feed, episode)
    # Idempotent -- skip re-download when the canonical path already
    # has a non-zero file. yt-dlp writes a .mp3 extension after the
    # ffmpeg post-process, so we check the .mp3 directly.
    if out_path.exists() and out_path.stat().st_size > 0:
        _record_audio_result(idx, episode_id,
                              local_path=str(out_path),
                              size_bytes=out_path.stat().st_size,
                              error=None,
                              status=EPISODE_STATUS_DOWNLOADED)
        return {"ok": True, "episode_id": episode_id,
                "local_path": str(out_path),
                "size_bytes": out_path.stat().st_size,
                "skipped_existing": True}

    # Move to status='queued' if not already there. This makes the row
    # show up in the in-flight section of the dashboard during the
    # download (which can take several minutes for an hour-long pod).
    if episode["status"] != EPISODE_STATUS_QUEUED:
        with idx._lock:
            idx._conn.execute(
                "UPDATE podcast_episodes SET status=? WHERE id=?",
                (EPISODE_STATUS_QUEUED, episode_id))

    # Output template: drop the extension; yt-dlp adds .mp3 after
    # ffmpeg converts. Pass the bare stem.
    out_stem = out_path.with_suffix("")
    cmd = list(ytdlp_cmd or [])
    if not cmd:
        # Lazy import to avoid a hard server.py dependency from here.
        try:
            import server as _server  # noqa: WPS433
            cmd = list(getattr(_server, "YTDLP_CMD", []))
        except Exception:
            cmd = []
    if not cmd:
        return {"ok": False, "error": "yt-dlp command not configured"}

    args = cmd + [
        "--no-progress",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",   # use VBR best
        "--max-filesize", str(_AUDIO_MAX_BYTES),
        # Output template: yt-dlp will append .mp3 after the postprocess
        "-o", str(out_stem) + ".%(ext)s",
        episode["audio_url"],
    ]
    log.info("podcast download: episode_id=%d url=%s -> %s",
              episode_id, episode["audio_url"], out_path)
    try:
        cp = subprocess.run(
            args, capture_output=True, text=True,
            timeout=timeout_sec, check=False,
        )
    except subprocess.TimeoutExpired:
        _record_audio_result(idx, episode_id, local_path=None,
                              size_bytes=None,
                              error=f"download timed out after {timeout_sec}s",
                              status=EPISODE_STATUS_NEW)
        return {"ok": False, "episode_id": episode_id,
                "error": "timeout"}
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "yt-dlp failed").strip()[-512:]
        _record_audio_result(idx, episode_id, local_path=None,
                              size_bytes=None, error=err,
                              status=EPISODE_STATUS_NEW)
        return {"ok": False, "episode_id": episode_id, "error": err}
    if not out_path.exists() or out_path.stat().st_size == 0:
        _record_audio_result(idx, episode_id, local_path=None,
                              size_bytes=None,
                              error="output file missing post-download",
                              status=EPISODE_STATUS_NEW)
        return {"ok": False, "episode_id": episode_id,
                "error": "output file missing"}
    size = out_path.stat().st_size
    _record_audio_result(idx, episode_id, local_path=str(out_path),
                          size_bytes=size, error=None,
                          status=EPISODE_STATUS_DOWNLOADED)
    return {"ok": True, "episode_id": episode_id,
            "local_path": str(out_path), "size_bytes": size,
            "feed_id": episode["feed_id"]}
