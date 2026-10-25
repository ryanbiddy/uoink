"""Offline regressions for optional captions in full and chunked captures."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from contextlib import nullcontext
from datetime import datetime, timedelta
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
MEDIA_429 = "ERROR: [youtube] xyz: HTTP Error 429: Too Many Requests"
SUBTITLE_FLAGS = {
    "--write-auto-subs", "--write-subs", "--sub-lang", "--convert-subs",
}


@pytest.fixture
def extraction(monkeypatch, tmp_path):
    state = SimpleNamespace(
        caption_error=None, media_error=None, captions_available=True,
        settings=server._default_settings(), model_cached=True, calls=[],
        media_has_audio=True, audio_error=None, source_has_audio=True,
        probe_error=None, cut_error=None,
    )
    metadata = {
        "id": "abcdef12345", "title": "Caption test", "duration": 60,
        "channel": "Example",
    }
    state.metadata = metadata
    state.folder = tmp_path / "capture"

    def fake_run(cmd, **kwargs):
        state.calls.append((list(cmd), kwargs))
        if Path(cmd[0]).stem == "ffprobe":
            assert Path(cmd[-1]).is_file(), "probe must inspect a captured or downloaded file"
            if state.probe_error is not None:
                raise state.probe_error
            has_audio = state.source_has_audio if Path(cmd[-1]).name.startswith("audio.") else state.media_has_audio
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps({"streams": [{"index": 1}] if has_audio else []}), b"")
        if cmd[0] == "ffmpeg":
            if Path(cmd[-1]).suffix == ".wav" and state.cut_error is not None:
                raise state.cut_error
            data = b"media" if Path(cmd[-1]).suffix == ".wav" else b"jpeg"
            Path(cmd[-1].replace("%04d", "0001")).write_bytes(data)
        elif "--skip-download" in cmd:
            if state.caption_error is not None:
                raise state.caption_error
            folder = Path(cmd[cmd.index("-o") + 1]).parent
            assert list(folder.glob("*.mp4")), "media must precede captions"
            if state.captions_available:
                (folder / "video.en.srt").write_text(
                    "1\n00:00:00,000 --> 00:00:02,000\nPlatform captions.\n",
                    encoding="utf-8",
                )
        else:
            if "bestaudio/best" in cmd and state.audio_error is not None:
                raise state.audio_error
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
    state.comments = Mock()
    state.index = Mock(spec=["enqueue_pending", "set_pending_error"])
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_run_subprocess", fake_run)
    monkeypatch.setattr(server, "_fetch_metadata", Mock(return_value=metadata))
    monkeypatch.setattr(server, "_classify_topic", Mock(return_value="Test"))
    monkeypatch.setattr(server, "_get_index", Mock(return_value=state.index))
    monkeypatch.setattr(server, "_read_settings", lambda: state.settings)
    monkeypatch.setattr(server, "_reliability_model_status",
                        lambda _model: {"cached": state.model_cached})
    monkeypatch.setattr(server.uoink_reliability, "transcribe_media", state.asr)
    monkeypatch.setattr(server, "_should_start_hook_type", Mock(return_value=False))
    monkeypatch.setattr(server, "_anthropic_key_for_feature", Mock(return_value=None))
    monkeypatch.setattr(server, "_fetch_channel_context", Mock(return_value={}))
    monkeypatch.setattr(server, "_capture_media_plan", Mock(return_value=None))
    monkeypatch.setattr(server, "_start_comments_thread", state.comments)
    for name in (
        "_download_thumbnail", "_incremental_index_update", "_index_yoink",
        "_start_entity_extraction_thread",
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
            URL, 30, state.folder, notify=False, metadata=metadata,
            topic="Test", generate_paste=False, long_video_mode=mode,
            cancel_event=cancel_event,
        )

    state.run = run
    yield state
    unexpected_io.assert_not_called()


@pytest.fixture
def extract_handler(monkeypatch):
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

    def run(mode):
        handler._handle_extract({"url": URL, "interval": 30, "long_video_mode": mode})
        return handler.response

    return run


@pytest.mark.parametrize("mode", ["full", "chunked"])
def test_full_mode_caption_429_completes_without_retry(
        extraction, extract_handler, caplog, mode):
    extraction.caption_error = subprocess.CalledProcessError(
        1, ["yt-dlp"], stderr=CAPTION_429)
    status, result = extract_handler(mode)

    assert status == 200
    assert result["ok"] is True
    assert not result.get("queued")
    extraction.index.enqueue_pending.assert_not_called()
    assert result["screenshot_count"] == 1
    assert result["caption_count"] == 0
    assert result["transcript_source"] == "asr"
    assert result["asr_fallback"]["reason"] == "captions_refused"
    extraction.asr.assert_called_once()
    assert extraction.asr.call_args.kwargs == {
        "model_name": "base", "model_root": server.RELIABILITY_MODEL_ROOT,
    }
    folder = Path(result["folder"])
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    assert sidecar["transcript_source"] == "asr"
    assert sidecar["asr_fallback"]["status"] == "completed"
    assert sidecar["asr_fallback"]["reason"] == "captions_refused"
    assert "Local Whisper transcript" in sidecar["transcript_note"]
    assert "YouTube refused captions" in result["yoink_md"]
    assert sidecar["transcript_note"] in (folder / f"{folder.name}.md").read_text(
        encoding="utf-8")
    assert (folder / "transcript.txt").read_text(encoding="utf-8") == "Local transcript."
    assert f"{mode} subtitle fetch unavailable" in caplog.text


@pytest.mark.parametrize("mode", ["full", "chunked"])
@pytest.mark.parametrize("asr_status", ["disabled", "model_not_downloaded"])
@pytest.mark.parametrize("refused", [True, False], ids=["refused", "unavailable"])
def test_captionless_capture_saved_without_asr_or_retry(
        extraction, extract_handler, mode, asr_status, refused):
    extraction.captions_available = False
    if refused:
        extraction.caption_error = subprocess.CalledProcessError(
            1, ["yt-dlp"], stderr=CAPTION_429.encode("utf-8"))
    if asr_status == "disabled":
        extraction.settings["asr_fallback_enabled"] = False
    else:
        extraction.model_cached = False

    status, result = extract_handler(mode)

    assert status == 200
    assert result["ok"] is True
    assert not result.get("queued")
    extraction.index.enqueue_pending.assert_not_called()
    extraction.asr.assert_not_called()
    extraction.comments.assert_called_once()
    assert result["screenshot_count"] == 1
    assert result["caption_count"] == 0
    assert result["transcript_segment_count"] == 0
    assert result["transcript_source"] is None
    folder = Path(result["folder"])
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    reason = "captions_refused" if refused else "captions_unavailable"
    note = ("No transcript: YouTube refused captions" if refused
            else "No transcript: YouTube captions unavailable")
    assert sidecar["asr_fallback"]["status"] == asr_status
    assert sidecar["asr_fallback"]["reason"] == reason
    assert sidecar["transcript_source"] is None
    assert sidecar["transcript"] == []
    assert sidecar["transcript_note"] == note
    assert result["transcript_note"] == note
    assert note in result["yoink_md"]
    assert note in (folder / f"{folder.name}.md").read_text(encoding="utf-8")
    assert (folder / "metadata.json").is_file()
    assert (folder / "screenshots" / "shot_0001.jpg").is_file()
    assert not (folder / "transcript.txt").exists()


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
    assert result["asr_fallback"] == {"status": "not_needed"}
    assert result["transcript_note"] is None
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
    extraction.asr.assert_called_once()
    assert result["transcript_source"] == "asr"
    assert result["asr_fallback"]["reason"] == (
        "captions_refused" if isinstance(error, subprocess.CalledProcessError)
        else "captions_unavailable"
    )


@pytest.mark.parametrize("mode", ["full", "chunked"])
def test_absent_captions_reach_asr(extraction, mode):
    extraction.captions_available = False
    result = extraction.run(mode)

    assert result["ok"] is True
    assert result["transcript_source"] == "asr"
    assert result["asr_fallback"]["reason"] == "captions_unavailable"
    assert "YouTube captions unavailable" in result["yoink_md"]
    extraction.asr.assert_called_once()
    assert not any("bestaudio/best" in cmd for cmd, _kwargs in extraction.calls)


@pytest.mark.parametrize("mode", ["full", "chunked"])
@pytest.mark.parametrize("probe_error", [
    None,
    FileNotFoundError("ffprobe missing"),
    subprocess.CalledProcessError(1, ["ffprobe"]),
    subprocess.TimeoutExpired(["ffprobe"], 30),
], ids=["positive", "missing", "exit-1", "timeout"])
def test_embedded_audio_transcribes_despite_probe_errors(extraction, mode, probe_error):
    extraction.captions_available = False
    extraction.metadata["duration"] = 7200
    extraction.probe_error = probe_error

    result = extraction.run(mode)

    assert result["ok"] is True
    assert result["asr_fallback"]["status"] == "completed"
    probes = [Path(cmd[-1]) for cmd, _kwargs in extraction.calls if Path(cmd[0]).stem == "ffprobe"]
    expected_count = len(result["long_video_chunks"]) if mode == "chunked" else 1
    assert expected_count > 1 if mode == "chunked" else expected_count == 1
    assert len(probes) == extraction.asr.call_count == expected_count
    assert probes == [call.args[0] for call in extraction.asr.call_args_list]
    assert all(path.name.startswith("video") for path in probes)
    assert not any("bestaudio/best" in cmd for cmd, _kwargs in extraction.calls)


@pytest.mark.parametrize("mode", ["full", "chunked"])
@pytest.mark.parametrize("probe_error", [
    FileNotFoundError("ffprobe missing"),
    subprocess.CalledProcessError(1, ["ffprobe"]),
    subprocess.TimeoutExpired(["ffprobe"], 30),
], ids=["missing", "exit-1", "timeout"])
def test_video_only_inconclusive_probe_downloads_once(extraction, mode, probe_error):
    extraction.captions_available = False
    extraction.metadata["duration"] = 7200
    extraction.media_has_audio = False
    extraction.probe_error = probe_error

    def asr(path, **_kwargs):
        assert path.is_file()
        if path.name.startswith("video"):
            raise IndexError("no audio stream")
        return [(0.0, 2.0, "Recovered transcript.")]

    extraction.asr.side_effect = asr
    result = extraction.run(mode)

    assert result["ok"] is True
    assert result["transcript_source"] == "asr"
    assert result["asr_fallback"]["status"] == "completed"
    assert len([cmd for cmd, _kwargs in extraction.calls if "bestaudio/best" in cmd]) == 1
    section_count = len(result["long_video_chunks"]) if mode == "chunked" else 1
    assert extraction.asr.call_count == 2 * section_count
    assert (extraction.folder / "transcript.txt").read_text(encoding="utf-8").count(
        "Recovered transcript.") == section_count
    assert not list(extraction.folder.glob(".asr-*"))


@pytest.mark.parametrize("mode", ["full", "chunked"])
def test_positive_probe_index_error_stays_failed(extraction, mode):
    extraction.captions_available = False
    extraction.asr.side_effect = IndexError("decoder index error")

    result = extraction.run(mode)

    assert result["ok"] is True
    assert result["asr_fallback"]["status"] == "failed"
    extraction.asr.assert_called_once()
    assert not any("bestaudio/best" in cmd for cmd, _kwargs in extraction.calls)
    assert not (extraction.folder / "transcript.txt").exists()


@pytest.mark.parametrize("mode", ["full", "chunked"])
def test_audio_download_timeout_keeps_capture_without_transcript(extraction, mode):
    extraction.captions_available = False
    extraction.media_has_audio = False
    extraction.audio_error = subprocess.TimeoutExpired(["yt-dlp"], 60)

    result = extraction.run(mode)

    assert result["ok"] is True
    assert result["asr_fallback"]["status"] == "no_audio"
    assert result["asr_fallback"]["caption_reason"] == "captions_unavailable"
    assert not (extraction.folder / "transcript.txt").exists()
    assert not list(extraction.folder.glob(".asr-*"))
    extraction.asr.assert_not_called()


@pytest.mark.parametrize("source_has_audio", [True, False], ids=["transcript", "no-audio"])
def test_asr_cleanup_lock_retries_without_discarding_result(extraction, monkeypatch, source_has_audio):
    extraction.captions_available = False
    extraction.media_has_audio = False
    extraction.source_has_audio = source_has_audio
    unlink = server.os.unlink
    locked = []

    def locked_unlink(path, *args, **kwargs):
        if (Path(path).name.startswith("audio.") and len(locked) < 2):
            locked.append(path)
            raise PermissionError("media temporarily locked")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(server.os, "unlink", locked_unlink)
    result = extraction.run()

    assert len(locked) == 2, "exercise the initial cleanup and its permission retry"
    assert result["ok"] is True
    assert result["asr_fallback"]["status"] == ("completed" if source_has_audio else "no_audio")
    assert result["transcript_source"] == ("asr" if source_has_audio else None)
    assert (extraction.folder / "transcript.txt").exists() is source_has_audio
    assert not any(part.startswith(".asr-") for path in extraction.folder.rglob("*")
                   for part in path.relative_to(extraction.folder).parts)


@pytest.mark.parametrize("nested", [False, True], ids=["capture-root", "nested"])
def test_refresh_does_not_publish_asr_files_when_cleanup_stays_locked(extraction, monkeypatch, nested):
    extraction.run()
    extraction.captions_available = False
    extraction.media_has_audio = False
    rmtree = server.shutil.rmtree
    temporary_rmtree = server.tempfile.TemporaryDirectory._rmtree
    rename = Path.rename
    cleanup_attempts = []
    published = []

    def locked_temporary_rmtree(path, ignore_errors=False, **kwargs):
        if Path(path).name.startswith(".asr-"):
            assert ignore_errors is True
            return  # A locked file remains after best-effort temporary cleanup.
        return temporary_rmtree(path, ignore_errors=ignore_errors, **kwargs)

    def locked_rmtree(path, *args, **kwargs):
        if Path(path).name.startswith(".asr-"):
            cleanup_attempts.append(Path(path))
            raise OSError("media still locked")
        return rmtree(path, *args, **kwargs)

    def record_rename(path, target):
        published.append(Path(target).relative_to(extraction.folder))
        return rename(path, target)

    original_asr = extraction.asr.side_effect

    def asr(path, **kwargs):
        if nested:
            nested_dir = path.parent.parent / "screenshots" / ".asr-leftover"
            nested_dir.mkdir()
            (nested_dir / "audio.m4a").write_bytes(b"leftover")
        return original_asr(path, **kwargs)

    extraction.asr.side_effect = asr
    monkeypatch.setattr(server.tempfile.TemporaryDirectory, "_rmtree", staticmethod(locked_temporary_rmtree))
    monkeypatch.setattr(server.shutil, "rmtree", locked_rmtree)
    monkeypatch.setattr(Path, "rename", record_rename)

    result = extraction.run()

    assert result["ok"] is True and result["transcript_source"] == "asr"
    assert cleanup_attempts
    assert all(not part.startswith(".asr-") for path in published for part in path.parts)
    assert not any(part.startswith(".asr-") for path in extraction.folder.rglob("*")
                   for part in path.relative_to(extraction.folder).parts)
    assert (extraction.folder / "transcript.txt").read_text(encoding="utf-8") == "Local transcript."


@pytest.mark.parametrize("mode", ["full", "chunked"])
@pytest.mark.parametrize("outcome", ["recovered", "download_failed", "silent_source"])
def test_caption_refusal_recovers_audio_or_reports_no_audio(extraction, mode, outcome):
    extraction.caption_error = subprocess.CalledProcessError(1, ["yt-dlp"], stderr=CAPTION_429)
    extraction.media_has_audio = False
    if outcome == "download_failed":
        extraction.audio_error = subprocess.CalledProcessError(1, ["yt-dlp"], stderr=MEDIA_429)
    extraction.source_has_audio = outcome != "silent_source"

    result = extraction.run(mode)

    assert result["ok"] is True
    assert not result.get("queued")
    extraction.index.enqueue_pending.assert_not_called()
    assert len([cmd for cmd, _kwargs in extraction.calls if "bestaudio/best" in cmd]) == 1
    if outcome == "recovered":
        assert result["transcript_source"] == "asr"
        assert result["asr_fallback"]["reason"] == "captions_refused"
        extraction.asr.assert_called_once()
    else:
        assert result["transcript_source"] is None
        assert result["asr_fallback"]["status"] == "no_audio"
        assert result["asr_fallback"]["caption_reason"] == "captions_refused"
        assert "audio stream" in result["transcript_note"]
        extraction.asr.assert_not_called()
    assert not list(extraction.folder.glob(".asr-*"))


def test_video_only_chunks_download_audio_once_and_preserve_offsets(extraction):
    extraction.captions_available = False
    extraction.media_has_audio = False
    extraction.metadata["duration"] = 7200
    extraction.asr.side_effect = None
    extraction.asr.return_value = [(-1.0, 2.0, "opening"), (119.0, 121.0, "ending")]

    result = extraction.run("chunked")

    chunks = result["long_video_chunks"]
    assert len(chunks) > 1
    downloads = [cmd for cmd, _kwargs in extraction.calls if "bestaudio/best" in cmd]
    cuts = [cmd for cmd, _kwargs in extraction.calls if cmd[0] == "ffmpeg" and "-ss" in cmd]
    assert len(downloads) == 1
    assert len(cuts) == len(chunks) == extraction.asr.call_count
    assert [float(cmd[cmd.index("-ss") + 1]) for cmd in cuts] == [c["start_seconds"] for c in chunks]
    assert [float(cmd[cmd.index("-t") + 1]) for cmd in cuts] == [c["duration_seconds"] for c in chunks]
    assert all(call.args[0].suffix == ".wav" for call in extraction.asr.call_args_list)
    assert result["asr_fallback"]["coverage"] == "sampled_sections"
    assert result["asr_fallback"]["duration_seconds"] == result["processed_media_seconds"]
    folder = extraction.folder
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    expected = []
    for chunk in chunks:
        offset, length = chunk["start_seconds"], chunk["duration_seconds"]
        expected.extend((offset + max(0, start), offset + min(end, length))
                        for start, end, _text in extraction.asr.return_value
                        if min(end, length) > max(0, start))
    assert [(row["start"], row["end"]) for row in sidecar["transcript"]] == expected
    assert not list(folder.glob(".asr-*"))


def test_audio_download_cancellation_prevents_publication(extraction):
    extraction.captions_available = False
    extraction.media_has_audio = False
    extraction.audio_error = server.PlaylistJobCancelled("playlist job cancelled")
    cancel_event = threading.Event()

    with pytest.raises(server.PlaylistJobCancelled):
        extraction.run(cancel_event=cancel_event)

    download = next((cmd, kwargs) for cmd, kwargs in extraction.calls if "bestaudio/best" in cmd)
    assert download[1]["cancel_event"] is cancel_event
    extraction.asr.assert_not_called()
    extraction.comments.assert_not_called()
    assert not list(extraction.folder.glob(".asr-*"))
    assert not (extraction.folder / f"{extraction.folder.name}.json").exists()


@pytest.mark.parametrize("phase", ["probe", "cut", "whisper"])
def test_audio_fallback_cancellation_prevents_publication(extraction, phase):
    extraction.captions_available = False
    extraction.media_has_audio = False
    error = server.PlaylistJobCancelled("playlist job cancelled")
    if phase == "probe":
        extraction.probe_error = error
    elif phase == "cut":
        extraction.cut_error = error
    else:
        extraction.asr.side_effect = error

    with pytest.raises(server.PlaylistJobCancelled):
        extraction.run("chunked", cancel_event=threading.Event())

    extraction.comments.assert_not_called()
    assert not list(extraction.folder.glob(".asr-*"))
    assert not (extraction.folder / "transcript.txt").exists()
    assert not (extraction.folder / f"{extraction.folder.name}.json").exists()


def test_chunked_asr_uses_source_timestamps_and_discloses_sampled_coverage(extraction):
    extraction.caption_error = subprocess.CalledProcessError(
        1, ["yt-dlp"], stderr=CAPTION_429)
    extraction.metadata["duration"] = 7200
    result = extraction.run("chunked")

    chunks = result["long_video_chunks"]
    assert len(chunks) > 1
    assert chunks[1]["start_seconds"] > chunks[0]["end_seconds"]
    assert extraction.asr.call_count == len(chunks)
    assert [call.args[0].name for call in extraction.asr.call_args_list] == [
        f"video-chunk-{number:03d}.mp4" for number in range(1, len(chunks) + 1)
    ]
    folder = Path(result["folder"])
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    assert sidecar["transcript_source"] == "asr"
    assert sidecar["asr_fallback"]["reason"] == "captions_refused"
    assert sidecar["asr_fallback"]["coverage"] == "sampled_sections"
    assert sidecar["asr_fallback"]["duration_seconds"] == result["processed_media_seconds"]
    assert [(row["start"], row["end"]) for row in sidecar["transcript"]] == [
        (chunk["start_seconds"], chunk["start_seconds"] + 2.0) for chunk in chunks
    ]
    assert "Local Whisper transcript of sampled sections" in result["yoink_md"]
    assert "retaining the full available subtitle track" not in result["yoink_md"]
    assert "retaining the full available subtitle track" not in sidecar["screenshot_cap_warning"]


@pytest.mark.parametrize("duration", [60, 7200])
def test_chunked_captions_retain_full_subtitle_coverage_note(extraction, duration):
    extraction.metadata["duration"] = duration
    result = extraction.run("chunked")

    assert result["ok"] is True
    assert result["transcript_source"] == "captions"
    extraction.asr.assert_not_called()
    folder = Path(result["folder"])
    sidecar = json.loads((folder / f"{folder.name}.json").read_text(encoding="utf-8"))
    note = (
        f"Chunked mode sampled {len(result['long_video_chunks'])} media sections "
        f"({result['processed_media_seconds'] // 60}m of {duration // 60}m) "
        "while retaining the full available subtitle track."
    )
    assert note in sidecar["screenshot_cap_warning"]
    assert f"**Note:** {sidecar['screenshot_cap_warning']}" in result["yoink_md"]
    assert note in (folder / f"{folder.name}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("mode, cancel_after", [
    ("chunked", 1), ("chunked", server.LONG_VIDEO_MAX_CHUNKS), ("full", 1),
], ids=["first-chunk", "last-chunk", "full-media"])
def test_cancellation_during_asr_prevents_publication(extraction, mode, cancel_after):
    extraction.caption_error = subprocess.CalledProcessError(
        1, ["yt-dlp"], stderr=CAPTION_429)
    extraction.metadata["duration"] = 7200
    cancel_event = threading.Event()

    def cancel_during_asr(_path, **_kwargs):
        if extraction.asr.call_count == cancel_after:
            cancel_event.set()
        return [(0.0, 2.0, "Local transcript.")]

    extraction.asr.side_effect = cancel_during_asr

    with pytest.raises(server.PlaylistJobCancelled):
        extraction.run(mode, cancel_event=cancel_event)

    assert cancel_event.is_set()
    assert extraction.asr.call_count == cancel_after
    extraction.comments.assert_not_called()
    extraction.index.enqueue_pending.assert_not_called()
    folder = extraction.folder
    assert not (folder / "transcript.txt").exists()
    assert not (folder / f"{folder.name}.md").exists()
    assert not (folder / f"{folder.name}.json").exists()


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


@pytest.mark.parametrize("as_bytes", [False, True], ids=["text", "bytes"])
@pytest.mark.parametrize("stderr, media_refused, captions_refused", [
    (CAPTION_429, False, True),
    ("ERROR: https://www.youtube.com/api/timedtext: "
     "HTTP Error 429: Too Many Requests", False, True),
    ("WARNING: Subtitles request failed with status 429", False, True),
    ("[info] xyz: Downloading 1 format(s): 18\n" + CAPTION_429, False, True),
    (MEDIA_429, True, False),
    ("ERROR: unable to download video data: HTTP Error 429", True, False),
    ("ERROR: HTTP Error 429: Too Many Requests", True, False),
    (CAPTION_429 + "\n" + MEDIA_429, True, True),
    (MEDIA_429 + "\n" + CAPTION_429, True, True),
    ("[info] xyz: Downloading subtitles: en\n" + MEDIA_429, True, False),
    ("ERROR: Unable to download video subtitles: HTTP Error 403\n" + MEDIA_429,
     True, False),
    ("ERROR: Unable to download video subtitles: HTTP Error 403", False, False),
    ("ERROR: HTTP Error 403: Forbidden", False, False),
    ("", False, False),
], ids=[
    "subtitles", "timedtext", "subtitle-status", "captions-with-media-info",
    "media-info", "media-data", "generic-429", "captions-then-media",
    "media-then-captions", "subtitle-info-with-media-429",
    "subtitle-403-with-media-429", "subtitle-403", "media-403", "empty",
])
def test_youtube_429_classification_by_endpoint(
        stderr, media_refused, captions_refused, as_bytes):
    if as_bytes:
        stderr = stderr.encode("utf-8")
    error = subprocess.CalledProcessError(1, ["yt-dlp"], stderr=stderr)

    assert server._is_youtube_rate_limit(error) is media_refused
    assert server._is_youtube_captions_refusal(error) is captions_refused


@pytest.mark.parametrize("error", [
    RuntimeError(MEDIA_429),
    OSError(CAPTION_429),
    subprocess.TimeoutExpired(["yt-dlp"], 30, stderr=CAPTION_429),
    subprocess.CalledProcessError(1, ["yt-dlp"]),
    subprocess.CalledProcessError(1, ["yt-dlp"], output=MEDIA_429),
], ids=["runtime", "os-error", "timeout", "no-stderr", "stdout-only"])
def test_youtube_429_classification_requires_subprocess_stderr(error):
    assert server._is_youtube_rate_limit(error) is False
    assert server._is_youtube_captions_refusal(error) is False


@pytest.mark.parametrize("mode", ["full", "chunked"])
@pytest.mark.parametrize("stderr", [
    MEDIA_429, CAPTION_429 + "\n" + MEDIA_429,
], ids=["media-only", "mixed"])
def test_media_429_still_enqueues_capture(
        extraction, extract_handler, monkeypatch, mode, stderr):
    extraction.media_error = subprocess.CalledProcessError(
        1, ["yt-dlp"], stderr=stderr)
    extraction.index.enqueue_pending.return_value = 42
    monkeypatch.setattr(server, "_pending_long_video_modes", {})
    earliest_retry = datetime.now() + timedelta(
        seconds=server._RATE_LIMIT_INITIAL_BACKOFF_SEC)

    status, result = extract_handler(mode)

    latest_retry = datetime.now() + timedelta(
        seconds=server._RATE_LIMIT_INITIAL_BACKOFF_SEC)
    assert status == 200
    assert result == {
        "ok": True, "queued": True, "pending_id": 42,
        "retry_after": result["retry_after"], "reason": "youtube_rate_limit",
        "long_video_mode": mode,
    }
    retry_after = datetime.fromisoformat(result["retry_after"])
    assert earliest_retry.replace(microsecond=0) <= retry_after <= latest_retry
    extraction.index.enqueue_pending.assert_called_once_with(
        URL, 30, result["retry_after"], mode)
    # The pending row keeps the reason code plus the real yt-dlp line.
    extraction.index.set_pending_error.assert_called_once()
    pending_id, stored = extraction.index.set_pending_error.call_args.args
    assert pending_id == 42
    assert stored.startswith("youtube_rate_limit: ERROR:")
    assert "HTTP Error 429" in stored
    assert server._pending_long_video_mode(42) == mode
    assert len(extraction.calls) == 1
    extraction.asr.assert_not_called()
    extraction.comments.assert_not_called()
