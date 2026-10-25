"""Per-user helper recovery. No server imports, services or third-party modules."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
# The Windows embedded interpreter does not add the script directory.
sys.path.insert(0, str(HERE))
STATE_FILE = "helper-recovery.json"
STOP_FILE = "helper-stop.json"
WINDOW = 600
BACKOFF = (5, 15, 45)
ACTION = "Run uoink doctor, check helper-output.log and server.log, then open Uoink to try again."


def data_root() -> Path:
    import _platform
    import uoink_install_isolation as isolation
    # Readers may be imported before server.py has applied the binding.
    if os.environ.get("UOINK_ISOLATED_PROFILE"):
        return Path(os.environ["UOINK_ISOLATED_PROFILE"]).resolve()
    return isolation.data_root(_platform.user_data_dir())


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict:
    try:
        if path.stat().st_size > 32768:
            raise ValueError("state file too large")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("state must be an object")
        return value
    except FileNotFoundError:
        return {}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".recovery-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def status(root: Path | None = None) -> dict:
    """Safe for public health: no paths, tokens, command lines or raw exceptions."""
    try:
        state = read_json(Path(root or data_root()) / STATE_FILE)
    except (OSError, ValueError):
        return {"available": False, "status": "unreadable",
                "reason": "Helper recovery state could not be read.", "action": ACTION}
    fields = ("schema_version", "status", "last_exit_code", "restart_count",
              "last_start_at", "last_stop_at", "ready_at", "reason", "action")
    return {"available": bool(state), **{k: state.get(k) for k in fields}}


def request_stop(root: Path | None = None, reason: str = "quit") -> None:
    write_json((root or data_root()) / STOP_FILE, {"requested_at": stamp(), "reason": reason})


def login_session() -> str:
    """Stable across supervisor retries, different after a new OS login."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = wintypes.HANDLE()
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            # TOKEN_STATISTICS starts with TokenId then AuthenticationId (LUIDs).
            buffer = ctypes.create_string_buffer(128)
            needed = wintypes.DWORD()
            if not advapi.GetTokenInformation(handle, 10, buffer, len(buffer), ctypes.byref(needed)):
                raise ctypes.WinError(ctypes.get_last_error())
            return "windows:" + buffer.raw[8:16].hex()
        finally:
            kernel.CloseHandle(handle)
    if sys.platform == "darwin":
        result = subprocess.run(["/bin/launchctl", "print", f"gui/{os.getuid()}"],
                                capture_output=True, text=True, check=True, timeout=5)
        match = re.search(r"(?m)^\s*asid = (\d+)\s*$", result.stdout)
        if not match:
            raise OSError("Cannot identify the login session")
        boot = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.boottime"],
                              capture_output=True, text=True, check=True, timeout=5)
        return "macos:" + match[1] + ":" + boot.stdout.strip()
    return "posix:" + str(os.getsid(0))


