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


_CUE_TIME = r"(?:\d+:)?\d{2}:\d{2}[,.]\d{3}"
_CUE_RANGE = re.compile(rf"^({_CUE_TIME})\s+-->\s+({_CUE_TIME})(?:\s|$)")
_WORD_TIME = re.compile(rf"<({_CUE_TIME})>")


def _seconds(stamp):
    parts = stamp.replace(",", ".").split(":")
    return sum(float(value) * 60 ** i for i, value in enumerate(reversed(parts)))


def _clean_caption_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text).replace("\\h", " ")
    text = re.sub(r"\[\s*__\s*\]", "[__]", text)
    return " ".join(text.split()) if text.isascii() else text.strip()


def caption_window_text(entries, *, automatic, stored=False):
    """Remove display history only when clocks or neighboring shifts confirm it."""
    windows = []
    shifts = []
    for i, (start, end, raw) in enumerate(entries):
        lines = [line for line in (raw.splitlines() if stored else
                 map(_clean_caption_text, raw.splitlines())) if line]
        words = " ".join(lines).split()
        skip = 0
        ghost = timed_roll = False
        clock = bool(_WORD_TIME.search(raw))
        # Use the conservative whitespace heuristic only for ASCII speech.
        if automatic and windows and raw.isascii() and entries[i-1][2].isascii():
            plines, prior, pclock, bridge, _ = windows[-1]
            pstart, pend, previous_raw = entries[i-1]
            adjacent = abs(start - pend) <= .001
            ghost = (not stored and adjacent and 0 <= end - start <= .020001
                     and len(words) >= 2 and lines == plines[-len(lines):] and (len(plines) > 1 or pclock)
                     and (not clock or set(_WORD_TIME.findall(raw)) <= set(_WORD_TIME.findall(previous_raw))))
            if adjacent and len(lines) > 1 and plines and (clock or pclock or bridge):
                # A carried display line may retain its old word clocks. Fresh
                # clocks on the repeated line identify a new utterance.
                carried_clocks = _WORD_TIME.findall(raw.splitlines()[0])
                if (lines[0] == plines[-1] and lines[0] not in lines[1:]
                        and (not carried_clocks or carried_clocks == _WORD_TIME.findall(previous_raw.splitlines()[-1]))):
                    skip = len(lines[0].split())
                    timed_roll = True
            elif start > pstart and pend - start >= .1:
                # Both windows must shift: old words leave and new words arrive.
                for size in range(min(len(prior) - 1, len(words) - 1), 1, -1):
                    if prior[-size:] == words[:size] and prior[:size] != words[:size]:
                        skip = size
                        break
        shifts.append(skip if skip >= 2 else 0)
        windows.append((lines, words, clock, ghost, timed_roll))
    for i, (lines, words, _, ghost, timed_roll) in enumerate(windows):
        if ghost:
            continue
        if shifts[i] and (timed_roll or (i and shifts[i-1]) or (i+1 < len(shifts) and shifts[i+1])):
            yield i, " ".join(words[shifts[i]:])
        elif words or stored:
            raw = entries[i][2]
            separator = " " if raw.isascii() else "\n"
            yield i, raw if stored else separator.join(lines)


class _JSON3Token(NamedTuple):
    start: int
    end: int | None
    text: str
    boundary: bool
    spaced: bool


def _json3_has_two_words(tokens):
    # A word can span segments, and punctuation can have its own clock.
    spoken = "".join((" " if token.spaced else "") + token.text for token in tokens)
    return sum(any(char.isalnum() for char in word) for word in spoken.split()) >= 2


