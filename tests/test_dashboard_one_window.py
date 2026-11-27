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
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

import uoink_dashboard as dash
import uoink_install_isolation as iso

WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Win32 pipe and mutex")


@pytest.fixture(autouse=True)
def no_clr(monkeypatch):
    monkeypatch.setitem(sys.modules, "System", SimpleNamespace(Action=lambda callback: callback))


class FakeWindow:
    """Model WinForms' dispatch boundary without loading a GUI backend."""

    def __init__(self, shown=True, show_delay=0, show_error=None):
        self.events = SimpleNamespace(shown=threading.Event(), loaded=threading.Event())
        if shown:
            self.events.shown.set()
        self.events.loaded.set()
        self.calls = []
        self.queued = []
        self.gui_threads = []
        self.show_delay = show_delay
        self.show_error = show_error
        self.hwnd = 777
        self.route_result = "true"
        self.native = SimpleNamespace(BeginInvoke=self.post, Handle=SimpleNamespace(ToInt64=self.handle),
                                      webview=SimpleNamespace(CoreWebView2=SimpleNamespace(
                                          ExecuteScriptAsync=self.script)))

    def handle(self):
        assert threading.current_thread().name == "mock-winforms"
        if self.show_error:
            raise self.show_error
        self.calls.append("handle")
        return self.hwnd

    def script(self, script):
        assert threading.current_thread().name == "mock-winforms"
        self.calls.append(script)
        return SimpleNamespace(Wait=lambda timeout: True, Result=self.route_result)

    def post(self, callback):
        if self.show_delay:
            self.queued.append(callback)
        else:
            thread = threading.Thread(target=callback, name="mock-winforms")
            self.gui_threads.append(thread)
            thread.start()

    def drain_gui(self):
        self.show_delay = 0
        for callback in self.queued:
            self.post(callback)
        for thread in self.gui_threads:
            thread.join(2)


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

    def user_sid(self, process=None):
        return self.sid if process is None else getattr(self, 'peer_sid', self.sid)

    def session_id(self, pid=None):
        return self.session if pid is None else getattr(self, "peer_session", self.session)

    def open_process(self, pid):
        return 301

    def image_path(self, process=None):
        return sys.executable if process is None else getattr(self, "peer_image", sys.executable)

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

    def activate(self, hwnd):
        assert threading.current_thread().name == "mock-winforms"
        self.calls.append(("activate", hwnd))

    def foreground(self):
        return self.foregrounds.pop(0) if len(self.foregrounds) > 1 else self.foregrounds[0]

    def is_iconic(self, hwnd):
        return self.iconic

    def close(self, handle):
        self.calls.append(("close", handle))


def _run_main(monkeypatch, api_factory, argv=(), platform="win32", broken=None):
    webview = ModuleType("webview")
    window = FakeWindow()
    webview.create_window = Mock(return_value=window)
    webview.start = Mock()
    if broken:
        getattr(webview, broken).side_effect = RuntimeError("backend failed")
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
    assert time.monotonic() < send.pop("expires") <= time.monotonic() + dash._REPLY_WAIT_S
    assert send == {"uoink": "dashboard-focus", "v": 2, "url": None}
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
    assert not any(c[0] == "connect" for c in api.calls)
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
    if case.startswith("mutex"):
        result.served.assert_not_called()
        assert not any(c[0] == "connect" for c in api.calls)
    elif "factory" not in spec:
        # The fallback window serves later launches too, so a failed handoff
        # never leaves a window that nobody can bring forward.
        result.served.assert_called_once()
        if api.pipe:
            assert ("close", api.pipe) in api.calls


@pytest.mark.parametrize("mismatch", [
    {"peer_sid": "S-1-5-18"}, {"peer_session": 9},
    {"peer_image": str(Path(sys.executable).parent / "other.exe")},
    {"peer_image": str(Path(sys.executable).parent / "elsewhere" / "python.exe")},
])
def test_identity_mismatch_opens_locally_before_grant_or_send(monkeypatch, mismatch):
    api = FakeApi(**mismatch)
    result = _run_main(monkeypatch, lambda: api, argv=[dash._dashboard_url() + "#activity"])
    _opened_a_window(result)
    assert not any(c[0] in ("allow", "send") for c in api.calls)