@contextmanager
def admission(root: Path):
    """Kernel-owned lock, automatically released after a supervisor crash."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / "helper-supervisor.lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                yield False
                return
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
        try:
            yield True
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def ready(url: str, run_id: str, pid: int) -> bool:
    try:
        # Never use an HTTP proxy for loopback readiness.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=0.5) as reply:
            body = json.loads(reply.read(32768))
            return (reply.status == 200 and body.get("ok") is True
                    and body.get("supervisor_run_id") == run_id and body.get("pid") == pid)
    except (OSError, ValueError, AttributeError):
        return False


def notify_failure(state: dict) -> None:
    import _platform
    # This runs in the surviving supervisor, never in the dead helper/tray.
    _platform.show_toast("Uoink stopped after repeated failures", state["reason"] + " " + ACTION)


def capture_output(pipe, root: Path, tail: list) -> None:
    handler = RotatingFileHandler(root / "helper-output.log", maxBytes=1024 * 1024,
                                  backupCount=3, encoding="utf-8")
    try:
        # Fixed chunks bound memory even if a child prints no newlines.
        while chunk := pipe.read(4096):
            tail[0] = (tail[0] + chunk)[-8192:]
            handler.emit(logging.LogRecord("helper", logging.INFO, "", 0,
                                          chunk.decode("utf-8", errors="replace"), (), None))
    finally:
        pipe.close()
        handler.close()


class Supervisor:
    def __init__(self, root: Path, command: list[str], url: str, *, session: str,
                 startup: bool = False, readiness_timeout: float = 120,
                 poll: float = 0.5, backoff=BACKOFF, window: float = WINDOW,
                 probe=ready, notify=notify_failure, clock=time.time, sleep=time.sleep):
        self.root, self.command, self.url = root, command, url
        self.session, self.startup = session, startup
        self.readiness_timeout, self.poll = readiness_timeout, poll
        self.backoff, self.window = backoff, window
        self.probe, self.notify, self.clock, self.sleep = probe, notify, clock, sleep
        self.state = {}

    def save(self, **changes):
        self.state.update(changes)
        write_json(self.root / STATE_FILE, self.state)

    def stopped(self):
        return (self.root / STOP_FILE).exists()

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.stopped():
                return False
            self.sleep(max(0, min(self.poll, deadline - time.monotonic())))
        return not self.stopped()

    def run(self) -> int:
        with admission(self.root) as owned:
            if not owned:
                return 0
            try:
                old = read_json(self.root / STATE_FILE)
            except ValueError:
                old = {}
            fresh = not self.startup or old.get("session") != self.session
            if fresh:
                (self.root / STOP_FILE).unlink(missing_ok=True)
            self.state = {"schema_version": 1, "status": "starting", "last_exit_code": None,
                          "restart_count": 0, "last_start_at": None, "last_stop_at": None,
                          "ready_at": None, "reason": "Starting helper.", "action": "",
                          **old, "session": self.session, "supervisor_pid": os.getpid()}
            if fresh:
                self.state.update(restart_times=[], restart_count=0)
            if self.stopped() or (not fresh and old.get("status") == "crash_loop"):
                return 0
            if sys.platform == "darwin":
                import _platform
                observation = _platform.darwin_observe(os.getpid(), with_executable=True)
                if observation.status != "alive" or observation.created_ms is None:
                    raise OSError("Cannot identify the supervisor process")
                write_json(self.root / "supervisor-identity.json", {
                    "pid": os.getpid(), "created_ms": observation.created_ms,
                    "executable": observation.executable, "script": str(Path(__file__).resolve())})
            try:
                return self.loop()
            except Exception:
                self.save(status="supervisor_error", reason="Helper supervision failed.", action=ACTION)
                self.notify(self.state)
                return 0  # No unbounded outer OS retry loop.

    def loop(self) -> int:
        while not self.stopped():
            run_id = uuid.uuid4().hex
            self.save(status="starting", last_start_at=stamp(), ready_at=None,
                      reason="Waiting for helper readiness.", action="")
            env = dict(os.environ, UOINK_SUPERVISOR_RUN_ID=run_id, PYTHONUNBUFFERED="1")
            child = None
            reader = None
            reason = "Helper could not be started. Check the installed Python files."
            code = None
            tail = [b""]
            try:
                child = subprocess.Popen(self.command, cwd=HERE, env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         creationflags=0x08000000 if os.name == "nt" else 0)
                reader = threading.Thread(target=capture_output, args=(child.stdout, self.root, tail), daemon=True)
                reader.start()
                self.save(helper_pid=child.pid)
                deadline = time.monotonic() + self.readiness_timeout
                successes = 0
                is_ready = False
                while child.poll() is None:
                    # A Quit is written before the helper shuts down. Allow it
                    # to finish gracefully; do not kill a slow job on health timeouts.
                    if self.stopped():
                        try:
                            child.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            child.terminate()
                        break
                    if not is_ready:
                        successes = successes + 1 if self.probe(self.url, run_id, child.pid) else 0
                        if successes >= 2:
                            is_ready = True
                            self.save(status="running", ready_at=stamp(), reason="Helper is ready.")
                        elif time.monotonic() >= deadline:
                            reason = "Helper did not become ready before the startup deadline. Check for a port conflict or startup error."
                            child.terminate()
                            break
                    self.sleep(self.poll)
                code = child.wait(timeout=10)
                if not reason.startswith("Helper did not"):
                    reason = f"Helper exited with code {code}. Check for a startup error or port conflict."
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                if child is not None and child.poll() is None:
                    child.kill()
                    code = child.wait(timeout=10)
                if reader is not None:
                    reader.join(timeout=2)
            bind_failure = code != 0 and re.search(
                rb"failed[- ]to[- ]bind|address already in use|WinError 10048", tail[0], re.IGNORECASE)
            already_running = code == 0 and re.search(
                rb"Uoink server already running", tail[0], re.IGNORECASE)
            self.save(last_exit_code=code, last_stop_at=stamp(), helper_pid=None, reason=reason)
            if not self.stopped() and (bind_failure or already_running):
                reason = ("Another Uoink helper is already running on the local port."
                          if already_running else "Helper could not bind its local port. Another helper or app is using it.")
                self.save(status="stopped", reason=reason,
                          action="Use the running Uoink helper, or close the app holding the port and open Uoink again.")
                return 0
            if self.stopped() or code == 0:
                self.save(status="stopped", reason="Helper was stopped. Open Uoink to start it again.", action="")
                return 0
            now = self.clock()
            times = [t for t in self.state.get("restart_times", []) if 0 <= now - t < self.window]
            if len(times) >= len(self.backoff):
                self.save(status="crash_loop", restart_count=len(times), restart_times=times,
                          reason=reason + f" Recovery stopped after {len(times)} restarts in ten minutes.", action=ACTION)
                self.notify(self.state)
                return 0
            delay = self.backoff[len(times)]
            self.save(status="backoff", reason=reason + f" Retrying in {delay} seconds.", action="")
            if not self.wait(delay):
                break
            times.append(self.clock())
            self.save(restart_times=times, restart_count=len(times))
        self.save(status="stopped", reason="Helper was stopped. Open Uoink to start it again.", action="")
        return 0


def main(argv=None) -> int:
    import uoink_install_isolation as isolation
    isolation.apply_from_process()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--startup", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--show-dashboard", action="store_true")
    args = parser.parse_args(isolation.strip_cli(sys.argv[1:] if argv is None else argv))
    if args.stop:
        request_stop()
        return 0
    command = [sys.executable, "-B", "-s", str(HERE / "server.py")]
    if args.show_dashboard:
        command.append("--show-dashboard")
    root = data_root()
    try:
        result = Supervisor(root, command, isolation.helper_url("/health"),
                            session=login_session(), startup=args.startup).run()
    except (OSError, ValueError, subprocess.SubprocessError):
        failure = {"status": "supervisor_error", "reason": "Helper recovery could not start. Check access to the Uoink data folder.",
                   "action": ACTION}
        try:
            write_json(root / STATE_FILE, {"schema_version": 1, **failure})
        finally:
            notify_failure(failure)
        return 0
    if args.show_dashboard and status(root).get("status") == "running":
        subprocess.Popen([sys.executable, str(HERE / "uoink_dashboard.py")],
                         creationflags=0x08000000 if os.name == "nt" else 0)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
