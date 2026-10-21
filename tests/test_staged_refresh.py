"""Offline refresh regressions; execute the core without importing the app.

Reuse the isolated capture fixture's temporary library and in-memory SQLite
index. Subprocesses, network access, settings, and background work are mocked.
"""
from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import index as index_module
import library_media
import yt_extract
from uoink_core.storage import _atomic_write_text

from test_unique_capture_folders import ROOT, URL_A, _load, _metadata, _snapshot, capture


@pytest.fixture
def refresh(capture):
    scope = capture.scope
    scope["tempfile"] = tempfile
    scope["time"] = SimpleNamespace(sleep=Mock())
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8-sig"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name in {"PlaylistJobCancelled", "ExtractionPhaseError"}]
    assert len(classes) == 2
    exec(compile(ast.Module(body=classes, type_ignores=[]), "server.py", "exec"), scope)
    state = SimpleNamespace(
        generation="old", failure=None, cancel_at=None, keep_media=True,
        event=threading.Event(), destinations=[], before=None, media_ext="mp4",
    )
    scope["_read_settings"] = lambda: {"keep_media": state.keep_media}
    scope["_long_video_chunks"] = lambda d: [
        {"start_seconds": 0, "end_seconds": 10, "duration_seconds": 10},
        {"start_seconds": 20, "end_seconds": 30, "duration_seconds": 10},
    ]
    scope["_chunk_section_spec"] = lambda c: f"*{c['start_seconds']}-{c['end_seconds']}"

    def thumbnail(metadata, folder, **kwargs):
        path = folder / "thumbnail.jpg"
        path.write_bytes(f"{state.generation} thumbnail".encode())
        return path

    scope["_download_thumbnail"] = thumbnail
    scope["_resolve_video_transcript"] = lambda *a, **k: (
        [(0, 1, f"{state.generation} transcript")], "asr", None)
    scope["_build_yoink_md"] = lambda **k: (
        f"# {state.generation} capture\n"
        + "\n".join(f"![frame](screenshots/{p.name})" for p in k["shots"]))

    def fake_subprocess(cmd, **kwargs):
        if cmd[0] == "ffmpeg":
            destination = Path(cmd[-1].replace("%04d", "0001"))
            if state.failure != "no_frames":
                destination.write_bytes(f"{state.generation} screenshot".encode())
            phase = "ffmpeg"
        else:
            template = cmd[cmd.index("-o") + 1]
            for number in range(1, (cmd.count("--download-sections") or 1) + 1):
                destination = Path(template.replace("%(section_number)03d", f"{number:03d}")
                                   .replace("%(ext)s", state.media_ext))
                destination.write_bytes(f"{state.generation} media".encode())
            phase = "download"
        state.destinations.append(destination)
        if state.before is not None:
            # Generation must never touch the existing capture, even after a
            # partial screenshot/download has been written in the stage.
            assert _published_snapshot(state.folder) == state.before
            assert state.folder in destination.parents
            assert any(p.name.startswith(".s-") for p in destination.parents)
        if state.failure == phase:
            raise subprocess.CalledProcessError(1, cmd, stderr=b"injected failure")
        if state.failure == f"{phase}_timeout":
            raise subprocess.TimeoutExpired(cmd, 10)
        if state.cancel_at == phase:
            state.event.set()
            scope["_raise_if_cancelled"](state.event)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    scope["_run_subprocess"] = fake_subprocess

    def run(mode="full"):
        return scope["_run_extraction"](
            URL_A, 30, state.folder, metadata=_metadata(URL_A), topic="Test",
            source_type="short_video", notify=False, generate_paste=False,
            cancel_event=state.event, long_video_mode=mode,
        )

    state.folder = scope["_video_capture_folder"](
        capture.idx._path.parent / "capture", URL_A, _metadata(URL_A))
    state.run = run
    state.scope = scope
    state.capture = capture
    run()
    # Include stale helper-owned assets and unrelated user files.
    (state.folder / "screenshots" / "shot_0002.jpg").write_bytes(b"old second screenshot")
    (state.folder / "screenshots" / "notes.txt").write_bytes(b"user screenshot notes")
    (state.folder / "notes.txt").write_bytes(b"user notes")
    (state.folder / "video.en.srt").write_bytes(b"old captions")
    state.before = _snapshot(state.folder)
    state.row_before = dict(capture.idx.get_yoink("aaaaaaaaaaa"))
    state.generation = "new"
    scope["_start_comments_thread"].reset_mock()
    scope["_start_entity_extraction_thread"].reset_mock()
    scope["_incremental_index_update"].reset_mock()
    return state


def _published_snapshot(folder):
    return {name: content for name, content in _snapshot(folder).items()
            if not Path(name).parts[0].startswith(".s-")}


