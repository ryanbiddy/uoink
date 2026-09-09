"""Lossless stdio recorder for the isolated AW real-client observation.

This is acceptance instrumentation, not a client or a production adapter.
It does not inject requests, alter messages, or call a model. Launch it as
the client-owned MCP command; place the actual child command after ``--``.
All output is private evidence. A byte transcript is distinct from a model's
description of what happened, and recorded latency includes recorder overhead.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--record-dir", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not Path(command[0]).is_absolute():
        parser.error("child command must name an absolute executable")
    root = args.fixture_root.resolve(strict=True)
    cwd = args.cwd.resolve(strict=True)
    record_parent = args.record_dir.parent.resolve(strict=True)
    if not cwd.is_relative_to(root) or not record_parent.is_relative_to(root):
        parser.error("working and recording directories must stay in the fixture")
    if os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("ANTHROPIC_API_KEY must be absent")
    required_roots = ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "UOINK_OUTPUT_DIR")
    for name in required_roots:
        value = os.environ.get(name)
        if not value or not Path(value).resolve().is_relative_to(root):
            parser.error(f"{name} must resolve inside the fixture")
    # Each client reconnect gets its own directory; never overwrite a receipt.
    record_dir = record_parent / f"{args.record_dir.name}-{os.getpid()}"
    record_dir.mkdir(exist_ok=False)
    lock = threading.Lock()
    pending: dict[tuple[str, str], tuple[int, str | None]] = {}
    log = (record_dir / "events.jsonl").open("x", encoding="utf-8", newline="\n")
    fatal = threading.Event()

    def record(kind: str, **fields) -> None:
        with lock:
            event = {
                "kind": kind, "utc": datetime.now(timezone.utc).isoformat(),
                "monotonic_ns": time.perf_counter_ns(), "wrapper_pid": os.getpid(),
                **fields,
            }
            log.write(json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n")
            log.flush()

    def frame(direction: str, raw: bytes) -> None:
        received = time.perf_counter_ns()
        fields = {"direction": direction, "received_ns": received,
                  "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                  "base64": base64.b64encode(raw).decode("ascii")}
        try:
            message = json.loads(raw)
        except (ValueError, UnicodeError):
            message = None
        if isinstance(message, dict):
            fields["method"] = message.get("method")
            if "id" in message:
                fields["request_id"] = message["id"]
                identity = json.dumps(message["id"], sort_keys=True)
                with lock:
                    if "method" in message:
                        pending[(direction, identity)] = (received, message["method"])
                    else:
                        other = "client_to_server" if direction == "server_to_client" else "server_to_client"
                        origin = pending.pop((other, identity), None)
                        if origin:
                            fields["request_method"] = origin[1]
                            fields["elapsed_ms"] = (received - origin[0]) / 1_000_000
        record("frame", **fields)

    record("launch", command=command, cwd=str(cwd), fixture_root=str(root),
           environment_roots={key: os.environ[key] for key in required_roots},
           api_key_present=False, executable_sha256=hashlib.sha256(Path(command[0]).read_bytes()).hexdigest())
    try:
        child = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        record("launch_failed", error_type=type(exc).__name__, error=str(exc))
        log.close()
        raise
    record("child_started", child_pid=child.pid)

    def pump(source, destination, direction: str, *, close_destination=False) -> None:
        try:
            while True:
                raw = source.readline()
                if not raw:
                    break
                frame(direction, raw)
                destination.write(raw)
                destination.flush()
            record("stream_eof", direction=direction)
        except (OSError, ValueError) as exc:
            fatal.set()
            record("stream_failed", direction=direction, error_type=type(exc).__name__, error=str(exc))
        finally:
            if close_destination:
                try:
                    destination.close()
                except OSError:
                    pass

    incoming = threading.Thread(target=pump, args=(sys.stdin.buffer, child.stdin, "client_to_server"),
                                kwargs={"close_destination": True}, daemon=True)
    outgoing = threading.Thread(target=pump, args=(child.stdout, sys.stdout.buffer, "server_to_client"), daemon=True)
    diagnostics = threading.Thread(target=pump, args=(child.stderr, sys.stderr.buffer, "server_stderr"), daemon=True)
    incoming.start()
    outgoing.start()
    diagnostics.start()
    try:
        code = child.wait()
    except BaseException:
        # Terminate only the exact stdio child this recorder created.
        record("wrapper_interrupted", child_pid=child.pid)
        child.kill()
        code = child.wait(timeout=5)
        raise
    finally:
        outgoing.join(timeout=5)
        diagnostics.join(timeout=5)
        with lock:
            unfinished = [{"direction": key[0], "id_json": key[1], "method": value[1]}
                          for key, value in pending.items()]
        record("child_exit", child_pid=child.pid, exit_code=child.returncode,
               incomplete_requests=unfinished, forwarding_failed=fatal.is_set(),
               output_drain_complete=not outgoing.is_alive() and not diagnostics.is_alive())
        # The stdin thread may still wait on an open client pipe at normal child
        # exit. Process exit ends that daemon; stdout/stderr were drained above.
        log.flush()
        os.fsync(log.fileno())
    return code if code else (1 if fatal.is_set() else 0)


if __name__ == "__main__":
    raise SystemExit(main())
