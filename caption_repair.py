"""Opt-in repair of one saved YouTube transcript, using the capture publisher."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import clips
import library_cards
import library_media as media
import yt_extract
from uoink_core.storage import checked_path, read_checked_bytes


def _check_track(side, video_id):
    if (side.get("video_id") != video_id or side.get("transcript_source") != "captions"
            or media._youtube_video_id(side.get("source_url") or side.get("url")) != video_id):
        raise ValueError("This item has no saved YouTube caption track.")
    for key in ("caption_kind", "caption_track_kind"):
        if side.get(key) not in (None, "auto_captions"):
            raise ValueError("This track is marked as manual or has an unknown track type.")


def _clean_rows(side):
    rows = side.get("transcript")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("text"), str)
        or any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k])
               for k in ("start", "end"))
        or not 0 <= row["start"] <= row["end"] or row.get("words") or row.get("speaker")
        or row.get("speaker_provenance") for row in rows
    ):
        raise ValueError("This track has word timings, speaker labels or unsupported cues.")
    entries = [(row["start"], row["end"], row["text"]) for row in rows]
    clean = yt_extract.clean_caption_windows(entries, stored=True)
    words = sum(len(row["text"].split()) for row in rows)
    removed = words - sum(len(text.split()) for _, _, text in clean)
    shifted = sum(text != row["text"] for (_, _, text), row in zip(clean, rows, strict=True))
    # Stored plain cues lack the original word clocks. Require four advancing
    # windows, eight removed words, and evidence covering 20% of this track.
    if shifted < 4 or removed < 8 or removed * 5 < words:
        raise ValueError("Too little evidence of rolling captions to repair this transcript.")
    return [dict(row, text=text) for row, (_, _, text) in zip(rows, clean)], removed


_UNSUPPORTED_CHAPTERS = "Cannot verify this save's chapter layout. Its files were kept."
_CHAPTER_SECTION_END = re.compile(rb"(?:\r?\n)*(?:\Z|---(?:\r?\n|\Z))")


def _legacy_chapters(source, folder, inputs, root):
    chapters = source.get("source_chapters") or source.get("chapters")
    if chapters:
        return chapters
    # Older captures put yt-dlp's chapter ranges in the sibling metadata file.
    path = folder / "metadata.json"
    if path.is_symlink() or not path.is_file() or path.resolve().parent != folder.resolve():
        raise ValueError(_UNSUPPORTED_CHAPTERS)
    try:
        inputs[path] = read_checked_bytes(root, path, limit=yt_extract.MAX_CAPTION_BYTES)
        data = json.loads(inputs[path])
    except (media.MediaError, ValueError, RecursionError) as exc:
        raise ValueError(_UNSUPPORTED_CHAPTERS) from exc
    if not isinstance(data, dict) or data.get("id", source["video_id"]) != source["video_id"]:
        raise ValueError(_UNSUPPORTED_CHAPTERS)
    return data.get("chapters")


def _legacy_chapter_section(rows, chapters):
    """Render the old chapter headings with each cue in its verified range."""
    if not chapters:
        raise ValueError(_UNSUPPORTED_CHAPTERS)
    lines = ["## Transcript", ""]
    pos = 0
    for chapter in chapters:
        start, end = chapter["start"], chapter["end"]
        lines.extend([f"### Chapter: {chapter['title']} ({yt_extract.fmt_time(start)})", ""])
        while pos < len(rows) and rows[pos]["start"] < end:
            row = rows[pos]
            if row["start"] < start:
                raise ValueError(_UNSUPPORTED_CHAPTERS)
            lines.append(f"[{yt_extract.fmt_time(row['start'])}] {row['text']}")
            pos += 1
        lines.append("")
    if pos != len(rows):
        raise ValueError(_UNSUPPORTED_CHAPTERS)
    return "\n".join(lines)


def _markdown_after_repair(corpus, old_sections, new, *, retry, grouped=False):
    newline = b"\r\n" if b"\r\n" in corpus else b"\n"
    def section(text):
        return text.rstrip("\n").encode().replace(b"\n", newline)
    new = section(new)
    candidates = [section(old) for old in old_sections]
    for candidate in candidates + ([new] if retry else []):
        if candidate and corpus.count(candidate) == 1:
            start = corpus.index(candidate)
            end = start + len(candidate)
            if grouped and not _CHAPTER_SECTION_END.match(corpus, end):
                continue  # An additional chapter or cue is outside the verified layout.
            if (start == 0 or corpus[start - 1:start] == b"\n") and (
                    end == len(corpus) or corpus.startswith((b"\n", b"\r\n"), end)):
                return corpus[:start] + new + corpus[end:]
    raise ValueError(_UNSUPPORTED_CHAPTERS if grouped else
                     "The saved caption section has changed. Your edits were kept.")


def repair(idx, item, build_plan, *, root, dry_run=True):
    video_id = item["video_id"]
    if item.get("platform") != "youtube":
        raise ValueError("Caption repair is only available for saved YouTube videos.")
    side_path = checked_path(root, Path(item["sidecar_path"]))
    folder = side_path.parent
    corpus_path = checked_path(root, Path(item["corpus_path"]))
    plain = folder / "transcript.txt"
    archive = folder / media.MEDIA_INPUTS_DIR
    if any(checked_path(root, p).parent != folder for p in (corpus_path, plain, archive)):
        raise ValueError("A transcript file has moved outside the saved item.")
    side_raw = read_checked_bytes(root, side_path)
    current = media._parse_json_object(side_raw, "sidecar")
    _check_track(current, video_id)
    backups = list(folder.glob("captions-before-*.bak"))
    if len(backups) > 1:
        raise ValueError("This item has several original caption backups.")
    if backups:
        backup = backups[0]
        if backup.is_symlink() or not backup.is_file():
            raise ValueError("The original caption backup has moved.")
        original = read_checked_bytes(root, backup)
    else:
        original = side_raw
    backup_path = folder / ("captions-before-" + hashlib.sha256(original).hexdigest() + ".bak")
    if backups and backup != backup_path:
        raise ValueError("The original caption backup has changed.")
    source = media._parse_json_object(original, "sidecar")
    _check_track(source, video_id)
    rows, removed = _clean_rows(source)
    target = dict(source, transcript=rows)
    corpus_before = read_checked_bytes(root, corpus_path)
    old_block = source.get("media_depth")
    grouped = old_block is None and re.search(
        rb"(?m)^## Transcript\r?\n\r?\n### Chapter: ", corpus_before) is not None
    inputs = {side_path: side_raw, corpus_path: corpus_before, backup_path: original if backups else None}
    if grouped:
        target["source_chapters"] = _legacy_chapters(source, folder, inputs, root)
    # A retry can find either carrier on disk. Reconstruct from the backup
    # every time so a second pass cannot trim a newly exposed spoken repeat.
    is_target = current.get("transcript") == rows
    expected = target if is_target else source
    if (current.get("transcript") != expected["transcript"]
            or media.capture_sidecar_inputs(current) != media.capture_sidecar_inputs(expected)):
        raise ValueError("The saved captions have changed since the original backup.")
    # A legacy save needs an explicit chapter list to build its first snapshot.
    source_for_plan = dict(source, source_chapters=target.get("source_chapters", []))
    old_plan = build_plan(source_for_plan, folder, item=item)
    old_sections = [old_plan["markdown"], media.capture_markdown_3180(old_plan, source["transcript"])]
    if old_block is not None:
        media.validate_media_block(old_block)
        if (old_block["diarization_state"] != "not_requested"
                or old_block["cue_revision"] != old_plan["block"]["cue_revision"]
                or old_block["chapters"] != old_plan["block"]["chapters"]):
            raise ValueError("The saved captions or chapters have changed. Your edits were kept.")
    elif not grouped and not source.get("source_chapters"):
        old_sections.append("## Transcript\n\n" + "\n".join(
            f"[{yt_extract.fmt_time(int(r['start']))}] {r['text']}" for r in source["transcript"]))
    plan = build_plan(dict(source_for_plan, transcript=rows), folder, item=item)
    new_section = plan["markdown"]
    if grouped:
        chapters = old_plan["block"]["chapters"]
        old_sections = [_legacy_chapter_section(source["transcript"], chapters)]
        new_section = _legacy_chapter_section(rows, chapters)
    corpus = _markdown_after_repair(corpus_before, old_sections, new_section, retry=bool(backups), grouped=grouped)
    head = corpus[:library_cards.CORPUS_READ_BYTES].decode("utf-8", "replace")
    row = media._merge_item(item)
    revision = library_cards.build_card(row, clips.merge_cues(plan["cues"], row), corpus_text=head)["source_revision"]
    block, digest = media.capture_snapshot(
        video_id=video_id, source_revision=revision, cues=plan["cues"], artifact_bytes=plan["artifact"],
        corpus_revision=hashlib.sha256(corpus).hexdigest(), playback=plan["playback"],
        transcript_kind=plan["transcript_kind"], transcript_provider=plan["transcript_provider"],
        chapter_rows=plan["chapter_rows"], recorded_at=source.get("yoinked_at"), item=item)
    expected_block = block if is_target else old_block
    if current.get("media_depth") != expected_block:
        raise ValueError("The published transcript has changed since this capture.")
    repaired = dict(current, transcript=rows, media_depth=block)
    if grouped:
        repaired["source_chapters"] = target["source_chapters"]
    artifacts = {backup_path: original, corpus_path: corpus, archive / (digest + ".json"): plan["artifact"],
                 side_path: json.dumps(repaired, ensure_ascii=False, indent=2).encode()}
    plain_before = read_checked_bytes(root, plain) if plain.is_file() else None
    inputs[plain] = plain_before
    if plain_before is not None:
        newline = b"\r\n" if b"\r\n" in plain_before else b"\n"
        old_plain = "\n".join(r["text"] for r in source["transcript"]).encode()
        new_plain = "\n".join(r["text"] for r in rows).encode()
        normalized = plain_before.replace(b"\r\n", b"\n")
        if normalized != old_plain and not (backups and normalized == new_plain):
            raise ValueError("The saved transcript.txt has changed. Your edits were kept.")
        artifacts[plain] = new_plain.replace(b"\n", newline)

    ticket = idx.begin_media_publication(video_id, folder=folder, root=root,
                                         capture_binding=media.capture_sidecar_inputs(current), input_files=inputs)
    old_revision = old_block["media_revision"] if old_block else None
    if ticket.base_media_revision not in (old_revision, block["media_revision"]):
        raise ValueError("A newer capture replaced these captions.")
    if backups and is_target and ticket.base_media_revision != block["media_revision"]:
        raise ValueError("The caption backup does not match the published transcript.")
    with idx.detached_snapshot() as conn:
        saved = conn.execute("SELECT media_revision FROM media_depth WHERE video_id=?", (video_id,)).fetchone()
        if not old_block and not is_target:
            existing = media._load_cues(conn, video_id)
            indexed_text = [(r["timestamp_start"], r["timestamp_end"], r["text"]) for r in existing]
            held_text = [(r["start"], r["end"], r["text"]) for r in source["transcript"]]
            if existing and indexed_text != held_text:
                raise ValueError("The indexed captions differ from the saved transcript.")
    settled = is_target and saved is not None and saved[0] == block["media_revision"]
    if not settled:
        idx.publish_media_snapshot(video_id, cues=plan["cues"], media_block=block, artifacts=artifacts,
                                   ticket=ticket, dry_run=dry_run)
    return {"ok": True, "video_id": video_id, "dry_run": dry_run, "removed_words": 0 if settled else removed,
            "original_sidecar": str(backup_path)}
