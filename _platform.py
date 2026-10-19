"""Cross-platform path + OS-integration helpers for the Uoink helper.

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
import ctypes
import errno
import os
import io
import subprocess
import sys
import wave
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

log = logging.getLogger("uoink.platform")

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


def library_mirror_capability() -> dict:
    """Publication is deferred until Darwin has identity-bound vault I/O."""
    if sys.platform == "darwin":
        return {"available": False, "code": "library_mirror_unavailable_macos",
                "reason": "Library mirroring is unavailable on macOS in this release. "
                          "Safe replacement and deletion of vault files have not been qualified."}
    return {"available": True, "code": None, "reason": None}


def capability_refusal(capability: dict) -> dict | None:
    if capability["available"]:
        return None
    return {"ok": False, "available": False, "enabled": False, "state": "unavailable",
            "code": capability["code"], "reason": capability["reason"],
            "error": {"code": capability["code"], "message": capability["reason"],
                      "retryable": False}}


MAC_BUNDLE_PYTHON = Path("Resources/Python/bin/python3")


def mac_bundle_contents() -> Path | None:
    """Identify the embedded interpreter, independently of cwd/env/module path."""
    if sys.platform != "darwin":
        return None
    executable = getattr(sys, "executable", "")
    if not executable:
        return None
    # Only the real interpreter location establishes bundle mode. python3 may
    # resolve to python3.13, but a link from the app to an external Python does
    # not qualify, nor does an unrelated executable elsewhere in the install.
    try:
        path = Path(executable).resolve()
        if len(path.parents) < 5:
            return None
        contents = path.parents[3]
        if (path.parent.name == "bin" and path.parents[1].name == "Python"
                and path.parents[2].name == "Resources" and contents.name == "Contents"
                and contents.parent.suffix == ".app"
                and path == (contents / MAC_BUNDLE_PYTHON).resolve()):
            return contents
    except (OSError, RuntimeError):
        pass
    return None


def media_binary(name: str) -> str:
    """Use app-owned binaries in a bundle; source checkouts retain PATH lookup."""
    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError(f"Unknown media executable: {name}")
    if sys.platform != "darwin":
        return name
    contents = mac_bundle_contents()
    if contents is None:
        return name
    helpers = contents / "Helpers"
    path = helpers / name
    if path.is_symlink() or helpers.is_symlink() or not path.is_file():
        raise FileNotFoundError(f"Bundled media executable missing: {path}")
    return str(path)


def ytdlp_media_args() -> list[str]:
    if sys.platform != "darwin":
        return []
    contents = mac_bundle_contents()
    if contents is None:
        return []
    helpers = contents / "Helpers"
    # A missing explicit location makes yt-dlp refuse FFmpeg, without PATH fallback.
    return ["--ignore-config", "--ffmpeg-location", str(helpers)]


def video_format(default: str) -> str:
    if sys.platform != "darwin" or mac_bundle_contents() is None:
        return default
    # No unknown-codec or unrestricted fallback: AV1/HEVC have not been enabled.
    native = '[vcodec~="^(avc1|h264|vp0?8|vp0?9)"]'
    return f"worst*{native}[height>=360]/worst*{native}"


def podcast_audio_format() -> str:
    # FFmpeg has no native MP3 encoder. WAV avoids an additional LGPL library.
    return "wav" if sys.platform == "darwin" and mac_bundle_contents() is not None else "mp3"


def _test_wav() -> bytes:
    data = io.BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x10\x00" * 800)
    return data.getvalue()


@lru_cache(maxsize=8)
def _media_self_test(ffmpeg: str, ffprobe: str, identities: tuple) -> bool:
    """Cache by executable identity; writes no files inside or outside the app."""
    try:
        for binary in (ffmpeg, ffprobe):
            subprocess.run([binary, "-version"], check=True, capture_output=True, timeout=10)
        result = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", "pipe:0",
                                 "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                                 "-f", "s16le", "pipe:1"], input=_test_wav(),
                                check=True, capture_output=True, timeout=10)
        return len(result.stdout) == 3200 and any(result.stdout)
    except (OSError, subprocess.SubprocessError):
        return False


def media_capability() -> dict:
    """Only a bundled runtime requires the app-owned executable self-test."""
    if sys.platform == "darwin" and mac_bundle_contents() is not None:
        try:
            binaries = [media_binary(name) for name in ("ffmpeg", "ffprobe")]
            identities = tuple((p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ino)
                               for p in map(Path, binaries))
            if _media_self_test(*binaries, identities):
                return {"available": True, "code": None, "reason": None}
        except OSError:
            pass
        return {"available": False, "code": "media_requires_ffmpeg",
                "reason": "Bundled ffmpeg/ffprobe are missing or failed their decode self-test. "
                          "Media extraction is unavailable."}
    return {"available": True, "code": None, "reason": None}


def alignment_capability() -> dict:
    """FFmpeg CLI availability does not establish the TorchCodec/WhisperX ABI."""
    contents = mac_bundle_contents() if sys.platform == "darwin" else None
    if contents is not None:
        import json
        try:
            report = json.loads((contents / "Resources/notices/torchcodec.json").read_text()) if contents else {}
            libraries = report.get("libraries", [])
            if (report.get("available") is True and libraries and
                    all((contents / "Frameworks/FFmpeg7" / name).is_file() for name in libraries)):
                return {"available": True, "code": None, "reason": None}
        except (OSError, ValueError):
            pass
        return {"available": False, "code": "alignment_requires_torchcodec",
                "reason": "WhisperX/alignment is unavailable: the bundled TorchCodec FFmpeg 7 "
                          "decoder did not pass qualification. See notices/torchcodec.json."}
    return {"available": True, "code": None, "reason": None}


def platform_capabilities() -> dict:
    result = {"library_mirror": library_mirror_capability(), "media": media_capability()}
    if sys.platform == "darwin":
        result["alignment"] = alignment_capability()
    return result


def capability_notice() -> str:
    return "".join(f" {value['reason']} ({value['code']})"
                   for value in platform_capabilities().values() if not value["available"])


class MediaUnavailableError(RuntimeError):
    """A capability refusal that survives user-facing error translation."""

    def __init__(self, capability: dict):
        self.code = capability["code"]
        self.refusal = capability_refusal(capability)
        super().__init__(f"{self.code}: {capability['reason']}")


def require_media() -> None:
    capability = media_capability()
    if not capability["available"]:
        raise MediaUnavailableError(capability)


def platform_detail() -> str:
    """Human-readable ``<os> <arch>`` for /diagnose -- e.g. ``windows
    AMD64``, ``macos arm64``, ``linux x86_64``. The arch comes from
    ``platform.machine()`` (stdlib) which is the machine the Python
    interpreter is running on, not the build target -- so an x86_64
    Python launched under Rosetta on Apple Silicon returns ``x86_64``,
    which is the right answer for "can this install run native binaries"."""
    import platform as _stdlib_platform
    arch = _stdlib_platform.machine() or "unknown"
    return f"{platform_label()} {arch}"


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
    """Where Uoink stores index.db, settings.json, server.log, the auth
    token, and the migrated jobs.json / taxonomy.json files.

    Windows: ``%LOCALAPPDATA%\\Uoink`` (falls back to
             ``~\\AppData\\Local\\Uoink`` if LOCALAPPDATA is unset, which
             happens in some headless test setups).
    macOS:   ``~/Library/Application Support/Uoink`` (the standard
             container per Apple's File System Programming Guide).
    Linux:   ``$XDG_DATA_HOME/Uoink``, else ``~/.local/share/Uoink``
             (XDG Base Directory Specification).

    v2.1 rename: the Yoink-era equivalents (``%LOCALAPPDATA%\\Yoink`` etc.)
    are migrated into these locations by migrate_install.py on first run.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local"
        )
        return Path(base) / "Uoink"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Uoink"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "Uoink"


