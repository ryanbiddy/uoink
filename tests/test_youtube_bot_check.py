"""YouTube's "confirm you're not a bot" check: say so, then back off.

Everything is offline: yt-dlp is replaced by fakes and the cooldown clock is
a fake clock.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402
from tests.test_caption_429_decouple import (  # noqa: E402,F401
    CAPTION_429, URL, extraction,
)

ROOT = Path(__file__).resolve().parent.parent

BOT_CHECK = (
    "ERROR: [youtube] abcdef12345: Sign in to confirm you're not a bot. "
    "Use --cookies-from-browser or --cookies for the authentication. "
    "See  https://github.com/yt-dlp/yt-dlp/wiki/FAQ"
)
OTHER = "ERROR: [youtube] abcdef12345: Video unavailable. This video is private"
MINUTE = 60.0


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(server, "_youtube_bot_check_clock", fake)
    monkeypatch.setattr(server, "_youtube_bot_check_until", None)
    monkeypatch.setattr(server, "_youtube_bot_check_hits", [])
    return fake


def refusal(stderr):
    return subprocess.CalledProcessError(1, ["yt-dlp"], stderr=stderr)


def fetch(monkeypatch, tmp_path, error, url=URL):
    runner = Mock(side_effect=error) if error is not None else Mock()
    monkeypatch.setattr(server, "_run_subprocess", runner)
    reason = server._fetch_video_subtitles(url, tmp_path, long_video_mode="full")
    return reason, runner


@pytest.mark.parametrize("stderr, expected", [
    (BOT_CHECK, "captions_bot_check"),
    (BOT_CHECK.encode(), "captions_bot_check"),
    (CAPTION_429, "captions_rate_limited"),
    ("ERROR: [youtube] x: HTTP Error 429: Too Many Requests", "captions_rate_limited"),
    (OTHER, "captions_failed"),
    ("", "captions_failed"),
])
def test_fetch_returns_a_fixed_reason(monkeypatch, tmp_path, stderr, expected):
    reason, runner = fetch(monkeypatch, tmp_path, refusal(stderr))
    assert reason == expected
    runner.assert_called_once()


def test_fetch_returns_none_when_captions_download(monkeypatch, tmp_path):
    reason, _runner = fetch(monkeypatch, tmp_path, None)
    assert reason is None


def test_timeout_and_os_errors_are_plain_failures(monkeypatch, tmp_path):
    assert fetch(monkeypatch, tmp_path, subprocess.TimeoutExpired(["yt-dlp"], 5))[0] == "captions_failed"
    assert fetch(monkeypatch, tmp_path, OSError("no such file"))[0] == "captions_failed"


def test_other_sites_never_report_a_youtube_wall(monkeypatch, tmp_path):
    reason, _runner = fetch(monkeypatch, tmp_path, refusal(BOT_CHECK), url="https://example.test/v/1")
    assert reason == "captions_failed"


def main_log(caplog):
    """What reaches server.log: the helper's own logger, not the detail log."""
    return " | ".join(r.getMessage() for r in caplog.records if r.name == server.log.name)


