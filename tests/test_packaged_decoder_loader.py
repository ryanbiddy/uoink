"""Regression coverage for the installed native decoder boundary."""
import importlib.util
from pathlib import Path
import sys

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "whisper_runner.py"
DLLS = ("avcodec-61.dll", "avdevice-61.dll", "avfilter-10.dll",
        "avformat-61.dll", "avutil-59.dll", "swresample-5.dll", "swscale-8.dll")


def load_at(tmp_path, monkeypatch, complete=True):
    app = tmp_path / "application"
    native = app / "bin" / "torchcodec"
    native.mkdir(parents=True)
    for name in DLLS if complete else DLLS[:-1]:
        (native / name).write_bytes(b"fixture; never loaded")
    module_path = app / "whisper_runner.py"
    module_path.write_bytes(SOURCE.read_bytes())
    spec = importlib.util.spec_from_file_location("decoder_loader_probe", module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(sys, "platform", "win32")
    return module, spec, native


def test_import_registers_only_app_directory_and_retains_handle(tmp_path, monkeypatch):
    module, spec, native = load_at(tmp_path, monkeypatch)
    calls = []
    handle = object()
    monkeypatch.setattr("os.add_dll_directory", lambda path: calls.append(path) or handle, raising=False)
    monkeypatch.chdir(tmp_path)
    spec.loader.exec_module(module)
    assert calls == [str(native)]
    assert module._PACKAGED_DECODER_DLL_HANDLE is handle


def test_incomplete_installed_runtime_fails_before_registration(tmp_path, monkeypatch):
    module, spec, native = load_at(tmp_path, monkeypatch, complete=False)
    calls = []
    monkeypatch.setattr("os.add_dll_directory", lambda path: calls.append(path), raising=False)
    with pytest.raises(RuntimeError, match="Missing or redirected.*swscale-8"):
        spec.loader.exec_module(module)
    assert calls == []


def test_redirected_dll_is_rejected(tmp_path, monkeypatch):
    module, spec, native = load_at(tmp_path, monkeypatch)
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        if path.name == "avcodec-61.dll":
            return tmp_path / "outside.dll"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(RuntimeError, match="Missing or redirected.*avcodec-61"):
        spec.loader.exec_module(module)
