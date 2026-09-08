"""Loaded as sitecustomize by BD's isolated pytest subprocesses."""
import importlib.abc
import os
from pathlib import Path
import sys
import socket
import threading

ROOT = Path(os.environ["BD_WORKTREE_ROOT"]).resolve()
SCRATCH = ROOT / "_scratch" / "bd"
os.environ.pop("ANTHROPIC_API_KEY", None)


class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "whisperx", "whisper", "faster_whisper", "torch", "torchaudio",
            "pyannote", "transformers", "anthropic", "openai", "keyring",
        }:
            raise ImportError("BD offline guard: inference and credential providers disabled")


sys.meta_path.insert(0, NoModels())
_scope = threading.local()
_socketpair = socket.socketpair


def local_socketpair(*args, **kwargs):
    # Windows asyncio uses an ephemeral loopback socket pair as a self-pipe.
    # Permit only this stdlib construction, never an application connection.
    _scope.socketpair = True
    try:
        return _socketpair(*args, **kwargs)
    finally:
        _scope.socketpair = False


socket.socketpair = local_socketpair


def audit(event, args):
    if event in {"socket.connect", "socket.connect_ex", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
        if getattr(_scope, "socketpair", False):
            return
        raise OSError("BD offline guard: network disabled")
    if event == "sqlite3.connect":
        database = os.fsdecode(args[0])
        if database != ":memory:":
            # No connection, even read-only, may follow the copied DB's old paths.
            if database.startswith("file:") or not Path(database).resolve().is_relative_to(ROOT):
                raise OSError("BD offline guard: database outside worktree")
    if event == "subprocess.Popen":
        executable, argv = args[:2]
        command = str(executable or argv).lower()
        if "python" not in command or "server.py" in command:
            raise OSError("BD offline guard: only test Python subprocesses permitted")
    if event in {"os.system", "os.startfile", "os.startfile/2"}:
        raise OSError("BD offline guard: shell/player launch disabled")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path, mode, flags = args
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing:
            resolved = Path(os.fsdecode(path)).resolve()
            if resolved == Path(os.devnull).resolve():
                return
            if not resolved.is_relative_to(ROOT) or resolved == ROOT / "token.txt":
                raise PermissionError("BD offline guard: write outside disposable scope")


sys.addaudithook(audit)
