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
    return " ".join(text.split())


def caption_window_text(entries, *, automatic, stored=False):
    """Yield the original row number and its newly spoken text."""
    previous = None
    for i, (start, end, raw) in enumerate(entries):
        lines = raw.splitlines() if stored else [_clean_caption_text(line) for line in raw.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            if stored:
                yield i, raw
            continue
        words = " ".join(lines).split()
        skip = 0
        tags = set(_WORD_TIME.findall(raw))
        if automatic and previous:
            pstart, pend, plines, pwords, ptags, rolled = previous
            # A roll-up moves the last displayed line to the top as a new
            # line appears below it. A tiny bridge cue can repeat that line.
            adjacent = pstart <= start <= pend + 0.001
            ghost = 0 < end - start <= 0.015
            if adjacent and lines[0] == plines[-1] and (
                    (len(lines) >= 2 and lines != plines) or ghost):
                skip = len(lines[0].split())
            elif adjacent and (start < pend or ptags & tags):
                for size in range(min(len(pwords), len(words)), 0, -1):
                    if pwords[-size:] != words[:size]:
                        continue
                    # A whole line can be sung again even when the cues overlap.
                    # A shared start or word clock identifies the same utterance.
                    if start == pstart or ptags & tags or (size < len(pwords) and words != pwords):
                        skip = size
                    elif len(words) > size:
                        # A single extended opening can be anaphora. Look for
                        # another overlapping shift before treating it as a roll.
                        continuing = False
                        if i + 1 < len(entries):
                            ns, _, next_raw = entries[i + 1]
                            next_words = (next_raw if stored else _clean_caption_text(next_raw)).split()
                            continuing = (start < ns < end and next_words != words and any(
                                words[-n:] == next_words[:n] for n in range(2, min(len(words), len(next_words)) + 1)))
                        if rolled or continuing:
                            skip = size
                    break
        if skip < len(words):
            yield i, raw if stored and not skip else " ".join(words[skip:])
        previous = start, end, lines, words, tags, bool(skip)


def _json3_entries(content, *, automatic):
    """JSON3 timestamps identify displayed segments even when a window is replayed."""
    from collections import Counter
    seen = set()
    timed = []
    for event in json.loads(content).get("events", []):
        if "tStartMs" not in event or not event.get("segs"):
            continue
        base = event["tStartMs"]
        end = base + event.get("dDurationMs", 0)
        occurrences = Counter()
        for seg in event["segs"]:
            text = seg.get("utf8", "").strip()
            if not text:
                continue
            start = base + seg.get("tOffsetMs", 0)
            key = (start, text)
            occurrences[key] += 1
            identity = (*key, occurrences[key])
            if automatic and identity in seen:
                continue
            seen.add(identity)
            timed.append((start, max(start, end), text))
    timed.sort(key=lambda row: row[0])
    for i, (start, end, text) in enumerate(timed):
        if i + 1 < len(timed) and timed[i + 1][0] > start:
            end = min(end, timed[i + 1][0])
        yield start / 1000, end / 1000, text


def parse_srt(srt_path: Path, duration: float | None = None, *, automatic=False):
    """Read native JSON3, VTT or SRT. Unknown and manual tracks retain every cue."""
    content = srt_path.read_text(encoding="utf-8-sig", errors="replace")
    if srt_path.suffix == ".json3":
        entries = list(_json3_entries(content, automatic=automatic))
    else:
        raw = []
        for block in re.split(r"\n\s*\n", content.strip()):
            lines = block.splitlines()
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
            for key in keys:
                if (metadata.get(table) or {}).get(key):
                    return {"key": key, "kind": kind}
    return None


def video_caption_prefix(track):
    # An older capture may still have video.en.srt of unknown origin.
    return "video.auto" if track and track["kind"] == "auto_captions" else "video"


def caption_args(track):
    if track is None:
        return ["--write-auto-subs", "--write-subs", "--sub-lang", ",".join(_ENGLISH_KEYS),
                "--convert-subs", "srt"]
    auto = track["kind"] == "auto_captions"
    return ["--write-auto-subs" if auto else "--write-subs", "--sub-lang", track["key"],
            "--sub-format", "json3/vtt/srt" if auto else "vtt/srt/best",
            *([] if auto else ["--convert-subs", "srt"])]


def caption_file(folder, prefix, track):
    if track:
        formats = ("json3", "vtt", "srt") if track["kind"] == "auto_captions" else ("srt", "vtt")
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

    entries = list(parse_srt(subtitle, automatic=bool(track and track["kind"] == "auto_captions"))) if subtitle else []

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
