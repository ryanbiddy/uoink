"""v2.5 P3 your-channel mode.

Multi-channel registry + verification + self-recognition + self-analysis.

Recognition is name-based (case-insensitive). The `user_channels` table
stores both a `handle` (the @handle or channel id, normalised) and a
`name` (the display name). A yoink's `channel` (text from the corpus
extraction) is matched against `user_channels.name` or `user_channels.handle`
(with the leading @ stripped). On match we insert a row into the v2.5
`yoink_tags` table with tag = 'is_self', source = 'auto' so the self
view can use the same tag plumbing as any other facet filter.

Verification is the only new outbound surface in this PR -- a single
plain GET to `https://www.youtube.com/@<handle>` or `/channel/<id>`. It
is explicitly enumerated in the v2.5 substrate prompt as permitted
YouTube traffic, parses only the public <title> tag, and never sends an
Anthropic call. The verifier sets `verified_at` + canonicalised `name`
on success and is a no-op (returns ok=False) if the network is
unavailable -- the channel row still exists, just without `verified_at`.

This module is transport-agnostic. server.py drives the HTTP surface
and uoink_mcp_tools.py drives the MCP surface."""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from datetime import datetime

log = logging.getLogger("uoink.channels")

# YouTube's HTML <title> tag for a channel page looks like:
#   <title>Channel Name - YouTube</title>
# We grab the first <title>...</title>, trim the trailing " - YouTube",
# and call that the canonical name. Tolerates extra whitespace.
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_USER_AGENT = "Mozilla/5.0 (Uoink/2.5 channel-verify)"
_VERIFY_TIMEOUT = 6.0  # seconds; intentionally short

# Outbound URL templates. Order matters: try the handle form first since
# it is the modern @handle that most user channels use; fall back to the
# /channel/<id> form for users who paste an id straight from the URL bar.
_HANDLE_URL = "https://www.youtube.com/@{handle}"
_CHANNEL_URL = "https://www.youtube.com/channel/{id}"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _normalise_handle(raw: str) -> str:
    """Strip leading @, whitespace, and any URL prefix. Keeps everything
    else verbatim because handles can contain dots, underscores, and
    digits and we do not want to over-sanitise."""
    if not raw:
        return ""
    h = raw.strip()
    if h.startswith("https://") or h.startswith("http://"):
        # User pasted a full URL -- pull the last path segment.
        h = h.rstrip("/").rsplit("/", 1)[-1]
    if h.startswith("@"):
        h = h[1:]
    return h.strip()


# ---- index helpers (user_channels table) ----------------------------------
def list_channels(idx) -> list[dict]:
    rows = idx._conn.execute(
        "SELECT handle, channel_id, name, added_at, verified_at "
        "FROM user_channels ORDER BY added_at").fetchall()
    return [dict(r) for r in rows]


def add_channel(idx, handle: str, *, name: str | None = None,
                channel_id: str | None = None) -> dict:
    handle = _normalise_handle(handle)
    if not handle:
        raise ValueError("handle required")
    with idx._lock:
        idx._conn.execute(
            "INSERT INTO user_channels (handle, channel_id, name, added_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(handle) DO UPDATE SET "
            "  channel_id = COALESCE(excluded.channel_id, user_channels.channel_id), "
            "  name       = COALESCE(excluded.name, user_channels.name)",
            (handle, channel_id, name, _now_iso()))
    return get_channel(idx, handle) or {}


def remove_channel(idx, handle: str) -> bool:
    handle = _normalise_handle(handle)
    with idx._lock:
        cur = idx._conn.execute(
            "DELETE FROM user_channels WHERE lower(handle) = lower(?)",
            (handle,))
        return cur.rowcount > 0


def get_channel(idx, handle: str) -> dict | None:
    """Case-insensitive lookup -- handles are stored verbatim (so users
    keep their preferred capitalisation) but matched case-insensitively
    because YouTube treats handles that way."""
    handle = _normalise_handle(handle)
    row = idx._conn.execute(
        "SELECT handle, channel_id, name, added_at, verified_at "
        "FROM user_channels WHERE lower(handle) = lower(?)",
        (handle,)).fetchone()
    return dict(row) if row else None


