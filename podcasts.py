"""Podcast feed, episode, audio, and corpus support.

Uoink watches registered RSS feeds for episode metadata. Feed registration
does not authorize audio processing: ``auto_ingest`` is a separate per-feed
opt-in, off by default, for downloading, transcribing, and publishing episodes
discovered while that flag is enabled.

Compute (locked policy: model-agnostic + local-first):
- RSS XML parsing uses Python's stdlib xml.etree.ElementTree -- no
  new vendored dependency. Sticks to RSS 2.0 + Atom 1.0 element names
  (the two formats that cover 99%+ of feeds in the wild).
- Polling is a plain HTTP GET with conditional ETag / If-Modified-Since
  headers when the feed previously returned them, so a daily news
  podcast doesn't re-download an unchanged feed body on every poll.

This module owns parsing, persistence, due-feed selection, audio download, and
the transcript-to-corpus bridge. The 30-second scheduler and HTTP/MCP
transports live in server.py and uoink_mcp_tools.py."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("uoink.podcasts")

# Bounded enum for the episode status flow. The dashboard renders
# 'new' as an unread chip; 'queued' once the user opts in to download;
# 'downloaded' + 'transcribed' as the audio + transcript
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

# Cap how many episodes we materialise per poll so a freshly-added feed with
# 800 back-episodes cannot flood local storage. The feed's latest 50 entries
# are retained; this release has no back-catalog load-more path.
_EPISODES_PER_POLL_CAP = 50

# Per-source safety caps from the Living Library decision record. The first
# opt-in may enroll at most 25 already-known episodes, and no source may start
# more than 10 new ingests on one UTC day.
AUTO_INGEST_BACK_CATALOG_CAP = 25
AUTO_INGEST_DAILY_CAP = 10

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
    if u.username is not None or u.password is not None:
        return None
    host = (u.hostname or "")
    if not host or len(host) > 253:
        return None
    try:
        port = u.port
    except ValueError:
        return None
    host = host.lower()
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return f"{u.scheme}://{netloc}" + (u.path or "/") + (
        f"?{u.query}" if u.query else "")


# ---- feed CRUD ----------------------------------------------------------
def add_feed(idx, feed_url: str, *, poll_interval_min: int = 60,
             auto_ingest: bool = False) -> dict:
    """Insert + return a fresh feed row. UNIQUE constraint on feed_url
    prevents duplicate registration. Returns an existing row's dict
    when the URL is already in the table -- idempotent add."""
    canonical = _validate_feed_url(feed_url)
    if not canonical:
        raise ValueError("feed_url must be a valid http(s) URL")
    interval = max(15, min(int(poll_interval_min or 60), 1440))
    with idx.write_transaction() as conn:
        # Phase 3: once the source tables exist, the old boolean can no longer
        # opt a feed in. The feed is projected as an off standing source; consent
        # needs the confirmed set_source_consent operation and its receipt.
        managed = _subscriptions().tables_present(conn)
        stored_auto_ingest = 0 if managed else (1 if auto_ingest else 0)
        cur = conn.execute(
            "INSERT OR IGNORE INTO podcast_feeds "
            "(feed_url, poll_interval_min, auto_ingest, added_at) "
            "VALUES (?, ?, ?, ?)",
            (canonical, interval, stored_auto_ingest, _now_iso()))
        if cur.rowcount == 0:
            # Already present; return that row.
            row = conn.execute(
                "SELECT * FROM podcast_feeds WHERE feed_url=?",
                (canonical,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM podcast_feeds WHERE id=?",
                (cur.lastrowid,)).fetchone()
        result = dict(row) if row else {}
        if result and managed:
            result["source_id"] = _subscriptions().legacy_register(
                conn, kind="podcast_rss", url=result["feed_url"],
                feed_id=int(result["id"]), interval=interval,
                detection_enabled=bool(result.get("enabled", 1)))
            if auto_ingest:
                result["consent_required"] = True
    return result


def get_feed(idx, feed_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM podcast_feeds WHERE id=?", (feed_id,)).fetchone()
    return dict(row) if row else None


def list_feeds(idx, *, enabled_only: bool = False) -> list[dict]:
    sql = (
        "SELECT f.*, "
        "  COUNT(e.id) AS episode_count, "
        "  MAX(e.published_at) AS latest_episode_published_at, "
        "  (SELECT e2.title FROM podcast_episodes e2 "
        "   WHERE e2.feed_id = f.id "
        "   ORDER BY e2.published_at DESC, e2.discovered_at DESC "
        "   LIMIT 1) AS last_episode_title "
        "FROM podcast_feeds f "
        "LEFT JOIN podcast_episodes e ON e.feed_id = f.id"
    )
    params: list = []
    if enabled_only:
        sql += " WHERE f.enabled = 1"
    sql += " GROUP BY f.id ORDER BY f.added_at DESC"
    rows = idx._conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


class ManagedBySubscription(ValueError):
    """The feed is a Phase 3 standing source; the old boolean route cannot
    change its consent (contract phase3-v1-2026-09-07, "Consent and
    enrollment": consent needs a user-confirmed operation and a receipt)."""

    def __init__(self, source_id: str):
        super().__init__(
            "standing capture consent for this feed is managed by source "
            "subscriptions; use set_source_consent")
        self.source_id = source_id


def _subscriptions():
    """Lazy import: podcasts.py stays importable on trees without Phase 3."""
    import source_subscriptions  # noqa: WPS433
    return source_subscriptions


def remove_feed(idx, feed_id: int) -> bool:
    """Delete a feed + its episodes (FK cascade).

    Phase 3: a feed linked to a source subscription is archived instead. The
    subscription, its consent receipts, items and ledger rows reference the
    feed and must survive (contract, "Migration 0028 schema": old delete
    routes archive the source and preserve referenced rows)."""
    with idx.write_transaction() as conn:
        source_id = _subscriptions().legacy_archive(conn, feed_id=int(feed_id))
        if source_id is not None:
            cur = conn.execute(
                "UPDATE podcast_feeds SET enabled=0, auto_ingest=0 WHERE id=?",
                (feed_id,))
            return cur.rowcount > 0
        cur = conn.execute(
            "DELETE FROM podcast_feeds WHERE id=?", (feed_id,))
        return cur.rowcount > 0


def set_feed_enabled(idx, feed_id: int, enabled: bool) -> bool:
    with idx.write_transaction() as conn:
        cur = conn.execute(
            "UPDATE podcast_feeds SET enabled=? WHERE id=?",
            (1 if enabled else 0, feed_id))
        # The old flag is a compatibility projection of the authoritative
        # detection flag; keep the two in step.
        _subscriptions().legacy_set_detection(
            conn, feed_id=int(feed_id), enabled=bool(enabled))
        return cur.rowcount > 0


def set_feed_auto_ingest(idx, feed_id: int, auto_ingest: bool) -> bool:
    """Set the explicit audio/transcription opt-in for one feed.

    Phase 3: once a feed is linked to a source subscription this boolean can
    no longer grant or revoke capture. Consent requires the dashboard's
    confirmed operation, a capability token and a receipt
    (``set_source_consent``); raising here keeps the old route from becoming
    a bypass. Unlinked feeds (pre-import trees) keep the legacy behaviour.
    """
    with idx.write_transaction() as conn:
        source_id = _subscriptions().legacy_source_id(conn, feed_id=int(feed_id))
        if source_id is not None:
            raise ManagedBySubscription(source_id)
        cur = conn.execute(
            "UPDATE podcast_feeds SET auto_ingest=? WHERE id=?",
            (1 if auto_ingest else 0, feed_id))
        return cur.rowcount > 0


def _parse_poll_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def list_due_feeds(idx, *, now: datetime | None = None) -> list[dict]:
    """Return enabled feeds whose persisted poll interval has elapsed."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    due: list[tuple[datetime, dict]] = []
    for feed in list_feeds(idx, enabled_only=True):
        last = _parse_poll_timestamp(feed.get("last_polled_at"))
        interval = max(15, min(int(feed.get("poll_interval_min") or 60), 1440))
        due_at = (last + timedelta(minutes=interval)
                  if last else datetime.min.replace(tzinfo=timezone.utc))
        if due_at <= current:
            due.append((due_at, feed))
    due.sort(key=lambda item: (item[0], int(item[1].get("id") or 0)))
    return [feed for _, feed in due]


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
            {'guid': ..., 'title': ..., 'audio_url': ...,
             'episode_page_url': ..., 'published_at': ...,
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
                episode_page_url = _findtext(item, "link")
                guid = _findtext(item, "guid") or episode_page_url
                if not guid:
                    continue
                audio = _findattr(item, "enclosure", "url")
                duration = _parse_duration(_findtext(item, "duration"))
                episodes.append({
                    "guid": guid,
                    "title": _findtext(item, "title"),
                    "audio_url": audio,
                    "episode_page_url": episode_page_url,
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
            episode_page_url = None
            for child in entry:
                if _localname(child.tag) == "link":
                    rel = child.attrib.get("rel") or ""
                    if rel == "enclosure":
                        audio = child.attrib.get("href")
                    elif rel in ("", "alternate") and not episode_page_url:
                        episode_page_url = child.attrib.get("href")
            episodes.append({
                "guid": guid,
                "title": _findtext(entry, "title"),
                "audio_url": audio,
                "episode_page_url": episode_page_url,
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
def _upsert_episodes_with_ids(
        idx, feed_id: int, episodes: list[dict]) -> tuple[int, int, list[int]]:
    """Insert episodes and retain the ids created by this exact poll."""
    inserted = 0
    seen = 0
    inserted_ids: list[int] = []
    now = _now_iso()
    with idx.write_transaction() as conn:
        feed = conn.execute(
            "SELECT auto_ingest FROM podcast_feeds WHERE id=?", (feed_id,)
        ).fetchone()
        existing_episode_count = int(conn.execute(
            "SELECT COUNT(*) FROM podcast_episodes WHERE feed_id=?", (feed_id,)
        ).fetchone()[0])
        # The first feed response is a back catalog even when registration was
        # opted in. Leave it unmarked for the scheduler's 25-item repair. Once
        # a feed already has episodes, newly discovered rows are future items
        # and retain durable eligibility across helper restarts.
        auto_ingest_requested = (
            1 if feed and feed["auto_ingest"] and existing_episode_count else 0
        )
        for ep in episodes:
            guid = (ep.get("guid") or "").strip()
            if not guid:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO podcast_episodes "
                "(feed_id, guid, title, audio_url, episode_page_url, "
                " duration_seconds, published_at, description, status, "
                " discovered_at, auto_ingest_requested) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)",
                (feed_id, guid, ep.get("title"), ep.get("audio_url"),
                 ep.get("episode_page_url"), ep.get("duration_seconds"),
                 ep.get("published_at"), ep.get("description"), now,
                 auto_ingest_requested))
            if cur.rowcount:
                inserted += 1
                inserted_ids.append(int(cur.lastrowid))
            else:
                seen += 1
                # Migration 0022 added this field after feeds could already
                # contain episodes. A later poll repairs those older rows
                # without changing their feed-scoped identity or status.
                if ep.get("episode_page_url"):
                    conn.execute(
                        "UPDATE podcast_episodes SET episode_page_url="
                        "COALESCE(episode_page_url, ?) "
                        "WHERE feed_id=? AND guid=?",
                        (ep.get("episode_page_url"), feed_id, guid))
    return inserted, seen, inserted_ids


def upsert_episodes(idx, feed_id: int, episodes: list[dict]) -> tuple[int, int]:
    """Insert new + return (inserted_count, already_seen_count)."""
    inserted, seen, _ = _upsert_episodes_with_ids(idx, feed_id, episodes)
    return inserted, seen


def record_feed_meta(idx, feed_id: int, *, title: str | None,
                      description: str | None, homepage: str | None,
                      etag: str | None, last_modified: str | None,
                      ok: bool, error: str | None = None) -> None:
    with idx.write_transaction() as conn:
        if ok:
            conn.execute(
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
            conn.execute(
                "UPDATE podcast_feeds SET "
                "  last_polled_at = ?, "
                "  error_count = error_count + 1, "
                "  last_error = ? "
                "WHERE id = ?",
                (_now_iso(), (error or "")[:512], feed_id))


def poll_feed(idx, feed_id: int, *, refresh=None) -> dict:
    """Fetch + parse + upsert episodes for one feed. Returns a structured
    result dict the endpoint can surface verbatim.

    Phase 3: a feed linked to a source subscription is polled only through the
    subscription service's due-time/lease gate (contract, "Scheduler and
    adapter boundaries"). ``refresh`` is the injected ``callable(source_id)``
    that performs that gated refresh; without it the legacy path refuses
    rather than running a second detection authority."""
    feed = get_feed(idx, feed_id)
    if feed is None:
        return {"ok": False, "error": f"feed not found: {feed_id}"}
    with idx._lock:
        source_id = _subscriptions().legacy_source_id(idx._conn, feed_id=int(feed_id))
    if source_id is not None:
        if not callable(refresh):
            return {"ok": False, "feed_id": feed_id, "source_id": source_id,
                    "error": "managed_by_subscription"}
        result = refresh(source_id)
        shaped = {"ok": bool(result.get("ok")), "feed_id": feed_id,
                  "source_id": source_id, "managed_by_subscription": True,
                  "outcome": result.get("outcome"),
                  "next_poll_at_ms": result.get("next_poll_at_ms")}
        poll = result.get("poll") if isinstance(result.get("poll"), dict) else {}
        shaped["inserted"] = int(poll.get("inserted") or 0)
        shaped["seen"] = int(poll.get("updated") or 0)
        shaped["new_episode_ids"] = []
        if not result.get("ok"):
            shaped["error"] = (result.get("error") or {}).get("code", "refresh_failed")
        elif poll.get("ok") is False:
            shaped["ok"] = False
            shaped["error"] = poll.get("code") or "poll_failed"
        return shaped
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
                "inserted": 0, "seen": 0, "new_episode_ids": []}
    try:
        parsed = parse_feed_body(body)
    except (ET.ParseError, ValueError) as e:
        record_feed_meta(idx, feed_id, title=None, description=None,
                          homepage=None, etag=None, last_modified=None,
                          ok=False, error=f"parse: {e}")
        return {"ok": False, "feed_id": feed_id, "error": f"parse: {e}"}
    inserted, seen, inserted_ids = _upsert_episodes_with_ids(
        idx, feed_id, parsed["episodes"])
    record_feed_meta(idx, feed_id,
                      title=parsed["feed"]["title"],
                      description=parsed["feed"]["description"],
                      homepage=parsed["feed"]["homepage"],
                      etag=(headers or {}).get("ETag"),
                      last_modified=(headers or {}).get("Last-Modified"),
                      ok=True)
    return {"ok": True, "feed_id": feed_id,
            "inserted": inserted, "seen": seen,
            "new_episode_ids": inserted_ids,
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


def list_auto_ingest_candidates(
        idx, *, feed_id: int | None = None, limit: int = 1,
        now: datetime | None = None) -> list[dict]:
    """Return eligible episodes from feeds that are opted in right now.

    Already-started episodes may finish regardless of the daily cap. New work
    is bounded to 10 starts per UTC day per source. The default of one episode
    per feed poll still prevents a source from monopolizing the scheduler.

    Phase 3: when the source tables exist, the episode marker no longer
    authorizes anything. Only episodes whose source item currently holds a
    ``started`` row in the capture ledger are returned, so every old caller is
    routed through the atomic start reservation (contract, "Atomic starts").
    """
    with idx._lock:
        managed = _subscriptions().tables_present(idx._conn)
        if managed:
            feed_ids = ([int(feed_id)] if feed_id is not None else [
                int(r[0]) for r in idx._conn.execute(
                    "SELECT id FROM podcast_feeds").fetchall()])
            started: list[int] = []
            for fid in feed_ids:
                started.extend(_subscriptions().legacy_started_episode_ids(idx._conn, fid))
    if managed:
        rows: list[dict] = []
        for episode_id in started[:max(1, min(int(limit), 50))]:
            row = get_episode_with_feed(idx, episode_id)
            if row is not None:
                rows.append(row)
        return rows
    wheres = [
        "e.auto_ingest_requested = 1",
        "e.yoink_video_id IS NULL",
        "e.status != ?",
        "f.enabled = 1",
        "f.auto_ingest = 1",
    ]
    params: list[Any] = [EPISODE_STATUS_IGNORED]
    if feed_id is not None:
        wheres.append("e.feed_id = ?")
        params.append(int(feed_id))
    requested_limit = max(1, min(int(limit), 50))
    rows = idx._conn.execute(
        "SELECT e.*, f.title AS podcast_title, f.feed_url "
        "FROM podcast_episodes e "
        "JOIN podcast_feeds f ON f.id=e.feed_id "
        "WHERE " + " AND ".join(wheres) + " "
        "ORDER BY CASE WHEN e.status='new' THEN 1 ELSE 0 END, "
        "e.published_at DESC NULLS LAST, e.id DESC",
        params,
    ).fetchall()
    shaped = [dict(row) for row in rows]
    selected: list[dict] = []
    starts_by_feed: dict[int, int] = {}
    for row in shaped:
        if len(selected) >= requested_limit:
            break
        if row.get("status") != EPISODE_STATUS_NEW:
            selected.append(row)
            continue
        source_id = int(row["feed_id"])
        if source_id not in starts_by_feed:
            starts_by_feed[source_id] = count_daily_ingest_starts(
                idx, source_id, now=now)
        if starts_by_feed[source_id] >= AUTO_INGEST_DAILY_CAP:
            continue
        selected.append(row)
        starts_by_feed[source_id] += 1
    return selected


def count_daily_ingest_starts(
        idx, feed_id: int, *, now: datetime | None = None) -> int:
    """Count durable evidence that this source started ingest today."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    day = current.astimezone(timezone.utc).date().isoformat()
    row = idx._conn.execute(
        "SELECT COUNT(DISTINCT e.id) "
        "FROM podcast_episodes e "
        "WHERE e.feed_id=? AND ("
        "  substr(coalesce(e.audio_downloaded_at, ''), 1, 10)=? "
        "  OR substr(coalesce(e.transcript_finished_at, ''), 1, 10)=? "
        "  OR EXISTS ("
        "    SELECT 1 FROM jobs j "
        "    WHERE j.kind='podcast_transcribe' "
        "      AND substr(j.updated_at, 1, 10)=? "
        "      AND json_valid(j.metadata_json) "
        "      AND CAST(json_extract(j.metadata_json, '$.episode_id') AS INTEGER)=e.id"
        "  )"
        ")",
        (int(feed_id), day, day, day),
    ).fetchone()
    return int(row[0]) if row else 0


def _published_sort_key(row: dict) -> tuple[float, int]:
    raw = str(row.get("published_at") or "").strip()
    parsed = None
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(raw)
            except (TypeError, ValueError, OverflowError):
                parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        stamp = parsed.astimezone(timezone.utc).timestamp()
    else:
        stamp = 0.0
    return stamp, int(row.get("id") or 0)


def repair_stranded_auto_ingest(
        idx, *, feed_id: int | None = None, dry_run: bool = False,
        now: datetime | None = None) -> dict:
    """Enroll a bounded backlog for currently opted-in feeds, once.

    ``auto_ingest_requested`` remains the durable cohort marker, but the
    scheduler computes that cohort from the feed's current consent flag. Once
    25 rows have ever been marked for a source, later repair passes do not pull
    progressively older episodes into the queue.

    Phase 3: with the source tables present this pass is report-only. The
    initial cohort is chosen once by the subscription service from its own
    observations (contract, "Consent and enrollment"); the old marker must not
    enlarge or replace it, so ``dry_run`` is forced on.
    """
    with idx._lock:
        managed = _subscriptions().tables_present(idx._conn)
    if managed:
        dry_run = True
    params: list[Any] = []
    feed_filter = ""
    if feed_id is not None:
        feed_filter = " AND f.id=?"
        params.append(int(feed_id))
    feeds = idx._conn.execute(
        "SELECT f.id, f.title FROM podcast_feeds f "
        "WHERE f.enabled=1 AND f.auto_ingest=1" + feed_filter,
        params,
    ).fetchall()
    stranded_before = int(idx._conn.execute(
        "SELECT COUNT(*) FROM podcast_episodes "
        "WHERE status='new' AND auto_ingest_requested=0"
    ).fetchone()[0])

    selected_by_feed: dict[int, list[int]] = {}
    detail: dict[str, int] = {}
    for feed_raw in feeds:
        source_id = int(feed_raw["id"])
        requested = int(idx._conn.execute(
            "SELECT COUNT(*) FROM podcast_episodes "
            "WHERE feed_id=? AND auto_ingest_requested=1",
            (source_id,),
        ).fetchone()[0])
        remaining = max(0, AUTO_INGEST_BACK_CATALOG_CAP - requested)
        candidates = [dict(row) for row in idx._conn.execute(
            "SELECT id, published_at FROM podcast_episodes "
            "WHERE feed_id=? AND status='new' "
            "AND auto_ingest_requested=0 AND yoink_video_id IS NULL",
            (source_id,),
        ).fetchall()]
        candidates.sort(key=_published_sort_key, reverse=True)
        selected = [int(row["id"]) for row in candidates[:remaining]]
        selected_by_feed[source_id] = selected
        detail[str(source_id)] = len(selected)

    marked = sum(len(ids) for ids in selected_by_feed.values())
    if marked and not dry_run:
        with idx.write_transaction() as conn:
            for source_id, ids in selected_by_feed.items():
                conn.executemany(
                    "UPDATE podcast_episodes SET auto_ingest_requested=1 "
                    "WHERE id=? AND feed_id=? AND status='new' "
                    "AND auto_ingest_requested=0",
                    [(episode_id, source_id) for episode_id in ids],
                )

    eligible_after = int(idx._conn.execute(
        "SELECT COUNT(*) FROM podcast_episodes e "
        "JOIN podcast_feeds f ON f.id=e.feed_id "
        "WHERE f.enabled=1 AND f.auto_ingest=1 "
        "AND e.status!='ignored' AND e.yoink_video_id IS NULL "
        "AND e.auto_ingest_requested=1"
    ).fetchone()[0])
    if dry_run:
        eligible_after += marked
    schedulable_today = 0
    for feed_raw in feeds:
        source_id = int(feed_raw["id"])
        existing = int(idx._conn.execute(
            "SELECT COUNT(*) FROM podcast_episodes "
            "WHERE feed_id=? AND status='new' AND yoink_video_id IS NULL "
            "AND auto_ingest_requested=1",
            (source_id,),
        ).fetchone()[0])
        if dry_run:
            existing += len(selected_by_feed[source_id])
        remaining_today = max(
            0,
            AUTO_INGEST_DAILY_CAP - count_daily_ingest_starts(
                idx, source_id, now=now),
        )
        schedulable_today += min(existing, remaining_today)

    return {
        "stranded_before": stranded_before,
        "feeds_considered": len(feeds),
        "marked_eligible": 0 if dry_run else marked,
        "would_mark_eligible": marked,
        "eligible_after": eligible_after,
        "schedulable_today": schedulable_today,
        "back_catalog_cap": AUTO_INGEST_BACK_CATALOG_CAP,
        "daily_cap": AUTO_INGEST_DAILY_CAP,
        "by_feed": detail,
        "dry_run": dry_run,
        "delegated_to": "source_subscriptions" if managed else None,
    }


def get_episode(idx, episode_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM podcast_episodes WHERE id=?",
        (episode_id,)).fetchone()
    return dict(row) if row else None


def get_episode_with_feed(idx, episode_id: int) -> dict | None:
    """Return one episode together with the feed fields needed to publish it."""
    row = idx._conn.execute(
        "SELECT e.*, f.feed_url, f.title AS podcast_title, "
        "f.homepage AS podcast_homepage "
        "FROM podcast_episodes e JOIN podcast_feeds f ON f.id=e.feed_id "
        "WHERE e.id=?", (episode_id,)).fetchone()
    return dict(row) if row else None


def set_episode_status(idx, episode_id: int, status: str) -> bool:
    if status not in _EPISODE_STATUSES:
        raise ValueError(
            f"status must be one of {list(_EPISODE_STATUSES)}")
    with idx.write_transaction() as conn:
        cur = conn.execute(
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


# ---- transcript -> corpus bridge --------------------------------------
def _http_source_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    return value if parsed.scheme in ("http", "https") and parsed.netloc else None


def _episode_source_url(row: dict) -> str:
    """Prefer the episode page; never use an opaque GUID as a fake URL."""
    for value in (
        row.get("episode_page_url"), row.get("guid"),
        row.get("podcast_homepage"), row.get("feed_url"),
    ):
        url = _http_source_url(value)
        if url:
            return url
    raise ValueError("episode and feed have no valid http(s) source URL")


def _episode_corpus_id(row: dict) -> tuple[str, str]:
    identity = f"{row.get('feed_url') or ''}\n{row.get('guid') or ''}"
    suffix = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:11]
    return f"episode_{suffix}", suffix


class CorpusIdentityConflict(ValueError):
    """The corpus row at this episode's deterministic, shortened id carries a
    different full identity (feed URL plus GUID). AS-06: the publisher never
    links, resumes or overwrites such a row; the conflict stays visible."""


def _episode_full_identity(row: dict) -> tuple[str, str, str]:
    """``(normalized feed URL, guid, capture_key)``: the collision-resistant
    identity persisted with every publication (AS-06)."""
    feed_url = str(row.get("feed_url") or "").strip()
    guid = str(row.get("guid") or "")
    try:
        feed_key = _subscriptions().normalize_podcast_feed_url(feed_url)
    except Exception:
        feed_key = feed_url
    return feed_key, guid, _subscriptions().capture_key_for("podcast_rss", feed_key, guid)


def _check_corpus_identity(idx, existing: dict | None, row: dict, video_id: str) -> None:
    """AS-06: before writing at a shortened corpus id, run the one full-identity
    check shared with the standing-capture service
    (``source_subscriptions.podcast_identity_conflict``): the row's persisted
    feed URL/GUID, its capture key, its ``episode_id`` provenance and every
    episode already linked to it by ``yoink_video_id`` (the reverse legacy
    link) must all agree with this episode. Any disagreement, or a row whose
    identity cannot be established at all, raises before anything is
    overwritten; existing content and tombstones are left untouched."""
    if not existing:
        return
    feed_key, guid, capture_key = _episode_full_identity(row)
    episode_id = row.get("id")
    reason = _subscriptions().podcast_identity_conflict(
        idx._conn, dict(existing), feed_key, guid, capture_key,
        episode_id=int(episode_id) if isinstance(episode_id, int) else None)
    if reason:
        raise CorpusIdentityConflict(
            f"corpus id {video_id}: {reason}; refusing to overwrite or link")


def _timestamp_label(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _source_deep_link(source_url: str, seconds: float | int | None) -> str:
    try:
        timestamp = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        timestamp = 0
    return f"{source_url.split('#', 1)[0]}#t={timestamp}"


def _load_transcript(path: Path) -> tuple[dict, list[dict]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"transcript file missing: {path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"transcript is not readable JSON: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("segments"), list):
        raise ValueError("transcript must be an object with a segments array")
    shaped: list[dict] = []
    for seq, segment in enumerate(raw["segments"]):
        if not isinstance(segment, dict):
            raise ValueError(f"transcript segment {seq} must be an object")
        try:
            start = float(segment["start"])
            end = float(segment["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"transcript segment {seq} requires numeric start and end"
            ) from exc
        text = segment.get("text")
        if start < 0 or end < start or not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"transcript segment {seq} has invalid timing or text")
        item: dict[str, Any] = {
            "start": start, "end": end, "text": text.strip(),
        }
        speaker = segment.get("speaker")
        if speaker is not None:
            if not isinstance(speaker, str):
                raise ValueError(f"transcript segment {seq} speaker must be text")
            if speaker.strip():
                item["speaker"] = speaker.strip()
        shaped.append(item)
    if not shaped:
        raise ValueError("transcript segments array is empty")
    return raw, shaped


def load_completed_episode_transcript(idx, episode_id: int) -> dict | None:
    """Load a reusable DONE transcript, or return None when none is recorded.

    A recorded path that no longer loads is an integrity failure, not a cache
    miss. Callers may catch that failure and deliberately transcribe again.
    """
    episode = get_episode(idx, episode_id)
    if episode is None:
        raise LookupError(f"episode not found: {episode_id}")
    path_raw = episode.get("transcript_local_path")
    if episode.get("transcript_status") != "done" or not path_raw:
        return None
    path = Path(path_raw)
    transcript, segments = _load_transcript(path)
    normalized = dict(transcript)
    normalized["segments"] = segments
    return {"path": path, "transcript": normalized}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", delete=False,
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _link_episode_to_yoink(idx, episode_id: int, video_id: str) -> None:
    with idx.write_transaction() as conn:
        cur = conn.execute(
            "UPDATE podcast_episodes SET yoink_video_id=?, status=? WHERE id=?",
            (video_id, EPISODE_STATUS_TRANSCRIBED, episode_id))
        if cur.rowcount != 1:
            raise LookupError(f"episode not found: {episode_id}")


def episode_to_corpus(idx, episode_id: int, *, data_root: Path) -> dict:
    """Publish a completed episode transcript into the shared corpus.

    Identity and file paths are deterministic, so retrying repairs a partial
    write without duplicating the yoink, FTS row, citations, or episode link.
    The MP3 remains flat in the feed directory; Markdown and its sidecar live
    together in a per-episode folder.
    """
    row = get_episode_with_feed(idx, episode_id)
    if row is None:
        raise LookupError(f"episode not found: {episode_id}")
    transcript_path_raw = row.get("transcript_local_path")
    if not transcript_path_raw:
        raise FileNotFoundError("episode has no transcript_local_path")
    transcript_raw, segments = _load_transcript(Path(transcript_path_raw))
    # Phase 6 (phase6-v1): the original transcript bytes are the archived
    # artifact behind every label's provenance; read them once, unchanged.
    transcript_bytes = Path(transcript_path_raw).read_bytes()
    source_url = _episode_source_url(row)
    video_id, suffix = _episode_corpus_id(row)
    podcast_title = row.get("podcast_title") or "Untitled podcast"
    episode_title = row.get("title") or "Untitled episode"
    feed_slug = _slugify(podcast_title, fallback=f"feed-{row['feed_id']}")
    episode_slug = _slugify(episode_title, fallback=f"ep-{episode_id}")
    folder = _podcast_root(Path(data_root)) / feed_slug / f"{episode_slug}-{suffix}"
    corpus_path = folder / f"{folder.name}.md"
    sidecar_path = folder / f"{folder.name}.json"

    speakers = list(dict.fromkeys(
        segment["speaker"] for segment in segments if segment.get("speaker")
    ))
    transcript_citations: list[dict] = []
    header_lines = [
        f"# {episode_title}", "", f"**Podcast:** {podcast_title}",
        f"**Source:** {source_url}",
    ]
    if row.get("published_at"):
        header_lines.append(f"**Published:** {row['published_at']}")
    header_lines.append("")
    for seq, segment in enumerate(segments):
        deep_link = _source_deep_link(source_url, segment["start"])
        transcript_citations.append({
            "kind": "transcript_chunk", "seq": seq,
            "timestamp_start": segment["start"],
            "timestamp_end": segment["end"], "text": segment["text"],
            "file_path": None, "youtube_deep_link": None,
            "source_url": source_url, "source_deep_link": deep_link,
            "speaker": segment.get("speaker"),
        })

    existing = idx.get_yoink(video_id)
    # AS-06: the shortened corpus id is not the identity. Refuse to write over
    # a row that carries another feed/GUID, and persist the full identity
    # (normalized feed URL, GUID, capture key) with this publication.
    _check_corpus_identity(idx, existing, row, video_id)
    # BC-2: the publication ownership fence is minted before the snapshot is
    # built and carried through settlement; a publication that started
    # against an older base refuses revision_unavailable before any file.
    import library_media as _media_fence  # noqa: WPS433 -- lazy: keeps module import graph unchanged
    ticket = (idx.begin_media_publication(video_id, folder=folder)
              if _media_fence.schema_ready(idx._conn) else None)
    feed_key, guid, capture_key = _episode_full_identity(row)
    captured_at = (existing or {}).get("yoinked_at") or _now_iso()
    record = {
        "video_id": video_id, "slug": folder.name,
        "channel": podcast_title, "author": podcast_title,
        "title": episode_title, "topic": "Uncategorized",
        "hook_type": None, "yoinked_at": captured_at,
        "corpus_path": str(corpus_path), "sidecar_path": str(sidecar_path),
        "health_score_json": None,
        "metadata_json": json.dumps({
            "url": source_url, "platform": "podcast",
            "content_type": "episode",
            "duration_seconds": row.get("duration_seconds"),
            "upload_date": row.get("published_at"),
            "podcast_title": podcast_title,
            "episode_id": episode_id,
            # AS-06: full identity provenance behind the shortened corpus id.
            "feed_url": feed_key,
            "guid": guid,
            "capture_key": capture_key,
        }, ensure_ascii=False),
        "schema_version": 2, "source_type": "episode",
        "platform": "podcast",
    }

    # Phase 6 (phase6-v1, BC-2): build the media snapshot from the already-
    # loaded transcript only (no fetch, no model) and render the transcript
    # section with the shared media renderer. The block's annotations do not
    # depend on the corpus bytes, so a provisional block renders the Markdown,
    # and the sealed block then binds the final corpus/source revisions. The
    # podcast adapter supplies no chapters, and no media-fragment player path
    # is verified, so playback records kind "none" with a null seek URL.
    import clips as _clips_mod  # noqa: WPS433 -- lazy: keeps module import graph unchanged
    import library_cards as _cards_mod  # noqa: WPS433
    import library_media as _media_mod  # noqa: WPS433
    import library_resources as _resources_mod  # noqa: WPS433
    media_item = dict(record, url=source_url)
    playback = {"source_url": _resources_mod.safe_url(source_url),
                "seek_url": None, "seek_kind": "none"}
    provisional, _ = _media_mod.transcript_snapshot(
        video_id=video_id, source_revision="0" * 64, cues=transcript_citations,
        transcript=transcript_raw, transcript_bytes=transcript_bytes,
        corpus_revision="0" * 64, playback=playback)
    markdown = "\n".join(header_lines) + "\n" + _media_mod.render_markdown(
        media_item, transcript_citations, chapters=[], annotations=provisional)
    corpus_bytes = markdown.encode("utf-8")
    corpus_head = corpus_bytes[:_cards_mod.CORPUS_READ_BYTES].decode("utf-8", "replace")
    source_revision = _cards_mod.build_card(
        media_item, _clips_mod.merge_cues(transcript_citations, media_item),
        corpus_text=corpus_head)["source_revision"]
    media_block, media_artifact = _media_mod.transcript_snapshot(
        video_id=video_id, source_revision=source_revision, cues=transcript_citations,
        transcript=transcript_raw, transcript_bytes=transcript_bytes,
        corpus_revision=hashlib.sha256(corpus_bytes).hexdigest(), playback=playback)
    sidecar_transcript = []
    for citation, annotation in zip(transcript_citations, media_block["cues"]):
        citation["speaker"] = annotation["speaker"]
        citation["speaker_provenance_json"] = (
            _media_mod.canonical_json(annotation["speaker_provenance"])
            if annotation["speaker_provenance"] is not None else None)
        sidecar_transcript.append({
            "start": citation["timestamp_start"], "end": citation["timestamp_end"],
            "text": citation["text"], "speaker": annotation["speaker"],
            "speaker_provenance": annotation["speaker_provenance"],
            "source_url": citation["source_url"],
            "source_deep_link": citation["source_deep_link"],
            "youtube_deep_link": None,
        })
    sidecar = {
        "schema_version": 2,
        "video_id": video_id,
        "slug": folder.name,
        "source_type": "episode",
        "platform": "podcast",
        "url": source_url,
        "source_url": source_url,
        "feed_url": feed_key,
        "guid": guid,
        "capture_key": capture_key,
        "podcast_title": podcast_title,
        "episode_title": episode_title,
        "title": episode_title,
        "channel": podcast_title,
        "author": podcast_title,
        # RSS core metadata identifies the show, not necessarily its host.
        # Keep the dashboard field explicit and null instead of presenting
        # the show title as a person.
        "host": None,
        "duration_seconds": row.get("duration_seconds"),
        "published_at": row.get("published_at"),
        "upload_date": row.get("published_at"),
        "yoinked_at": captured_at,
        "transcript_model": (
            row.get("transcript_model_used") or transcript_raw.get("model")),
        "language": transcript_raw.get("language"),
        # Phase 6: this OR remains a compatibility projection only; readers
        # inspect media_depth.diarization_state and the run records instead.
        "diarization_ran": bool(
            row.get("diarization_ran") or transcript_raw.get("diarization_ran")),
        "speakers": speakers,
        "transcript": sidecar_transcript,
        "media_depth": media_block,
    }
    sidecar_bytes = (json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if _media_mod.schema_ready(idx._conn):
        # BC-2: one complete publication operation. The ownership ticket was
        # minted before this build; the item row is upserted first (the
        # publisher binds against it) and the legacy citation write keeps
        # the Phase 3 durability seam (row-before-citations) in place; then
        # the fenced publisher replaces the owned artifact, corpus and
        # sidecar (sidecar last), commits the citation/media/clip rows
        # together, prunes obsolete owned inputs and invalidates Phase 2
        # work. Retry replays the same inputs.
        idx.upsert_yoink(record, content=markdown)
        idx.insert_citations(video_id, transcript_citations)
        idx.publish_media_snapshot(
            video_id, cues=transcript_citations, media_block=media_block,
            artifacts={
                str(folder / _media_mod.MEDIA_INPUTS_DIR
                    / (hashlib.sha256(media_artifact).hexdigest() + ".json")): media_artifact,
                str(corpus_path): corpus_bytes,
                str(sidecar_path): sidecar_bytes,
            },
            ticket=ticket)
    else:
        # Legacy schema (migration 0030 absent): the pre-Phase 6 file-then-
        # rows sequence; no media snapshot can be materialized.
        _media_mod.archive_artifact(folder, media_artifact)
        _atomic_write(corpus_path, markdown)
        _atomic_write(sidecar_path, sidecar_bytes.decode("utf-8"))
        idx.upsert_yoink(record, content=markdown)
        idx.insert_citations(video_id, transcript_citations)
    _link_episode_to_yoink(idx, episode_id, video_id)
    return {
        "ok": True, "episode_id": episode_id, "video_id": video_id,
        "slug": folder.name, "corpus_path": str(corpus_path),
        "sidecar_path": str(sidecar_path), "source_url": source_url,
        "citations": len(transcript_citations), "segments": len(segments),
        "speakers": speakers,
        "source_revision": source_revision,
        "media_revision": media_block["media_revision"],
    }


def reconcile_episode_corpus_links(
        idx, *, data_root: Path, repair: bool = False) -> dict:
    """Find podcast corpus rows whose source episode lacks its completion link.

    The deterministic episode video ID lets this detect the narrow crash window
    after corpus upsert but before ``yoink_video_id`` is stored. With ``repair``
    enabled, the normal idempotent bridge is run again for every loadable item.
    """
    corpus_ids = {
        str(row["video_id"])
        for row in idx._conn.execute(
            "SELECT video_id FROM yoinks "
            "WHERE platform='podcast' AND source_type='episode'"
        ).fetchall()
    }
    episode_rows = idx._conn.execute(
        "SELECT e.*, f.feed_url, f.title AS podcast_title, "
        "f.homepage AS podcast_homepage "
        "FROM podcast_episodes e JOIN podcast_feeds f ON f.id=e.feed_id "
        "WHERE e.yoink_video_id IS NULL ORDER BY e.id"
    ).fetchall()
    items: list[dict] = []
    repaired = 0
    for raw in episode_rows:
        episode = dict(raw)
        video_id, _suffix = _episode_corpus_id(episode)
        if video_id not in corpus_ids:
            continue
        transcript_path = episode.get("transcript_local_path")
        repairable = False
        reason = None
        if not transcript_path:
            reason = "episode has no transcript_local_path"
        else:
            try:
                _load_transcript(Path(transcript_path))
                repairable = True
            except (FileNotFoundError, ValueError) as exc:
                reason = str(exc)
        item = {
            "episode_id": int(episode["id"]),
            "video_id": video_id,
            "title": episode.get("title") or "Untitled episode",
            "transcript_status": episode.get("transcript_status"),
            "repairable": repairable,
            "repaired": False,
            "error": reason,
        }
        if repair and repairable:
            try:
                result = episode_to_corpus(
                    idx, int(episode["id"]), data_root=Path(data_root))
                item["repaired"] = True
                item["result"] = result
                repaired += 1
            except Exception as exc:  # report every repair failure to doctor
                item["error"] = f"{type(exc).__name__}: {exc}"
        items.append(item)
    remaining = len(items) - repaired
    return {
        "ok": remaining == 0,
        "checked": len(corpus_ids),
        "orphaned": len(items),
        "repairable": sum(1 for item in items if item["repairable"]),
        "repaired": repaired,
        "remaining": remaining,
        "repair_command": "python server.py --reconcile-podcast-corpus",
        "items": items,
    }


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
    with idx.write_transaction() as conn:
        conn.execute(
            "UPDATE podcast_episodes SET "
            "  audio_local_path = COALESCE(?, audio_local_path), "
            "  audio_downloaded_at = ?, "
            "  audio_size_bytes = COALESCE(?, audio_size_bytes), "
            "  audio_download_error = ?, "
            "  status = ? "
            "WHERE id = ?",
            (local_path, _now_iso() if local_path else None,
             size_bytes, error, status, episode_id))


def _is_http_url(value) -> bool:
    """True only for absolute http:// or https:// URLs with a host."""
    try:
        parts = urlparse(str(value or ""))
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


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
    # SEC-01 (security review 2026-09-04): the enclosure URL is attacker-
    # controlled feed content. Only http(s) may reach yt-dlp, and it always
    # follows a "--" so it can never be parsed as an option (e.g. --exec).
    if not _is_http_url(episode["audio_url"]):
        _record_audio_result(idx, episode_id, local_path=None, size_bytes=0,
                             error="audio_url is not an http(s) URL",
                             status="error")
        return {"ok": False, "error": "audio_url is not an http(s) URL"}

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
        set_episode_status(idx, episode_id, EPISODE_STATUS_QUEUED)

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
        "--",
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
