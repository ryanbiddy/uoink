"""Bounded JSON-RPC stdio session and owned process-tree cleanup.

A nonresponding or partial-frame child must produce a bounded failure and
complete retained traffic. The complete send+receive operation is deadline
bound. stdout is pumped in chunks so partial live frames are retained before
newline or exit. stderr is drained continuously into files (not truncated).
Windows Job Objects are assigned while the child is still suspended; assignment
failure is a closed refusal, never a silent continue. Cleanup waits for
descendants on the owned job. Unknown PIDs and process names are never targeted.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from p4_common import IsolationError


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
CREATE_SUSPENDED = 0x00000004
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9
JobObjectBasicProcessIdList = 3
PROCESS_SUSPEND_RESUME = 0x0800
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_MORE_DATA = 234
_STDERR_MEM_CAP = 8_000_000


def _kernel32():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = wintypes.HANDLE
    k32.CreateJobObjectW.restype = handle
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.SetInformationJobObject.argtypes = [
        handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [handle, handle]
    k32.QueryInformationJobObject.restype = wintypes.BOOL
    k32.QueryInformationJobObject.argtypes = [
        handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    k32.TerminateJobObject.restype = wintypes.BOOL
    k32.TerminateJobObject.argtypes = [handle, wintypes.UINT]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [handle]
    k32.OpenProcess.restype = handle
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.TerminateProcess.restype = wintypes.BOOL
    k32.TerminateProcess.argtypes = [handle, wintypes.UINT]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.GetExitCodeProcess.argtypes = [handle, ctypes.POINTER(wintypes.DWORD)]
    k32.ResumeThread.restype = wintypes.DWORD
    k32.ResumeThread.argtypes = [handle]
    return k32


def _ntdll():
    import ctypes
    from ctypes import wintypes

    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.restype = ctypes.c_long
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    return ntdll


class _JOBOBJECT_BASIC_LIMIT_INFORMATION:
    @staticmethod
    def struct():
        import ctypes
        from ctypes import wintypes

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        return JOBOBJECT_EXTENDED_LIMIT_INFORMATION


def _pid_list_struct(capacity: int = 256):
    import ctypes
    from ctypes import wintypes

    class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
        _fields_ = [
            ("NumberOfAssignedProcesses", wintypes.DWORD),
            ("NumberOfProcessIdsInList", wintypes.DWORD),
            ("ProcessIdList", ctypes.c_size_t * capacity),
        ]

    return JOBOBJECT_BASIC_PROCESS_ID_LIST


def create_kill_job():
    """Create a job with KILL_ON_JOB_CLOSE. None on non-Windows."""
    if os.name != "nt":
        return None
    import ctypes

    k32 = _kernel32()
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info_cls = _JOBOBJECT_BASIC_LIMIT_INFORMATION.struct()
    info = info_cls()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation,
        ctypes.byref(info), ctypes.sizeof(info),
    ):
        k32.CloseHandle(job)
        return None
    return job


def assign_popen_to_job(job, popen) -> bool:
    """Assign using the Popen process handle. Never OpenProcess by unverified PID."""
    if job is None or os.name != "nt":
        return False
    handle = getattr(popen, "_handle", None)
    if not handle:
        return False
    return bool(_kernel32().AssignProcessToJobObject(job, handle))


def resume_popen(popen) -> bool:
    if os.name != "nt":
        return True
    handle = getattr(popen, "_handle", None)
    if not handle:
        return False
    status = _ntdll().NtResumeProcess(handle)
    return int(status) >= 0


def terminate_popen_handle(popen, exit_code: int = 1) -> bool:
    if os.name != "nt":
        try:
            popen.kill()
            return True
        except OSError:
            return False
    handle = getattr(popen, "_handle", None)
    if not handle:
        return False
    return bool(_kernel32().TerminateProcess(handle, exit_code))


def query_job_process_ids(job) -> dict:
    """Affirmative job membership. Query failure is not an empty list."""
    if os.name != "nt":
        return {"ok": True, "pids": [], "error": None, "job_empty": True, "assigned": 0}
    if job is None:
        return {"ok": False, "pids": None, "error": "no_job", "job_empty": False, "assigned": None}
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    capacity = 256
    last_error = None
    for _ in range(4):
        cls = _pid_list_struct(capacity)
        info = cls()
        written = wintypes.DWORD(0)
        ok = k32.QueryInformationJobObject(
            job, JobObjectBasicProcessIdList, ctypes.byref(info),
            ctypes.sizeof(info), ctypes.byref(written),
        )
        if ok:
            count = int(info.NumberOfProcessIdsInList)
            assigned = int(info.NumberOfAssignedProcesses)
            pids = [int(info.ProcessIdList[i]) for i in range(min(count, capacity))]
            return {
                "ok": True,
                "pids": pids,
                "error": None,
                "job_empty": assigned == 0 and count == 0,
                "assigned": assigned,
            }
        last_error = ctypes.get_last_error()
        if last_error == ERROR_MORE_DATA:
            capacity = min(capacity * 2, 4096)
            continue
        return {
            "ok": False,
            "pids": None,
            "error": f"QueryInformationJobObject:{last_error}",
            "job_empty": False,
            "assigned": None,
        }
    return {
        "ok": False,
        "pids": None,
        "error": f"QueryInformationJobObject:{last_error}",
        "job_empty": False,
        "assigned": None,
    }


def job_process_ids(job) -> list[int]:
    """PIDs currently assigned to the owned job. Empty list is not query-failure credit."""
    result = query_job_process_ids(job)
    if not result["ok"] or result["pids"] is None:
        return []
    return list(result["pids"])


def pid_still_active(pid: int, *, owned_pids: set[int]) -> bool:
    """Query liveness only for a PID previously observed on the owned job."""
    if pid not in owned_pids or pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return int(code.value) == STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def _read_chunk(stream, n: int = 4096) -> bytes:
    if stream is None:
        return b""
    read1 = getattr(stream, "read1", None)
    if callable(read1):
        return read1(n) or b""
    try:
        return os.read(stream.fileno(), n)
    except (OSError, ValueError):
        return b""


class OwnedProcess:
    """Popen wrapper that owns the child process tree."""

    def __init__(self, popen: subprocess.Popen, *, label: str = "p4-child",
                 job=None, job_assigned: bool = False, fail_closed_on_job: bool = True):
        self.popen = popen
        self.label = label
        self.pid = popen.pid
        self._job = job
        self._job_assigned = bool(job_assigned)
        self._closed = False
        self._fail_closed_on_job = fail_closed_on_job
        self._owned_pids: set[int] = {int(popen.pid)} if popen.pid else set()
        self._assignment_error = None
        self._cleanup_result = None
        if os.name == "nt" and self._job is None:
            self._assign_windows_job()

    def _assign_windows_job(self) -> None:
        """Post-launch assignment. Prefer spawn_owned (suspended) instead."""
        try:
            job = create_kill_job()
            if not job:
                self._assignment_error = "CreateJobObjectW failed"
                if self._fail_closed_on_job:
                    terminate_popen_handle(self.popen)
                    raise IsolationError("owned job could not be created; fail closed")
                return
            if not assign_popen_to_job(job, self.popen):
                _kernel32().CloseHandle(job)
                self._assignment_error = "AssignProcessToJobObject failed"
                if self._fail_closed_on_job:
                    terminate_popen_handle(self.popen)
                    raise IsolationError("job assignment failed closed")
                return
            self._job = job
            self._job_assigned = True
            for pid in job_process_ids(job):
                self._owned_pids.add(pid)
        except IsolationError:
            raise
        except Exception as exc:
            self._job = None
            self._job_assigned = False
            self._assignment_error = f"{type(exc).__name__}: {exc}"
            if self._fail_closed_on_job:
                terminate_popen_handle(self.popen)
                raise IsolationError(
                    f"job assignment failed closed: {self._assignment_error}"
                ) from exc

    def poll(self):
        return self.popen.poll()

    def wait(self, timeout=None):
        return self.popen.wait(timeout=timeout)

    def descendant_snapshot(self) -> dict:
        query = query_job_process_ids(self._job) if self._job is not None else {
            "ok": False, "pids": None, "error": "no_job", "job_empty": False, "assigned": None,
        }
        pids = list(query["pids"] or []) if query.get("ok") else []
        for pid in pids:
            self._owned_pids.add(pid)
        return {
            "job_assigned": self._job_assigned,
            "job_pids": pids,
            "owned_pids": sorted(self._owned_pids),
            "parent_pid": self.pid,
            "parent_exit": self.popen.poll(),
            "job_query_ok": bool(query.get("ok")),
            "job_empty_affirmed": bool(query.get("ok") and query.get("job_empty")),
            "job_query_error": query.get("error"),
            "identity_uncertain": not bool(query.get("ok")),
        }

    def terminate_tree(self, timeout: float = 5.0) -> dict:
        """Confirmed cleanup of the owned tree. Does not kill by name or a
        foreign PID."""
        if self._closed and self._cleanup_result is not None:
            return dict(self._cleanup_result)
        snapshot_before = self.descendant_snapshot()
        result = {
            "pid": self.pid,
            "label": self.label,
            "job_assigned": self._job_assigned,
            "already_exited": self.popen.poll() is not None,
            "exit_code": self.popen.poll(),
            "assignment_error": self._assignment_error,
            "descendants_before": snapshot_before,
        }
        if os.name == "nt" and self._job is not None:
            try:
                _kernel32().TerminateJobObject(self._job, 1)
            except Exception as exc:
                result["terminate_job_error"] = str(exc)
        if self.popen.poll() is None:
            try:
                self.popen.terminate()
            except OSError as exc:
                result["terminate_error"] = str(exc)
            try:
                self.popen.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    self.popen.kill()
                except OSError as exc:
                    result["kill_error"] = str(exc)
                try:
                    self.popen.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    result["still_alive"] = True
        deadline = time.monotonic() + timeout
        owned = set(self._owned_pids)
        remaining = []
        while time.monotonic() < deadline:
            remaining = [
                pid for pid in sorted(owned)
                if pid != self.pid and pid_still_active(pid, owned_pids=owned)
            ]
            live_query = query_job_process_ids(self._job) if self._job is not None else {
                "ok": False, "job_empty": False,
            }
            if (
                not remaining
                and self.popen.poll() is not None
                and live_query.get("ok")
                and live_query.get("job_empty")
            ):
                break
            time.sleep(0.05)
        result["exit_code"] = self.popen.poll()
        after = self.descendant_snapshot()
        result["descendants_after"] = after
        result["descendants_remaining"] = remaining
        result["descendants_exited"] = not remaining
        result["job_query_ok"] = bool(after.get("job_query_ok"))
        result["job_empty_affirmed"] = bool(after.get("job_empty_affirmed"))
        result["identity_uncertain"] = bool(after.get("identity_uncertain"))
        result["job_query_error"] = after.get("job_query_error")
        self._close_job()
        parent_exited = self.popen.poll() is not None
        result["parent_exited"] = parent_exited
        result["cleaned"] = bool(
            parent_exited
            and not remaining
            and result["job_query_ok"]
            and result["job_empty_affirmed"]
            and not result["identity_uncertain"]
        )
        self._cleanup_result = dict(result)
        return result

    def _close_job(self) -> None:
        if self._closed:
            return
        self._closed = True
        job = self._job
        self._job = None
        if job and os.name == "nt":
            try:
                _kernel32().CloseHandle(job)
            except Exception:
                pass

    def close(self) -> dict:
        return self.terminate_tree()


def spawn_owned(command, *, cwd, env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                label: str = "p4-child", fail_closed_on_job: bool = True) -> OwnedProcess:
    """Launch an owned child. On Windows: create job, start suspended, assign,
    resume. Assignment failure kills the suspended child and refuses."""
    if os.name != "nt":
        popen = subprocess.Popen(
            command, cwd=str(cwd), env=env,
            stdin=stdin, stdout=stdout, stderr=stderr,
            start_new_session=True,
        )
        return OwnedProcess(
            popen, label=label, job=None, job_assigned=False,
            fail_closed_on_job=False,
        )

    job = create_kill_job()
    if job is None and fail_closed_on_job:
        raise IsolationError("owned job could not be created; fail closed")

    flags_breakaway = (
        CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        | CREATE_SUSPENDED | CREATE_BREAKAWAY_FROM_JOB
    )
    flags_plain = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED
    popen = None
    last_err = None
    for flags in (flags_breakaway, flags_plain):
        try:
            popen = subprocess.Popen(
                command, cwd=str(cwd), env=env,
                stdin=stdin, stdout=stdout, stderr=stderr,
                creationflags=flags,
            )
            break
        except OSError as exc:
            last_err = exc
            popen = None
    if popen is None:
        if job is not None:
            try:
                _kernel32().CloseHandle(job)
            except Exception:
                pass
        raise IsolationError(f"owned child launch failed: {last_err}")

    assigned = False
    if job is not None:
        assigned = assign_popen_to_job(job, popen)
    if not assigned:
        terminate_popen_handle(popen)
        try:
            popen.wait(timeout=2)
        except Exception:
            pass
        if job is not None:
            try:
                _kernel32().CloseHandle(job)
            except Exception:
                pass
        if fail_closed_on_job:
            raise IsolationError("job assignment failed closed")
        raise IsolationError("job assignment failed closed")

    if not resume_popen(popen):
        terminate_popen_handle(popen)
        try:
            popen.wait(timeout=2)
        except Exception:
            pass
        try:
            _kernel32().CloseHandle(job)
        except Exception:
            pass
        raise IsolationError("resume after job assignment failed")

    owned = OwnedProcess(
        popen, label=label, job=job, job_assigned=True,
        fail_closed_on_job=fail_closed_on_job,
    )
    for pid in job_process_ids(job):
        owned._owned_pids.add(pid)
    return owned


class BoundedStdio:
    """Deadline-aware JSON-RPC over newline-delimited stdio.

    The complete send+receive is bound. stdout is chunk-pumped so a partial
    live frame is retained before newline/exit. stderr is written in full to
    files. close() drains readers before terminating the owned tree.
    """

    def __init__(self, owned: OwnedProcess, *, default_timeout_s: float = 15.0,
                 retain_dir: Path | None = None):
        if owned.popen.stdin is None or owned.popen.stdout is None or owned.popen.stderr is None:
            raise IsolationError("owned stdio child must expose pipes")
        self.owned = owned
        self.proc = owned.popen
        self.default_timeout_s = float(default_timeout_s)
        self.stdout_q: queue.Queue = queue.Queue()
        self.stderr_chunks: list[bytes] = []
        self.retained: list[dict] = []
        self.partial_stdout = b""
        self._stderr_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._write_thread: threading.Thread | None = None
        self._stderr_overflow = False
        self._stop = threading.Event()
        self._retain_dir = Path(retain_dir) if retain_dir is not None else None
        if self._retain_dir is not None:
            self._retain_dir.mkdir(parents=True, exist_ok=True)
        self._stdout_file = self._open_retain("stdout.bin")
        self._stderr_file = self._open_retain("stderr.bin")
        self._stdin_file = self._open_retain("stdin.bin")
        self._partial_file = self._open_retain("stdout.partial.bin")
        self._stdout_thread = threading.Thread(target=self._pump_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._pump_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _open_retain(self, name: str):
        if self._retain_dir is None:
            return None
        return (self._retain_dir / name).open("ab")

    def _write_retain(self, handle, chunk: bytes) -> None:
        if handle is None or not chunk:
            return
        try:
            handle.write(chunk)
            handle.flush()
        except OSError:
            return

    def _pump_stdout(self) -> None:
        stream = self.proc.stdout
        buf = b""
        try:
            while True:
                raw = _read_chunk(stream)
                if not raw:
                    if buf:
                        self.partial_stdout = buf
                        self._write_retain(self._partial_file, buf)
                        self.stdout_q.put(("partial", buf))
                    self.stdout_q.put(None)
                    break
                self._write_retain(self._stdout_file, raw)
                buf += raw
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self.stdout_q.put(line + b"\n")
        except (OSError, ValueError) as exc:
            if buf:
                self.partial_stdout = buf
                self._write_retain(self._partial_file, buf)
                self.stdout_q.put(("partial", buf))
            self.stdout_q.put(("error", exc))

    def _pump_stderr(self) -> None:
        stream = self.proc.stderr
        try:
            while True:
                chunk = _read_chunk(stream)
                if not chunk:
                    break
                self._write_retain(self._stderr_file, chunk)
                with self._stderr_lock:
                    held = sum(len(part) for part in self.stderr_chunks)
                    if held + len(chunk) <= _STDERR_MEM_CAP:
                        self.stderr_chunks.append(chunk)
                    else:
                        self._stderr_overflow = True
        except (OSError, ValueError):
            return

    def stderr_bytes(self) -> bytes:
        with self._stderr_lock:
            overflow = self._stderr_overflow
            held = b"".join(self.stderr_chunks)
        if overflow and self._retain_dir is not None:
            path = self._retain_dir / "stderr.bin"
            if path.is_file():
                try:
                    return path.read_bytes()
                except OSError:
                    return held
        return held

    def stderr_text(self, limit: int = 8000) -> str:
        raw = self.stderr_bytes()
        if limit is None or limit <= 0:
            return raw.decode("utf-8", "replace")
        return raw[-limit:].decode("utf-8", "replace")

    def _retain_params(self, params):
        if params is None:
            return None
        try:
            encoded = json.dumps(params, ensure_ascii=False)
        except (TypeError, ValueError):
            return {"_unserializable": True}
        raw = encoded.encode("utf-8")
        if len(raw) > 4096:
            return {"_truncated": True, "bytes": len(raw)}
        return params

    def _bounded_write(self, raw_out: bytes, deadline: float) -> str | None:
        error_box: list[BaseException] = []

        def writer():
            try:
                with self._write_lock:
                    stdin = self.proc.stdin
                    if stdin is None:
                        raise OSError("stdin already closed")
                    stdin.write(raw_out)
                    stdin.flush()
            except BaseException as exc:
                error_box.append(exc)

        thread = threading.Thread(target=writer, daemon=True)
        self._write_thread = thread
        self._write_retain(self._stdin_file, raw_out)
        thread.start()
        remaining = max(0.01, deadline - time.monotonic())
        thread.join(timeout=remaining)
        if thread.is_alive():
            return "stdin_write_timeout"
        if error_box:
            exc = error_box[0]
            return f"{type(exc).__name__}: {exc}"
        return None

    def notify(self, method: str, params=None) -> None:
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        raw = (json.dumps(message) + "\n").encode("utf-8")
        deadline = time.monotonic() + self.default_timeout_s
        error = self._bounded_write(raw, deadline)
        self.retained.append({
            "kind": "notify", "method": method, "params": self._retain_params(params),
            "error": error,
        })

    def rpc(self, req_id, method, params=None, *, timeout_s: float | None = None):
        timeout = self.default_timeout_s if timeout_s is None else float(timeout_s)
        started = time.perf_counter_ns()
        deadline = time.monotonic() + timeout
        if self.proc.poll() is not None:
            record = {
                "kind": "rpc", "id": req_id, "method": method,
                "params": self._retain_params(params),
                "elapsed_ms": 0.0, "error": f"child_already_exited:{self.proc.returncode}",
                "reply": None, "raw": b"", "stderr_tail": self.stderr_text(),
            }
            self.retained.append(record)
            return None, 0.0, b"", record["error"]
        message = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            message["params"] = params
        raw_out = (json.dumps(message) + "\n").encode("utf-8")
        write_error = self._bounded_write(raw_out, deadline)
        if write_error:
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            record = {
                "kind": "rpc", "id": req_id, "method": method,
                "params": self._retain_params(params),
                "elapsed_ms": elapsed_ms, "error": write_error,
                "reply": None, "raw": b"", "stderr_tail": self.stderr_text(),
                "child_exit": self.proc.poll(),
            }
            self.retained.append(record)
            return None, elapsed_ms, b"", write_error
        leftover = []
        error = None
        parsed = None
        raw_in = b""
        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            try:
                item = self.stdout_q.get(timeout=min(0.2, remaining))
            except queue.Empty:
                if self.proc.poll() is not None:
                    error = f"child_exited:{self.proc.returncode}"
                    break
                continue
            if item is None:
                error = f"stdout_eof:{self.proc.returncode}"
                break
            if isinstance(item, tuple) and item and item[0] == "error":
                error = f"{type(item[1]).__name__}: {item[1]}"
                break
            if isinstance(item, tuple) and item and item[0] == "partial":
                leftover.append({"kind": "partial_live_frame", "bytes": len(item[1])})
                raw_in = item[1]
                continue
            raw_in = item
            try:
                candidate = json.loads(item)
            except (ValueError, UnicodeError):
                leftover.append({"kind": "partial_or_non_json", "bytes": len(item)})
                continue
            if not isinstance(candidate, dict):
                leftover.append({"kind": "non_object", "value": candidate})
                continue
            if "id" in candidate and candidate.get("id") == req_id and "method" not in candidate:
                parsed = candidate
                error = None
                break
            leftover.append({"kind": "unmatched_frame", "message": candidate})
        else:
            if error is None:
                error = "timeout"
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        record = {
            "kind": "rpc", "id": req_id, "method": method,
            "params": self._retain_params(params),
            "elapsed_ms": elapsed_ms, "error": error, "reply": parsed,
            "raw_bytes": len(raw_in), "unmatched": leftover,
            "stderr_tail": self.stderr_text(2000),
            "child_exit": self.proc.poll(),
            "partial_stdout_bytes": len(self.partial_stdout),
        }
        self.retained.append(record)
        return parsed, elapsed_ms, raw_in, error

    def close_stdin(self) -> None:
        try:
            stdin = self.proc.stdin
            if stdin is not None:
                stdin.close()
        except OSError:
            pass

    def _close_retain_files(self) -> None:
        for handle in (self._stdout_file, self._stderr_file, self._stdin_file, self._partial_file):
            if handle is None:
                continue
            try:
                handle.flush()
                handle.close()
            except OSError:
                pass
        self._stdout_file = self._stderr_file = self._stdin_file = self._partial_file = None

    def close(self, timeout: float = 5.0) -> dict:
        writer_pending = self._write_thread is not None and self._write_thread.is_alive()
        cleanup = self.owned.terminate_tree(timeout=timeout)
        if self._write_thread is not None:
            self._write_thread.join(timeout=1.0)
        if self._write_thread is None or not self._write_thread.is_alive():
            self.close_stdin()
        else:
            cleanup["stdin_left_open_writer_pending"] = True
        drain_deadline = time.monotonic() + min(2.0, timeout)
        while time.monotonic() < drain_deadline:
            if not self._stdout_thread.is_alive() and not self._stderr_thread.is_alive():
                break
            time.sleep(0.02)
        self._stdout_thread.join(timeout=1.0)
        self._stderr_thread.join(timeout=1.0)
        self._stop.set()
        self._close_retain_files()
        writer_exited = self._write_thread is None or not self._write_thread.is_alive()
        stdout_drained = not self._stdout_thread.is_alive()
        stderr_drained = not self._stderr_thread.is_alive()
        drain_uncertain = not (writer_exited and stdout_drained and stderr_drained)
        cleanup["stderr_tail"] = self.stderr_text()
        cleanup["stderr_bytes"] = len(self.stderr_bytes())
        cleanup["retained_events"] = len(self.retained)
        cleanup["partial_stdout_bytes"] = len(self.partial_stdout)
        cleanup["retain_dir"] = str(self._retain_dir) if self._retain_dir else None
        cleanup["stdout_drained"] = stdout_drained
        cleanup["stderr_drained"] = stderr_drained
        cleanup["writer_exited"] = writer_exited
        cleanup["writer_was_pending"] = writer_pending
        cleanup["drain_uncertain"] = drain_uncertain
        if drain_uncertain or cleanup.get("identity_uncertain"):
            cleanup["cleaned"] = False
        return cleanup