@pytest.mark.parametrize("method", ["open_process", "image_path", "user_sid", "session_id"])
def test_failed_peer_query_never_grants_or_sends(monkeypatch, method):
    api = FakeApi()
    original = getattr(api, method)

    def failure(*args):
        if args:
            raise OSError("query denied")
        return original()

    monkeypatch.setattr(api, method, failure)
    _opened_a_window(_run_main(monkeypatch, lambda: api))
    assert not any(c[0] in ("allow", "send") for c in api.calls)


def test_sibling_console_and_gui_interpreters_can_hand_off(monkeypatch, tmp_path):
    api = FakeApi()
    monkeypatch.setattr(api, "image_path", lambda process=None:
                        str(tmp_path / ("pythonw.exe" if process else "python.exe")))
    result = _run_main(monkeypatch, lambda: api)
    result.webview.create_window.assert_not_called()
    assert ("allow", api.pid) in api.calls


@pytest.mark.parametrize("broken", ["create_window", "start"])
def test_webview_failure_releases_mutex_and_opens_original_url(monkeypatch, broken):
    api = FakeApi(mutex_result=(101, False))
    link = dash._dashboard_url() + "#settings"
    result = _run_main(monkeypatch, lambda: api, argv=[link], broken=broken)
    result.browser.assert_called_once_with(link)
    assert ("close", 101) in api.calls


def test_long_valid_target_opens_intact_without_a_handoff(monkeypatch):
    link = dash._dashboard_url() + "#item/" + "a" * dash._MAX_URL
    api = FakeApi()
    result = _run_main(monkeypatch, lambda: api, argv=[link])
    _opened_a_window(result)
    assert result.webview.create_window.call_args.args[1] == link
    assert not any(c[0] in ("connect", "allow", "send") for c in api.calls)


def test_startup_only_accepts_the_dashboard_document(monkeypatch):
    base = dash._dashboard_url()
    monkeypatch.setattr(dash.sys, "argv", ["dashboard", base + "/qrcode.js"])
    assert dash._target_url() == base


def test_startup_and_handoff_compare_the_parsed_origin(monkeypatch):
    base = "http://127.0.0.1:18123/dashboard"
    monkeypatch.setattr(dash, "_dashboard_url", lambda: base)
    same = base.replace(":18123", ":018123") + "#settings"
    monkeypatch.setattr(dash.sys, "argv", ["dashboard", same])
    assert dash._allowed_url(same) and dash._target_url() == same
    for invalid in [base.replace("://", "://user@"), base.replace(":18123", ":bad"), base.replace("http:", "https:")]:
        assert not dash._allowed_url(invalid)


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
    return json.dumps({"uoink": "dashboard-focus", "v": 2, "url": url,
                       "expires": time.monotonic() + dash._REPLY_WAIT_S}).encode()


@WIN_ONLY
@pytest.mark.parametrize("minimized", [False, True])
def test_native_restore_uses_window_placement_only_when_minimized(minimized):
    api = dash._Win32()
    user32 = Mock()
    user32.IsIconic.return_value = minimized
    api._u = user32
    api.activate(777)
    if minimized:
        user32.ShowWindow.assert_called_once_with(777, 9)
    else:
        user32.ShowWindow.assert_not_called()
    user32.SetForegroundWindow.assert_called_once_with(777)


def test_listener_opens_deep_link_on_gui_thread_and_checks_router_reply():
    server = _server()
    link = dash._dashboard_url() + "#item/example-1"
    assert json.loads(server.answer(_request(link))) == {"ok": True, "hwnd": 777}
    assert server.api.calls == [("activate", 777)]
    assert "uoinkOpenDashboardLink(" + json.dumps(link) in server.window.calls[1]
    server.window.route_result = "false"
    assert server.answer(_request(link)) == dash._FAILED