def _assert_preserved(state):
    assert _snapshot(state.folder) == state.before
    assert not list(state.folder.glob(".s-*"))
    assert dict(state.capture.idx.get_yoink("aaaaaaaaaaa")) == state.row_before
    for name in ("_start_comments_thread", "_start_entity_extraction_thread",
                 "_incremental_index_update"):
        state.scope[name].assert_not_called()


@pytest.mark.parametrize("mode", ["full", "lite", "chunked"])
@pytest.mark.parametrize("failure", ["ffmpeg", "ffmpeg_timeout", "download"])
def test_failed_refresh_keeps_previous_assets(refresh, mode, failure):
    refresh.failure = failure
    expected = (refresh.scope["ExtractionPhaseError"] if failure.endswith("timeout")
                else subprocess.CalledProcessError)
    with pytest.raises(expected):
        refresh.run(mode)
    _assert_preserved(refresh)


@pytest.mark.parametrize("mode", ["full", "lite", "chunked"])
@pytest.mark.parametrize("cancel_at", ["download", "ffmpeg", "before_publication"])
def test_cancelled_refresh_keeps_previous_assets(refresh, monkeypatch, mode, cancel_at):
    if cancel_at == "before_publication":
        write = refresh.scope["_atomic_write_text"]

        def cancel_after_sidecar(path, text):
            write(path, text)
            if path.suffix == ".json":
                refresh.event.set()

        monkeypatch.setitem(refresh.scope, "_atomic_write_text", cancel_after_sidecar)
    else:
        refresh.cancel_at = cancel_at
    with pytest.raises(refresh.scope["PlaylistJobCancelled"]):
        refresh.run(mode)
    _assert_preserved(refresh)


@pytest.mark.parametrize("mode", ["full", "lite", "chunked"])
@pytest.mark.parametrize("keep_media", [False, True])
def test_successful_refresh_publishes_complete_replacement(refresh, mode, keep_media):
    refresh.keep_media = keep_media
    result = refresh.run(mode)
    folder = refresh.folder
    assert result["ok"] is True
    assert result["folder"] == str(folder)
    assert result["video_slug"] == folder.name
    assert not list(folder.glob(".s-*"))
    assert (folder / "thumbnail.jpg").read_bytes() == b"new thumbnail"
    assert (folder / "transcript.txt").read_text(encoding="utf-8") == "new transcript"
    assert (folder / "screenshots" / "shot_0001.jpg").read_bytes() == b"new screenshot"
    assert (folder / "notes.txt").read_bytes() == b"user notes"
    assert (folder / "screenshots" / "notes.txt").read_bytes() == b"user screenshot notes"
    assert not (folder / "video.en.srt").exists()
    assert len(list((folder / "screenshots").glob("shot_*.jpg"))) == result["screenshot_count"]
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    assert len(sidecar["screenshots"]) == result["screenshot_count"]
    for shot in sidecar["screenshots"]:
        assert (folder / shot["path"]).read_bytes() == b"new screenshot"
    if keep_media:
        assert (folder / sidecar["media_file"]).read_bytes() == b"new media"
    else:
        assert "media_file" not in sidecar
        assert not list(folder.glob("*.mp4"))
    row = refresh.capture.idx.get_yoink("aaaaaaaaaaa")
    assert Path(row["corpus_path"]) == folder / f"{folder.name}.md"
    assert Path(row["sidecar_path"]) == folder / f"{folder.name}.json"
    assert ".s-" not in (folder / f"{folder.name}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("suffix", [".md", ".json"])
def test_staged_write_failure_preserves_capture(refresh, monkeypatch, suffix):
    write = refresh.scope["_atomic_write_text"]

    def fail(path, text):
        if path.suffix == suffix:
            path.write_bytes(b"partial write")
            raise OSError("disk full")
        write(path, text)

    monkeypatch.setitem(refresh.scope, "_atomic_write_text", fail)
    with pytest.raises(OSError, match="disk full"):
        refresh.run()
    _assert_preserved(refresh)


def test_metadata_write_failure_preserves_capture(refresh, monkeypatch):
    write = Path.write_text

    def fail(path, *args, **kwargs):
        if path.name == "metadata.json" and path.parent.name == "n":
            path.write_bytes(b"partial metadata")
            raise OSError("injected metadata failure")
        return write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail)
    with pytest.raises(OSError, match="injected metadata failure"):
        refresh.run()
    _assert_preserved(refresh)


def test_empty_ffmpeg_output_does_not_replace_previous_frames(refresh):
    refresh.failure = "no_frames"
    with pytest.raises(refresh.scope["ExtractionPhaseError"], match="produced no images"):
        refresh.run()
    _assert_preserved(refresh)


