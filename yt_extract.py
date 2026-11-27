#!/usr/bin/env python3
"""
yt_extract.py — pull transcript + screenshots from any YouTube video.

Usage:
    python yt_extract.py <url>
    python yt_extract.py <url> --interval 30 --out ./yt_extracts

Outputs (per video, in a folder named after the video title):
    transcript.txt   — plain text transcript
    combined.md      — transcript + screenshots interleaved by timestamp
    screenshots/     — frames extracted every <interval> seconds
    video.<ext>      — low-res copy used for frame extraction (delete if you want)

Requirements:
    pip install yt-dlp
    ffmpeg on PATH in source checkouts; app-owned Helpers in the macOS bundle
"""

import argparse
import json
import logging
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import NamedTuple


# Windows reserved device names. As path segments these fail to open even
# when extensions are appended ("CON.txt" still resolves to the console
# device). slugify() prepends an underscore when it would otherwise emit
# one of these. Match is case-insensitive.
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def slugify(text: str) -> str:
    # ASCII-only so the resulting slug is safe as a filesystem path segment
    # AND satisfies the server's strict session_id regex
    # ([A-Za-z0-9_-]{1,64}). Without re.ASCII, \w matches Unicode word
    # chars and a session named "cafe" with non-ASCII letters would slug to
    # those same letters -- which the API would later reject when the user
    # tried to add to it.
    slug = re.sub(r"[^\w\-]+", "_", text.strip(), flags=re.ASCII)[:80].strip("_")
    # Windows reserved-name guard. A video titled "CON" or "AUX" would
    # otherwise produce a folder Windows refuses to open.
    if slug.upper() in _WINDOWS_RESERVED_NAMES:
        slug = "_" + slug
    return slug


def fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


_CAPTION_TIME = r"(?:\d{1,6}:)?\d{2}:\d{2}[,.]\d{3}"
_CAPTION_RANGE = re.compile(rf"^({_CAPTION_TIME})\s+-->\s+({_CAPTION_TIME})(?:\s|$)")
_SRT_SEPARATOR = re.compile(rf"\n(?:\n+|[ \t]+\n(?=(?:[^\n]+\n)?[ \t]*{_CAPTION_TIME}\s+-->))")
_INLINE_TIME = re.compile(rf"<({_CAPTION_TIME})>")
_CAPTION_TAG = re.compile(
    rf"<(?:{_CAPTION_TIME}|/?(?:[biu]|ruby|rt|c(?:\.[\w.-]+)?|(?:v|lang|font)(?:\s+[^<>]*)?))>",
    re.IGNORECASE,
)


def _caption_seconds(stamp):
    value = 0.0
    for part in stamp.replace(",", ".").split(":"):
        value = value * 60 + float(part)
    return value


def protected_caption_text(text: str) -> bool:
    """These scripts need their original spacing, line boundaries and bidi marks."""
    if text.isascii():
        return False
    return any(
        unicodedata.bidirectional(c) in {"R", "AL", "AN", "RLE", "RLO", "RLI", "FSI"}
        or c in "\u200e\u202a\u202c\u202d\u2066\u2069"
        or 0x20000 <= ord(c) <= 0x3FFFD  # supplementary ideographic planes
        or unicodedata.name(c, "").startswith((
            "CJK", "HIRAGANA", "KATAKANA", "HALFWIDTH KATAKANA", "HANGUL",
            "BOPOMOFO", "IDEOGRAPHIC", "THAI", "LAO", "KHMER", "MYANMAR",
        ))
        for c in text if not c.isascii()
    )


def _clean_caption_text(text: str) -> str:
    # Decode subtitle markup without normalizing the speaker's text or spacing.
    text = _CAPTION_TAG.sub("", text)
    text = re.sub(r"\[(?:\\h)+__(?:\\h)+\]", "[__]", text)
    return re.sub(r"(?:\\h)+", " ", text)


