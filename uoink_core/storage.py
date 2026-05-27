r"""uoink_core.storage -- pure filesystem/path helpers (Sprint 21 split).

Lifted verbatim from server.py with no behavior change: atomic text writes and
the writable-directory probe. These depend only on the stdlib (no server-side
mutable globals such as DESKTOP_ROOT), so they live cleanly here and are
re-exported by server.py for backward compatibility. The only non-functional
difference is the logger name (`uoink.storage`, a child of `uoink`, propagating
to the same handlers) -- log text is unchanged.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger("uoink.storage")


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write text via temp file + replace so crashy exits don't leave partial files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        # Path.replace() can raise PermissionError when the destination file
        # is momentarily held open by OneDrive sync -- and the default
        # DESKTOP_ROOT lives under OneDrive. Retry with short backoff before
        # giving up so a transient sync lock doesn't lose the write.
        for delay in (0.05, 0.2, 0.5, None):
            try:
                tmp.replace(path)
                break
            except PermissionError:
                if delay is None:
                    log.warning("atomic write to %s failed after retries "
                                "(destination locked?)", path)
                    raise
                time.sleep(delay)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _is_writable_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    probe = path / f".yoink-write-test-{os.getpid()}-{uuid.uuid4().hex}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        return False
