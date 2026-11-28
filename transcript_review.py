"""Keep the original cue and its position while publishing only reviewed speech."""
from __future__ import annotations

from contextlib import contextmanager
from itertools import groupby
from pathlib import Path
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from uoink_core.storage import checked_path, open_regular, read_checked_json, unlink_regular


SCORES = ("no_speech_prob", "avg_logprob", "compression_ratio")
# Exact whole lines reported in openai/whisper discussions 171 and 293,
# and amicalhq/amical issue 71. Never substring-match a speaker discussing one.
_PHRASES = {
    "thank you", "thanks for watching", "thank you for watching",
    "please like and subscribe", "subtitles by the amara org community",
    "sottotitoli creati dalla comunità amara org",
    "sous titres réalisés par l amara org", "ご視聴ありがとうございました",
}
_LABEL = re.compile(r"(?:\[[^][\n]{1,100}\]|\([^()\n]{1,100}\))")
_SOUNDS = {"music", "applause", "door closes", "door opens", "laughter", "laughs",
           "cheering", "silence", "inaudible", "background music", "instrumental",
           "footsteps", "clapping", "crowd cheering", "door slams", "phone rings",
           "sighs", "gasps", "coughs", "music playing", "soft music", "upbeat music",
           "musique", "applaudissements", "música", "aplausos"}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def scores(row):
    return {key: row[key] for key in SCORES if _number(row.get(key))}


