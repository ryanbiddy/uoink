r"""uoink_dashboard.py -- pywebview dashboard window (Tier 2 GUI).

Subprocess entrypoint launched by the tray's left-click action. Standard
chrome (resizable, default decorations matching mock 3.2.1's title bar +
window controls), 1280x800, loads http://127.0.0.1:5179/dashboard.

Why a subprocess: pywebview's main loop must run on the GUI thread, and the
helper's main thread is already owning serve_forever(). Spawning a separate
process keeps both lifecycles independent -- closing the dashboard window
never touches the helper.

JsApi is intentionally small: Codex's dashboard HTML only feature-detects
window.pywebview.api, so the only call worth exposing today is open_url for
external links. Falls back to opening the URL in the default browser if
pywebview/WebView2 isn't available.

One window on Windows: every launch path (Start menu, tray, splash, helper)
runs this script, so a launch that finds a dashboard already open asks that
window to come to the front and exits instead of opening a second one. Any
failure in that handoff opens a window exactly as before.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

if sys.platform == "darwin":
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

log = logging.getLogger("uoink.dashboard")

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
import uoink_install_isolation as _install_isolation  # noqa: E402
_install_isolation.apply_from_process()

WIDTH, HEIGHT = 1280, 800
ICON_PATH = HERE / "uoink.ico"
_ICON_HANDLES = []


def _dashboard_url() -> str:
    return _install_isolation.helper_url("/dashboard")


def _target_url() -> str:
    bound = _dashboard_url()
    for candidate in sys.argv[1:]:
        if _allowed_url(candidate):
            return candidate
    return bound


class JsApi:
    """window.pywebview.api.* surface for the dashboard window. Today the
    dashboard HTML doesn't call into native; expose open_url for future
    external-link clicks so Codex's feature-detection has something to find."""

    def helper_recovery(self):
        import uoink_supervisor
        return uoink_supervisor.status()

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception as e:
            log.debug("open_url failed: %s", e)
        return True


class MacJsApi(JsApi):
    def copy_text(self, text):
        from helper.mac_ui import copy_text
        return copy_text(text)


