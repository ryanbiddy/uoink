"""Run foreground saves and background transcriptions in separate FIFO slots.

Each slot keeps one child warm for 120 seconds after its last job. Peak
memory is two transcription models when both slots are busy, plus any
alignment and speaker-label runtimes. A job runs once. Its owner can cancel
it or raise at a segment checkpoint to pause backfill and release the slot.

The helper writes requests to stdin. Replies use a private inherited pipe;
native stdout and stderr go to the worker log. One OS lock per slot protects
its resident model across helper/MCP processes. A second, scoped request
lock lets an idle owner hand it off for a new job or model deletion.
Processes running inference in-process never participate in these slots.
"""

from __future__ import annotations

import atexit
from collections import deque
from contextlib import contextmanager, ExitStack
import json
import math
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ENV_CHILD = "UOINK_ASR_CHILD"
DEFAULT_IDLE_SECONDS = 120
DECODE_SECONDS = 600
FRAME_LIMIT = 64 * 1024 * 1024
LOG_NAME = "asr-worker.log"
_LOG_ROTATE_BYTES = 4 * 1024 * 1024
# Windows creation flags: no console window, below-normal priority.
_CREATE_NO_WINDOW = 0x08000000
_BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
# Modules a long-lived Uoink process must never load (tests check this).
HEAVY_MODULES = ("torch", "whisperx", "pyannote", "lightning", "pytorch_lightning",
                 "ctranslate2", "faster_whisper", "onnxruntime", "av")


class TranscriptionCancelled(Exception):
    """The caller's cancel event fired; the job stopped."""


class WorkerCrashed(RuntimeError):
    """The child process ended before it answered."""


# ---- configuration -----------------------------------------------------
_config: dict[str, Any] | None = None


class _Slot:
    def __init__(self, name):
        self.name = name
        self.condition = threading.Condition()
        self.waiting = deque()
        self.active = None
        self.child = None
        self.release_at = None

    @contextmanager
    def turn(self, op, cancel, request_path):
        ticket = object()
        with self.condition:
            self.waiting.append(ticket)
            try:
                while True:
                    _check_cancel(cancel)
                    if self.active is None and self.waiting[0] is ticket:
                        request = _try_file(request_path)
                        if request is not None:
                            self.active = op
                            self.release_at = None
                            break
                    # While another process owns the request our idle monitor
                    # must remain free to hand that process the warm model.
                    self.condition.wait(.1)
            finally:
                self.waiting.remove(ticket)
                self.condition.notify_all()
        try:
            yield
        finally:
            with self.condition:
                if self.child:
                    self.release_at = time.monotonic() + _config["idle_seconds"]
                request.close()
                self.active = None
                self.condition.notify_all()


_slots = {name: _Slot(name) for name in ("foreground", "background")}
_jobs_run = 0
_last_exit = None
_EOF = object()


def _check_cancel(event):
    if _config is None or _config["closing"]:
        raise WorkerCrashed("The transcription helper is shutting down.")
    if event is not None and event.is_set():
        raise TranscriptionCancelled("Transcription cancelled.")


def in_child() -> bool:
    return os.environ.get(ENV_CHILD) == "1"


def enable_offload(*, log_dir: str | Path, idle_seconds: float = DEFAULT_IDLE_SECONDS,
                   python: str | None = None) -> None:
    """Send this process's model work to a child. Call once at start."""
    global _config
    if in_child():
        return
    folder = Path(log_dir)
    _config = {
        "idle_seconds": max(0.2, float(idle_seconds)),
        "log_path": folder / LOG_NAME,
        "root": folder,
        "closing": False,
        "python": python or sys.executable,
    }
    atexit.unregister(shutdown)
    atexit.register(shutdown)


def disable_offload() -> None:
    """Stop the child and run models in-process again (tests use this)."""
    global _config
    shutdown()
    _config = None


def offload_active() -> bool:
    return _config is not None and not in_child()


