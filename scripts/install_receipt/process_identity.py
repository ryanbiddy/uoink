"""PID plus creation-time identity. Never stop a process by PID alone."""

from __future__ import annotations

import os
import time
from typing import Any

_FILETIME_EPOCH_OFFSET_100NS = 116444736000000000
_STILL_ACTIVE = 259
_PROCESS_START_TOLERANCE_MS = 2000


def current_created_ms() -> int | None:
    try:
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            return _windows_created_ms(kernel32.GetCurrentProcess())
        return _posix_created_ms(os.getpid())
    except Exception:
        return None


def created_ms_for_pid(pid: int) -> int | None:
    try:
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.restype = ctypes.c_void_p
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return None
            try:
                return _windows_created_ms(ctypes.c_void_p(handle))
            finally:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
        return _posix_created_ms(int(pid))
    except Exception:
        return None


def identity_for_pid(pid: int) -> dict[str, Any]:
    created = created_ms_for_pid(int(pid))
    return {
        "pid": int(pid),
        "created_ms": created,
        "observed_ms": int(time.time() * 1000),
    }


def liveness(pid: int, created_ms: int | None) -> str:
    """alive, dead, or unknown. Never signals the process on Windows."""
    try:
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.restype = ctypes.c_void_p
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                error = ctypes.get_last_error()
                return "dead" if error == 87 else "unknown"
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(
                        ctypes.c_void_p(handle), ctypes.byref(code)):
                    return "unknown"
                if int(code.value) != _STILL_ACTIVE:
                    return "dead"
                if created_ms is not None:
                    actual = _windows_created_ms(ctypes.c_void_p(handle))
                    if (actual is not None
                            and abs(actual - int(created_ms))
                            > _PROCESS_START_TOLERANCE_MS):
                        return "dead"
                return "alive"
            finally:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return "dead"
        except PermissionError:
            pass
        if created_ms is not None:
            actual = _posix_created_ms(int(pid))
            if (actual is not None
                    and abs(actual - int(created_ms))
                    > _PROCESS_START_TOLERANCE_MS):
                return "dead"
        return "alive"
    except Exception:
        return "unknown"


def matches(identity: dict[str, Any], pid: int | None = None) -> bool:
    if not isinstance(identity, dict):
        return False
    expected_pid = identity.get("pid")
    if type(expected_pid) is not int or expected_pid <= 0:
        return False
    if pid is not None and int(pid) != expected_pid:
        return False
    return liveness(expected_pid, identity.get("created_ms")) == "alive"


def executable_for_pid(pid: int) -> str | None:
    try:
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.restype = ctypes.c_void_p
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return None
            try:
                return _windows_executable(ctypes.c_void_p(handle))
            finally:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
        return os.readlink(f"/proc/{int(pid)}/exe")
    except Exception:
        return None


def identity_from_popen(proc) -> dict[str, Any]:
    """Identity taken from the live Popen object, not a later PID lookup."""
    pid = int(getattr(proc, "pid", 0) or 0)
    created = None
    exe = None
    if pid:
        for _ in range(5):
            created = created_ms_for_pid(pid)
            exe = executable_for_pid(pid)
            if created is not None and exe:
                break
            time.sleep(0.02)
    return {
        "pid": pid,
        "created_ms": created,
        "executable": exe,
        "observed_ms": int(time.time() * 1000),
        "from_popen": True,
        "poll": proc.poll() if hasattr(proc, "poll") else None,
    }


def exact_identity_on_handle(observed: dict[str, Any],
                             expected: dict[str, Any]) -> bool:
    """Complete exact pid+creation+executable. No 2s tolerance. Missing fails."""
    if not isinstance(observed, dict) or not isinstance(expected, dict):
        return False
    pid = observed.get("pid")
    if type(pid) is not int or pid <= 0 or pid != expected.get("pid"):
        return False
    expected_created = expected.get("created_ms")
    if type(expected_created) is not int:
        return False
    handle = observed.get("handle")
    if handle is not None and os.name == "nt":
        actual_created = _windows_created_ms(handle)
        actual_exe = _windows_executable(handle)
    else:
        actual_created = observed.get("created_ms")
        actual_exe = observed.get("executable") or executable_for_pid(pid)
    if type(actual_created) is not int or actual_created != expected_created:
        return False
    expected_exe = expected.get("executable")
    if not expected_exe or not actual_exe:
        return False
    return os.path.normcase(os.path.normpath(str(actual_exe))) == os.path.normcase(
        os.path.normpath(str(expected_exe)))


def wait_exit_on_handle(handle, *, timeout: float) -> dict[str, Any]:
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint
    ms = max(1, int(timeout * 1000))
    waited = kernel32.WaitForSingleObject(handle, ms)
    code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    got = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    exit_code = int(code.value) if got else None
    still = exit_code == _STILL_ACTIVE
    return {
        "wait_code": int(waited),
        "exit": None if still else exit_code,
        "stopped": not still,
        "unknown_not_dead": still,
    }


def _windows_executable(handle) -> str | None:
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not isinstance(handle, ctypes.c_void_p):
        handle = ctypes.c_void_p(handle)
    length = ctypes.c_uint(32768)
    buf = ctypes.create_unicode_buffer(length.value)
    query = getattr(kernel32, "QueryFullProcessImageNameW", None)
    if query is None:
        return None
    query.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_uint)]
    query.restype = ctypes.c_int
    if not query(handle, 0, buf, ctypes.byref(length)):
        return None
    text = buf.value
    return text or None


def _windows_created_ms(handle) -> int | None:
    import ctypes
    import ctypes.wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not isinstance(handle, ctypes.c_void_p):
        handle = ctypes.c_void_p(handle)
    creation, exit_, kernel, user = (ctypes.wintypes.FILETIME() for _ in range(4))
    if not kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_),
            ctypes.byref(kernel), ctypes.byref(user)):
        return None
    value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    return (value - _FILETIME_EPOCH_OFFSET_100NS) // 10_000


def _posix_created_ms(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="ascii",
                  errors="replace") as handle:
            stat = handle.read()
        with open("/proc/stat", "r", encoding="ascii",
                  errors="replace") as handle:
            boot = next(int(line.split()[1])
                        for line in handle if line.startswith("btime "))
        ticks = int(stat.rsplit(")", 1)[1].split()[19])
        hertz = os.sysconf("SC_CLK_TCK")
        return boot * 1000 + (ticks * 1000) // hertz
    except (OSError, ValueError, IndexError, StopIteration, AttributeError):
        return None