def legacy_user_data_dir() -> Path:
    """The pre-rename (Yoink) user-data directory, used only by the one-time
    install migration. Mirrors user_data_dir() with the old brand folder."""
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


def app_state_path(app: Path, data: Path, name: str) -> Path:
    """Darwin state belongs outside the sealed app; other layouts stay intact."""
    return (data if sys.platform == "darwin" else app) / name


def prepare_app_state(data: Path) -> None:
    if sys.platform == "darwin":
        data.mkdir(mode=0o700, parents=True, exist_ok=True)


def topics_source(app: Path, target: Path) -> Path:
    if sys.platform == "darwin" and not target.exists():
        return app / "topics.json"
    return target


def write_darwin_identity(data: Path, script: Path) -> Path:
    """Record a complete native identity for the ordinary Darwin resident."""
    import json
    observation = darwin_observe(os.getpid(), with_executable=True)
    if observation.status != "alive" or observation.created_ms is None or not observation.executable:
        raise OSError("Darwin helper process identity is unavailable")
    target = data / "runtime-identity.json"
    temporary = target.with_suffix(".json.tmp")
    payload = {"pid": os.getpid(), "created_ms": observation.created_ms,
               "executable": observation.executable, "script": str(script.resolve())}
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream)
    temporary.replace(target)
    return target