def _json3_entries(content, *, automatic):
    """Read clocks in source order. Never sort untimed fragments ahead of speech."""
    data = json.loads(content)
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise ValueError("Missing JSON3 events")
    tokens = []
    boundary = False
    trailing_space = False
    for event in data["events"]:
        if not isinstance(event, dict):
            raise ValueError("Invalid JSON3 event")
        boundary |= bool(event.get("aAppend")) or not automatic
        segs = event.get("segs")
        if segs is None:
            continue
        base, duration = event.get("tStartMs"), event.get("dDurationMs")
        if (not isinstance(segs, list) or type(base) is not int or base < 0
                or (duration is not None and (type(duration) is not int or duration < 0))):
            raise ValueError("Invalid JSON3 timing")
        end = base + duration if duration else None
        # Native JSON3 includes separators in utf8. Some producers instead
        # supply a timed word list with no separators at all.
        native_spacing = any(isinstance(seg, dict) and isinstance(seg.get("utf8"), str)
                             and re.search(r"\s|\\h", seg["utf8"]) for seg in segs)
        offset = 0
        current = []
        for index, seg in enumerate(segs):
            if not isinstance(seg, dict) or not isinstance(seg.get("utf8"), str):
                raise ValueError("Invalid JSON3 segment")
            clock = seg.get("tOffsetMs")
            if clock is not None:
                if type(clock) is not int or clock < offset:
                    raise ValueError("Invalid JSON3 offset")
                offset = clock
            start = base + offset
            if end is not None and end < start:
                raise ValueError("Invalid JSON3 duration")
            if automatic and current and start - current[-1].start > 700:
                boundary = True
            for part, fragment in enumerate(seg["utf8"].split("\n")):
                boundary |= part > 0
                text = _clean_caption_text(fragment)
                spaced = trailing_space or fragment[:1].isspace() or fragment.startswith("\\h")
                trailing_space = fragment[-1:].isspace() or fragment.endswith("\\h")
                if not text:
                    if boundary:
                        current.append(_JSON3Token(start, start, "", True, False))
                    continue
                word_start = index == 0 or (not native_spacing and clock is not None)
                if word_start and text[0].isascii() and text[0].isalnum():
                    spaced = True
                current.append(_JSON3Token(start, end, text, boundary, spaced))
                boundary = False
        if automatic and not event.get("aAppend") and tokens and current and current[0].start <= tokens[-1].start:
            # A replay must match the tail by both clock and text, leave new
            # speech, and span at least two words with different clocks.
            for size in range(min(len(current) - 1, len(tokens)), 1, -1):
                if tokens[-size].start != current[0].start:
                    continue
                prefix = current[:size]
                tail = tokens[-size:]
                if (prefix[0].start < prefix[-1].start
                        and any(token.text for token in current[size:])
                        and all(a.text and a.text.isascii() and a.start == b.start and a.text == b.text
                                for a, b in zip(prefix, tail))
                        and _json3_has_two_words(prefix) and _json3_has_two_words(tail)):
                    boundary_before_replay = current[0].boundary
                    current = current[size:]
                    if boundary_before_replay:
                        current[0] = current[0]._replace(boundary=True)
                    break
        if current and tokens:
            prior = tokens[-1]
            if current[0].start < prior.start:
                raise ValueError("Ambiguous JSON3 chronology")
            previous_end = prior.end if prior.end is not None else prior.start
            if automatic and current[0].start - previous_end > 700:
                current[0] = current[0]._replace(boundary=True)
        tokens.extend(current)

    cue = ""
    for i, (start, end, text, boundary, spaced) in enumerate(tokens):
        if i + 1 < len(tokens):
            following = tokens[i + 1].start
            end = following if end is None else min(end, following)
        if end is None:
            end = start  # Open final append: retain speech up to its last known word clock.
        exceeds_budget = cue and (start - cue_start >= 6000 or len(cue.split()) + len(text.split()) > 12)
        if cue and (boundary or (automatic and exceeds_budget)):
            yield cue_start / 1000, cue_end / 1000, cue
            cue = ""
        if not text:
            continue
        if not cue:
            cue_start = start
        cue += (" " if cue and spaced else "") + text
        cue_end = end
        if automatic and text.rstrip('"”’)').endswith((".", "!", "?", "。", "！", "？")):
            yield cue_start / 1000, cue_end / 1000, cue
            cue = ""
    if cue:
        yield cue_start / 1000, cue_end / 1000, cue