def _apply_windows_icon_once() -> bool:
    """Best-effort pywebview title-bar icon branding on Windows.

    pywebview 5.x does not expose a create_window(icon=...) argument, so the
    dashboard otherwise inherits pythonw.exe's yellow/blue Python icon. Set the
    native HWND icons after the window exists so the dashboard title bar and
    taskbar carry the bundled Uoink mark.
    """
    if sys.platform != "win32" or not ICON_PATH.is_file():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        current_pid = os.getpid()
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE = 0x00000040

        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SendMessageW.restype = wintypes.LPARAM
        user32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

        big = user32.LoadImageW(None, str(ICON_PATH), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        small = user32.LoadImageW(None, str(ICON_PATH), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if not big and not small:
            return False
        _ICON_HANDLES.extend([handle for handle in (big, small) if handle])
        applied = False

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_window(hwnd, _lparam):
            nonlocal applied
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != current_pid or not user32.IsWindowVisible(hwnd):
                return True
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            if title.value != "Uoink":
                return True
            if small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small)
            if big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
            applied = True
            return True

        user32.EnumWindows(enum_window, 0)
        return applied
    except Exception as e:
        log.debug("dashboard icon branding failed: %s", e)
        return False


def _brand_windows_icon_when_ready() -> None:
    for _ in range(24):
        if _apply_windows_icon_once():
            return
        time.sleep(0.25)


# ---- one dashboard window (Windows) ----------------------------------------
#
# The first window holds a named mutex and, once pywebview reports it shown,
# serves a named pipe. A later launch that finds the mutex connects to the
# pipe, lets the window's process take the foreground, asks it to come to the
# front (and to open a deep link, if one was asked for) and exits only after it
# sees that window in front. Every failure along the way opens a window as
# before. Kernel objects die with their process, so a crash leaves nothing
# stale behind. Names hash the user's SID, the session, the helper address and
# the isolated profile, so an isolated install never sees the real one.

WINDOW_TITLE = "Uoink"
_HANDOFF_WAIT_S = 10.0  # a window that is still starting gets this long to get ready
_REPLY_WAIT_S = 5.0
_FOREGROUND_WAIT_S = 1.5
_MAX_MESSAGE = 8192
_MAX_URL = 4096
_FAILED = b'{"ok": false}'


def _requested_url(target_url: str) -> str | None:
    """The URL a launch asked for, or None when it only wants the dashboard."""
    return None if target_url == _dashboard_url() else target_url


def _allowed_url(url) -> bool:
    """Only this window's own dashboard address may be loaded through the pipe."""
    if not isinstance(url, str) or url != url.strip() or "\\" in url:
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return False
    try:
        target, bound = urlsplit(url), urlsplit(_dashboard_url())
        return (target.scheme == bound.scheme and target.hostname == bound.hostname
                and target.username is None and target.password is None
                and target.port == bound.port and target.path == bound.path == "/dashboard")
    except ValueError:
        return False


def _instance_name(api) -> str:
    binding = _install_isolation.current_binding()
    profile = os.path.normcase(str(binding.profile)) if binding is not None else "default-profile"
    scope = "|".join([api.user_sid(), str(api.session_id()), _dashboard_url(), profile])
    return "Uoink-Dashboard-" + hashlib.sha256(scope.encode("utf-8")).hexdigest()[:32]


class _Win32:
    """The few Win32 calls the one-window handoff needs, kept in one place so
    tests can replace them. Raises on import or binding failure; callers then
    open a window without the handoff."""

    ERROR_FILE_NOT_FOUND = 2
    ERROR_ALREADY_EXISTS = 183
    ERROR_IO_PENDING = 997
    WAIT_OBJECT_0 = 0
    SECURITY_IDENTIFICATION = 0x00010000
    SECURITY_SQOS_PRESENT = 0x00100000
    FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
    PIPE_REJECT_REMOTE_CLIENTS = 0x00000008

    def __init__(self) -> None:
        import ctypes
        import _winapi
        from ctypes import wintypes as wt

        self._ctypes, self._w, self._wt = ctypes, _winapi, wt
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        u = ctypes.WinDLL("user32", use_last_error=True)
        a = ctypes.WinDLL("advapi32", use_last_error=True)
        k.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
        k.CreateMutexW.restype = wt.HANDLE
        k.OpenMutexW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
        k.OpenMutexW.restype = wt.HANDLE
        k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k.OpenProcess.restype = wt.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        k.QueryFullProcessImageNameW.restype = wt.BOOL

        class SecurityAttributes(ctypes.Structure):
            _fields_ = [("length", wt.DWORD), ("descriptor", ctypes.c_void_p), ("inherit", wt.BOOL)]

        self._sa = SecurityAttributes
        a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wt.LPCWSTR, wt.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.DWORD)]
        a.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wt.BOOL
        k.CreateNamedPipeW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD,
                                       wt.DWORD, wt.DWORD, ctypes.POINTER(SecurityAttributes)]
        k.CreateNamedPipeW.restype = wt.HANDLE
        k.DisconnectNamedPipe.argtypes = [wt.HANDLE]
        k.DisconnectNamedPipe.restype = wt.BOOL
        u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        u.ShowWindow.restype = wt.BOOL
        u.SetForegroundWindow.argtypes = [wt.HWND]
        u.SetForegroundWindow.restype = wt.BOOL
        k.CloseHandle.argtypes = [wt.HANDLE]
        k.CloseHandle.restype = wt.BOOL
        k.GetNamedPipeServerProcessId.argtypes = [wt.HANDLE, ctypes.POINTER(wt.ULONG)]
        k.GetNamedPipeServerProcessId.restype = wt.BOOL
        k.ProcessIdToSessionId.argtypes = [wt.DWORD, ctypes.POINTER(wt.DWORD)]
        k.ProcessIdToSessionId.restype = wt.BOOL
        k.GetCurrentProcess.argtypes = []
        k.GetCurrentProcess.restype = wt.HANDLE
        k.LocalFree.argtypes = [ctypes.c_void_p]
        k.LocalFree.restype = ctypes.c_void_p
        a.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
        a.OpenProcessToken.restype = wt.BOOL
        a.GetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                          wt.DWORD, ctypes.POINTER(wt.DWORD)]
        a.GetTokenInformation.restype = wt.BOOL
        a.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        a.ConvertSidToStringSidW.restype = wt.BOOL
        u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        u.GetWindowThreadProcessId.restype = wt.DWORD
        u.IsIconic.argtypes = [wt.HWND]
        u.IsIconic.restype = wt.BOOL
        u.GetForegroundWindow.argtypes = []
        u.GetForegroundWindow.restype = wt.HWND
        u.AllowSetForegroundWindow.argtypes = [wt.DWORD]
        u.AllowSetForegroundWindow.restype = wt.BOOL
        self._k, self._u, self._a = k, u, a

    # identity
    def open_process(self, pid):
        handle = self._k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        return handle

    def image_path(self, process=None) -> str:
        size = self._wt.DWORD(32768)
        buf = self._ctypes.create_unicode_buffer(size.value)
        handle = process or self._k.GetCurrentProcess()
        if not self._k.QueryFullProcessImageNameW(handle, 0, buf, self._ctypes.byref(size)):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        return buf.value

    def user_sid(self, process=None) -> str:
        ctypes, wt = self._ctypes, self._wt
        token = wt.HANDLE()
        if not self._a.OpenProcessToken(process or self._k.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            size = wt.DWORD()
            self._a.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            buf = ctypes.create_string_buffer(size.value)
            if not self._a.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
            text = ctypes.c_void_p()
            if not self._a.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                return ctypes.wstring_at(text.value)
            finally:
                self._k.LocalFree(text)
        finally:
            self.close(token.value)

    def session_id(self, pid=None) -> int:
        session = self._wt.DWORD()
        if not self._k.ProcessIdToSessionId(os.getpid() if pid is None else pid, self._ctypes.byref(session)):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        return session.value

    # handles
    def has_mutex(self, name: str) -> bool:
        handle = self._k.OpenMutexW(0x00100000, False, name)  # SYNCHRONIZE
        if not handle:
            return False
        self.close(handle)
        return True

    def create_mutex(self, name: str):
        """(handle or None, True when another process already holds the name)."""
        self._ctypes.set_last_error(0)
        handle = self._k.CreateMutexW(None, False, name)
        existed = bool(handle) and self._ctypes.get_last_error() == self.ERROR_ALREADY_EXISTS
        return (handle or None), existed

    def close(self, handle) -> None:
        try:
            self._w.CloseHandle(handle)
        except OSError:
            pass

    # pipe, client side
    def connect(self, pipe: str, wait_s: float):
        w = self._w
        deadline = time.monotonic() + max(0.0, wait_s)
        while True:
            try:
                handle = w.CreateFile(pipe, w.GENERIC_READ | w.GENERIC_WRITE, 0, w.NULL,
                                      w.OPEN_EXISTING, w.FILE_FLAG_OVERLAPPED | self.SECURITY_SQOS_PRESENT
                                      | self.SECURITY_IDENTIFICATION, w.NULL)
                break
            except OSError as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                if exc.winerror == w.ERROR_PIPE_BUSY:
                    try:
                        w.WaitNamedPipe(pipe, max(1, min(500, int(remaining * 1000))))
                    except OSError:
                        time.sleep(min(0.1, remaining))
                elif exc.winerror == self.ERROR_FILE_NOT_FOUND:
                    time.sleep(min(0.1, remaining))
                else:
                    return None
        try:
            w.SetNamedPipeHandleState(handle, w.PIPE_READMODE_MESSAGE, None, None)
        except OSError:
            self.close(handle)
            return None
        return handle

    def server_pid(self, handle):
        pid = self._wt.ULONG()
        if self._k.GetNamedPipeServerProcessId(handle, self._ctypes.byref(pid)):
            return int(pid.value) or None
        return None

    # pipe, both sides
    def _finish(self, ov, err, timeout_s: float):
        if err == self.ERROR_IO_PENDING:
            if self._w.WaitForSingleObject(ov.event, max(1, int(timeout_s * 1000))) != self.WAIT_OBJECT_0:
                ov.cancel()
        return ov.GetOverlappedResult(True)

    def send(self, handle, data: bytes, timeout_s: float = 2.0) -> None:
        ov, err = self._w.WriteFile(handle, data, overlapped=True)
        written, err = self._finish(ov, err, timeout_s)
        if err or written != len(data):
            raise OSError(err or 0, "pipe write incomplete")

    def recv(self, handle, timeout_s: float):
        """One message, or None on timeout, overflow or a closed pipe."""
        try:
            ov, err = self._w.ReadFile(handle, _MAX_MESSAGE, overlapped=True)
            _, err = self._finish(ov, err, timeout_s)
        except OSError:
            return None
        return bytes(ov.getbuffer()) if err == 0 else None

    # pipe, server side
    def create_server(self, pipe: str):
        w = self._w
        ctypes = self._ctypes
        descriptor = ctypes.c_void_p()
        dacl = f"D:P(A;;GA;;;{self.user_sid()})"
        if not self._a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                dacl, 1, ctypes.byref(descriptor), None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            attrs = self._sa(ctypes.sizeof(self._sa), descriptor, False)
            handle = self._k.CreateNamedPipeW(
                pipe, w.PIPE_ACCESS_DUPLEX | w.FILE_FLAG_OVERLAPPED | self.FILE_FLAG_FIRST_PIPE_INSTANCE,
                w.PIPE_TYPE_MESSAGE | w.PIPE_READMODE_MESSAGE | self.PIPE_REJECT_REMOTE_CLIENTS,
                1, _MAX_MESSAGE, _MAX_MESSAGE, 0, ctypes.byref(attrs))
            if handle == self._wt.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            return handle
        finally:
            self._k.LocalFree(descriptor)

    def disconnect(self, handle):
        if not self._k.DisconnectNamedPipe(handle) and self._ctypes.get_last_error() != 233:
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def accept(self, handle, stop: threading.Event) -> bool:
        ov = self._w.ConnectNamedPipe(handle, overlapped=True)
        try:
            while not stop.is_set():
                if self._w.WaitForSingleObject(ov.event, 250) == self.WAIT_OBJECT_0:
                    break
            else:
                ov.cancel()
        finally:
            _, err = ov.GetOverlappedResult(True)
        return err == 0 and not stop.is_set()

    def linger(self, handle, timeout_s: float) -> None:
        """Wait (bounded) for the client to read the reply and hang up."""
        self.recv(handle, timeout_s)

    # windows
    def window_pid(self, hwnd) -> int:
        pid = self._wt.DWORD()
        self._u.GetWindowThreadProcessId(hwnd, self._ctypes.byref(pid))
        return int(pid.value)

    def is_iconic(self, hwnd) -> bool:
        return bool(self._u.IsIconic(hwnd))

    def activate(self, hwnd):
        if self.is_iconic(hwnd):
            self._u.ShowWindow(hwnd, 9)  # SW_RESTORE uses the native window placement.
        self._u.SetForegroundWindow(hwnd)

    def foreground(self):
        return self._u.GetForegroundWindow() or None

    def allow_foreground(self, pid: int) -> bool:
        return bool(self._u.AllowSetForegroundWindow(pid))


def has_window_candidate() -> bool:
    """A shortcut may try the normal verified handoff even during helper recovery."""
    try:
        api = _Win32()
        return api.has_mutex("Local\\" + _instance_name(api))
    except Exception:
        return False


def _hand_off(api, name: str, url: str | None, wait_s: float) -> bool:
    """True only when an open Uoink window of this profile is now in front."""
    pipe = process = None
    try:
        if url is not None and (not _allowed_url(url) or len(url) > _MAX_URL):
            return False
        pipe = api.connect("\\\\.\\pipe\\" + name, wait_s)
        if not pipe:
            return False
        pid = api.server_pid(pipe)
        if not pid:
            return False
        process = api.open_process(pid)  # Keep the process object alive through HWND verification.
        image = Path(api.image_path(process))
        local = Path(api.image_path())
        if api.user_sid(process) != api.user_sid() or api.session_id(pid) != api.session_id():
            return False
        python_pair = {image.name.lower(), local.name.lower()} == {"python.exe", "pythonw.exe"}
        if image != local and not (python_pair and image.parent == local.parent):
            return False
        expires = time.monotonic() + _REPLY_WAIT_S
        message = json.dumps({"uoink": "dashboard-focus", "v": 2, "url": url, "expires": expires},
                             ensure_ascii=False).encode("utf-8")
        if len(message) > _MAX_MESSAGE:
            return False
        # This launch came from the user's click, so it may give the open
        # window's process the right to come to the front.
        api.allow_foreground(pid)
        api.send(pipe, message)
        raw = api.recv(pipe, max(0, expires - time.monotonic()))
        # Hang up now so the open window can answer the next launch.
        api.close(pipe)
        pipe = None
        reply = json.loads(raw.decode("utf-8")) if raw else None
        if not isinstance(reply, dict) or reply.get("ok") is not True:
            return False
        hwnd = reply.get("hwnd")
        if type(hwnd) is not int or hwnd <= 0 or api.window_pid(hwnd) != pid:
            return False
        deadline = time.monotonic() + _FOREGROUND_WAIT_S
        while True:
            if api.foreground() == hwnd and not api.is_iconic(hwnd):
                return True
            if time.monotonic() >= deadline:
                log.info("Open dashboard did not come to the front; opening a new window")
                return False
            time.sleep(0.05)
    except Exception as exc:
        log.debug("Dashboard handoff failed; opening a new window: %s", exc)
        return False
    finally:
        if pipe:
            api.close(pipe)
        if process:
            api.close(process)


class _FocusServer:
    """Own one pipe instance and dispatch its requests to the WinForms thread."""

    def __init__(self, api, name: str, window, owner=None) -> None:
        self.api = api
        self.pipe = "\\\\.\\pipe\\" + name
        self.window = window
        self.stop = threading.Event()
        self.owner = owner

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name="uoink-dashboard-focus", daemon=True)
        thread.start()
        return thread

    def run(self) -> None:
        handle = listener_mutex = None
        try:
            while not self.window.events.shown.wait(0.5):
                if self.stop.is_set():
                    return
            # Every live candidate holds the presence mutex. Only one listens.
            # A third click can therefore wait for a fallback already on screen
            # even if it arrives just as the original owner exits.
            failures = 0
            while not self.stop.is_set():
                try:
                    if self.owner and listener_mutex is None:
                        candidate, existed = self.api.create_mutex("Local\\" + self.owner.name + "-listener")
                        if not candidate:
                            raise OSError("listener mutex unavailable")
                        if existed:
                            self.api.close(candidate)
                            self.stop.wait(0.1)
                            continue
                        listener_mutex = candidate
                    if handle is None:
                        handle = self.api.create_server(self.pipe)
                    if not self.api.accept(handle, self.stop):
                        if self.stop.is_set():
                            return
                        raise OSError("pipe accept failed")
                    request = self.api.recv(handle, 2.0)
                    self.api.send(handle, self.answer(request))
                    self.api.linger(handle, 2.0)
                    self.api.disconnect(handle)
                    failures = 0
                except OSError as exc:
                    # Disconnect and reuse the reserved instance even if the client vanished.
                    if handle is not None:
                        try:
                            self.api.disconnect(handle)
                        except OSError:
                            self.api.close(handle)
                            handle = None
                    failures += 1
                    log.debug("dashboard focus pipe failed: %s", exc)
                    if failures >= 8 or self.stop.wait(min(1.0, 0.05 * 2 ** (failures - 1))):
                        return
        except Exception as exc:
            log.debug("dashboard focus listener stopped: %s", exc)
        finally:
            if handle is not None:
                self.api.close(handle)
            if listener_mutex:
                self.api.close(listener_mutex)
            if self.owner:
                self.owner.drop_mutex()

    def answer(self, raw) -> bytes:
        try:
            request = json.loads(raw) if raw else None
            if (not isinstance(request, dict) or request.get("uoink") != "dashboard-focus"
                    or request.get("v") != 2):
                return _FAILED
            expires = request["expires"]
            if type(expires) not in (float, int) or not 0 < expires - time.monotonic() <= _REPLY_WAIT_S:
                return _FAILED
            url = request["url"]
            if url is not None and (not _allowed_url(url) or len(url) > _MAX_URL):
                return _FAILED
            if url is not None and not self.window.events.loaded.wait(max(0, expires - time.monotonic())):
                return _FAILED

            # BeginInvoke is safe across threads. All form, HWND and WebView2 access
            # happens inside its delegate, including the deadline check after a busy UI.
            from System import Action
            done = threading.Event()
            result = {}
            form = self.window.native

            def focus():
                try:
                    if self.stop.is_set() or time.monotonic() >= expires:
                        return
                    hwnd = form.Handle.ToInt64()
                    if not hwnd:
                        return
                    self.api.activate(hwnd)
                    if url is not None:
                        # WebView2 may dispatch this later than WinForms. Check the
                        # current document before giving its page the link.
                        page_deadline = int(1000 * (time.time() + (expires - time.monotonic())))
                        script = (f"location.origin + location.pathname === {json.dumps(_dashboard_url())}"
                                  f" && window.uoinkOpenDashboardLink({json.dumps(url)}, {page_deadline})")
                        result["navigation"] = form.webview.CoreWebView2.ExecuteScriptAsync(script)
                    result["hwnd"] = hwnd
                except Exception as exc:
                    log.debug("dashboard GUI handoff failed: %s", exc)
                finally:
                    done.set()

            form.BeginInvoke(Action(focus))
            if not done.wait(max(0, expires - time.monotonic())) or not result.get("hwnd"):
                return _FAILED
            if url is not None:
                task = result["navigation"]
                if not task.Wait(max(0, int(1000 * (expires - time.monotonic())))) or task.Result != "true":
                    return _FAILED
            return json.dumps({"ok": True, "hwnd": result["hwnd"]}).encode()
        except Exception as exc:
            log.debug("could not bring the dashboard forward: %s", exc)
            return _FAILED