class _CaptionWindow(NamedTuple):
    start: float
    end: float
    lines: tuple[str, ...]
    words: tuple[str, ...]
    clock_line: int | None


def _caption_window(start, end, raw, text, stored):
    lines = tuple(line.strip() for line in text.split("\n") if line.strip())
    clock_line = None
    if not stored and _INLINE_TIME.search(raw):
        # A clock on the proposed carried line may be a new performance of the
        # very same lyric. Only untimed lines before the newly timed line qualify.
        count = 0
        for line in raw.split("\n"):
            stamps = _INLINE_TIME.findall(line)
            if stamps:
                fresh = (_clean_caption_text(line).strip()
                         and all(start <= _caption_seconds(stamp) <= end for stamp in stamps))
                clock_line = count if fresh else 0
                break
            if _clean_caption_text(line).strip():
                count += 1
    return _CaptionWindow(start, end, lines, tuple(text.split()), clock_line)


def _two_spoken_words(words):
    names = {"".join(c for c in word.casefold() if c.isalnum()) for word in words}
    return len(names - {""}) >= 2


def _window_overlap(previous, current, bridge_end):
    if current.start <= previous.start or current.end <= previous.end:
        return 0
    if current.clock_line is not None:
        carry = current.lines[:current.clock_line]
        if (not carry or len(carry) == len(current.lines) or current.start > bridge_end + .001
                or previous.lines[-len(carry):] != carry):
            return 0
        words = " ".join(carry).split()
        return len(words) if _two_spoken_words(words) else 0
    # Clockless SRT / stored captions need at least 100ms of overlap and a
    # constant-size window. A longer edition of the same opening, a repeated
    # whole cue, and a one-word handoff are all ambiguous.
    if previous.clock_line is not None or previous.end - current.start < .099999:
        return 0
    before, after = previous.words, current.words
    # Very long rows are probably paragraphs. Don't guess their display layout.
    if len(before) != len(after) or len(before) > 128:
        return 0
    for size in range(min(len(before), len(after)) - 1, 1, -1):
        if before[-size:] == after[:size]:
            if before[:size] != after[:size] and _two_spoken_words(after[:size]):
                if any(c.isalnum() for word in after[size:] for c in word):
                    return size
            break
    return 0


def clean_caption_windows(entries, *, stored=False):
    """Keep every cue and its times. Trim carried words only in confirmed runs."""
    entries = list(entries)
    output = [(start, end, raw if stored else _clean_caption_text(raw))
              for start, end, raw in entries]
    if any(protected_caption_text(text) for _, _, text in output):
        return output
    windows = [_caption_window(start, end, raw, text, stored)
               for (start, end, raw), (_, _, text) in zip(entries, output)]
    if not windows:
        return output

    def finish_run(run):
        # Three consecutive shifts (four time-ordered windows) corroborate
        # each other. Clockless cycles may instead be deliberate lyrics.
        if len(run) < 3:
            return
        if any(windows[i].clock_line is None for i, _ in run):
            phrases = {windows[i].words[skip:] for i, skip in run}
            cues = {windows[i].words for i, _ in run}
            cues.add(windows[run[0][0] - 1].words)
            if len(phrases) != len(run) or len(cues) != len(run) + 1:
                return
        for i, skip in run:
            start, end, text = output[i]
            output[i] = (start, end, text.split(None, skip)[-1])

    run = []
    shape = None
    previous = windows[0]
    bridge_end = previous.end
    for i, current in enumerate(windows[1:], 1):
        # A 0-20ms bridge can copy all or the last line of a timed display.
        # Keep its words and timing; it provides continuity, not new evidence.
        if (not stored and previous.clock_line is not None and current.clock_line is None
                and abs(current.start - previous.end) <= .001
                and 0 <= current.end - current.start <= .020001 and current.lines
                and previous.lines[-len(current.lines):] == current.lines):
            bridge_end = current.end
            continue
        skip = _window_overlap(previous, current, bridge_end)
        # Without inline clocks, all three steps must also shift the same
        # number of words. A chain of spoken echoes rarely has this geometry.
        next_shape = (len(current.words), skip) if current.clock_line is None else None
        if not skip or next_shape != shape:
            finish_run(run)
            run.clear()
        if skip:
            run.append((i, skip))
        shape = next_shape
        previous = current
        bridge_end = current.end
    finish_run(run)
    return output