def darwin_helper_running(app: Path, data: Path) -> bool:
    import json
    try:
        identity = json.loads((data / "runtime-identity.json").read_text(encoding="utf-8"))
        if not isinstance(identity, dict) or identity.get("pid") == os.getpid():
            return False
        script = identity.get("script")
        executable = identity.get("executable")
        if not script or not executable or not (app / "server.py").samefile(script):
            return False
        return darwin_liveness(identity.get("pid"), identity.get("created_ms"), executable) == "alive"
    except (OSError, ValueError, TypeError):
        return False


def editable_extension_dir(app: Path, data: Path) -> Path:
    """Seed/update Darwin's unpacked extension, preserving edited prompts.

    A version change refreshes packaged files, retaining prompts.json and any
    user-added files. The version stamp is written last so interrupted copies
    are retried. Windows continues to return the installed extension directory.
    """
    packaged = app / "extension"
    if sys.platform != "darwin":
        return packaged
    import shutil
    if not packaged.is_dir():
        return packaged  # Let callers report a missing installation resource.
    target = data.resolve() / "extension"
    version = (app / "VERSION").read_text(encoding="utf-8").strip()
    stamp = target / ".uoink-packaged-version"
    if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == version:
        return target
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    for source in packaged.rglob("*"):
        relative = source.relative_to(packaged)
        dest = target / relative
        if source.is_symlink() or dest.is_symlink() or any(p.is_symlink() for p in dest.parents):
            raise OSError("Linked extension resources are not writable copies")
        if source.is_dir():
            dest.mkdir(exist_ok=True)
        elif not (relative == Path("prompts.json") and dest.exists()):
            temporary = dest.with_name(dest.name + ".uoink-tmp")
            if temporary.is_symlink():
                raise OSError("Linked extension temporary file")
            shutil.copyfile(source, temporary)
            temporary.replace(dest)
    stamp.write_text(version + "\n", encoding="utf-8")
    return target