class _OneWindow:
    """Never raises: any failure means 'open a window as before'."""

    def __init__(self) -> None:
        self.api = None
        self.name = None
        self.mutex = None
        self.server = None
        self.handed_off = False
        self._lock = threading.Lock()
        self.thread = None

    @classmethod
    def claim(cls, target_url: str, api_factory=None) -> "_OneWindow":
        one = cls()
        try:
            one.api = (api_factory or _Win32)()
            one.name = _instance_name(one.api)
            if one.keep_presence():
                # Only windows may keep the name alive. A client waiting for
                # a dead listener must not make the next click wait too.
                one.drop_mutex()
                one.handed_off = _hand_off(one.api, one.name, _requested_url(target_url), _HANDOFF_WAIT_S)
                if not one.handed_off:
                    one.keep_presence()  # The local fallback will be a candidate.
        except Exception as exc:
            log.debug("One-window check unavailable: %s", exc)
            one.drop_mutex()
            one.api = None
        return one

    def keep_presence(self) -> bool:
        self.mutex, existed = self.api.create_mutex("Local\\" + self.name)
        if not self.mutex:
            raise OSError("CreateMutexW failed")
        return existed

    def drop_mutex(self) -> None:
        with self._lock:
            if self.mutex:
                self.api.close(self.mutex)
                self.mutex = None

    def serve(self, window) -> None:
        if self.api is None:
            return
        try:
            self.server = _FocusServer(self.api, self.name, window, self)
            self.thread = self.server.start()
        except Exception as exc:
            self.release()
            log.debug("One-window listener unavailable: %s", exc)

    def release(self) -> None:
        if self.server is not None:
            self.server.stop.set()
            if self.thread is not None:
                self.thread.join(0.5)
        self.drop_mutex()