def test_main_log_names_the_category_not_the_stderr(monkeypatch, tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        fetch(monkeypatch, tmp_path, refusal(BOT_CHECK))
    text = main_log(caplog)
    assert "full subtitle fetch unavailable: captions_bot_check" in text
    for leaked in ("Sign in", "not a bot", "cookies", "CalledProcessError", "yt-dlp"):
        assert leaked not in text


# ---- capture result, sidecar, note ------------------------------------------


def test_capture_records_why_captions_were_skipped(extraction, caplog):
    extraction.caption_error = refusal(BOT_CHECK)
    with caplog.at_level(logging.INFO):
        result = extraction.run()

    assert result["ok"] is True
    assert result["captions_skipped_reason"] == "captions_bot_check"
    assert result["captions_refused"] is False  # that flag stays for 429 only
    assert result["transcript_source"] == "asr"
    folder = Path(result["folder"])
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    assert sidecar["captions_skipped_reason"] == "captions_bot_check"
    assert sidecar["transcript_source"] == "asr"
    assert "YouTube asked for a bot check" in sidecar["transcript_note"]
    assert "full subtitle fetch unavailable: captions_bot_check" in main_log(caplog)
    assert "not a bot" not in main_log(caplog)


def test_capture_429_keeps_its_old_behavior(extraction):
    extraction.caption_error = refusal(CAPTION_429)
    result = extraction.run()
    assert result["captions_refused"] is True
    assert result["captions_skipped_reason"] == "captions_rate_limited"
    assert result["asr_fallback"]["reason"] == "captions_refused"
    assert "YouTube refused captions" in result["transcript_note"]


def test_capture_with_captions_has_no_reason(extraction):
    result = extraction.run()
    assert result["transcript_source"] == "captions"
    assert result["captions_skipped_reason"] is None


# ---- cooldown ---------------------------------------------------------------


def status():
    return server._youtube_bot_check_status()


def test_health_shape_when_quiet():
    assert status() == {"active": False, "until": None, "hits": 0, "seconds_left": 0}


def test_three_hits_in_fifteen_minutes_start_a_thirty_minute_cooldown(clock):
    server._note_youtube_bot_check()
    clock.advance(5 * MINUTE)
    server._note_youtube_bot_check()
    assert status()["active"] is False and status()["hits"] == 2
    clock.advance(9 * MINUTE)  # 14 minutes after the first hit
    server._note_youtube_bot_check()
    live = status()
    assert live["active"] is True and live["hits"] == 3
    assert live["seconds_left"] == 30 * 60
    assert isinstance(live["until"], str) and live["until"].startswith("20")
    assert set(live) == {"active", "until", "hits", "seconds_left"}


def test_hits_spread_over_more_than_the_window_never_trigger(clock):
    for _ in range(6):
        server._note_youtube_bot_check()
        clock.advance(8 * MINUTE)
    assert status()["active"] is False
    assert status()["hits"] <= 2


def test_cooldown_expires_after_thirty_minutes(clock):
    for _ in range(3):
        server._note_youtube_bot_check()
    clock.advance(29 * MINUTE)
    assert status()["active"] is True
    clock.advance(2 * MINUTE)
    assert status() == {"active": False, "until": None, "hits": 0, "seconds_left": 0}


def test_hits_during_a_cooldown_do_not_extend_it(clock):
    for _ in range(3):
        server._note_youtube_bot_check()
    clock.advance(20 * MINUTE)
    server._note_youtube_bot_check()
    clock.advance(11 * MINUTE)
    assert status()["active"] is False


def test_skips_the_caption_request_while_active_and_resumes_after(monkeypatch, tmp_path, clock):
    for _ in range(3):
        server._note_youtube_bot_check()
    reason, runner = fetch(monkeypatch, tmp_path, refusal(BOT_CHECK))
    assert reason == "captions_bot_check_cooldown"
    runner.assert_not_called()

    # Other sites are not YouTube's business.
    reason, runner = fetch(monkeypatch, tmp_path, None, url="https://example.test/v/1")
    assert reason is None
    runner.assert_called_once()

    clock.advance(31 * MINUTE)
    reason, runner = fetch(monkeypatch, tmp_path, None)
    assert reason is None
    runner.assert_called_once()


def test_capture_during_cooldown_goes_straight_to_local_transcription(extraction):
    for _ in range(3):
        server._note_youtube_bot_check()
    result = extraction.run()

    assert result["ok"] is True
    assert not [cmd for cmd, _kw in extraction.calls if "--skip-download" in cmd]
    assert result["captions_skipped_reason"] == "captions_bot_check_cooldown"
    assert result["transcript_source"] == "asr"
    assert "YouTube asked for a bot check" in result["transcript_note"]
    extraction.asr.assert_called_once()


class FakeProc:
    def __init__(self, stderr, returncode):
        self.stderr_text, self.returncode, self.pid = stderr, returncode, 1

    def communicate(self, timeout=None):
        return b"", self.stderr_text

    def poll(self):
        return self.returncode


def test_real_runner_counts_bot_checks_from_any_youtube_step(monkeypatch):
    monkeypatch.setattr(server, "_youtube_network_slot", lambda _cancel: nullcontext())
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: FakeProc(BOT_CHECK.encode(), 1))
    for step in ("--dump-single-json", "--skip-download", "-f"):  # details, captions, audio
        with pytest.raises(subprocess.CalledProcessError):
            server._run_subprocess([*server.YTDLP_CMD, step, URL],
                                   check=True, stderr=subprocess.PIPE)
    assert status()["active"] is True


def test_real_runner_ignores_other_failures_and_other_programs(monkeypatch):
    monkeypatch.setattr(server, "_youtube_network_slot", lambda _cancel: nullcontext())
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: FakeProc(OTHER.encode(), 1))
    for _ in range(4):
        with pytest.raises(subprocess.CalledProcessError):
            server._run_subprocess([*server.YTDLP_CMD, URL],
                                   check=True, stderr=subprocess.PIPE)
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: FakeProc(BOT_CHECK.encode(), 1))
    for _ in range(4):
        with pytest.raises(subprocess.CalledProcessError):
            server._run_subprocess(["ffmpeg", "-i", "x"], check=True, stderr=subprocess.PIPE)
    assert status() == {"active": False, "until": None, "hits": 0, "seconds_left": 0}


def test_cooldown_state_is_per_process_and_never_touches_disk():
    source = (ROOT / "server.py").read_text(encoding="utf-8")
    start = source.index("def _note_youtube_bot_check")
    block = source[start:source.index("def _fetch_video_subtitles")]
    for word in ("DATA_ROOT", "write_text", "open(", "json.dump", "cookies"):
        assert word not in block


# ---- dashboard ----------------------------------------------------------------


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_dashboard_notice_and_item_line():
    done = subprocess.run(
        ["node", str(ROOT / "tests/js/rehaul_library_reader_test.mjs"), "botcheck"],
        capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
