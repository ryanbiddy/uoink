"""Offline regressions for optional captions in full and chunked captures."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


URL = "https://www.youtube.com/watch?v=abcdef12345"
CAPTION_429 = (
    "ERROR: Unable to download video subtitles for 'en': "
    "HTTP Error 429: Too Many Requests"
)
SUBTITLE_FLAGS = {
    "--write-auto-subs", "--write-subs", "--sub-lang", "--convert-subs",
}


@pytest.fixture
def extraction(monkeypatch, tmp_path):
    state = SimpleNamespace(caption_error=None, media_error=None, calls=[])
    metadata = {
        "id": "abcdef12345", "title": "Caption test", "duration": 60,
        "channel": "Example",
    }

    def fake_run(cmd, **kwargs):
        state.calls.append((list(cmd), kwargs))
        if cmd[0] == "ffmpeg":
            Path(cmd[-1].replace("%04d", "0001")).write_bytes(b"jpeg")
        elif "--skip-download" in cmd:
            if state.caption_error is not None:
                raise state.caption_error
            folder = Path(cmd[cmd.index("-o") + 1]).parent
            assert list(folder.glob("*.mp4")), "media must precede captions"
            (folder / "video.en.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nPlatform captions.\n",
                encoding="utf-8",
            )
        else:
            if state.media_error is not None:
                raise state.media_error
            if SUBTITLE_FLAGS.intersection(cmd) and state.caption_error is not None:
                raise state.caption_error
            template = cmd[cmd.index("-o") + 1]
            count = cmd.count("--download-sections") or 1
            for number in range(1, count + 1):
                path = template.replace("%(section_number)03d", f"{number:03d}")
                Path(path.replace("%(ext)s", "mp4")).write_bytes(b"media")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def fake_asr(media_path, **_kwargs):
        assert media_path.read_bytes() == b"media"
        return [(0.0, 2.0, "Local transcript.")]

    state.asr = Mock(side_effect=fake_asr)
    state.index = Mock(spec=["enqueue_pending"])
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_run_subprocess", fake_run)
    monkeypatch.setattr(server, "_fetch_metadata", Mock(return_value=metadata))
    monkeypatch.setattr(server, "_classify_topic", Mock(return_value="Test"))
    monkeypatch.setattr(server, "_get_index", Mock(return_value=state.index))
    monkeypatch.setattr(server, "_read_settings", Mock(return_value={}))
    monkeypatch.setattr(server, "_reliability_model_status",
                        Mock(return_value={"cached": True}))
    monkeypatch.setattr(server.uoink_reliability, "transcribe_media", state.asr)
    monkeypatch.setattr(server, "_should_start_hook_type", Mock(return_value=False))
    monkeypatch.setattr(server, "_anthropic_key_for_feature", Mock(return_value=None))
    monkeypatch.setattr(server, "_fetch_channel_context", Mock(return_value={}))
    monkeypatch.setattr(server, "_capture_media_plan", Mock(return_value=None))
    for name in (
        "_download_thumbnail", "_incremental_index_update", "_index_yoink",
        "_start_entity_extraction_thread", "_start_comments_thread",
        "_generate_paste_corpus", "_record_single_extract_job", "maybe_toast",
    ):
        monkeypatch.setattr(server, name, Mock(return_value=None))

    unexpected_io = Mock(side_effect=AssertionError("unmocked external I/O"))
    monkeypatch.setattr(subprocess, "run", unexpected_io)
    monkeypatch.setattr(subprocess, "Popen", unexpected_io)
    monkeypatch.setattr(server.urllib.request, "urlopen", unexpected_io)
    monkeypatch.setattr(server.socket, "create_connection", unexpected_io)

    def run(mode="full", cancel_event=None):
        return server._run_extraction(
            URL, 30, tmp_path / "capture", notify=False, metadata=metadata,
            topic="Test", generate_paste=False, long_video_mode=mode,
            cancel_event=cancel_event,
        )

    state.run = run
    yield state
    unexpected_io.assert_not_called()


def test_full_mode_caption_429_completes_without_retry(
        extraction, monkeypatch, caplog):
    extraction.caption_error = subprocess.CalledProcessError(
        1, ["yt-dlp"], stderr=CAPTION_429)
    ownership = SimpleNamespace(
        ok=True, conflict=None, completed_while_waiting=False, reused=None,
    )
    monkeypatch.setattr(server, "_manual_extraction_ownership",
                        lambda _url: nullcontext(ownership))

    class FakeHandler:
        _validate_url_interval = server.Handler._validate_url_interval
        _handle_extract = server.Handler._handle_extract

        def _send_json(self, status, payload):
            self.response = (status, payload)

    handler = FakeHandler()
    handler._handle_extract({"url": URL, "interval": 30, "long_video_mode": "full"})
    status, result = handler.response

    assert status == 200
    assert result["ok"] is True
    assert not result.get("queued")
    extraction.index.enqueue_pending.assert_not_called()
    assert result["screenshot_count"] == 1
    assert result["caption_count"] == 0
    assert result["transcript_source"] == "asr"
    extraction.asr.assert_called_once()
    folder = Path(result["folder"])
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    assert sidecar["transcript_source"] == "asr"
    assert (folder / "transcript.txt").read_text(encoding="utf-8") == "Local transcript."
    assert "full subtitle fetch unavailable" in caplog.text


def test_full_mode_media_command_has_no_subtitle_flags(extraction):
    result = extraction.run()
    media_cmd, media_kwargs = extraction.calls[0]
    caption_cmd, caption_kwargs = extraction.calls[1]

    assert not SUBTITLE_FLAGS.intersection(media_cmd)
    assert "--skip-download" not in media_cmd
    assert media_kwargs["check"] is True
    assert caption_cmd == [
        *server.YTDLP_CMD,
        "--skip-download", "--write-auto-subs", "--write-subs",
        "--sub-lang", "en.*,en", "--convert-subs", "srt",
        "-o", media_cmd[media_cmd.index("-o") + 1], URL,
    ]
    assert Path(caption_cmd[caption_cmd.index("-o") + 1]).name == "video.%(ext)s"
    assert caption_kwargs["check"] is True
    assert caption_kwargs["timeout"] == server.COMMENTS_TIMEOUT_SEC
    assert result["ok"] is True
    assert result["caption_count"] == 1
    assert result["transcript_source"] == "captions"
    extraction.asr.assert_not_called()


@pytest.mark.parametrize("mode", ["full", "chunked"])
@pytest.mark.parametrize("error", [
    OSError("caption fetch unavailable"),
    subprocess.TimeoutExpired(["yt-dlp"], server.COMMENTS_TIMEOUT_SEC),
    subprocess.CalledProcessError(1, ["yt-dlp"], stderr=CAPTION_429.encode("utf-8")),
], ids=["os-error", "timeout", "caption-429-bytes"])
def test_caption_failures_are_optional(extraction, caplog, mode, error):
    extraction.caption_error = error
    result = extraction.run(mode)

    assert result["ok"] is True
    assert result["screenshot_count"] >= 1
    assert result["caption_count"] == 0
    assert f"{mode} subtitle fetch unavailable" in caplog.text
    assert any("--skip-download" in cmd for cmd, _kwargs in extraction.calls)
    if mode == "full":
        extraction.asr.assert_called_once()
    else:
        extraction.asr.assert_not_called()


@pytest.mark.parametrize("mode", ["full", "chunked"])
def test_cancellation_during_caption_fetch_propagates(extraction, caplog, mode):
    cancel_event = threading.Event()
    error = server.PlaylistJobCancelled("playlist job cancelled")
    extraction.caption_error = error

    with pytest.raises(server.PlaylistJobCancelled) as raised:
        extraction.run(mode, cancel_event=cancel_event)

    assert raised.value is error
    assert len(extraction.calls) == 2
    caption_cmd, caption_kwargs = extraction.calls[1]
    assert "--skip-download" in caption_cmd
    assert caption_kwargs["cancel_event"] is cancel_event
    assert "subtitle fetch unavailable" not in caplog.text
    extraction.asr.assert_not_called()


def test_media_failure_still_propagates(extraction):
    error = subprocess.CalledProcessError(
        1, ["yt-dlp"], stderr="ERROR: unable to download video data: HTTP Error 429")
    extraction.media_error = error

    with pytest.raises(subprocess.CalledProcessError) as raised:
        extraction.run()

    assert raised.value is error
    assert len(extraction.calls) == 1
    extraction.asr.assert_not_called()
