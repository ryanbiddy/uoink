"""Offline regressions for media-429 retries and stored diagnostics."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index  # noqa: E402
import server  # noqa: E402


URL = "https://www.youtube.com/watch?v=abcdef12345"
ERROR_LINE = (
    "ERROR: unable to download video data: HTTP Error 429 from "
    "https://fixture-user:fixture-secret@media.example/video "
    r"while saving C:\private\clip.mp4 /private/cache"
)


@pytest.fixture
def retry_queue(monkeypatch, tmp_path, caplog):
    idx = index.Index.open(tmp_path / "index.db")
    state = SimpleNamespace(
        index=idx, now=datetime(2026, 10, 15, 12, 0, 0),
        ownership=SimpleNamespace(
            ok=True, conflict=None, completed_while_waiting=False, reused=None,
            error="capture_ownership_unavailable",
        ),
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return state.now

    class Handler:
        _validate_url_interval = server.Handler._validate_url_interval
        _handle_extract = server.Handler._handle_extract

        def _send_json(self, status, payload):
            self.response = (status, payload)

    state.handler = Handler()
    state.extract = Mock(side_effect=subprocess.CalledProcessError(
        1, ["yt-dlp"],
        stderr=b"ERROR: unable to download video data: HTTP Error 429",
    ))
    state.record_job = Mock()
    state.real_record_job = server._record_single_extract_job
    monkeypatch.setattr(server, "datetime", Clock)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "captures")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_pending_long_video_modes", {})
    monkeypatch.setattr(server, "_jobs", {})
    monkeypatch.setattr(server, "_manual_extraction_ownership",
                        lambda _url: nullcontext(state.ownership))
    monkeypatch.setattr(server, "_fetch_metadata", Mock(return_value={
        "id": "abcdef12345", "title": "Retry test", "duration": 60,
    }))
    monkeypatch.setattr(server, "_classify_topic", Mock(return_value="Test"))
    monkeypatch.setattr(server, "_run_extraction", state.extract)
    monkeypatch.setattr(server, "_record_single_extract_job", state.record_job)
    caplog.set_level(logging.INFO, logger=server.log.name)

    unexpected_io = Mock(side_effect=AssertionError("unmocked external I/O"))
    monkeypatch.setattr(server, "_run_subprocess", unexpected_io)
    monkeypatch.setattr(subprocess, "run", unexpected_io)
    monkeypatch.setattr(subprocess, "Popen", unexpected_io)
    monkeypatch.setattr(subprocess, "check_output", unexpected_io)
    monkeypatch.setattr(server.urllib.request, "urlopen", unexpected_io)
    monkeypatch.setattr(server.socket.socket, "connect", unexpected_io)
    try:
        yield state
    finally:
        idx.close()
    unexpected_io.assert_not_called()


def _enqueue(state):
    state.handler._handle_extract({"url": URL, "interval": 30})
    status, result = state.handler.response
    assert status == 200
    assert result["ok"] is True
    assert result["queued"] is True
    assert result["reason"] == "youtube_rate_limit"
    row = _row(state)
    assert result["pending_id"] == row["pending_id"]
    assert result["retry_after"] == row["retry_after"]
    return row


def _row(state):
    rows = state.index.list_pending(include_terminal=True)
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("failed_retries, delay_minutes", [(0, 5), (1, 20), (2, 60)])
def test_media_429_retry_schedule(retry_queue, caplog, failed_retries, delay_minutes):
    state = retry_queue
    row = _enqueue(state)
    for _ in range(failed_retries):
        state.now = datetime.fromisoformat(row["retry_after"])
        caplog.clear()
        assert server._retry_pending_one() is True
        row = _row(state)

    expected = state.now + timedelta(minutes=delay_minutes)
    assert row["status"] == "pending"
    assert row["attempt_count"] == failed_retries
    assert datetime.fromisoformat(row["retry_after"]) == expected
    assert f"retry at {expected.isoformat()}" in caplog.text
    assert f"in {delay_minutes} minutes, retry {failed_retries + 1} of 3" in caplog.text
    state.record_job.assert_not_called()

    state.now = expected - timedelta(seconds=1)
    assert server._retry_pending_one() is False
    assert state.extract.call_count == failed_retries + 1


def test_media_429_stops_after_three_failed_retries(retry_queue, caplog):
    state = retry_queue
    assert index._PENDING_MAX_ATTEMPTS == 3
    row = _enqueue(state)
    for attempt, delay_minutes in enumerate((5, 20, 60), start=1):
        state.now += timedelta(minutes=delay_minutes)
        assert row["retry_after"] == state.now.isoformat()
        caplog.clear()
        assert server._retry_pending_one() is True
        row = _row(state)
        assert row["attempt_count"] == attempt
        if attempt < 3:
            assert row["status"] == "pending"
            state.record_job.assert_not_called()

    assert row["status"] == "failed"
    assert "stopped after 3 attempts" in row["last_error"]
    assert "retry at" not in caplog.text
    assert "gave up after 3 attempts" in caplog.text
    assert state.index.list_pending() == []
    assert row["pending_id"] not in server._pending_long_video_modes
    state.record_job.assert_called_once()
    job = state.record_job.call_args.kwargs
    assert job["retry_exhausted"] is True
    assert job["attempt_count"] == 3
    assert "won't retry it on its own" in job["error"]
    state.now += timedelta(days=1)
    assert server._retry_pending_one() is False
    assert state.extract.call_count == 4  # Initial capture plus three retries.


def test_capture_lock_failure_keeps_existing_backoff(retry_queue):
    state = retry_queue
    state.index.enqueue_pending(URL, 30, state.now.isoformat())
    state.ownership.ok = False
    assert server._retry_pending_one() is True
    row = _row(state)
    assert row["status"] == "pending"
    assert row["attempt_count"] == 1
    assert row["last_error"] == "capture_ownership_unavailable"
    assert datetime.fromisoformat(row["retry_after"]) == state.now + timedelta(minutes=2)
    state.extract.assert_not_called()


@pytest.mark.parametrize("stream", ["stderr", "stdout"])
@pytest.mark.parametrize("as_bytes", [False, True], ids=["text", "bytes"])
def test_media_429_persists_sanitized_last_error(retry_queue, stream, as_bytes):
    state = retry_queue
    state.record_job.side_effect = state.real_record_job
    row = None
    for attempt in range(4):
        last_error = f"{ERROR_LINE} refusal {attempt}"
        output = ("[debug] request started\nERROR: earlier refusal\n"
                  f"{last_error}\nWARNING: trailing diagnostic")
        stderr = output if stream == "stderr" else "WARNING: HTTP Error 429"
        stdout = output if stream == "stdout" else "[download] finished"
        state.extract.side_effect = subprocess.CalledProcessError(
            1, [r"C:\private\yt-dlp.exe", "--password", "command-secret"],
            stderr=stderr.encode("utf-8") if as_bytes else stderr,
            output=stdout.encode("utf-8") if as_bytes else stdout,
        )
        if row is None:
            row = _enqueue(state)
        else:
            state.now = datetime.fromisoformat(row["retry_after"])
            assert server._retry_pending_one() is True
            row = _row(state)

        sanitized = server._sanitize_error(last_error)
        assert "<url>" in sanitized
        assert sanitized.count("<path>") == 2
        assert row["last_error"].startswith("youtube_rate_limit: ")
        assert sanitized in row["last_error"]
        assert row["attempt_count"] == attempt
        for unwanted in ("fixture-user", "fixture-secret", "private",
                         "command-secret", "earlier refusal", "trailing diagnostic"):
            assert unwanted not in row["last_error"]
        if attempt < 3:
            assert row["status"] == "pending"
            state.record_job.assert_not_called()

    assert row["status"] == "failed"
    assert "stopped after 3 attempts" in row["last_error"]
    state.record_job.assert_called_once()
    jobs = state.index.list_jobs()
    assert len(jobs) == 1
    job = json.loads(jobs[0]["metadata_json"])
    assert job["retry_exhausted"] is True
    assert job["attempt_count"] == 3
    assert job["error_detail"].startswith("youtube_rate_limit: ")
    assert sanitized in job["error_detail"]
    for unwanted in ("fixture-user", "fixture-secret", "private",
                     "command-secret", "earlier refusal", "trailing diagnostic"):
        assert unwanted not in job["error_detail"]


def test_media_429_without_error_line_keeps_reason(retry_queue):
    state = retry_queue
    state.extract.side_effect = subprocess.CalledProcessError(
        1, ["yt-dlp", "--password", "command-secret"],
        stderr="WARNING: HTTP Error 429 from https://user:secret@media.example/",
    )
    row = _enqueue(state)
    assert row["last_error"] == "youtube_rate_limit"
    for _ in range(3):
        state.now = datetime.fromisoformat(row["retry_after"])
        assert server._retry_pending_one() is True
        row = _row(state)
        assert row["last_error"].startswith("youtube_rate_limit")
        assert "secret" not in row["last_error"]
    detail = state.record_job.call_args.kwargs["error_detail"]
    assert detail.startswith("youtube_rate_limit")
    assert "secret" not in detail


def test_media_429_detail_uses_existing_sanitizer_limit(retry_queue):
    line = ERROR_LINE + " " + "diagnostic " * 100
    state = retry_queue
    state.extract.side_effect = subprocess.CalledProcessError(
        1, ["yt-dlp"], stderr=line)
    row = _enqueue(state)
    sanitized = server._sanitize_error(line)
    assert len(sanitized) == 200
    assert row["last_error"] == "youtube_rate_limit: " + sanitized


def test_media_429_enqueue_failure_records_sanitized_detail(retry_queue, monkeypatch):
    state = retry_queue
    state.record_job.side_effect = state.real_record_job
    monkeypatch.setattr(state.index, "enqueue_pending",
                        Mock(side_effect=RuntimeError("index unavailable")))
    state.extract.side_effect = subprocess.CalledProcessError(
        1, ["yt-dlp", "--password", "command-secret"], stderr=ERROR_LINE)
    state.handler._handle_extract({"url": URL, "interval": 30})
    status, result = state.handler.response
    assert status == 200
    assert result["ok"] is False
    assert state.index.list_pending(include_terminal=True) == []
    detail = "youtube_rate_limit: " + server._sanitize_error(ERROR_LINE)
    assert result["error_detail"] == detail
    state.record_job.assert_called_once()
    assert state.record_job.call_args.kwargs["error_detail"] == detail
    jobs = state.index.list_jobs()
    assert len(jobs) == 1
    job = json.loads(jobs[0]["metadata_json"])
    assert job["error_detail"] == detail
    assert job["retry_exhausted"] is False


def test_media_429_detail_write_failure_keeps_capture_queued(
        retry_queue, monkeypatch, caplog):
    state = retry_queue
    monkeypatch.setattr(state.index, "set_pending_error",
                        Mock(side_effect=RuntimeError("index unavailable")))
    state.extract.side_effect = subprocess.CalledProcessError(
        1, ["yt-dlp", "--password", "command-secret"], stderr=ERROR_LINE)
    row = _enqueue(state)
    assert row["status"] == "pending"
    assert row["attempt_count"] == 0
    state.record_job.assert_not_called()
    assert "command-secret" not in caplog.text
    assert "fixture-secret" not in caplog.text


@pytest.mark.parametrize("status", ["running", "pending", "failed", "cancelled", "succeeded"])
def test_initial_detail_cannot_overwrite_retry_state(retry_queue, status):
    state = retry_queue
    row = _enqueue(state)
    pending_id = row["pending_id"]
    if status == "running":
        state.index.mark_pending_running(pending_id)
    elif status in {"pending", "failed"}:
        detail = "youtube_rate_limit: ERROR: HTTP Error 429 on retry"
        state.index.mark_pending_failed(
            pending_id, detail, row["retry_after"], force_final=status == "failed")
    elif status == "cancelled":
        state.index.cancel_pending(pending_id)
    else:
        state.index.mark_pending_succeeded(pending_id, "job_fixture")
    before = _row(state)
    assert before["status"] == status

    state.index.set_pending_error(pending_id, "youtube_rate_limit: ERROR: initial refusal")

    assert _row(state) == before
