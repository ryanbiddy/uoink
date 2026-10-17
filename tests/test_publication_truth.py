"""Offline publication failures, durable retries and truthful capture jobs.

Execute production functions without importing server or opening a profile.
All files/databases are temporary; media, network and background work are mocked.
"""
from __future__ import annotations

from contextlib import nullcontext
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

import index
import library_media
from uoink_core.storage import _atomic_write_text
from test_staged_refresh import phase6_refresh, refresh, _assert_current_media_snapshot
from test_unique_capture_folders import (
    ROOT, URL_A, URL_B, _load, _metadata, _snapshot, capture, _session_handler, _playlist_job,
)


class _JobsLock:
    """server._jobs_lock is a plain Lock. Re-entry fails here instead of
    deadlocking, so a check run under the lock cannot take it again."""

    def __init__(self):
        self._lock = threading.Lock()
        self._owner = None

    def __enter__(self):
        if self._owner == threading.get_ident():
            raise AssertionError("_jobs_lock re-entered; production would deadlock")
        self._lock.acquire()
        self._owner = threading.get_ident()
        return self

    def __exit__(self, *exc_info):
        self._owner = None
        self._lock.release()
        return False


@pytest.fixture
def publication(capture, tmp_path):
    scope = capture.scope
    idx = index.Index.open(tmp_path / "publication.db")
    idx._invalidate_library_sources = Mock()
    scope.update({
        "index": index, "uuid": uuid, "DATA_ROOT": tmp_path / "profile",
        "_get_index": lambda: idx, "_atomic_write_text": _atomic_write_text,
        "_read_settings": lambda: {"keep_media": True},
        "_jobs": {}, "_jobs_lock": _JobsLock(),
        "_JOB_TERMINAL_STATES": {"completed", "failed", "cancelled"},
        "_sidecar_update_lock": threading.Lock(),
        "_manual_extraction_ownership": Mock(side_effect=lambda url: nullcontext(
            SimpleNamespace(ok=True, conflict=None, reused=None, completed_while_waiting=False))),
        "_fetch_metadata": Mock(side_effect=lambda url, *, cancel_event=None: _metadata(url)),
        "_detect_live_state": lambda m: "none",
        "LIVE_STATE_LIVE": "live", "LIVE_STATE_UPCOMING": "upcoming",
        "LIVE_STATE_POST_LIVE": "post_live", "_is_youtube_rate_limit": lambda e: False,
        "_job_text_only_corpus": lambda text: text,
    })
    _load(ROOT / "server.py", {
        "_schedule_publication_retry", "_retry_publication_one", "_finish_publication_retry",
        "_capture_folder_removed", "_publication_retry_superseded",
        "_publication_retry_superseded_locked", "_record_single_extract_job",
        "_public_job", "_sanitize_single_job_result", "_index_job_row", "_persist_jobs_locked",
        "_add_job_record", "_supersede_terminal_single_jobs_locked", "_make_job_id",
        "_failure_phase", "friendly_error", "_validate_persisted_job",
    }, scope)
    _load(ROOT / "server.py", {"_handle_extract"}, scope, class_name="Handler")
    responses = []
    handler = SimpleNamespace(
        _validate_url_interval=lambda b: (URL_A, 30, None),
        _send_json=lambda status, result: responses.append((status, result)),
    )
    folder = scope["_video_capture_folder"](scope["DESKTOP_ROOT"] / "Test", URL_A, _metadata(URL_A))
    state = SimpleNamespace(scope=scope, idx=idx, folder=folder, capture=capture,
                            responses=responses, handler=handler,
                            queue=index.PublicationRetryQueue(scope["DATA_ROOT"] / "publication-retries"))
    try:
        yield state
    finally:
        idx.close()


def _request(state):
    state.scope["_handle_extract"](state.handler, {"__source_type": "short_video"})
    status, response = state.responses[-1]
    assert status == 200
    return response


def _job(state):
    job, = state.scope["_jobs"].values()
    persisted = state.idx.get_job(job["id"])
    assert persisted["status"] == job["state"]
    public = json.loads(persisted["metadata_json"])
    assert state.scope["_validate_persisted_job"](public)["state"] == job["state"]
    return public


def _assert_failed_save(state, response):
    assert response["ok"] is False
    assert response["failure_phase"] == "save"
    assert "Files kept in" in response["error"]
    job = _job(state)
    assert job["state"] == "failed"
    assert job["current_video_phase"] == "save"
    assert job["videos_done"] == 0
    assert job["videos_failed"] == 1
    assert job["session_folder"] == str(state.folder)
    assert (state.folder / f"{state.folder.name}.md").is_file()
    assert (state.folder / "screenshots" / "shot_0001.jpg").is_file()
    assert (state.folder / "video.mp4").is_file()
    state.scope["_start_comments_thread"].assert_not_called()
    state.scope["_start_entity_extraction_thread"].assert_not_called()
    state.scope["maybe_toast"].assert_not_called()


def _fail_sidecar(state, monkeypatch):
    replace = Path.replace

    def locked(source, target):
        if Path(target) == state.folder / f"{state.folder.name}.json":
            raise PermissionError("injected sidecar lock")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", locked)


def test_locked_sidecar_returns_save_failure_and_durable_retry(publication, monkeypatch):
    state = publication
    _fail_sidecar(state, monkeypatch)
    response = _request(state)
    _assert_failed_save(state, response)
    assert "injected sidecar lock" in response["error"]
    assert "One publication retry is queued" in response["error"]
    assert state.idx.get_yoink("aaaaaaaaaaa") is None
    assert not (state.folder / f"{state.folder.name}.json").exists()
    # Reopening the queue simulates a restart; the complete sidecar survived.
    reopened = index.PublicationRetryQueue(state.queue.root)
    receipt_id, record = reopened.next_pending()
    assert record["sidecar"]["video_id"] == "aaaaaaaaaaa"
    assert record["sidecar_sha256"] is None
    assert reopened.enqueue(record) == receipt_id
    assert len(list(state.queue.root.glob("*.json"))) == 1


@pytest.mark.parametrize("failure", ["upsert", "citations", "false_return"])
def test_index_failures_never_report_done(publication, monkeypatch, failure):
    state = publication
    if failure == "false_return":
        monkeypatch.setitem(state.scope, "_index_yoink", Mock(return_value=False))
    else:
        monkeypatch.setattr(state.idx, "upsert_yoink" if failure == "upsert" else "insert_citations",
                            Mock(side_effect=sqlite3.OperationalError("injected database full")))
    phases = []
    with pytest.raises((sqlite3.OperationalError, RuntimeError)) as raised:
        state.scope["_run_extraction"](
            URL_A, 30, state.folder, metadata=_metadata(URL_A), topic="Test",
            source_type="short_video", phase_callback=phases.append)
    assert raised.value.phase == "save"
    assert phases[-1] == "save"
    assert "done" not in phases
    assert (state.folder / f"{state.folder.name}.json").is_file()
    assert (state.folder / "video.mp4").is_file()
    assert state.queue.next_pending() is not None
    state.scope["maybe_toast"].assert_not_called()


def test_sqlite_failure_is_visible_in_response_and_persisted_job(publication, monkeypatch):
    state = publication
    monkeypatch.setattr(state.idx, "upsert_yoink",
                        Mock(side_effect=sqlite3.OperationalError("injected database full")))
    response = _request(state)
    _assert_failed_save(state, response)
    assert "injected database full" in response["error"]
    assert state.queue.next_pending() is not None


