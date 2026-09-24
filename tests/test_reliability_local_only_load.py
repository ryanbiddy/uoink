"""Ordinary reliability loads stay local-only; ensure_model is acquisition.

Fake WhisperModel constructors record keyword arguments. No real model
bytes, runtime, or network. Run: python tests/test_reliability_local_only_load.py
"""
from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uoink_reliability as rel  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


class _FakeModel:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs
        _FakeModel.calls.append({"name": name, **kwargs})

    def transcribe(self, *_args, **_kwargs):
        return [], {"language": "en"}


def _audio(directory: Path) -> Path:
    path = directory / "clip.wav"
    path.write_bytes(b"not real audio; never decoded")
    return path


def test_load_model_default_is_local_only():
    params = inspect.signature(rel._load_model).parameters
    _assert(params["local_files_only"].default is True,
            "ordinary _load_model must default local_files_only to True")
    _FakeModel.calls = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "models"
        with patch.object(rel, "_import_faster_whisper", return_value=_FakeModel):
            rel._load_model("tiny", root)
    _assert(len(_FakeModel.calls) == 1, _FakeModel.calls)
    _assert(_FakeModel.calls[0]["local_files_only"] is True,
            f"default constructor must be local-only: {_FakeModel.calls}")
    _assert(not root.exists(), "ordinary load must not create a download root")
    print("ok  _load_model defaults to local_files_only=True")


def test_detect_unreliable_spans_does_not_enable_download():
    _FakeModel.calls = []
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        audio = _audio(directory)
        root = directory / "models"
        with patch.object(rel, "_import_faster_whisper", return_value=_FakeModel):
            spans = rel.detect_unreliable_spans(
                "ignored transcript", audio, model_name="tiny", model_root=root)
    _assert(spans == [], f"empty fake stream: {spans}")
    _assert(_FakeModel.calls[0]["local_files_only"] is True,
            f"detect_unreliable_spans must not acquire: {_FakeModel.calls}")
    _assert(not root.exists(), "span detection must not create the cache root")
    print("ok  detect_unreliable_spans is local-only")


def test_transcribe_media_stays_local_only():
    _FakeModel.calls = []
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        media = _audio(directory)
        root = directory / "models"
        with patch.object(rel, "_import_faster_whisper", return_value=_FakeModel):
            entries = rel.transcribe_media(
                media, model_name="base", model_root=root)
    _assert(entries == [], entries)
    _assert(_FakeModel.calls[0]["local_files_only"] is True,
            f"transcribe_media must stay cache-only: {_FakeModel.calls}")
    print("ok  transcribe_media is local-only")


def test_ensure_model_is_the_explicit_acquisition_path():
    _FakeModel.calls = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "models"
        with patch.object(rel, "_import_faster_whisper", return_value=_FakeModel):
            result = rel.ensure_model("small", root)
        marker = root / "small.pt"
        _assert(root.is_dir(), "explicit acquisition may create the download root")
        _assert(marker.is_file(), f"consent marker missing: {result}")
        _assert(result["ready_marker"] == str(marker), result)
    _assert(_FakeModel.calls[0]["local_files_only"] is False,
            f"ensure_model must request acquisition: {_FakeModel.calls}")
    print("ok  ensure_model is the explicit download path")


def test_stale_marker_ordinary_path_still_refuses_download():
    _FakeModel.calls = []
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "models"
        root.mkdir()
        (root / "tiny.pt").write_text(
            "Uoink faster-whisper model ready\n", encoding="utf-8")
        audio = _audio(Path(raw))
        with patch.object(rel, "_import_faster_whisper", return_value=_FakeModel):
            rel.detect_unreliable_spans("t", audio, model_root=root)
    _assert(_FakeModel.calls[0]["local_files_only"] is True,
            f"stale marker must not enable download: {_FakeModel.calls}")
    print("ok  stale marker does not enable ordinary acquisition")


def main() -> int:
    test_load_model_default_is_local_only()
    test_detect_unreliable_spans_does_not_enable_download()
    test_transcribe_media_stays_local_only()
    test_ensure_model_is_the_explicit_acquisition_path()
    test_stale_marker_ordinary_path_still_refuses_download()
    print("\nall green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