def set_verified(idx, handle: str, *, channel_id: str | None,
                  name: str | None) -> None:
    handle = _normalise_handle(handle)
    with idx._lock:
        idx._conn.execute(
            "UPDATE user_channels "
            "SET channel_id = COALESCE(?, channel_id), "
            "    name       = COALESCE(?, name), "
            "    verified_at = ? "
            "WHERE lower(handle) = lower(?)",
            (channel_id, name, _now_iso(), handle))


# ---- verification (the one outbound call) ---------------------------------
def fetch_channel_name(handle: str, *,
                       channel_id: str | None = None) -> dict:
    """Hit YouTube's public channel page, parse the <title>, return the
    canonical display name. Returns {ok, name?, source_url?, error?}.

    No Anthropic, no extra headers beyond a UA string. The handle form is
    tried first; the /channel/<id> form is the fallback when caller passed
    an id."""
    targets = []
    h = _normalise_handle(handle)
    if h:
        targets.append(_HANDLE_URL.format(handle=h))
    if channel_id:
        targets.append(_CHANNEL_URL.format(id=channel_id))
    if not targets:
        return {"ok": False, "error": "handle or channel_id required"}
    last_err = None
    for url in targets:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=_VERIFY_TIMEOUT) as resp:
                if resp.status != 200:
                    last_err = f"HTTP {resp.status} for {url}"
                    continue
                # Channel pages are large (~hundreds of KB) -- read only
                # enough bytes to span the <title> tag.
                blob = resp.read(65536).decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            last_err = str(e)
            continue
        except Exception as e:
            last_err = str(e)
            continue
        m = _TITLE_RE.search(blob)
        if not m:
            last_err = f"no <title> in {url}"
            continue
        title = m.group(1).strip()
        # Strip the trailing " - YouTube" YouTube appends to every page.
        if title.lower().endswith("- youtube"):
            title = title[: -len("- youtube")].strip()
        if not title:
            last_err = f"empty <title> in {url}"
            continue
        return {"ok": True, "name": title, "source_url": url}
    return {"ok": False, "error": last_err or "no verification target"}


def verify_channel(idx, handle: str) -> dict:
    """Fetch the public channel page + persist verified_at/name. Returns
    the up-to-date row + {ok, verified}."""
    row = get_channel(idx, handle)
    if row is None:
        return {"ok": False, "error": "channel not in registry"}
    fetched = fetch_channel_name(row["handle"], channel_id=row.get("channel_id"))
    if not fetched.get("ok"):
        return {"ok": False, "error": fetched.get("error", "fetch failed"),
                "channel": row}
    set_verified(idx, row["handle"], channel_id=row.get("channel_id"),
                 name=fetched["name"])
    return {"ok": True, "verified": True, "channel": get_channel(idx, row["handle"]),
            "fetched_name": fetched["name"]}


# ---- recognition + self-tagging -------------------------------------------
def is_self_channel(idx, channel_name: str | None) -> bool:
    """True iff the yoink's channel text matches any user_channels row by
    name OR by handle (both case-insensitive)."""
    if not channel_name:
        return False
    name = channel_name.strip()
    if not name:
        return False
    row = idx._conn.execute(
        "SELECT 1 FROM user_channels "
        "WHERE name IS NOT NULL AND lower(name) = lower(?) "
        "   OR lower(handle) = lower(?) "
        "   OR lower(handle) = lower(?) "
        "LIMIT 1",
        (name, name, name.lstrip("@"))).fetchone()
    return row is not None


def tag_if_self(idx, video_id: str, channel_name: str | None) -> bool:
    """Insert ('is_self', source='auto') into yoink_tags if the video's
    channel matches a user_channels entry. Returns True iff a NEW row was
    inserted (so callers can count fresh tags vs no-ops on backfills)."""
    if not is_self_channel(idx, channel_name):
        return False
    with idx._lock:
        cur = idx._conn.execute(
            "INSERT OR IGNORE INTO yoink_tags (video_id, tag, source, added_at) "
            "VALUES (?, 'is_self', 'auto', ?)",
            (video_id, _now_iso()))
        return cur.rowcount > 0