def test_new_media_extension_replaces_old_only_after_success(refresh):
    refresh.media_ext = "webm"
    refresh.failure = "ffmpeg"
    with pytest.raises(subprocess.CalledProcessError):
        refresh.run()
    _assert_preserved(refresh)
    refresh.failure = None
    refresh.run()
    assert not (refresh.folder / "video.mp4").exists()
    assert (refresh.folder / "video.webm").read_bytes() == b"new media"
    sidecar = json.loads((refresh.folder / f"{refresh.folder.name}.json").read_text(encoding="utf-8"))
    assert sidecar["media_file"] == "video.webm"


@pytest.mark.parametrize("phase", ["backup", "publish", "cancel_publish"])
def test_interrupted_swap_restores_previous_capture(refresh, monkeypatch, phase):
    rename = Path.rename
    calls = []

    def interrupt(path, target):
        publishing = path.parent.name == "n"
        backing_up = Path(target).parent.name == "p"
        if (publishing and phase in {"publish", "cancel_publish"}) or (backing_up and phase == "backup"):
            calls.append(path)
            if len(calls) == 2:
                if phase == "cancel_publish":
                    refresh.event.set()
                else:
                    raise OSError("injected rename failure")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", interrupt)
    expected = refresh.scope["PlaylistJobCancelled"] if phase == "cancel_publish" else OSError
    with pytest.raises(expected):
        refresh.run()
    assert len(calls) == 2
    _assert_preserved(refresh)


@pytest.mark.parametrize("phase", ["backup", "publish"])
def test_interruption_after_rename_restores_previous_capture(refresh, monkeypatch, phase):
    rename = Path.rename
    interrupted = []

    def move_then_interrupt(path, target):
        result = rename(path, target)
        selected = (Path(target).parent.name == "p" if phase == "backup"
                    else path.parent.name == "n")
        if selected and not interrupted:
            interrupted.append(path)
            raise KeyboardInterrupt("injected interruption after rename")
        return result

    monkeypatch.setattr(Path, "rename", move_then_interrupt)
    with pytest.raises(KeyboardInterrupt, match="injected interruption after rename"):
        refresh.run()
    assert len(interrupted) == 1
    _assert_preserved(refresh)


@pytest.mark.parametrize("mode", ["full", "chunked"])
@pytest.mark.parametrize("keep_media", [False, True])
@pytest.mark.parametrize("error", [sqlite3.OperationalError, sqlite3.IntegrityError])
def test_sqlite_failure_keeps_replacement_and_previous_backup(
        refresh, monkeypatch, error, caplog, keep_media, mode):
    refresh.keep_media = keep_media
    monkeypatch.setattr(refresh.capture.idx, "upsert_yoink",
                        Mock(side_effect=error("injected SQLite failure")))
    with pytest.raises(RuntimeError, match="injected SQLite failure") as exc:
        refresh.run(mode)
    assert isinstance(exc.value.__cause__, error)
    # Index entry is the conservative commit boundary: an exception from an
    # index writer cannot tell the caller whether it committed first.
    previous = _assert_publication_failure_preserves_both(refresh)
    assert str(previous) in str(exc.value)
    assert dict(refresh.capture.idx.get_yoink("aaaaaaaaaaa")) == refresh.row_before
    assert "previous files retained in" in caplog.text


def _assert_publication_failure_preserves_both(state):
    folder = state.folder
    assert (folder / "screenshots" / "shot_0001.jpg").read_bytes() == b"new screenshot"
    assert (folder / "thumbnail.jpg").read_bytes() == b"new thumbnail"
    assert (folder / "transcript.txt").read_text(encoding="utf-8") == "new transcript"
    assert (folder / f"{folder.name}.md").read_text(encoding="utf-8").startswith("# new capture")
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    for shot in sidecar["screenshots"]:
        assert (folder / shot["path"]).read_bytes() == b"new screenshot"
    if state.keep_media:
        assert (folder / sidecar["media_file"]).read_bytes() == b"new media"
    else:
        assert "media_file" not in sidecar
        assert not list(folder.glob("*.mp4"))
    stages = list(folder.glob(".s-*"))
    assert len(stages) == 1
    previous = stages[0] / "p"
    media_backup = stages[0] / "m"
    expected_dirs = {previous}
    if (folder / ".media-inputs").exists():
        expected_dirs.add(media_backup)
    assert set(stages[0].iterdir()) == expected_dirs
    for name, content in state.before.items():
        backup_name = {f"{folder.name}.md": "c.md", f"{folder.name}.json": "c.json"}.get(name, name)
        backup = previous / backup_name
        relative = Path(name)
        if relative.parts[0] == ".media-inputs":
            backup = media_backup / relative.relative_to(".media-inputs")
            assert backup.is_file()
        # Unrelated files were never moved; every replaced original is kept.
        assert (backup if backup.is_file() else folder / name).read_bytes() == content
    for name in ("_start_comments_thread", "_start_entity_extraction_thread",
                 "_incremental_index_update"):
        state.scope[name].assert_not_called()
    return previous


