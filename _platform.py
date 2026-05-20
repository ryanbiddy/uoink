"""Cross-platform path + OS-integration helpers for the Yoink helper.

Sprint 19.5 Stage 1: every per-platform branch that used to live inline in
server.py (Windows known-folder API, ``%LOCALAPPDATA%``, ``os.startfile``,
PowerShell toast) is consolidated here so the same code paths run on
Windows, macOS, and (future) Linux without ``sys.platform`` branches at
call sites.

This module is Mac-CAPABLE, not yet Mac-tested. Stage 2 packages the Mac
distribution and runs the actual Mac runtime verification; until then the
darwin / linux branches are best-effort + flagged in their docstrings.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

log = logging.getLogger("yoink.platform")

# When we shell out (open / xdg-open / osascript / explorer / notify-send),
# detach stdio so the child never blocks on a pipe and the parent doesn't
# accumulate zombie file descriptors. SUBPROCESS_KW from server.py
# (creationflags=CREATE_NO_WINDOW on Windows) is layered on by the caller
# where applicable -- we keep this module dependency-free so it can be
# imported before server.py finishes initialising.
_DETACHED_IO = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------
def platform_label() -> str:
    """Short, stable identifier for /diagnose and log lines."""
    return {
        "win32": "windows",
        "darwin": "macos",
        "linux": "linux",
    }.get(sys.platform, sys.platform)


def keyring_display_name() -> str:
    """Human-readable name of the OS credential store the keyring package
    binds to. Used in /diagnose."""
    if sys.platform == "win32":
        return "Windows Credential Manager"
    if sys.platform == "darwin":
        return "macOS Keychain"
    return "Secret Service"


# --------------------------------------------------------------------------
# Path resolution
# --------------------------------------------------------------------------
def user_data_dir() -> Path:
    """Where Yoink stores index.db, settings.json, server.log, the auth
    token, and the migrated jobs.json / taxonomy.json files.

    Windows: ``%LOCALAPPDATA%\\Yoink`` (falls back to
             ``~\\AppData\\Local\\Yoink`` if LOCALAPPDATA is unset, which
             happens in some headless test setups).
    macOS:   ``~/Library/Application Support/Yoink`` (the standard
             container per Apple's File System Programming Guide).
    Linux:   ``$XDG_DATA_HOME/Yoink``, else ``~/.local/share/Yoink``
             (XDG Base Directory Specification).
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local"
        )
        return Path(base) / "Yoink"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Yoink"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "Yoink"


def desktop_dir() -> Path:
    """User's Desktop folder.

    Windows uses the known-folder API (``SHGetKnownFolderPath`` with
    ``FOLDERID_Desktop``) so a Desktop redirected to OneDrive is followed
    correctly -- consumer OneDrive opts Desktop in by default, and naive
    ``%USERPROFILE%\\Desktop`` would land yoinks in a folder the user
    can't see in Explorer.

    macOS / Linux assume the standard ``~/Desktop`` location. Linux users
    with XDG_DESKTOP_DIR set to something non-standard get the standard
    path; revisit if Linux ever becomes a shipped target (Sprint 19.5
    Stage 1 ships Windows + Mac only).
    """
    if sys.platform == "win32":
        return _windows_desktop_dir()
    return Path.home() / "Desktop"


# --------------------------------------------------------------------------
# OS integrations
# --------------------------------------------------------------------------
def open_in_os(path: Path | str) -> None:
    """Open a file or folder in the OS's default handler.

    Windows: ``os.startfile`` (registered per-extension handler).
    macOS:   ``open <path>`` (Finder for folders, default app for files).
    Linux:   ``xdg-open <path>``.

    Raises the underlying OSError on failure -- callers wrap in
    try/except for "best-effort, log-on-failure" semantics, matching the
    pre-Sprint-19.5 behaviour where each call site had its own catch."""
    p = str(path)
    if sys.platform == "win32":
        # os.startfile is Windows-only; the type ignore mirrors the
        # comments that used to live at every call site.
        os.startfile(p)  # type: ignore[attr-defined]
        return
    cmd = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([cmd, p], **_DETACHED_IO)


