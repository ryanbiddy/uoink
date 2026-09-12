"""Lossless stdio recorder for the installed Phase 4 receipt.

Adapted from the reviewed AW recorder into a new file. It does not inject
requests, alter messages, or call a model. Isolation flags are required.
Each launch creates a fresh recording directory; prior receipts are kept.
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

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from p4_common import FORBIDDEN_PORT, IsolationError, ENV_ROOT_KEYS, require_no_api_key, require_port
try:
    from p4_session import spawn_owned, _read_chunk
except ImportError:
    spawn_owned = None
    _read_chunk = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isolated-profile", type=Path, required=True)
    parser.add_argument("--isolated-port", required=True)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--record-dir", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--route-label", required=True,
                        help="original-installed | fixture-attached | synthetic-instrument")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not Path(command[0]).is_absolute():
        parser.error("child command must name an absolute executable")
    try:
        require_no_api_key()
        port = require_port(args.isolated_port)
        root = args.fixture_root.resolve(strict=True)
        profile = args.isolated_profile.resolve(strict=True)
        cwd = args.cwd.resolve(strict=True)
        record_parent = args.record_dir.parent.resolve(strict=True)
    except IsolationError as exc:
        parser.error(str(exc))
    installed_app = os.environ.get("P4_INSTALLED_APP")
    allowed_cwd = cwd.is_relative_to(root) or cwd == profile
    if installed_app:
        try:
            allowed_cwd = allowed_cwd or cwd.resolve() == Path(installed_app).resolve()
        except OSError:
            allowed_cwd = False
    if not allowed_cwd:
        parser.error("working directory must stay in the fixture/profile or be the declared installed app")
    if not record_parent.is_relative_to(root):
        parser.error("recording directory must stay in the fixture")
    if not profile.is_absolute() or port == FORBIDDEN_PORT:
        parser.error("explicit isolated profile and non-5179 port are required")
    declared_profile = os.environ.get("P4_ISOLATED_PROFILE")
    declared_port = os.environ.get("P4_ISOLATED_PORT")
    if not declared_profile or Path(declared_profile).resolve() != profile:
        parser.error("P4_ISOLATED_PROFILE must match --isolated-profile")
    if not declared_port or int(declared_port) != port:
        parser.error("P4_ISOLATED_PORT must match --isolated-port")
    for name in ENV_ROOT_KEYS:
        value = os.environ.get(name)
        if not value:
            parser.error(f"{name} must resolve inside the isolated profile")
        resolved = Path(value).resolve()
        if resolved.is_relative_to(profile):
            continue
        if name in ("LOCALAPPDATA", "APPDATA"):
            original = os.environ.get("P4_ORIGINAL_LOCALAPPDATA")
            if original and resolved == Path(original).resolve():
                continue
            if name == "APPDATA":
                continue
        parser.error(f"{name} must resolve inside the isolated profile")
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
                "route_label": args.route_label, **fields,
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
           isolated_profile=str(profile), isolated_port=port,
           route_label=args.route_label,
           environment_roots={key: os.environ[key] for key in ENV_ROOT_KEYS},
           api_key_present=False,
           executable_sha256=hashlib.sha256(Path(command[0]).read_bytes()).hexdigest())
    owned = None
    child = None
    try:
        if spawn_owned is None:
            raise IsolationError("p4_session.spawn_owned is required for owned-tree tap launch")
        if args.route_label in ("original-installed", "fixture-attached"):
            guard_path = profile / "guard" / "sitecustomize.py"
            if not guard_path.is_file():
                raise IsolationError(
                    "tap refused: receipt guard sitecustomize missing before product launch"
                )
        owned = spawn_owned(
            command, cwd=cwd, env=os.environ.copy(), label="p4-tap-child",
        )
        child = owned.popen
    except Exception as exc:
        record("launch_failed", error_type=type(exc).__name__, error=str(exc))
        log.close()
        raise
    record("child_started", child_pid=child.pid, job_assigned=owned._job_assigned if owned else False,
           owned_pids=sorted(owned._owned_pids) if owned else [child.pid])

    def pump(source, destination, direction: str, *, close_destination=False) -> None:
        buf = b""
        try:
            while True:
                chunk = _read_chunk(source) if _read_chunk is not None else source.readline()
                if not chunk:
                    if buf:
                        frame(direction, buf)
                        try:
                            destination.write(buf)
                            destination.flush()
                        except OSError:
                            pass
                        record("partial_frame", direction=direction, bytes=len(buf))
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    raw = line + b"\n"
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

    incoming = threading.Thread(
        target=pump, args=(sys.stdin.buffer, child.stdin, "client_to_server"),
        kwargs={"close_destination": True}, daemon=True)
    outgoing = threading.Thread(
        target=pump, args=(child.stdout, sys.stdout.buffer, "server_to_client"), daemon=True)
    diagnostics = threading.Thread(
        target=pump, args=(child.stderr, sys.stderr.buffer, "server_stderr"), daemon=True)
    incoming.start()
    outgoing.start()
    diagnostics.start()
    try:
        code = child.wait()
    except BaseException:
        record("wrapper_interrupted", child_pid=child.pid)
        if owned is not None:
            owned.terminate_tree(timeout=5)
        else:
            child.kill()
            child.wait(timeout=5)
        code = child.poll()
        raise
    finally:
        outgoing.join(timeout=5)
        diagnostics.join(timeout=5)
        with lock:
            unfinished = [{"direction": key[0], "id_json": key[1], "method": value[1]}
                          for key, value in pending.items()]
        snap = owned.descendant_snapshot() if owned is not None else {}
        record("child_exit", child_pid=child.pid, exit_code=child.returncode,
               incomplete_requests=unfinished, forwarding_failed=fatal.is_set(),
               output_drain_complete=not outgoing.is_alive() and not diagnostics.is_alive(),
               descendants=snap)
        if owned is not None:
            owned.terminate_tree(timeout=5)
        log.flush()
        os.fsync(log.fileno())
    return code if code else (1 if fatal.is_set() else 0)


if __name__ == "__main__":
    raise SystemExit(main())
