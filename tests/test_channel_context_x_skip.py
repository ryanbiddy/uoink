"""F33: an X video capture must not try (and log) a channel-context fetch."""
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server


def test_x_profile_urls_are_skipped_without_running_ytdlp(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("yt-dlp must not run for an X profile")
    monkeypatch.setattr(server, "_run_subprocess", boom)
    for url in ("https://twitter.com/someone", "https://x.com/someone", "https://mobile.twitter.com/a"):
        assert server._fetch_channel_context(url) == {"description": "", "recent_videos": []}


def test_other_failures_log_at_debug_not_warning(monkeypatch, caplog):
    def fail(*_a, **_k):
        raise subprocess.CalledProcessError(1, "yt-dlp")
    monkeypatch.setattr(server, "_run_subprocess", fail)
    with caplog.at_level(logging.DEBUG):
        out = server._fetch_channel_context("https://www.youtube.com/@someone")
    assert out == {"description": "", "recent_videos": []}
    records = [r for r in caplog.records if "channel context fetch failed" in r.getMessage()]
    assert records and all(r.levelno == logging.DEBUG for r in records)