def recognize_now(idx) -> dict:
    """Backfill: scan every yoink, tag any whose channel matches a user
    channel. Returns counts. Cheap enough to run on demand because both
    user_channels and yoinks are small."""
    rows = idx._conn.execute(
        "SELECT video_id, channel FROM yoinks WHERE deleted_at IS NULL"
    ).fetchall()
    tagged = 0
    for r in rows:
        if tag_if_self(idx, r["video_id"], r["channel"]):
            tagged += 1
    return {"ok": True, "scanned": len(rows), "tagged": tagged}


# ---- self analysis --------------------------------------------------------
def _yoinked_month(ts: str | None) -> str:
    """Bucket a yoinked_at ISO timestamp to YYYY-MM. Falls back to 'unknown'
    so a missing field is visible in the histogram rather than skipped."""
    if not ts:
        return "unknown"
    try:
        return ts[:7]
    except Exception:
        return "unknown"


def self_yoink_rows(idx) -> list[dict]:
    """Pull every yoink the user owns (tagged is_self), newest first."""
    rows = idx._conn.execute(
        "SELECT y.* FROM yoinks y "
        "JOIN yoink_tags t ON t.video_id = y.video_id "
        "WHERE t.tag = 'is_self' AND y.deleted_at IS NULL "
        "ORDER BY y.yoinked_at DESC NULLS LAST"
    ).fetchall()
    return [dict(r) for r in rows]


def self_analysis(idx, *, handle: str | None = None,
                   top_n: int = 10) -> dict:
    """Aggregate self-tagged yoinks into:

      hook_evolution        {hook_type: {YYYY-MM: count}}
      format_evolution      {format: {YYYY-MM: count}}    (S1 facet)
      performance_trend     {YYYY-MM: {over: n, average: n, under: n}}
      top_performers        [{video_id, title, views, performance_tier, ...}]
      summary               {total, channels, verified_count}

    `handle` filters to one channel if the caller wants a single-channel
    view; default is the union of all user channels."""
    rows = self_yoink_rows(idx)
    if handle:
        target = handle.strip().lstrip("@").lower()
        ch = get_channel(idx, target)
        ch_name = (ch or {}).get("name")
        rows = [r for r in rows if r.get("channel") and
                ((ch_name and r["channel"].lower() == ch_name.lower()) or
                 r["channel"].lower() == target)]

    hook_evo: dict[str, dict[str, int]] = {}
    format_evo: dict[str, dict[str, int]] = {}
    perf_trend: dict[str, dict[str, int]] = {}
    channels: set[str] = set()
    for r in rows:
        if r.get("channel"):
            channels.add(r["channel"])
        month = _yoinked_month(r.get("yoinked_at"))
        hk = r.get("hook_type") or "unknown"
        hook_evo.setdefault(hk, {})[month] = hook_evo.setdefault(hk, {}).get(month, 0) + 1
        fmt = r.get("format") or "unknown"
        format_evo.setdefault(fmt, {})[month] = format_evo.setdefault(fmt, {}).get(month, 0) + 1
        tier = r.get("performance_tier") or "unknown"
        bucket = perf_trend.setdefault(month, {"over": 0, "average": 0,
                                                 "under": 0, "unknown": 0})
        bucket[tier] = bucket.get(tier, 0) + 1

    # Top performers: prefer rows with a numeric views column if it exists;
    # otherwise rank by performance_tier (over > average > under). Returning
    # the original row dicts (minus large bodies) keeps the dashboard's job
    # simple.
    def _views(r):
        try:
            return int(r.get("views") or 0)
        except (TypeError, ValueError):
            return 0
    _tier_rank = {"over": 3, "average": 2, "under": 1, "unknown": 0}
    sorted_rows = sorted(
        rows, key=lambda r: (_tier_rank.get(r.get("performance_tier") or "unknown", 0),
                              _views(r)), reverse=True)
    keep = ("video_id", "slug", "title", "channel", "yoinked_at",
             "hook_type", "format", "performance_tier", "views")
    top = [{k: r.get(k) for k in keep} for r in sorted_rows[:max(1, top_n)]]

    all_channels = list_channels(idx)
    return {
        "ok": True,
        "handle": handle,
        "summary": {
            "total": len(rows),
            "channels": sorted(channels),
            "registered_channels": len(all_channels),
            "verified_channels": sum(1 for c in all_channels if c.get("verified_at")),
        },
        "hook_evolution": hook_evo,
        "format_evolution": format_evo,
        "performance_trend": perf_trend,
        "top_performers": top,
    }
