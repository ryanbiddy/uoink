"""Run local speech models in a child process the OS can reclaim.

Whisper models, CTranslate2 and (for speaker labels) torch, Lightning and
pyannote hold gigabytes that their allocators rarely give back to the OS,
even after the model object is gone. Long-lived Uoink processes (the helper
and the stdio MCP server) therefore never load them. They call
``enable_offload()`` once at start; after that every transcription entry
point (``uoink_reliability.transcribe_media``, ``detect_unreliable_spans``,
``ensure_model`` and ``whisper_runner.transcribe_audio``) sends its work to
one child process through ``call()``. The child keeps a model warm while jobs
keep coming and is stopped after ``idle_seconds`` with nothing to do, so the
OS reclaims everything it loaded.

Guarantees:
- One model job at a time: a thread lock in this process plus an OS file lock
  in the data folder, so the helper and an MCP server never run two models.
- Cancellation kills the child. The next job starts a fresh one.
- A child crash (exit, out of memory, native fault) is a failed job with a
  reason. It never takes the caller down.
- The child inherits the isolation binding (profile, port, app folder) and
  uses this interpreter with this interpreter's flags, so the Windows
  embeddable Python and the macOS app bundle can both start it. On Windows
  it starts with no console window and below-normal priority.

Processes that never call ``enable_offload()`` (tests, the one-shot CLI, the
child itself) keep running models in-process, exactly as before.

Protocol: one JSON object per line. Caller to child:
``{"id", "op", "args"}``. Child to caller: ``{"id", "type": "started"}``,
``{"id", "type": "progress", "done", "total"}``, ``{"id", "type": "result",
"value"}`` or ``{"id", "type": "error", "error_type", "message"}``.
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ENV_CHILD = "UOINK_ASR_CHILD"
DEFAULT_IDLE_SECONDS = 120
LOG_NAME = "asr-worker.log"
LOCK_NAME = "asr-worker.lock"
_LOG_ROTATE_BYTES = 4 * 1024 * 1024
# Windows creation flags: no console window, below-normal priority.
_CREATE_NO_WINDOW = 0x08000000
_BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
# Modules a long-lived Uoink process must never load (tests check this).
HEAVY_MODULES = ("torch", "whisperx", "pyannote", "lightning", "pytorch_lightning",
                 "ctranslate2", "faster_whisper", "onnxruntime", "av")


class TranscriptionCancelled(Exception):
    """The caller's cancel event fired; the child was stopped."""


class WorkerCrashed(RuntimeError):
    """The child process ended before it answered."""


