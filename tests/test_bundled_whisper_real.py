"""The staged bundled model loads by path, offline, and writes nothing.

Uses the real weights a build staged (installer/staging/models/whisper-bundled
after build.ps1), or the folder named by UOINK_BUNDLED_WHISPER_ROOT. Skips
when faster-whisper or a staged model is missing, so ordinary CI runs stay
offline and fast.

tests/fixtures has no speech recording, so the audio here is a generated
tone: this proves the CTranslate2 weights load from the bundle and the
decoder runs, not recognition quality.
"""
from __future__ import annotations

import math
import os
import struct
import wave
from pathlib import Path

import pytest

import uoink_reliability as rel

ROOT = Path(__file__).resolve().parents[1]


def staged_root() -> Path:
    configured = os.environ.get("UOINK_BUNDLED_WHISPER_ROOT")
    return Path(configured) if configured else ROOT / "installer" / "staging" / "models" / "whisper-bundled"


def tone(path: Path, seconds: float = 2.0) -> Path:
    rate = 16000
    frames = b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / rate)))
                      for i in range(int(rate * seconds)))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(frames)
    return path


def snapshot(root: Path) -> list[tuple[str, int, int]]:
    return sorted((p.relative_to(root).as_posix(), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in root.rglob("*"))


def test_staged_bundle_loads_offline_and_stays_read_only(tmp_path, monkeypatch):
    pytest.importorskip("faster_whisper")
    root = staged_root()
    info = rel.bundled_model_info(root)
    if info is None:
        pytest.skip(f"no staged bundled model under {root}; run build.ps1 first")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf-home-must-stay-empty"))
    monkeypatch.setattr(rel, "bundled_model_root", lambda: root)
    user_cache = tmp_path / "profile" / "models" / "whisper"
    status = rel.reliability_model_status(info["model"], user_cache)
    assert status["cached"] is True and status["source"] == "bundled", status
    before = snapshot(root)
    audio = tone(tmp_path / "tone.wav")

    model = rel._load_model(info["model"], user_cache)
    segments, _info = model.transcribe(str(audio), beam_size=1, vad_filter=False)
    list(segments)  # run the decoder; a tone has no words to check
    entries = rel.transcribe_media(audio, model_name=info["model"], model_root=user_cache)

    assert isinstance(entries, list)
    assert snapshot(root) == before, "loading must not write into the bundled model folder"
    assert not user_cache.exists(), "a bundled load must not create the user cache"
    assert not (tmp_path / "hf-home-must-stay-empty").exists(), "no Hugging Face cache use"