def _vtt_word_times(raw, row):
    """Attach clocks only when they account for every visible word, in order."""
    if not _INLINE_TIME.search(raw):
        return row
    start, end, text = row
    original = [line for line in raw.split("\n") if _clean_caption_text(line).strip()]
    kept = sum(bool(line.strip()) for line in text.split("\n"))
    # Timed window cleanup can trim only entire display lines from the top.
    fragments = _INLINE_TIME.split("\n".join(original[-kept:]))
    if len(fragments) == 1:
        return row
    words = []
    first = _clean_caption_text(fragments[0]).strip()
    if first:
        # An intact, single-line cue supplies its first clock. After a roll
        # the cue start can precede the new words by seconds.
        if len(original) != 1 or len(first.split()) != 1:
            return row
        words.append({"start": start, "word": first})
    for stamp, fragment in zip(fragments[1::2], fragments[2::2]):
        clock = _caption_seconds(stamp)
        word = _clean_caption_text(fragment).strip()
        if (not start <= clock < end or (words and clock <= words[-1]["start"])
                or len(word.split()) != 1):
            return row
        words.append({"start": clock, "word": word})
    # An inline tag can be inside a syllable. Never turn those pieces into words.
    if [w["word"] for w in words] != text.split():
        return row
    for i, word in enumerate(words):
        word["end"] = words[i + 1]["start"] if i + 1 < len(words) else end
    from uoink_reliability import TranscriptEntry
    return TranscriptEntry(start, end, text, words)


def parse_srt(srt_path: Path, duration: float | None = None, *, automatic=False):
    """Yield (start_sec, end_sec, text) from an SRT or WebVTT file.

    With a known ``duration``, cues that start at or after it are dropped and
    end times are clamped: uploaders sometimes attach captions for a longer cut.
    """
    content = srt_path.read_text(encoding="utf-8-sig", errors="replace").strip("\n")
    entries: list[tuple[float, float, str]] = []
    # YouTube sometimes puts a space-only display line directly after the
    # timestamp. Splitting on blank *or whitespace* lines loses the next words.
    blocks = (_SRT_SEPARATOR.split(content) if srt_path.suffix.lower() == ".srt"
              else re.split(r"\n{2,}", content))
    for block in blocks:
        lines = block.split("\n")
        if re.match(r"^(?:WEBVTT|NOTE|STYLE|REGION)(?:\s|$)", lines[0].strip()):
            continue
        for i, header in enumerate(lines[:2]):
            match = _CAPTION_RANGE.match(header.strip())
            if match:
                start, end = map(_caption_seconds, match.groups())
                raw = "\n".join(lines[i+1:])
                if end >= start and _clean_caption_text(raw).strip():
                    entries.append((start, end, raw))
                break

    if duration and duration > 0:
        kept = [(start, min(end, duration), text) for start, end, text in entries if start < duration]
        if len(kept) < len(entries):
            logging.getLogger(__name__).info(
                "dropped %d caption cue(s) past the %.0fs video", len(entries) - len(kept), duration)
        entries = kept
    if automatic:
        rows = clean_caption_windows(entries)
        if srt_path.suffix.lower() == ".vtt" and not any(protected_caption_text(r[2]) for r in rows):
            for (_, _, raw), row in zip(entries, rows):
                yield _vtt_word_times(raw, row)
        else:
            yield from rows
    else:
        yield from ((s, e, _clean_caption_text(raw)) for s, e, raw in entries)


