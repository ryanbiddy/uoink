"""Clips -- the quotable unit of the living library (phase 1).

A *clip* is a merged, de-overlapped window of transcript cues derived from
the ``citations`` rows of kind ``transcript_chunk``. Raw caption cues are
tiny (~37 characters on the live corpus) and repeat the tail of the previous
cue, so as search hits and as evidence they are useless. This module turns
them into windows of at most 120 seconds where cue timing permits. Longer
single cues are split into bounded text excerpts with the original coarse
interval and source link; no word-level timestamps are invented.

Clips are derived data: ``build_clips_for_video`` deletes and re-derives a
video's clips from its citations, so a rebuild is deterministic and
idempotent. ``migrations/0024_clips.sql`` owns the schema; the ``clips_fts``
external-content table is kept in sync by triggers, so this module only
ever writes the ``clips`` table.

Offline by construction: standard library only, no network, no model.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import time

log = logging.getLogger("uoink.clips")

# Close a window once it is at least this long AND the cue that got it
# there ends a sentence ...
MIN_WINDOW_SECONDS = 45.0
# ... or once it is this long regardless of punctuation.
MAX_WINDOW_SECONDS = 120.0
MAX_COARSE_CHARS = 1200


def timing_kind(clip: dict) -> str:
    """Coarse intervals retain source bounds, including in legacy databases."""
    try:
        start, end = float(clip.get("start")), float(clip.get("end"))
        if not math.isfinite(start) or not math.isfinite(end):
            return "unknown"
        return "coarse" if end - start > MAX_WINDOW_SECONDS else "source_cues"
    except (TypeError, ValueError):
        return "unknown"


def _coarse_parts(text: str):
    """Contiguous, lossless slices, preferably at a word boundary."""
    while len(text) > MAX_COARSE_CHARS:
        cut = text.rfind(" ", 0, MAX_COARSE_CHARS + 1)
        cut = cut if cut > 0 else MAX_COARSE_CHARS
        yield text[:cut]
        text = text[cut:]
    if text:
        yield text

# YouTube caption tracks emit a ~10 ms echo of the previous cue's tail
# (seq 16 in the D_FCYsshMI4 sample: 19.91-19.92 s, text fully repeated).
# A cue this short that adds no new words is dropped outright.
_DUP_CUE_SECONDS = 0.05

# A cue whose start is more than this far *before* the previous cue's start
# is not a caption glitch; it is a stale track left behind by an earlier,
# longer extraction of the same video (see Index.insert_citations). Walking
# stops there so the stale cues never become duplicate clips.
_REWIND_TOLERANCE_SECONDS = 5.0

# How many trailing window words to compare against a new cue when looking
# for the overlap. Cues are short; 80 words is several cues of slack.
_OVERLAP_TAIL_WORDS = 80

_SENTENCE_END_RE = re.compile(r"""[.!?]["'”’)\]]*$""")
_WS_RE = re.compile(r"\s+")
_YOUTUBE_HOSTS = ("youtube.com/", "youtu.be/")


# --------------------------------------------------------------------------
# Text merging
# --------------------------------------------------------------------------
def normalize_text(text) -> str:
    """Collapse whitespace and trim. The only text normalisation clips do."""
    return _WS_RE.sub(" ", str(text or "")).strip()


def ends_sentence(text: str) -> bool:
    """True when the cue closes a sentence (. ! ? optionally followed by a
    closing quote or bracket)."""
    return bool(_SENTENCE_END_RE.search(text or ""))


def _key(word: str) -> str:
    return word.casefold()


def overlap_words(window_words: list[str], cue_words: list[str]) -> int:
    """Longest k such that the last k window words equal the first k cue
    words (case-insensitive, whole words only, so a window ending in "the"
    never swallows a cue starting with "theory")."""
    if not window_words or not cue_words:
        return 0
    tail = window_words[-_OVERLAP_TAIL_WORDS:]
    tail_keys = [_key(w) for w in tail]
    cue_keys = [_key(w) for w in cue_words]
    for k in range(min(len(tail_keys), len(cue_keys)), 0, -1):
        if tail_keys[-k:] == cue_keys[:k]:
            return k
    return 0


def _contained_in_tail(window_words: list[str], cue_words: list[str]) -> bool:
    """True when the cue is a contiguous run somewhere in the recent tail of
    the window (an echo that is not aligned to the very end). Cues under
    three words are never treated as echoes: "Yeah." said twice is speech."""
    if len(cue_words) < 3:
        return False
    span = min(len(window_words), 2 * len(cue_words) + 10)
    tail = [_key(w) for w in window_words[-span:]]
    needle = [_key(w) for w in cue_words]
    n = len(needle)
    for i in range(0, len(tail) - n + 1):
        if tail[i:i + n] == needle:
            return True
    return False


