"""v3.1 mobile -> desktop playlist bridge.

Per PROMPT-V3.1-FULL-BUILD-PLAN.md track C (net-new Ryan-requested
feature). User creates a designated YouTube playlist on mobile, adds
videos one-tap, helper polls + diffs + auto-queues the unseen ones.

Compute policy (locked):
- No model. Pure yt-dlp playlist listing + set diff.
- Outbound: yt-dlp --flat-playlist --dump-single-json against the
  playlist URL. Same posture as the existing yt-dlp YouTube extraction.
- The actual extraction of each new video is delegated to the existing
  pending_yoinks retry worker (with retry_after = now) so it processes
  alongside the regular queue -- no separate threadpool.

This module owns no transport; server.py wraps it with HTTP +
uoink_mcp_tools.py wraps it with MCP."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from typing import Any

log = logging.getLogger("uoink.mobile_playlists")

# Status flow on the per-discovery log rows.
EVENT_DISCOVERED = "discovered"
EVENT_QUEUED = "queued"
EVENT_EXTRACTED = "extracted"
EVENT_FAILED = "failed"
_EVENT_STATUSES = (EVENT_DISCOVERED, EVENT_QUEUED,
                    EVENT_EXTRACTED, EVENT_FAILED)

# Polite per-call yt-dlp timeout. Most playlists are <100 videos -- a
# --flat-playlist call returns in a couple of seconds.
_PLAYLIST_LIST_TIMEOUT_SEC = 30

# Cap how many "new" videos we surface per poll. Protects against a
# user pasting a 5,000-episode playlist URL by accident.
_NEW_VIDEOS_PER_POLL_CAP = 50


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# ---- registry CRUD -----------------------------------------------------
def add_playlist(idx, playlist_url: str, *,
                  name: str | None = None,
                  poll_interval_min: int = 5,
                  normalize_playlist_url) -> dict:
    """Insert + return a fresh playlist row. UNIQUE constraint on
    playlist_url makes the call idempotent -- re-adding the same URL
    returns the existing row.

    `normalize_playlist_url` is a callable injected by server.py
    (typically server._normalize_playlist_url) so this module avoids a
    server-import cycle. Returns None on invalid input -> raises
    ValueError."""
    canonical = normalize_playlist_url(playlist_url)
    if not canonical:
        raise ValueError("playlist_url must be a valid youtube playlist URL")
    interval = max(1, min(int(poll_interval_min or 5), 1440))
    with idx._lock:
        cur = idx._conn.execute(
            "INSERT OR IGNORE INTO monitored_playlists "
            "(playlist_url, name, poll_interval_min, added_at) "
            "VALUES (?, ?, ?, ?)",
            (canonical, name, interval, _now_iso()))
        if cur.rowcount == 0:
            row = idx._conn.execute(
                "SELECT * FROM monitored_playlists WHERE playlist_url=?",
                (canonical,)).fetchone()
            return _shape_row(dict(row)) if row else {}
        playlist_id = cur.lastrowid
    return get_playlist(idx, playlist_id) or {}


def get_playlist(idx, playlist_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM monitored_playlists WHERE id=?",
        (playlist_id,)).fetchone()
    return _shape_row(dict(row)) if row else None


def list_playlists(idx, *, enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM monitored_playlists"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY added_at DESC"
    rows = idx._conn.execute(sql).fetchall()
    return [_shape_row(dict(r)) for r in rows]


def remove_playlist(idx, playlist_id: int) -> bool:
    with idx._lock:
        cur = idx._conn.execute(
            "DELETE FROM monitored_playlists WHERE id=?", (playlist_id,))
        return cur.rowcount > 0


def set_playlist_enabled(idx, playlist_id: int, enabled: bool) -> bool:
    with idx._lock:
        cur = idx._conn.execute(
            "UPDATE monitored_playlists SET enabled=? WHERE id=?",
            (1 if enabled else 0, playlist_id))
        return cur.rowcount > 0


def _shape_row(row: dict) -> dict:
    """Convert SQLite row to API shape (deserialise JSON, normalise
    enabled to bool, etc.)."""
    try:
        row["last_seen_video_ids"] = json.loads(
            row.get("last_seen_video_ids") or "[]")
    except (json.JSONDecodeError, TypeError):
        row["last_seen_video_ids"] = []
    row["seen_count"] = len(row["last_seen_video_ids"])
    row["enabled"] = bool(row.get("enabled"))
    return row


# ---- poll a single playlist --------------------------------------------
def _fetch_playlist_video_ids(playlist_url: str, *,
                                ytdlp_cmd: list[str]) -> list[dict]:
    """yt-dlp --flat-playlist returns one JSON line per entry. We only
    need (id, title). --skip-download is a no-op for --flat-playlist
    but we set it explicitly so a future yt-dlp doesn't change its
    default extractor behaviour on us."""
    if not ytdlp_cmd:
        raise RuntimeError("yt-dlp command not configured")
    args = list(ytdlp_cmd) + [
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--skip-download",
        playlist_url,
    ]
    cp = subprocess.run(
        args, capture_output=True, text=True,
        timeout=_PLAYLIST_LIST_TIMEOUT_SEC, check=False,
        encoding="utf-8", errors="replace",
    )
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "yt-dlp failed").strip()[-512:]
        raise RuntimeError(err)
    entries: list[dict] = []
    for line in (cp.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid = entry.get("id")
        if vid:
            entries.append({"video_id": vid,
                              "title": entry.get("title")})
    return entries


def poll_playlist(idx, playlist_id: int, *,
                   ytdlp_cmd: list[str] | None = None,
                   normalize_video_to_canonical_url=None) -> dict:
    """Fetch + diff + record the new entries. Returns:
        {ok, playlist_id, new[{video_id, title, canonical_url}], seen_count,
         total_in_playlist, enqueued[]}

    Does NOT itself call /extract -- it records the discovery events
    and (optionally) registers each new video to pending_yoinks via the
    injected `normalize_video_to_canonical_url` so the existing retry
    worker picks it up next tick. Decoupling here keeps the polling
    cheap + lets the dashboard's Activity tab show the pre-queue
    "discovered" state.

    Injection rationale (same shape as add_playlist): the canonical
    URL helper lives in server.py; importing it from this module would
    create a server -> mobile_playlists -> server cycle. The endpoint
    handler wires the dependency at call-time."""
    pl = get_playlist(idx, playlist_id)
    if pl is None:
        return {"ok": False, "error": f"playlist not found: {playlist_id}"}
    if not pl.get("enabled"):
        return {"ok": True, "playlist_id": playlist_id, "skipped": "disabled"}

    if not ytdlp_cmd:
        try:
            import server as _server  # lazy
            ytdlp_cmd = list(getattr(_server, "YTDLP_CMD", []))
        except Exception:
            ytdlp_cmd = []

    try:
        entries = _fetch_playlist_video_ids(pl["playlist_url"],
                                              ytdlp_cmd=ytdlp_cmd)
    except Exception as e:
        log.warning("playlist poll failed (%s): %s", pl["playlist_url"], e)
        _record_poll_failure(idx, playlist_id, str(e))
        return {"ok": False, "playlist_id": playlist_id, "error": str(e)}

    seen = set(pl.get("last_seen_video_ids") or [])
    new_entries = [e for e in entries
                    if e["video_id"] not in seen][:_NEW_VIDEOS_PER_POLL_CAP]
    all_ids = [e["video_id"] for e in entries]

    enqueued: list[dict] = []
    now = _now_iso()
    with idx._lock:
        for e in new_entries:
            canonical = None
            pending_id = None
            if callable(normalize_video_to_canonical_url):
                try:
                    canonical = normalize_video_to_canonical_url(
                        e["video_id"])
                except Exception:
                    canonical = None
                if canonical:
                    try:
                        # Enqueue with retry_after = now so the retry
                        # worker picks it up next tick. The existing
                        # queue infrastructure handles the actual
                        # extraction; we just register the URL.
                        pending_id = idx.enqueue_pending(
                            canonical, 30, _now_iso())
                    except Exception as enq_err:
                        log.warning(
                            "mobile playlist enqueue failed: %s", enq_err)
                        pending_id = None
            # Always record the discovery event, even if enqueue failed
            # so the dashboard can show it + the user can retry manually.
            cur = idx._conn.execute(
                "INSERT INTO mobile_queue_events "
                "(playlist_id, video_id, video_title, discovered_at, "
                " status, pending_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (playlist_id, e["video_id"], e.get("title"), now,
                 EVENT_QUEUED if pending_id else EVENT_DISCOVERED,
                 pending_id))
            enqueued.append({
                "event_id": cur.lastrowid,
                "video_id": e["video_id"],
                "title": e.get("title"),
                "canonical_url": canonical,
                "pending_id": pending_id,
                "status": EVENT_QUEUED if pending_id else EVENT_DISCOVERED,
            })
        # Update the rolling state on the playlist row.
        idx._conn.execute(
            "UPDATE monitored_playlists SET "
            "  last_polled_at = ?, "
            "  last_seen_video_ids = ?, "
            "  error_count = 0, "
            "  last_error = NULL "
            "WHERE id = ?",
            (now, json.dumps(all_ids), playlist_id))
    return {
        "ok": True,
        "playlist_id": playlist_id,
        "playlist_url": pl["playlist_url"],
        "new": enqueued,
        "seen_count": len(seen),
        "total_in_playlist": len(all_ids),
    }


def _record_poll_failure(idx, playlist_id: int, error: str) -> None:
    with idx._lock:
        idx._conn.execute(
            "UPDATE monitored_playlists SET "
            "  last_polled_at = ?, "
            "  error_count = error_count + 1, "
            "  last_error = ? "
            "WHERE id = ?",
            (_now_iso(), error[:512], playlist_id))


# ---- queue event read paths --------------------------------------------
def list_events(idx, *, playlist_id: int | None = None,
                  status: str | None = None,
                  limit: int = 200) -> list[dict]:
    wheres: list[str] = []
    params: list = []
    if playlist_id is not None:
        wheres.append("playlist_id=?")
        params.append(playlist_id)
    if status is not None:
        if status not in _EVENT_STATUSES:
            raise ValueError(
                f"status must be one of {list(_EVENT_STATUSES)}")
        wheres.append("status=?")
        params.append(status)
    where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
    params.append(max(1, min(int(limit), 1000)))
    rows = idx._conn.execute(
        "SELECT * FROM mobile_queue_events" + where_sql +
        " ORDER BY discovered_at DESC LIMIT ?",
        params).fetchall()
    return [dict(r) for r in rows]