class _CaptionWord(NamedTuple):
    start: int          # absolute JSON3 clock, milliseconds
    window_end: int     # latest possible end supplied by the event
    text: str
    break_before: bool
    break_after: bool


def _json3_event_words(event, append):
    base, duration = event.get("tStartMs"), event.get("dDurationMs")
    if type(base) is not int or base < 0 or type(duration) is not int or duration <= 0:
        raise ValueError("missing caption interval")
    if not isinstance(event.get("segs"), list) or not event["segs"]:
        raise ValueError("missing caption segments")
    words = []
    previous_separator = True
    for seg in event["segs"]:
        if not isinstance(seg, dict) or not isinstance(seg.get("utf8"), str):
            raise ValueError("invalid caption segment")
        offset = seg.get("tOffsetMs")
        if type(offset) is not int or not 0 <= offset < duration:
            raise ValueError("missing or out-of-window word clock")
        raw = seg["utf8"].replace("\\h", " ")
        text = re.sub(r"\[\s*__\s*\]", "[__]", raw).strip()
        # One clock for a phrase or an unspaced word fragment cannot supply
        # reliable word boundaries. A lone surrogate cannot be saved as UTF-8.
        if (len(text.split()) != 1 or protected_caption_text(raw)
                or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff]", raw)
                or not previous_separator and not raw[0].isspace()):
            raise ValueError("invalid caption word")
        start = base + offset
        if words and start <= words[-1].start:
            raise ValueError("unordered word clocks")
        leading = raw[:len(raw) - len(raw.lstrip())]
        trailing = raw[len(raw.rstrip()):]
        previous_separator = bool(trailing)
        # Within an event only word onsets are known. Between events the
        # preceding event's explicit end gives us an actual gap.
        pause = bool(words) and start - words[-1].start > 700
        words.append(_CaptionWord(start, base + duration, text,
                                  pause or "\n" in leading or (not words and bool(append)),
                                  "\n" in trailing))
    return words


def _json3_words(events):
    """Accept one ordered word stream. A repaint must replay its exact timed tail."""
    words = []
    by_start = {}
    window = None
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("invalid caption event")
        win_id, append = event.get("wWinId"), event.get("aAppend", 0)
        if (win_id is not None and type(win_id) is not int) or (words and window != win_id):
            raise ValueError("ambiguous caption window")
        if type(append) is not int or append not in (0, 1):
            raise ValueError("invalid caption operation")
        window = win_id
        incoming = _json3_event_words(event, append)

        if words and incoming[0].start <= words[-1].start:
            # Identity includes the word clock, the complete tail and the window.
            # Equal lyrics at a later clock are always new speech. Never sort a
            # conflicting edit into the transcript or publish a partial stream.
            pos = by_start.get(incoming[0].start)
            if append or pos is None or len(words) - pos > len(incoming):
                raise ValueError("ambiguous replay")
            overlap = len(words) - pos
            if any(old.start != new.start or old.text != new.text
                   for old, new in zip(words[pos:], incoming)):
                raise ValueError("conflicting replay")
            incoming = incoming[overlap:]
        if incoming and words and incoming[0].start - words[-1].window_end > 700:
            incoming[0] = incoming[0]._replace(break_before=True)
        for word in incoming:
            by_start[word.start] = len(words)
            words.append(word)
    return words


def _json3_entries(words, duration):
    from uoink_reliability import TranscriptEntry

    rows, cue = [], []

    def flush():
        if cue:
            rows.append(TranscriptEntry(cue[0]["start"], cue[-1]["end"],
                                        " ".join(w["word"] for w in cue), cue.copy()))
            cue.clear()

    limit = duration * 1000 if duration and duration > 0 else None
    for i, word in enumerate(words):
        if limit is not None and word.start >= limit:
            break
        # JSON3 supplies starts and the event end. The next word can shorten
        # the previous word's interval, including across display windows.
        end = word.window_end
        if i + 1 < len(words):
            end = min(end, words[i + 1].start)
        if limit is not None:
            end = min(end, limit)
        if cue and (word.break_before or len(cue) >= 12 or end / 1000 - cue[0]["start"] > 6):
            flush()
        cue.append({"word": word.text, "start": word.start / 1000, "end": end / 1000})
        if word.break_after or word.text.rstrip("\"'”’)]").endswith((".", "?", "!")):
            flush()
    flush()
    return rows


