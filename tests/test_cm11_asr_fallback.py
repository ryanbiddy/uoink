"""CM-11: local ASR fallback for video captures without captions.

The fallback is deliberately caption-first and local-only. A platform
subtitle track wins whenever one exists. When it does not, Uoink may use an
already-downloaded faster-whisper model; it must never turn capture into an
implicit model download. The setting defaults on but is reversible, and an
ASR failure must not discard the otherwise valid capture.

Run: python -m pytest tests/test_cm11_asr_fallback.py -q

Red before CM-11:
  - no ASR fallback setting or resolver exists;
  - ensure_model does not leave the readiness marker the server checks;
  - caption-less X video sidecars have no transcript or source provenance;
  - the dashboard has no opt-out control or duration-scaled compute copy.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import types
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402
import uoink_reliability as reliability  # noqa: E402


@pytest.fixture(autouse=True)
def offline_capture(monkeypatch):
    unexpected_io = Mock(side_effect=AssertionError("unmocked external I/O"))
    monkeypatch.setattr(server.subprocess, "run", unexpected_io)
    monkeypatch.setattr(server.subprocess, "Popen", unexpected_io)
    monkeypatch.setattr(server.urllib.request, "urlopen", unexpected_io)
    monkeypatch.setattr(server.socket, "create_connection", unexpected_io)
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: None)
    monkeypatch.setattr(server, "_get_saved_scrapecreators_key", lambda: "")
    monkeypatch.setattr(server, "_anthropic_key_for_feature", lambda *_args: None)
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)

    def probe_only(cmd, **_kwargs):
        assert Path(cmd[0]).stem == "ffprobe", f"unexpected command: {cmd}"
        return subprocess.CompletedProcess(cmd, 0, b'{"streams": [{"index": 1}]}', b"")

    monkeypatch.setattr(server, "_run_subprocess", probe_only)
    yield
    unexpected_io.assert_not_called()


def _assert(condition, message="assertion failed"):
    if not condition:
        raise AssertionError(message)


def test_asr_fallback_setting_defaults_on_and_is_public():
    _assert(server._default_settings().get("asr_fallback_enabled") is True,
            "caption-less video fallback must default ON but remain opt-outable")
    _assert(server._normalize_settings(
        {"asr_fallback_enabled": 0})["asr_fallback_enabled"] is False,
        "normalization must preserve an explicit opt-out")
    _assert(server._public_settings(
        {"asr_fallback_enabled": False}).get("asr_fallback_enabled") is False,
        "the dashboard must receive the user's opt-out")


def test_duration_expectation_scales_with_source_length():
    one_hour = server._asr_duration_expectation(3600)
    two_hours = server._asr_duration_expectation(7200)
    _assert(one_hour["estimated_minutes_min"] == 10.0
            and one_hour["estimated_minutes_max"] == 15.0,
            f"one-hour estimate must document 10-15 minutes: {one_hour}")
    _assert(two_hours["estimated_minutes_min"] == 20.0
            and two_hours["estimated_minutes_max"] == 30.0,
            f"estimate must scale with duration: {two_hours}")
    unknown = server._asr_duration_expectation(0)
    _assert(unknown["estimated_minutes_min"] is None
            and unknown["estimated_minutes_max"] is None,
            f"unknown duration must not claim zero compute time: {unknown}")
    _assert("typical laptop" in one_hour["basis"],
            f"estimate needs an honest hardware qualifier: {one_hour}")


def test_captions_win_without_loading_asr(monkeypatch, tmp_path):
    entries = [(0.0, 2.0, "platform words")]

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("ASR must not run when captions exist")

    monkeypatch.setattr(reliability, "transcribe_media", _must_not_run,
                        raising=False)
    resolved, source, fallback = server._resolve_video_transcript(
        entries, tmp_path / "video.mp4", 120,
        settings={"asr_fallback_enabled": True, "whisper_model": "tiny"})

    _assert(resolved == entries, f"captions changed: {resolved}")
    _assert(source == "captions", f"wrong provenance: {source}")
    _assert(fallback["status"] == "not_needed", f"wrong status: {fallback}")


def test_opt_out_and_missing_model_do_not_transcribe(monkeypatch, tmp_path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"media")
    calls = []
    monkeypatch.setattr(
        reliability, "transcribe_media",
        lambda *_args, **_kwargs: calls.append(True) or [],
        raising=False,
    )

    entries, source, fallback = server._resolve_video_transcript(
        [], media, 3600,
        settings={"asr_fallback_enabled": False, "whisper_model": "tiny"})
    _assert(entries == [] and source is None,
            f"opt-out must leave the transcript empty: {entries}, {source}")
    _assert(fallback["status"] == "disabled", f"opt-out status: {fallback}")

    monkeypatch.setattr(
        server, "_reliability_model_status",
        lambda _model=None: {"model": "tiny", "cached": False},
    )
    entries, source, fallback = server._resolve_video_transcript(
        [], media, 3600,
        settings={"asr_fallback_enabled": True, "whisper_model": "tiny"})
    _assert(entries == [] and source is None and not calls,
            "a missing model must never trigger an implicit download")
    _assert(fallback["status"] == "model_not_downloaded",
            f"missing-model status: {fallback}")
    _assert(fallback["estimated_minutes_min"] == 10.0
            and fallback["estimated_minutes_max"] == 15.0,
            f"skip metadata must retain the duration estimate: {fallback}")


def test_asr_failure_is_nonfatal_and_sanitized(monkeypatch, tmp_path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"media")
    monkeypatch.setattr(
        server, "_reliability_model_status",
        lambda _model=None: {"model": "tiny", "cached": True},
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("decoder failed at C:\\Users\\Ryan\\secret.mp4")

    monkeypatch.setattr(reliability, "transcribe_media", _boom, raising=False)
    entries, source, fallback = server._resolve_video_transcript(
        [], media, 30,
        settings={"asr_fallback_enabled": True, "whisper_model": "tiny"})

    _assert(entries == [] and source is None,
            "ASR failure must leave a valid caption-less capture")
    _assert(fallback["status"] == "failed", f"failure status: {fallback}")
    _assert("C:\\Users" not in fallback.get("error", ""),
            f"sidecar error leaked a local path: {fallback}")


@pytest.mark.parametrize("payload, expected", [
    ('{"streams": [{"index": 1}]}', True),
    ('{"streams": []}', False),
    ('{"streams": null}', None),
    ('{"streams": {}}', None),
    ('{"streams": "audio"}', None),
    ('{}', None),
    ('[]', None),
    ('null', None),
    ('invalid json', None),
])
def test_audio_probe_requires_an_object_with_a_streams_list(monkeypatch, tmp_path, payload, expected):
    probe = Mock(return_value=subprocess.CompletedProcess(["ffprobe"], 0, payload, b""))
    monkeypatch.setattr(server, "_run_subprocess", probe)

    assert server._media_has_audio(tmp_path / "video.mp4") is expected
    probe.assert_called_once()


@pytest.mark.parametrize("error", [
    FileNotFoundError("ffprobe missing"),
    subprocess.CalledProcessError(1, ["ffprobe"]),
    subprocess.TimeoutExpired(["ffprobe"], 30),
], ids=["missing", "exit-1", "timeout"])
def test_audio_probe_errors_are_inconclusive(monkeypatch, tmp_path, error):
    monkeypatch.setattr(server, "_run_subprocess", Mock(side_effect=error))
    assert server._media_has_audio(tmp_path / "video.mp4") is None


def test_audio_probe_cancellation_propagates(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_run_subprocess", Mock(side_effect=server.PlaylistJobCancelled()))
    with pytest.raises(server.PlaylistJobCancelled):
        server._media_has_audio(tmp_path / "video.mp4")


def test_cancellation_after_probe_stops_before_whisper(monkeypatch, tmp_path):
    cancel_event = threading.Event()
    monkeypatch.setattr(server, "_reliability_model_status", lambda _model: {"cached": True})

    def probe(*_args):
        cancel_event.set()
        return True

    monkeypatch.setattr(server, "_media_has_audio", probe)
    asr = Mock()
    monkeypatch.setattr(reliability, "transcribe_media", asr)
    with pytest.raises(server.PlaylistJobCancelled):
        server._resolve_video_transcript(
            [], tmp_path / "video.mp4", 60, settings={"whisper_model": "base"},
            cancel_event=cancel_event)
    asr.assert_not_called()


@pytest.mark.parametrize("has_audio", [True, None], ids=["positive", "inconclusive"])
@pytest.mark.parametrize("error_type", [IndexError, RuntimeError])
def test_only_inconclusive_probe_index_error_downloads_audio(
        monkeypatch, tmp_path, has_audio, error_type):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"media")
    monkeypatch.setattr(server, "_reliability_model_status", lambda _model: {"cached": True})
    probe = Mock(return_value=has_audio)
    monkeypatch.setattr(server, "_media_has_audio", probe)
    words = [(0.0, 2.0, "recovered words")]
    asr = Mock(side_effect=[error_type("decoder error"), words])
    monkeypatch.setattr(reliability, "transcribe_media", asr)

    def download(_url, folder, _cancel_event):
        path = folder / "audio.m4a"
        path.write_bytes(b"audio")
        return path

    download = Mock(side_effect=download)
    monkeypatch.setattr(server, "_download_reliability_audio", download)
    entries, source, fallback = server._resolve_video_transcript(
        [], media, 60, url="https://example.com/video", settings={"whisper_model": "base"})

    assert asr.call_args_list[0].args[0] == media
    if has_audio is None and error_type is IndexError:
        download.assert_called_once()
        assert probe.call_count == asr.call_count == 2
        assert asr.call_args_list[1].args[0].name == "audio.m4a"
        assert entries == words and source == "asr"
        assert fallback["status"] == "completed"
    else:
        download.assert_not_called()
        asr.assert_called_once()
        assert entries == [] and source is None
        assert fallback["status"] == "failed"
    assert not list(tmp_path.glob(".asr-*"))


@pytest.mark.parametrize("media_sections", [None, "## Transcript\n\n", "## Chapters\n\nNone.\n"])
@pytest.mark.parametrize("with_entries", [False, True], ids=["empty", "provenance"])
def test_markdown_transcript_note_occurs_once(media_sections, with_entries):
    note = "Local Whisper transcript: captions unavailable" if with_entries else "No transcript: no audio available."
    entries = [(0.0, 2.0, "words")] if with_entries else []
    markdown = server._build_yoink_md(
        {"title": "Example"}, "https://example.com/video", entries, [], 30, {},
        "2026-10-24", "Test", media_sections=media_sections, transcript_note=note)

    assert markdown.count(note) == 1
    in_header = with_entries or (media_sections and "## Transcript\n" not in media_sections)
    assert (f"**Transcript:** {note}" in markdown) == bool(in_header)
    if not in_header:
        assert note in markdown.split("## Transcript\n", 1)[1]


@pytest.mark.parametrize("outcome", ["completed", "empty", "failed"])
def test_caption_refusal_reason_survives_asr_outcome(monkeypatch, tmp_path, outcome):
    monkeypatch.setattr(server, "_reliability_model_status", lambda _model: {"cached": True})
    asr = Mock(return_value=[] if outcome == "empty" else [(0.0, 2.0, "words")])
    if outcome == "failed":
        asr.side_effect = RuntimeError("decoder failed")
    monkeypatch.setattr(reliability, "transcribe_media", asr)

    entries, source, fallback = server._resolve_video_transcript(
        [], tmp_path / "video.mp4", 60, captions_refused=True,
        settings={"whisper_model": "base"})

    asr.assert_called_once_with(
        tmp_path / "video.mp4", model_name="base", model_root=server.RELIABILITY_MODEL_ROOT)
    assert fallback["reason"] == "captions_refused"
    assert fallback["status"] == {"failed": "failed", "empty": "no_speech"}.get(outcome, "completed")
    assert source == ("asr" if outcome == "completed" else None)
    assert entries == ([(0.0, 2.0, "words")] if outcome == "completed" else [])


def test_chunk_asr_bounds_segments_before_source_timestamp_mapping(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_reliability_model_status", lambda _model: {"cached": True})
    monkeypatch.setattr(reliability, "transcribe_media", Mock(return_value=[
        (-1.0, 2.0, "opening"), (8.0, 12.0, "ending"), (11.0, 13.0, "outside"),
    ]))
    media = tmp_path / "video-chunk-002.mp4"
    entries, source, fallback = server._resolve_video_transcript(
        [], media, 7200, settings={"whisper_model": "base"},
        media_chunks=[(media, 1200.0, 10.0)])

    assert entries == [(1200.0, 1202.0, "opening"), (1208.0, 1210.0, "ending")]
    assert source == "asr"
    assert fallback["reason"] == "captions_unavailable"
    assert fallback["coverage"] == "sampled_sections"
    assert fallback["duration_seconds"] == 10.0


def test_transcribe_media_uses_cached_model_only(tmp_path, monkeypatch):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"media")
    seen = {}

    class FakeModel:
        def transcribe(self, path, **kwargs):
            seen["path"] = path
            seen["transcribe_kwargs"] = kwargs
            return iter([
                {"start": 0.0, "end": 1.25, "text": " hello "},
                {"start": 1.25, "end": 2.5, "text": ""},
                types.SimpleNamespace(start=2.5, end=4.0, text="world"),
            ]), {"language": "en"}

    def _fake_load(model_name, model_root, *, local_files_only=False):
        seen["load"] = (model_name, Path(model_root), local_files_only)
        return FakeModel()

    monkeypatch.setattr(reliability, "_load_model", _fake_load)
    entries = reliability.transcribe_media(
        media, model_name="tiny", model_root=tmp_path / "models")

    _assert(seen["load"][2] is True,
            f"fallback model load must be cache-only: {seen['load']}")
    _assert(entries == [(0.0, 1.25, "hello"), (2.5, 4.0, "world")],
            f"segment normalization failed: {entries}")
    _assert(seen["transcribe_kwargs"]["beam_size"] == 1,
            f"CPU fallback should use bounded decoding: {seen}")


def test_explicit_model_download_writes_readiness_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(reliability, "_load_model",
                        lambda *_args, **_kwargs: object())
    result = reliability.ensure_model("tiny", tmp_path)
    marker = tmp_path / "tiny.pt"
    _assert(marker.is_file(),
            "successful explicit download must leave the marker server checks")
    _assert(result.get("ready_marker") == str(marker),
            f"download response must identify the marker: {result}")


def test_failed_model_download_never_writes_readiness_marker(
        tmp_path, monkeypatch):
    def _fail(*_args, **_kwargs):
        raise RuntimeError("download failed")

    monkeypatch.setattr(reliability, "_load_model", _fail)
    try:
        reliability.ensure_model("tiny", tmp_path)
        raise AssertionError("failed model load must propagate")
    except RuntimeError:
        pass
    _assert(not (tmp_path / "tiny.pt").exists(),
            "failed download must not leave a false ready marker")


def _fake_no_caption_subprocess(cmd, **_kwargs):
    """Mock yt-dlp + ffmpeg. It emits media and a screenshot, never an SRT."""
    parts = [str(part) for part in cmd]
    if Path(parts[0]).stem == "ffprobe":
        return subprocess.CompletedProcess(cmd, 0, b'{"streams": [{"index": 1}]}', b"")
    is_ffmpeg = parts and parts[0].endswith("ffmpeg")
    out = None
    if "-o" in parts:
        out = parts[parts.index("-o") + 1]
    elif is_ffmpeg:
        out = parts[-1]
    if is_ffmpeg and out:
        shot = Path(out.replace("%04d", "0001"))
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"\xff\xd8\xff\xe0jpg")
    elif out:
        base_dir = Path(out).parent
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp4")
    return types.SimpleNamespace(returncode=0, stdout="", stderr=b"")


@pytest.mark.parametrize("audio_case", ["embedded", "video_only", "download_failed", "silent_source"])
def test_captionless_x_capture_persists_asr_and_provenance(
        monkeypatch, tmp_path, audio_case):
    root = tmp_path / "corpus"
    root.mkdir()
    idx = index_mod.Index.open(tmp_path / "index.db")
    calls = []
    downloads = []
    probes = []

    def fake_run(cmd, **kwargs):
        if Path(cmd[0]).stem == "ffprobe":
            probes.append(Path(cmd[-1]))
            assert probes[-1].is_file()
            assert cmd[cmd.index("-select_streams") + 1] == "a"
            assert kwargs["check"] is True
            has_audio = (audio_case == "embedded" or
                         (Path(cmd[-1]).name == "audio.m4a" and audio_case == "video_only"))
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps({"streams": [{"index": 1}] if has_audio else []}), b"")
        if "bestaudio/best" in cmd:
            downloads.append((cmd, kwargs))
            if audio_case == "download_failed":
                raise subprocess.CalledProcessError(1, cmd, stderr=b"audio unavailable")
            path = Path(cmd[cmd.index("-o") + 1].replace("%(ext)s", "m4a"))
            path.write_bytes(b"audio")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return _fake_no_caption_subprocess(cmd, **kwargs)

    try:
        monkeypatch.setattr(server, "DESKTOP_ROOT", root)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_run_subprocess", fake_run)
        monkeypatch.setattr(server, "_download_thumbnail",
                            lambda *_args, **_kwargs: None)
        monkeypatch.setattr(server, "_fetch_channel_context",
                            lambda *_args, **_kwargs: {})
        monkeypatch.setattr(server, "_start_comments_thread",
                            lambda *_args, **_kwargs: None)
        monkeypatch.setattr(server, "_start_entity_extraction_thread",
                            lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            server, "_read_settings",
            lambda: {
                "asr_fallback_enabled": True,
                "whisper_model": "tiny",
                "transcript_reliability_auto_check": False,
            },
        )
        monkeypatch.setattr(
            server, "_reliability_model_status",
            lambda _model=None: {"model": "tiny", "cached": True},
        )

        def _asr(media_path, **kwargs):
            calls.append((Path(media_path), kwargs))
            return [
                (0.0, 2.0, "x video words"),
                (2.0, 4.0, "now queryable locally"),
            ]

        monkeypatch.setattr(reliability, "transcribe_media", _asr,
                            raising=False)

        url = "https://x.com/replayryan/status/1812345678901234567"
        metadata = {
            "id": "1812345678901234567",
            "title": "Captionless X clip",
            "description": "an X video without platform captions",
            "uploader": "ReplayRyan",
            "duration": 60,
            "thumbnails": [],
            "webpage_url": url,
        }
        folder = root / "AI" / "captionless-x-clip"
        result = server._run_extraction(
            url, 30, folder, notify=False, metadata=metadata,
            generate_paste=False)

        sidecar = json.loads(
            (folder / f"{folder.name}.json").read_text(encoding="utf-8"))
        assert result["ok"] is True
        assert len(downloads) == (0 if audio_case == "embedded" else 1)
        assert len(probes) == (1 if audio_case in {"embedded", "download_failed"} else 2)
        assert not list(folder.glob(".asr-*")), "temporary audio must be removed"
        if downloads:
            assert downloads[0][0][-1] == url
            assert Path(downloads[0][0][downloads[0][0].index("-o") + 1]).parent.parent == folder
        if audio_case in {"download_failed", "silent_source"}:
            assert not calls
            assert result["transcript_source"] is None
            assert sidecar["transcript_source"] is None
            assert sidecar["transcript"] == []
            assert sidecar["asr_fallback"]["status"] == "no_audio"
            assert "audio stream" in sidecar["asr_fallback"]["reason"]
            assert sidecar["asr_fallback"]["caption_reason"] == "captions_unavailable"
            assert not (folder / "transcript.txt").exists()
            for markdown in (result["yoink_md"], (folder / f"{folder.name}.md").read_text(encoding="utf-8")):
                assert markdown.count(sidecar["transcript_note"]) == 1
                transcript_section = markdown.split("## Transcript\n", 1)[1].split("\n## ", 1)[0]
                assert sidecar["transcript_note"] in transcript_section
                assert "No transcript:" in transcript_section
                assert "No captions available for this video." not in transcript_section
            return
        assert len(calls) == 1
        assert calls[0][0].name == ("video.mp4" if audio_case == "embedded" else "audio.m4a")
        assert sidecar["media_depth"]["provenance"]["transcript_source"]["kind"] == "local_asr"
        _assert(result["ok"] is True and calls,
                f"X fallback did not run: result={result}, calls={calls}")
        _assert(sidecar.get("transcript_source") == "asr",
                f"sidecar provenance missing: {sidecar}")
        _assert(sidecar.get("asr_fallback", {}).get("status") == "completed",
                f"sidecar fallback status missing: {sidecar}")
        _assert(sidecar["asr_fallback"]["reason"] == "captions_unavailable",
                f"sidecar fallback reason missing: {sidecar}")
        _assert(sidecar["transcript_note"] == "Local Whisper transcript: captions unavailable",
                f"X capture must not claim a YouTube refusal: {sidecar}")
        _assert(len(sidecar.get("transcript") or []) == 2,
                f"ASR segments not persisted: {sidecar.get('transcript')}")
        _assert("x video words" in (
            folder / "transcript.txt").read_text(encoding="utf-8"),
            "plain transcript did not use ASR output")
        _assert("x video words" in (
            folder / f"{folder.name}.md").read_text(encoding="utf-8"),
            "corpus markdown did not use ASR output")
        _assert(sidecar["transcript_note"] in (
            folder / f"{folder.name}.md").read_text(encoding="utf-8"),
            "corpus publication lost the ASR provenance note")
        _assert(result.get("transcript_source") == "asr",
                f"caller response lacks provenance: {result}")
    finally:
        idx.close()


def test_dashboard_exposes_opt_out_and_compute_copy():
    html = (Path(__file__).resolve().parent.parent
            / "assets" / "dashboard" / "index.html").read_text(
                encoding="utf-8")
    for needle in (
        'id="asrFallbackEnabled"',
        "asr_fallback_enabled",
        "10–15 minutes per hour",
        "Runs locally",
        "captions are missing",
    ):
        _assert(needle in html, f"dashboard ASR disclosure missing: {needle}")
