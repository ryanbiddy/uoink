"""Lean Linux podcast contracts, without a model, torch, or network access."""
import json
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import _platform
import server
import uoink_mcp_tools
import uoink_reliability
import whisper_runner as runner


@pytest.mark.parametrize("platform", ["linux", "linux2", "win32", "darwin"])
@pytest.mark.parametrize("whisperx", [False, True])
@pytest.mark.parametrize("faster", [False, True])
@pytest.mark.parametrize("media", [False, True])
def test_engine_selection(monkeypatch, platform, whisperx, faster, media):
    monkeypatch.setattr(runner, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(runner, "_WHISPERX_AVAILABLE", whisperx)
    probes = []

    def capability():
        probes.append("media")
        return {"available": media}

    def find_spec(name):
        assert name == "faster_whisper"
        probes.append(name)
        return object() if faster else None

    monkeypatch.setattr(_platform, "media_capability", capability)
    monkeypatch.setattr(runner.importlib.util, "find_spec", find_spec)
    expected = ("whisperx" if whisperx else "faster-whisper"
                if platform.startswith("linux") and faster and media else None)
    assert runner.transcription_engine() == expected
    assert runner.is_transcription_available() is (expected is not None)
    if whisperx or not platform.startswith("linux"):
        assert probes == []
    elif not media:
        assert "faster_whisper" not in probes


@pytest.fixture
def lean_linux(monkeypatch):
    monkeypatch.setattr(runner, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(runner, "_WHISPERX_AVAILABLE", False)
    monkeypatch.setattr(runner.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(_platform, "media_capability", lambda: {
        "available": True, "code": None, "reason": None})


@pytest.mark.parametrize("platform", ["linux", "win32", "darwin"])
def test_server_refuses_without_engine(lean_linux, monkeypatch, tmp_path, platform):
    monkeypatch.setattr(runner, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: None)
    monkeypatch.setattr(runner.importlib.util, "find_spec", lambda name: None)
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"placeholder; never decoded")
    monkeypatch.setattr(server, "_get_index", lambda: None)
    monkeypatch.setattr(server, "_jobs", {})
    monkeypatch.setattr(server.podcasts, "get_episode", lambda *args: {
        "audio_local_path": str(audio)})
    monkeypatch.setattr(runner, "is_model_downloaded", lambda *args:
                        pytest.fail("Model consent must follow engine admission"))
    payload, status = server._queue_podcast_transcription(1)
    assert status == 503
    assert payload["ok"] is False
    assert payload["whisperx_available"] is False
    assert payload["transcription_engine"] is None
    backend = object.__new__(server._ServerCaptureBackend)
    outcome = backend.preflight({
        "legacy_episode_id": 1,
        "metadata_json": json.dumps({"audio_url": "https://example.com/episode.mp3"}),
    }, {"kind": "podcast_rss"})
    assert outcome.code == "missing_transcription_setup"


def test_linux_fallback_passes_admission_and_preserves_consent(
        lean_linux, monkeypatch, tmp_path):
    audio = tmp_path / "episode.mp3"
    audio.touch()
    monkeypatch.setattr(server, "_get_index", lambda: None)
    monkeypatch.setattr(server, "_jobs", {})
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server.podcasts, "get_episode", lambda *args: {
        "audio_local_path": str(audio)})
    monkeypatch.setattr(runner, "is_model_downloaded", lambda *args: False)
    payload, status = server._queue_podcast_transcription(1)
    assert status == 412 and payload["consent_required"] is True
    monkeypatch.setattr(runner, "is_model_downloaded", lambda *args: True)
    backend = object.__new__(server._ServerCaptureBackend)
    assert backend.preflight({
        "legacy_episode_id": 1,
        "metadata_json": json.dumps({"audio_url": "https://example.com/episode.mp3"}),
    }, {"kind": "podcast_rss"}) is None


def test_linux_status_reports_engine_without_claiming_whisperx(lean_linux, monkeypatch):
    monkeypatch.setattr(uoink_mcp_tools, "_b", lambda: server)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    payload = uoink_mcp_tools.get_whisperx_status({})
    assert payload["whisperx_available"] is False
    assert payload["transcription_engine"] == "faster-whisper"
    assert payload["media_capability"]["available"] is True


def cached_snapshot(data_root):
    repo = runner._model_repo_root(data_root, "base")
    snapshot = repo / "snapshots" / ("a" * 40)
    snapshot.mkdir(parents=True)
    (repo / "refs").mkdir()
    (repo / "refs/main").write_text("a" * 40, encoding="ascii")
    for name in runner._ASR_CACHE_FILES:
        (snapshot / name).write_bytes(b"placeholder; never loaded")
    return snapshot


@pytest.mark.parametrize("source", ["bundled", "cached", "consented"])
@pytest.mark.parametrize("diarize", [False, True])
def test_faster_whisper_transcript_uses_resolved_snapshot(
        lean_linux, monkeypatch, tmp_path, caplog, source, diarize):
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"placeholder; never decoded")
    data = tmp_path / "data"
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for name in runner._ASR_CACHE_FILES:
        (bundle / name).write_bytes(b"placeholder; never loaded")
    monkeypatch.setattr(runner, "_bundled_snapshot", lambda size:
                        None if source == "consented" else bundle)
    # Even when a different bundled model exists, a user's snapshot wins.
    monkeypatch.setattr(uoink_reliability, "bundled_model_root", lambda: tmp_path / "absent")
    expected = cached_snapshot(data) if source == "cached" else bundle
    downloads = []

    def download(model, cache):
        nonlocal expected
        downloads.append((model, cache))
        expected = cached_snapshot(data)
        return expected

    monkeypatch.setattr(runner, "_download_model_snapshot", download)
    constructed = []
    language = "fr" if diarize else None

    class FakeModel:
        def __init__(self, path, **kwargs):
            constructed.append(path)
            assert path == str(expected)
            assert kwargs == {"device": "cpu", "compute_type": "int8", "local_files_only": True}

        def transcribe(self, path, **kwargs):
            assert path == str(audio)
            assert kwargs == {"beam_size": 1, "best_of": 1, "vad_filter": True,
                              **({"language": language} if language else {})}
            return iter([SimpleNamespace(start=0.0, end=1.5, text=" Bonjour. ")]), SimpleNamespace(
                language="fr", language_probability=0.99)

    monkeypatch.setattr(uoink_reliability, "_import_faster_whisper", lambda: FakeModel)
    with caplog.at_level(logging.WARNING):
        result = runner.transcribe_audio(
            audio, data_root=data, model_size="BASE", language=language,
            diarize=diarize, consent_given=source == "consented")
    assert constructed == [str(expected)]
    assert len(downloads) == (1 if source == "consented" else 0)
    assert result == {
        "model": "base", "language": "fr", "diarization_ran": False,
        "segments": [{"start": 0.0, "end": 1.5, "text": "Bonjour."}],
        "generated_at": result["generated_at"], "engine": "faster-whisper",
    }
    assert datetime.fromisoformat(result["generated_at"].replace("Z", "+00:00"))
    assert ("install.sh --with-whisperx" in caplog.text) is diarize
    assert "diarization_run" not in result and "diarization_run_id" not in result
    if source == "bundled":
        assert not data.exists()


def test_fallback_refuses_unconsented_download(lean_linux, monkeypatch, tmp_path):
    audio = tmp_path / "episode.mp3"
    audio.touch()
    monkeypatch.setattr(runner, "_bundled_snapshot", lambda size: None)
    monkeypatch.setattr(runner, "_download_model_snapshot", lambda *args:
                        pytest.fail("Unconsented model download"))
    monkeypatch.setattr(uoink_reliability, "_import_faster_whisper", lambda:
                        pytest.fail("Runtime loaded before model consent"))
    with pytest.raises(PermissionError, match="explicit download consent"):
        runner.transcribe_audio(audio, data_root=tmp_path / "data")
    assert not (tmp_path / "data").exists()