def new_words(window_words: list[str], cue_text) -> list[str]:
    """The words of ``cue_text`` that are not already at the end of the
    window. Empty when the cue only repeats what the window already says."""
    text = normalize_text(cue_text)
    if not text:
        return []
    cue_words = text.split(" ")
    if not window_words:
        return cue_words
    k = overlap_words(window_words, cue_words)
    if k == len(cue_words):
        return []
    if k == 0 and _contained_in_tail(window_words, cue_words):
        return []
    return cue_words[k:]


# --------------------------------------------------------------------------
# Deep links
# --------------------------------------------------------------------------
def _known_non_youtube(platform, url: str) -> bool:
    """True only when the item is positively not a YouTube video: a
    non-YouTube platform, or (platform unknown) a URL on another host. An
    item with neither is treated as YouTube, matching the pre-0020 default
    the citation writer used."""
    if platform:
        return platform != "youtube"
    return bool(url) and not any(host in url for host in _YOUTUBE_HOSTS)


def _deep_link(cue: dict, item: dict) -> str | None:
    """The clip's link: the first cue's source_deep_link when it is usable.

    Citations written before migration 0022 for non-YouTube videos (X posts
    in particular) carry either no source_deep_link or a fabricated
    ``youtube.com/watch?v=<status id>`` one. For those, rebuild the link
    from the item's real URL with the same ``#t=N`` convention the rest of
    the app uses for sources without a native timestamp form."""
    link = cue.get("source_deep_link")
    url = item.get("url") or ""
    non_youtube = _known_non_youtube(item.get("platform"), url)
    if isinstance(link, str) and link.strip():
        if not (non_youtube and "youtube.com/watch" in link):
            return link.strip()
    try:
        t = max(0, int(float(cue.get("timestamp_start") or 0)))
    except (TypeError, ValueError):
        t = 0
    if non_youtube:
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return f"{url.split('#', 1)[0]}#t={t}"
        return None
    return f"https://youtube.com/watch?v={item.get('video_id')}&t={t}s"


# --------------------------------------------------------------------------
# Windowing
# --------------------------------------------------------------------------
def merge_cues(cues: list[dict], item: dict | None = None) -> list[dict]:
    """Pure function: cue dicts (citations rows, seq order) -> clip dicts.

    Each clip carries ``seq``, ``start``, ``end``, ``text``, ``cue_count``
    and ``source_deep_link``. Screenshot rows must not be passed in.
    Deterministic for a given input."""
    item = item or {}
    clips: list[dict] = []
    words: list[str] = []
    w_start = w_end = None
    w_cues = 0
    w_link = None
    prev_start = None

    def flush():
        nonlocal words, w_start, w_end, w_cues, w_link
        if words and w_start is not None:
            clips.append({
                "seq": len(clips),
                "start": float(w_start),
                "end": float(w_end if w_end is not None else w_start),
                "text": " ".join(words),
                "cue_count": w_cues,
                "source_deep_link": w_link,
                "timing": "source_cues",
            })
        words, w_start, w_end, w_cues, w_link = [], None, None, 0, None

    for cue in cues:
        try:
            start = float(cue.get("timestamp_start"))
        except (TypeError, ValueError):
            continue  # a cue with no place on the timeline cannot be a clip
        try:
            end = float(cue.get("timestamp_end"))
        except (TypeError, ValueError):
            end = start
        end = max(end, start)
        if not math.isfinite(start) or not math.isfinite(end):
            continue
        if prev_start is not None and start + _REWIND_TOLERANCE_SECONDS < prev_start:
            log.debug("clips: stale cue track at seq %s (start %.2f < %.2f); "
                      "stopping", cue.get("seq"), start, prev_start)
            break
        prev_start = max(prev_start, start) if prev_start is not None else start

        text = normalize_text(cue.get("text"))
        if not text:
            continue
        fresh = new_words(words, text)
        if not fresh and (end - start) < _DUP_CUE_SECONDS:
            continue  # the ~10 ms caption echo
        if end - start > MAX_WINDOW_SECONDS:
            flush()
            for part in _coarse_parts(" ".join(fresh)):
                clips.append({"seq": len(clips), "start": start, "end": end,
                              "text": part, "cue_count": 1,
                              "source_deep_link": _deep_link(cue, item),
                              "timing": "coarse"})
            continue
        if w_start is not None and max(w_end, end) - w_start > MAX_WINDOW_SECONDS:
            flush()
        if w_start is None:
            w_start = start
            w_link = _deep_link(cue, item)
        words.extend(fresh)
        w_end = max(w_end, end) if w_end is not None else end
        w_cues += 1

        duration = w_end - w_start
        if duration >= MAX_WINDOW_SECONDS or (
                duration >= MIN_WINDOW_SECONDS and ends_sentence(text)):
            flush()
    flush()

    # Fold a short trailing window into its predecessor when the merged
    # window still fits, so a video never ends on a three-second orphan.
    if len(clips) >= 2:
        last, prev = clips[-1], clips[-2]
        if last["timing"] != "coarse" and prev["timing"] != "coarse" and (
                last["end"] - last["start"]) < MIN_WINDOW_SECONDS and (
                last["end"] - prev["start"]) <= MAX_WINDOW_SECONDS:
            prev["end"] = last["end"]
            prev["text"] = f"{prev['text']} {last['text']}"
            prev["cue_count"] += last["cue_count"]
            clips.pop()
    return clips


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def _item_for(conn: sqlite3.Connection, video_id: str) -> dict:
    row = conn.execute(
        "SELECT video_id, platform, metadata_json FROM yoinks WHERE video_id=?",
        (video_id,)).fetchone()
    if row is None:
        return {"video_id": video_id, "platform": None, "url": ""}
    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        meta = {}
    url = meta.get("url") if isinstance(meta, dict) else None
    return {"video_id": video_id, "platform": row["platform"],
            "url": url if isinstance(url, str) else ""}


