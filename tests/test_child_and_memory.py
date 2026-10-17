"""Offline child cleanup, bounded Activity memory, and cancelled media tests.

Load server functions without importing the app or opening a user profile.
All storage is temporary and subprocesses/network access are mocked.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
import io
import json
import logging
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.request

import pytest

import index
import source_subscriptions
from test_unique_capture_folders import ROOT, URL_A, _load, _metadata, _snapshot, capture
from test_staged_refresh import refresh, _published_snapshot


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    blocked = Mock(side_effect=AssertionError("unexpected external I/O"))
    for owner, name in ((socket, "create_connection"), (socket.socket, "connect"),
                        (subprocess, "Popen"), (subprocess, "run"),
                        (urllib.request, "urlopen")):
        monkeypatch.setattr(owner, name, blocked)
    yield
    blocked.assert_not_called()


def _load_cancelled(scope):
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                and n.name == "PlaylistJobCancelled")
    exec(compile(ast.Module(body=[node], type_ignores=[]), "server.py", "exec"), scope)


@pytest.fixture
def child(tmp_path):
    proc = Mock(pid=12345, returncode=None)
    proc.stdin, proc.stdout, proc.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
    proc.poll.side_effect = lambda: proc.returncode
    proc.terminate.side_effect = lambda: setattr(proc, "returncode", -15)
    proc.kill.side_effect = lambda: setattr(proc, "returncode", -9)
    proc.wait.side_effect = lambda **kwargs: proc.returncode

    def communicate(**kwargs):
        proc.returncode = 0
        proc.wait()
        return b"output", b""

    proc.communicate.side_effect = communicate
    sources = SimpleNamespace(
        current_capture_context=lambda: {"start_id": "start-1", "instance": "instance-1"},
        record_child_launch_intent=Mock(), resolve_child_launch_intent=Mock(),
        record_child_start=Mock(), record_child_end=Mock(),
    )
    spawn = Mock(return_value=proc)
    scope = {
        "subprocess": SimpleNamespace(Popen=spawn, CompletedProcess=subprocess.CompletedProcess,
                                      TimeoutExpired=subprocess.TimeoutExpired,
                                      CalledProcessError=subprocess.CalledProcessError),
        "threading": threading, "time": time, "SUBPROCESS_KW": {}, "DATA_ROOT": tmp_path,
        "source_subscriptions": sources, "log": logging.getLogger(__name__),
    }
    _load_cancelled(scope)
    _load(ROOT / "server.py", {"_run_subprocess", "_terminate_process", "_raise_if_cancelled"}, scope)
    return SimpleNamespace(proc=proc, sources=sources, spawn=spawn, scope=scope,
                           run=lambda **kw: scope["_run_subprocess"](["mock-yt-dlp"], **kw))


@pytest.mark.parametrize("error", [OSError("disk full"), sqlite3.OperationalError("locked"),
                                   KeyboardInterrupt("interrupted registration")])
@pytest.mark.parametrize("force_kill", [False, True])
def test_registration_failure_reaps_child_closes_pipes_and_preserves_error(child, error, force_kill):
    child.sources.record_child_start.side_effect = error
    child.sources.record_child_end.side_effect = OSError("exit record also failed")
    if force_kill:
        child.proc.terminate.side_effect = OSError("terminate refused")
    with pytest.raises(type(error)) as raised:
        child.run()
    assert raised.value is error
    child.spawn.assert_called_once()
    child.proc.terminate.assert_called_once()
    assert child.proc.kill.call_count == int(force_kill)
    assert child.proc.wait.call_count >= 1
    assert child.proc.returncode is not None
    assert all(getattr(child.proc, name).closed for name in ("stdin", "stdout", "stderr"))
    child.proc.communicate.assert_not_called()
    child.sources.resolve_child_launch_intent.assert_not_called()


def test_registration_failure_keeps_unresolved_ownership_evidence(child, tmp_path, monkeypatch):
    sources = source_subscriptions
    monkeypatch.setattr(sources, "_process_created_ms", lambda pid: 123)
    write = sources._write_ownership_record

    def fail_registration(path, record):
        if record.get("children"):
            raise OSError("registration disk full")
        write(path, record)

    monkeypatch.setattr(sources, "_write_ownership_record", fail_registration)
    child.scope["source_subscriptions"] = sources
    with sources.capture_context("start-1", SimpleNamespace(identity="instance-1")):
        with pytest.raises(OSError, match="registration disk full"):
            child.run()
    assert child.proc.returncode is not None
    assert child.proc.wait.called
    assert sources.child_ownership_liveness(tmp_path, "start-1") == "unknown"
    record = json.loads(next((tmp_path / sources.CHILD_OWNERSHIP_DIR).iterdir()).read_text())
    assert record["unresolved_launch"] is True
    assert record["children"] == []


@pytest.mark.parametrize("failure", ["timeout", "cancel", "communication", "success"])
def test_every_spawned_child_is_reaped_and_pipes_closed(child, failure):
    event = threading.Event()
    if failure == "timeout":
        child.proc.communicate.side_effect = subprocess.TimeoutExpired("mock", 0)
        expected = subprocess.TimeoutExpired
    elif failure == "cancel":
        def communicate(**kwargs):
            event.set()
            raise subprocess.TimeoutExpired("mock", 0)
        child.proc.communicate.side_effect = communicate
        expected = child.scope["PlaylistJobCancelled"]
    elif failure == "communication":
        child.proc.communicate.side_effect = OSError("pipe failure")
        expected = OSError
    if failure == "success":
        assert child.run().stdout == b"output"
        child.proc.terminate.assert_not_called()
    else:
        with pytest.raises(expected):
            child.run(cancel_event=event, timeout=0 if failure == "timeout" else None)
        child.proc.terminate.assert_called_once()
    assert child.proc.wait.called
    child.sources.record_child_end.assert_called_once()
    assert all(getattr(child.proc, name).closed for name in ("stdin", "stdout", "stderr"))


@pytest.mark.parametrize("output", ["output", b"output"])
@pytest.mark.parametrize("returncode", [0, 1])
def test_cleanup_accepts_non_pipe_output_and_missing_pid(child, output, returncode):
    # Pacing callers use process doubles whose output is already captured.
    # Cleanup must leave the CompletedProcess/error contract intact.
    proc = SimpleNamespace(
        returncode=returncode, stdout=output, stderr=output,
        communicate=lambda **kw: (output, output), poll=lambda: returncode,
    )
    child.spawn.return_value = proc
    child.sources.current_capture_context = lambda: None
    if returncode:
        with pytest.raises(subprocess.CalledProcessError) as raised:
            child.run()
        assert raised.value.returncode == returncode
        assert raised.value.output == raised.value.stderr == output
    else:
        result = child.run()
        assert result.returncode == 0
        assert result.stdout == result.stderr == output
    child.sources.record_child_start.assert_not_called()
    child.sources.record_child_end.assert_not_called()


def test_pipe_close_error_does_not_mask_failure_without_pid(child, caplog):
    error = OSError("communication failed")
    del child.proc.pid
    child.sources.current_capture_context = lambda: None
    child.proc.communicate.side_effect = error
    child.proc.stdin = SimpleNamespace(close=Mock(side_effect=OSError("close failed")))
    with pytest.raises(OSError) as raised:
        child.run()
    assert raised.value is error
    child.proc.terminate.assert_called_once()
    child.proc.wait.assert_called_once()
    child.proc.stdin.close.assert_called_once()
    assert child.proc.stdout.closed and child.proc.stderr.closed
    assert "could not close subprocess" in caplog.text


def test_unreaped_child_never_records_an_exit_or_clears_intent(child, caplog):
    child.sources.record_child_start.side_effect = OSError("registration failed")
    child.proc.terminate.side_effect = OSError("terminate failed")
    child.proc.kill.side_effect = OSError("kill failed")
    with pytest.raises(OSError, match="registration failed"):
        child.run()
    child.sources.record_child_end.assert_not_called()
    child.sources.resolve_child_launch_intent.assert_not_called()
    assert "could not reap subprocess" in caplog.text
    assert child.proc.stderr.closed


@pytest.fixture
def jobs(tmp_path):
    idx = index.Index.open(tmp_path / "jobs.db")
    scope = {"index": index, "Path": Path, "json": json, "threading": threading, "re": re,
             "log": logging.getLogger(__name__), "_jobs": {}, "_jobs_lock": threading.Lock(),
             "_get_index": lambda: idx, "_now_iso": lambda: "2026-10-17T12:00:00"}
    _load(ROOT / "server.py", {
        "_public_job", "_index_job_row", "_persist_jobs_locked", "_add_job_record",
        "_supersede_terminal_single_jobs_locked", "_get_public_job", "_list_public_jobs",
        "_update_job", "_sanitize_single_job_result", "_job_text_only_corpus",
        "_strip_image_refs", "_strip_paste_header", "_restore_jobs_from_disk",
        "_validate_persisted_job", "_create_playlist_job", "_cancel_playlist_job",
    }, scope, constants={"_JOB_TERMINAL_STATES", "_IMAGE_REF_LINE_RE"})
    try:
        yield SimpleNamespace(scope=scope, idx=idx, records=scope["_jobs"])
    finally:
        idx.close()


def _job(n, state="completed", **extra):
    return {"id": f"job-{n:04}", "kind": "playlist", "state": state,
            "updated_at": (datetime(2026, 10, 15) + timedelta(seconds=n)).isoformat(),
            "result": {"combined_md_path": "unused.md", "combined_md_text": "corpus" * 10000},
            "_videos": [{"large_metadata": "x" * 10000}], "_cancel_event": threading.Event(),
            **extra}


@pytest.mark.parametrize("ties", [False, True])
def test_terminal_history_matches_sqlite_limit_and_releases_payloads(jobs, ties):
    for n in range(500):
        job = _job(n, ("completed", "failed", "cancelled")[n % 3])
        if ties:
            job["updated_at"] = "2026-10-15T00:00:00"
        jobs.scope["_add_job_record"](job)
    assert len(jobs.records) == index.TERMINAL_JOB_RETENTION
    assert set(jobs.records) == {row["job_id"] for row in jobs.idx.list_jobs(limit=1000)}
    assert set(jobs.records) == {f"job-{n:04}" for n in range(300, 500)}
    for job in jobs.records.values():
        assert "combined_md_text" not in job["result"]
        assert not any(key.startswith("_") for key in job)
    assert all("combined_md_text" not in row["metadata_json"]
               for row in jobs.idx.list_jobs(limit=1000))


def test_retention_preserves_active_workers_and_unsettled_ownership(jobs):
    active = [_job(-1, "queued"), _job(-2, "running"),
              _job(-3, "cancelled", _thread=SimpleNamespace(ident=None)),
              _job(-4, "completed", _source_owner_token="owner", source_start_id="standing")]
    for job in active:
        jobs.scope["_add_job_record"](job)
    for n in range(250):
        jobs.scope["_add_job_record"](_job(n))
    assert len(jobs.records) == 204
    for job in active:
        assert jobs.records[job["id"]] is job
        assert "_videos" in job
        assert job["_cancel_event"] is not None
    assert active[-1]["_source_owner_token"] == "owner"
    # Once the worker exits / ownership settles, its old terminal record can go.
    active[-2].pop("_thread")
    active[-1].pop("_source_owner_token")
    with jobs.scope["_jobs_lock"]:
        jobs.scope["_persist_jobs_locked"]()
    assert len(jobs.records) == 202
    assert all(job["id"] not in jobs.records for job in active[-2:])


def test_memory_retention_still_runs_when_sqlite_fails(jobs, monkeypatch, caplog):
    monkeypatch.setattr(jobs.idx, "upsert_job", Mock(side_effect=sqlite3.OperationalError("disk full")))
    for n in range(205):
        jobs.scope["_add_job_record"](_job(n))
    assert len(jobs.records) == 200
    assert "job persistence write failed: disk full" in caplog.text
    assert all("combined_md_text" not in j["result"] for j in jobs.records.values())


def test_restore_prunes_terminal_history_but_keeps_durable_queue(jobs):
    for n in range(249):
        jobs.idx.upsert_job(jobs.scope["_index_job_row"](_job(n)))
    jobs.idx.upsert_job(jobs.scope["_index_job_row"](
        _job(-1, "queued", kind="podcast_transcribe", result=None)))
    jobs.scope["_restore_jobs_from_disk"]()
    assert len(jobs.records) == 201
    assert jobs.records["job--001"]["state"] == "queued"


def test_job_detail_loads_text_outside_lock_without_caching(jobs, tmp_path, monkeypatch):
    path = tmp_path / "corpus.md"
    path.write_text("# Corpus\n\n![frame](screenshots/frame.jpg)\nFirst text", encoding="utf-8")
    job = _job(1, result={"combined_md_path": str(path), "combined_md_text": "discard me"})
    jobs.scope["_add_job_record"](job)
    read = Path.read_text

    def read_unlocked(p, *args, **kwargs):
        assert not jobs.scope["_jobs_lock"].locked()
        return read(p, *args, **kwargs)

    spy = Mock(side_effect=read_unlocked)
    monkeypatch.setattr(Path, "read_text", lambda p, *a, **kw: spy(p, *a, **kw))
    jobs.scope["_list_public_jobs"]()
    spy.assert_not_called()
    detail = jobs.scope["_get_public_job"](job["id"])
    assert "First text" in detail["result"]["combined_md_text"]
    assert "![frame]" not in detail["result"]["combined_md_text"]
    assert "combined_md_text" not in job["result"]
    path.write_text("Second text", encoding="utf-8")
    assert jobs.scope["_get_public_job"](job["id"])["result"]["combined_md_text"] == "Second text"
    path.unlink()
    detail = jobs.scope["_get_public_job"](job["id"])
    assert detail["state"] == "completed"
    assert detail["result"]["combined_md_text"] == ""
    assert "Could not read saved corpus" in detail["result"]["combined_md_error"]
    assert "combined_md_error" not in job["result"]


def test_cancel_before_worker_starts_keeps_event_until_worker_exits(jobs, tmp_path):
    workers = []

    def thread(**kwargs):
        worker = SimpleNamespace(start=Mock(), target=kwargs["target"], ident=None)
        workers.append(worker)
        return worker

    seen = []

    def work(job_id):
        job = jobs.records[job_id]
        seen.append(job["_cancel_event"].is_set())
        assert job["_videos"] == [{"url": URL_A}]
        assert job["_folder"] == str(tmp_path / "playlist")

    jobs.scope.update({"threading": SimpleNamespace(Thread=thread, Event=threading.Event),
                       "_make_job_id": lambda: "playlist-job", "slugify": lambda title: title,
                       "_session_folder": lambda slug: tmp_path / slug, "_playlist_worker": work})
    job_id, _ = jobs.scope["_create_playlist_job"](
        {"title": "playlist", "url": URL_A, "will_process_count": 1, "videos": [{"url": URL_A}]}, 30)
    assert jobs.scope["_cancel_playlist_job"](job_id)[1] is None
    assert "_thread" in jobs.records[job_id]
    workers[0].target()
    assert seen == [True]
    assert not any(k.startswith("_") for k in jobs.records[job_id])


@pytest.mark.parametrize("setup_failure", [False, True])
def test_worker_completion_and_setup_failure_release_inputs(jobs, tmp_path, setup_failure):
    workers = []

    def thread(**kwargs):
        worker = SimpleNamespace(start=Mock(), target=kwargs["target"], ident=None)
        workers.append(worker)
        return worker

    def work(job_id):
        if setup_failure:
            raise PermissionError("playlist folder unavailable")
        jobs.scope["_update_job"](job_id, state="completed", result={
            "combined_md_path": str(tmp_path / "corpus.md"), "combined_md_text": "large corpus"})

    jobs.scope.update({"threading": SimpleNamespace(Thread=thread, Event=threading.Event),
                       "_make_job_id": lambda: "playlist-job", "slugify": lambda title: title,
                       "_session_folder": lambda slug: tmp_path / slug, "_playlist_worker": work})
    job_id, _ = jobs.scope["_create_playlist_job"](
        {"title": "playlist", "url": URL_A, "will_process_count": 1, "videos": [{"url": URL_A}]}, 30)
    workers[0].target()
    job = jobs.records[job_id]
    assert job["state"] == ("failed" if setup_failure else "completed")
    assert not any(k.startswith("_") for k in job)
    assert "combined_md_text" not in (job["result"] or {})
    assert jobs.idx.get_job(job_id)["status"] == job["state"]


def test_finished_thread_reference_does_not_pin_history(jobs):
    for n in range(205):
        jobs.scope["_add_job_record"](_job(
            n, _thread=SimpleNamespace(ident=42, is_alive=lambda: False)))
    assert len(jobs.records) == 200
    assert all("_thread" not in job for job in jobs.records.values())


@pytest.mark.parametrize("settled", [False, True])
def test_source_ownership_is_released_only_after_verified_settlement(jobs, settled):
    backend = SimpleNamespace(kind="podcast", release=Mock())
    service = SimpleNamespace(backend=backend, complete_capture=Mock(return_value={
        "outcome": "succeeded" if settled else "uncertain"}))
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = ("capture-key",)
    job_index = SimpleNamespace(_lock=threading.Lock(), _conn=connection,
                                upsert_job=jobs.idx.upsert_job)
    jobs.scope.update({"_source_service": lambda: service,
                       "_get_index": lambda: job_index, "source_subscriptions": source_subscriptions})
    _load(ROOT / "server.py", {"_settle_source_capture"}, jobs.scope)
    job = _job(1, source_start_id="standing", _source_owner_token="owner")
    jobs.scope["_add_job_record"](job)
    jobs.scope["_settle_source_capture"](job["id"], video_id="video", failure_code=None)
    assert ("_source_owner_token" not in job) == settled
    assert backend.release.call_count == int(settled)
    assert service.complete_capture.call_args.args[:3] == ("standing", "owner", "video")


@pytest.mark.parametrize("mode", ["full", "lite", "chunked"])
@pytest.mark.parametrize("keep_media", [False, True])
@pytest.mark.parametrize("boundary", ["download", "markdown", "sidecar"])
def test_first_capture_cancel_removes_only_unretained_downloads(
        capture, tmp_path, mode, keep_media, boundary):
    scope = capture.scope
    _load_cancelled(scope)
    event = threading.Event()
    scope["_read_settings"] = lambda: {"keep_media": keep_media}
    scope["_long_video_chunks"] = lambda duration: [{"start_seconds": 0, "end_seconds": 30,
                                                     "duration_seconds": 30}]
    scope["_chunk_section_spec"] = lambda chunk: "*0-30"
    folder = scope["_video_capture_folder"](tmp_path, URL_A, _metadata(URL_A))
    media = []

    def run(cmd, **kwargs):
        if cmd[0] == "ffmpeg":
            Path(cmd[-1].replace("%04d", "0001")).write_bytes(b"frame")
        else:
            template = cmd[cmd.index("-o") + 1]
            path = Path(template.replace("%(ext)s", "mp4").replace("%(section_number)03d", "001"))
            path.write_bytes(b"this attempt's media")
            media.append(path)
            # Unrelated files in the attempt folder must survive cancellation.
            (folder / "user-notes.txt").write_bytes(b"notes")
            if boundary == "download":
                event.set()
                scope["_raise_if_cancelled"](event)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    scope["_run_subprocess"] = run
    build = scope["_build_yoink_md"]
    write = scope["_atomic_write_text"]

    def build_md(**kwargs):
        if boundary == "markdown":
            event.set()
        return build(**kwargs)

    def write_text(path, text):
        write(path, text)
        if boundary == "sidecar" and path.name == f"{folder.name}.json":
            event.set()

    scope["_build_yoink_md"] = build_md
    scope["_atomic_write_text"] = write_text
    with pytest.raises(scope["PlaylistJobCancelled"]):
        scope["_run_extraction"](URL_A, 30, folder, metadata=_metadata(URL_A), topic="Test",
                                  source_type="short_video", cancel_event=event,
                                  long_video_mode=mode, notify=False, generate_paste=False)
    assert media and all(path.exists() == keep_media for path in media)
    assert (folder / "user-notes.txt").read_bytes() == b"notes"
    assert (folder / ".capture-source.json").is_file()
    assert capture.idx.get_yoink("aaaaaaaaaaa") is None
    scope["_start_comments_thread"].assert_not_called()


def test_cancelled_first_capture_cleanup_failure_is_visible(capture, tmp_path, monkeypatch, caplog):
    scope = capture.scope
    _load_cancelled(scope)
    event = threading.Event()
    write = scope["_atomic_write_text"]
    folder = scope["_video_capture_folder"](tmp_path, URL_A, _metadata(URL_A))

    def write_text(path, text):
        write(path, text)
        if path.name == f"{folder.name}.json":
            event.set()

    unlink = Path.unlink

    def fail_unlink(path, **kwargs):
        if path == folder / "video.mp4":
            raise PermissionError("media locked")
        return unlink(path, **kwargs)

    scope["_atomic_write_text"] = write_text
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(RuntimeError, match="Capture cancelled; could not remove downloaded media"):
        scope["_run_extraction"](URL_A, 30, folder, metadata=_metadata(URL_A), topic="Test",
                                  cancel_event=event, notify=False, generate_paste=False)
    assert (folder / "video.mp4").read_bytes() == b"media"
    assert (folder / f"{folder.name}.md").is_file()
    assert "cancelled capture media cleanup failed; file kept" in caplog.text


@pytest.mark.parametrize("preserve", ["before_download", "changed_after_download"])
def test_cancel_cleanup_preserves_media_it_does_not_own(capture, tmp_path, preserve):
    scope = capture.scope
    _load_cancelled(scope)
    event = threading.Event()
    folder = scope["_video_capture_folder"](tmp_path, URL_A, _metadata(URL_A))
    original = b"media belonging to another writer"
    write = scope["_atomic_write_text"]
    if preserve == "before_download":
        scope["_download_thumbnail"] = lambda *a, **k: (folder / "video.webm").write_bytes(original)

    def write_text(path, text):
        write(path, text)
        if path.name == f"{folder.name}.json":
            if preserve == "changed_after_download":
                (folder / "video.mp4").write_bytes(original)
            event.set()

    scope["_atomic_write_text"] = write_text
    with pytest.raises(scope["PlaylistJobCancelled"]):
        scope["_run_extraction"](URL_A, 30, folder, metadata=_metadata(URL_A), topic="Test",
                                  cancel_event=event, notify=False, generate_paste=False)
    retained = folder / ("video.webm" if preserve == "before_download" else "video.mp4")
    assert retained.read_bytes() == original
    if preserve == "before_download":
        assert not (folder / "video.mp4").exists()


def test_cancel_during_failed_sidecar_save_keeps_recovery_media(capture, tmp_path):
    scope = capture.scope
    _load_cancelled(scope)
    event = threading.Event()
    folder = scope["_video_capture_folder"](tmp_path, URL_A, _metadata(URL_A))
    write = scope["_atomic_write_text"]
    scope["_schedule_publication_retry"] = Mock()

    def fail_sidecar(path, text):
        if path.name == f"{folder.name}.json":
            event.set()
            raise PermissionError("sidecar locked during cancellation")
        write(path, text)

    scope["_atomic_write_text"] = fail_sidecar
    with pytest.raises(scope["PlaylistJobCancelled"]):
        scope["_run_extraction"](URL_A, 30, folder, metadata=_metadata(URL_A), topic="Test",
                                  cancel_event=event, notify=False, generate_paste=False)
    assert (folder / "video.mp4").read_bytes() == b"media"
    assert (folder / f"{folder.name}.md").is_file()
    assert capture.idx.get_yoink("aaaaaaaaaaa") is None
    scope["_schedule_publication_retry"].assert_not_called()


def test_cancelled_refresh_preserves_capture_backup_and_recovery_inputs(refresh, monkeypatch):
    state = refresh
    recovery = state.folder / ".s-recovery" / "p"
    recovery.mkdir(parents=True)
    (recovery / "video.mp4").write_bytes(b"recovery media")
    inputs = state.folder / ".media-inputs"
    inputs.mkdir()
    (inputs / "original.mp4").write_bytes(b"retained media input")
    before = _snapshot(state.folder)
    state.before = _published_snapshot(state.folder)
    state.keep_media = False
    write = state.scope["_atomic_write_text"]

    def cancel_after_sidecar(path, text):
        write(path, text)
        if path.name == "c.json":
            state.event.set()

    monkeypatch.setitem(state.scope, "_atomic_write_text", cancel_after_sidecar)
    with pytest.raises(state.scope["PlaylistJobCancelled"]):
        state.run()
    assert _snapshot(state.folder) == before
    assert dict(state.capture.idx.get_yoink("aaaaaaaaaaa")) == state.row_before
    for name in ("_start_comments_thread", "_start_entity_extraction_thread",
                 "_incremental_index_update"):
        state.scope[name].assert_not_called()