@pytest.mark.parametrize("first_capture", [False, True])
def test_cancel_during_index_finishes_committed_capture(refresh, monkeypatch, first_capture):
    state = refresh
    if first_capture:
        state.before = None
        state.folder = state.folder.with_name("first-capture")
    index_yoink = state.scope["_index_yoink"]

    def cancel_after_index(*args):
        result = index_yoink(*args)
        state.event.set()
        return result

    monkeypatch.setitem(state.scope, "_index_yoink", cancel_after_index)
    result = state.run()
    assert result["ok"] is True
    assert state.event.is_set()
    assert not list(state.folder.glob(".s-*"))
    assert (state.folder / "video.mp4").read_bytes() == b"new media"
    assert (state.folder / "screenshots" / "shot_0001.jpg").read_bytes() == b"new screenshot"
    row = state.capture.idx.get_yoink("aaaaaaaaaaa")
    assert Path(row["corpus_path"]) == state.folder / f"{state.folder.name}.md"
    for name in ("_start_comments_thread", "_start_entity_extraction_thread",
                 "_incremental_index_update"):
        state.scope[name].assert_called_once()


@pytest.fixture
def phase6_refresh(refresh, tmp_path, monkeypatch):
    """Exercise the real migrated index, publisher, ledger and artifact pruning."""
    monkeypatch.setitem(sys.modules, "library_media", library_media)
    monkeypatch.setitem(sys.modules, "yt_extract", yt_extract)
    idx = index_module.Index.open(tmp_path / "phase6.db")
    monkeypatch.setattr(idx, "_invalidate_library_sources", Mock())
    monkeypatch.setattr(idx, "_invalidate_after_publication", Mock())
    scope = refresh.scope
    scope["_get_index"] = lambda: idx
    scope["RELIABILITY_DEFAULT_THRESHOLD"] = 0.5
    scope["RELIABILITY_MODEL_NAME"] = "tiny"
    scope["RELIABILITY_MODEL_ROOT"] = tmp_path / "unused-model"
    scope["_sidecar_update_lock"] = threading.Lock()
    scope["_selected_reliability_model"] = lambda: "tiny"
    scope["_reliability_model_status"] = lambda model: {"cached": True}
    scope["uoink_reliability"] = SimpleNamespace(detect_unreliable_spans=Mock(return_value=[]))
    scope["_download_reliability_audio"] = Mock(side_effect=AssertionError("unexpected download"))
    _load(ROOT / "server.py", {
        "_as_float", "_parse_hms", "_youtube_deep_link", "_source_deep_link",
        "_sidecar_link_builder", "_transcript_entries_with_links", "_citations_from_sidecar",
        "_capture_media_plan", "_publish_capture_media", "_compute_transcript_reliability",
        "_transcript_text_from_sidecar", "_read_sidecar_for_folder",
        "_write_reliability_to_sidecar", "_render_reliability_summary",
        "_replace_reliability_section",
    }, scope)
    try:
        # Replace the seed fixture with an old capture published through Phase 6.
        refresh.before = None
        refresh.generation = "old"
        refresh.run()
        assert library_media.schema_ready(idx._conn)
        refresh.idx = idx
        refresh.before = _snapshot(refresh.folder)
        refresh.row_before = idx.get_yoink("aaaaaaaaaaa")
        refresh.generation = "new"
        for name in ("_start_comments_thread", "_start_entity_extraction_thread",
                     "_incremental_index_update"):
            scope[name].reset_mock()
        yield refresh
    finally:
        idx.close()


def _assert_current_media_snapshot(state):
    folder = state.folder
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    block = sidecar["media_depth"]
    inputs = folder / library_media.MEDIA_INPUTS_DIR
    ledger = json.loads((inputs / library_media.PUBLICATION_LEDGER).read_text(encoding="utf-8"))
    row = state.idx._conn.execute(
        "SELECT * FROM media_depth WHERE video_id=?", ("aaaaaaaaaaa",)).fetchone()
    assert row["media_revision"] == ledger["media_revision"] == block["media_revision"]
    digest = block["provenance"]["transcript_source"]["artifact_sha256"]
    artifact = inputs / f"{digest}.json"
    assert state.scope["hashlib"].sha256(artifact.read_bytes()).hexdigest() == digest
    assert json.loads(artifact.read_bytes())["transcript"][0]["text"] == "new transcript"
    assert sidecar["transcript"][0]["text"] == "new transcript"
    citations = state.idx._conn.execute(
        "SELECT text FROM citations WHERE video_id=? AND kind='transcript_chunk'",
        ("aaaaaaaaaaa",)).fetchall()
    assert [row["text"] for row in citations] == ["new transcript"]
    corpus = (folder / f"{folder.name}.md").read_text(encoding="utf-8")
    fts = state.idx._conn.execute(
        "SELECT content FROM yoinks_fts WHERE video_id=?", ("aaaaaaaaaaa",)).fetchone()
    assert fts["content"] == corpus
    assert corpus.startswith("# new capture")
    row = state.idx.get_yoink("aaaaaaaaaaa")
    assert Path(row["corpus_path"]) == folder / f"{folder.name}.md"
    assert Path(row["sidecar_path"]) == folder / f"{folder.name}.json"
    assert not state.idx._conn.in_transaction