def parse_srt(srt_path: Path, duration: float | None = None, *, automatic=False, fetch_text=None):
    """Read native JSON3, VTT or SRT. Unknown and manual tracks retain every cue."""
    content = srt_path.read_text(encoding="utf-8-sig", errors="replace")
    if srt_path.suffix == ".json3":
        try:
            entries = list(_json3_entries(content, automatic=automatic))
        except (ValueError, OverflowError, RecursionError):
            entries = []
        if not entries:
            alternates = [srt_path.with_suffix(ext) for ext in (".vtt", ".srt")]
            if fetch_text and not any(path.is_file() for path in alternates):
                fetch_text()
            for alternate in alternates:
                if alternate.is_file():
                    entries = list(parse_srt(alternate, duration, automatic=automatic))
                    if entries:
                        yield from entries
                        return
    else:
        raw = []
        for block in re.split(r"\n\s*\n", content.strip()):
            lines = block.splitlines()
            if lines and re.match(r"^(?:WEBVTT|NOTE|STYLE|REGION)(?:\s|$)", lines[0].strip()):
                continue
            for i, line in enumerate(lines[:2]):
                match = _CUE_RANGE.match(line.strip())
                if match:
                    start, end = map(_seconds, match.groups())
                    raw.append((start, end, "\n".join(lines[i+1:])))
                    break
        entries = [(raw[i][0], raw[i][1], text)
                   for i, text in caption_window_text(raw, automatic=automatic)]
    if duration and duration > 0:
        kept = [(s, min(e, duration), t) for s, e, t in entries if s < duration]
        if len(kept) < len(entries):
            logging.getLogger(__name__).info(
                "dropped %d caption cue(s) past the %.0fs video", len(entries) - len(kept), duration)
        entries = kept
    yield from entries


_ENGLISH_KEYS = ("en", "en-US", "en-GB", "en-orig")


def english_caption_track(metadata, youtube):
    """Choose one known track so yt-dlp cannot silently substitute a manual one."""
    if youtube:
        for table, kind in (("subtitles", "captions"), ("automatic_captions", "auto_captions")):
            keys = ("en-orig", "en", "en-US", "en-GB") if kind == "auto_captions" else _ENGLISH_KEYS
            tracks = metadata.get(table) or {}
            regional = (k for k in tracks if isinstance(k, str) and re.fullmatch(r"en(?:-[a-z0-9]{1,8})+", k, re.I))
            for key in (*keys, *regional):
                if tracks.get(key):
                    return {"key": key, "kind": kind}
    return None


def video_caption_prefix(track):
    # An older capture may still have video.en.srt of unknown origin.
    return "video.auto" if track and track["kind"] == "auto_captions" else "video"


def caption_args(track, *, text_only=False):
    if track is None:
        return ["--write-auto-subs", "--write-subs", "--sub-lang", ",".join(_ENGLISH_KEYS),
                "--convert-subs", "srt"]
    auto = track["kind"] == "auto_captions"
    formats = ("vtt/srt" if text_only else "json3/vtt/srt") if auto else "vtt/srt/best"
    return ["--write-auto-subs" if auto else "--write-subs", "--sub-lang", track["key"],
            "--sub-format", formats,
            *([] if auto else ["--convert-subs", "srt"])]


def caption_file(folder, prefix, track, *, text_only=False):
    if track:
        formats = ("srt", "vtt")
        if track["kind"] == "auto_captions":
            formats = ("vtt", "srt") if text_only else ("json3", "vtt", "srt")
        for ext in formats:
            file = folder / f"{prefix}.{track['key']}.{ext}"
            if file.is_file():
                return file
        return None
    files = sorted(folder.glob(f"{prefix}*.srt"))
    for key in _ENGLISH_KEYS:
        file = folder / f"{prefix}.{key}.srt"
        if file in files:
            return file
    return files[0] if files else None


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
    track = english_caption_track(metadata, metadata.get("extractor_key") == "Youtube")
    folder = out_root / slugify(title)
    folder.mkdir(exist_ok=True)
    print(f"-> {folder}")

    print("Downloading video + subtitles...")
    subprocess.run(
        [
            *ytdlp,
            *caption_args(track),
            "-f", (_platform.video_format("worst[height>=360]/worst")
                   if sys.platform == "darwin" else "worst[height>=360]/worst"),
            "-o", str(folder / "video.%(ext)s"),
            "-o", "subtitle:" + str(folder / (video_caption_prefix(track) + ".%(ext)s")),
            args.url,
        ],
        check=True,
    )

    video_files = [f for f in folder.glob("video.*") if f.suffix in (".mp4", ".webm", ".mkv")]
    subtitle = caption_file(folder, video_caption_prefix(track), track)
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

    def fetch_text():
        subprocess.run([*ytdlp, "--skip-download", *caption_args(track, text_only=True),
                        "-o", str(folder / (video_caption_prefix(track) + ".%(ext)s")), args.url], check=True)

    entries = list(parse_srt(subtitle, automatic=bool(track and track["kind"] == "auto_captions"),
                             fetch_text=fetch_text)) if subtitle else []

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