def reveal_in_file_manager(path: Path | str) -> None:
    """Open the OS file manager focused on ``path``.

    Windows: ``explorer /select,<path>`` (selects the item in its parent).
    macOS:   ``open -R <path>`` (reveals in Finder).
    Linux:   ``xdg-open <parent>`` -- there's no portable "select this
             specific file" affordance across Linux file managers, so we
             degrade to opening the containing folder.
    """
    p = Path(path)
    if sys.platform == "win32":
        subprocess.Popen(
            ["explorer", f"/select,{p}"], **_DETACHED_IO,
        )
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(p)], **_DETACHED_IO)
        return
    subprocess.Popen(["xdg-open", str(p.parent)], **_DETACHED_IO)


def show_toast(title: str, body: str) -> None:
    """Best-effort transient notification when the helper finishes booting.

    Windows: PowerShell + ``System.Windows.Forms.NotifyIcon`` balloon
             (Win10/Win11; suppressed gracefully by Focus Assist).
    macOS:   ``osascript -e 'display notification ...'``.
    Linux:   ``notify-send`` (libnotify) -- silently skipped if missing.

    Fire-and-forget. Any failure is debug-logged and swallowed -- a
    missing tray icon should never block startup."""
    try:
        if sys.platform == "win32":
            _windows_toast(title, body)
        elif sys.platform == "darwin":
            _macos_toast(title, body)
        else:
            _linux_toast(title, body)
    except Exception as e:
        log.debug("toast (%s) failed: %s", platform_label(), e)


# --------------------------------------------------------------------------
# Windows-only internals
# --------------------------------------------------------------------------
def _windows_desktop_dir() -> Path:
    """Windows-specific Desktop resolution via the known-folder API. See
    desktop_dir() for the rationale."""
    fallback = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    if sys.platform != "win32":
        # Defensive: this is only invoked from desktop_dir() under the
        # win32 branch, but a future caller might import the symbol
        # directly. Falling back to ~/Desktop is harmless on non-Windows.
        return fallback
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Desktop = {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
        FOLDERID_Desktop = _GUID(
            0xB4BFCC3A, 0xDB2C, 0x424C,
            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
        )
        SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
        SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        SHGetKnownFolderPath.restype = ctypes.c_long  # HRESULT

        out = ctypes.c_wchar_p()
        hr = SHGetKnownFolderPath(
            ctypes.byref(FOLDERID_Desktop), 0, None, ctypes.byref(out)
        )
        if hr == 0 and out.value:
            try:
                return Path(out.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        # Module loads before logging is configured and pythonw.exe has no
        # stderr, so we silently fall back. Users with redirected Desktops
        # will see yoinks under %USERPROFILE%\\Desktop -- not optimal, but
        # workable as a degraded mode.
        pass
    return fallback


def _windows_toast(title: str, body: str) -> None:
    # Single-quote escape for PowerShell single-quoted strings.
    t = title.replace("'", "''")
    b = body.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon = [System.Drawing.SystemIcons]::Information;"
        "$n.BalloonTipIcon = 'Info';"
        f"$n.BalloonTipTitle = '{t}';"
        f"$n.BalloonTipText = '{b}';"
        "$n.Visible = $true;"
        "$n.ShowBalloonTip(5000);"
        # Keep the tray icon alive long enough for Windows to render the
        # balloon (the timeout arg is advisory; Windows uses a fixed ~5s).
        "Start-Sleep -Seconds 6;"
        "$n.Dispose()"
    )
    # CREATE_NO_WINDOW prevents a console flash; not portable so we set it
    # locally rather than importing server.py's SUBPROCESS_KW (avoids a
    # circular import at module-load time).
    creationflags = 0x08000000  # CREATE_NO_WINDOW
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
        creationflags=creationflags,
        **_DETACHED_IO,
    )


# --------------------------------------------------------------------------
# macOS-only internals (Stage 2 will runtime-test these)
# --------------------------------------------------------------------------
def _macos_toast(title: str, body: str) -> None:
    # AppleScript string literals use double-quotes; escape backslashes
    # and double-quotes inside the user-supplied strings to keep the
    # script grammar intact.
    t = title.replace("\\", "\\\\").replace('"', '\\"')
    b = body.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{b}" with title "{t}"'
    subprocess.Popen(["osascript", "-e", script], **_DETACHED_IO)


# --------------------------------------------------------------------------
# Linux-only internals (future)
# --------------------------------------------------------------------------
def _linux_toast(title: str, body: str) -> None:
    try:
        subprocess.Popen(["notify-send", title, body], **_DETACHED_IO)
    except FileNotFoundError:
        # libnotify isn't installed -- this is fine, the helper still
        # boots, the user just doesn't see a desktop notification.
        log.debug("notify-send not available; toast skipped")