@pytest.mark.parametrize("url", [
    "https://example.com/dashboard",
    "http://127.0.0.1:1/dashboard",
    "javascript:alert(1)",
    "{base}x", "{base}/qrcode.js",
    "{base}#\nitem",
    "{base}#" + "a" * 5000,
    42,
], ids=["other-site", "other-port", "script", "lookalike-path", "subresource", "control-char", "too-long", "not-text"])
def test_listener_only_opens_its_own_dashboard_address(url):
    server = _server()
    if isinstance(url, str):
        url = url.replace("{base}", dash._dashboard_url())
    assert json.loads(server.answer(_request(url)))["ok"] is False
    assert server.window.calls == []


@pytest.mark.parametrize("raw", [None, b"", b"not json", b"[]", b'{"uoink": "other"}', b"\xff"])
def test_listener_refuses_requests_it_does_not_understand(raw):
    server = _server()
    assert server.answer(raw) == dash._FAILED
    assert server.window.calls == []


def test_listener_reports_failure_when_the_window_is_gone_or_closing():
    server = _server()
    server.window.hwnd = 0
    assert server.answer(_request()) == dash._FAILED
    closing = _server(FakeWindow(show_error=RuntimeError("window closing")))
    assert closing.answer(_request()) == dash._FAILED


def test_listener_backs_off_on_consecutive_accept_errors():
    server = _server()
    server.api.create_server = Mock(return_value=301)
    server.api.accept = Mock(side_effect=OSError("accept unavailable"))
    server.api.disconnect = Mock()
    server.stop.wait = Mock(side_effect=[False, False, True])
    server.run()
    delays = [call.args[0] for call in server.stop.wait.call_args_list]
    assert len(delays) == 3 and 0 < delays[0] < delays[1] < delays[2]
    assert ("close", 301) in server.api.calls


@WIN_ONLY
def test_listener_waits_for_the_window_before_serving():
    api = RealPipeApi()
    window = FakeWindow(shown=False)
    name = _unique_name()
    server = dash._FocusServer(api, name, window)
    waited = threading.Event()
    original_wait = window.events.shown.wait

    def wait(timeout):
        result = original_wait(timeout)
        if not result:
            waited.set()
        return result

    window.events.shown.wait = wait
    thread = server.start()
    try:
        assert waited.wait(2)
        assert not dash._hand_off(api, name, None, 0)
        window.events.shown.set()
        assert dash._hand_off(api, name, None, 2)
    finally:
        server.stop.set()
        thread.join(3)


@WIN_ONLY
def test_real_listener_recovers_after_one_create_failure(monkeypatch):
    api = RealPipeApi()
    name = _unique_name()
    create = api.create_server
    calls = []
    def transient(pipe):
        calls.append(pipe)
        if len(calls) == 1:
            raise OSError("temporarily unavailable")
        return create(pipe)
    monkeypatch.setattr(api, "create_server", transient)
    server = dash._FocusServer(api, name, FakeWindow())
    thread = server.start()
    try:
        assert dash._hand_off(api, name, None, 2)
        assert dash._hand_off(api, name, None, 2)
        assert len(calls) == 2  # the same successful pipe serves both requests
    finally:
        server.stop.set()
        thread.join(3)


# ---- real pipe# ---- real pipe and mutex (no window) ---------------------------------------

