"""Isolated vault I/O worker for library_mirror.

One interpreter per resync operation. The parent talks JSON-lines over stdin/
stdout and kills this process (Windows job object / POSIX process group) when
the caller's deadline expires. This process is the only one that mutates the
vault, so a terminated worker cannot publish or roll back destination bytes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys


def _reply(payload: dict) -> None:
    sys.stdout.buffer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def _sha256_path(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 64)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _handle(req: dict) -> dict:
    cmd = req.get("cmd")
    if cmd == "shutdown":
        return {"ok": True, "shutdown": True}
    if cmd == "mkdir":
        os.makedirs(req["path"], exist_ok=bool(req.get("exist_ok", True)))
        return {"ok": True}
    if cmd == "write":
        data = base64.b64decode(req["b64"])
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY if hasattr(os, "O_BINARY") else os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(req["path"], flags, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return {"ok": True, "hash": hashlib.sha256(data).hexdigest()}
    if cmd == "replace":
        os.replace(req["src"], req["dst"])
        return {"ok": True}
    if cmd == "unlink":
        try:
            os.unlink(req["path"])
        except FileNotFoundError:
            return {"ok": True, "gone": True}
        return {"ok": True}
    if cmd == "sha256":
        return {"ok": True, "hash": _sha256_path(req["path"])}
    if cmd == "exists":
        return {"ok": True, "exists": os.path.lexists(req["path"])}
    return {"ok": False, "error": "unknown_cmd"}


def main() -> int:
    sys.stdout.buffer.write((json.dumps({"ok": True, "ready": True}) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except (json.JSONDecodeError, UnicodeError, TypeError):
            _reply({"ok": False, "error": "bad_request"})
            continue
        if not isinstance(req, dict):
            _reply({"ok": False, "error": "bad_request"})
            continue
        try:
            result = _handle(req)
        except OSError as exc:
            _reply({
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
                "errno": getattr(exc, "errno", None),
            })
            continue
        except Exception as exc:
            _reply({"ok": False, "error": type(exc).__name__, "message": str(exc)})
            continue
        _reply(result)
        if result.get("shutdown"):
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