# Darwin's native process adapter lives in this already-shipped module so the
# Windows installer file set does not change. Calls load libproc only on demand.
class _DarwinProcBSDInfo(ctypes.Structure):
    # Darwin sys/proc_info.h: PROC_PIDTBSDINFO (flavor 3), 136 bytes on arm64.
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "flags", "status", "xstatus", "pid", "ppid", "uid", "gid", "ruid",
        "rgid", "svuid", "svgid", "rfu_1",
    )] + [("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32)] + [
        (name, ctypes.c_uint32) for name in ("nfiles", "pgid", "pjobc", "e_tdev", "e_tpgid")
    ] + [("nice", ctypes.c_int32), ("start_sec", ctypes.c_uint64),
         ("start_usec", ctypes.c_uint64)]


@dataclass(frozen=True)
class DarwinProcessObservation:
    status: str  # alive, dead, unknown
    started_us: int | None = None
    executable: str | None = None

    @property
    def created_ms(self) -> float | None:
        # Keep the wire field's millisecond units, including its microsecond
        # fraction. At current epoch dates binary64 round-trips every native
        # microsecond through JSON. Never truncate this value to an integer.
        return None if self.started_us is None else self.started_us / 1000


def darwin_creation_us(created_ms) -> int | None:
    """Decode a persisted millisecond timestamp at libproc's native precision."""
    import math
    if type(created_ms) not in (int, float) or not 0 < created_ms < 2**42:
        return None
    if not math.isfinite(created_ms):
        return None
    return round(created_ms * 1000)


@lru_cache(maxsize=1)
def _darwin_libproc():
    lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                 ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidinfo.restype = ctypes.c_int
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    lib.proc_pidpath.restype = ctypes.c_int
    return lib


def _darwin_bsd_info(lib, pid: int) -> DarwinProcessObservation:
    info = _DarwinProcBSDInfo()
    ctypes.set_errno(0)
    size = lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if size <= 0:
        # libproc can report ESRCH for an unreaped child: kill(pid, 0) alone
        # cannot distinguish that exited process from a running one.
        return DarwinProcessObservation("dead" if ctypes.get_errno() == errno.ESRCH else "unknown")
    if size != ctypes.sizeof(info) or info.pid != pid:
        return DarwinProcessObservation("unknown")
    if info.status == 5:  # SZOMB: kill(pid, 0) would still succeed.
        return DarwinProcessObservation("dead")
    if info.status not in (1, 2, 3, 4) or not info.start_sec or info.start_usec >= 1_000_000:
        return DarwinProcessObservation("unknown")
    return DarwinProcessObservation("alive", info.start_sec * 1_000_000 + info.start_usec)


def darwin_observe(pid: int, *, with_executable: bool = False) -> DarwinProcessObservation:
    if type(pid) is not int or not 0 < pid <= 0x7fffffff:
        return DarwinProcessObservation("unknown")
    try:
        lib = _darwin_libproc()
        before = _darwin_bsd_info(lib, pid)
        if before.status != "alive" or not with_executable:
            return before
        buf = ctypes.create_string_buffer(4096)  # PROC_PIDPATHINFO_MAXSIZE
        size = lib.proc_pidpath(pid, buf, len(buf))
        after = _darwin_bsd_info(lib, pid)
        if after.status == "dead":
            return after
        if (after.status != "alive" or before.started_us != after.started_us
                or size <= 0 or size >= len(buf) or not buf.value.startswith(b"/")):
            return DarwinProcessObservation("unknown")
        return DarwinProcessObservation("alive", before.started_us, os.fsdecode(buf.value))
    except (OSError, AttributeError, ValueError):
        return DarwinProcessObservation("unknown")


def darwin_created_ms(pid: int) -> float | None:
    return darwin_observe(pid).created_ms


def darwin_executable(pid: int) -> str | None:
    return darwin_observe(pid, with_executable=True).executable


def darwin_state(pid: int) -> str | None:
    status = darwin_observe(pid).status
    return {"alive": "R", "dead": "Z"}.get(status)


def darwin_liveness(
    pid: int, expected_ms: int | float | None, expected_exe: str | None = None,
    *, tolerance_ms: int = 0, require_identity: bool = True,
) -> str:
    """Check birth and executable in one snapshot; PID-only probes opt in.

    A tolerance is only for legacy lease observations, never ownership. Missing
    birth identity remains unknown unless the caller requests a liveness probe.
    """
    observation = darwin_observe(pid, with_executable=expected_exe is not None)
    if observation.status != "alive":
        return observation.status
    if expected_ms is None and not require_identity:
        pass
    else:
        expected_us = darwin_creation_us(expected_ms)
        if expected_us is None or observation.started_us is None:
            return "unknown"
        if type(tolerance_ms) is not int or tolerance_ms < 0:
            return "unknown"
        if abs(observation.started_us - expected_us) > tolerance_ms * 1000:
            return "dead"
    if expected_exe is not None:
        if not isinstance(expected_exe, str) or not expected_exe or not observation.executable:
            return "unknown"
        try:
            if not os.path.samefile(observation.executable, expected_exe):
                return "dead"
        except OSError:
            return "unknown"
    return "alive"


def desktop_dir() -> Path:
    """User's Desktop folder.

    Windows uses the known-folder API (``SHGetKnownFolderPath`` with
    ``FOLDERID_Desktop``) so a Desktop redirected to OneDrive is followed
    correctly -- consumer OneDrive opts Desktop in by default, and naive
    ``%USERPROFILE%\\Desktop`` would land uoinks in a folder the user
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


def show_toast(title: str, body: str, icon_path: str | None = None) -> None:
    """Best-effort transient notification when the helper finishes booting.

    Windows: PowerShell + ``System.Windows.Forms.NotifyIcon`` balloon
             (Win10/Win11; suppressed gracefully by Focus Assist).
    macOS:   ``osascript -e 'display notification ...'``.
    Linux:   ``notify-send`` (libnotify) -- silently skipped if missing.

    ``icon_path`` (Windows only) brands the balloon with the bundled
    uoink.ico; falls back to the generic OS information icon when None or
    the file is missing. macOS/Linux notification icons are owned by the OS
    notification centre, so the argument is ignored there.

    Fire-and-forget. Any failure is debug-logged and swallowed -- a
    missing tray icon should never block startup."""
    try:
        if sys.platform == "win32":
            _windows_toast(title, body, icon_path)
        elif sys.platform == "darwin":
            _macos_toast(title, body)
        else:
            _linux_toast(title, body)
    except Exception as e:
        log.debug("toast (%s) failed: %s", platform_label(), e)


def is_foreground_fullscreen(
    *,
    platform_name: str | None = None,
    bounds_probe=None,
) -> bool:
    """Return whether a real foreground window covers its monitor.

    This is deliberately a courtesy signal, not an ownership or security
    boundary. On Windows it catches exclusive-fullscreen games and borderless
    fullscreen windows. Other platforms return False until their window APIs
    have an equally cheap, bounded probe.

    ``bounds_probe`` exists so tests never need to create or focus a window.
    It returns ``(window_rect, monitor_rect, class_name)`` where each rect is
    ``(left, top, right, bottom)``.
    """
    selected_platform = sys.platform if platform_name is None else platform_name
    if selected_platform != "win32":
        return False
    probe = bounds_probe or _windows_foreground_bounds
    try:
        observed = probe()
        if observed is None:
            return False
        window_rect, monitor_rect, class_name = observed
        if class_name in {"Progman", "WorkerW", "Shell_TrayWnd"}:
            return False
        tolerance = 2
        return bool(
            window_rect[0] <= monitor_rect[0] + tolerance
            and window_rect[1] <= monitor_rect[1] + tolerance
            and window_rect[2] >= monitor_rect[2] - tolerance
            and window_rect[3] >= monitor_rect[3] - tolerance
        )
    except (OSError, TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
# Windows-only internals
# --------------------------------------------------------------------------
def _windows_foreground_bounds():
    """Return foreground/monitor bounds without changing window state."""
    import ctypes
    from ctypes import wintypes

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", _RECT),
            ("rcWork", _RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_MONITORINFO),
    ]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    user32.GetClassNameW.restype = ctypes.c_int
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    window = _RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(window)):
        return None
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    if not monitor:
        return None
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    class_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))

    def values(rect):
        return (rect.left, rect.top, rect.right, rect.bottom)

    return values(window), values(info.rcMonitor), class_buffer.value


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
        # will see uoinks under %USERPROFILE%\\Desktop -- not optimal, but
        # workable as a degraded mode.
        pass
    return fallback


def _windows_toast(title: str, body: str, icon_path: str | None = None) -> None:
    # Single-quote escape for PowerShell single-quoted strings.
    t = title.replace("'", "''")
    b = body.replace("'", "''")
    # v2.1: brand the balloon with the bundled uoink.ico when it's available,
    # so the notification carries the rust U rather than the generic blue
    # OS information icon. Fall back to SystemIcons::Information if the icon
    # is missing or can't be loaded (e.g. a corrupt file) -- a failed icon
    # load must never suppress the notification itself.
    if icon_path and os.path.isfile(icon_path):
        ip = icon_path.replace("'", "''")
        icon_line = (
            "try { $n.Icon = New-Object System.Drawing.Icon('" + ip + "') } "
            "catch { $n.Icon = [System.Drawing.SystemIcons]::Information };"
        )
    else:
        icon_line = "$n.Icon = [System.Drawing.SystemIcons]::Information;"
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        + icon_line +
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
