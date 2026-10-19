"""Offline live-wait and retry cancellation regressions.

Load production functions without importing server or opening a user profile.
The shared fixture blocks network/subprocess I/O and uses temporary storage.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_publication_truth import publication
from test_unique_capture_folders import ROOT, URL_A, _load, _metadata, _snapshot, capture


@pytest.fixture
def retry(publication):
    state = publication
    scope = state.scope
    state.now = datetime(2026, 10, 16, 12)
    state.settings = {"live_stream_behavior": "wait_for_end", "keep_media": True}
    state.metadata = _metadata(URL_A)
    state.ownership = SimpleNamespace(
        ok=True, conflict=None, completed_while_waiting=False, reused=None,
        error="capture_ownership_unavailable")
    state.real_extract = scope["_run_extraction"]
    state.real_record = scope["_record_single_extract_job"]
    state.extract = Mock(return_value={
        "ok": True, "folder": str(state.folder), "title": "Recorded", "screenshot_count": 1})
    state.record = Mock(return_value={"id": "retry-job"})

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return state.now

    scope.update({
        "datetime": Clock, "timedelta": timedelta,
        "_now_iso": lambda: state.now.isoformat(),
        "_read_settings": lambda: state.settings,
        "_fetch_metadata": Mock(side_effect=lambda url, **kwargs: state.metadata),
        "_manual_extraction_ownership": Mock(side_effect=lambda url: nullcontext(state.ownership)),
        "_pending_long_video_mode": Mock(return_value="full"),
        "_remember_pending_long_video_mode": Mock(),
        "_run_extraction": state.extract, "_record_single_extract_job": state.record,
        "_make_job_id": lambda: "retry-job", "_sanitize_error": str, "friendly_error": str,
        "_check_queue_mutate_rate_limit": lambda: True,
        "_is_youtube_rate_limit": lambda e: isinstance(e, subprocess.CalledProcessError),
        "_youtube_rate_limit_detail": lambda e: "youtube_rate_limit: HTTP 429",
    })
    _load(ROOT / "server.py", {
        "_retry_pending_one", "_detect_live_state", "_normalize_live_behavior",
        "_is_youtube_ytdlp_call",
    }, scope, constants={
        "LIVE_STATE_NOT_LIVE", "LIVE_STATE_LIVE", "LIVE_STATE_UPCOMING",
        "LIVE_STATE_POST_LIVE", "LIVE_STATE_WAS_LIVE", "LIVE_BEHAVIOR_WAIT",
        "LIVE_BEHAVIOR_NOW", "_LIVE_BEHAVIORS", "_LIVE_RETRY_INTERVAL_SEC",
        "_RETRY_INITIAL_BACKOFF_SEC", "_RETRY_MAX_BACKOFF_SEC", "_RATE_LIMIT_BACKOFF_SEC",
    })
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8-sig"))
    cancelled = next(n for n in tree.body
                     if isinstance(n, ast.ClassDef) and n.name == "PlaylistJobCancelled")
    exec(compile(ast.Module(body=[cancelled], type_ignores=[]), "server.py", "exec"), scope)
    methods = {"_handle_extract", "_handle_live_extract_dispatch", "_handle_queue_cancel",
               "_validate_pending_id"}
    _load(ROOT / "server.py", methods, scope, class_name="Handler")
    handler = type("Handler", (), {name: scope[name] for name in methods})()
    handler._validate_url_interval = lambda body: (URL_A, 30, None)
    # _send_json really returns None. A response payload mock hid the bug.
    handler._send_json = lambda status, payload: state.responses.append((status, payload))
    state.handler = handler
    state.run = scope["_retry_pending_one"]
    return state


def _enqueue(state, attempts=0):
    pending_id = state.idx.enqueue_pending(URL_A, 30, "2026-10-15T00:00:00", "full")
    for _ in range(attempts):
        assert state.idx.mark_pending_running(pending_id)
        assert state.idx.mark_pending_failed(
            pending_id, "previous refusal", "2026-10-15T00:00:00",
            expected_status="running") == "pending"
    return pending_id


def _row(state):
    row, = state.idx.list_pending(include_terminal=True)
    return row


def _cancel(state, pending_id):
    state.handler._handle_queue_cancel({"pending_id": pending_id})
    assert state.responses[-1] == (200, {"ok": True})


def _cancel_too_late(state, pending_id):
    state.handler._handle_queue_cancel({"pending_id": pending_id})
    status, response = state.responses[-1]
    assert status == 409
    assert response["ok"] is False
    assert "too late to cancel" in response["error"]
    assert _row(state)["status"] == "publishing"
    event = state.idx._pending_cancel_events.get(pending_id)
    assert event is None or not event.is_set()


def _assert_cancelled(state):
    assert _row(state)["status"] == "cancelled"
    assert _row(state)["attempt_count"] == 0
    assert _row(state)["succeeded_job_id"] is None
    assert state.idx.next_pending("2099-01-01T00:00:00") is None
    assert state.idx.list_pending(include_terminal=False) == []
    assert state.idx._pending_cancel_events == {}
    state.record.assert_not_called()


@pytest.mark.parametrize("live_status", ["is_live", "is_upcoming", "post_live"])
def test_wait_dispatch_sends_one_response_and_never_extracts(retry, live_status):
    retry.metadata["live_status"] = live_status
    retry.handler._handle_extract({})
    response, = retry.responses
    assert response[0] == 200
    assert response[1]["queued"] is True
    assert response[1]["reason"] == "live_stream"
    assert _row(retry)["status"] == "pending"
    assert _row(retry)["attempt_count"] == 0
    retry.extract.assert_not_called()
    retry.record.assert_not_called()


@pytest.mark.parametrize("live_status", ["is_live", "is_upcoming", "post_live", "was_live"])
def test_recorded_mode_rejects_broadcasts_but_allows_recordings(retry, live_status):
    retry.settings["live_stream_behavior"] = "extract_when_recorded"
    retry.metadata["live_status"] = live_status
    retry.handler._handle_extract({})
    response, = retry.responses
    assert retry.idx.list_pending(include_terminal=True) == []
    if live_status in {"is_live", "is_upcoming"}:
        assert response[0] == 409
        retry.extract.assert_not_called()
        retry.record.assert_not_called()
    else:
        assert response[0] == 200
        retry.extract.assert_called_once()


def test_dispatch_flag_is_independent_of_send_json_return(retry):
    dispatch = retry.handler._handle_live_extract_dispatch
    assert dispatch(URL_A, 30, "live", retry.metadata, "full") is True
    retry.settings["live_stream_behavior"] = "extract_when_recorded"
    assert dispatch(URL_A, 30, "live", retry.metadata, "full") is True
    assert dispatch(URL_A, 30, "post_live", retry.metadata, "full") is False
    assert len(retry.responses) == 2


def test_live_queue_sqlite_failure_fails_visibly_without_downloading(retry, monkeypatch):
    retry.metadata["is_live"] = True
    monkeypatch.setattr(retry.idx, "enqueue_pending", Mock(
        side_effect=sqlite3.OperationalError("injected database full")))
    retry.handler._handle_extract({})
    response, = retry.responses
    assert response[0] == 503
    assert response[1]["ok"] is False
    assert "could not be queued" in response[1]["error"]
    retry.extract.assert_not_called()
    assert not retry.folder.exists()


@pytest.mark.parametrize("behavior", ["wait_for_end", "extract_when_recorded"])
@pytest.mark.parametrize("live_status", ["is_live", "is_upcoming", "post_live"])
def test_retry_rechecks_live_state_without_spending_attempts(retry, behavior, live_status):
    retry.settings["live_stream_behavior"] = behavior
    retry.metadata["live_status"] = live_status
    _enqueue(retry, attempts=2)
    if behavior == "extract_when_recorded" and live_status == "post_live":
        assert retry.run() is True
        assert _row(retry)["status"] == "succeeded"
        retry.extract.assert_called_once()
        return
    for _ in range(5):
        assert retry.run() is True
        row = _row(retry)
        assert row["status"] == "pending"
        assert row["attempt_count"] == 2
        assert row["last_error"] == "previous refusal"
        assert datetime.fromisoformat(row["retry_after"]) == retry.now + timedelta(minutes=10)
        assert retry.run() is False
        retry.now += timedelta(minutes=10)
    retry.extract.assert_not_called()
    retry.record.assert_not_called()
    assert not retry.folder.exists()
    retry.metadata["live_status"] = "was_live"
    assert retry.run() is True
    retry.extract.assert_called_once()
    event = retry.extract.call_args.kwargs["cancel_event"]
    assert isinstance(event, threading.Event) and not event.is_set()
    assert _row(retry)["status"] == "succeeded"
    assert _row(retry)["attempt_count"] == 2
    assert retry.idx._pending_cancel_events == {}


@pytest.mark.parametrize("live_status", ["is_upcoming", "is_live"])
@pytest.mark.parametrize("cancel", [False, True])
def test_live_wait_through_dispatch_retry_and_terminal_result(retry, live_status, cancel):
    retry.metadata["live_status"] = live_status
    retry.scope["_run_extraction"] = retry.real_extract
    retry.record.side_effect = retry.real_record
    _load(ROOT / "server.py", {"_fetch_metadata"}, retry.scope,
          constants={"COMMENTS_TIMEOUT_SEC"})
    run = retry.scope["_run_subprocess"]
    metadata_events = []

    def fetch_or_extract(cmd, **kwargs):
        if "--dump-single-json" in cmd:
            metadata_events.append(kwargs["cancel_event"])
            return subprocess.CompletedProcess(cmd, 0, json.dumps(retry.metadata), "")
        return run(cmd, **kwargs)

    retry.scope["_run_subprocess"] = fetch_or_extract
    retry.handler._handle_extract({})
    response, = retry.responses
    assert response[0] == 200
    assert response[1]["queued"] is True
    pending_id = response[1]["pending_id"]
    for status in (live_status, "is_live", "post_live"):
        assert retry.run() is False
        retry.now = datetime.fromisoformat(_row(retry)["retry_after"])
        retry.metadata["live_status"] = status
        assert retry.run() is True
        assert _row(retry)["status"] == "pending"
        assert _row(retry)["attempt_count"] == 0
        assert datetime.fromisoformat(_row(retry)["retry_after"]) == (
            retry.now + timedelta(minutes=10))
        assert retry.capture.calls == []
        assert not retry.folder.exists()
        assert retry.scope["_jobs"] == {}
        assert retry.idx.list_jobs() == []
    if cancel:
        _cancel(retry, pending_id)
        assert retry.idx.retry_pending_now(pending_id) is False
        assert retry.idx.reset_running_pending() == 0
    retry.metadata["live_status"] = "was_live"
    retry.now += timedelta(days=1)
    assert retry.run() is (not cancel)
    if cancel:
        _assert_cancelled(retry)
        assert retry.capture.calls == []
        assert not retry.folder.exists()
        assert retry.scope["_jobs"] == {}
        assert retry.idx.list_jobs() == []
    else:
        assert _row(retry)["status"] == "succeeded"
        assert _row(retry)["attempt_count"] == 0
        assert retry.idx.get_yoink("aaaaaaaaaaa") is not None
        job, = retry.scope["_jobs"].values()
        assert job["state"] == "completed"
        assert retry.idx.get_job(job["id"])["status"] == "completed"
        assert _row(retry)["succeeded_job_id"] == job["id"]
        result = retry.record.call_args.kwargs["result"]
        assert result["ok"] is True
        assert Path(result["folder"]) == retry.folder
        assert (retry.folder / f"{retry.folder.name}.md").is_file()
        assert (retry.folder / f"{retry.folder.name}.json").is_file()
        assert json.loads((retry.folder / "metadata.json").read_text()) == retry.metadata
    assert metadata_events[0] is None
    assert len(metadata_events) == (4 if cancel else 5)
    assert all(isinstance(event, threading.Event) and not event.is_set()
               for event in metadata_events[1:])
    assert retry.run() is False
    assert retry.idx._pending_cancel_events == {}


def test_failed_live_deferral_does_not_spend_attempt_or_extract(retry, monkeypatch, caplog):
    _enqueue(retry)
    retry.metadata["is_live"] = True
    monkeypatch.setattr(retry.idx, "defer_pending", Mock(
        side_effect=sqlite3.OperationalError("injected disk full")))
    assert retry.run() is True
    assert _row(retry)["attempt_count"] == 0
    assert "deferring live broadcast failed" in caplog.text
    retry.extract.assert_not_called()
    retry.record.assert_not_called()
    assert retry.idx._pending_cancel_events == {}


def test_cancel_after_metadata_429_backoff_survives_reopen(retry, monkeypatch):
    # Keep the production metadata signature and inject the refusal below it,
    # so a mock cannot hide a missing or rejected cancellation argument.
    _load(ROOT / "server.py", {
        "_fetch_metadata", "_is_youtube_rate_limit", "_youtube_429_endpoints",
        "_youtube_rate_limit_detail", "_subprocess_output",
    }, retry.scope, constants={"COMMENTS_TIMEOUT_SEC", "_RATE_LIMIT_INITIAL_BACKOFF_SEC"})
    events = []

    def refuse_metadata(cmd, *, cancel_event, **kwargs):
        assert "--dump-single-json" in cmd
        events.append(cancel_event)
        raise subprocess.CalledProcessError(
            1, cmd, stderr=b"ERROR: HTTP Error 429: Too Many Requests")

    retry.scope["_run_subprocess"] = Mock(side_effect=refuse_metadata)
    retry.handler._handle_extract({})
    response, = retry.responses
    assert response[0] == 200
    assert response[1]["queued"] is True
    assert response[1]["reason"] == "youtube_rate_limit"
    pending_id = response[1]["pending_id"]
    for attempt, minutes in ((1, 20), (2, 60)):
        assert retry.run() is False
        retry.now = datetime.fromisoformat(_row(retry)["retry_after"])
        assert retry.run() is True
        row = _row(retry)
        assert row["status"] == "pending"
        assert row["attempt_count"] == attempt
        assert datetime.fromisoformat(row["retry_after"]) == retry.now + timedelta(minutes=minutes)
        assert retry.idx._pending_cancel_events == {}
    assert events[0] is None
    assert len(events) == 3
    assert all(isinstance(event, threading.Event) and not event.is_set() for event in events[1:])

    _cancel(retry, pending_id)
    cancelled = _row(retry)
    assert cancelled["status"] == "cancelled"
    assert cancelled["attempt_count"] == 2
    assert cancelled["succeeded_job_id"] is None
    # Reopen queue storage without the unrelated library service importing server.
    monkeypatch.setattr(type(retry.idx), "library_service", Mock())
    with type(retry.idx).open(retry.idx._path) as reopened:
        monkeypatch.setitem(retry.scope, "_get_index", lambda: reopened)
        assert reopened.reset_running_pending() == 0
        assert reopened.retry_pending_now(pending_id) is False
        retry.now += timedelta(days=1)
        assert retry.run() is False
        assert reopened.list_pending(include_terminal=True) == [cancelled]
        assert reopened.list_pending(include_terminal=False) == []
        assert reopened.list_jobs() == []
    assert retry.scope["_jobs"] == {}
    retry.record.assert_not_called()
    retry.extract.assert_not_called()
    assert retry.scope["_run_subprocess"].call_count == 3
    assert not retry.folder.exists()


def test_cancel_between_selection_and_claim_cannot_start_worker(retry, monkeypatch):
    pending_id = _enqueue(retry)
    stale = _row(retry)
    _cancel(retry, pending_id)
    with monkeypatch.context() as patch:
        patch.setattr(retry.idx, "next_pending", lambda now: stale)
        assert retry.run() is False
    retry.scope["_manual_extraction_ownership"].assert_not_called()
    retry.scope["_fetch_metadata"].assert_not_called()
    _assert_cancelled(retry)


@pytest.mark.parametrize("ownership", ["available", "unavailable", "reused", "conflict"])
def test_cancel_while_waiting_for_ownership_stops_after_wait(retry, ownership):
    pending_id = _enqueue(retry)
    waiting, release = threading.Event(), threading.Event()
    if ownership == "unavailable":
        retry.ownership.ok = False
    elif ownership == "reused":
        retry.ownership.completed_while_waiting = True
        retry.ownership.reused = {"ok": True}
    elif ownership == "conflict":
        retry.ownership.conflict = "capture belongs to another source"

    @contextmanager
    def hold(url):
        waiting.set()
        assert release.wait(5), "test did not release the ownership wait"
        yield retry.ownership

    retry.scope["_manual_extraction_ownership"] = hold
    outcomes = []
    errors = []

    def work():
        try:
            outcomes.append(retry.run())
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=work)
    thread.start()
    try:
        assert waiting.wait(5)
        event = retry.idx._pending_cancel_events[pending_id]
        _cancel(retry, pending_id)
        assert event.is_set()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert errors == []
    assert outcomes == [True]
    retry.scope["_fetch_metadata"].assert_not_called()
    retry.extract.assert_not_called()
    _assert_cancelled(retry)


def test_cancel_during_metadata_stops_before_capture_folder(retry):
    pending_id = _enqueue(retry)

    def fetch(url, *, cancel_event=None):
        _cancel(retry, pending_id)
        return retry.metadata

    retry.scope["_fetch_metadata"] = fetch
    assert retry.run() is True
    retry.extract.assert_not_called()
    assert not retry.folder.exists()
    _assert_cancelled(retry)


def test_cancel_during_metadata_terminates_child_and_never_restarts(retry, monkeypatch):
    pending_id = _enqueue(retry)
    _load(ROOT / "server.py", {"_fetch_metadata", "_run_subprocess", "_terminate_process"},
          retry.scope, constants={"COMMENTS_TIMEOUT_SEC"})
    retry.scope.update({
        "SUBPROCESS_KW": {},
        "source_subscriptions": SimpleNamespace(current_capture_context=lambda: None),
    })
    proc = Mock(returncode=0)

    def communicate(*, timeout):
        if proc.communicate.call_count == 1:
            _cancel(retry, pending_id)
            raise subprocess.TimeoutExpired("mock metadata", timeout)
        return json.dumps(retry.metadata), ""

    proc.communicate.side_effect = communicate
    spawn = Mock(return_value=proc)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    assert retry.run() is True
    spawn.assert_called_once()
    assert "--dump-single-json" in spawn.call_args.args[0]
    proc.terminate.assert_called_once_with()
    proc.wait.assert_called_once_with(timeout=3)
    proc.communicate.assert_called_once_with(timeout=0.2)
    retry.extract.assert_not_called()
    assert not retry.folder.exists()
    assert retry.idx.reset_running_pending() == 0
    retry.now += timedelta(days=1)
    assert retry.run() is False
    _assert_cancelled(retry)
    assert retry.scope["_jobs"] == {}
    assert retry.idx.list_jobs() == []


@pytest.mark.parametrize("outcome", ["success", "rate_limit", "failure", "publication_failure"])
def test_cancel_during_extraction_cannot_be_overwritten(retry, outcome):
    pending_id = _enqueue(retry)

    def extract(*args, cancel_event, **kwargs):
        _cancel(retry, pending_id)
        assert cancel_event.is_set()
        if outcome == "success":
            return {"ok": True}
        if outcome == "rate_limit":
            raise subprocess.CalledProcessError(1, "mock yt-dlp", stderr=b"HTTP 429")
        error = OSError("injected write failure")
        if outcome == "publication_failure":
            error.capture_result = {"ok": False}
        raise error

    retry.scope["_run_extraction"] = extract
    assert retry.run() is True
    _assert_cancelled(retry)


@pytest.mark.parametrize("outcome", ["success", "rate_limit", "final_rate_limit", "failure"])
def test_cancel_racing_with_settlement_keeps_cancelled_row(retry, monkeypatch, outcome):
    pending_id = _enqueue(retry, attempts=2 if outcome == "final_rate_limit" else 0)
    if outcome != "success":
        retry.extract.side_effect = (OSError("injected failure") if outcome == "failure"
                                    else subprocess.CalledProcessError(1, "mock", stderr=b"429"))
    name = "mark_pending_succeeded" if outcome == "success" else "mark_pending_failed"
    settle = getattr(retry.idx, name)

    def cancel_then_settle(*args, **kwargs):
        assert kwargs["expected_status"] == "running"
        _cancel(retry, pending_id)
        return settle(*args, **kwargs)

    monkeypatch.setattr(retry.idx, name, cancel_then_settle)
    assert retry.run() is True
    row = _row(retry)
    assert row["status"] == "cancelled"
    assert row["attempt_count"] == (2 if outcome == "final_rate_limit" else 0)
    assert row["succeeded_job_id"] is None
    retry.record.assert_not_called()
    assert retry.idx._pending_cancel_events == {}


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("outcome", ["success", "failure", "final_rate_limit", "conflict"])
@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_terminal_settlement_errors_preserve_activity_unless_cancelled(
        retry, monkeypatch, caplog, outcome, cancel, platform):
    monkeypatch.setattr(retry.scope["_platform"], "sys", SimpleNamespace(platform=platform))
    attempts_before = 2 if outcome == "final_rate_limit" else 0
    pending_id = _enqueue(retry, attempts=attempts_before)
    retry.record.side_effect = retry.real_record
    if outcome == "success":
        # The capture really publishes before the queue settlement fails.
        retry.scope["_run_extraction"] = retry.real_extract
    elif outcome == "conflict":
        retry.ownership.conflict = "capture belongs to another source"
    else:
        retry.extract.side_effect = (
            OSError("injected extraction failure") if outcome == "failure"
            else subprocess.CalledProcessError(1, "mock yt-dlp", stderr=b"HTTP 429"))
    name = "mark_pending_succeeded" if outcome == "success" else "mark_pending_failed"

    def fail_settlement(*args, **kwargs):
        assert kwargs["expected_status"] == ("publishing" if outcome == "success" else "running")
        if cancel:
            if outcome == "success":
                _cancel_too_late(retry, pending_id)
            else:
                _cancel(retry, pending_id)
        raise sqlite3.OperationalError("injected settlement database locked")

    settle = Mock(side_effect=fail_settlement)
    monkeypatch.setattr(retry.idx, name, settle)
    assert retry.run() is True
    settle.assert_called_once()
    assert "injected settlement database locked" in caplog.text
    row = _row(retry)
    assert row["status"] == ("publishing" if outcome == "success"
                             else "cancelled" if cancel else "running")
    assert row["attempt_count"] == attempts_before
    assert row["succeeded_job_id"] is None
    assert retry.idx._pending_cancel_events == {}
    if outcome == "success":
        assert retry.idx.get_yoink("aaaaaaaaaaa") is not None
        assert (retry.folder / f"{retry.folder.name}.md").is_file()
        assert (retry.folder / f"{retry.folder.name}.json").is_file()
    if cancel and outcome != "success":
        retry.record.assert_not_called()
        assert retry.scope["_jobs"] == {}
        return
    retry.record.assert_called_once()
    job, = retry.scope["_jobs"].values()
    assert job["state"] == ("completed" if outcome == "success" else "failed")
    assert retry.idx.get_job(job["id"])["status"] == job["state"]
    retry.scope["_pending_long_video_mode"].assert_any_call(pending_id, remove=True)
    if outcome == "final_rate_limit":
        assert job["retry_exhausted"] is True
        assert job["attempt_count"] == 3
    elif outcome == "conflict":
        assert job["error"] == retry.ownership.conflict
        retry.extract.assert_not_called()
    elif outcome == "failure":
        assert job["error"] == "injected extraction failure"


def test_retry_reports_missing_bundle_media_before_metadata(retry, monkeypatch, tmp_path):
    platform = retry.scope["_platform"]
    monkeypatch.setattr(platform, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(platform, "__file__", str(tmp_path / "App/Contents/Resources/_platform.py"))
    # Exercise the real translation too; the retry fixture normally uses str.
    _load(ROOT / "server.py", {"friendly_error"}, retry.scope)
    retry.record.side_effect = retry.real_record
    _enqueue(retry)
    assert retry.run() is True
    retry.scope["_fetch_metadata"].assert_not_called()
    retry.extract.assert_not_called()
    assert _row(retry)["status"] == "failed"
    assert _row(retry)["last_error"].startswith("media_requires_ffmpeg:")
    assert retry.idx._pending_cancel_events == {}
    job, = retry.scope["_jobs"].values()
    assert job["state"] == "failed"
    assert job["error"].startswith("media_requires_ffmpeg:")
    assert not retry.folder.exists()


@pytest.mark.parametrize("phase", ["media", "screenshots", "before_publication", "publish_rename"])
def test_cancelled_retry_refresh_preserves_capture(retry, monkeypatch, phase):
    retry.real_extract(URL_A, 30, retry.folder, metadata=retry.metadata, topic="Test")
    (retry.folder / "notes.txt").write_text("user notes", encoding="utf-8")
    recovery = retry.folder / ".s-recovery" / "p"
    recovery.mkdir(parents=True)
    (recovery / "video.mp4").write_bytes(b"previous recovery input")
    media_inputs = retry.folder / ".media-inputs"
    media_inputs.mkdir()
    (media_inputs / "retained.json").write_bytes(b"previous media input")
    before = _snapshot(retry.folder)
    row_before = retry.idx.get_yoink("aaaaaaaaaaa")
    pending_id = _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    if phase in {"media", "screenshots"}:
        run = retry.scope["_run_subprocess"]
        _load(ROOT / "server.py", {"_run_subprocess", "_terminate_process"}, retry.scope)
        retry.scope.update({
            "SUBPROCESS_KW": {},
            "source_subscriptions": SimpleNamespace(current_capture_context=lambda: None),
        })
        children = []

        def spawn(cmd, **kwargs):
            proc = Mock(returncode=0)
            children.append(proc)

            def communicate(*, timeout):
                if (cmd[0] == "ffmpeg") == (phase == "screenshots"):
                    _cancel(retry, pending_id)
                    raise subprocess.TimeoutExpired(cmd, timeout)
                result = run(cmd, **kwargs)
                return result.stdout, result.stderr

            proc.communicate.side_effect = communicate
            return proc

        monkeypatch.setattr(subprocess, "Popen", Mock(side_effect=spawn))
    elif phase == "before_publication":
        write = retry.scope["_atomic_write_text"]

        def cancel_sidecar(path, text):
            write(path, text)
            if path.name == "c.json":
                _cancel(retry, pending_id)

        retry.scope["_atomic_write_text"] = cancel_sidecar
    else:
        rename = Path.rename

        def cancel_rename(path, target):
            result = rename(path, target)
            if Path(target).parent.name == "p" and _row(retry)["status"] == "running":
                _cancel(retry, pending_id)
            return result

        monkeypatch.setattr(Path, "rename", cancel_rename)
    assert retry.run() is True
    assert _snapshot(retry.folder) == before
    assert retry.idx.get_yoink("aaaaaaaaaaa") == row_before
    assert retry.queue.next_pending() is None
    _assert_cancelled(retry)
    if phase in {"media", "screenshots"}:
        assert len(children) == (1 if phase == "media" else 2)
        children[-1].communicate.assert_called_once_with(timeout=0.2)
        children[-1].terminate.assert_called_once_with()
        children[-1].wait.assert_called_once_with(timeout=3)
        for child in children[:-1]:
            child.terminate.assert_not_called()
    assert retry.scope["_jobs"] == {}
    assert retry.idx.list_jobs() == []
    assert retry.idx.retry_pending_now(pending_id) is False
    assert retry.idx.reset_running_pending() == 0
    retry.now += timedelta(days=1)
    assert retry.run() is False
    assert _snapshot(retry.folder) == before


def test_first_capture_checks_cancellation_before_writing_corpus(retry):
    pending_id = _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    build = retry.scope["_build_yoink_md"]

    def cancel_before_corpus(**kwargs):
        text = build(**kwargs)
        _cancel(retry, pending_id)
        return text

    retry.scope["_build_yoink_md"] = cancel_before_corpus
    assert retry.run() is True
    assert not (retry.folder / f"{retry.folder.name}.md").exists()
    assert not (retry.folder / f"{retry.folder.name}.json").exists()
    assert retry.idx.get_yoink("aaaaaaaaaaa") is None
    _assert_cancelled(retry)


def test_stale_transitions_and_retry_now_cannot_revive_cancelled_row(retry):
    pending_id = _enqueue(retry)
    event = threading.Event()
    assert retry.idx.mark_pending_running(pending_id, cancel_event=event)
    assert retry.idx.retry_pending_now(pending_id) is False
    assert retry.idx.mark_pending_running(pending_id, cancel_event=threading.Event()) is False
    _cancel(retry, pending_id)
    before = _row(retry)
    assert event.is_set()
    assert retry.idx.mark_pending_running(pending_id) is False
    assert retry.idx.defer_pending(pending_id, "2099-01-01T00:00:00") is False
    assert retry.idx.fail_pending_publication(pending_id, "stale save failure") is False
    for expected in (None, "running", "publishing", "failed", "succeeded", "cancelled"):
        assert retry.idx.mark_pending_publishing(pending_id, expected_status=expected) is False
        assert retry.idx.mark_pending_succeeded(pending_id, "stale-job", expected_status=expected) is False
        assert retry.idx.mark_pending_failed(
            pending_id, "stale error", "2099-01-01T00:00:00", expected_status=expected) == ""
    assert retry.idx.retry_pending_now(pending_id) is False
    assert _row(retry) == before
    retry.idx.release_pending_cancel_event(pending_id, event)
    assert retry.idx._pending_cancel_events == {}


def test_ownership_exception_releases_event(retry):
    _enqueue(retry)
    retry.scope["_manual_extraction_ownership"] = Mock(side_effect=OSError("injected lock failure"))
    with pytest.raises(OSError, match="injected lock failure"):
        retry.run()
    assert retry.idx._pending_cancel_events == {}


def test_cancel_sqlite_failure_is_visible_and_does_not_signal_event(retry, monkeypatch):
    pending_id = _enqueue(retry)
    event = threading.Event()
    assert retry.idx.mark_pending_running(pending_id, cancel_event=event)
    monkeypatch.setattr(retry.idx, "cancel_pending", Mock(
        side_effect=sqlite3.OperationalError("injected database locked")))
    retry.handler._handle_queue_cancel({"pending_id": pending_id})
    assert retry.responses == [(500, {"ok": False, "error": "queue unavailable"})]
    assert not event.is_set()
    assert _row(retry)["status"] == "running"
    retry.idx.release_pending_cancel_event(pending_id, event)


@pytest.mark.parametrize("operation", ["claim", "cancel", "publish", "success", "failure", "defer", "reset"])
def test_failed_queue_commit_rolls_back_before_signalling(retry, monkeypatch, operation):
    pending_id = _enqueue(retry)
    event = threading.Event()
    if operation != "claim":
        assert retry.idx.mark_pending_running(pending_id, cancel_event=event)
    if operation == "reset":
        assert retry.idx.mark_pending_publishing(pending_id)
    before = _row(retry)
    connection = retry.idx._conn
    failing = SimpleNamespace(
        execute=connection.execute, rollback=Mock(wraps=connection.rollback),
        commit=Mock(side_effect=sqlite3.OperationalError("injected commit failure")))
    with monkeypatch.context() as patch:
        patch.setattr(retry.idx, "_conn", failing)
        if operation == "claim":
            assert retry.run() is False
        elif operation == "publish":
            with pytest.raises(sqlite3.OperationalError, match="injected commit failure"):
                retry.idx.mark_pending_publishing(pending_id)
        elif operation == "reset":
            with pytest.raises(sqlite3.OperationalError, match="injected commit failure"):
                retry.idx.reset_running_pending()
        elif operation in ("success", "failure", "defer"):
            with pytest.raises(sqlite3.OperationalError, match="injected commit failure"):
                if operation == "success":
                    retry.idx.mark_pending_succeeded(pending_id, "job", expected_status="running")
                elif operation == "failure":
                    retry.idx.mark_pending_failed(
                        pending_id, "error", "2099-01-01", expected_status="running")
                else:
                    retry.idx.defer_pending(pending_id, "2099-01-01")
        else:
            retry.handler._handle_queue_cancel({"pending_id": pending_id})
            assert retry.responses == [(500, {"ok": False, "error": "queue unavailable"})]
    failing.rollback.assert_called_once()
    assert not event.is_set()
    assert _row(retry) == before
    if operation != "claim":
        retry.idx.release_pending_cancel_event(pending_id, event)
    assert retry.idx._pending_cancel_events == {}


def test_running_settlement_does_not_claim_a_pending_row(retry):
    pending_id = _enqueue(retry)
    before = _row(retry)
    assert retry.idx.mark_pending_succeeded(
        pending_id, "stale-job", expected_status="running") is False
    assert retry.idx.mark_pending_failed(
        pending_id, "stale failure", "2099-01-01T00:00:00", expected_status="running") == ""
    assert _row(retry) == before


def test_publication_handoff_survives_queue_write_failure(retry, monkeypatch):
    pending_id = _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    with monkeypatch.context() as patch:
        patch.setattr(retry.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected index full")))
        patch.setattr(retry.idx, "mark_pending_failed", Mock(
            side_effect=sqlite3.OperationalError("injected queue full")))
        assert retry.run() is True
    assert _row(retry)["status"] == "publishing"
    retry.record.assert_called_once()
    assert retry.record.call_args.kwargs["result"]["ok"] is False
    assert retry.idx._pending_cancel_events == {}
    _, receipt = retry.queue.next_pending()
    assert receipt["pending_id"] == pending_id
    assert retry.scope["_retry_publication_one"]() is True
    assert _row(retry)["status"] == "succeeded"
    assert retry.queue.next_pending() is None


@pytest.mark.parametrize("refreshing", [False, True])
@pytest.mark.parametrize("phase", ["reliability", "markdown_index", "library_index", "settlement"])
def test_cancel_after_commit_is_refused_and_capture_has_activity(
        retry, monkeypatch, refreshing, phase):
    if refreshing:
        retry.real_extract(URL_A, 30, retry.folder, metadata=retry.metadata, topic="Test")
    pending_id = _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    retry.record.side_effect = retry.real_record
    if phase == "reliability":
        retry.settings["transcript_reliability_auto_check"] = True
        retry.scope["RELIABILITY_DEFAULT_THRESHOLD"] = 0.5
        retry.scope["_read_sidecar_for_folder"] = lambda folder: (
            folder / f"{folder.name}.json",
            json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8")))
        callback = Mock(side_effect=lambda *a, **k: (
            _cancel_too_late(retry, pending_id) or {"ok": True}))
        retry.scope["_compute_transcript_reliability"] = callback
    elif phase == "settlement":
        settle = retry.idx.mark_pending_succeeded

        def cancel_at_settlement(*args, **kwargs):
            _cancel_too_late(retry, pending_id)
            return settle(*args, **kwargs)

        callback = Mock(side_effect=cancel_at_settlement)
        monkeypatch.setattr(retry.idx, "mark_pending_succeeded", callback)
    else:
        name = "_incremental_index_update" if phase == "markdown_index" else "_index_yoink"
        original = retry.scope[name]

        def cancel_at_index(*args, **kwargs):
            _cancel_too_late(retry, pending_id)
            return original(*args, **kwargs)

        callback = Mock(side_effect=cancel_at_index)
        retry.scope[name] = callback
    assert retry.run() is True
    callback.assert_called_once()
    assert retry.responses[-1][0] == 409
    assert _row(retry)["status"] == "succeeded"
    assert _row(retry)["attempt_count"] == 0
    assert retry.idx.get_yoink("aaaaaaaaaaa") is not None
    job, = retry.scope["_jobs"].values()
    assert job["state"] == "completed"
    assert retry.idx.get_job(job["id"])["status"] == "completed"
    assert _row(retry)["succeeded_job_id"] == job["id"]
    assert retry.idx._pending_cancel_events == {}


@pytest.mark.parametrize("failure", ["sidecar", "index", "refresh_index"])
def test_cancel_during_real_publication_handoff_is_refused(retry, monkeypatch, failure):
    if failure == "refresh_index":
        retry.real_extract(URL_A, 30, retry.folder, metadata=retry.metadata, topic="Test")
    pending_id = _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    retry.record.side_effect = retry.real_record
    schedule = retry.scope["_schedule_publication_retry"]

    def schedule_then_cancel(*args, **kwargs):
        receipt_id = schedule(*args, **kwargs)
        assert retry.queue.next_pending()[0] == receipt_id
        _cancel_too_late(retry, pending_id)
        return receipt_id

    retry.scope["_schedule_publication_retry"] = Mock(side_effect=schedule_then_cancel)
    with monkeypatch.context() as patch:
        if failure == "sidecar":
            write = retry.scope["_atomic_write_text"]

            def fail_sidecar(path, text):
                if path.name == f"{retry.folder.name}.json":
                    raise PermissionError("injected sidecar lock")
                return write(path, text)

            patch.setitem(retry.scope, "_atomic_write_text", fail_sidecar)
        else:
            patch.setattr(retry.idx, "upsert_yoink", Mock(
                side_effect=sqlite3.OperationalError("injected index full")))
        assert retry.run() is True
    retry.scope["_schedule_publication_retry"].assert_called_once()
    assert retry.responses[-1][0] == 409
    assert _row(retry)["status"] == "failed"
    assert _row(retry)["attempt_count"] == 1
    job, = retry.scope["_jobs"].values()
    assert job["state"] == "failed"
    receipt_id, record = retry.queue.next_pending()
    assert record["pending_id"] == pending_id
    calls_before = list(retry.capture.calls)
    index_capture = retry.scope["_index_yoink"]

    def cancel_during_receipt(*args, **kwargs):
        _cancel_too_late(retry, pending_id)
        return index_capture(*args, **kwargs)

    retry.scope["_index_yoink"] = cancel_during_receipt
    assert retry.scope["_retry_publication_one"]() is True
    assert retry.queue.is_settled(receipt_id)
    assert retry.queue.next_pending() is None
    assert _row(retry)["status"] == "succeeded"
    assert _row(retry)["attempt_count"] == 1
    assert retry.idx.get_yoink("aaaaaaaaaaa") is not None
    job, = retry.scope["_jobs"].values()
    assert job["state"] == "completed"
    assert retry.idx.get_job(job["id"])["status"] == "completed"
    assert _row(retry)["succeeded_job_id"] == job["id"]
    assert retry.capture.calls == calls_before
    assert retry.idx._pending_cancel_events == {}


def test_real_receipt_cannot_publish_after_requeue_and_cancel(retry, monkeypatch):
    pending_id = _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    retry.record.side_effect = retry.real_record
    with monkeypatch.context() as patch:
        patch.setattr(retry.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected index full")))
        assert retry.run() is True
    receipt_id, record = retry.queue.next_pending()
    assert record["pending_id"] == pending_id
    before = _snapshot(retry.folder)
    assert retry.idx.retry_pending_now(pending_id)
    _cancel(retry, pending_id)
    retry.scope["_index_yoink"] = Mock()
    assert retry.scope["_retry_publication_one"]() is True
    retry.scope["_index_yoink"].assert_not_called()
    assert retry.queue.is_settled(receipt_id)
    assert _row(retry)["status"] == "cancelled"
    assert retry.idx.get_yoink("aaaaaaaaaaa") is None
    assert _snapshot(retry.folder) == before
    job, = retry.scope["_jobs"].values()
    assert job["state"] == "failed"
    assert "cancelled" in job["error"]


def test_cancel_at_publication_claim_preserves_refresh_and_queues_no_receipt(retry, monkeypatch):
    retry.real_extract(URL_A, 30, retry.folder, metadata=retry.metadata, topic="Test")
    before = _snapshot(retry.folder)
    row_before = retry.idx.get_yoink("aaaaaaaaaaa")
    pending_id = _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    claim = retry.idx.mark_pending_publishing

    def cancel_before_claim(*args, **kwargs):
        _cancel(retry, pending_id)
        return claim(*args, **kwargs)

    monkeypatch.setattr(retry.idx, "mark_pending_publishing", cancel_before_claim)
    assert retry.run() is True
    assert _snapshot(retry.folder) == before
    assert retry.idx.get_yoink("aaaaaaaaaaa") == row_before
    assert retry.queue.next_pending() is None
    _assert_cancelled(retry)


def test_restart_does_not_redownload_a_publishing_capture(retry):
    pending_id = _enqueue(retry)
    assert retry.idx.mark_pending_running(pending_id)
    assert retry.idx.mark_pending_publishing(pending_id)
    assert retry.idx.retry_pending_now(pending_id) is False
    assert retry.idx.reset_running_pending() == 0
    assert _row(retry)["status"] == "failed"
    assert "publication was interrupted" in _row(retry)["last_error"]
    assert retry.run() is False
    retry.extract.assert_not_called()


def test_cancel_before_failed_sidecar_handoff_queues_no_receipt(retry):
    pending_id = _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    write = retry.scope["_atomic_write_text"]

    def cancel_then_fail_sidecar(path, text):
        if path.name == f"{retry.folder.name}.json":
            _cancel(retry, pending_id)
            raise PermissionError("injected sidecar lock")
        return write(path, text)

    retry.scope["_atomic_write_text"] = cancel_then_fail_sidecar
    assert retry.run() is True
    assert retry.queue.next_pending() is None
    assert retry.idx.get_yoink("aaaaaaaaaaa") is None
    assert (retry.folder / f"{retry.folder.name}.md").is_file()
    assert (retry.folder / "video.mp4").is_file()
    _assert_cancelled(retry)


def test_publication_claim_error_restores_refresh(retry, monkeypatch):
    retry.real_extract(URL_A, 30, retry.folder, metadata=retry.metadata, topic="Test")
    before = _snapshot(retry.folder)
    row_before = retry.idx.get_yoink("aaaaaaaaaaa")
    _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    monkeypatch.setattr(retry.idx, "mark_pending_publishing", Mock(
        side_effect=sqlite3.OperationalError("injected publication claim failure")))
    assert retry.run() is True
    assert _snapshot(retry.folder) == before
    assert retry.idx.get_yoink("aaaaaaaaaaa") == row_before
    assert retry.queue.next_pending() is None
    assert _row(retry)["status"] == "failed"
    retry.record.assert_called_once()
    assert "publication claim failure" in retry.record.call_args.kwargs["error"]


def test_failure_after_publication_still_records_activity(retry):
    _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    retry.record.side_effect = retry.real_record
    retry.scope["_start_entity_extraction_thread"] = Mock(
        side_effect=OSError("injected extraction tail failure"))
    assert retry.run() is True
    assert retry.idx.get_yoink("aaaaaaaaaaa") is not None
    assert _row(retry)["status"] == "failed"
    job, = retry.scope["_jobs"].values()
    assert job["state"] == "failed"
    assert "extraction tail failure" in job["error"]
    assert retry.idx.get_job(job["id"])["status"] == "failed"


def test_receipt_settlement_refusal_is_not_reported_as_success(retry, monkeypatch):
    _enqueue(retry)
    retry.scope["_run_extraction"] = retry.real_extract
    retry.record.side_effect = retry.real_record
    with monkeypatch.context() as patch:
        patch.setattr(retry.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected index full")))
        assert retry.run() is True
    receipt_id, _ = retry.queue.next_pending()
    monkeypatch.setattr(retry.idx, "mark_pending_succeeded", Mock(return_value=False))
    assert retry.scope["_retry_publication_one"]() is True
    assert _row(retry)["status"] == "failed"
    job, = retry.scope["_jobs"].values()
    assert job["state"] == "failed"
    assert "queue row changed" in job["error"]
    outcome = json.loads((retry.queue.root / f"{receipt_id}.result.json").read_text())
    assert outcome["status"] == "failed"


def test_old_receipt_cannot_reopen_a_completed_queue_row(retry, monkeypatch):
    pending_id = _enqueue(retry)
    _load(ROOT / "server.py", {"_make_job_id"}, retry.scope)
    retry.scope["_run_extraction"] = retry.real_extract
    retry.record.side_effect = retry.real_record
    with monkeypatch.context() as patch:
        patch.setattr(retry.idx, "upsert_yoink", Mock(
            side_effect=sqlite3.OperationalError("injected index full")))
        assert retry.run() is True
    receipt_id, _ = retry.queue.next_pending()
    assert retry.idx.retry_pending_now(pending_id)
    retry.now = datetime.fromisoformat(_row(retry)["retry_after"])
    assert retry.run() is True
    row_before = _row(retry)
    assert row_before["status"] == "succeeded"
    files_before = _snapshot(retry.folder)
    jobs_before = dict(retry.scope["_jobs"])
    retry.scope["_index_yoink"] = Mock()
    assert retry.scope["_retry_publication_one"]() is True
    assert retry.queue.is_settled(receipt_id)
    retry.scope["_index_yoink"].assert_not_called()
    assert _row(retry) == row_before
    assert _snapshot(retry.folder) == files_before
    assert retry.scope["_jobs"] == jobs_before