def test_citations_failure_after_committed_upsert_keeps_new_snapshot(phase6_refresh, monkeypatch):
    state = phase6_refresh
    insert = Mock(side_effect=sqlite3.OperationalError("injected citation failure"))
    monkeypatch.setattr(state.idx, "insert_citations", insert)
    with pytest.raises(RuntimeError, match="injected citation failure") as exc:
        state.run()
    assert isinstance(exc.value.__cause__, sqlite3.OperationalError)
    insert.assert_called_once()
    previous = _assert_publication_failure_preserves_both(state)
    assert str(previous) in str(exc.value)
    _assert_current_media_snapshot(state)


def test_cancel_after_reliability_index_keeps_new_snapshot(phase6_refresh, monkeypatch):
    state = phase6_refresh
    monkeypatch.setitem(state.scope, "_read_settings", lambda: {
        "keep_media": True, "transcript_reliability_auto_check": True,
    })
    index_yoink = state.scope["_index_yoink"]
    indexed_reliability = []

    def cancel_after_reliability_write(folder, sidecar, *args):
        result = index_yoink(folder, sidecar, *args)
        if sidecar.get("reliability", {}).get("status") == "completed":
            _assert_current_media_snapshot(state)
            indexed_reliability.append(sidecar["reliability"])
            state.event.set()
        return result

    monkeypatch.setitem(state.scope, "_index_yoink", cancel_after_reliability_write)
    result = state.run()
    assert result["ok"] is True
    assert state.event.is_set()
    assert len(indexed_reliability) == 1
    state.scope["uoink_reliability"].detect_unreliable_spans.assert_called_once()
    state.scope["_download_reliability_audio"].assert_not_called()
    assert not list(state.folder.glob(".s-*"))
    assert (state.folder / "video.mp4").read_bytes() == b"new media"
    for name in ("_start_comments_thread", "_start_entity_extraction_thread",
                 "_incremental_index_update"):
        state.scope[name].assert_called_once()
    _assert_current_media_snapshot(state)


def test_media_invalidation_failure_keeps_committed_publication(phase6_refresh, monkeypatch):
    state = phase6_refresh
    invalidate = Mock(side_effect=library_media.MediaError("library_unavailable"))
    monkeypatch.setattr(state.idx, "_invalidate_after_publication", invalidate)
    with pytest.raises(RuntimeError, match="Previous files are retained in") as exc:
        state.run()
    assert isinstance(exc.value.__cause__, library_media.MediaError)
    assert exc.value.__cause__.code == "library_unavailable"
    invalidate.assert_called_once_with("aaaaaaaaaaa")
    previous = _assert_publication_failure_preserves_both(state)
    assert str(previous) in str(exc.value)
    _assert_current_media_snapshot(state)


def test_media_sqlite_failure_after_sidecar_write_keeps_retryable_files(phase6_refresh, monkeypatch):
    state = phase6_refresh
    before = dict(state.idx._conn.execute("SELECT * FROM media_depth").fetchone())
    with monkeypatch.context() as patch:
        write_rows = Mock(side_effect=sqlite3.OperationalError("injected media row failure"))
        patch.setattr(library_media, "_write_media_rows", write_rows)
        with pytest.raises(RuntimeError, match="Previous files are retained in") as exc:
            state.run()
        assert isinstance(exc.value.__cause__, library_media.MediaError)
        assert exc.value.__cause__.code == "library_unavailable"
        write_rows.assert_called_once()
    previous = _assert_publication_failure_preserves_both(state)
    assert str(previous) in str(exc.value)
    # The row/FTS upsert committed, but the media transaction rolled back
    # after publishing its ledger, artifact and sidecar. Keep those exact
    # inputs so the publisher can complete its existing claim on retry.
    assert dict(state.idx._conn.execute("SELECT * FROM media_depth").fetchone()) == before
    folder = state.folder
    sidecar_path = folder / f"{folder.name}.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["transcript"][0]["text"] == "new transcript"
    ledger = json.loads((folder / library_media.MEDIA_INPUTS_DIR /
                         library_media.PUBLICATION_LEDGER).read_text(encoding="utf-8"))
    assert ledger["media_revision"] == sidecar["media_depth"]["media_revision"]
    assert ledger["media_revision"] != before["media_revision"]
    corpus_path = folder / f"{folder.name}.md"
    assert state.idx._conn.execute("SELECT content FROM yoinks_fts").fetchone()[0] == \
        corpus_path.read_text(encoding="utf-8")
    assert state.scope["_index_yoink"](folder, sidecar, corpus_path, sidecar_path) is True
    _assert_current_media_snapshot(state)