def parse_json3(path: Path, duration: float | None = None):
    """Read a known auto track. An empty result asks the caller for VTT/SRT."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            return []
        return _json3_entries(_json3_words(data["events"]), duration)
    except (OSError, ValueError, OverflowError, RecursionError):
        return []


def chapters_from_metadata(info) -> list[dict]:
    """Phase 6 (phase6-v1): the source chapter list already present in a
    fetched YouTube metadata blob, as ``{seq, start, end, title,
    record_locator}`` rows in source order. Pure: no fetch, no CLI call, no
    sort, clamp, gap fill or invented title. Entries missing any of the
    three fields are returned with ``None`` so the media validator rejects
    the whole list visibly (``chapter_state=invalid``) instead of guessing.
    The caller supplies the artifact digest and recorded time when it builds
    the producer descriptor (``provider="youtube_metadata"``)."""
    if not isinstance(info, dict) or not isinstance(info.get("chapters"), list):
        return []
    rows: list[dict] = []
    for index, entry in enumerate(info["chapters"]):
        if not isinstance(entry, dict):
            rows.append({"seq": index, "start": None, "end": None, "title": None,
                         "record_locator": ["chapters", index]})
            continue
        rows.append({
            "seq": index,
            "start": entry.get("start_time"),
            "end": entry.get("end_time"),
            "title": entry.get("title"),
            "record_locator": ["chapters", index],
        })
    return rows


_ENGLISH_TRACKS = ("en", "en-US", "en-GB", "en-orig")


def english_caption_tracks(metadata, youtube):
    """Keep the capture's English preference. Select the kind before downloading."""
    if not youtube:
        return [None]
    manual = metadata.get("subtitles")
    auto = metadata.get("automatic_captions")
    tracks = []
    if isinstance(manual, dict):
        regional = sorted(k for k in manual if isinstance(k, str) and
                          re.fullmatch(r"en(?:-[A-Za-z0-9]{1,8})+", k))
        for key in (*_ENGLISH_TRACKS, *regional):
            if manual.get(key):
                tracks.append({"kind": "captions", "key": key})
                break
    if isinstance(auto, dict):
        for key in ("en-orig", *_ENGLISH_TRACKS[:3]):
            if auto.get(key):
                tracks.append({"kind": "auto_captions", "key": key})
                break
    if not isinstance(manual, dict) and not isinstance(auto, dict):
        # A resumed capture or a backfill may have no track list. Separate
        # requests keep a new automatic track distinguishable from an upload.
        return [{"kind": "captions", "key": None}, {"kind": "auto_captions", "key": None}]
    return tracks


def caption_args(track, text_only=False):
    if track is None:
        return ["--write-auto-subs", "--write-subs", "--sub-lang", ",".join(_ENGLISH_TRACKS),
                "--convert-subs", "srt"]
    automatic = track["kind"] == "auto_captions"
    # Never wildcard automatic tracks: it also downloads translated variants.
    key = track["key"] or (",".join(_ENGLISH_TRACKS) if automatic else "en(?:-[A-Za-z0-9]+)*")
    formats = "json3/vtt/srt" if automatic and not text_only else "vtt/srt"
    args = ["--write-auto-subs" if automatic else "--write-subs", "--sub-lang", key,
            "--sub-format", track.get("convert") or formats]
    if track.get("convert"):
        args.extend(["--convert-subs", "srt"])
    elif text_only:
        # The existing VTT was empty or unreadable. yt-dlp otherwise reuses it.
        args.append("--force-overwrites")
    return args