def test_unavailable_database_cannot_prevent_durable_retry(publication, monkeypatch):
    state = publication
    with monkeypatch.context() as patch:
        patch.setitem(state.scope, "_get_index", Mock(
            side_effect=sqlite3.OperationalError("injected database unavailable")))
        response = _request(state)
    assert response["ok"] is False
    assert response["failure_phase"] == "save"
    assert "One publication retry is queued" in response["error"]
    job, = state.scope["_jobs"].values()
    assert job["state"] == "failed"
    assert state.queue.next_pending() is not None
    assert state.scope["_retry_publication_one"]() is True
    assert _job(state)["state"] == "completed"


@pytest.mark.parametrize("failure", ["sidecar", "index"])
def test_retry_publishes_saved_artifacts_once_without_network(publication, monkeypatch, failure):
    state = publication
    if failure == "sidecar":
        _fail_sidecar(state, monkeypatch)
    else:
        upsert = state.idx.upsert_yoink
        monkeypatch.setattr(state.idx, "upsert_yoink",
                            Mock(side_effect=sqlite3.OperationalError("injected database full")))
    _assert_failed_save(state, _request(state))
    before = _snapshot(state.folder)
    calls_before = list(state.capture.calls)
    state.scope["_fetch_metadata"].reset_mock()
    if failure == "index":
        monkeypatch.setattr(state.idx, "upsert_yoink", upsert)
    receipt_id, record = state.queue.next_pending()
    assert record["markdown_index_attempted"] is (failure == "index")
    assert state.scope["_retry_publication_one"]() is True
    assert state.scope["_retry_publication_one"]() is False
    assert state.queue.next_pending() is None
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == "succeeded"
    for name, content in before.items():
        assert (state.folder / name).read_bytes() == content
    assert state.capture.calls == calls_before
    state.scope["_fetch_metadata"].assert_not_called()
    row = state.idx.get_yoink("aaaaaaaaaaa")
    assert Path(row["sidecar_path"]).is_file()
    assert Path(row["corpus_path"]).is_file()
    assert _job(state)["state"] == "completed"
    state.scope["_start_entity_extraction_thread"].assert_called_once()
    state.scope["_start_comments_thread"].assert_called_once()
    state.scope["_incremental_index_update"].assert_called_once()
    args = state.scope["_start_comments_thread"].call_args.args
    assert args[:3] == (URL_A, state.folder, Path(row["corpus_path"]))
    assert args[3]["id"] == "aaaaaaaaaaa"
    assert args[4] == []


@pytest.mark.parametrize("existing", [False, True])
def test_retry_without_hardlinks_never_overwrites_sidecar(publication, monkeypatch, existing):
    state = publication
    _fail_sidecar(state, monkeypatch)
    hardlink = Mock(side_effect=OSError("hard links are unsupported on this volume"))
    monkeypatch.setattr(Path, "hardlink_to", hardlink)
    _assert_failed_save(state, _request(state))
    receipt_id, record = state.queue.next_pending()
    sidecar_path = state.folder / f"{state.folder.name}.json"
    before = _snapshot(state.folder)
    if existing:
        # Simulate another writer winning after the retry's existence checks.
        def appeared(path, target):
            if path == sidecar_path:
                path.write_bytes(b'{"title": "user metadata"}')
            raise OSError("hard links are unsupported on this volume")

        monkeypatch.setattr(Path, "hardlink_to", appeared)
    assert state.scope["_retry_publication_one"]() is True
    assert state.scope["_retry_publication_one"]() is False
    assert state.queue.next_pending() is None
    for name, content in before.items():
        assert (state.folder / name).read_bytes() == content
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    if existing:
        assert sidecar_path.read_bytes() == b'{"title": "user metadata"}'
        assert outcome["status"] == "failed"
        assert "sidecar changed" in outcome["error"]
        assert state.idx.get_yoink("aaaaaaaaaaa") is None
    else:
        assert json.loads(sidecar_path.read_text()) == record["sidecar"]
        assert outcome["status"] == "succeeded"
        assert _job(state)["state"] == "completed"


def test_retry_failure_is_terminal_and_keeps_all_files(publication, monkeypatch):
    state = publication
    fail = Mock(side_effect=sqlite3.OperationalError("injected database full"))
    monkeypatch.setattr(state.idx, "upsert_yoink", fail)
    _assert_failed_save(state, _request(state))
    before = _snapshot(state.folder)
    receipt_id, record = state.queue.next_pending()
    assert state.scope["_retry_publication_one"]() is True
    assert state.scope["_retry_publication_one"]() is False
    assert fail.call_count == 2  # capture + one publication retry
    assert _snapshot(state.folder) == before
    job = _job(state)
    assert job["state"] == "failed"
    assert job["current_video_phase"] == "save"
    assert job["retry_exhausted"] is True
    assert state.queue.enqueue(record) == receipt_id
    assert state.queue.next_pending() is None