# ---- configuration -----------------------------------------------------
_config: dict[str, Any] | None = None
_state_lock = threading.RLock()
_slot = threading.Lock()
_proc: subprocess.Popen | None = None
_lines: queue.Queue | None = None
_idle_timer: threading.Timer | None = None
_generation = 0
_release_at: float | None = None
_running_op: str | None = None
_jobs_run = 0
_last_exit: dict[str, Any] | None = None
_EOF = object()
_NOT_STARTED = object()


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
        "lock_path": folder / LOCK_NAME,
        "python": python or sys.executable,
    }
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
    with _state_lock:
        alive = _proc is not None and _proc.poll() is None
        state = "running" if _running_op else ("loaded" if alive else "not_loaded")
        return {
            "offloaded": offload_active(),
            "state": state,
            "pid": _proc.pid if alive else None,
            "op": _running_op,
            "idle_release_seconds": int(_config["idle_seconds"]) if _config else None,
            "release_at": (datetime.fromtimestamp(_release_at, timezone.utc)
                           .replace(microsecond=0).isoformat().replace("+00:00", "Z")
                           if alive and _release_at and not _running_op else None),
            "jobs_run": _jobs_run,
            "last_exit": dict(_last_exit) if _last_exit else None,
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


# ---- one job at a time ---------------------------------------------------
@contextmanager
def _file_lock(path: Path, cancel_event: threading.Event | None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
        while True:
            try:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if cancel_event is not None and cancel_event.is_set():
                    raise TranscriptionCancelled("cancelled while waiting for another transcription")
                time.sleep(0.25)
        try:
            yield
        finally:
            try:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


@contextmanager
def job_slot(cancel_event: threading.Event | None = None):
    """Hold the one-model slot. Waits for a running job; a cancel stops the wait."""
    while not _slot.acquire(timeout=0.25):
        if cancel_event is not None and cancel_event.is_set():
            raise TranscriptionCancelled("cancelled while waiting for another transcription")
    try:
        if _config is not None:
            with _file_lock(_config["lock_path"], cancel_event):
                yield
        else:
            yield
    finally:
        _slot.release()


# ---- the child process ---------------------------------------------------
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
            os.replace(path, path.with_name(path.name + ".1"))
        handle = path.open("ab")
        handle.write(f"\n--- transcription process start {_now_iso()} ---\n".encode())
        handle.flush()
        return handle
    except OSError:
        return subprocess.DEVNULL


def _spawn() -> subprocess.Popen:
    global _proc, _lines
    try:
        import uoink_install_isolation as isolation
        extra_args = isolation.child_argv()
        extra_env = isolation.child_environ()
    except Exception:  # pragma: no cover - the isolation module always ships
        extra_args, extra_env = [], {}
    env = dict(os.environ)
    env.update(extra_env)
    env.update({ENV_CHILD: "1", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
    log = _open_log()
    flags = (_CREATE_NO_WINDOW | _BELOW_NORMAL_PRIORITY_CLASS) if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            [*_python_command(), *extra_args], cwd=str(HERE), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
            creationflags=flags, close_fds=True)
    except OSError as exc:
        raise WorkerCrashed(f"Could not start the transcription process: {exc}") from exc
    finally:
        if log is not subprocess.DEVNULL:
            log.close()
    lines: queue.Queue = queue.Queue()

    def read(stream=proc.stdout, sink=lines):
        try:
            for raw in stream:
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue  # stray output is never part of the protocol
                if isinstance(message, dict):
                    sink.put(message)
        except (OSError, ValueError):
            pass
        sink.put(_EOF)

    threading.Thread(target=read, name="uoink-asr-reader", daemon=True).start()
    _proc, _lines = proc, lines
    return proc


def _log_tail(limit: int = 4000) -> str:
    """The child's last meaningful log line, for a crash reason."""
    try:
        with _config["log_path"].open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            text = handle.read().decode("utf-8", "replace")
    except (OSError, TypeError):
        return ""
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.startswith("--- transcription process")]
    return lines[-1][:300] if lines else ""


def _reap(reason: str) -> int | None:
    """Forget a child that has ended or that we stop now."""
    global _proc, _lines, _release_at, _last_exit
    with _state_lock:
        proc = _proc
        _proc, _lines, _release_at = None, None, None
    if proc is None:
        return None
    for stream in (proc.stdin,):
        try:
            if stream:
                stream.close()
        except OSError:
            pass
    try:
        code = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            code = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - the OS failed to stop it
            code = None
    _last_exit = {"at": _now_iso(), "code": code, "reason": reason}
    return code


def _kill(reason: str) -> None:
    with _state_lock:
        proc = _proc
    if proc is not None and proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    _reap(reason)


def _ensure_child() -> tuple[subprocess.Popen, queue.Queue]:
    with _state_lock:
        if _proc is not None and _proc.poll() is None and _lines is not None:
            return _proc, _lines
    if _proc is not None:
        _reap("exited")
    proc = _spawn()
    return proc, _lines


def _send(proc: subprocess.Popen, message: dict) -> None:
    proc.stdin.write(json.dumps(message, ensure_ascii=True).encode("ascii") + b"\n")
    proc.stdin.flush()


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


def _await(proc, lines, job_id, cancel_event, progress):
    started = False
    while True:
        if cancel_event is not None and cancel_event.is_set():
            _kill("cancelled")
            raise TranscriptionCancelled("transcription cancelled")
        try:
            message = lines.get(timeout=0.2)
        except queue.Empty:
            continue
        if message is _EOF:
            code = _reap("crashed" if started else "exited")
            if not started:
                return _NOT_STARTED
            tail = _log_tail()
            raise WorkerCrashed(
                "The transcription process stopped unexpectedly"
                + (f" (exit code {code})" if code is not None else "")
                + (f": {tail}" if tail else "."))
        if message.get("id") != job_id:
            continue
        kind = message.get("type")
        if kind == "started":
            started = True
        elif kind == "progress" and progress is not None:
            try:
                progress(message.get("done"), message.get("total"))
            except Exception:  # noqa: BLE001 - a progress display never fails a job
                pass
        elif kind == "result":
            return message.get("value")
        elif kind == "error":
            raise _rebuild_error(message)


def call(op: str, args: dict, *, cancel_event: threading.Event | None = None,
         progress: Callable[[Any, Any], None] | None = None) -> Any:
    """Run one model job in the child and return its JSON result."""
    global _running_op, _jobs_run
    if not offload_active():
        raise RuntimeError("model work is not offloaded in this process")
    with job_slot(cancel_event):
        _cancel_idle_timer()
        try:
            for attempt in (1, 2):
                proc, lines = _ensure_child()
                job_id = uuid.uuid4().hex
                with _state_lock:
                    _running_op = op
                try:
                    _send(proc, {"id": job_id, "op": op, "args": args})
                except (OSError, ValueError):
                    _reap("exited")
                    if attempt == 1:
                        continue
                    raise WorkerCrashed("Could not reach the transcription process.")
                outcome = _await(proc, lines, job_id, cancel_event, progress)
                if outcome is _NOT_STARTED:
                    # It stopped before it read the job (idle exit race): retry once.
                    if attempt == 1:
                        continue
                    raise WorkerCrashed("The transcription process exited before it started.")
                _jobs_run += 1
                return outcome
        finally:
            with _state_lock:
                _running_op = None
            _schedule_idle_stop()


def _cancel_idle_timer() -> None:
    global _idle_timer, _release_at
    with _state_lock:
        if _idle_timer is not None:
            _idle_timer.cancel()
            _idle_timer = None
        _release_at = None


def _schedule_idle_stop() -> None:
    global _idle_timer, _generation, _release_at
    with _state_lock:
        if _config is None or _proc is None:
            return
        _generation += 1
        wait = _config["idle_seconds"]
        timer = threading.Timer(wait, _stop_if_idle, args=(_generation,))
        timer.daemon = True
        _idle_timer = timer
        _release_at = time.time() + wait
    timer.start()


def _stop_if_idle(generation: int) -> None:
    if not _slot.acquire(blocking=False):
        return  # a job is running; it schedules the next stop when it ends
    try:
        with _state_lock:
            if generation != _generation or _proc is None:
                return
        _reap("idle")
    finally:
        _slot.release()


def shutdown() -> None:
    """Stop the child now (helper exit)."""
    _cancel_idle_timer()
    with _state_lock:
        proc = _proc
    if proc is not None:
        _reap("shutdown")


# ---- child side ------------------------------------------------------------
def _install_model_cache(limit: int = 2) -> None:
    """Reuse loaded models across jobs in this child (at most ``limit``).

    A detection model plus the chosen model is the common pair. Downloads
    (local_files_only=False) are never cached.
    """
    import uoink_reliability as rel
    original = rel._load_model
    cache: dict[tuple, Any] = {}

    def cached(model_name, model_root, *, local_files_only=True):
        if not local_files_only:
            return original(model_name, model_root, local_files_only=False)
        key = (str(model_name), str(model_root) if model_root else None)
        if key in cache:
            cache[key] = cache.pop(key)  # most recent last
            return cache[key]
        while len(cache) >= limit:
            cache.pop(next(iter(cache)))
            import gc
            gc.collect()
        model = original(model_name, model_root, local_files_only=True)
        cache[key] = model
        return model

    rel._load_model = cached


def _run_op(op: str, args: dict, progress: Callable[[Any, Any], None]) -> Any:
    if op == "ping":
        return {"pid": os.getpid(),
                "heavy_loaded": sorted(m for m in HEAVY_MODULES if m in sys.modules)}
    if op == "transcribe_media":
        import uoink_reliability as rel
        info: dict = {}
        entries = rel.transcribe_media(
            args["media_path"], model_name=args.get("model_name") or rel.DEFAULT_MODEL,
            model_root=args.get("model_root"), info=info, language=args.get("language"),
            initial_prompt=args.get("initial_prompt"), progress=progress)
        return {"entries": [rel.entry_to_json(entry) for entry in entries], "info": info}
    if op == "detect_unreliable_spans":
        import uoink_reliability as rel
        spans = rel.detect_unreliable_spans(
            args.get("transcript_text") or "", args["audio_path"],
            threshold=args.get("threshold", rel.DEFAULT_THRESHOLD),
            model_name=args.get("model_name") or rel.DEFAULT_MODEL,
            model_root=args.get("model_root"))
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
            initial_prompt=args.get("initial_prompt"))
    raise ValueError(f"unknown transcription operation: {op}")


def _child_main(argv: list[str]) -> int:
    # The protocol owns the original stdout. Anything a library prints (and
    # any native printf) goes to the log instead, so it cannot break a line.
    channel = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    write_lock = threading.Lock()

    def emit(message: dict) -> None:
        data = json.dumps(message, ensure_ascii=True, default=str).encode("ascii") + b"\n"
        with write_lock:
            channel.write(data)

    import uoink_install_isolation as isolation
    isolation.apply_from_process(argv)
    if os.name != "nt":
        try:
            os.nice(10)
        except OSError:
            pass
    try:
        _install_model_cache()
    except Exception as exc:  # noqa: BLE001 - caching is an optimization
        print(f"model cache unavailable: {exc}", file=sys.stderr)

    jobs: queue.Queue = queue.Queue()

    def read() -> None:
        for raw in sys.stdin.buffer:
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(message, dict) and message.get("id"):
                jobs.put(message)
        # The caller closed the pipe (idle stop) or died: leave now, even mid-job.
        sys.stderr.flush()
        os._exit(0)

    threading.Thread(target=read, name="uoink-asr-input", daemon=True).start()
    while True:
        job = jobs.get()
        job_id = job["id"]
        emit({"id": job_id, "type": "started"})
        last = [0.0]

        def progress(done, total, job_id=job_id, last=last):
            now = time.monotonic()
            if now - last[0] >= 0.5:
                last[0] = now
                emit({"id": job_id, "type": "progress", "done": done, "total": total})

        try:
            value = _run_op(str(job.get("op")), job.get("args") or {}, progress)
            emit({"id": job_id, "type": "result", "value": value})
        except BaseException as exc:  # noqa: BLE001 - every failure is reported
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            emit({"id": job_id, "type": "error", "error_type": type(exc).__name__,
                  "message": str(exc)[:2000]})


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))  # the embeddable Python never adds the script folder
    os.environ[ENV_CHILD] = "1"
    raise SystemExit(_child_main(sys.argv[1:]))