def caption_rate_warning(stderr, folder, prefix, track, text_only):
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    if not isinstance(stderr, str) or not re.search(
            r"\b(?:HTTP(?: Error)?|status(?: code)?)\s*:?\s*429\b|\b429[: ]+Too Many Requests", stderr, re.I):
        return False
    # A warning for a different requested language can accompany a successful
    # download. Use a readable track from this request first.
    formats = ("vtt", "srt") if text_only else None
    return not any(_read_caption_file(path, track, None)
                   for path in _caption_paths(folder, prefix, track, formats))


def _caption_paths(folder, prefix, track, formats=None):
    automatic = bool(track and track["kind"] == "auto_captions")
    formats = formats or (("json3", "vtt", "srt") if automatic else ("vtt", "srt"))
    key = track and track["key"]
    if key:
        paths = [folder / f"{prefix}.{key}.{ext}" for ext in formats]
        return [p for p in paths if p.is_file() and not p.is_symlink()]
    # The old video.en.srt naming has no provenance. Never let a wildcard
    # for old files consume video.auto.en.srt or a different kind of track.
    paths = [p for ext in formats for p in folder.glob(f"{prefix}.*.{ext}")
             if p.is_file() and not p.is_symlink()
             and re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8}){0,3}",
                              p.stem[len(prefix) + 1:])]
    keys = {p.stem[len(prefix) + 1:] for p in paths}
    preferred = ("en-orig", *_ENGLISH_TRACKS[:3]) if automatic else _ENGLISH_TRACKS
    selected = next((k for k in preferred if k in keys), min(keys, default=None))
    return [p for p in paths if p.stem == f"{prefix}.{selected}"]


def _read_caption_file(path, track, duration):
    try:
        if path.suffix == ".json3":
            return parse_json3(path, duration=duration)
        auto = bool(track and track["kind"] == "auto_captions")
        return list(parse_srt(path, duration=duration, automatic=auto))
    except (OSError, ValueError, OverflowError, RecursionError):
        return []


def read_caption_track(folder, prefix, track, duration, fetch, *, reuse=False):
    """Fetch and parse one kind of track, retrying bad JSON in its text format."""
    if not reuse:
        reason = fetch(track, prefix, False)
        if reason:
            return [], reason
    paths = _caption_paths(folder, prefix, track)
    for path in paths:
        entries = _read_caption_file(path, track, duration)
        if entries:
            return entries, None
    # yt-dlp picks ONE format. A bad JSON file usually has no VTT sibling.
    # If no requested format exists, yt-dlp may have saved TTML/ASS instead.
    if not paths and track and not reuse:
        paths = _caption_paths(folder, prefix, track, ("ttml", "dfxp", "tt", "ass", "ssa", "lrc"))
    if not paths or paths[0].suffix in (".vtt", ".srt"):
        return [], None
    source = paths[0]
    same_track = dict(track, key=source.stem[len(prefix) + 1:])
    if source.suffix != ".json3":
        same_track["convert"] = source.suffix[1:]
    reason = fetch(same_track, prefix, True)
    if reason:
        return [], reason
    for path in _caption_paths(folder, prefix, same_track, ("vtt", "srt")):
        entries = _read_caption_file(path, same_track, duration)
        if entries:
            return entries, None
    return [], None


