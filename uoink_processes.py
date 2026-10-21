"""POSIX child trees with a parent-death lifeline and a pinned process group.

The supervisor is outside the workload group. Its anchor stays alive (or an
unreaped child) until group cleanup ends, so the group ID cannot be recycled.
Only the supervisor and anchor signal that group; callers never kill a persisted PID.
Commands must retain their inherited group (yt-dlp, ffmpeg and our workers do).
Windows callers continue using their existing Popen / Job Object paths.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time


_lifelines: set[int] = set()


def _after_fork():
    # A library may fork without exec after a job starts. Such a child must
    # not keep its parent's ownership pipe alive after the parent crashes.
    for fd in _lifelines:
        os.close(fd)
    _lifelines.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def _send(fd, message):
    data = json.dumps(message).encode() + b"\n"
    while data:
        data = data[os.write(fd, data):]


def _receive(fd, timeout=None):
    deadline = None if timeout is None else time.monotonic() + timeout
    data = bytearray()
    while len(data) < 65536:
        remaining = None if deadline is None else max(0, deadline - time.monotonic())
        if not select.select([fd], [], [], remaining)[0]:
            raise TimeoutError("owned process handshake timed out")
        byte = os.read(fd, 1)
        if not byte:
            raise OSError("owned process supervisor closed without proof of cleanup")
        if byte == b"\n":
            return json.loads(data)
        data.extend(byte)
    raise OSError("invalid owned process handshake")


def _group_drained(pgid):
    """No executable members left. Zombies cannot run or hold file locks."""
    if sys.platform == "darwin":
        import ctypes
        from _platform import _darwin_libproc, darwin_observe
        lib = _darwin_libproc()
        lib.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p, ctypes.c_int]
        lib.proc_listpids.restype = ctypes.c_int
        ctypes.set_errno(0)
        size = lib.proc_listpids(2, pgid, None, 0)  # PROC_PGRP_ONLY
        if size < 0 or (size == 0 and ctypes.get_errno()):
            return False
        pids = (ctypes.c_int * (max(size // 4, 1) + 32))()
        ctypes.set_errno(0)
        count = lib.proc_listpids(2, pgid, pids, ctypes.sizeof(pids))
        if (count < 0 or count % 4 or count >= ctypes.sizeof(pids)
                or (count == 0 and ctypes.get_errno())):
            return False
        if count == 0:
            return darwin_observe(pgid).status == "dead"
        return all(darwin_observe(pid).status == "dead"
                   for pid in pids[:count // 4] if pid > 0)
    if sys.platform.startswith("linux"):
        for path in Path("/proc").iterdir():
            if not path.name.isdecimal():
                continue
            try:
                fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
                if int(fields[2]) == pgid and fields[0] not in {"Z", "X"}:
                    return False
            except FileNotFoundError:
                continue
            except (OSError, ValueError, IndexError):
                return False
        return True
    return False  # An unqualified platform cannot certify cleanup.


def _anchor(command, channel, supervisor_life):
    """Keep the group number reserved after the command exits."""
    os.setpgid(0, 0)
    try:
        child = subprocess.Popen(command, close_fds=True)
        _send(channel, {"pid": child.pid})
        for fd in (0, 1, 2):
            os.close(fd)
        while child.poll() is None:
            if select.select([supervisor_life], [], [], .05)[0]:
                os.killpg(os.getpid(), signal.SIGKILL)
        _send(channel, {"returncode": child.returncode})
    except BaseException as exc:
        try:
            _send(channel, {"error": type(exc).__name__})
        except OSError:
            # The supervisor may have died during either handshake write.
            os.killpg(os.getpid(), signal.SIGKILL)
    finally:
        os.close(channel)
    # If the supervisor itself crashes, its last writer closes. We are the
    # group leader and can still kill our own group without a stale-ID lookup.
    while True:
        if select.select([supervisor_life], [], [])[0]:
            os.killpg(os.getpid(), signal.SIGKILL)


def _supervise(lifeline, status, command):
    read_fd, write_fd = os.pipe()
    supervisor_read, supervisor_write = os.pipe()
    anchor = os.fork()  # Fresh, single-threaded interpreter; never the server.
    if anchor == 0:
        os.close(read_fd)
        os.close(supervisor_write)
        os.close(lifeline)
        os.close(status)
        try:
            _anchor(command, write_fd, supervisor_read)
        finally:
            os._exit(127)
    os.close(write_fd)
    os.close(supervisor_read)
    # Both sides setpgid before any command can be admitted or cleanup signaled.
    os.setpgid(anchor, anchor)
    for fd in (0, 1, 2):
        os.close(fd)
    result = {"returncode": -int(signal.SIGKILL), "cleaned": False}
    try:
        while True:
            ready = select.select([lifeline, read_fd], [], [])[0]
            if lifeline in ready:
                # Explicit close and OS close on parent death have identical
                # meaning. No descendant inherits the parent's writer FD.
                break
            message = _receive(read_fd)
            if "pid" in message:
                _send(status, {**message, "pgid": anchor})
            else:
                result.update(message)
                break
    except (OSError, ValueError):
        pass
    finally:
        # The anchor is still our unreaped child: no PID/PGID reuse window.
        started = time.monotonic()
        while not result["cleaned"]:
            try:
                # A fork already in the kernel when the first signal was
                # delivered can add a member. The pinned group is still ours.
                os.killpg(anchor, signal.SIGKILL)
            except ProcessLookupError:
                result["cleaned"] = True
                break
            except OSError:
                pass
            try:
                result["cleaned"] = _group_drained(anchor)
            except (OSError, ValueError, AttributeError):
                pass
            if not result["cleaned"]:
                # Callers have bounded waits. The supervisor retains the
                # anchor and admission locks if death cannot yet be proved;
                # parent death must not turn uncertainty into a free lock.
                time.sleep(.01 if time.monotonic() - started < 5 else .2)
        os.waitpid(anchor, 0)
        try:
            _send(status, result)
        except OSError:
            pass  # Parent died; cleanup still ran.
        os.close(status)
        os.close(lifeline)
        os.close(read_fd)
        os.close(supervisor_write)


class PosixChild:
    """The Popen subset used by server, vault I/O and receipt sessions.

    pid is the command PID. poll/wait report completion only after the group
    drains, even when the direct child has already exited. Missing supervisor
    evidence raises OSError; it never certifies descendant death.
    """

    def __init__(self, command, *, hold_fds=(), **kwargs):
        if os.name == "nt":
            raise OSError("POSIX ownership is unavailable on Windows")
        self.args = command
        self._lock = threading.RLock()
        self.returncode = None
        self.cleaned = False
        self._failure = None
        self._lifeline = None
        self._status = None
        life_read, life_write = os.pipe()
        status_read, status_write = os.pipe()
        self._lifeline, self._status = life_write, status_read
        _lifelines.add(life_write)
        kwargs.pop("start_new_session", None)  # The supervisor always owns a session.
        try:
            self._supervisor = subprocess.Popen(
                [sys.executable, "-B", str(Path(__file__).resolve()),
                 str(life_read), str(status_write), json.dumps([os.fspath(v) for v in command])],
                pass_fds=(life_read, status_write, *hold_fds), start_new_session=True, **kwargs)
        except BaseException:
            _lifelines.discard(life_write)
            os.close(life_write)
            os.close(status_read)
            raise
        finally:
            os.close(life_read)
            os.close(status_write)
        self.stdin, self.stdout, self.stderr = (
            self._supervisor.stdin, self._supervisor.stdout, self._supervisor.stderr)
        # Durable capture records follow the supervisor through descendant
        # cleanup, rather than becoming dead when only the command exits.
        self.ownership_pid = self._supervisor.pid
        self.pid = self.ownership_pid  # Retain an owner even if admission fails.
        try:
            started = _receive(status_read, 15)
            if "error" in started:
                if started["error"] == "FileNotFoundError":
                    raise FileNotFoundError(str(command[0]))
                raise OSError("owned child launch failed: " + started["error"])
            self.pid, self.pgid = started["pid"], started["pgid"]
        except BaseException:
            self.terminate()
            try:
                if self._supervisor.wait(timeout=10) != 0:
                    raise OSError("supervisor exited without cleanup proof")
            except BaseException as cleanup_error:
                pending = OSError("owned child admission failed; cleanup remains pending")
                pending.owned_process = self
                raise pending from cleanup_error
            os.close(status_read)
            self._status = None
            for stream in (self.stdin, self.stdout, self.stderr):
                if stream is not None:
                    stream.close()
            raise

    def poll(self):
        with self._lock:
            if self._failure:
                raise OSError(self._failure)
            if self.returncode is not None:
                return self.returncode
            if self._supervisor.poll() is None:
                return None
            try:
                result = _receive(self._status)
                while "pid" in result:  # Admission may have timed out before this frame.
                    result = _receive(self._status)
                if not result.get("cleaned"):
                    raise OSError("owned process group cleanup is unconfirmed")
                self.cleaned = True
                self.returncode = int(result["returncode"])
            except (OSError, ValueError) as exc:
                self._failure = str(exc)
                raise OSError(self._failure) from exc
            finally:
                self.terminate()
                os.close(self._status)
                self._status = None
            return self.returncode

    def wait(self, timeout=None):
        try:
            self._supervisor.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise subprocess.TimeoutExpired(self.args, timeout) from exc
        return self.poll()

    def communicate(self, input=None, timeout=None):
        try:
            output = self._supervisor.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise subprocess.TimeoutExpired(self.args, timeout, output=exc.output,
                                            stderr=exc.stderr) from exc
        self.poll()
        return output

    def terminate(self):
        with self._lock:
            if self._lifeline is not None:
                _lifelines.discard(self._lifeline)
                os.close(self._lifeline)
                self._lifeline = None

    kill = terminate


def run_owned(command, *, capture_output=False, timeout=None, check=False,
              input=None, **kwargs):
    """subprocess.run semantics for bounded POSIX downloads and probes."""
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("capture_output cannot be combined with stdout/stderr")
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input is not None:
        if kwargs.get("stdin") is not None:
            raise ValueError("input cannot be combined with stdin")
        kwargs["stdin"] = subprocess.PIPE
    proc = PosixChild(command, **kwargs)
    try:
        out, err = proc.communicate(input=input, timeout=timeout)
        result = subprocess.CompletedProcess(command, proc.returncode, out, err)
        if check:
            result.check_returncode()
        return result
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()


if __name__ == "__main__":
    _supervise(int(sys.argv[1]), int(sys.argv[2]), json.loads(sys.argv[3]))
