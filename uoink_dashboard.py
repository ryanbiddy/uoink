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
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

log = logging.getLogger("uoink.dashboard")

HERE = Path(__file__).parent.resolve()
DASHBOARD_URL = "http://127.0.0.1:5179/dashboard"
WIDTH, HEIGHT = 1280, 800
ICON_PATH = HERE / "uoink.ico"
_ICON_HANDLES = []


def _target_url() -> str:
    if len(sys.argv) > 1:
        candidate = str(sys.argv[1])
        if candidate.startswith(DASHBOARD_URL):
            return candidate
    return DASHBOARD_URL


class JsApi:
    """window.pywebview.api.* surface for the dashboard window. Today the
    dashboard HTML doesn't call into native; expose open_url for future
    external-link clicks so Codex's feature-detection has something to find."""

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception as e:
            log.debug("open_url failed: %s", e)
        return True


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


def main() -> int:
    target_url = _target_url()
    try:
        import webview
    except Exception as e:
        log.debug("pywebview unavailable; opening dashboard in default browser: %s", e)
        webbrowser.open(target_url)
        return 0
    webview.create_window(
        "Uoink",
        target_url,
        width=WIDTH,
        height=HEIGHT,
        resizable=True,
        js_api=JsApi(),
    )
    if sys.platform == "win32":
        threading.Thread(
            target=_brand_windows_icon_when_ready,
            name="uoink-dashboard-icon",
            daemon=True,
        ).start()
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