def build_clips_for_video(conn: sqlite3.Connection, video_id: str, *,
                          commit: bool = True) -> int:
    """Delete and re-derive one video's clips from its transcript citations.
    Returns the number of clips written. ``conn`` needs ``row_factory =
    sqlite3.Row`` (Index's connection has it). Pass ``commit=False`` when the
    caller owns the transaction."""
    cues = [dict(r) for r in conn.execute(
        "SELECT seq, timestamp_start, timestamp_end, text, source_deep_link "
        "FROM citations WHERE video_id=? AND kind='transcript_chunk' "
        "ORDER BY seq", (video_id,))]
    conn.execute("DELETE FROM clips WHERE video_id=?", (video_id,))
    clips = merge_cues(cues, _item_for(conn, video_id)) if cues else []
    if clips:
        conn.executemany(
            "INSERT INTO clips (video_id, seq, start, end, text, speaker, "
            "source_deep_link, cue_count) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
            [(video_id, c["seq"], c["start"], c["end"], c["text"],
              c["source_deep_link"], c["cue_count"]) for c in clips])
    if commit:
        conn.commit()
    return len(clips)


def rebuild_all_clips(conn: sqlite3.Connection) -> dict:
    """Rebuild clips for every indexed item, in one transaction. Items with
    no transcript citations end up with zero clips (any stale rows go)."""
    started = time.monotonic()
    video_ids = [r[0] for r in conn.execute(
        "SELECT video_id FROM yoinks ORDER BY video_id")]
    conn.execute("DELETE FROM clips")
    items_with_clips = 0
    clip_count = 0
    for video_id in video_ids:
        n = build_clips_for_video(conn, video_id, commit=False)
        if n:
            items_with_clips += 1
            clip_count += n
    conn.commit()
    return {
        "items": len(video_ids),
        "items_with_clips": items_with_clips,
        "items_without_clips": len(video_ids) - items_with_clips,
        "clip_count": clip_count,
        "seconds": round(time.monotonic() - started, 3),
    }


def clip_coverage(conn: sqlite3.Connection) -> dict:
    """How much of the live library has clips."""
    row = conn.execute(
        "SELECT "
        " SUM(EXISTS (SELECT 1 FROM clips c WHERE c.video_id = y.video_id)) "
        "   AS with_clips, "
        " COUNT(*) AS items "
        "FROM yoinks y WHERE y.deleted_at IS NULL").fetchone()
    with_clips = int(row["with_clips"] or 0)
    items = int(row["items"] or 0)
    total = conn.execute("SELECT COUNT(*) AS n FROM clips").fetchone()
    return {
        "items_with_clips": with_clips,
        "items_without_clips": items - with_clips,
        "clip_count": int(total["n"] or 0),
    }