def test_generic_source_retry_uses_original_extractor_id(publication, monkeypatch):
    state = publication
    url = "https://example.test/clip.mp4"
    with monkeypatch.context() as patch:
        patch.setattr(state.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected database full")))
        with pytest.raises(sqlite3.OperationalError):
            state.capture.run(url, metadata=_metadata(url, id="clip"))
    _, record = state.queue.next_pending()
    before = _snapshot(Path(record["folder"]))
    assert record["metadata_id"] == "clip"
    assert record["sidecar"]["video_id"].startswith("url_")
    assert state.scope["_retry_publication_one"]() is True
    assert _snapshot(Path(record["folder"])) == before
    assert _job(state)["state"] == "completed"


@pytest.mark.parametrize("failure", ["upsert", "media_rows"])
def test_refresh_publication_retry_keeps_previous_backup(phase6_refresh, tmp_path, monkeypatch, failure):
    state = phase6_refresh
    scope = state.scope
    scope.update({
        "index": index, "DATA_ROOT": tmp_path / "profile",
        "_record_single_extract_job": Mock(),
        "_manual_extraction_ownership": lambda url: nullcontext(
            SimpleNamespace(ok=True, conflict=None)),
        "_jobs": {}, "_jobs_lock": _JobsLock(),
        "_JOB_TERMINAL_STATES": {"completed", "failed", "cancelled"}, "uuid": uuid,
    })
    _load(ROOT / "server.py", {
        "_schedule_publication_retry", "_retry_publication_one", "_finish_publication_retry",
        "_capture_folder_removed", "_publication_retry_superseded",
        "_publication_retry_superseded_locked", "_make_job_id",
    }, scope)
    with monkeypatch.context() as patch:
        target, method = ((state.idx, "upsert_yoink") if failure == "upsert"
                          else (library_media, "_write_media_rows"))
        patch.setattr(target, method, Mock(side_effect=sqlite3.OperationalError("injected full")))
        message = "injected full" if failure == "upsert" else "library storage is unavailable"
        with pytest.raises(RuntimeError, match=message) as raised:
            state.run()
    if failure == "media_rows":
        assert isinstance(raised.value.__cause__, library_media.MediaError)
        assert raised.value.__cause__.code == "library_unavailable"
    assert raised.value.phase == "save"
    assert "One publication retry is queued" in raised.value.publication_error
    stage, = state.folder.glob(".s-*")
    backups = _snapshot(stage)
    assert (stage / "p" / "c.md").read_bytes() == state.before[f"{state.folder.name}.md"]
    _, record = index.PublicationRetryQueue(scope["DATA_ROOT"] / "publication-retries").next_pending()
    assert record["markdown_index_attempted"] is False
    scope["_incremental_index_update"].assert_not_called()
    assert scope["_retry_publication_one"]() is True
    assert scope["_retry_publication_one"]() is False
    scope["_incremental_index_update"].assert_called_once()
    assert _snapshot(stage) == backups
    _assert_current_media_snapshot(state)
    assert scope["_record_single_extract_job"].call_args.kwargs["error"] is None


@pytest.mark.parametrize("changed", ["sidecar", "corpus", "deleted", "moved"])
def test_stale_retry_does_not_overwrite_or_resurrect_capture(publication, monkeypatch, changed):
    state = publication
    _fail_sidecar(state, monkeypatch)
    _assert_failed_save(state, _request(state))
    if changed == "sidecar":
        (state.folder / f"{state.folder.name}.json").write_text(json.dumps({
            "url": URL_A, "video_id": "aaaaaaaaaaa", "title": "new user metadata"}))
    elif changed == "corpus":
        (state.folder / f"{state.folder.name}.md").write_bytes(b"newer user content")
    elif changed == "deleted":
        state.idx.upsert_yoink({"video_id": "aaaaaaaaaaa", "slug": state.folder.name,
                               "yoinked_at": "2026-10-16T12:00:00",
                               "sidecar_path": str(state.folder / f"{state.folder.name}.json"),
                               "corpus_path": str(state.folder / f"{state.folder.name}.md")})
        state.idx._conn.execute("UPDATE yoinks SET deleted_at='2026-10-16'")
        state.idx._conn.commit()
    else:
        state.idx.upsert_yoink({"video_id": "aaaaaaaaaaa", "slug": "new-location",
                               "yoinked_at": "2026-10-16T12:00:00",
                               "sidecar_path": str(state.folder.parent / "new-location" / "new.json"),
                               "corpus_path": str(state.folder.parent / "new-location" / "new.md")})
    before = _snapshot(state.folder)
    row_before = state.idx.get_yoink("aaaaaaaaaaa")
    assert state.scope["_retry_publication_one"]() is True
    assert _snapshot(state.folder) == before
    assert state.idx.get_yoink("aaaaaaaaaaa") == row_before
    assert _job(state)["state"] == "failed"
    # No newer attempt exists, so the refusal ends the "retry is queued" job.
    assert "One publication retry is queued" not in _job(state)["error"]
    assert "publication retry refused" in _job(state)["error"]


def test_old_retry_does_not_replace_new_completed_job(publication, monkeypatch):
    state = publication
    with monkeypatch.context() as patch:
        patch.setattr(state.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected full")))
        _assert_failed_save(state, _request(state))
    monkeypatch.setitem(state.scope, "_fetch_metadata", lambda url: _metadata(url, title="New title"))
    assert _request(state)["ok"] is True
    completed = _job(state)
    assert completed["state"] == "completed"
    receipt_id, _ = state.queue.next_pending()
    assert state.scope["_retry_publication_one"]() is True
    assert _job(state) == completed
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == "failed"
    assert "deleted or moved" in outcome["error"]


def test_receipt_write_failure_is_visible_and_preserves_artifacts(publication, monkeypatch):
    state = publication
    _fail_sidecar(state, monkeypatch)
    monkeypatch.setattr(index.PublicationRetryQueue, "enqueue",
                        Mock(side_effect=OSError("injected receipt disk full")))
    response = _request(state)
    _assert_failed_save(state, response)
    assert "retry could not be queued" in response["error"]
    assert "injected receipt disk full" in response["error"]
    assert state.queue.next_pending() is None


def test_ownership_wait_does_not_spend_retry(publication, monkeypatch):
    state = publication
    _fail_sidecar(state, monkeypatch)
    _request(state)
    pending = state.queue.next_pending()
    monkeypatch.setitem(state.scope, "_manual_extraction_ownership",
                        lambda url: nullcontext(SimpleNamespace(ok=False)))
    assert state.scope["_retry_publication_one"]() is False
    assert state.queue.next_pending() == pending
    assert not list(state.queue.root.glob("*.attempt.json"))


def test_interrupted_retry_is_not_run_twice(publication, monkeypatch):
    state = publication
    _fail_sidecar(state, monkeypatch)
    _request(state)
    receipt_id, _ = state.queue.next_pending()
    assert state.queue.claim(receipt_id) is True
    before = _snapshot(state.folder)
    publish = Mock(side_effect=AssertionError("must not repeat an interrupted retry"))
    monkeypatch.setitem(state.scope, "_index_yoink", publish)
    assert state.scope["_retry_publication_one"]() is True
    publish.assert_not_called()
    assert _snapshot(state.folder) == before
    assert "interrupted" in _job(state)["error"]
    assert state.queue.next_pending() is None


@pytest.mark.parametrize("result", [
    {"ok": False, "error": "save failed", "failure_phase": "save"},
    {"ok": True, "status": "saved_with_errors", "reason": "index failed"},
])
def test_error_result_never_becomes_completed_job(publication, result):
    job = publication.scope["_record_single_extract_job"](URL_A, "2026-10-16", result=result)
    assert job["state"] == "failed"
    assert job["videos_done"] == 0
    assert job["current_video_phase"] == "save"
    assert _job(publication)["state"] == "failed"


def test_successful_capture_is_unchanged_and_has_no_retry(publication):
    publication.scope["_read_settings"] = lambda: {"keep_media": False}
    response = _request(publication)
    assert response["ok"] is True
    assert _job(publication)["state"] == "completed"
    assert publication.queue.next_pending() is None
    assert not publication.queue.root.exists()
    assert not (publication.folder / "video.mp4").exists()


def test_queue_write_failure_never_replaces_existing_receipt(tmp_path, monkeypatch):
    queue = index.PublicationRetryQueue(tmp_path / "receipts")
    record = {"folder": "saved", "sidecar": {"video_id": "first"}}
    receipt_id = queue.enqueue(record)
    before = _snapshot(tmp_path)
    monkeypatch.setattr(index.os, "fsync", Mock(side_effect=OSError("injected disk full")))
    with pytest.raises(OSError, match="disk full"):
        queue.enqueue(record)
    assert _snapshot(tmp_path) == before
    assert queue.next_pending() == (receipt_id, record)


def test_legacy_none_index_return_does_not_queue_first_capture_or_refresh(publication, monkeypatch):
    monkeypatch.setitem(publication.scope, "_index_yoink", Mock(return_value=None))
    for _ in range(2):
        assert _request(publication)["ok"] is True
        assert _job(publication)["state"] == "completed"
        assert not publication.queue.root.exists()


def test_legacy_none_index_return_accepts_publication_retry(publication, monkeypatch):
    _fail_sidecar(publication, monkeypatch)
    _assert_failed_save(publication, _request(publication))
    monkeypatch.setitem(publication.scope, "_index_yoink", Mock(return_value=None))
    assert publication.scope["_retry_publication_one"]() is True
    assert _job(publication)["state"] == "completed"
    publication.scope["_start_comments_thread"].assert_called_once()


@pytest.mark.parametrize("changed", [False, True])
def test_retry_cleans_only_unchanged_unretained_downloads(publication, monkeypatch, changed):
    state = publication
    state.scope["_read_settings"] = lambda: {"keep_media": False}
    _fail_sidecar(state, monkeypatch)
    _assert_failed_save(state, _request(state))
    media = state.folder / "video.mp4"
    if changed:
        media.write_bytes(b"replacement supplied after the failed save")
    extra = state.folder / "video-chunk-user.mp4"
    extra.write_bytes(b"user media outside the receipt")
    assert state.scope["_retry_publication_one"]() is True
    assert _job(state)["state"] == "completed"
    assert media.exists() is changed
    if changed:
        assert media.read_bytes() == b"replacement supplied after the failed save"
    assert extra.read_bytes() == b"user media outside the receipt"
    row = state.idx.get_yoink("aaaaaaaaaaa")
    assert Path(row["corpus_path"]).is_file()
    assert "media_file" not in json.loads(Path(row["sidecar_path"]).read_text())


def test_retry_resumes_local_reliability_before_removing_download(publication, monkeypatch):
    state = publication
    state.scope["_read_settings"] = lambda: {
        "keep_media": False, "transcript_reliability_auto_check": True}
    _fail_sidecar(state, monkeypatch)
    _assert_failed_save(state, _request(state))
    sidecar_path = state.folder / f"{state.folder.name}.json"

    def reliability(video_id, **kwargs):
        assert video_id == "aaaaaaaaaaa"
        assert kwargs["audio_path"].read_bytes() == b"media"
        assert kwargs["allow_model_download"] is False
        return {"ok": True}

    check = Mock(side_effect=reliability)
    state.scope.update({
        "_compute_transcript_reliability": check, "RELIABILITY_DEFAULT_THRESHOLD": 0.6,
        "_read_sidecar_for_folder": lambda folder: (
            sidecar_path, json.loads(sidecar_path.read_text(encoding="utf-8"))),
    })
    assert state.scope["_retry_publication_one"]() is True
    check.assert_called_once()
    assert not (state.folder / "video.mp4").exists()
    assert _job(state)["state"] == "completed"


@pytest.mark.parametrize("failure", ["sidecar", "index"])
def test_session_keeps_saved_capture_even_if_closed_before_retry(publication, tmp_path, monkeypatch, failure):
    state = publication
    handler, folder, session = _session_handler(state.capture, tmp_path)
    state.folder = state.scope["_video_capture_folder"](folder, URL_A, _metadata(URL_A))
    with monkeypatch.context() as patch:
        if failure == "sidecar":
            _fail_sidecar(state, patch)
        else:
            patch.setattr(state.idx, "upsert_yoink", Mock(side_effect=sqlite3.OperationalError("full")))
        state.scope["_handle_session_add"](handler, {"url": URL_A})
    response = handler.response[1]
    assert response["ok"] is True
    assert response["status"] == "saved_with_errors"
    assert response["reason"] == response["error"]
    assert "Capture publication failed" in response["reason"]
    assert "One publication retry is queued" in response["reason"]
    assert response["failure_phase"] == "save"
    assert response["video_count"] == 1
    assert len(session["videos"]) == 1
    assert session["videos"][0]["video_slug"] == state.folder.name
    assert _job(state)["state"] == "failed"
    state.scope["_handle_session_close"](handler, {})
    assert handler.response[1]["ok"] is True
    assert (folder / "corpus.md").read_text(encoding="utf-8").count(f"Body for {URL_A}") == 1
    session_before = (folder / "session.json").read_bytes()
    calls_before = list(state.capture.calls)
    assert state.scope["_retry_publication_one"]() is True
    assert _job(state)["state"] == "completed"
    assert (folder / "session.json").read_bytes() == session_before
    assert state.capture.calls == calls_before


@pytest.mark.parametrize("failure", ["sidecar", "index"])
@pytest.mark.parametrize("successful_videos", [0, 1])
def test_playlist_reports_original_save_failure_and_retry_has_separate_outcome(
        publication, tmp_path, monkeypatch, failure, successful_videos):
    state = publication
    job, folder = _playlist_job(
        state.capture, tmp_path, urls=(URL_A, URL_B) if successful_videos else (URL_A,))
    job["warnings"] = ["Existing playlist warning."]
    state.folder = state.scope["_video_capture_folder"](folder, URL_A, _metadata(URL_A))
    upsert = state.idx.upsert_yoink

    def fail_first_capture(row, **kwargs):
        if row["video_id"] == "aaaaaaaaaaa":
            raise sqlite3.OperationalError("injected database full")
        return upsert(row, **kwargs)

    with monkeypatch.context() as patch:
        if failure == "sidecar":
            _fail_sidecar(state, patch)
        else:
            patch.setattr(state.idx, "upsert_yoink", fail_first_capture)
        state.scope["_playlist_worker"]("playlist-test")
    assert job["state"] == ("completed" if successful_videos else "failed")
    assert job["current_video_phase"] == (None if successful_videos else "save")
    assert job["videos_done"] == successful_videos
    assert job["videos_failed"] == 1
    assert job["error"] == (None if successful_videos else "Some captures could not be published.")
    assert len(job["per_video"]) == successful_videos + 1
    item = job["per_video"][0]
    assert item["ok"] is False
    assert item["status"] == "saved_with_errors"
    assert "Capture publication failed" in item["error"]
    assert job["warnings"] == ["Existing playlist warning.", f"Video 1: {item['error']}"]
    assert item["publication_retry_id"]
    assert Path(item["md_path"]).is_file()
    assert not (state.folder / "FAILED.txt").exists()
    assert (folder / "corpus.md").read_text(encoding="utf-8").count(f"Body for {URL_A}") == 1
    assert job["result"]["combined_md_text"].count(f"Body for {URL_A}") == 1
    if successful_videos:
        assert job["per_video"][1]["ok"] is True
        assert (folder / "corpus.md").read_text(encoding="utf-8").count(f"Body for {URL_B}") == 1
        assert job["result"]["combined_md_text"].count(f"Body for {URL_B}") == 1
    original_attempt = json.dumps(job, sort_keys=True)
    state.scope["_manual_extraction_ownership"] = lambda url: nullcontext(
        SimpleNamespace(ok=True, conflict=None))
    record_job = Mock()
    state.scope["_record_single_extract_job"] = record_job
    calls_before = list(state.capture.calls)
    assert state.scope["_retry_publication_one"]() is True
    assert record_job.call_args.kwargs["result"]["ok"] is True
    assert record_job.call_args.kwargs["error"] is None
    assert json.dumps(job, sort_keys=True) == original_attempt
    assert state.capture.calls == calls_before


@pytest.mark.parametrize("failure", ["sidecar", "index"])
def test_pending_download_hands_off_to_one_local_publication_retry(publication, monkeypatch, failure):
    state = publication
    state.scope.update({"_pending_long_video_mode": Mock(), "_sanitize_error": str})
    _load(ROOT / "server.py", {"_retry_pending_one"}, state.scope)
    pending_id = state.idx.enqueue_pending(URL_A, 30, "2026-10-14T00:00:00", "full")
    with monkeypatch.context() as patch:
        if failure == "sidecar":
            _fail_sidecar(state, patch)
        else:
            patch.setattr(state.idx, "upsert_yoink", Mock(side_effect=sqlite3.OperationalError("full")))
        assert state.scope["_retry_pending_one"]() is True
    row, = state.idx.list_pending(include_terminal=True)
    assert row["pending_id"] == pending_id
    assert row["status"] == "failed"
    assert "One publication retry is queued" in row["last_error"]
    receipt_id, record = index.PublicationRetryQueue(state.queue.root).next_pending()
    assert record["pending_id"] == pending_id
    assert _job(state)["current_video_phase"] == "save"
    calls_before = list(state.capture.calls)
    assert state.scope["_retry_pending_one"]() is False
    assert state.scope["_retry_publication_one"]() is True
    job = _job(state)
    assert job["state"] == "completed"
    succeeded, = state.idx.list_pending(include_terminal=True)
    assert succeeded == dict(row, status="succeeded", last_error=None, succeeded_job_id=job["id"])
    assert state.idx.retry_pending_now(pending_id) is False
    assert state.scope["_retry_pending_one"]() is False
    assert state.scope["_retry_publication_one"]() is False
    assert state.queue.enqueue(record) == receipt_id
    assert state.queue.next_pending() is None
    assert state.capture.calls == calls_before


@pytest.mark.parametrize("failure", ["publication", "queue_settlement"])
def test_pending_publication_retry_does_not_report_failed_settlement_as_success(
        publication, monkeypatch, failure):
    state = publication
    state.scope.update({"_pending_long_video_mode": Mock(), "_sanitize_error": str})
    _load(ROOT / "server.py", {"_retry_pending_one"}, state.scope)
    pending_id = state.idx.enqueue_pending(URL_A, 30, "2026-10-14T00:00:00", "full")
    with monkeypatch.context() as patch:
        patch.setattr(state.idx, "upsert_yoink", Mock(side_effect=sqlite3.OperationalError("full")))
        assert state.scope["_retry_pending_one"]() is True
    receipt_id, record = state.queue.next_pending()
    assert record["pending_id"] == pending_id
    before = _snapshot(state.folder)
    calls_before = list(state.capture.calls)
    with monkeypatch.context() as patch:
        if failure == "publication":
            patch.setitem(state.scope, "_index_yoink", Mock(
                side_effect=sqlite3.OperationalError("injected retry publication failure")))
        else:
            patch.setattr(state.idx, "mark_pending_succeeded", Mock(
                side_effect=sqlite3.OperationalError("injected retry queue settlement failure")))
        assert state.scope["_retry_publication_one"]() is True
    row, = state.idx.list_pending(include_terminal=True)
    assert row["status"] == "failed"
    assert row["succeeded_job_id"] is None
    job = _job(state)
    assert job["state"] == "failed"
    assert job["current_video_phase"] == "save"
    assert job["retry_exhausted"] is True
    assert "injected retry" in job["error"]
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == "failed"
    assert outcome["error"] == job["error"]
    assert state.scope["_retry_publication_one"]() is False
    assert _snapshot(state.folder) == before
    assert state.capture.calls == calls_before


def test_standing_save_failure_is_terminal_for_downloads(publication, monkeypatch):
    state = publication
    service = SimpleNamespace(
        claim_execution=Mock(return_value={"outcome": "active"}),
        complete_capture=Mock(), fail_capture=Mock(return_value={"outcome": "failed"}))
    backend = SimpleNamespace(kind="test", _pacing=SimpleNamespace(),
                              _ensure_ownership=Mock(), holds_execution=lambda start: True,
                              release=Mock())
    source_api = SimpleNamespace(
        video_watch_url=lambda video_id: URL_A,
        CompletionProof=lambda *args: args,
        CaptureOutcome=lambda status: SimpleNamespace(status=status),
        CaptureOwnershipUnavailable=type("CaptureOwnershipUnavailable", (Exception,), {}),
        process_incarnation=lambda root: "test",
        capture_context=lambda *args: nullcontext(),
        settlement_releases_dispatcher_locks=lambda outcome: outcome["outcome"] == "failed")
    state.scope.update({
        "source_subscriptions": source_api, "_source_service": lambda: service,
        "_source_capture_threads_lock": threading.Lock(), "_source_capture_threads": {},
        "_sanitize_error": str,
        "threading": SimpleNamespace(Thread=lambda *, target, **kwargs: SimpleNamespace(start=target)),
    })
    _load(ROOT / "server.py", {"_run_youtube"}, state.scope, class_name="_ServerCaptureBackend")
    start = {"start_id": "test-start", "owner_token": "test-owner"}
    with monkeypatch.context() as patch:
        patch.setattr(state.idx, "upsert_yoink", Mock(side_effect=sqlite3.OperationalError("full")))
        assert state.scope["_run_youtube"](backend, start, {"entry_id": "aaaaaaaaaaa"}, {}).status == "in_flight"
    service.complete_capture.assert_not_called()
    service.fail_capture.assert_called_once_with(
        "test-start", "test-owner", "publication_failed", terminal=True,
        proof=("test-start", "test-owner", "test", "worker_finished"))
    backend.release.assert_called_once_with(start)
    assert _job(state)["current_video_phase"] == "save"
    calls_before = list(state.capture.calls)
    assert state.scope["_retry_publication_one"]() is True
    assert _job(state)["state"] == "completed"
    # Source completion requires a started/uncertain entry and verified
    # executor completion. This local retry cannot reopen a failed start;
    # the source item stays publication_failed while Activity records recovery.
    service.complete_capture.assert_not_called()
    assert service.fail_capture.call_count == 1
    assert state.capture.calls == calls_before


@pytest.mark.parametrize("mode", ["lite", "chunked"])
def test_retry_keeps_capture_mode_and_removes_its_unretained_inputs(publication, monkeypatch, mode):
    state = publication
    state.scope.update({
        "_read_settings": lambda: {"keep_media": False},
        "_long_video_chunks": lambda duration: [
            {"start_seconds": 0, "end_seconds": 10, "duration_seconds": 10},
            {"start_seconds": 20, "end_seconds": 30, "duration_seconds": 10}],
        "_chunk_section_spec": lambda chunk: f"*{chunk['start_seconds']}-{chunk['end_seconds']}",
    })

    def media_command(cmd, **kwargs):
        state.capture.calls.append(cmd)
        if cmd[0] == "ffmpeg":
            Path(cmd[-1].replace("%04d", "0001")).write_bytes(b"jpeg")
        else:
            template = cmd[cmd.index("-o") + 1]
            for number in range(1, (cmd.count("--download-sections") or 1) + 1):
                path = template.replace("%(section_number)03d", f"{number:03d}")
                Path(path.replace("%(ext)s", "mp4")).write_bytes(b"media")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    state.scope["_run_subprocess"] = media_command
    _fail_sidecar(state, monkeypatch)
    with pytest.raises(PermissionError) as raised:
        state.scope["_run_extraction"](
            URL_A, 30, state.folder, metadata=_metadata(URL_A, duration=7200),
            topic="Test", source_type="short_video", long_video_mode=mode)
    assert raised.value.phase == "save"
    assert len(list(state.folder.glob("video*.mp4"))) == (2 if mode == "chunked" else 1)
    _, record = state.queue.next_pending()
    assert record["sidecar"]["long_video_mode"] == mode
    calls_before = list(state.capture.calls)
    assert state.scope["_retry_publication_one"]() is True
    assert _job(state)["state"] == "completed"
    assert not list(state.folder.glob("video*.mp4"))
    assert state.capture.calls == calls_before
    state.scope["_start_entity_extraction_thread"].assert_called_once()
    if mode == "lite":
        state.scope["_start_comments_thread"].assert_not_called()
        assert record["sidecar"]["comments_status"] == "skipped"
        assert record["sidecar"]["hook_type_status"] == "skipped"
    else:
        state.scope["_start_comments_thread"].assert_called_once()


def test_retry_does_not_require_best_effort_metadata_cache(publication, monkeypatch):
    state = publication
    _fail_sidecar(state, monkeypatch)
    _assert_failed_save(state, _request(state))
    # The optional metadata cache can be absent. The receipt carries the
    # inputs needed to start comments and hook typing after publication.
    (state.folder / "metadata.json").unlink()
    assert state.scope["_retry_publication_one"]() is True
    assert _job(state)["state"] == "completed"
    state.scope["_start_comments_thread"].assert_called_once()


def _assert_tail_not_started(state):
    state.scope["_start_comments_thread"].assert_not_called()
    state.scope["_start_entity_extraction_thread"].assert_not_called()


@pytest.mark.parametrize("failure", ["sharing_violation", "offline_drive"])
def test_transient_verification_error_records_failed_retry(publication, monkeypatch, failure):
    state = publication
    _fail_sidecar(state, monkeypatch)
    _assert_failed_save(state, _request(state))
    receipt_id, _ = state.queue.next_pending()
    assert receipt_id in _job(state)["error"]
    before = _snapshot(state.folder)
    with monkeypatch.context() as patch:
        if failure == "sharing_violation":
            read_text = Path.read_text

            def locked(path, *args, **kwargs):
                if path == state.folder / ".capture-source.json":
                    raise PermissionError(13, "file is being used by another process", str(path))
                return read_text(path, *args, **kwargs)

            patch.setattr(Path, "read_text", locked)
        else:
            # An unplugged drive reports the folder and its volume as missing.
            iterdir, exists = Path.iterdir, Path.exists
            offline = {state.folder, Path(state.folder.anchor)}

            def missing_folder(path):
                if path == state.folder:
                    raise FileNotFoundError(3, "The system cannot find the path specified", str(path))
                return iterdir(path)

            patch.setattr(Path, "iterdir", missing_folder)
            patch.setattr(Path, "exists", lambda path, *args, **kwargs: (
                False if path in offline else exists(path, *args, **kwargs)))
        assert state.scope["_retry_publication_one"]() is True
    assert _snapshot(state.folder) == before
    assert state.idx.get_yoink("aaaaaaaaaaa") is None
    job = _job(state)
    assert job["state"] == "failed"
    assert job["current_video_phase"] == "save"
    assert job["retry_exhausted"] is True
    assert "Capture publication retry failed" in job["error"]
    assert "One publication retry is queued" not in job["error"]
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == "failed"
    assert outcome["code"] == "publication_failed"
    assert outcome["error"] == job["error"]
    _assert_tail_not_started(state)
    assert state.scope["_retry_publication_one"]() is False


def test_removed_folder_refusal_still_ends_queued_activity_job(publication, monkeypatch, tmp_path):
    state = publication
    _fail_sidecar(state, monkeypatch)
    _assert_failed_save(state, _request(state))
    receipt_id, _ = state.queue.next_pending()
    moved = tmp_path / "moved-away"
    shutil.move(str(state.folder), str(moved))
    before = _snapshot(moved)
    assert state.scope["_retry_publication_one"]() is True
    assert not state.folder.exists()
    assert _snapshot(moved) == before
    job = _job(state)
    assert job["state"] == "failed"
    assert job["retry_exhausted"] is True
    assert "capture folder was removed" in job["error"]
    assert receipt_id not in job["error"]
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == "failed"
    assert outcome["code"] == "obsolete"
    _assert_tail_not_started(state)


SCREENSHOT_CITATION = {"kind": "screenshot", "seq": 1, "timestamp_start": 0.0,
                       "timestamp_end": None, "text": None,
                       "file_path": "screenshots/shot_0001.jpg"}


def _backfill_after_failed_save(state, monkeypatch, backfill):
    """Fail a first capture's upsert, then run startup backfill on it.

    ``published`` completes backfill publication. ``failed_after_sidecar``
    commits the row and replaces the sidecar, then fails before the media
    and citation commit, as the Phase 6 publisher can."""
    state.scope.update({
        "_trash_root": lambda: state.scope["DESKTOP_ROOT"] / "_yoink-trash",
        "_backfill_lock": threading.Lock(), "_backfill_state": {},
        "_backfill_cancel": threading.Event(), "_index_recovering": True,
    })
    _load(ROOT / "server.py", {"_run_backfill", "_iter_corpus_folders"}, state.scope)
    monkeypatch.setitem(state.scope, "_citations_from_sidecar",
                        lambda sidecar, folder: [dict(SCREENSHOT_CITATION)])
    with monkeypatch.context() as patch:
        patch.setattr(state.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected database full")))
        _assert_failed_save(state, _request(state))
    receipt_id, record = state.queue.next_pending()
    sidecar_path = state.folder / f"{state.folder.name}.json"
    insert_citations = state.idx.insert_citations

    def phase6_commit(video_id, citations):
        # The Phase 6 publisher replaces the complete sidecar before its commit.
        side = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar_path.write_text(json.dumps(dict(side, media_depth={"revision": "backfill"})),
                                encoding="utf-8")
        if backfill == "failed_after_sidecar":
            raise sqlite3.OperationalError("injected media commit failure")
        return insert_citations(video_id, citations)

    with monkeypatch.context() as patch:
        patch.setattr(state.idx, "insert_citations", phase6_commit)
        state.scope["_run_backfill"]()
    row = state.idx.get_yoink("aaaaaaaaaaa")
    assert Path(row["corpus_path"]).parent == state.folder
    assert hashlib.sha256(sidecar_path.read_bytes()).hexdigest() != record["sidecar_sha256"]
    assert len(state.idx.get_citations("aaaaaaaaaaa")) == (backfill == "published")
    return receipt_id, row


@pytest.mark.parametrize("backfill, retry", [
    ("published", "publishes"),
    ("failed_after_sidecar", "publishes"),
    ("failed_after_sidecar", "fails"),
])
def test_backfill_before_retry_is_published_again_before_completion(
        publication, monkeypatch, backfill, retry):
    state = publication
    receipt_id, row = _backfill_after_failed_save(state, monkeypatch, backfill)
    before = _snapshot(state.folder)
    calls_before = list(state.capture.calls)
    index_yoink = state.scope["_index_yoink"]
    published_from = []

    def publish(folder, sidecar, corpus_path, path):
        published_from.append(json.loads(json.dumps(sidecar)))
        if retry == "fails":
            raise sqlite3.OperationalError("injected retry publication failure")
        return index_yoink(folder, sidecar, corpus_path, path)

    monkeypatch.setitem(state.scope, "_index_yoink", publish)
    assert state.scope["_retry_publication_one"]() is True
    # A row alone is not completion: the retry publishes once, from the
    # sidecar on disk, and never writes the receipt's older copy over it.
    assert [side.get("media_depth") for side in published_from] == [{"revision": "backfill"}]
    assert _snapshot(state.folder) == before
    job = _job(state)
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    if retry == "publishes":
        assert state.idx.get_citations("aaaaaaaaaaa")[0]["file_path"] == SCREENSHOT_CITATION["file_path"]
        assert job["state"] == "completed"
        assert job["error"] is None
        assert outcome["status"] == "succeeded"
        entity_args = state.scope["_start_entity_extraction_thread"].call_args.args
        assert entity_args[2]["media_depth"] == {"revision": "backfill"}
        args = state.scope["_start_comments_thread"].call_args.args
        assert args[:3] == (URL_A, state.folder, Path(row["corpus_path"]))
        state.scope["_start_comments_thread"].assert_called_once()
    else:
        assert state.idx.get_citations("aaaaaaaaaaa") == []
        assert job["state"] == "failed"
        assert job["retry_exhausted"] is True
        assert "injected retry publication failure" in job["error"]
        assert outcome["status"] == "failed"
        assert outcome["code"] == "publication_failed"
        _assert_tail_not_started(state)
    state.scope["_incremental_index_update"].assert_called_once()  # capture only
    assert state.capture.calls == calls_before
    assert state.scope["_retry_publication_one"]() is False


def test_obsolete_refusal_never_reports_completion_from_a_library_row(publication, monkeypatch):
    state = publication
    receipt_id, row = _backfill_after_failed_save(state, monkeypatch, "published")
    (state.folder / f"{state.folder.name}.md").write_bytes(b"edited after backfill")
    before = _snapshot(state.folder)
    publish = Mock(side_effect=AssertionError("an obsolete receipt must not publish"))
    monkeypatch.setitem(state.scope, "_index_yoink", publish)
    assert state.scope["_retry_publication_one"]() is True
    publish.assert_not_called()
    assert _snapshot(state.folder) == before
    assert state.idx.get_yoink("aaaaaaaaaaa") == row
    # Newer corpus bytes are never published by the old receipt, and it
    # cannot verify the row is a complete publication: the queued job ends
    # failed rather than completed.
    job = _job(state)
    assert job["state"] == "failed"
    assert job["retry_exhausted"] is True
    assert "capture changed; publication retry refused" in job["error"]
    assert receipt_id not in job["error"]
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == "failed"
    assert outcome["code"] == "obsolete"
    _assert_tail_not_started(state)


@pytest.mark.parametrize("old_outcome", ["sharing_violation", "malformed_json", "published"])
def test_old_receipt_outcome_never_replaces_newer_activity_job(publication, monkeypatch, old_outcome):
    state = publication
    with monkeypatch.context() as patch:
        _fail_sidecar(state, patch)
        _assert_failed_save(state, _request(state))
    receipt_id, _ = state.queue.next_pending()
    if old_outcome == "published":
        # A newer attempt that failed before indexing, so the old receipt
        # can still publish its own folder.
        state.scope["_record_single_extract_job"](
            URL_A, state.scope["_now_iso"](), error="newer attempt failed to download",
            failure_phase="download")
    else:
        # A newer attempt captured the same source into another folder.
        monkeypatch.setitem(state.scope, "_fetch_metadata",
                            lambda url: _metadata(url, title="New title"))
        assert _request(state)["ok"] is True
    newer = _job(state)
    assert receipt_id not in str(newer["error"])
    with monkeypatch.context() as patch:
        if old_outcome == "sharing_violation":
            read_text = Path.read_text

            def locked(path, *args, **kwargs):
                if path == state.folder / ".capture-source.json":
                    raise PermissionError(13, "file is being used by another process", str(path))
                return read_text(path, *args, **kwargs)

            patch.setattr(Path, "read_text", locked)
        elif old_outcome == "malformed_json":
            (state.folder / "metadata.json").write_text("{not json", encoding="utf-8")
        assert state.scope["_retry_publication_one"]() is True
    assert _job(state) == newer
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    if old_outcome == "published":
        assert outcome["status"] == "succeeded"
        assert Path(state.idx.get_yoink("aaaaaaaaaaa")["corpus_path"]).parent == state.folder
    else:
        assert outcome["status"] == "failed"
        assert outcome["code"] == "publication_failed"
    assert state.scope["_retry_publication_one"]() is False


SECRET_TRANSCRIPT = "SECRET-TRANSCRIPT-PHRASE"
SECRET_DESCRIPTION = "SECRET-DESCRIPTION-TEXT"


def _capture_secret_content(state):
    state.scope.update({
        "_fetch_metadata": lambda url: _metadata(url, description=SECRET_DESCRIPTION),
        "_resolve_video_transcript": lambda *a, **k: (
            [(0.0, 2.0, SECRET_TRANSCRIPT)], "captions", None),
        "_transcript_entries_with_links": lambda seed, entries: [
            {"start": start, "end": end, "text": text} for start, end, text in entries],
    })


def _queue_files(state):
    return {path.name: path.read_text(encoding="utf-8")
            for path in state.queue.root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "obsolete", "compaction_interrupted"])
def test_settled_receipt_keeps_no_transcript_or_metadata(publication, monkeypatch, outcome):
    state = publication
    _capture_secret_content(state)
    with monkeypatch.context() as patch:
        patch.setattr(state.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected database full")))
        _assert_failed_save(state, _request(state))
    receipt_id, record = state.queue.next_pending()
    stored = (state.queue.root / f"{receipt_id}.json").read_text(encoding="utf-8")
    assert SECRET_TRANSCRIPT in stored and SECRET_DESCRIPTION in stored
    with monkeypatch.context() as patch:
        if outcome == "failed":
            patch.setattr(state.idx, "upsert_yoink", Mock(
                side_effect=sqlite3.OperationalError("injected database full")))
        elif outcome == "obsolete":
            (state.folder / f"{state.folder.name}.md").write_bytes(b"newer user content")
        elif outcome == "compaction_interrupted":
            patch.setattr(index.PublicationRetryQueue, "_replace", Mock(
                side_effect=PermissionError("injected sharing violation")))
        assert state.scope["_retry_publication_one"]() is True
    if outcome == "compaction_interrupted":
        # Settled and unable to run again; the next start removes the content.
        assert state.queue.next_pending() is None
        assert SECRET_TRANSCRIPT in (state.queue.root / f"{receipt_id}.json").read_text(
            encoding="utf-8")
        assert state.queue.compact_settled() == 1
        assert state.queue.compact_settled() == 0
    files = {path.name: path.read_text(encoding="utf-8")
             for path in state.queue.root.rglob("*") if path.is_file()}
    assert set(files) == {f"{receipt_id}.json", f"{receipt_id}.result.json"}
    for text in files.values():
        assert SECRET_TRANSCRIPT not in text
        assert SECRET_DESCRIPTION not in text
    tombstone = json.loads(files[f"{receipt_id}.json"])
    assert tombstone["tombstone"] is True
    assert tombstone["receipt_id"] == receipt_id
    assert tombstone["video_id"] == "aaaaaaaaaaa"
    assert tombstone["status"] == ("failed" if outcome in ("failed", "obsolete") else "succeeded")
    assert tombstone["error_code"] == {"failed": "publication_failed", "obsolete": "obsolete"}.get(outcome)
    assert tombstone["settled_at"] and tombstone["started_at"] and tombstone["created_at"]
    assert not {"sidecar", "metadata", "entries", "folder"} & set(tombstone)
    # The same request can never be stored or run again.
    assert state.queue.enqueue(record) == receipt_id
    assert state.queue.next_pending() is None
    assert {path.name: path.read_text(encoding="utf-8")
            for path in state.queue.root.rglob("*") if path.is_file()} == files
    assert state.scope["_retry_publication_one"]() is False


@pytest.mark.parametrize("cleanup_blocked_at_settle", [False, True])
def test_orphaned_temporary_receipt_copy_is_removed_once_settled(
        publication, monkeypatch, cleanup_blocked_at_settle):
    state = publication
    _capture_secret_content(state)
    root = state.queue.root
    unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if path.parent == root and path.name.endswith(".tmp"):
            raise PermissionError(32, "file is being used by another process", str(path))
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", locked)
        patch.setattr(state.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected database full")))
        _assert_failed_save(state, _request(state))
    # Enqueue succeeded, but its temporary copy of the request stayed behind.
    receipt_id, _ = state.queue.next_pending()
    orphan, = root.glob("*.tmp")
    assert orphan.name.startswith(f"{receipt_id}.json.")
    assert SECRET_TRANSCRIPT in orphan.read_text(encoding="utf-8")
    # A pending request still holds the same data; its copy waits for settlement.
    assert state.queue.compact_settled() == 0
    assert orphan.exists()
    with monkeypatch.context() as patch:
        if cleanup_blocked_at_settle:
            patch.setattr(Path, "unlink", locked)
        assert state.scope["_retry_publication_one"]() is True
    assert _job(state)["state"] == "completed"
    if cleanup_blocked_at_settle:
        # Still locked at settlement: the next start retries the cleanup.
        assert orphan.exists()
        assert state.queue.compact_settled() == 1
        assert state.queue.compact_settled() == 0
    files = _queue_files(state)
    assert set(files) == {f"{receipt_id}.json", f"{receipt_id}.result.json"}
    for text in files.values():
        assert SECRET_TRANSCRIPT not in text
        assert SECRET_DESCRIPTION not in text


def test_abandoned_temporary_copy_without_request_is_removed_after_grace(tmp_path):
    queue = index.PublicationRetryQueue(tmp_path / "receipts")
    queue.root.mkdir()
    old = queue.root / f"{'a' * 64}.json.abandoned.tmp"
    fresh = queue.root / f"{'b' * 64}.json.writing.tmp"
    unowned = queue.root / "unrelated.tmp"
    for path in (old, fresh, unowned):
        path.write_text(json.dumps({"transcript": SECRET_TRANSCRIPT}), encoding="utf-8")
    hour_ago = time.time() - 7200
    os.utime(old, (hour_ago, hour_ago))
    os.utime(unowned, (hour_ago, hour_ago))
    # Only an owned copy whose request was never stored, and that no writer
    # can still be finishing, is removed. Other files are left alone.
    assert queue.compact_settled() == 1
    assert not old.exists()
    assert fresh.exists()
    assert unowned.exists()


def _lock_capture_source(state, patch):
    read_text = Path.read_text

    def locked(path, *args, **kwargs):
        if path == state.folder / ".capture-source.json":
            raise PermissionError(13, "file is being used by another process", str(path))
        return read_text(path, *args, **kwargs)

    patch.setattr(Path, "read_text", locked)


@pytest.mark.parametrize("old_outcome", ["obsolete", "sharing_violation"])
def test_overlapping_newer_request_keeps_its_activity_job(publication, monkeypatch, old_outcome):
    state = publication
    clock = ["2026-10-15T12:00:10"]
    monkeypatch.setitem(state.scope, "_now_iso", lambda: clock[0])
    with monkeypatch.context() as patch:
        _fail_sidecar(state, patch)
        _assert_failed_save(state, _request(state))
    receipt_id, record = state.queue.next_pending()
    assert record["job_id"] == _job(state)["id"]
    # A second request started before this receipt existed, waited for the
    # capture lock, and completed after the failed attempt.
    clock[0] = "2026-10-15T12:00:05"
    monkeypatch.setitem(state.scope, "_fetch_metadata",
                        lambda url: _metadata(url, title="New title"))
    assert _request(state)["ok"] is True
    newer = _job(state)
    assert newer["state"] == "completed"
    assert newer["started_at"] < record["created_at"]
    clock[0] = "2026-10-15T12:00:20"
    with monkeypatch.context() as patch:
        if old_outcome == "sharing_violation":
            _lock_capture_source(state, patch)
        assert state.scope["_retry_publication_one"]() is True
    # Ownership, not timestamps, decides: the newer job is neither deleted
    # nor replaced by the older receipt's outcome.
    assert _job(state) == newer
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == "failed"
    assert outcome["code"] == ("obsolete" if old_outcome == "obsolete" else "publication_failed")
    assert state.scope["_retry_publication_one"]() is False


def test_interrupted_outcome_write_is_retried_and_compacted(publication, monkeypatch):
    state = publication
    _capture_secret_content(state)
    root = state.queue.root
    # Hard links are unavailable, so outcomes use the copy-and-move fallback.
    monkeypatch.setattr(Path, "hardlink_to", Mock(
        side_effect=OSError("hard links are unsupported on this volume")))
    with monkeypatch.context() as patch:
        patch.setattr(state.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected database full")))
        _assert_failed_save(state, _request(state))
    receipt_id, _ = state.queue.next_pending()
    result = root / f"{receipt_id}.result.json"
    replace = os.replace

    def disk_full(source, target):
        if Path(target) == result:
            raise OSError(errno.ENOSPC, "No space left on device", str(target))
        return replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(index.os, "replace", disk_full)
        assert state.scope["_retry_publication_one"]() is True
    # Activity reports what the attempt did, and no partial outcome exists.
    job = _job(state)
    assert job["state"] == "completed"
    assert not result.exists()
    assert not list(root.glob("*.tmp"))
    assert state.queue.next_pending()[0] == receipt_id
    # A truncated outcome from an interrupted in-place write settles nothing:
    # the receipt stays pending instead of being stranded with its content.
    result.write_text('{"status": "succ', encoding="utf-8")
    assert state.queue.next_pending()[0] == receipt_id
    assert state.queue.compact_settled() == 0
    assert SECRET_TRANSCRIPT in (root / f"{receipt_id}.json").read_text(encoding="utf-8")
    # Storage recovered: the next pass replaces the partial outcome, settles
    # and compacts the receipt, and leaves the attempt's Activity job alone.
    assert state.scope["_retry_publication_one"]() is True
    assert _job(state) == job
    outcome = json.loads(result.read_text(encoding="utf-8"))
    assert outcome["status"] == "failed"
    assert outcome["code"] == "interrupted"
    files = _queue_files(state)
    assert set(files) == {f"{receipt_id}.json", f"{receipt_id}.result.json"}
    for text in files.values():
        assert SECRET_TRANSCRIPT not in text
        assert SECRET_DESCRIPTION not in text
    assert json.loads(files[f"{receipt_id}.json"])["tombstone"] is True
    assert state.scope["_retry_publication_one"]() is False


@pytest.mark.parametrize("old_outcome", ["failed", "published", "published_pending"])
def test_newer_job_recorded_during_settlement_survives(publication, monkeypatch, old_outcome):
    state = publication
    pending_id = None
    with monkeypatch.context() as patch:
        _fail_sidecar(state, patch)
        if old_outcome == "published_pending":
            state.scope.update({"_pending_long_video_mode": Mock(), "_sanitize_error": str})
            _load(ROOT / "server.py", {"_retry_pending_one"}, state.scope)
            pending_id = state.idx.enqueue_pending(URL_A, 30, "2026-10-14T00:00:00", "full")
            assert state.scope["_retry_pending_one"]() is True
        else:
            _assert_failed_save(state, _request(state))
    receipt_id, record = state.queue.next_pending()
    assert record["job_id"] == _job(state)["id"]
    settle = index.PublicationRetryQueue.settle
    newer = []

    def settle_while_newer_extract_finishes(queue, *args, **kwargs):
        settle(queue, *args, **kwargs)
        # A successful /extract records its job after releasing capture
        # ownership, so it lands after every ownership check this retry made.
        newer.append(state.scope["_record_single_extract_job"](
            URL_A, state.scope["_now_iso"](),
            result={"ok": True, "folder": str(state.folder), "title": "Newer capture"}))

    monkeypatch.setattr(index.PublicationRetryQueue, "settle", settle_while_newer_extract_finishes)
    with monkeypatch.context() as patch:
        if old_outcome == "failed":
            _lock_capture_source(state, patch)
        assert state.scope["_retry_publication_one"]() is True
    # The newer job survives, and the older receipt's outcome is not recorded.
    job = _job(state)
    assert job["id"] == newer[0]["id"]
    assert job["state"] == "completed"
    assert job["title"] == "Newer capture"
    outcome = json.loads((state.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == ("failed" if old_outcome == "failed" else "succeeded")
    if pending_id is not None:
        # The queue row completes without linking to the unrecorded job.
        row, = state.idx.list_pending(include_terminal=True)
        assert row["status"] == "succeeded"
        assert row["succeeded_job_id"] is None
    assert state.scope["_retry_publication_one"]() is False