def idle_seconds() -> float | None:
    return _config["idle_seconds"] if _config else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def status() -> dict[str, Any]:
    """What the health view shows: is a model process holding memory now?"""
    alive = []
    running = []
    deadlines = []
    for slot in _slots.values():
        with slot.condition:
            if slot.child and slot.child.proc.poll() is None:
                alive.append(slot.child.proc.pid)
                if slot.active:
                    running.append(slot.active)
                if slot.release_at:
                    deadlines.append(slot.release_at)
    return {
        "offloaded": offload_active(),
        "state": "running" if running else ("loaded" if alive else "not_loaded"),
        "pid": alive[0] if alive else None,
        "op": running[0] if running else None,
        "idle_release_seconds": idle_seconds(),
        "release_at": (datetime.fromtimestamp(time.time() + min(deadlines) - time.monotonic(),
                                              timezone.utc).isoformat() if deadlines and not running else None),
        "jobs_run": _jobs_run, "last_exit": _last_exit,
    }


def status_line(info: dict | None = None) -> str:
    """One plain sentence for the health view."""
    info = info or status()
    if not info.get("offloaded"):
        return "Transcription engine: runs inside this process."
    minutes = max(1, round((info.get("idle_release_seconds") or 0) / 60))
    if info["state"] == "running":
        return "Transcription engine: working now. It frees its memory when the queue is empty."
    if info["state"] == "loaded":
        return (f"Transcription engine: loaded, frees its memory after {minutes} "
                f"minute{'s' if minutes != 1 else ''} idle.")
    return "Transcription engine: idle (not loaded)."


def _try_os_lock(handle) -> bool:
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


class _Lease:
    def __init__(self, handle):
        self.handle = handle

    def close(self):
        if self.handle.closed:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _try_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    # Both platforms can lock a byte past EOF. No initialization write races.
    if _try_os_lock(handle):
        return _Lease(handle)
    handle.close()
    return None


def _wait_file(path, cancel):
    while True:
        _check_cancel(cancel)
        handle = _try_file(path)
        if handle is not None:
            return handle
        time.sleep(0.025)


def _python_command() -> list[str]:
    flags = ["-B"]
    if sys.flags.no_user_site:
        flags.append("-s")
    if sys.flags.ignore_environment:
        flags.append("-E")
    return [_config["python"], *flags, str(HERE / "asr_worker.py")]


def _open_log() -> Any:
    path: Path = _config["log_path"]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _LOG_ROTATE_BYTES:
            try:
                os.replace(path, path.with_name(path.name + ".1"))
            except PermissionError:
                pass  # The other slot still has this log open on Windows.
        handle = path.open("ab")
        handle.write(f"\n--- transcription process start {_now_iso()} ---\n".encode())
        handle.flush()
        return handle
    except OSError:
        return subprocess.DEVNULL


class _Child:
    def __init__(self, proc, stream, win_job, lease):
        self.proc = proc
        self.messages = queue.Queue()
        self.win_job = win_job
        self.lease = lease
        self.closed = threading.Event()

        def read():
            try:
                with stream:
                    for message in _frames(stream):
                        if isinstance(message, dict):
                            self.messages.put(message)
            except (OSError, ValueError):
                pass
            finally:
                self.messages.put(_EOF)

        threading.Thread(target=read, name="asr-replies", daemon=True).start()


