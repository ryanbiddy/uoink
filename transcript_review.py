"""Keep the original cue and its position while publishing only reviewed speech."""
from __future__ import annotations

from itertools import groupby
from pathlib import Path
import hashlib
import json
import math
import re
import sqlite3
import unicodedata


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


def _label(text):
    if text and text[0] in "♪♫" and text[-1] in "♪♫":
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
    last_silent = None
    silent_run = 0
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
        # Last cue only, ending within 2 s of the actual audio end. Silence
        # <= .20, or < .40 with logprob >= -.50, protects a spoken sign-off.
        end = row.get("end")
        at_end = (i == len(rows) - 1 and _number(end) and _number(duration)
                  and duration > 0 and abs(duration - end) <= 2)
        reason = None
        clear = silence is not None and (silence <= .20 or
                                         (silence < .40 and confidence is not None and confidence >= -.50))
        if restored:
            pass
        elif _label(text):
            reason = "non_speech"
        elif whisper:
            if row.get("held_reason") in ("outro", "silent_phrase", "repetition", "low_confidence"):
                reason = row["held_reason"]
            elif silence is not None and silence > .60 and confidence is not None and confidence < -1:
                reason = "low_confidence"
            elif key in _PHRASES and not clear:
                if silence is not None and silence >= .40:
                    reason = "silent_phrase"
                elif at_end:
                    reason = "outro"
            # Keep the earlier loop guard reversible. Over likely silence,
            # four cycles inside one cue, or a third identical short cue,
            # can indicate a loop even when the compression score is missing.
            if (silence is not None and silence > .60 and not _emphasis_or_count(tokens)
                    and repeated_phrase(tokens)):
                reason = "repetition"
        short = whisper and not restored and 0 < len(key) <= 80 and len(tokens) <= 8 and not _emphasis_or_count(tokens)
        silent_key = key if short and silence is not None and silence > .60 else None
        silent_run = silent_run + 1 if silent_key and silent_key == last_silent else 1
        last_silent = silent_key
        if silent_key and silent_run >= 3:
            reason = reason or "repetition"
        result.append(reason)
        # Three consecutive copies, each short (<=8 words / 80 characters)
        # and each over 2.4 compression. Clear speech breaks the run.
        repeats.append(key if short and not clear and ratio > 2.4 else None)
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
        if held:
            return kept, held
        return partition(kept, whisper=whisper, duration=duration)
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
        return (Path(root) / "transcript-review-summary.txt").read_text("utf-8")
    except (OSError, UnicodeError):
        return None


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _review_capture(server, item, path, side, kept, held, pending):
    """Write intent first. A stopped CLI can settle each output on its next run."""
    folder = path.parent
    corpus = Path(item["corpus_path"])
    plain = folder / "transcript.txt"
    if corpus.parent != folder or corpus.resolve() != corpus or plain.resolve() != plain:
        raise ValueError("A transcript file has moved.")
    if not pending:
        new = dict(side, transcript=kept, held_transcript_lines=held)
        # A legacy capture gets a first media snapshot, including an all-held item.
        new.setdefault("source_chapters", [])
        new["health"] = server.compute_health(new)
        old_text = server._transcript_text_from_sidecar(side)
        if plain.exists() and plain.read_text("utf-8").strip() != old_text.strip():
            raise ValueError("The plain transcript has edits. Its files were kept.")
        md = corpus.read_text("utf-8")
        old_plan = server._capture_media_plan(side, folder, item=item)
        plan = server._capture_media_plan(new, folder, item=item)
        old_block = old_plan["markdown"].rstrip() if old_plan else None
        if not old_block or md.count(old_block) != 1:
            # Formats before the media snapshot: replace only the exact
            # transcript block generated from these rows, never the rest of the file.
            entries = side.get("transcript") or []
            legacy, _ = server._transcript_backfill_render(folder, side)
            candidates = [legacy.rstrip(), "## Transcript\n\n" + "\n".join(
                f"- [{server.fmt_time(int(r['start']))}] {r['text']}" for r in entries)]
            old_block = next((b for b in candidates if b and md.count(b) == 1), None)
        if not old_block:
            raise ValueError("The saved transcript section has edits. Its files were kept.")
        updated = md.replace(old_block, plan["markdown"].rstrip(), 1)
        pending = {"after": _digest(updated),
                   "old_block": old_block, "new_block": plan["markdown"].rstrip(),
                   "old_plain": _digest(old_text.strip())}
        new["pending_transcript_review"] = pending
        if "reliability" in new:
            new["reliability"] = {"status": "not_computed", "spans": [], "span_count": 0}
        server._atomic_write_text(path, json.dumps(new, ensure_ascii=False, indent=2))
        side = new
    with server._corpus_update_lock:
        md = corpus.read_text("utf-8")
        if _digest(md) != pending["after"]:
            old, new = pending["old_block"], pending["new_block"]
            if md.count(old) != 1:
                if md.count(new) != 1:
                    raise ValueError("The saved transcript section changed during review.")
            else:
                server._atomic_write_text(corpus, md.replace(old, new, 1))
    if plain.exists():
        target = server._transcript_text_from_sidecar(side)
        current = plain.read_text("utf-8").strip()
        if current != target.strip():
            if _digest(current) != pending["old_plain"]:
                raise ValueError("The plain transcript changed during review.")
            server._atomic_write_text(plain, target)
    server._index_yoink(folder, side, corpus, path, require_media_update=True)
    latest = json.loads(path.read_text("utf-8"))
    if latest.get("pending_transcript_review") != pending:
        raise ValueError("The transcript changed during review.")
    latest.pop("pending_transcript_review")
    server._atomic_write_text(path, json.dumps(latest, ensure_ascii=False, indent=2))


