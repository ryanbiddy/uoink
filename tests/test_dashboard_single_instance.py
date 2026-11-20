from unittest.mock import Mock
import sys
from types import SimpleNamespace

import pytest

import uoink_dashboard as dashboard


@pytest.mark.parametrize("minimized", [True, False])
def test_focus_restores_only_minimized_windows(monkeypatch, minimized):
    import ctypes
    user32 = Mock()
    user32.IsIconic.return_value = minimized
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    window = Mock()
    window.native.Handle.ToInt64.return_value = 23
    dashboard._focus_dashboard(window)
    assert window.restore.called == minimized
    user32.SetForegroundWindow.assert_called_once_with(23)


def test_second_windows_launch_only_signals(monkeypatch):
    kernel = Mock()
    kernel.CreateEventW.return_value = 17
    monkeypatch.setattr(dashboard.sys, "platform", "win32")
    monkeypatch.setattr(dashboard, "_focus_event_api", lambda: (kernel, lambda: 183), raising=False)
    webview = Mock()
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(dashboard, "_brand_windows_icon_when_ready", lambda: None)
    assert dashboard.main() == 0
    kernel.SetEvent.assert_called_once_with(17)
    kernel.CloseHandle.assert_called_once_with(17)
    webview.create_window.assert_not_called()
    webview.start.assert_not_called()


def test_primary_window_handles_focus_request(monkeypatch):
    kernel = Mock()
    kernel.CreateEventW.return_value = 17
    monkeypatch.setattr(dashboard.sys, "platform", "win32")
    monkeypatch.setattr(dashboard, "_focus_event_api", lambda: (kernel, lambda: 0), raising=False)
    webview = Mock()
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(dashboard, "_brand_windows_icon_when_ready", lambda: None)
    focus = Mock()
    monkeypatch.setattr(dashboard, "_focus_dashboard", focus, raising=False)
    # Drive the callback synchronously. No threads interact with a real HWND.
    kernel.WaitForSingleObject.side_effect = [0, 0xFFFFFFFF]
    webview.start.side_effect = lambda callback, args: callback(*args)
    assert dashboard.main() == 0
    focus.assert_called_once_with(webview.create_window.return_value)
    kernel.CloseHandle.assert_called_once_with(17)
