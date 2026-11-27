"""Exercise offline repair on files published by the real capture writer."""
from pathlib import Path
import json
import sqlite3
from types import SimpleNamespace

import pytest

import index
import library_media as media
import server
from tests.phase4_fixtures import seed_yoink_item


VID = "talk0000001"
SPOKEN = "the blue sky above us today shows stars before sunset beyond the far ridge"
WORDS = SPOKEN.split()
ROLLING = [(i, i + 3, " ".join(WORDS[2*i:2*i+6])) for i in range(5)]


@pytest.fixture
def library(tmp_path, monkeypatch):
    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "library")
        def save(entries=ROLLING, legacy=False, **fields):
            folder = server.DESKTOP_ROOT / VID
            folder.mkdir(parents=True)
            item = seed_yoink_item(idx, folder, video_id=VID, slug=VID, title="Evening sky")
            side = {"video_id": VID, "url": "https://www.youtube.com/watch?v=" + VID,
                    "transcript_source": "captions", "source_chapters": [], "duration_seconds": 20,
                    "yoinked_at": "2026-01-01T00:00:00Z", **fields}
            side["transcript"] = server._transcript_entries_with_links(side, entries)
            side_path = Path(item["sidecar_path"])
            corpus = Path(item["corpus_path"])
            plain = folder / "transcript.txt"
            if legacy:
                side.pop("source_chapters")
                side["transcript"] = [{"start": s, "end": e, "text": t} for s, e, t in entries]
            side_path.write_text(json.dumps(side), encoding="utf-8")
            section = ("## Transcript\n\n" + "\n".join(
                f"[{server.fmt_time(int(s))}] {t}" for s, _, t in entries) if legacy
                else server._capture_media_plan(side, folder)["markdown"])
            corpus.write_text("Notes\n" + section, encoding="utf-8")
            plain.write_text("\n".join(t for _, _, t in entries), encoding="utf-8")
            if not legacy:
                server._publish_capture_media(idx, folder, side, corpus, side_path)
            return side_path, corpus, plain
        yield idx, save


def _files(paths):
    return {p: p.read_bytes() for p in paths}


@pytest.mark.parametrize("kind,legacy", [(None, True), (None, False), ("auto_captions", False)])
def test_preview_apply_repeat_and_search(library, kind, legacy, monkeypatch):
    idx, save = library
    paths = save(legacy=legacy, **({"caption_kind": kind} if kind else {}))
    side, corpus, plain = paths
    with corpus.open("ab") as file:
        file.write(b"\nA note added after saving.\n")
    before = _files(paths)
    changed = []
    monkeypatch.setattr(idx, "_notify_source_changed", changed.append)
    preview = server.repair_rolling_captions(VID)
    backup = Path(preview["original_sidecar"])
    assert preview["dry_run"] and preview["removed_words"] == 16
    assert not backup.exists() and _files(paths) == before and changed == []
    result = server.repair_rolling_captions(VID, dry_run=False)
    assert not result["dry_run"] and result["removed_words"] == 16
    assert backup.parent == side.parent and backup.read_bytes() == before[side]
    assert corpus.read_bytes().endswith(b"A note added after saving.\n")
    repaired = json.loads(side.read_bytes())
    assert set(repaired) == set(json.loads(before[side])) | {"media_depth"}
    assert " ".join(r["text"] for r in repaired["transcript"]) == SPOKEN
    assert plain.read_text(encoding="utf-8").split() == WORDS
    assert [(r["start"], r["end"]) for r in repaired["transcript"]] == [(s, e) for s, e, _ in ROLLING]
    with idx.detached_snapshot() as conn:
        indexed = conn.execute("SELECT content FROM yoinks_fts WHERE video_id=?", (VID,)).fetchone()[0]
        cues = conn.execute("SELECT text FROM citations WHERE video_id=? "
                            "AND kind='transcript_chunk' ORDER BY seq", (VID,)).fetchall()
    assert indexed.encode() == corpus.read_bytes()
    assert " ".join(r[0] for r in cues) == SPOKEN
    assert changed == [VID]
    saved_track = server.get_transcript_cascade(VID)
    assert saved_track["source"] == "library"
    assert " ".join(t for _, _, t in saved_track["segments"]) == SPOKEN
    clean_files = _files(paths)
    assert server.repair_rolling_captions(VID, dry_run=False)["removed_words"] == 0
    assert _files(paths) == clean_files and backup.read_bytes() == before[side]
    assert changed == [VID]


@pytest.mark.parametrize("fields,entries,reason", [
    ({"caption_kind": "captions"}, ROLLING, "manual"),
    ({"caption_track_kind": "captions", "caption_kind": "auto_captions"}, ROLLING, "manual"),
    ({"caption_kind": "unknown"}, ROLLING, "unknown track type"),
    ({"transcript_source": "asr"}, ROLLING, "no saved YouTube"),
    ({}, [(0, 2, "we should go"), (1, 3, "go right now")], "Too little evidence"),
    ({}, ROLLING[:4], "Too little evidence"),
    ({}, ROLLING + [(8, 12, "later " * 80)], "Too little evidence"),
])
def test_refuses_before_writing(library, fields, entries, reason):
    _, save = library
    paths = save(entries, **fields)
    before = _files(paths)
    for dry_run in (True, False):
        with pytest.raises(ValueError, match=reason):
            server.repair_rolling_captions(VID, dry_run=dry_run)
    assert _files(paths) == before and not list(paths[0].parent.glob("*.bak"))