def main() -> int:
    target_url = _target_url()
    if sys.platform == "darwin":
        from helper.mac_ui import watch_parent
        watch_parent()
        try:
            import webview
            # Fail before making a window if the Cocoa backend cannot import.
            import webview.platforms.cocoa  # noqa: F401
            from helper.mac_ui import cursor_screen
            webview.create_window("Uoink", target_url, width=WIDTH, height=HEIGHT,
                                  resizable=True, js_api=MacJsApi(), screen=cursor_screen())
            webview.start(gui="cocoa")
        except Exception as exc:
            log.warning("Cocoa dashboard unavailable; opening browser: %s", exc)
            webbrowser.open(target_url)
        return 0
    try:
        import webview
    except Exception as e:
        log.debug("pywebview unavailable; opening dashboard in default browser: %s", e)
        webbrowser.open(target_url)
        return 0
    one = _OneWindow.claim(target_url) if sys.platform == "win32" else None
    if one is not None and one.handed_off:
        return 0
    try:
        window = webview.create_window(WINDOW_TITLE, target_url, width=WIDTH, height=HEIGHT,
                                       resizable=True, js_api=JsApi())
        if window is None:
            raise RuntimeError("pywebview did not create a dashboard window")
        if sys.platform == "win32":
            threading.Thread(target=_brand_windows_icon_when_ready, name="uoink-dashboard-icon",
                             daemon=True).start()
        if one is not None:
            one.serve(window)
        webview.start()
    except Exception as exc:
        log.warning("Dashboard window unavailable; opening browser: %s", exc)
    else:
        return 0
    finally:
        if one is not None:
            one.release()
    webbrowser.open(target_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