def _normalized(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def _label(text, note_wrapped):
    if note_wrapped:
        text = text[1:-1].strip()
        if not text.strip("♪♫… .\t\n") or text.casefold() in _SOUNDS:
            return True
    matches = _LABEL.findall(text)
    return bool(matches and not _LABEL.sub("", text).strip()
                and all(_normalized(label) in _SOUNDS for label in matches))


def repeated_phrase(tokens):
    """Start and width of a 2–8 word phrase repeated at least four times."""
    for offset in range(min(2, len(tokens))):
        for width in range(2, min(8, (len(tokens) - offset) // 4) + 1):
            candidate = tokens[offset:offset + width]
            if (len(set(candidate)) > 1 and
                    all(t == candidate[j % width] for j, t in enumerate(tokens[offset:]))):
                return offset, width
    return None


def reasons(rows, *, whisper, duration=None):
    """One decision per original ordinal. Missing scores are unknown, never zero."""
    result = []
    repeats = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            row = {}
        text = str(row.get("text") or "").strip()
        key = _normalized(text)
        tokens = key.split()
        restored = row.get("review_restored") is True
        score = scores(row)
        silence = score.get("no_speech_prob")
        confidence = score.get("avg_logprob")
        ratio = score.get("compression_ratio", 0)
        # Low silence (<= .20) or a healthy logprob (>= -.50) independently
        # protects speech. The last cue must end within 2 s of the audio end.
        end = row.get("end")
        # The decoder can know the audio duration before the library does.
        at_end = i == len(rows) - 1 and (
            (_number(end) and _number(duration) and duration > 0 and abs(duration - end) <= 2)
            or (duration is None and row.get("held_reason") == "outro"))
        reason = None
        clear = ((silence is not None and silence <= .20)
                 or (confidence is not None and confidence >= -.50))
        note_wrapped = bool(text and text[0] in "♪♫" and text[-1] in "♪♫")
        if not restored and _label(text, note_wrapped):
            reason = "non_speech"
        # Words enclosed in musical notes are lyrics, even on a noisy recording.
        candidate = whisper and not restored and not note_wrapped and not clear and reason is None
        if candidate:
            if silence is not None and silence > .60 and confidence is not None and confidence < -1:
                reason = "low_confidence"
            elif key in _PHRASES:
                if silence is not None and silence >= .40 and confidence is not None and confidence < -1:
                    reason = "silent_phrase"
                elif at_end and key != "thank you":
                    reason = "outro"
            # Four cycles inside one cue also need silence and high compression.
            if (ratio > 2.4 and silence is not None and silence > .60
                    and not _emphasis_or_count(tokens) and repeated_phrase(tokens)):
                reason = "repetition"
        result.append(reason)
        # Three consecutive copies, each short (<=8 words / 80 characters)
        # and each over 2.4 compression. Clear speech breaks the run.
        short = 0 < len(key) <= 80 and len(tokens) <= 8 and not _emphasis_or_count(tokens)
        repeats.append(key if candidate and short and ratio > 2.4 else None)
    for key, group in groupby(enumerate(repeats), key=lambda item: item[1]):
        indices = [i for i, _ in group]
        if key and len(indices) >= 3:
            for i in indices:
                result[i] = result[i] or "repetition"
    return result


def _emphasis_or_count(tokens):
    counts = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}
    return all(t.isdecimal() or t in counts for t in tokens) or (len(tokens) > 1 and len(set(tokens)) == 1)


def partition(rows, *, whisper, duration=None):
    kept, held = [], []
    for line, (row, reason) in enumerate(zip(rows, reasons(rows, whisper=whisper, duration=duration)), 1):
        if reason:
            held.append({"line": line, "reason": reason, "segment": row})
        else:
            kept.append(row)
    return kept, held


def all_rows(kept, held):
    """Linear-time reconstruction, including equal timestamps."""
    by_line = {h["line"]: h["segment"] for h in held}
    if len(by_line) != len(held) or any(type(i) is not int or not 1 <= i <= len(kept) + len(held)
                                        for i in by_line):
        raise ValueError("The saved held-line numbers are invalid.")
    visible = iter(kept)
    return [by_line[i] if i in by_line else next(visible)
            for i in range(1, len(kept) + len(by_line) + 1)]


def reviewed_fields(rows, *, whisper, duration=None, field="transcript"):
    kept, held = partition(rows, whisper=whisper, duration=duration)
    return {field: kept, **({"held_transcript_lines": held} if held else {})}


def held_cue(segment):
    """Return the original timed text if a saved held segment is readable."""
    if not isinstance(segment, dict):
        return None
    start, end, text = segment.get("start"), segment.get("end"), segment.get("text")
    if not _number(start) or not isinstance(text, str) or not text.strip():
        return None
    return start, end if _number(end) else start, text


def notice(held):
    invented = sum(h["reason"] != "non_speech" for h in held)
    labels = len(held) - invented
    parts = []
    if invented:
        parts.append(f"Uoink held back {invented} {'line' if invented == 1 else 'lines'} "
                     "it thinks Whisper made up in silence.")
    if labels:
        parts.append(f"Uoink held back {labels} non-speech {'label' if labels == 1 else 'labels'}.")
    return " ".join(parts)


def _decision(record, field, whisper, duration, restore):
    kept = record.get(field) or []
    held = record.get("held_transcript_lines") or []
    if restore is None:
        return partition(all_rows(kept, held) if held else kept, whisper=whisper, duration=duration)
    if not any(h["line"] == restore for h in held):
        raise ValueError("That line is not held in this item.")
    original = all_rows(kept, held)
    original[restore - 1] = dict(original[restore - 1], review_restored=True)
    original[restore - 1].pop("held_reason", None)
    held = [h for h in held if h["line"] != restore]
    hidden = {h["line"] for h in held}
    return [s for n, s in enumerate(original, 1) if n not in hidden], held


def last_summary(root):
    try:
        with open_regular(root, Path(root) / "transcript-review-summary.txt") as source:
            return source.read()
    except (OSError, UnicodeError):
        return None


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _changed_lines(before, after):
    return len({h["line"] for h in before} ^ {h["line"] for h in after})


class _PublicationPending(RuntimeError):
    """The edited files are on disk and this item still needs to be indexed."""


@contextmanager
def _publishing():
    try:
        yield
    except Exception as exc:
        raise _PublicationPending(str(exc)) from exc


def _generated_section(markdown, section):
    if not section or markdown.count(section) != 1:
        return False
    start = markdown.index(section)
    end = start + len(section)
    return (start == 0 or markdown[start - 1] == "\n") and (end == len(markdown) or markdown[end] == "\n")


def _review_capture(server, item, path, side, kept, held, pending):
    """Write intent first. A stopped CLI can settle each output on its next run."""
    folder = path.parent
    root = server.DESKTOP_ROOT
    corpus = checked_path(root, Path(item["corpus_path"]))
    plain = checked_path(root, folder / "transcript.txt")
    if corpus.parent != folder:
        raise ValueError("A transcript file has moved.")
    def read_text(file):
        with open_regular(root, file) as source:
            return source.read()

    if not pending:
        new = dict(side, transcript=kept, held_transcript_lines=held)
        # A legacy capture gets a first media snapshot, including an all-held item.
        new.setdefault("source_chapters", [])
        new["health"] = server.compute_health(new)
        old_text = server._transcript_text_from_sidecar(side)
        if plain.exists() and read_text(plain).strip() != old_text.strip():
            raise ValueError("The plain transcript has edits. Its files were kept.")
        md = read_text(corpus)
        old_plan = server._capture_media_plan(side, folder, item=item)
        plan = server._capture_media_plan(new, folder, item=item)
        old_block = old_plan["markdown"].rstrip() if old_plan else None
        if not _generated_section(md, old_block):
            # Formats before the media snapshot: replace only the exact
            # transcript block generated from these rows, never the rest of the file.
            entries = side.get("transcript") or []
            legacy, _ = server._transcript_backfill_render(folder, side)
            from library_media import capture_markdown_3180
            historical = capture_markdown_3180(old_plan, entries).rstrip() if old_plan else None
            candidates = [historical, legacy.rstrip(), "## Transcript\n\n" + "\n".join(
                f"- [{server.fmt_time(int(r['start']))}] {r['text']}" for r in entries)]
            old_block = next((b for b in candidates if _generated_section(md, b)), None)
        if not old_block:
            raise ValueError("The saved transcript section has edits. Its files were kept.")
        updated = md.replace(old_block, plan["markdown"].rstrip(), 1)
        pending = {"after": _digest(updated),
                   "changed": _changed_lines(side.get("held_transcript_lines") or [], held),
                   "old_block": old_block, "new_block": plan["markdown"].rstrip(),
                   "old_plain": _digest(old_text.strip())}
        new["pending_transcript_review"] = pending
        if "reliability" in new:
            new["reliability"] = {"status": "not_computed", "spans": [], "span_count": 0}
        server._atomic_write_text(path, json.dumps(new, ensure_ascii=False, indent=2), root=root)
        side = new
    with server._corpus_update_lock:
        md = read_text(corpus)
        if _digest(md) != pending["after"]:
            old, new = pending["old_block"], pending["new_block"]
            if not _generated_section(md, old):
                if not _generated_section(md, new):
                    raise ValueError("The saved transcript section changed during review.")
            else:
                server._atomic_write_text(corpus, md.replace(old, new, 1), root=root)
    if plain.exists():
        target = server._transcript_text_from_sidecar(side)
        current = read_text(plain).strip()
        if current != target.strip():
            if _digest(current) != pending["old_plain"]:
                raise ValueError("The plain transcript changed during review.")
            server._atomic_write_text(plain, target, root=root)
    with _publishing():
        server._index_yoink(folder, side, corpus, path, require_media_update=True)
    latest = read_checked_json(root, path)
    if latest.get("pending_transcript_review") != pending:
        raise ValueError("The transcript changed during review.")
    latest.pop("pending_transcript_review")
    server._atomic_write_text(path, json.dumps(latest, ensure_ascii=False, indent=2), root=root)


def _episode_review(server, item, side, restore, write):
    """Use the original producer file and the podcast's own fenced publisher."""
    import library_media
    import podcasts
    idx = server._get_index()
    episode_id = json.loads(item["metadata_json"])["episode_id"]
    root = podcasts.podcast_storage(server.DATA_ROOT)
    producer = podcasts.episode_media_path(idx, episode_id, server.DATA_ROOT, transcript=True)
    raw = read_checked_json(root, producer)
    duration = side.get("duration_seconds")
    before = raw.get("held_transcript_lines") or []
    published = side.get("held_transcript_lines") or []
    # Do not pair a stale sidecar with a different transcription.
    def signature(record, field):
        return [(s.get("start"), s.get("end"), s.get("text")) for s in
                all_rows(record.get(field) or [], record.get("held_transcript_lines") or [])]
    if signature(raw, "segments") != signature(side, "transcript"):
        raise ValueError("This episode has a newer transcript. Publish it before reviewing.")
    # A stop between producer write and publication leaves two complete
    # versions; the next apply finishes publishing the producer.
    pending = [h["line"] for h in before] != [h["line"] for h in published]
    if pending and restore is not None:
        with _publishing():
            podcasts.episode_to_corpus(idx, episode_id, data_root=server.DATA_ROOT)
        if not any(h["line"] == restore for h in before):
            if any(h["line"] == restore for h in published):
                return len(before), 1  # finish an interrupted restore of this very line
            raise ValueError("That line is not held in this item.")
        pending = False
    kept, held = (raw["segments"], before) if pending else _decision(
        raw, "segments", True, duration, restore)
    if write and (held != before or pending):
        if not pending:
            run = raw.get("diarization_run")
            valid = isinstance(run, dict) and run.get("artifact_sha256") == hashlib.sha256(
                library_media.transcript_artifact_bytes(raw)).hexdigest()
            raw.update(segments=kept, held_transcript_lines=held)
            if valid:
                run["artifact_sha256"] = hashlib.sha256(library_media.transcript_artifact_bytes(raw)).hexdigest()
            server._atomic_write_text(producer, json.dumps(raw, ensure_ascii=False, indent=2), root=root)
        with _publishing():
            podcasts.episode_to_corpus(idx, episode_id, data_root=server.DATA_ROOT)
    return len(held), _changed_lines(published, held)


def _item_review(server, item, restore, write):
    from contextlib import nullcontext
    from source_subscriptions import CaptureLock

    if not item.get("sidecar_path") and restore is None:
        return 0, 0
    path = Path(item.get("sidecar_path") or "")
    episode = item.get("source_type") == "episode"
    root = server._item_storage_root(item)
    path = checked_path(root, path)
    if not episode and not server._transcript_backfill_inside_library(path):
        raise ValueError("The transcript is outside the library.")
    if not path.is_file():
        if restore:
            raise ValueError("This save has no transcript file.")
        return 0, 0
    side = read_checked_json(root, path)
    if not isinstance(side, dict) or not (side.get("transcript") or side.get("held_transcript_lines")
                                           or side.get("pending_transcript_review")):
        if restore:
            raise ValueError("This save has no held lines.")
        return 0, 0
    if side.get("video_id") != item["video_id"]:
        raise ValueError("The transcript belongs to another item.")
    if write:
        url = side.get("source_url") or side.get("url") or item["video_id"]
        key = side.get("capture_key") if episode else None
        lock = CaptureLock.try_acquire(server.DATA_ROOT, key or server._manual_capture_key(url))
        if lock is None:
            raise ValueError("A capture is using this item. Run the command again when it finishes.")
    else:
        lock = nullcontext()
    with lock, server._sidecar_update_lock:
        if write and read_checked_json(root, path) != side:
            raise ValueError("The transcript changed during review.")
        if episode:
            return _episode_review(server, item, side, restore, write)
        before = side.get("held_transcript_lines") or []
        pending = side.get("pending_transcript_review")
        if pending and restore is not None:
            _review_capture(server, item, path, side, side["transcript"], before, pending)
            side = read_checked_json(root, path)
            rows = all_rows(side["transcript"], before)
            if 1 <= restore <= len(rows) and rows[restore - 1].get("review_restored"):
                return len(before), 1
            pending = None
        if pending:
            kept, held = side["transcript"], before
        else:
            kept, held = _decision(side, "transcript", side.get("transcript_source") == "asr",
                                   side.get("duration_seconds"), restore)
        if write and (held != before or pending):
            _review_capture(server, item, path, side, kept, held, pending)
        return len(held), pending.get("changed", 0) if pending else _changed_lines(before, held)


def tidy(server, *, apply=False, restore=None):
    """Foreground CLI work. Committed items survive Ctrl+C and helper restarts."""
    from library_media import MediaError
    from source_subscriptions import CaptureLock
    idx = server._get_index()
    if restore:
        item = idx.get_yoink(restore[0])
        if not item or item.get("deleted_at"):
            raise ValueError("Saved item not found.")
        line = int(restore[1])
        if line < 1:
            raise ValueError("Line numbers start at 1.")
        try:
            _item_review(server, item, line, True)
        except (MediaError, sqlite3.Error, _PublicationPending) as exc:
            raise ValueError(str(exc)) from exc
        return {"ok": True, "review_summary": f"Restored line {line} to the transcript and search."}
    lock = CaptureLock.try_acquire(server.DATA_ROOT, "tidy-transcripts")
    if lock is None:
        raise ValueError("A transcript review is already running.")
    mode = "apply" if apply else "dry-run"
    with lock:
        checkpoint = checked_path(server.DATA_ROOT, Path(server.DATA_ROOT) / f"transcript-review-{mode}.json")
        summary_path = checked_path(server.DATA_ROOT, Path(server.DATA_ROOT) / "transcript-review-summary.txt")
        progress = {"cursor": "", "held": 0, "changed": 0, "errors": [], "root": str(server.DESKTOP_ROOT)}
        if checkpoint.is_file():
            try:
                previous = read_checked_json(server.DATA_ROOT, checkpoint)
                if (not isinstance(previous, dict)
                        or any(type(previous.get(k)) is not type(v) for k, v in progress.items())
                        or previous["held"] < 0 or previous["changed"] < 0):
                    raise ValueError("invalid progress")
            except ValueError as exc:
                raise ValueError(f"Repair or remove the damaged checkpoint {checkpoint} "
                                 f"and run uoink tidy-transcripts --{mode} again.") from exc
            if previous.get("root") == progress["root"]:
                progress = previous
        # Commit progress between pages. Replaying a partial page is safe:
        # each item's intent or completed decision is already on disk.
        try:
            while True:
                with idx.read_snapshot() as db:
                    items = db.execute(
                        "SELECT video_id, title, slug, source_type, sidecar_path, corpus_path, metadata_json FROM yoinks "
                        "WHERE deleted_at IS NULL AND video_id>? ORDER BY video_id LIMIT 64",
                        (progress["cursor"],)).fetchall()
                if not items:
                    break
                for item in items:
                    try:
                        count, difference = _item_review(server, dict(item), None, apply)
                        progress["held"] += count
                        progress["changed"] += difference
                    except _PublicationPending as exc:
                        # Cursor and totals still describe the last completed item.
                        server._atomic_write_text(checkpoint, json.dumps(progress), root=server.DATA_ROOT)
                        message = (f"Publication stopped at {item['video_id']}. "
                                   f"Run uoink tidy-transcripts --{mode} to resume.")
                        return {"ok": False, "review_summary": message, "error": message,
                                "errors": [*progress["errors"], {"item": item["video_id"], "error": str(exc)}],
                                "held_count": progress["held"], "changed": progress["changed"]}
                    except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error, MediaError) as exc:
                        progress["errors"].append({"item": item["video_id"], "error": str(exc)})
                    progress["cursor"] = item["video_id"]
                server._atomic_write_text(checkpoint, json.dumps(progress), root=server.DATA_ROOT)
        except KeyboardInterrupt:
            server._atomic_write_text(checkpoint, json.dumps(progress), root=server.DATA_ROOT)
            raise ValueError(f"Review stopped. Run uoink tidy-transcripts --{mode} to resume.") from None
        total, changed, errors = progress["held"], progress["changed"], progress["errors"]
        action = "Changed" if apply else "Would change"
        summary = (f"Last review found {total} held or suspect {'line' if total == 1 else 'lines'}. "
                   f"{action} {changed} {'line' if changed == 1 else 'lines'}. "
                   "Without Whisper scores, only a known phrase at the end can be flagged as invented. "
                   "A scoreless closing ‘Thank you’ stays.")
        if errors:
            summary += f" {len(errors)} saves need another look."
        server._atomic_write_text(summary_path, summary, root=server.DATA_ROOT)
        if checkpoint.exists():
            unlink_regular(server.DATA_ROOT, checkpoint)
        return {"ok": not errors, "held_count": total, "changed": changed,
                "review_summary": summary, "errors": errors, **({"error": summary} if errors else {})}