class RealPipeApi(dash._Win32 if sys.platform == "win32" else object):
    """Real pipe I/O; only the window queries are stand-ins."""

    def __init__(self):
        super().__init__()
        self.allowed = []
        self.activations = []

    def activate(self, hwnd):
        assert threading.current_thread().name == "mock-winforms"
        self.activations.append(hwnd)

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
        assert api.activations == [777]
        assert "uoinkOpenDashboardLink(" + json.dumps(link) in window.calls[1]
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
    window = FakeWindow(show_delay=1.5)
    server = dash._FocusServer(api, name, window)
    thread = server.start()
    try:
        started = time.monotonic()
        assert dash._hand_off(api, name, dash._dashboard_url() + '#activity', 3.0) is False
        assert time.monotonic() - started < 1.4
        assert len(window.queued) == 1
        time.sleep(0.1)  # The GUI resumes after the client has already fallen back.
        window.drain_gui()
        assert window.calls == [] and api.activations == []
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
def test_candidate_probe_only_observes_live_presence_mutex(monkeypatch):
    name = _unique_name()
    monkeypatch.setattr(dash, "_instance_name", lambda _: name)
    assert not dash.has_window_candidate()
    one = dash._OneWindow.claim(dash._dashboard_url())
    try:
        assert one.mutex and dash.has_window_candidate()
    finally:
        one.release()
    assert not dash.has_window_candidate()


@WIN_ONLY
def test_real_identity_is_available():
    api = dash._Win32()
    assert api.user_sid().startswith("S-1-")
    assert api.session_id() >= 0
    assert dash._instance_name(api).startswith("Uoink-Dashboard-")


@WIN_ONLY
def test_pipe_security_flags(monkeypatch):
    api = RealPipeApi()
    pipe = "\\\\.\\pipe\\" + _unique_name()
    create = Mock(wraps=api._k.CreateNamedPipeW)
    connect = Mock(wraps=api._w.CreateFile)
    monkeypatch.setattr(api._k, "CreateNamedPipeW", create)
    monkeypatch.setattr(api._w, "CreateFile", connect)
    server = api.create_server(pipe)
    try:
        client = api.connect(pipe, 0)
        assert client
        api.close(client)
        assert connect.call_args.args[5] & 0x001F0000 == 0x00110000  # SQOS + identification
        create.assert_called_once()
        assert create.call_args.args[1] & 0x00080000  # FILE_FLAG_FIRST_PIPE_INSTANCE
    finally:
        api.close(server)


@WIN_ONLY
def test_kernel_pipe_descriptor_contains_only_the_current_user():
    import ctypes
    from ctypes import wintypes as wt
    api = RealPipeApi()
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    ptr = ctypes.c_void_p
    security.GetKernelObjectSecurity.argtypes = [wt.HANDLE, wt.DWORD, ptr, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    security.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ptr, wt.DWORD, wt.DWORD, ctypes.POINTER(ptr), ctypes.POINTER(wt.DWORD)]
    server = api.create_server("\\\\.\\pipe\\" + _unique_name())
    try:
        size = wt.DWORD()
        security.GetKernelObjectSecurity(server, 4, None, 0, ctypes.byref(size))
        descriptor = ctypes.create_string_buffer(size.value)
        assert security.GetKernelObjectSecurity(server, 4, descriptor, size, ctypes.byref(size))
        sddl = ptr()
        assert security.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, 4, ctypes.byref(sddl), None)
        try:
            assert ctypes.wstring_at(sddl.value) == f"D:P(A;;FA;;;{api.user_sid()})"
        finally:
            api._k.LocalFree(sddl)
    finally:
        api.close(server)


