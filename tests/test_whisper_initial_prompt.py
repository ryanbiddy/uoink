"""Whisper gets a short titles-only vocabulary hint. Models are mocked; no audio is decoded."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import _platform
import server
import uoink_reliability as rel
import whisper_runner as runner


def test_prompt_is_titles_only_deduped_plain_and_capped():
    assert rel.build_initial_prompt("Mars Rovers Weekly", "Why rovers die on Mars") == \
        "Mars Rovers Weekly. Why rovers die on Mars"
    assert rel.build_initial_prompt("Same", "same", None, "  ") == "Same"
    assert rel.build_initial_prompt(None, "", "  ") is None
    assert rel.build_initial_prompt("Bell\x07 ring\n  tone") == "Bell ring tone"
    long = rel.build_initial_prompt("Feed", " ".join(["word"] * 100))
    assert len(long) <= rel.INITIAL_PROMPT_MAX_CHARS and not long.endswith(" ")


def test_transcribe_media_hands_the_prompt_to_the_model(tmp_path, monkeypatch):
    seen = []

    class Model:
        def transcribe(self, path, **kwargs):
            seen.append(kwargs)
            return [], SimpleNamespace(language="en", language_probability=1.0)

    monkeypatch.setattr(rel, "_load_model", lambda *a, **k: Model())
    media = tmp_path / "a.wav"
    media.write_bytes(b"x")
    rel.transcribe_media(media, initial_prompt="Rovers Weekly")
    rel.transcribe_media(media)
    assert seen[0]["initial_prompt"] == "Rovers Weekly"
    assert "initial_prompt" not in seen[1]


def _runner_ready(monkeypatch, tmp_path, engine):
    monkeypatch.setattr(_platform, "require_media", lambda: None)
    monkeypatch.setattr(runner, "transcription_engine", lambda: engine)
    monkeypatch.setattr(runner, "_prepare_model_snapshot", lambda *a, **k: tmp_path)
    monkeypatch.setattr(runner, "_bundled_snapshot", lambda size: tmp_path)
    audio = tmp_path / "ep.mp3"
    audio.write_bytes(b"x")
    return audio


def test_faster_whisper_engine_passes_the_prompt(tmp_path, monkeypatch):
    audio = _runner_ready(monkeypatch, tmp_path, "faster-whisper")
    calls = []
    monkeypatch.setattr(rel, "transcribe_media", lambda *a, **k: calls.append(k) or [])
    runner.transcribe_audio(audio, data_root=tmp_path, initial_prompt="Rovers Weekly")
    assert calls[0]["initial_prompt"] == "Rovers Weekly"


def test_whisperx_engine_passes_the_prompt_as_an_asr_option(tmp_path, monkeypatch):
    audio = _runner_ready(monkeypatch, tmp_path, "whisperx")
    monkeypatch.setattr(runner, "_WHISPERX_AVAILABLE", True)
    monkeypatch.setattr(runner, "_runtime_device", lambda: "cpu")
    monkeypatch.setattr(runner, "sys", SimpleNamespace(platform="linux"))
    loads = []

    class Model:
        def transcribe(self, audio_input, language=None):
            return {"segments": [], "language": "en"}

    fake = SimpleNamespace(load_model=lambda *a, **k: loads.append(k) or Model())
    monkeypatch.setitem(sys.modules, "whisperx", fake)
    runner.transcribe_audio(audio, data_root=tmp_path, initial_prompt="Rovers Weekly")
    runner.transcribe_audio(audio, data_root=tmp_path)
    assert loads[0]["asr_options"] == {"initial_prompt": "Rovers Weekly"}
    assert "asr_options" not in loads[1]


def test_podcast_job_builds_the_prompt_from_feed_and_episode_titles(monkeypatch):
    monkeypatch.setattr(server, "_get_index", lambda: object())
    monkeypatch.setattr(server.podcasts, "get_episode_with_feed", lambda idx, eid: {
        "podcast_title": "Rovers Weekly", "title": "Why rovers die", "audio_local_path": "/secret/path.mp3"})
    assert server._podcast_initial_prompt(7) == "Rovers Weekly. Why rovers die"
    monkeypatch.setattr(server.podcasts, "get_episode_with_feed", lambda idx, eid: 1 / 0)
    assert server._podcast_initial_prompt(7) is None


def test_podcast_worker_passes_the_prompt_to_transcribe_audio():
    source = Path(server.__file__).read_text(encoding="utf-8")
    call = source.split("transcript = whisper_runner.transcribe_audio(", 1)[1].split(")\n", 1)[0]
    assert "initial_prompt=vocabulary_hint" in call and "_podcast_initial_prompt(episode_id)" in source


def test_youtube_whisper_fallback_passes_channel_and_title(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_reliability_model_status", lambda name: {"cached": True})
    monkeypatch.setattr(server, "_download_reliability_audio", lambda url, tmp: tmp_path / "a.wav")
    calls = []

    def fake(audio, **kwargs):
        calls.append(kwargs)
        return [(0.0, 1.0, "hi")]

    monkeypatch.setattr(server.uoink_reliability, "transcribe_media", fake)
    server._whisper_transcript("https://youtu.be/x", settings={}, title="Rover Teardown", channel="Space Bench")
    server._whisper_transcript("https://youtu.be/x", settings={})
    assert calls[0]["initial_prompt"] == "Space Bench. Rover Teardown"
    assert "initial_prompt" not in calls[1]


def test_youtube_capture_fallback_passes_the_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_reliability_model_status", lambda name: {"cached": True})
    monkeypatch.setattr(server, "_media_has_audio", lambda *a, **k: True)
    calls = []
    monkeypatch.setattr(server.uoink_reliability, "transcribe_media",
                        lambda path, **k: calls.append(k) or [(0.0, 1.0, "hi")])
    media = tmp_path / "v.mp4"
    media.write_bytes(b"x")
    entries, source, _ = server._resolve_video_transcript(
        [], media, 60, settings={"asr_fallback_enabled": True}, asr_titles=("Space Bench", "Rover Teardown"))
    assert source == "asr" and calls[0]["initial_prompt"] == "Space Bench. Rover Teardown"
