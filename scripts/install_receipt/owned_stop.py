"""Owned helper stop via the held Popen handle.

Never taskkill by PID. Never authorize a kill from missing/tolerant creation
identity. Unknown is not dead. Wait for confirmed exit and record the code.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .process_identity import (
    executable_for_pid,
    exact_identity_on_handle,
    identity_from_popen,
    wait_exit_on_handle,
)
from .validation import C22ValidationError, port_is_open


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
PROCESS_SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
STILL_ACTIVE = 259


def _windows_open_terminating_handle(pid: int):
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    access = (PROCESS_QUERY_LIMITED_INFORMATION
              | PROCESS_TERMINATE
              | PROCESS_SYNCHRONIZE)
    handle = kernel32.OpenProcess(access, False, int(pid))
    if not handle:
        return None, ctypes.get_last_error()
    return ctypes.c_void_p(handle), 0


def terminate_held_popen(proc: subprocess.Popen, *,
                         expected: dict[str, Any],
                         timeout: float = 15.0) -> dict[str, Any]:
    """Terminate only the process represented by *proc* after identity check
    on the same held handle. Wait for confirmed exit."""
    result: dict[str, Any] = {
        "method": "popen_handle",
        "pid": proc.pid,
        "taskkill": False,
    }
    checked = identity_from_popen(proc)
    result["checked_identity"] = checked
    if not exact_identity_on_handle(checked, expected):
        result["refused"] = True
        result["reason"] = (
            "owned stop refused: held handle identity does not exactly match "
            "the recorded executable/creation pair"
        )
        result["exit"] = proc.poll()
        return result
    if proc.poll() is not None:
        result["already_exited"] = True
        result["exit"] = proc.returncode
        result["stopped"] = True
        return result
    try:
        proc.terminate()
    except OSError as exc:
        result["terminate_error"] = str(exc)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["kill_error"] = str(exc)
    result["exit"] = proc.returncode
    result["stopped"] = proc.poll() is not None
    if not result["stopped"]:
        result["unknown_not_dead"] = True
    return result


def terminate_via_exact_handle(*, pid: int, expected: dict[str, Any],
                               timeout: float = 15.0) -> dict[str, Any]:
    """Open QUERY|TERMINATE on pid, check complete identity on that handle,
    then terminate and wait. Missing identity never authorizes a kill."""
    result: dict[str, Any] = {
        "method": "exact_terminating_handle",
        "pid": pid,
        "taskkill": False,
    }
    expected_exe = expected.get("executable")
    expected_created = expected.get("created_ms")
    if type(pid) is not int or pid <= 0:
        result["refused"] = True
        result["reason"] = "missing pid is not dead"
        result["stopped"] = False
        return result
    if expected_created is None or type(expected_created) is not int:
        result["refused"] = True
        result["reason"] = "missing creation identity is unknown, not dead"
        result["stopped"] = False
        return result
    if not expected_exe:
        result["refused"] = True
        result["reason"] = "missing executable identity is unknown, not dead"
        result["stopped"] = False
        return result
    if os.name != "nt":
        live_exe = executable_for_pid(pid)
        if live_exe is None or not _same_exe(live_exe, expected_exe):
            result["refused"] = True
            result["reason"] = "posix executable identity did not match"
            result["stopped"] = False
            return result
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            result["stopped"] = True
            result["exit"] = None
            return result
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                result["stopped"] = True
                result["exit"] = None
                return result
            time.sleep(0.05)
        result["unknown_not_dead"] = True
        result["stopped"] = False
        return result

    import ctypes
    handle, error = _windows_open_terminating_handle(pid)
    if not handle:
        result["refused"] = True
        result["reason"] = (
            f"could not open terminating handle (winerror={error}); "
            "unknown is not dead"
        )
        result["stopped"] = False
        return result
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        checked = exact_identity_on_handle(
            {"pid": pid, "handle": handle}, expected)
        result["handle_checked"] = True
        if not checked:
            result["refused"] = True
            result["reason"] = (
                "terminating handle identity did not exactly match executable "
                "and creation time"
            )
            result["stopped"] = False
            return result
        kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.TerminateProcess.restype = ctypes.c_int
        if not kernel32.TerminateProcess(handle, 1):
            result["terminate_error"] = ctypes.get_last_error()
        waited = wait_exit_on_handle(handle, timeout=timeout)
        result.update(waited)
        return result
    finally:
        kernel32.CloseHandle(handle)


def _same_exe(left: str, right: str) -> bool:
    try:
        return os.path.normcase(os.path.normpath(left)) == os.path.normcase(
            os.path.normpath(right))
    except OSError:
        return False


def wait_port_freed(port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_is_open("127.0.0.1", port):
            return True
        time.sleep(0.05)
    return not port_is_open("127.0.0.1", port)


def require_owned_handle(record: dict[str, Any]) -> subprocess.Popen:
    proc = record.get("popen")
    if not isinstance(proc, subprocess.Popen):
        raise C22ValidationError(
            "owned stop requires the actual Popen process handle; "
            "pid-only stop is refused")
    return proc