def _spawn(lease):
    try:
        import uoink_install_isolation as isolation
        extra_args = isolation.child_argv()
        extra_env = isolation.child_environ()
    except Exception:  # pragma: no cover - the isolation module always ships
        extra_args, extra_env = [], {}
    env = dict(os.environ)
    env.update(extra_env)
    env.update({ENV_CHILD: "1", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
    command = _python_command()
    # Windows venv python.exe is a launcher that spawns another process.
    # Start the interpreter directly so containment covers its first instruction
    # that can perform model work, including in an installed virtualenv.
    if os.name == "nt" and command[0] == sys.executable and sys.prefix != sys.base_prefix:
        env["__PYVENV_LAUNCHER__"] = sys.executable
        command[0] = sys._base_executable
    log = _open_log()
    win_job = None
    flags = (_CREATE_NO_WINDOW | _BELOW_NORMAL_PRIORITY_CLASS) if os.name == "nt" else 0
    read_fd, write_fd = os.pipe()
    try:
        if os.name == "nt":
            import msvcrt
            writer = msvcrt.get_osfhandle(write_fd)
            os.set_handle_inheritable(writer, True)
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [writer]}
            inherit = {"startupinfo": startup}
        else:
            writer = write_fd
            inherit = {"pass_fds": (writer,), "start_new_session": True}
        env["UOINK_ASR_CHANNEL"] = str(writer)
        if os.name == "nt":
            from library_mirror import _win_create_kill_job, _win_assign_job, _win_close_handle
            win_job = _win_create_kill_job()
            if not win_job:
                raise OSError("Could not create a transcription Job Object.")
        proc = subprocess.Popen(
            [*command, *extra_args], cwd=str(HERE), env=env,
            stdin=subprocess.PIPE, stdout=log, stderr=log,
            creationflags=flags, close_fds=True, **inherit)
        if win_job and not _win_assign_job(win_job, proc):
            proc.kill()
            proc.wait()
            proc.stdin.close()
            raise OSError("Could not contain the transcription process.")
    except BaseException as exc:
        os.close(read_fd)
        if win_job:
            _win_close_handle(win_job)
        if isinstance(exc, OSError):
            raise WorkerCrashed(f"Could not start the transcription process: {exc}") from exc
        raise
    finally:
        os.close(write_fd)
        if log != subprocess.DEVNULL:
            log.close()

    return _Child(proc, os.fdopen(read_fd, "rb"), win_job, lease)


def _retire(slot, child, reason):
    """Called under the slot condition. Kill descendants even if the leader exited."""
    global _last_exit
    if slot.child is not child:
        return
    child.closed.set()
    proc = child.proc
    if os.name == "nt":
        from library_mirror import _win_close_handle
        _win_close_handle(child.win_job)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    code = proc.wait()
    try:
        proc.stdin.close()
    except OSError:
        pass
    child.lease.close()
    slot.child = slot.release_at = None
    _last_exit = {"at": _now_iso(), "code": code, "reason": reason}


def _watch_idle(slot, child, request_path):
    while not child.closed.wait(.2):
        with slot.condition:
            if slot.child is not child:
                return
            if slot.active:
                continue
            if child.proc.poll() is not None:
                _retire(slot, child, "exited")
                return
            if slot.release_at and time.monotonic() >= slot.release_at:
                _retire(slot, child, "idle")
                return
            # A foreign job or deletion can claim a warm, unused model.
            probe = _try_file(request_path)
            if probe is None:
                _retire(slot, child, "idle")
                return
            probe.close()


def _write_frame(stream, message):
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {k: finite(v) for k, v in value.items()
                    if not isinstance(k, float) or math.isfinite(k)}
        if isinstance(value, (list, tuple)):
            return [finite(v) for v in value]
        return value

    data = json.dumps(finite(message), ensure_ascii=True, allow_nan=False, default=str)
    data = data.encode("ascii") + b"\n"
    if len(data) > FRAME_LIMIT:
        raise ValueError("The transcription result exceeds the worker message size limit.")
    remaining = memoryview(data)
    while remaining:
        written = stream.write(remaining)
        if not written:
            raise OSError("The transcription pipe closed during a write.")
        remaining = remaining[written:]
    stream.flush()


def _frames(stream, limit=FRAME_LIMIT):
    while True:
        raw = stream.readline(limit + 1)
        if not raw:
            return
        if len(raw) > limit or not raw.endswith(b"\n"):
            raise ValueError("Invalid transcription message size.")
        yield json.loads(raw)


def _send(proc: subprocess.Popen, message: dict) -> None:
    # One controller owns each child. Never hold the global state lock across pipe I/O.
    _write_frame(proc.stdin, message)


def _send_job(child, message):
    # A stalled stdin reader must not block the watchdog or cancellation.
    def write():
        try:
            _send(child.proc, message)
        except OSError:
            child.messages.put(_EOF)
        except Exception as exc:
            child.messages.put(_EOF if child.proc.stdin.closed else exc)

    threading.Thread(target=write, name="asr-request", daemon=True).start()


_ERROR_TYPES: dict[str, type[BaseException]] = {
    "FileNotFoundError": FileNotFoundError, "PermissionError": PermissionError,
    "IndexError": IndexError, "ValueError": ValueError, "TimeoutError": TimeoutError,
    "OSError": OSError, "RuntimeError": RuntimeError,
}


def _rebuild_error(message: dict) -> BaseException:
    name = str(message.get("error_type") or "RuntimeError")
    text = str(message.get("message") or "transcription failed")
    if name == "ReliabilityUnavailableError":
        import uoink_reliability
        return uoink_reliability.ReliabilityUnavailableError(text)
    if name == "TranscriptionCancelled":
        return TranscriptionCancelled(text)
    if name == "MemoryError":
        return RuntimeError("The transcription process ran out of memory.")
    return _ERROR_TYPES.get(name, RuntimeError)(text)


def _crashed(code: int | None) -> WorkerCrashed:
    detail = f" (exit code {code})" if code is not None else ""
    return WorkerCrashed(f"The transcription process stopped unexpectedly{detail}.")


def _inactivity_seconds(phase, duration):
    """Decode: 10 min between segments. Silent stages: 10 min plus a bounded
    multiple of audio seconds (unknown length: one hour). All cap at 6 hours.
    Model load and language check add 0.1x, ffmpeg 0.5x, batch transcription,
    alignment and diarization 2x. Each actual progress update renews its phase.
    """
    scale = {"model load": .1, "language check": .1, "ffmpeg": .5,
             "batch transcription": 2, "alignment": 2, "diarization": 2}.get(phase, 0)
    seconds = duration if isinstance(duration, (int, float)) and duration > 0 else 3600
    return min(21600, DECODE_SECONDS + scale * seconds)


def _await(child, job_id, duration, cancel, progress, checkpoint):
    phase = "decode"
    deadline = time.monotonic() + _inactivity_seconds(phase, duration)
    while True:
        _check_cancel(cancel)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkerCrashed(f"Transcription stopped making progress during {phase}. Try again.")
        try:
            message = child.messages.get(timeout=min(.1, remaining))
        except queue.Empty:
            continue
        if message is _EOF:
            # Windows can close the pipe just before it publishes the exit code.
            try:
                code = child.proc.wait(timeout=.3)
            except subprocess.TimeoutExpired:
                code = None
            raise _crashed(code)
        if isinstance(message, BaseException):
            raise message
        if message.get("id") != job_id:
            continue
        kind = message.get("type")
        if kind in ("result", "error"):
            return message
        if kind == "phase":
            phase = message["name"]
        elif kind == "progress":
            if progress is not None and message.get("done") is not None:
                try:
                    progress(message["done"], message.get("total"))
                except Exception:
                    pass  # A progress display cannot fail a transcription.
        elif kind == "segment":
            checkpoint(message["segment"])
            _check_cancel(cancel)
            try:
                _send(child.proc, {"id": job_id, "control": "continue"})
            except (ValueError, OSError):
                raise _crashed(child.proc.poll()) from None
        elif kind != "started":
            continue
        deadline = time.monotonic() + _inactivity_seconds(phase, duration)


def call(op: str, args: dict, *, cancel_event=None, progress=None, checkpoint=None,
         background=False) -> Any:
    """Run a single request in FIFO order in the caller's selected slot."""
    global _jobs_run
    if not offload_active():
        raise RuntimeError("model work is not offloaded in this process")
    slot = _slots["background" if background else "foreground"]
    root = _config["root"]
    request = root / f"asr-{slot.name}.request.lock"
    with slot.turn(op, cancel_event, request):
        with slot.condition:
            _check_cancel(cancel_event)
            if slot.child and slot.child.proc.poll() is not None:
                _retire(slot, slot.child, "exited")
            if slot.child is None:
                lease = _wait_file(root / f"asr-{slot.name}.model.lock", cancel_event)
                try:
                    slot.child = _spawn(lease)
                except BaseException:
                    lease.close()
                    raise
                threading.Thread(target=_watch_idle, args=(slot, slot.child, request),
                                 name="asr-idle", daemon=True).start()
            child = slot.child
        job_id = uuid.uuid4().hex
        try:
            _send_job(child, {"id": job_id, "op": op,
                              "args": {**args, "checkpoint": checkpoint is not None}})
            reply = _await(child, job_id, args.get("duration_seconds"), cancel_event, progress, checkpoint)
        except BaseException as exc:
            reason = "cancelled" if isinstance(exc, TranscriptionCancelled) else "failed"
            if isinstance(exc, WorkerCrashed):
                reason = "crashed" if child.proc.poll() is not None else "timeout"
            with slot.condition:
                _retire(slot, child, reason)
            raise
        if reply["type"] == "error":
            raise _rebuild_error(reply)
        _jobs_run += 1
        return reply.get("value")


def shutdown() -> None:
    """End this offload session and release both process trees."""
    if _config:
        _config["closing"] = True
    for slot in _slots.values():
        with slot.condition:
            if slot.child:
                _retire(slot, slot.child, "shutdown")


@contextmanager
def deletion_slot(root):
    """Hold both slots across unlink. A crashed owner leaves no OS locks."""
    busy = "A transcription is using the model. Try again when it finishes."
    with ExitStack() as locks:
        for name in _slots:
            request = _try_file(Path(root) / f"asr-{name}.request.lock")
            if not request:
                raise RuntimeError(busy)
            locks.enter_context(request)
        for name in _slots:
            path = Path(root) / f"asr-{name}.model.lock"
            until = time.monotonic() + 2
            lease = _try_file(path)
            while lease is None and time.monotonic() < until:
                time.sleep(.025)
                lease = _try_file(path)
            if lease is None:
                raise RuntimeError(busy)
            locks.enter_context(lease)
        yield


# ---- child side ------------------------------------------------------------
def _install_model_cache() -> None:
    """Reuse the last local model across jobs in this child.

    Keep one transcription model resident per slot. Downloads
    (local_files_only=False) are never cached.
    """
    import uoink_reliability as rel
    original = rel._load_model
    cache: dict[tuple, Any] = {}

    def cached(model_name, model_root, *, local_files_only=True):
        if not local_files_only:
            return original(model_name, model_root, local_files_only=False)
        # A podcast may pass the resolved snapshot while a capture passes its model ID.
        snapshot = Path(model_name) if Path(model_name).is_absolute() else None
        if snapshot is None:
            source, snapshot = rel.resolve_model(model_name, model_root)
            if source == rel.SOURCE_DOWNLOADED and model_root:
                snapshot = rel._cached_reliability_snapshot(model_root, model_name)
        key = (str(snapshot.resolve()), None) if snapshot else (
            str(model_name), str(model_root) if model_root else None)
        if key in cache:
            return cache[key]
        if cache:
            cache.clear()
            import gc
            gc.collect()
        model = original(model_name, model_root, local_files_only=True)
        cache[key] = model
        return model

    cached.cache_clear = cache.clear
    rel._load_model = cached


# Set only by the active job in a child. Direct callers have no watchdog.
_phase_callback = None


def report_phase(name):
    if _phase_callback is not None:
        _phase_callback(name)


def _run_op(op: str, args: dict, progress: Callable[[Any, Any], None],
            checkpoint: Callable[[Any], None] | None) -> Any:
    if op == "ping":
        return {"pid": os.getpid(),
                "heavy_loaded": sorted(m for m in HEAVY_MODULES if m in sys.modules)}
    if op == "transcribe_media":
        import uoink_reliability as rel
        info: dict = {}
        entries = rel.transcribe_media(
            args["media_path"], model_name=args.get("model_name") or rel.DEFAULT_MODEL,
            model_root=args.get("model_root"), info=info, language=args.get("language"),
            initial_prompt=args.get("initial_prompt"), progress=progress, checkpoint=checkpoint)
        return {"entries": [rel.entry_to_json(entry) for entry in entries], "info": info}
    if op == "detect_unreliable_spans":
        import uoink_reliability as rel
        spans = rel.detect_unreliable_spans(
            args.get("transcript_text") or "", args["audio_path"],
            threshold=args.get("threshold", rel.DEFAULT_THRESHOLD),
            model_name=args.get("model_name") or rel.DEFAULT_MODEL,
            model_root=args.get("model_root"), progress=progress)
        return [span.to_dict() for span in spans]
    if op == "ensure_model":
        import uoink_reliability as rel
        return rel.ensure_model(args.get("model_name") or rel.DEFAULT_MODEL, args.get("model_root"))
    if op == "transcribe_audio":
        import whisper_runner
        return whisper_runner.transcribe_audio(
            Path(args["audio_path"]), data_root=Path(args["data_root"]),
            model_size=args.get("model_size") or whisper_runner.MODEL_BASE,
            language=args.get("language"), diarize=bool(args.get("diarize")),
            consent_given=bool(args.get("consent_given")),
            initial_prompt=args.get("initial_prompt"), checkpoint=checkpoint,
            progress=progress, duration_seconds=args.get("duration_seconds"))
    raise ValueError(f"unknown transcription operation: {op}")


def _child_main(argv: list[str]) -> int:
    # stdout and stderr have pointed to the log since process creation, even
    # during interpreter startup. Only the framed writer gets this handle.
    descriptor = int(os.environ.pop("UOINK_ASR_CHANNEL"))
    if os.name == "nt":
        import msvcrt
        descriptor = msvcrt.open_osfhandle(descriptor, os.O_WRONLY | os.O_BINARY)
    os.set_inheritable(descriptor, False)
    channel = os.fdopen(descriptor, "wb", buffering=0)

    def emit(message):
        _write_frame(channel, message)

    import uoink_install_isolation as isolation
    isolation.apply_from_process(argv)
    if os.name != "nt":
        try:
            os.nice(10)
        except OSError:
            pass
    jobs = queue.Queue()
    controls = queue.Queue()

    def read():
        try:
            for message in _frames(sys.stdin.buffer):
                if message.get("op"):
                    jobs.put(message)
                elif message.get("control") == "continue":
                    controls.put(message["id"])
        finally:
            if os.name != "nt" and os.getpgrp() == os.getpid():
                os.killpg(os.getpid(), signal.SIGKILL)
            os._exit(0)

    threading.Thread(target=read, name="uoink-asr-input", daemon=True).start()
    _install_model_cache()

    def handle(job: dict) -> None:
        global _phase_callback
        job_id = str(job["id"])
        emit({"id": job_id, "type": "started"})
        def phase(name):
            emit({"id": job_id, "type": "phase", "name": name})

        def progress(done, total):
            emit({"id": job_id, "type": "progress", "done": done, "total": total})

        def checkpoint(segment):
            if isinstance(segment, dict):
                data = {key: segment[key] for key in ("start", "end", "text", "percent") if key in segment}
            else:
                data = {key: getattr(segment, key, None) for key in ("start", "end", "text")}
            emit({"id": job_id, "type": "segment", "segment": data})
            if controls.get() != job_id:
                raise RuntimeError("Unexpected transcription checkpoint reply.")

        _phase_callback = phase
        try:
            args = job.get("args") or {}
            value = _run_op(str(job.get("op")), args, progress,
                            checkpoint if args.get("checkpoint") else None)
            emit({"id": job_id, "type": "result", "value": value})
        except BaseException as exc:  # noqa: BLE001 - every failure is reported
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            if not isinstance(exc, TranscriptionCancelled):
                import traceback
                traceback.print_exc(file=sys.stderr)
                sys.stderr.flush()
            emit({"id": job_id, "type": "error", "error_type": type(exc).__name__,
                  "message": str(exc)[:2000]})
        finally:
            _phase_callback = None

    while True:
        handle(jobs.get())


if __name__ == "__main__":
    sys.modules["asr_worker"] = sys.modules[__name__]
    sys.path.insert(0, str(HERE))  # the embeddable Python never adds the script folder
    os.environ[ENV_CHILD] = "1"
    raise SystemExit(_child_main(sys.argv[1:]))