def capture_captions(folder, metadata, youtube, duration, fetch, *, reuse=False):
    tracks = english_caption_tracks(metadata, youtube)
    if reuse:
        # Finish can use existing media offline. Recognize only our own
        # kind-specific prefixes; files from earlier versions remain unlabelled.
        for kind, prefix in (("captions", "video.manual"), ("auto_captions", "video.auto"),
                             (None, "video")):
            track = {"key": None, "kind": kind} if kind and youtube else None
            if kind and track is None:
                continue
            entries, reason = read_caption_track(folder, prefix, track, duration, fetch, reuse=True)
            if entries or reason:
                return entries, kind if entries else None, reason
    for track in tracks:
        kind = track and track["kind"]
        prefix = {"captions": "video.manual", "auto_captions": "video.auto"}.get(kind, "video")
        entries, reason = read_caption_track(folder, prefix, track, duration, fetch)
        if entries or reason:
            return entries, kind if entries else None, reason
    return [], None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--interval", type=int, default=30, help="screenshot interval in seconds (default: 30)")
    ap.add_argument("--out", default="./yt_extracts", help="output root folder")
    ap.add_argument("--keep-video", action="store_true", help="keep the downloaded video file")
    args = ap.parse_args()

    import _platform
    _platform.require_media()

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    print("Fetching title...")
    ytdlp = ([sys.executable, "-m", "yt_dlp", *_platform.ytdlp_media_args()]
             if sys.platform == "darwin" else ["yt-dlp"])
    metadata = json.loads(subprocess.check_output(
        [*ytdlp, "--dump-single-json", "--skip-download", args.url], text=True, encoding="utf-8"))
    title = metadata["title"]
    folder = out_root / slugify(title)
    folder.mkdir(exist_ok=True)
    print(f"-> {folder}")

    print("Downloading video + subtitles...")
    subprocess.run(
        [
            *ytdlp,
            "-f", (_platform.video_format("worst[height>=360]/worst")
                   if sys.platform == "darwin" else "worst[height>=360]/worst"),
            "-o", str(folder / "video.%(ext)s"),
            args.url,
        ],
        check=True,
    )

    video_files = [f for f in folder.glob("video.*") if f.suffix in (".mp4", ".webm", ".mkv")]
    if not video_files:
        sys.exit("No video file found.")
    video_file = video_files[0]

    print(f"Extracting screenshots every {args.interval}s...")
    shots_dir = folder / "screenshots"
    shots_dir.mkdir(exist_ok=True)
    subprocess.run(
        [
            _platform.media_binary("ffmpeg") if sys.platform == "darwin" else "ffmpeg",
            "-loglevel", "error", "-y",
            "-i", str(video_file),
            "-vf", f"fps=1/{args.interval}:round=up",
            "-q:v", "2",
            str(shots_dir / "shot_%04d.jpg"),
        ],
        check=True,
    )
    shots = sorted(shots_dir.glob("shot_*.jpg"))

    def fetch(track, prefix, text_only):
        try:
            subprocess.run([*ytdlp, "--skip-download", *caption_args(track, text_only),
                            "-o", str(folder / f"{prefix}.%(ext)s"), args.url], check=True)
        except (OSError, subprocess.SubprocessError):
            return "captions_failed"
        return None

    entries, _, _ = capture_captions(
        folder, metadata, metadata.get("extractor_key") == "Youtube",
        metadata.get("duration"), fetch)

    print("Writing transcript.txt and combined.md...")
    if entries:
        plain = "\n".join(text for _, _, text in entries)
        (folder / "transcript.txt").write_text(plain, encoding="utf-8")

    md = [f"# {title}", "", f"Source: {args.url}", ""]
    for i, shot in enumerate(shots):
        start = i * args.interval
        end = (i + 1) * args.interval
        chunk = " ".join(t for s, _, t in entries if start <= s < end)
        md.append(f"## [{fmt_time(start)}]")
        md.append("")
        md.append(f"![shot {i+1}](screenshots/{shot.name})")
        md.append("")
        if chunk:
            md.append(chunk)
            md.append("")
    (folder / "combined.md").write_text("\n".join(md), encoding="utf-8")

    if not args.keep_video:
        video_file.unlink(missing_ok=True)

    print()
    print(f"Done. {len(shots)} screenshots, {len(entries)} caption lines.")
    print(f"Folder: {folder}")

if __name__ == "__main__":
    main()
