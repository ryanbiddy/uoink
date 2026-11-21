import sys
from unittest.mock import Mock

import pytest
import uoink_dashboard as dashboard


@pytest.fixture
def windows(monkeypatch):
    kernel = Mock()
    kernel.CreateEventW.return_value = 17
    ui = Mock()
    ui.find.return_value = (23, 73)
    ui.foreground.return_value = 23
    ui.allow.return_value = True
    ui.iconic.return_value = False
    monkeypatch.setattr(dashboard.sys, "platform", "win32")
    monkeypatch.setattr(dashboard, "_focus_event_api", lambda: (kernel, lambda: 183))
    monkeypatch.setattr(dashboard, "_window_api", lambda: ui, raising=False)
    monkeypatch.setattr(dashboard, "_brand_windows_icon_when_ready", lambda: None)
    monkeypatch.setattr(dashboard.time, "sleep", lambda _: None)
    webview = Mock()
    monkeypatch.setitem(sys.modules, "webview", webview)
    return kernel, ui, webview


def test_second_windows_launch_only_signals(windows):
    kernel, ui, webview = windows
    assert dashboard.main() == 0
    ui.allow.assert_called_once_with(73)
    kernel.SetEvent.assert_called_once_with(17)
    assert kernel.CreateEventW.call_args.args[-1].startswith("Local\\")
    kernel.CloseHandle.assert_called_once_with(17)
    webview.create_window.assert_not_called()
    webview.start.assert_not_called()


@pytest.mark.parametrize("failure", ["create", "setup", "stale", "signal", "grant", "foreground"])
def test_failed_handoff_opens_dashboard(windows, failure):
    kernel, ui, webview = windows
    if failure == "create":
        kernel.CreateEventW.return_value = 0
    elif failure == "setup":
        kernel.CreateEventW.side_effect = OSError()
    elif failure == "stale":
        ui.find.return_value = None
    elif failure == "signal":
        kernel.SetEvent.return_value = False
    elif failure == "grant":
        ui.allow.return_value = False
    else:
        ui.foreground.return_value = 99
    assert dashboard.main() == 0
    webview.create_window.assert_called_once()
    webview.start.assert_called_once()


@pytest.mark.parametrize("minimized", [True, False])
def test_primary_window_handles_focus_on_ui_thread(windows, monkeypatch, minimized):
    kernel, ui, webview = windows
    monkeypatch.setattr(dashboard, "_focus_event_api", lambda: (kernel, lambda: 0))
    kernel.WaitForSingleObject.side_effect = [0, 0xFFFFFFFF]
    owner_thread = False
    window = webview.create_window.return_value

    def on_owner(form, action):
        nonlocal owner_thread
        owner_thread = True
        try:
            return action()
        finally:
            owner_thread = False

    def read_handle():
        assert owner_thread
        return 23

    window.native.Handle.ToInt64.side_effect = read_handle
    ui.iconic.return_value = minimized
    monkeypatch.setattr(dashboard, "_on_window_thread", on_owner, raising=False)
    webview.start.side_effect = lambda callback, args: callback(*args)
    assert dashboard.main() == 0
    assert ui.restore.called == minimized
    ui.focus.assert_called_once_with(23)
    kernel.CloseHandle.assert_called_once_with(17)
