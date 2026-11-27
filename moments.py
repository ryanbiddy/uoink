"""Local YouTube pins and playback links for cited transcript lines."""
import math
import re
import sqlite3
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit


def citation_link(url, start, *, youtube=False, lead=2):
    """Build from the stored start every time, including for an older saved URL."""
    try:
        second = max(0, math.floor(float(start)) - lead)
    except (ValueError, TypeError, OverflowError):
        second = 0
    if not youtube:
        return f"{url.split('#', 1)[0]}#t={second}"
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k not in ("t", "start")]
    return urlunsplit(parts._replace(query=urlencode([*query, ("t", f"{second}s")]), fragment=""))


def cited_url(link, start, *, lead=2):
    """Retarget known timed links. Preserve opaque publisher links and untimed cues."""
    if not isinstance(link, str) or start is None:
        return link
    try:
        parts = urlsplit(link)
        if parts.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
            if {"t", "start"} & parse_qs(parts.query).keys():
                return citation_link(link, start, youtube=True, lead=lead)
        if re.fullmatch(r"t=\d+(?:\.\d+)?s?", parts.fragment):
            return citation_link(link, start, lead=lead)
    except ValueError:
        pass
    return link


def export_links(markdown):
    """Refresh generated transcript headings in an older saved Markdown export."""
    if "## Transcript" not in markdown or "### [" not in markdown:
        return markdown
    def retime(match):
        h, m, s = match.group(2, 3, 4)
        start = int(h) * 3600 + int(m) * 60 + int(s)
        return match[1] + cited_url(match[5], start) + ")"
    sections = re.split(r"(?m)(^## [^\n]+$)", markdown)
    for index in range(1, len(sections), 2):
        if sections[index].strip() == "## Transcript":
            sections[index + 1] = re.sub(
                r"(?m)^(### \[(\d+):(\d\d):(\d\d)\.\d{3}–\d+:\d\d:\d\d\.\d{3}\]\()"
                r"(https?://[^)\s]+)\)", retime, sections[index + 1])
    return "".join(sections)


def requested_time(url):
    """Parse explicit YouTube t/start values after the caller validated the video."""
    query = parse_qs(urlsplit(url).query)
    for key in ("t", "start"):
        value = (query.get(key) or [""])[0]
        if not value or len(value) > 16:
            continue
        match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?", value)
        if match:
            h, m, s = (int(part or 0) for part in match.groups())
            seconds = h * 3600 + m * 60 + s
            if seconds <= 2147483647:
                return seconds
    return None


def add(idx, video_id, seconds, *, pending_id=None):
    with idx._lock, idx._conn as db:
        # Re-pinning takes the new row's place in eviction order, keeping the
        # original pin date, note and ownership. A cancelled job cannot add a pin.
        write = db.execute("""
            INSERT OR IGNORE INTO item_moments(video_id, seconds, pending_id)
            SELECT :video_id, :seconds, CASE WHEN EXISTS (
                SELECT 1 FROM yoinks WHERE video_id=:video_id
            ) THEN NULL ELSE :pending_id END
            WHERE :pending_id IS NULL OR EXISTS (
                SELECT 1 FROM pending_yoinks WHERE pending_id=:pending_id AND status!='cancelled'
            )
            ON CONFLICT(video_id, seconds) DO UPDATE SET rowid=excluded.rowid
        """, {"video_id": video_id, "seconds": seconds, "pending_id": pending_id})
        if write.rowcount == 0:
            return {}
        db.execute("DELETE FROM item_moments WHERE video_id=? AND rowid NOT IN "
                   "(SELECT rowid FROM item_moments WHERE video_id=? ORDER BY rowid DESC LIMIT 20)",
                   (video_id, video_id))
    return {"pinned_seconds": seconds}


def remove(idx, video_id, seconds):
    with idx._lock, idx._conn as db:
        db.execute("DELETE FROM item_moments WHERE video_id=? AND seconds=?", (video_id, seconds))


def pending_capture(idx, url):
    with idx._lock:
        row = idx._conn.execute(
            "SELECT pending_id, retry_after FROM pending_yoinks WHERE url=? "
            "AND status IN ('pending','running','publishing') ORDER BY pending_id LIMIT 1", (url,)
        ).fetchone()
        return dict(row) if row else None


def for_item(idx, video_id):
    """Overlapping cues within 45 seconds. Quoting begins at the first included line."""
    with idx._lock:
        db = idx._conn
        try:
            pins = [dict(row) for row in db.execute(
                "SELECT seconds, pinned_at, note FROM item_moments WHERE video_id=? ORDER BY seconds",
                (video_id,))]
        except sqlite3.OperationalError as error:
            if str(error) == "no such table: item_moments":
                return []  # A read-only agent opened a library from before migration 0041.
            raise
        if not pins:
            return []
        ready = bool(db.execute("SELECT 1 FROM citations WHERE video_id=? AND kind='transcript_chunk' "
                                "AND timestamp_start IS NOT NULL AND text<>'' LIMIT 1", (video_id,)).fetchone())
        for pin in pins:
            second = pin["seconds"]
            lines = [dict(row) for row in db.execute(
                "SELECT timestamp_start AS start, timestamp_end AS end, text FROM citations "
                "WHERE video_id=? AND kind='transcript_chunk' AND timestamp_start<=? "
                "AND coalesce(timestamp_end,timestamp_start)>=? AND text<>'' ORDER BY timestamp_start,seq",
                (video_id, second + 45, second - 45))]
            pin.update(lines=lines, transcript_ready=ready, deep_link=citation_link(
                f"https://youtube.com/watch?v={video_id}", lines[0]["start"] if lines else second,
                youtube=True, lead=2 if lines else 0))
    return pins
