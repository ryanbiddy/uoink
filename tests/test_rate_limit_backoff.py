"""Offline regressions for media-429 retry timing and exhaustion."""
from __future__ import annotations

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
    monkeypatch.setattr(server, "datetime", Clock)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "captures")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_pending_long_video_modes", {})
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
