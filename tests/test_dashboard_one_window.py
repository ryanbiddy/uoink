"""One dashboard window on Windows (3.18.1).

A second launch hands off to the open window and exits; every failure of the
handoff opens a window exactly as before. Mocks cover each failure path; the
pipe and mutex tests at the bottom use the real Win32 calls (no window).
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import uuid
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

import uoink_dashboard as dash
import uoink_install_isolation as iso

WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Win32 pipe and mutex")


class FakeEvent:
    def __init__(self, is_set: bool = False) -> None:
        self._event = threading.Event()
        if is_set:
            self._event.set()
        self.handlers = []

    def wait(self, timeout=None):
        return self._event.wait(timeout)

    def set(self):
        self._event.set()
        for handler in self.handlers:
            handler()

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeWindow:
    """Records pywebview calls. Touching .native (WinForms objects) from the
    listener thread is what the earlier attempt got wrong, so it fails here."""

    def __init__(self, shown: bool = True, show_delay: float = 0.0, show_error=None) -> None:
        self.events = SimpleNamespace(shown=FakeEvent(shown), maximized=FakeEvent(),
                                      restored=FakeEvent())
        self.calls = []
        self.threads = set()
        self.show_delay = show_delay
        self.show_error = show_error

    @property
    def native(self):
        raise AssertionError("the listener touched the native window")

    def _record(self, *call):
        self.threads.add(threading.current_thread().name)
        self.calls.append(call)

    def show(self):
        if self.show_delay:
            time.sleep(self.show_delay)
        if self.show_error:
            raise self.show_error
        self._record("show")

    def restore(self):
        self._record("restore")

    def maximize(self):
        self._record("maximize")

    def load_url(self, url):
        self._record("load_url", url)


class FakeApi:
    """Client side of the handoff, all Win32 replaced."""

    def __init__(self, **overrides) -> None:
        self.sid = "S-1-5-21-1000-2000-3000-1001"
        self.session = 1
        self.mutex_result = (101, True)
        self.pipe = 201
        self.pid = 4242
        self.reply = json.dumps({"ok": True, "hwnd": 777}).encode()
        self.hwnd_pid = {777: 4242}
        self.foregrounds = [777]
        self.iconic = False
        self.send_error = None
        self.calls = []
        self.__dict__.update(overrides)

    def user_sid(self):
        return self.sid

    def session_id(self):
        return self.session

    def create_mutex(self, name):
        self.calls.append(("mutex", name))
        if isinstance(self.mutex_result, Exception):
            raise self.mutex_result
        return self.mutex_result

    def connect(self, pipe, wait_s):
        self.calls.append(("connect", pipe, wait_s))
        return self.pipe

    def server_pid(self, handle):
        return self.pid

    def allow_foreground(self, pid):
        self.calls.append(("allow", pid))
        return True

    def send(self, handle, data, timeout_s=2.0):
        if self.send_error:
            raise self.send_error
        self.calls.append(("send", json.loads(data.decode())))

    def recv(self, handle, timeout_s):
        self.calls.append(("recv", timeout_s))
        return self.reply

    def window_pid(self, hwnd):
        return self.hwnd_pid.get(hwnd, 0)

    def foreground(self):
        return self.foregrounds.pop(0) if len(self.foregrounds) > 1 else self.foregrounds[0]

    def is_iconic(self, hwnd):
        return self.iconic

    def close(self, handle):
        self.calls.append(("close", handle))


def _run_main(monkeypatch, api_factory, argv=(), platform="win32"):
    webview = ModuleType("webview")
    window = FakeWindow()
    webview.create_window = Mock(return_value=window)
    webview.start = Mock()
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(dash.sys, "platform", platform)
    monkeypatch.setattr(dash.sys, "argv", ["uoink_dashboard.py", *argv])
    monkeypatch.setattr(dash, "_Win32", api_factory)
    monkeypatch.setattr(dash, "_brand_windows_icon_when_ready", lambda: None)
    monkeypatch.setattr(dash, "_FOREGROUND_WAIT_S", 0.05)
    monkeypatch.setattr(dash.time, "sleep", lambda _s: None)
    served = Mock()
    monkeypatch.setattr(dash._FocusServer, "start", served)
    opened = Mock()
    monkeypatch.setattr(dash.webbrowser, "open", opened)
    rc = dash.main()
    return SimpleNamespace(rc=rc, webview=webview, window=window, served=served, browser=opened)


def _opened_a_window(result):
    assert result.rc == 0
    result.webview.create_window.assert_called_once()
    result.webview.start.assert_called_once()
    result.browser.assert_not_called()


# ---- second launch ---------------------------------------------------------

def test_second_launch_hands_off_and_exits_without_a_window(monkeypatch):
    api = FakeApi()
    result = _run_main(monkeypatch, lambda: api)
    assert result.rc == 0
    result.webview.create_window.assert_not_called()
    result.webview.start.assert_not_called()
    names = [c for c in api.calls if c[0] == "mutex"]
    assert names and names[0][1].startswith("Local\\Uoink-Dashboard-")
    connect = next(c for c in api.calls if c[0] == "connect")
    assert connect[1] == "\\\\.\\pipe\\" + names[0][1][len("Local\\"):]
    assert connect[2] == dash._HANDOFF_WAIT_S  # a window that is still starting gets time
    kinds = [c[0] for c in api.calls]
    # The launching process grants the foreground before it asks.
    assert kinds.index("allow") < kinds.index("send")
    assert ("allow", 4242) in api.calls
    send = next(c for c in api.calls if c[0] == "send")[1]
    assert send == {"uoink": "dashboard-focus", "v": 1, "url": None}
    assert ("close", 201) in api.calls and ("close", 101) in api.calls


def test_second_launch_passes_a_deep_link(monkeypatch):
    api = FakeApi()
    link = dash._dashboard_url() + "#item/example-1"
    result = _run_main(monkeypatch, lambda: api, argv=[link])
    result.webview.create_window.assert_not_called()
    assert next(c for c in api.calls if c[0] == "send")[1]["url"] == link


def test_handoff_waits_for_the_window_to_come_forward(monkeypatch):
    api = FakeApi(foregrounds=[1, 1, 777])
    result = _run_main(monkeypatch, lambda: api)
    result.webview.create_window.assert_not_called()


def test_first_launch_does_not_wait_and_serves_its_window(monkeypatch):
    api = FakeApi(mutex_result=(101, False), pipe=None)
    result = _run_main(monkeypatch, lambda: api)
    _opened_a_window(result)
    assert next(c for c in api.calls if c[0] == "connect")[2] == 0.0
    result.served.assert_called_once()
    assert ("close", 101) in api.calls  # released when the window closes


# ---- every failure opens a window as before -------------------------------

def _broken_factory():
    raise OSError("ctypes unavailable")


FAILURES = {
    "win32 binding fails": dict(factory=_broken_factory),
    "mutex call raises": dict(api=dict(mutex_result=OSError("CreateMutexW failed"), pipe=None)),
    "mutex not created": dict(api=dict(mutex_result=(None, False), pipe=None)),
    "stale mutex, no listener": dict(api=dict(pipe=None)),
    "no server pid": dict(api=dict(pid=None)),
    "send fails": dict(api=dict(send_error=OSError(232, "pipe closing"))),
    "no reply in time": dict(api=dict(reply=None)),
    "garbled reply": dict(api=dict(reply=b"\xff not json")),
    "refused reply": dict(api=dict(reply=b'{"ok": false}')),
    "reply without window": dict(api=dict(reply=b'{"ok": true}')),
    "bool window handle": dict(api=dict(reply=b'{"ok": true, "hwnd": true}')),
    "string window handle": dict(api=dict(reply=b'{"ok": true, "hwnd": "777"}')),
    "window of another process": dict(api=dict(hwnd_pid={777: 9999})),
    "windows refuses foreground": dict(api=dict(foregrounds=[555])),
    "window stays minimized": dict(api=dict(iconic=True)),
}


@pytest.mark.parametrize("case", list(FAILURES), ids=list(FAILURES))
def test_any_handoff_failure_opens_a_window(monkeypatch, case):
    spec = FAILURES[case]
    api = FakeApi(**spec.get("api", {}))
    factory = spec.get("factory") or (lambda: api)
    result = _run_main(monkeypatch, factory)
    _opened_a_window(result)
    if "factory" not in spec:
        # The fallback window serves later launches too, so a failed handoff
        # never leaves a window that nobody can bring forward.
        result.served.assert_called_once()
        if api.pipe:
            assert ("close", api.pipe) in api.calls


def test_pywebview_missing_still_opens_the_browser(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)
    monkeypatch.setattr(dash.sys, "platform", "win32")
    monkeypatch.setattr(dash, "_Win32", Mock(side_effect=AssertionError("no handoff without a window")))
    opened = Mock()
    monkeypatch.setattr(dash.webbrowser, "open", opened)
    assert dash.main() == 0
    opened.assert_called_once()


def test_linux_keeps_its_current_behavior(monkeypatch):
    result = _run_main(monkeypatch, Mock(side_effect=AssertionError("Windows only")), platform="linux")
    _opened_a_window(result)
    result.served.assert_not_called()


# ---- scope ----------------------------------------------------------------

def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port if port != 5179 else _free_port()


def test_names_are_scoped_to_user_session_and_profile(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    port = _free_port()
    user = FakeApi()
    with iso.bound_isolation(profile=a, port=port):
        first = dash._instance_name(user)
        assert dash._instance_name(FakeApi()) == first
        assert dash._instance_name(FakeApi(sid="S-1-5-21-1000-2000-3000-1002")) != first
        assert dash._instance_name(FakeApi(session=2)) != first
    with iso.bound_isolation(profile=b, port=port):
        assert dash._instance_name(user) != first
    with iso.bound_isolation(profile=a, port=_free_port()):
        assert dash._instance_name(user) != first


# ---- the open window's listener --------------------------------------------

def _server(window=None, **api):
    return dash._FocusServer(FakeApi(**api), "Uoink-Dashboard-test", window or FakeWindow())


def _request(url=None):
    return json.dumps({"uoink": "dashboard-focus", "v": 1, "url": url}).encode()


def test_listener_restores_a_minimized_window_and_brings_it_forward(monkeypatch):
    server = _server()
    monkeypatch.setattr(server.api, "find_window", lambda pid, title: 777, raising=False)
    server.api.iconic = True
    reply = json.loads(server.answer(_request()))
    assert reply == {"ok": True, "hwnd": 777}
    assert server.window.calls == [("restore",), ("show",)]


def test_listener_returns_a_maximized_window_to_maximized(monkeypatch):
    window = FakeWindow()
    server = _server(window)
    monkeypatch.setattr(server.api, "find_window", lambda pid, title: 777, raising=False)
    window.events.maximized.set()
    server.api.iconic = True
    server.answer(_request())
    assert window.calls == [("maximize",), ("show",)]
    window.events.restored.set()
    window.calls.clear()
    server.answer(_request())
    assert window.calls == [("restore",), ("show",)]


def test_listener_leaves_a_normal_window_size_alone_and_opens_a_deep_link(monkeypatch):
    server = _server()
    monkeypatch.setattr(server.api, "find_window", lambda pid, title: 777, raising=False)
    link = dash._dashboard_url() + "#item/example-1"
    server.answer(_request(link))
    assert server.window.calls == [("show",), ("load_url", link)]


@pytest.mark.parametrize("url", [
    "https://example.com/dashboard",
    "http://127.0.0.1:1/dashboard",
    "javascript:alert(1)",
    "{base}x",
    "{base}#\nitem",
    "{base}#" + "a" * 5000,
    42,
], ids=["other-site", "other-port", "script", "lookalike-path", "control-char", "too-long", "not-text"])
def test_listener_only_opens_its_own_dashboard_address(monkeypatch, url):
    server = _server()
    monkeypatch.setattr(server.api, "find_window", lambda pid, title: 777, raising=False)
    if isinstance(url, str):
        url = url.replace("{base}", dash._dashboard_url())
    assert json.loads(server.answer(_request(url)))["ok"] is True
    assert server.window.calls == [("show",)]


@pytest.mark.parametrize("raw", [None, b"", b"not json", b"[]", b'{"uoink": "other"}', b"\xff"])
def test_listener_refuses_requests_it_does_not_understand(monkeypatch, raw):
    server = _server()
    monkeypatch.setattr(server.api, "find_window", lambda pid, title: 777, raising=False)
    assert server.answer(raw) == dash._FAILED
    assert server.window.calls == []


def test_listener_reports_failure_when_the_window_is_gone_or_closing(monkeypatch):
    server = _server()
    monkeypatch.setattr(server.api, "find_window", lambda pid, title: None, raising=False)
    assert server.answer(_request()) == dash._FAILED
    closing = _server(FakeWindow(show_error=RuntimeError("window closing")))
    monkeypatch.setattr(closing.api, "find_window", lambda pid, title: 777, raising=False)
    assert closing.answer(_request()) == dash._FAILED


def test_listener_waits_for_the_window_before_serving():
    window = FakeWindow(shown=False)
    server = _server(window)
    server.api.create_server = Mock(side_effect=AssertionError("served before the window existed"))
    thread = server.start()
    time.sleep(0.2)
    server.stop.set()
    thread.join(2)
    assert not thread.is_alive()
    server.api.create_server.assert_not_called()


def test_listener_stops_quietly_when_the_pipe_cannot_be_made():
    server = _server()
    server.api.create_server = Mock(side_effect=OSError(5, "access denied"))
    server.run()
    server.api.create_server.assert_called_once()


def test_listener_does_not_spin_on_repeated_failures(monkeypatch):
    monkeypatch.setattr(dash.time, "sleep", lambda _s: None)
    server = _server()
    server.api.create_server = Mock(return_value=301)
    server.api.accept = Mock(return_value=False)
    server.run()
    assert server.api.accept.call_count == 50


# ---- real pipe and mutex (no window) ---------------------------------------

class RealPipeApi(dash._Win32 if sys.platform == "win32" else object):
    """Real pipe I/O; only the window queries are stand-ins."""

    def __init__(self):
        super().__init__()
        self.allowed = []

    def find_window(self, pid, title):
        return 777 if pid == os.getpid() and title == "Uoink" else None

    def window_pid(self, hwnd):
        return os.getpid() if hwnd == 777 else 0

    def is_iconic(self, hwnd):
        return False

    def foreground(self):
        return 777

    def allow_foreground(self, pid):
        self.allowed.append(pid)
        return True


def _unique_name():
    return "Uoink-Dashboard-test-" + uuid.uuid4().hex


@WIN_ONLY
def test_real_pipe_round_trip_brings_the_window_forward():
    api = RealPipeApi()
    name = _unique_name()
    window = FakeWindow()
    server = dash._FocusServer(api, name, window)
    thread = server.start()
    try:
        link = dash._dashboard_url() + "#item/example-2"
        assert dash._hand_off(api, name, link, 3.0) is True
        assert api.allowed == [os.getpid()]
        assert window.calls == [("show",), ("load_url", link)]
        # Calls reach the window from the listener thread only through pywebview.
        assert window.threads == {"uoink-dashboard-focus"}
        assert dash._hand_off(api, name, None, 3.0) is True  # serves again
    finally:
        server.stop.set()
        thread.join(3)
    assert not thread.is_alive()


@WIN_ONLY
def test_real_pipe_without_a_listener_fails_fast():
    api = RealPipeApi()
    started = time.monotonic()
    assert dash._hand_off(api, _unique_name(), None, 0.0) is False
    assert time.monotonic() - started < 1.0


@WIN_ONLY
def test_real_pipe_hung_window_times_out_and_falls_back(monkeypatch):
    monkeypatch.setattr(dash, "_REPLY_WAIT_S", 0.3)
    api = RealPipeApi()
    name = _unique_name()
    server = dash._FocusServer(api, name, FakeWindow(show_delay=1.5))
    thread = server.start()
    try:
        started = time.monotonic()
        assert dash._hand_off(api, name, None, 3.0) is False
        assert time.monotonic() - started < 1.4
    finally:
        server.stop.set()
        thread.join(5)


@WIN_ONLY
def test_real_mutex_reports_an_open_window_and_leaves_nothing_stale():
    api = dash._Win32()
    name = "Local\\" + _unique_name()
    first, existed = api.create_mutex(name)
    assert first and existed is False
    second, existed = api.create_mutex(name)
    assert second and existed is True
    api.close(second)
    api.close(first)
    # Once every handle is gone (a closed or crashed window), the name is free.
    third, existed = api.create_mutex(name)
    assert third and existed is False
    api.close(third)


@WIN_ONLY
def test_real_identity_is_available():
    api = dash._Win32()
    assert api.user_sid().startswith("S-1-")
    assert api.session_id() >= 0
    assert dash._instance_name(api).startswith("Uoink-Dashboard-")
