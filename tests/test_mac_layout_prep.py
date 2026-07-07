"""cc/mac-prep: lock the cross-platform installed-layout / bundled-interpreter
helpers that gate the ambient tray + first-run splash.

These helpers previously hard-coded ``python\\pythonw.exe``, so on any
non-Windows layout the tray + splash were silently dead. The gate is now
platform-aware. This test proves:

  * Windows behaviour is unchanged (pythonw.exe -> installed; nothing -> dev).
  * A macOS ``.app`` layout (python/bin/python3) is recognised as installed.
  * The darwin/linux branch can NEVER match on a Windows install, so the
    change is Windows-behaviour-identical.

Pure unit test -- no server boot, no network, no subprocess spawn. Runtime
verification of the actual tray/splash on macOS still needs a Mac (see
docs/MAC-BUILD-PLAN.md).

Run: python -m pytest tests/test_mac_layout_prep.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


def _mk(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stub", encoding="utf-8")


def test_windows_installed_layout(monkeypatch, tmp_path):
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "HERE", tmp_path)
    _mk(tmp_path / "python" / "pythonw.exe")
    _mk(tmp_path / "python" / "python.exe")
    assert server._is_installed_layout() is True
    assert server._bundled_interpreter(gui=True) == tmp_path / "python" / "pythonw.exe"
    assert server._bundled_interpreter(gui=False) == tmp_path / "python" / "python.exe"


def test_windows_dev_checkout_has_no_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "HERE", tmp_path)
    assert server._is_installed_layout() is False
    assert server._bundled_interpreter(gui=True) is None


def test_macos_app_bundle_layout(monkeypatch, tmp_path):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server, "HERE", tmp_path)
    _mk(tmp_path / "python" / "bin" / "python3")
    assert server._is_installed_layout() is True
    # gui flag is ignored off Windows -- a .app child has no console to flash.
    assert server._bundled_interpreter(gui=True) == tmp_path / "python" / "bin" / "python3"
    assert server._bundled_interpreter(gui=False) == tmp_path / "python" / "bin" / "python3"


def test_macos_dev_checkout_has_no_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server, "HERE", tmp_path)
    assert server._is_installed_layout() is False


def test_windows_never_matches_posix_bundle(monkeypatch, tmp_path):
    """A stray python/bin/python3 on a Windows box must NOT count as installed
    -- this is what makes the darwin branch Windows-behaviour-identical."""
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "HERE", tmp_path)
    _mk(tmp_path / "python" / "bin" / "python3")
    assert server._is_installed_layout() is False
    assert server._bundled_interpreter(gui=True) is None