@pytest.mark.parametrize("failure", ["ffmpeg", "cancel"])
def test_phase6_generation_failure_preserves_files_and_media_rows(phase6_refresh, failure):
    state = phase6_refresh
    tables = ("yoinks", "yoinks_fts", "citations", "clips", "media_depth", "chapters")

    def rows():
        return {name: [tuple(row) for row in state.idx._conn.execute(f"SELECT * FROM {name}")]
                for name in tables}

    before = rows()
    if failure == "cancel":
        state.cancel_at = "ffmpeg"
        expected = state.scope["PlaylistJobCancelled"]
    else:
        state.failure = "ffmpeg"
        expected = subprocess.CalledProcessError
    with pytest.raises(expected):
        state.run()
    assert _snapshot(state.folder) == state.before
    assert rows() == before
    assert not list(state.folder.glob(".s-*"))


def test_media_backup_failure_preserves_published_capture(phase6_refresh, monkeypatch):
    state = phase6_refresh
    monkeypatch.setattr(state.scope["shutil"], "copytree",
                        Mock(side_effect=OSError("injected media backup failure")))
    with pytest.raises(OSError, match="injected media backup failure"):
        state.run()
    assert _snapshot(state.folder) == state.before
    assert state.idx.get_yoink("aaaaaaaaaaa") == state.row_before
    assert not list(state.folder.glob(".s-*"))


def test_failed_rollback_retains_original_backup_and_reports_location(refresh, monkeypatch):
    rename = Path.rename

    def fail(path, target):
        if path.parent.name == "n" and path.name == "thumbnail.jpg":
            raise PermissionError("injected publication failure")
        if path.parent.name == "p" and path.name == "video.mp4":
            raise PermissionError("injected restore failure")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(RuntimeError, match="Previous files are retained in") as exc:
        refresh.run()
    stages = list(refresh.folder.glob(".s-*"))
    assert len(stages) == 1
    assert str(stages[0]) in str(exc.value)
    assert (stages[0] / "p" / "video.mp4").read_bytes() == b"old media"
    for name, content in refresh.before.items():
        if name != "video.mp4":
            assert (refresh.folder / name).read_bytes() == content
    assert dict(refresh.capture.idx.get_yoink("aaaaaaaaaaa")) == refresh.row_before


def test_failed_staging_cleanup_is_visible_and_never_removes_originals(refresh, monkeypatch, caplog):
    refresh.failure = "ffmpeg"
    monkeypatch.setattr(refresh.scope["shutil"], "rmtree",
                        Mock(side_effect=PermissionError("injected cleanup failure")))
    with pytest.raises(subprocess.CalledProcessError):
        refresh.run()
    assert _published_snapshot(refresh.folder) == refresh.before
    assert len(list(refresh.folder.glob(".s-*"))) == 1
    assert "could not remove capture staging directory" in caplog.text


def test_rollback_never_overwrites_a_file_that_appears_at_original_path(refresh, monkeypatch):
    rename = Path.rename
    occupied = refresh.folder / "video.mp4"

    def interrupted(path, target):
        if path.parent.name == "n" and path.name == "thumbnail.jpg":
            assert not occupied.exists()
            occupied.write_bytes(b"new file from another writer")
            raise OSError("injected publication failure")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", interrupted)
    with pytest.raises(RuntimeError, match="Previous files are retained in") as exc:
        refresh.run()
    stage, = refresh.folder.glob(".s-*")
    assert str(stage) in str(exc.value)
    assert occupied.read_bytes() == b"new file from another writer"
    assert (stage / "p" / "video.mp4").read_bytes() == b"old media"
    for name, content in refresh.before.items():
        if name != "video.mp4":
            assert (refresh.folder / name).read_bytes() == content
    assert dict(refresh.capture.idx.get_yoink("aaaaaaaaaaa")) == refresh.row_before


