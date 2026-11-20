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
"""
from __future__ import annotations

import logging
import hashlib
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

if sys.platform == "darwin":
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

log = logging.getLogger("uoink.dashboard")

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
import uoink_install_isolation as _install_isolation  # noqa: E402
_install_isolation.apply_from_process()

DASHBOARD_URL = "http://127.0.0.1:5179/dashboard"
WIDTH, HEIGHT = 1280, 800
ICON_PATH = HERE / "uoink.ico"
_ICON_HANDLES = []


def _dashboard_url() -> str:
    return _install_isolation.helper_url("/dashboard")


def _target_url() -> str:
    bound = _dashboard_url()
    for candidate in sys.argv[1:]:
        if candidate.startswith(bound) or (
            _install_isolation.current_binding() is None
            and candidate.startswith(DASHBOARD_URL)
        ):
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


def _focus_event_api():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    for fn in (kernel.SetEvent, kernel.CloseHandle):
        fn.argtypes = [wintypes.HANDLE]
        fn.restype = wintypes.BOOL
    return kernel, ctypes.get_last_error


def _focus_dashboard(window):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    hwnd = window.native.Handle.ToInt64()
    if user32.IsIconic(hwnd):
        window.restore()
    window.show()
    user32.SetForegroundWindow(hwnd)


def _windows_dashboard(webview, target_url):
    kernel, last_error = _focus_event_api()
    # Local to this logon session and helper binding. The OS drops the
    # event if the window process crashes, including during startup.
    identity = hashlib.sha256(_dashboard_url().encode()).hexdigest()[:24]
    handle = kernel.CreateEventW(None, False, False, "Local\\UoinkDashboard-" + identity)
    error = last_error()
    if not handle:
        raise OSError(error, "Could not open the dashboard focus event")
    stopped = threading.Event()
    waiting = threading.Lock()

    def listen(window):
        while True:
            with waiting:
                if stopped.is_set():
                    return
                result = kernel.WaitForSingleObject(handle, 250)
            if result == 0:
                try:
                    _focus_dashboard(window)
                except Exception as exc:
                    log.debug("dashboard focus unavailable: %s", exc)
            elif result != 258:  # WAIT_TIMEOUT
                return

    try:
        if error == 183:  # ERROR_ALREADY_EXISTS
            if not kernel.SetEvent(handle):
                raise OSError(last_error(), "Could not signal the dashboard window")
            return 0
        window = webview.create_window("Uoink", target_url, width=WIDTH, height=HEIGHT,
                                       resizable=True, js_api=JsApi())
        threading.Thread(target=_brand_windows_icon_when_ready, name="uoink-dashboard-icon", daemon=True).start()
        webview.start(listen, (window,))
        return 0
    finally:
        stopped.set()
        with waiting:
            kernel.CloseHandle(handle)


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
    if sys.platform == "win32":
        return _windows_dashboard(webview, target_url)
    webview.create_window(
        "Uoink",
        target_url,
        width=WIDTH,
        height=HEIGHT,
        resizable=True,
        js_api=JsApi(),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