@WIN_ONLY
def test_pipe_dacl_grants_only_current_user_and_denies_guest_read():
    # Inspect the kernel object's installed DACL, including effective rights
    # for the local Guest SID. No second login or credentials are needed.
    security = pytest.importorskip("win32security")
    api = RealPipeApi()
    server = api.create_server("\\\\.\\pipe\\" + _unique_name())
    try:
        sd = security.GetSecurityInfo(server, security.SE_KERNEL_OBJECT, security.DACL_SECURITY_INFORMATION)
        acl = sd.GetSecurityDescriptorDacl()
        assert acl.GetAceCount() == 1
        (kind, _), mask, trustee = acl.GetAce(0)
        assert kind == security.ACCESS_ALLOWED_ACE_TYPE and mask & 1
        assert security.ConvertSidToStringSid(trustee) == api.user_sid()
        policy = security.LsaOpenPolicy(None, security.POLICY_VIEW_LOCAL_INFORMATION)
        try:
            domain = security.LsaQueryInformationPolicy(policy, security.PolicyAccountDomainInformation)
        finally:
            security.LsaClose(policy)
        guest = security.ConvertStringSidToSid(security.ConvertSidToStringSid(domain[1]) + "-501")
        rights = acl.GetEffectiveRightsFromAcl({"TrusteeForm": security.TRUSTEE_IS_SID,
                                                "TrusteeType": security.TRUSTEE_IS_USER,
                                                "Identifier": guest})
        assert rights & 1 == 0  # FILE_READ_DATA
    finally:
        api.close(server)


@WIN_ONLY
def test_permanent_listener_failure_releases_live_windows_mutex(monkeypatch):
    api = RealPipeApi()
    name = _unique_name()
    monkeypatch.setattr(dash, "_instance_name", lambda _: name)
    one = dash._OneWindow.claim(dash._dashboard_url(), lambda: api)
    monkeypatch.setattr(api, "create_server", Mock(side_effect=OSError("unavailable")))
    try:
        one.serve(FakeWindow())
        deadline = time.monotonic() + 6
        while one.mutex and time.monotonic() < deadline:
            time.sleep(0.01)
        assert one.mutex is None
        assert 1 < api.create_server.call_count <= 10
        monkeypatch.setattr(api, "connect", Mock(side_effect=AssertionError("stale listener")))
        next_launch = dash._OneWindow.claim(dash._dashboard_url(), lambda: api)
        try:
            assert next_launch.mutex and not next_launch.handed_off
            api.connect.assert_not_called()
        finally:
            next_launch.release()
    finally:
        one.release()


@WIN_ONLY
def test_waiting_client_does_not_keep_a_dead_listener_discoverable(monkeypatch):
    name = _unique_name()
    monkeypatch.setattr(dash, "_instance_name", lambda _: name)
    target = dash._dashboard_url()
    primary = dash._OneWindow.claim(target)
    waiting, resume = threading.Event(), threading.Event()
    client_api, next_api = RealPipeApi(), RealPipeApi()

    def blocked_connect(pipe, timeout):
        waiting.set()
        resume.wait(2)
        return None

    monkeypatch.setattr(client_api, "connect", blocked_connect)
    monkeypatch.setattr(next_api, "connect", Mock(return_value=None))
    def second_launch():
        dash._OneWindow.claim(target, lambda: client_api).release()

    thread = threading.Thread(target=second_launch)
    thread.start()
    try:
        assert waiting.wait(2)
        primary.release()
        third = dash._OneWindow.claim(target, lambda: next_api)
        try:
            next_api.connect.assert_not_called()
            assert third.mutex and not third.handed_off
        finally:
            third.release()
    finally:
        resume.set()
        thread.join(3)
        primary.release()


@WIN_ONLY
def test_fallback_window_answers_third_launch_after_original_closes(monkeypatch):
    api = RealPipeApi()
    name = _unique_name()
    monkeypatch.setattr(dash, "_instance_name", lambda _: name)
    monkeypatch.setattr(dash, "_HANDOFF_WAIT_S", 2)
    target = dash._dashboard_url()
    first = dash._OneWindow.claim(target, lambda: api)
    first.serve(FakeWindow(show_error=RuntimeError("closing")))
    fallback = dash._OneWindow.claim(target, lambda: api)
    window = FakeWindow()
    try:
        assert not fallback.handed_off
        fallback.serve(window)
        first.release()
        third = dash._OneWindow.claim(target + "#settings", lambda: api)
        try:
            assert third.handed_off
            assert window.calls[0] == "handle" and "#settings" in window.calls[1]
        finally:
            third.release()
    finally:
        first.release()
        fallback.release()