def _episode_review(server, item, side, restore, write):
    """Use the original producer file and the podcast's own fenced publisher."""
    import library_media
    import podcasts
    idx = server._get_index()
    episode_id = json.loads(item["metadata_json"])["episode_id"]
    episode = podcasts.get_episode(idx, episode_id)
    producer = podcasts._owned_file(server.DATA_ROOT, episode["transcript_local_path"])
    if not producer:
        raise ValueError("The saved episode transcript file has moved.")
    raw = json.loads(producer.read_text("utf-8"))
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
            server._atomic_write_text(producer, json.dumps(raw, ensure_ascii=False, indent=2))
        podcasts.episode_to_corpus(idx, episode_id, data_root=server.DATA_ROOT)
    return len(held), abs(len(held) - len(published))


def _item_review(server, item, restore, write):
    from contextlib import nullcontext
    from source_subscriptions import CaptureLock

    if not item.get("sidecar_path") and restore is None:
        return 0, 0
    path = Path(item.get("sidecar_path") or "")
    episode = item.get("source_type") == "episode"
    root = (Path(server.DATA_ROOT) / "Podcasts").resolve()
    if not (path.is_relative_to(root) if episode else path.is_relative_to(server.DESKTOP_ROOT)):
        raise ValueError("The transcript is outside the library.")
    if path.resolve() != path or (not episode and not server._transcript_backfill_inside_library(path)):
        raise ValueError("The transcript is outside the library.")
    if not path.is_file():
        if restore:
            raise ValueError("This save has no transcript file.")
        return 0, 0
    side = json.loads(path.read_text("utf-8"))
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
        if write and json.loads(path.read_text("utf-8")) != side:
            raise ValueError("The transcript changed during review.")
        if episode:
            return _episode_review(server, item, side, restore, write)
        before = side.get("held_transcript_lines") or []
        pending = side.get("pending_transcript_review")
        if pending and restore is not None:
            _review_capture(server, item, path, side, side["transcript"], before, pending)
            side = json.loads(path.read_text("utf-8"))
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
        return len(held), abs(len(held) - len(before))


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
        except (MediaError, sqlite3.Error) as exc:
            raise ValueError(str(exc)) from exc
        return {"ok": True, "review_summary": f"Restored line {line} to the transcript and search."}
    lock = CaptureLock.try_acquire(server.DATA_ROOT, "tidy-transcripts")
    if lock is None:
        raise ValueError("A transcript review is already running.")
    mode = "apply" if apply else "dry-run"
    checkpoint = Path(server.DATA_ROOT) / f"transcript-review-{mode}.json"
    with lock:
        progress = {"cursor": "", "held": 0, "changed": 0, "errors": [], "root": str(server.DESKTOP_ROOT)}
        if checkpoint.is_file():
            previous = json.loads(checkpoint.read_text("utf-8"))
            if previous.get("root") == progress["root"]:
                progress = previous
        # Commit progress between pages. Replaying a partial page is safe:
        # each item's intent or completed decision is already on disk.
        try:
            while True:
                with idx.read_snapshot() as db:
                    items = db.execute(
                        "SELECT video_id, source_type, sidecar_path, corpus_path, metadata_json FROM yoinks "
                        "WHERE deleted_at IS NULL AND video_id>? ORDER BY video_id LIMIT 64",
                        (progress["cursor"],)).fetchall()
                if not items:
                    break
                for item in items:
                    try:
                        count, difference = _item_review(server, dict(item), None, apply)
                        progress["held"] += count
                        progress["changed"] += difference
                    except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error, MediaError) as exc:
                        progress["errors"].append({"item": item["video_id"], "error": str(exc)})
                    progress["cursor"] = item["video_id"]
                server._atomic_write_text(checkpoint, json.dumps(progress))
        except KeyboardInterrupt:
            server._atomic_write_text(checkpoint, json.dumps(progress))
            raise ValueError(f"Review stopped. Run uoink tidy-transcripts --{mode} to resume.") from None
        total, changed, errors = progress["held"], progress["changed"], progress["errors"]
        summary = (f"Last review found {total} held or suspect lines. "
                   + (f"{changed} newly held." if apply else f"{changed} would be newly held."))
        if errors:
            summary += f" {len(errors)} saves need another look."
        server._atomic_write_text(Path(server.DATA_ROOT) / "transcript-review-summary.txt", summary)
        checkpoint.unlink(missing_ok=True)
        return {"ok": not errors, "held_count": total, "changed": changed,
                "review_summary": summary, "errors": errors, **({"error": summary} if errors else {})}
