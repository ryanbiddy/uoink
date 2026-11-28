"""Full paths for file operations made relative to a held directory.

On Linux and macOS the checked storage writer opens, replaces and unlinks
files by name inside a held directory descriptor (``dir_fd``) instead of by
full path. Tests that watch or fail particular files use these helpers so the
same check runs on every platform.
"""
from __future__ import annotations

import os
from pathlib import Path


def directory_of(fd) -> Path | None:
    if fd is None:
        return None
    try:
        return Path(os.readlink(f"/proc/self/fd/{fd}"))
    except OSError:
        pass
    try:
        import fcntl
        raw = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
        return Path(os.fsdecode(raw.split(b"\0", 1)[0]))
    except (ImportError, AttributeError, OSError):
        return None


def full_path(name, dir_fd=None) -> Path:
    path = Path(os.fsdecode(name))
    base = directory_of(dir_fd)
    return path if base is None or path.is_absolute() else base / path


def replace_target(target, kwargs) -> Path:
    return full_path(target, kwargs.get("dst_dir_fd"))


def replace_source(source, kwargs) -> Path:
    return full_path(source, kwargs.get("src_dir_fd"))