@pytest.mark.parametrize("edited", ["corpus", "plain", "timings", "chapters"])
def test_user_edits_kept_and_preview_matches_apply(library, edited):
    _, save = library
    side, corpus, plain = save()
    if edited == "plain":
        plain.write_text("my transcription", encoding="utf-8")
    elif edited == "corpus":
        corpus.write_bytes(corpus.read_bytes().replace(b"the blue sky", b"the night sky"))
    else:
        data = json.loads(side.read_bytes())
        if edited == "timings":
            data["transcript"][0]["words"] = [{"word": "the", "start": 0, "end": 0.3}]
        else:
            data["source_chapters"] = [{"title": "New chapter", "start_time": 0, "end_time": 2}]
        side.write_text(json.dumps(data), encoding="utf-8")
    before = _files((side, corpus, plain))
    for dry_run in (True, False):
        with pytest.raises(ValueError, match="edits|timings"):
            server.repair_rolling_captions(VID, dry_run=dry_run)
    assert before == _files((side, corpus, plain)) and not list(side.parent.glob("*.bak"))


@pytest.mark.parametrize("stop_at", ["backup", "corpus", "plain", "side", "db"])
def test_retry_after_interrupted_publication(library, monkeypatch, stop_at):
    idx, save = library
    side, corpus, plain = save()
    original = side.read_bytes()
    backup = Path(server.repair_rolling_captions(VID)["original_sidecar"])
    stop_path = {"backup": backup, "corpus": corpus, "plain": plain, "side": side}.get(stop_at)
    with monkeypatch.context() as interrupt:
        replace = media._atomic_replace
        def stop_at_file(path, data):
            if path in (corpus, side, plain):
                assert backup.read_bytes() == original
            if path == stop_path:
                raise OSError("simulated interruption")
            replace(path, data)
        interrupt.setattr(media, "_atomic_replace", stop_at_file)
        if stop_at == "db":
            def stop_before_commit(*args):
                raise sqlite3.OperationalError("simulated interruption")
            interrupt.setattr(media, "_write_clips", stop_before_commit)
        with pytest.raises((OSError, ValueError), match="interruption|could not finish"):
            server.repair_rolling_captions(VID, dry_run=False)
    server.repair_rolling_captions(VID)
    server.repair_rolling_captions(VID, dry_run=False)
    assert plain.read_text(encoding="utf-8").split() == WORDS
    assert backup.read_bytes() == original
    with idx.detached_snapshot() as conn:
        stored = conn.execute("SELECT media_revision FROM media_depth WHERE video_id=?", (VID,)).fetchone()[0]
    assert stored == json.loads(side.read_bytes())["media_depth"]["media_revision"]


def test_kind_change_at_publication_is_refused(library, monkeypatch):
    idx, save = library
    side, corpus, plain = save()
    before = _files((corpus, plain))
    publish = idx.publish_media_snapshot
    def racing(*args, **kwargs):
        data = json.loads(side.read_bytes())
        side.write_text(json.dumps(dict(data, caption_kind="captions")), encoding="utf-8")
        return publish(*args, **kwargs)
    monkeypatch.setattr(idx, "publish_media_snapshot", racing)
    with pytest.raises(ValueError, match="could not finish"):
        server.repair_rolling_captions(VID, dry_run=False)
    assert _files((corpus, plain)) == before and not list(side.parent.glob("*.bak"))


def test_modified_original_backup_refused_in_preview_and_apply(library):
    _, save = library
    paths = save()
    backup = Path(server.repair_rolling_captions(VID, dry_run=False)["original_sidecar"])
    backup.write_bytes(b"the user changed the archive")
    before = _files((*paths, backup))
    for dry_run in (True, False):
        with pytest.raises(ValueError, match="backup has changed"):
            server.repair_rolling_captions(VID, dry_run=dry_run)
    assert _files((*paths, backup)) == before


@pytest.mark.parametrize("supplied,status", [(VID, 200), ("other", 400)])
def test_running_helper_queues_only_the_repaired_video(monkeypatch, supplied, status):
    changed, replies = [], []
    monkeypatch.setattr(server, "_local_search_singleton", SimpleNamespace(update_source=changed.append))
    request = SimpleNamespace(
        path="/search/refresh-item", _reject_bad_host=lambda: False, _require_token=lambda: True,
        _read_json_body=lambda **kwargs: {"video_id": supplied},
        _send_json=lambda code, body: replies.append((code, body)))
    server.Handler.do_POST(request)
    assert replies[0][0] == status and changed == ([VID] if status == 200 else [])