@pytest.mark.parametrize("mode", ["full", "chunked"])
@pytest.mark.parametrize("rollback", [False, True])
def test_long_topic_and_63_character_slug_keep_all_staged_paths_under_max_path(
        refresh, monkeypatch, mode, rollback):
    # A short disposable root makes this test independent of pytest's own
    # potentially long basetemp. The final JSON path is 259 characters.
    with tempfile.TemporaryDirectory(prefix="sr-") as temporary:
        root = Path(temporary)
        slug = "Long_video_" + "x" * 52
        assert len(slug) == 63
        topic_length = 190 - len(str(root)) - len(slug) - 2
        assert topic_length >= 30
        folder = root / ("Long_topic_" + "t" * (topic_length - 11)) / slug
        folder.parent.mkdir()
        old_name = refresh.folder.name
        # The capture lives under pytest's basetemp; on CI that can be a different
        # drive from the short temp root, where os.rename fails with WinError 17.
        shutil.move(str(refresh.folder), str(folder))
        for suffix in (".md", ".json"):
            (folder / f"{old_name}{suffix}").rename(folder / f"{slug}{suffix}")
        refresh.folder = folder
        sidecar_path = folder / f"{slug}.json"
        assert len(str(sidecar_path)) == 259
        refresh.scope["_index_yoink"](
            folder, json.loads(sidecar_path.read_text(encoding="utf-8")),
            folder / f"{slug}.md", sidecar_path)
        refresh.before = _snapshot(folder)
        refresh.row_before = dict(refresh.capture.idx.get_yoink("aaaaaaaaaaa"))
        monkeypatch.setitem(refresh.scope, "_atomic_write_text", _atomic_write_text)
        paths = []
        operations = set()

        def observe(path, operation):
            if any(part.startswith(".s-") for part in path.parts):
                paths.append(path)
                operations.add(operation)
                assert len(str(path)) < 260, str(path)

        def track(method):
            original = getattr(Path, method)

            def wrapped(path, *args, **kwargs):
                observe(path, method)
                if method in {"rename", "replace"}:
                    observe(Path(args[0]), method)
                if (rollback and method == "rename" and path.parent.name == "n"
                        and path.name == "thumbnail.jpg"):
                    raise OSError("injected publication failure")
                return original(path, *args, **kwargs)

            monkeypatch.setattr(Path, method, wrapped)

        for method in ("open", "mkdir", "rename", "replace"):
            track(method)
        if rollback:
            with pytest.raises(OSError, match="injected publication failure"):
                refresh.run(mode)
            _assert_preserved(refresh)
        else:
            assert refresh.run(mode)["ok"] is True
        assert operations == {"open", "mkdir", "rename", "replace"}
        assert any(path.suffix == ".tmp" for path in paths)
        assert any("p" in path.parts for path in paths)
        assert not list(folder.glob(".s-*"))


@pytest.mark.parametrize("failure", ["publish", "index"])
def test_long_media_artifact_backup_does_not_exceed_original_path_length(
        refresh, monkeypatch, failure):
    with tempfile.TemporaryDirectory(prefix="sr-") as temporary:
        root = Path(temporary)
        slug = "Long_video_" + "x" * 52
        topic_length = 175 - len(str(root)) - len(slug) - 2
        assert topic_length >= 20
        folder = root / ("t" * topic_length) / slug
        folder.parent.mkdir()
        old_name = refresh.folder.name
        # The capture lives under pytest's basetemp; on CI that can be a different
        # drive from the short temp root, where os.rename fails with WinError 17.
        shutil.move(str(refresh.folder), str(folder))
        for suffix in (".md", ".json"):
            (folder / f"{old_name}{suffix}").rename(folder / f"{slug}{suffix}")
        refresh.folder = folder
        inputs = folder / ".media-inputs"
        inputs.mkdir()
        artifact = inputs / ("a" * 64 + ".json")
        artifact.write_bytes(b"previous media artifact")
        assert len(str(artifact)) == 259
        refresh.before = _snapshot(folder)
        copytree = refresh.scope["shutil"].copytree
        copied = []

        def copy_with_path_check(source, destination, **kwargs):
            for path in source.rglob("*"):
                target = destination / path.relative_to(source)
                assert len(str(target)) <= len(str(path)) < 260
                copied.append(target)
            return copytree(source, destination, **kwargs)

        monkeypatch.setattr(refresh.scope["shutil"], "copytree", copy_with_path_check)
        if failure == "publish":
            rename = Path.rename

            def fail_publish(path, target):
                if path.parent.name == "n" and path.name == "thumbnail.jpg":
                    raise OSError("injected publication failure")
                return rename(path, target)

            monkeypatch.setattr(Path, "rename", fail_publish)
            with pytest.raises(OSError, match="injected publication failure"):
                refresh.run()
            _assert_preserved(refresh)
        else:
            monkeypatch.setitem(refresh.scope, "_index_yoink", Mock(
                side_effect=sqlite3.OperationalError("injected index failure")))
            with pytest.raises(RuntimeError, match="injected index failure") as exc:
                refresh.run()
            stage, = folder.glob(".s-*")
            assert str(stage / "m") in str(exc.value)
            assert (stage / "m" / artifact.name).read_bytes() == artifact.read_bytes()
            _assert_publication_failure_preserves_both(refresh)
        assert len(copied) == 1


@pytest.mark.parametrize("phase", ["backup", "publish"])
def test_transient_rename_lock_during_successful_refresh_is_retried(refresh, monkeypatch, phase):
    rename = Path.rename
    failures = []

    def lock_once(path, target):
        selected = (Path(target).parent.name == "p" if phase == "backup"
                    else path.parent.name == "n")
        if selected and path.name == "thumbnail.jpg" and not failures:
            failures.append(path)
            raise PermissionError("transient OneDrive lock")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", lock_once)
    assert refresh.run()["ok"] is True
    assert len(failures) == 1
    refresh.scope["time"].sleep.assert_called_once_with(0.05)
    assert (refresh.folder / "thumbnail.jpg").read_bytes() == b"new thumbnail"
    assert not list(refresh.folder.glob(".s-*"))


@pytest.mark.parametrize("rollback_phase", ["unpublish", "restore"])
def test_transient_publish_and_rollback_locks_restore_complete_capture(
        refresh, monkeypatch, rollback_phase):
    rename = Path.rename
    failures = []

    def lock_once(path, target):
        target = Path(target)
        if path.parent.name == "n" and path.name == "metadata.json":
            if "publish" not in failures:
                failures.append("publish")
                raise PermissionError("transient publish lock")
        if path.parent.name == "n" and path.name == "thumbnail.jpg":
            raise OSError("later publish failure")
        rolling_back = (target.parent.name == "n" if rollback_phase == "unpublish"
                        else path.parent.name == "p")
        if rolling_back and path.name == "metadata.json" and "rollback" not in failures:
            failures.append("rollback")
            raise PermissionError("transient rollback lock")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", lock_once)
    with pytest.raises(OSError, match="later publish failure"):
        refresh.run()
    assert failures == ["publish", "rollback"]
    assert [call.args for call in refresh.scope["time"].sleep.call_args_list] == [(0.05,), (0.05,)]
    _assert_preserved(refresh)


@pytest.mark.parametrize("phase", ["backup", "publish", "unpublish", "restore"])
def test_persistent_rename_locks_have_bounded_retries(refresh, monkeypatch, phase):
    rename = Path.rename
    attempts = []

    def locked(path, target):
        target = Path(target)
        selected = {
            "backup": target.parent.name == "p",
            "publish": path.parent.name == "n",
            "unpublish": target.parent.name == "n",
            "restore": path.parent.name == "p",
        }[phase]
        if selected and path.name == "metadata.json":
            attempts.append(path)
            raise PermissionError("persistent OneDrive lock")
        if phase in {"unpublish", "restore"} and path.parent.name == "n" and path.name == "thumbnail.jpg":
            raise OSError("trigger rollback")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", locked)
    expected = RuntimeError if phase in {"unpublish", "restore"} else PermissionError
    with pytest.raises(expected):
        refresh.run()
    assert len(attempts) == 4
    assert [call.args for call in refresh.scope["time"].sleep.call_args_list] == [(0.05,), (0.2,), (0.5,)]
    if phase in {"backup", "publish"}:
        _assert_preserved(refresh)
    else:
        stage, = refresh.folder.glob(".s-*")
        assert (stage / "p" / "metadata.json").read_bytes() == refresh.before["metadata.json"]
        assert dict(refresh.capture.idx.get_yoink("aaaaaaaaaaa")) == refresh.row_before


@pytest.mark.parametrize("mode", ["full", "chunked"])
def test_first_capture_identity_conflict_still_removes_downloaded_media(refresh, monkeypatch, mode):
    refresh.before = None
    refresh.folder = refresh.folder.with_name("first-conflict")
    refresh.keep_media = False
    order = []

    def markdown_index(entry):
        assert not list(refresh.folder.glob("video*.mp4"))
        order.append("markdown")

    def index_conflict(*args, **kwargs):
        assert not list(refresh.folder.glob("video*.mp4"))
        order.append("sqlite")
        raise sqlite3.IntegrityError("injected slug conflict")

    monkeypatch.setitem(refresh.scope, "_incremental_index_update", markdown_index)
    monkeypatch.setattr(refresh.capture.idx, "upsert_yoink", index_conflict)
    with pytest.raises(sqlite3.IntegrityError, match="injected slug conflict"):
        refresh.run(mode)
    assert order == ["markdown", "sqlite"]
    assert refresh.destinations
    assert not list(refresh.folder.glob("video*.mp4"))
    assert (refresh.folder / f"{refresh.folder.name}.md").is_file()
    assert (refresh.folder / f"{refresh.folder.name}.json").is_file()
    assert (refresh.folder / "screenshots" / "shot_0001.jpg").is_file()
    assert dict(refresh.capture.idx.get_yoink("aaaaaaaaaaa")) == refresh.row_before
