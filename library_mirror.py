"""library_mirror.py - Opt-in corpus mirror (contract phase4-v1-2026-09-08).

One-way generated view of Librarian cards, shelf pages and accepted briefs
under ``<vault>/Uoink/``. Vault I/O is derived delivery state: it never
owns Phase 2 pins, exclusive policies or the correction journal, never
reads ``TASTE.md`` / ``USER.md`` back, and never routes through
``memory_layer.write_user``.

Contract rules this module does not implement exactly, and why
--------------------------------------------------------------
1. Isolated worker cancellation. Vault mutation runs in one child process
   per resync (not per file), assigned to a Windows kill-on-close job or a
   POSIX process group. The caller's deadline kills that worker and waits
   until it can no longer mutate the destination. A hung ``os.replace`` in
   the parent interpreter is not used. Source/dependency checks stay in the
   parent against authoritative storage immediately before publication.
2. Mirror-specific codes (``destination_unavailable``, ``user_edit_conflict``,
   ``unmanaged_conflict``, ``path_collision``, ``purge_blocked_user_edit``)
   are returned through ``library_resources.refusal``, not
   ``ResourceError``, because that type remaps unknown codes to
   ``internal_error``.
3. Brief artifacts are exported only when a ``brief_store`` with
   ``latest_valid`` / ``read`` / ``purge_dependents`` is supplied. The
   ``library_briefs`` import is optional so this module loads without it.
4. ``st_nlink > 1`` is treated as a containment/ownership failure on the
   destination file. Windows link counts are not always meaningful; the
   check is skipped when ``st_nlink`` is missing or zero.
"""
from __future__ import annotations

import base64
import contextlib
import ctypes
import hashlib
import json
import logging
import os
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator

import library_cards
from library_resources import (
    CONTRACT_VERSION as _RESOURCES_CONTRACT,
    LIMITS,
    RENDER_VERSION,
    SCHEMA_VERSION,
    ResourceError,
    label,
    refusal,
    safe_url,
)

try:
    import library_briefs as _library_briefs  # optional; guarded for import-time
except ImportError:
    _library_briefs = None  # type: ignore[assignment]

log = logging.getLogger("uoink.library_mirror")

CONTRACT_VERSION = "phase4-v1-2026-09-08"
MIRROR_LEDGER_DIR = "reach/mirror"
MIRROR_ROOT = "Uoink"
SCOPE_ALL = "all_current_and_future_items"

MAX_FILE_BYTES = 65536
DEFAULT_MAX_FILES = 20
DEFAULT_BUDGET_S = 2.0
VOLUME_MARKER_NAME = ".uoink-volume-marker"
MANIFEST_REL = ".uoink-mirror/manifest.json"
LIBRARY_INDEX_REL = "Library.md"
TASTE_NAME = "TASTE.md"
USER_NAME = "USER.md"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BRIEF_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([0-9a-f]{64})\.md$")
_OUR_TMP_RE = re.compile(r"^[0-9a-f]{12,24}$")

_CONTENT_KINDS = frozenset({
    "capture", "source_refresh", "apply", "undo", "pin",
    "brief_published", "restore",
})
_TOMBSTONE_KINDS = frozenset({"soft_delete"})
_PURGE_KINDS = frozenset({"hard_purge"})

INDEXING_NOTICE = (
    "Other software with access to this vault can index its contents. "
    "Uoink does not register the vault with Basic Memory/Hermes, start "
    "another indexer, edit its configuration, turn on sync, or infer "
    "consent from an installed application. Existing third-party indexing "
    "is outside Uoink's deletion control."
)
EDITS_NOTICE = "Edits to this file are not imported."
TOMBSTONE_BODY = "This library item was deleted. Source content is not exported.\n"


# --------------------------------------------------------------------------
# Public types
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MirrorConsent:
    destination: str
    scope: str
    allowlist: tuple[str, ...]
    consented_at_ms: int
    marker: str


# --------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------
def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_date(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def identity_hash(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def item_relpath(video_id: str) -> str:
    return f"Library/{identity_hash(video_id)}.md"


def shelf_relpath(shelf_id: str) -> str:
    return f"Shelves/{identity_hash(shelf_id)}.md"


def brief_relpath(date: str, brief_hash: str) -> str:
    return f"Briefs/{date}-{brief_hash}.md"


def item_key(video_id: str) -> str:
    return f"item:{video_id}"


def shelf_key(shelf_id: str) -> str:
    return f"shelf:{shelf_id}"


def brief_key(date: str, brief_hash: str) -> str:
    return f"brief:{date}:{brief_hash}"


def index_key() -> str:
    return "index:Library.md"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _yaml_quote(value: str) -> str:
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f"\"{escaped}\""


def _break_injections(text: str) -> str:
    """Neutralize wikilinks, images, and raw HTML tag openers in generated views."""
    text = text.replace("[[", "[\\[")
    text = text.replace("]]", "\\]]")
    text = text.replace("![", "\\!\\[")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _safe_label(value: Any, limit: int = 200) -> str:
    """Safely escape active markdown syntax in display labels."""
    cleaned = label(str(value) if value is not None else "", limit=limit)
    cleaned = (
        cleaned
        .replace("\\", "\\\\")
        .replace("!", "\\!")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("`", "\\`")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return cleaned


def _frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, int) and not isinstance(value, bool):
            lines.append(f"{key}: {value}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {_yaml_quote(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _cap_utf8(text: str, limit: int = MAX_FILE_BYTES) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    cut = raw[:limit]
    while cut:
        try:
            return cut.decode("utf-8")
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""


def _rel_is_allowed(rel: str) -> bool:
    if rel in (LIBRARY_INDEX_REL, MANIFEST_REL):
        return True
    if rel.startswith("Library/") and rel.endswith(".md"):
        stem = rel[len("Library/"):-3]
        return bool(_HEX64_RE.match(stem))
    if rel.startswith("Shelves/") and rel.endswith(".md"):
        stem = rel[len("Shelves/"):-3]
        return bool(_HEX64_RE.match(stem))
    if rel.startswith("Briefs/") and rel.endswith(".md"):
        name = rel[len("Briefs/"):]
        return bool(_BRIEF_NAME_RE.match(name))
    return False


def _is_reparse(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attrs = getattr(info, "st_file_attributes", 0)
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _contained(root: Path, path: Path) -> bool:
    try:
        root_r = root.resolve()
        path_r = path.resolve()
    except OSError:
        return False
    root_s = os.path.normcase(str(root_r))
    path_s = os.path.normcase(str(path_r))
    sep = os.sep
    return path_s == root_s or path_s.startswith(root_s + sep)


def _escaping_reparse(root: Path, path: Path) -> bool:
    try:
        root_r = root.resolve()
    except OSError:
        return True
    current = path
    seen = 0
    while seen < 64:
        seen += 1
        if _is_reparse(current):
            try:
                resolved = current.resolve()
            except OSError:
                return True
            if not _contained(root_r, resolved) and resolved != root_r:
                return True
        if current == current.parent:
            break
        try:
            if current.resolve() == root_r:
                break
        except OSError:
            return True
        current = current.parent
    return False


def _hardlink_conflict(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    nlink = getattr(info, "st_nlink", 1)
    return isinstance(nlink, int) and nlink > 1


def _path_too_long(path: Path) -> bool:
    text = str(path)
    return len(text) > 240 or len(text.encode("utf-8", errors="replace")) > 240


def _mirror_refusal(code: str, message: str, *, retryable: bool = False,
                    details: dict | None = None, **extra) -> dict:
    envelope = refusal(code, message, retryable=retryable, details=details)
    envelope.update(extra)
    return envelope


def _ok(**fields) -> dict:
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        **fields,
    }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _pending_temps_from_intent(intent: dict | None) -> list[dict]:
    """Collect recorded temps without dropping prior generations."""
    if not isinstance(intent, dict):
        return []
    out: list[dict] = []
    seen: set[str] = set()

    def add(rel: str, digest: str, file_id: int | None = None, volume_id: int | None = None) -> None:
        if not rel or rel in seen:
            return
        seen.add(rel)
        entry: dict[str, Any] = {"rel": rel, "hash": digest or ""}
        if file_id:
            entry["file_id"] = file_id
        if volume_id is not None:
            entry["volume_id"] = volume_id
        out.append(entry)

    for item in intent.get("pending_temps") or []:
        if isinstance(item, dict):
            add(
                str(item.get("rel") or ""),
                str(item.get("hash") or ""),
                _optional_int(item.get("file_id")),
                _optional_int(item.get("volume_id")),
            )
        elif isinstance(item, str):
            add(item, "")
    add(
        str(intent.get("temp_rel") or ""),
        str(intent.get("temp_hash") or ""),
        _optional_int(intent.get("temp_file_id")),
        _optional_int(intent.get("temp_volume_id")),
    )
    return out


def _safe_temp_path(uoink: Path, rel: str) -> Path | None:
    if not rel or os.path.isabs(rel):
        return None
    rel_path = Path(rel)
    if ".." in rel_path.parts:
        return None
    path = uoink / rel_path
    if not _contained(uoink, path):
        return None
    return path


def _pid_is_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        k32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return int(code.value) == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, PermissionError, ValueError):
        return False
    return True


def _dest_lease_path(dest: str) -> Path:
    canonical = os.path.normcase(os.path.realpath(str(dest)))
    dest_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    lock_dir = Path(tempfile.gettempdir()) / "uoink-mirror-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"{dest_key}.lease"


def _read_dest_lease(dest: str) -> dict:
    path = _dest_lease_path(dest)
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_dest_lease(dest: str, payload: dict) -> None:
    path = _dest_lease_path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with open(tmp, "xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _clear_dest_lease(dest: str, pid: int | None = None) -> None:
    path = _dest_lease_path(dest)
    try:
        if pid is not None:
            current = _read_dest_lease(dest)
            if current.get("pid") not in (None, pid) and _pid_is_alive(current.get("pid")):
                return
        path.unlink()
    except OSError:
        pass


def _foreign_vault_worker_alive(dest: str, our_pid: int | None = None) -> bool:
    lease = _read_dest_lease(dest)
    pid = lease.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    if our_pid is not None and pid == our_pid:
        return False
    return _pid_is_alive(pid)


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _win_create_kill_job():
    if os.name != "nt":
        return None
    k32 = ctypes.windll.kernel32
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = k32.SetInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info), ctypes.sizeof(info),
    )
    if not ok:
        k32.CloseHandle(job)
        return None
    return job


def _win_assign_job(job, proc: subprocess.Popen) -> bool:
    if job is None or os.name != "nt":
        return False
    handle = getattr(proc, "_handle", None)
    if not handle:
        return False
    k32 = ctypes.windll.kernel32
    return bool(k32.AssignProcessToJobObject(job, int(handle)))


class _VaultIoSession:
    """One isolated vault-I/O interpreter for a single resync."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.job = None
        self.dest = ""
        self.startup_s = 0.0
        self._rpc_lock = threading.Lock()
        self._dead = False

    @property
    def pid(self) -> int | None:
        proc = self.proc
        return int(proc.pid) if proc is not None and proc.pid else None

    @property
    def alive(self) -> bool:
        proc = self.proc
        return (not self._dead) and proc is not None and proc.poll() is None

    def _readline(self, timeout: float | None = None) -> bytes | None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return None
        box: dict[str, Any] = {}

        def reader() -> None:
            try:
                box["line"] = proc.stdout.readline()
            except Exception as exc:
                box["error"] = exc

        thread = threading.Thread(target=reader, name="uoink-vault-io-read", daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            return None
        if "error" in box:
            return None
        line = box.get("line")
        return line if isinstance(line, (bytes, bytearray)) else None

    @classmethod
    def start(cls, dest: str) -> "_VaultIoSession":
        session = cls()
        session.dest = dest
        t0 = time.monotonic()
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("ANTHROPIC_API_KEY", None)
        root = str(Path(__file__).resolve().parent)
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        worker = str(Path(__file__).resolve().parent / "library_mirror_vault_io.py")
        kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "env": env,
            "cwd": root,
        }
        if os.name == "nt":
            kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            kwargs["start_new_session"] = True
        session.proc = subprocess.Popen(
            [sys.executable, "-B", worker],
            **kwargs,
        )
        if os.name == "nt":
            session.job = _win_create_kill_job()
            if session.job is not None:
                _win_assign_job(session.job, session.proc)
        ready_line = session._readline(timeout=15.0)
        session.startup_s = time.monotonic() - t0
        ready = None
        if ready_line:
            try:
                ready = json.loads(ready_line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeError, TypeError):
                ready = None
        if not isinstance(ready, dict) or not ready.get("ready") or not session.alive:
            session.terminate()
            raise OSError("vault io worker failed to start")
        _write_dest_lease(dest, {
            "pid": session.pid,
            "destination": dest,
            "ppid": os.getpid(),
        })
        return session

    def call(self, req: dict) -> dict:
        with self._rpc_lock:
            if not self.alive or self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
                raise OSError("vault io worker is not running")
            payload = json.dumps(req, ensure_ascii=False).encode("utf-8") + b"\n"
            try:
                self.proc.stdin.write(payload)
                self.proc.stdin.flush()
                raw = self.proc.stdout.readline()
            except (OSError, BrokenPipeError, ValueError) as exc:
                self._dead = True
                raise OSError("vault io worker closed") from exc
            if not raw:
                self._dead = True
                raise OSError("vault io worker closed")
            try:
                result = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeError, TypeError) as exc:
                raise OSError("vault io worker returned invalid status") from exc
            if not isinstance(result, dict):
                raise OSError("vault io worker returned invalid status")
            return result

    def write_file(self, path: str, data: bytes) -> dict:
        result = self.call({
            "cmd": "write",
            "path": path,
            "b64": base64.b64encode(data).decode("ascii"),
        })
        if not result.get("ok"):
            raise OSError(result.get("error") or "write failed")
        return result

    def replace(self, src: str, dst: str) -> None:
        result = self.call({"cmd": "replace", "src": src, "dst": dst})
        if not result.get("ok"):
            raise OSError(result.get("error") or "replace failed")

    def unlink(
        self,
        path: str,
        expected_file_id: int | None = None,
        expected_hash: str | None = None,
        expected_volume_id: int | None = None,
    ) -> dict:
        req: dict[str, Any] = {"cmd": "unlink", "path": path}
        if expected_file_id is not None:
            req["expected_file_id"] = int(expected_file_id)
        if expected_volume_id is not None:
            req["expected_volume_id"] = int(expected_volume_id)
        if expected_hash is not None:
            req["expected_hash"] = str(expected_hash)
        result = self.call(req)
        if result.get("not_ours") or result.get("gone"):
            return result
        if not result.get("ok"):
            raise OSError(result.get("error") or "unlink failed")
        return result

    def file_identity(self, path: str) -> tuple[int | None, int | None]:
        try:
            result = self.call({"cmd": "file_id", "path": path})
        except OSError:
            return None, None
        if not result.get("ok"):
            return None, None
        fid = _optional_int(result.get("file_id"))
        vol = _optional_int(result.get("volume_id"))
        if not fid:
            return None, None
        return fid, vol

    def file_id(self, path: str) -> int | None:
        fid, _vol = self.file_identity(path)
        return fid

    def mkdir(self, path: str, exist_ok: bool = True) -> None:
        result = self.call({"cmd": "mkdir", "path": path, "exist_ok": exist_ok})
        if not result.get("ok"):
            raise OSError(result.get("error") or "mkdir failed")

    def sha256(self, path: str) -> str | None:
        try:
            result = self.call({"cmd": "sha256", "path": path})
        except OSError:
            return None
        if not result.get("ok"):
            return None
        digest = result.get("hash")
        return digest if isinstance(digest, str) else None

    def terminate(self) -> None:
        self._dead = True
        proc = self.proc
        job = self.job
        dest = self.dest
        pid = self.pid
        if job is not None and os.name == "nt":
            try:
                ctypes.windll.kernel32.TerminateJobObject(job, 1)
            except Exception:
                pass
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=2.0)
            except Exception:
                pass
        if proc is not None:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        if job is not None and os.name == "nt":
            try:
                ctypes.windll.kernel32.CloseHandle(job)
            except Exception:
                pass
        self.proc = None
        self.job = None
        if dest:
            _clear_dest_lease(dest, pid)

    def shutdown(self) -> None:
        try:
            if self.alive:
                self.call({"cmd": "shutdown"})
        except OSError:
            pass
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                proc.wait(timeout=1.0)
            except Exception:
                self.terminate()
                return
        dest = self.dest
        pid = self.pid
        self._dead = True
        self.proc = None
        if self.job is not None and os.name == "nt":
            try:
                ctypes.windll.kernel32.CloseHandle(self.job)
            except Exception:
                pass
            self.job = None
        if dest:
            _clear_dest_lease(dest, pid)


# --------------------------------------------------------------------------
# Mirror
# --------------------------------------------------------------------------
class Mirror:
    """Opt-in one-way corpus mirror. Ledger under data_root; files under vault/Uoink."""

    def __init__(self, index, reader, brief_store, *, data_root,
                 consent: MirrorConsent | None, enabled: bool,
                 clock: Callable[[], float] | None = None,
                 wall_clock: Callable[[], float] | None = None):
        self.index = index
        self.reader = reader
        self.brief_store = brief_store
        self.data_root = Path(data_root)
        self.consent = consent
        self.enabled = bool(enabled)
        self._clock = clock or time.monotonic
        self._wall = wall_clock or time.time
        self._thread_lock = threading.RLock()
        self._vault_io: _VaultIoSession | None = None
        self._vault_io_startup_s = 0.0
        self._unlink_expected: dict[str, Any] | None = None
        self.ledger_dir = self.data_root / MIRROR_LEDGER_DIR

    # ---- public API ----------------------------------------------------
    def preview(self, destination: str, scope: str,
                allowlist: list[str] | None = None) -> dict:
        dest = Path(destination) if destination else None
        if dest is None or not self._destination_exists(dest):
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                planned_paths=[],
                counts={"items": 0, "shelves": 0, "briefs": 0},
                notice=INDEXING_NOTICE,
                indexing=INDEXING_NOTICE,
                third_party_indexing=INDEXING_NOTICE,
                destination_unavailable=True,
            )
        allow = tuple(allowlist or ())
        items = self._in_scope_items(scope, allow)
        shelves = self._in_scope_shelves(scope, allow, items)
        briefs = self._in_scope_briefs(scope, allow)
        planned: list[str] = []
        for item in items:
            planned.append(item_relpath(item["video_id"]))
        for shelf in shelves:
            planned.append(shelf_relpath(shelf["shelf_id"]))
        for brief in briefs:
            planned.append(brief_relpath(brief["date"], brief["brief_hash"]))
        planned.append(LIBRARY_INDEX_REL)
        planned.append(MANIFEST_REL)
        uoink = dest / MIRROR_ROOT
        conflicts: list[dict] = []
        for rel in planned:
            path = uoink / rel
            try:
                if path.exists() and path.is_file():
                    conflicts.append({"path": rel, "code": "unmanaged_conflict"})
            except OSError:
                pass
        return _ok(
            planned_paths=planned,
            paths=planned,
            counts={"items": len(items), "shelves": len(shelves), "briefs": len(briefs)},
            notice=INDEXING_NOTICE,
            indexing=INDEXING_NOTICE,
            third_party_indexing=INDEXING_NOTICE,
            conflicts=conflicts,
            destination=str(dest),
            scope=scope,
        )

    def status(self) -> dict:
        if self.consent is None or not self.consent.destination:
            return _ok(
                enabled=False,
                state="disabled",
                pending=0,
                synced=0,
                stale=0,
                conflicts={},
                deletion_pending=0,
                destination_state="disabled",
                destination_available=False,
            )
        dest = Path(self.consent.destination)
        available = self._destination_exists(dest)
        ledger = self._load_ledger()
        pending = synced = stale = deletion_pending = 0
        user_edits: list[dict] = []
        for key, entry in ledger.get("entries", {}).items():
            action = entry.get("pending_action") or "none"
            status = entry.get("status") or ""
            if action in ("purge", "tombstone") or status == "deletion_pending":
                deletion_pending += 1
            elif action == "write" or status == "pending":
                pending += 1
            elif status == "stale":
                stale += 1
            elif status == "synced":
                synced += 1
            if status == "user_edit_conflict":
                user_edits.append({"key": key, "path": entry.get("relpath")})
                pending += 1
        unmanaged = []
        collisions = []
        if available:
            unmanaged, collisions, extra_edits = self._scan_conflicts(dest, ledger)
            user_edits.extend(extra_edits)
        else:
            return _ok(
                enabled=bool(self.enabled),
                state="destination_unavailable",
                pending=pending,
                synced=0,
                stale=stale,
                conflicts={"user_edit": user_edits, "unmanaged": [], "path_collision": []},
                deletion_pending=deletion_pending,
                destination_state="unavailable",
                destination_available=False,
                destination_unavailable=True,
            )
        conflicts = {
            "user_edit": user_edits,
            "unmanaged": unmanaged,
            "path_collision": collisions,
        }
        paused = bool(ledger.get("exports_paused"))
        return _ok(
            enabled=bool(self.enabled),
            state="disabled" if not self.enabled else ("paused" if paused else "ready"),
            pending=pending,
            synced=synced,
            stale=stale,
            conflicts=conflicts,
            unmanaged=unmanaged,
            deletion_pending=deletion_pending,
            destination_state="available",
            destination_available=True,
            exports_paused=paused,
        )

    def resync(self, *, max_files: int = DEFAULT_MAX_FILES, budget_s: float = DEFAULT_BUDGET_S) -> dict:
        if self.consent is None or not self.consent.destination:
            return _ok(synced=0, enabled=False, state="disabled")
        if not self.enabled:
            ledger = self._load_ledger()
            has_deletions = any(
                (e.get("pending_action") in ("purge", "tombstone") or e.get("status") == "deletion_pending")
                for e in ledger.get("entries", {}).values()
            )
            if not has_deletions:
                return _ok(synced=0, enabled=False, state="disabled")
        start = float(self._clock())
        try:
            with self._exclusive(timeout=max(0.05, float(budget_s))):
                if _foreign_vault_worker_alive(self.consent.destination):
                    return _mirror_refusal(
                        "destination_unavailable",
                        "The mirror destination is unavailable.",
                        retryable=True,
                        destination_unavailable=True,
                        synced=0,
                    )
                remaining = float(budget_s) - (float(self._clock()) - start)
                return self._resync_locked(max_files=int(max_files), budget_s=max(0.0, remaining))
        except _LockTimeout:
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
            )

    def on_committed_event(self, kind: str, *, video_id: str | None = None,
                           shelf_id: str | None = None, brief_hash: str | None = None) -> None:
        if self.consent is None or not self.consent.destination:
            return
        if not self.enabled and kind not in _PURGE_KINDS and kind not in _TOMBSTONE_KINDS:
            return
        try:
            with self._exclusive(timeout=2.0):
                self._record_event(kind, video_id=video_id, shelf_id=shelf_id, brief_hash=brief_hash)
        except Exception:
            log.exception("mirror ledger update failed for %s", kind)

    def tombstone(self, video_id: str) -> dict:
        if self.consent is None or not self.consent.destination:
            return _ok(tombstoned=False, enabled=False)
        try:
            with self._exclusive(timeout=DEFAULT_BUDGET_S):
                self._record_event("soft_delete", video_id=video_id)
                return self._resync_locked(max_files=DEFAULT_MAX_FILES, budget_s=DEFAULT_BUDGET_S)
        except Exception as exc:
            log.exception("mirror tombstone failed")
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                details={"reason": type(exc).__name__},
            )

    def purge(self, video_id: str) -> dict:
        if self.consent is None or not self.consent.destination:
            return _ok(purged=True, enabled=False)
        try:
            with self._exclusive(timeout=DEFAULT_BUDGET_S):
                self._record_event("hard_purge", video_id=video_id)
                result = self._resync_locked(max_files=DEFAULT_MAX_FILES, budget_s=DEFAULT_BUDGET_S)
                return result
        except Exception as exc:
            log.exception("mirror purge failed")
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                details={"reason": type(exc).__name__},
            )

    def restore(self, video_id: str) -> dict:
        if not self._is_enabled():
            return _ok(restored=False, enabled=False)
        try:
            with self._exclusive(timeout=DEFAULT_BUDGET_S):
                self._record_event("restore", video_id=video_id)
                return self._resync_locked(max_files=DEFAULT_MAX_FILES, budget_s=DEFAULT_BUDGET_S)
        except Exception as exc:
            log.exception("mirror restore failed")
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                details={"reason": type(exc).__name__},
            )

    # ---- enablement / scope -------------------------------------------
    def _is_enabled(self) -> bool:
        return bool(self.enabled) and self.consent is not None

    def _in_scope_id(self, video_id: str, scope: str | None = None,
                     allowlist: tuple[str, ...] | None = None) -> bool:
        if scope is None:
            if self.consent is None:
                return False
            scope = self.consent.scope
            allowlist = self.consent.allowlist
        if scope == SCOPE_ALL:
            return True
        allowed = allowlist if allowlist is not None else ()
        return video_id in allowed

    def _destination_exists(self, dest: Path) -> bool:
        def probe() -> bool:
            try:
                return dest.exists() and dest.is_dir()
            except OSError:
                return False
        value, err = self._run_cancellable(probe, 2.0)
        return bool(value) and err is None

    # ---- index snapshots (never vault I/O) ----------------------------
    def _index_lock(self):
        lock = getattr(self.index, "_lock", None)
        return lock if lock is not None and hasattr(lock, "__enter__") else contextlib.nullcontext()

    def _sql(self, sql: str, params: tuple = ()) -> list[dict]:
        conn = getattr(self.index, "_conn", None)
        if conn is None:
            return []
        try:
            with self._index_lock():
                rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            log.debug("mirror index query failed", exc_info=True)
            return []

    def _live_items(self) -> list[dict]:
        rows = self._sql(
            "SELECT video_id, title, slug, channel, yoinked_at, deleted_at "
            "FROM yoinks WHERE deleted_at IS NULL ORDER BY yoinked_at DESC, video_id"
        )
        out = []
        for row in rows:
            vid = row.get("video_id")
            if isinstance(vid, str) and vid:
                out.append(row)
        return out

    def _in_scope_items(self, scope: str, allowlist: tuple[str, ...]) -> list[dict]:
        return [row for row in self._live_items() if self._in_scope_id(row["video_id"], scope, allowlist)]

    def _in_scope_shelves(self, scope: str, allowlist: tuple[str, ...],
                          items: list[dict]) -> list[dict]:
        allowed_ids = {row["video_id"] for row in items}
        try:
            tables = self._sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                "('library_meta','shelf_nodes','item_shelves','shelf_versions')"
            )
            names = {r.get("name") for r in tables}
            if len(names) < 4:
                return []
            meta = self._sql("SELECT projection_revision, active_version_id FROM library_meta WHERE singleton=1")
            if not meta or not meta[0].get("active_version_id"):
                return []
            version_id = meta[0]["active_version_id"]
            nodes = self._sql(
                "SELECT shelf_id, name FROM shelf_nodes WHERE version_id=? AND retired=0 ORDER BY shelf_id",
                (version_id,),
            )
            out = []
            for node in nodes:
                sid = node.get("shelf_id")
                if not isinstance(sid, str) or not sid:
                    continue
                members = self._sql(
                    "SELECT s.video_id AS video_id FROM item_shelves s "
                    "JOIN yoinks y ON y.video_id = s.video_id "
                    "WHERE s.shelf_id=? AND y.deleted_at IS NULL",
                    (sid,),
                )
                member_ids = [m["video_id"] for m in members if isinstance(m.get("video_id"), str)]
                if scope != SCOPE_ALL:
                    member_ids = [vid for vid in member_ids if vid in allowed_ids]
                    if not member_ids:
                        continue
                out.append({"shelf_id": sid, "name": node.get("name"), "members": member_ids})
            return out
        except Exception:
            return []

    def _in_scope_briefs(self, scope: str, allowlist: tuple[str, ...]) -> list[dict]:
        store = self.brief_store
        if store is None or not hasattr(store, "latest_valid"):
            return []
        date = _utc_date(self._wall())
        try:
            rec = store.latest_valid(date)
        except Exception:
            return []
        if not isinstance(rec, dict) or not rec.get("brief_hash"):
            return []
        bhash = rec["brief_hash"]
        bdate = rec.get("date") or date
        deps = []
        if hasattr(store, "validated_dependencies"):
            try:
                deps = store.validated_dependencies(bdate, bhash)
            except Exception:
                deps = []
        if not deps:
            deps = rec.get("dependencies") or rec.get("source_item_ids") or []
        if not deps:
            return []
        if scope != SCOPE_ALL:
            allowed = set(allowlist)
            if not all(dep in allowed for dep in deps):
                return []
        return [{"date": bdate, "brief_hash": bhash, "dependencies": deps}]

    def _item_snapshot(self, video_id: str) -> tuple[dict | None, list[dict]]:
        def run():
            with self._index_lock():
                row = self.index.get_yoink(video_id)
                if row is None:
                    return None, []
                clips = self.index.get_clips(video_id) if hasattr(self.index, "get_clips") else []
                return dict(row), [dict(c) for c in clips]
        try:
            return run()
        except Exception:
            log.debug("mirror item snapshot failed", exc_info=True)
            return None, []

    def _build_item_document(self, video_id: str) -> tuple[bytes | None, str | None, str | None]:
        item, clips = self._item_snapshot(video_id)
        if item is None:
            return None, None, None
        if item.get("deleted_at") is not None:
            return None, None, "deleted"
        try:
            card, _head = self.reader._build_card(item, clips)
            self.reader._assert_card_safe(card, item)
        except ResourceError:
            return None, None, "unsafe"
        except Exception:
            log.debug("mirror card build failed", exc_info=True)
            return None, None, "unsafe"
        source_link = safe_url(card.get("url"))
        generated_at = _utc_iso(self._wall())
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "item",
            "identity": video_id,
            "source_revision": card.get("source_revision") or "",
            "card_hash": card.get("card_hash") or "",
            "generated_at": generated_at,
            "notice": EDITS_NOTICE,
        }
        if source_link:
            fields["source_url"] = source_link
        body = library_cards.card_text(card)
        text = _frontmatter(fields) + "\n" + body + "\n\n" + EDITS_NOTICE + "\n"
        text = _break_injections(text)
        text = _cap_utf8(text)
        dep = str(card.get("card_hash") or card.get("source_revision") or "")
        return text.encode("utf-8"), dep, None

    def _build_tombstone_document(self, video_id: str) -> bytes:
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "item",
            "identity": video_id,
            "deleted": True,
            "deleted_at": _utc_iso(self._wall()),
            "notice": EDITS_NOTICE,
        }
        text = _frontmatter(fields) + "\n" + TOMBSTONE_BODY
        return _cap_utf8(_break_injections(text)).encode("utf-8")

    def _build_shelf_document(self, shelf_id: str, allowed: set[str] | None) -> tuple[bytes | None, str | None]:
        try:
            deadline = float(self._clock()) + DEFAULT_BUDGET_S
            op = _BudgetOp(self.reader, deadline)
            snapshot = self.reader._shelf_snapshot(op, shelf_id)
        except Exception:
            return None, None
        definition = snapshot.get("definition") or {}
        members = []
        for member in snapshot.get("members") or []:
            vid = member.get("video_id")
            if not isinstance(vid, str):
                continue
            if allowed is not None and vid not in allowed:
                continue
            members.append({
                "video_id": vid,
                "relpath": "../" + item_relpath(vid),
                "title": _safe_label(member.get("title") or vid),
            })
        generated_at = _utc_iso(self._wall())
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "shelf",
            "identity": shelf_id,
            "taxonomy_revision": (snapshot.get("taxonomy") or {}).get("taxonomy_revision") or "",
            "projection_revision": (snapshot.get("taxonomy") or {}).get("projection_revision") or 0,
            "shelf_revision": snapshot.get("shelf_revision") or "",
            "generated_at": generated_at,
            "notice": EDITS_NOTICE,
        }
        name = _safe_label(definition.get("name") or shelf_id)
        lines = [f"# {name}", "", f"Members: {len(members)}", ""]
        for member in members[:20]:
            lines.append(f"- [{member['title']}]({member['relpath']})")
        if len(members) > 20:
            lines.append("")
            lines.append(f"Omissions: {len(members) - 20} additional members not listed.")
        lines.extend(["", EDITS_NOTICE, ""])
        text = _frontmatter(fields) + "\n" + "\n".join(lines)
        text = _cap_utf8(_break_injections(text))
        dep = str(snapshot.get("shelf_revision") or "")
        return text.encode("utf-8"), dep

    def _build_brief_document(self, date: str, brief_hash: str) -> tuple[bytes | None, list[str], list[dict], dict]:
        store = self.brief_store
        if store is None:
            return None, [], [], {}
        deps: list[str] = []
        bound_deps: list[dict] = []
        report_bindings: dict = {}
        if hasattr(store, "_load_artifact"):
            try:
                manifest, _doc, _cits, packet = store._load_artifact(date, brief_hash)
                if isinstance(manifest, dict):
                    bound_deps = manifest.get("dependencies") or []
                    deps = [d["item_id"] for d in bound_deps if isinstance(d, dict) and d.get("item_id")]
                if isinstance(packet, dict):
                    report_bindings = packet.get("bindings") or {}
            except Exception:
                pass
        if not deps and hasattr(store, "validated_dependencies"):
            try:
                deps = store.validated_dependencies(date, brief_hash)
            except Exception:
                deps = []
        document = None
        if hasattr(store, "read"):
            try:
                payload = store.read(date, brief_hash)
            except Exception:
                return None, [], [], {}
            if isinstance(payload, dict):
                contents = payload.get("contents") or []
                if contents and isinstance(contents[0], dict) and "text" in contents[0]:
                    fenced = contents[0]["text"]
                    open_fence = "<untrusted_uoink_library_context>\n"
                    close_fence = "\n</untrusted_uoink_library_context>"
                    if open_fence in fenced and close_fence in fenced:
                        json_str = fenced.split(open_fence, 1)[1].split(close_fence, 1)[0]
                        try:
                            data = json.loads(json_str)
                            document = data.get("document") or data.get("text")
                            if not bound_deps:
                                bound_deps = data.get("dependencies") or []
                            if not deps:
                                deps = [d["item_id"] for d in bound_deps if isinstance(d, dict) and d.get("item_id")]
                        except Exception:
                            pass
                    if not document:
                        document = fenced
                if not document:
                    document = payload.get("document") or payload.get("text")
                if not deps:
                    deps = payload.get("source_item_ids") or payload.get("dependencies") or []
        if not deps:
            return None, [], [], {}
        deps = [d for d in deps if isinstance(d, str)]
        allowed_ids = None
        if self.consent and self.consent.scope != SCOPE_ALL:
            allowed_ids = set(self.consent.allowlist)
        if allowed_ids is not None and not all(d in allowed_ids for d in deps):
            return None, [], [], {}
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "brief",
            "identity": f"{date}/{brief_hash}",
            "date": date,
            "brief_hash": brief_hash,
            "generated_at": _utc_iso(self._wall()),
            "notice": EDITS_NOTICE,
        }
        text = _frontmatter(fields) + "\n" + _break_injections(str(document or "")) + "\n\n" + EDITS_NOTICE + "\n"
        text = _cap_utf8(text)
        return text.encode("utf-8"), deps, bound_deps, report_bindings

    def _build_library_index(self, completed: list[dict], omitted: int,
                             shelf_rows: list[dict], brief_rows: list[dict]) -> bytes:
        generated_at = _utc_iso(self._wall())
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "index",
            "generated_at": generated_at,
            "notice": EDITS_NOTICE,
        }
        lines = [
            "# Library",
            "",
            f"Items: {len(completed)}",
            f"Shelves: {len(shelf_rows)}",
            f"Briefs: {len(brief_rows)}",
            "",
            "## Recent",
            "",
        ]
        for row in completed[:20]:
            title = _safe_label(row.get("title") or row.get("identity") or "")
            rel = row.get("relpath") or ""
            ident = _safe_label(row.get("identity") or "").replace("`", "")
            lines.append(f"- [{title}]({rel}) `{ident}`")
        if omitted > 0 or len(completed) > 20:
            extra = omitted + max(0, len(completed) - 20)
            lines.append("")
            lines.append(f"Omissions: {extra} additional items not listed.")
        if shelf_rows:
            lines.extend(["", "## Shelves", ""])
            for row in shelf_rows[:10]:
                title = _safe_label(row.get("title") or row.get("identity") or "")
                lines.append(f"- [{title}]({row.get('relpath')})")
        if brief_rows:
            lines.extend(["", "## Briefs", ""])
            for row in brief_rows[:5]:
                ident = _safe_label(row.get("identity") or "")
                lines.append(f"- [{ident}]({row.get('relpath')})")
        lines.extend(["", EDITS_NOTICE, ""])
        text = _frontmatter(fields) + "\n" + "\n".join(lines)
        return _cap_utf8(_break_injections(text)).encode("utf-8")

    # ---- durable destination binding ----------------------------------
    def _dest_binding_path(self) -> Path:
        return self.ledger_dir / "destination_binding.json"

    def _authority_witness_path(self) -> Path:
        return self.ledger_dir / "authority_witness.json"

    def _consent_time_ms(self) -> int:
        return int(self.consent.consented_at_ms if self.consent else 0)

    def _read_authority_witness(self) -> dict | str | None:
        p = self._authority_witness_path()
        try:
            if not p.is_file():
                return None
            raw = p.read_text(encoding="utf-8")
            if not raw.strip():
                return "corrupt"
            data = json.loads(raw)
        except OSError:
            return "unavailable"
        except (json.JSONDecodeError, UnicodeError, TypeError):
            return "corrupt"
        if not isinstance(data, dict) or not isinstance(data.get("destination"), str) or not data.get("destination"):
            return "corrupt"
        return data

    def _write_authority_witness(self, dest: str, marker: str, have_synced: bool) -> None:
        p = self._authority_witness_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "destination": dest,
            "marker": marker,
            "have_synced": have_synced,
            "consented_at_ms": self._consent_time_ms(),
        }, ensure_ascii=False, sort_keys=True)
        self._atomic_local(p, payload.encode("utf-8"))

    def _newer_consent_authorizes_dest_change(self, prior_dest: str, prior_consented_at: int, dest_str: str) -> bool:
        if not dest_str or not prior_dest or not self.consent:
            return False
        try:
            dest_changed = os.path.normcase(os.path.realpath(dest_str)) != os.path.normcase(os.path.realpath(prior_dest))
        except OSError:
            return False
        return bool(dest_changed and self._consent_time_ms() > int(prior_consented_at or 0))

    def _has_prior_authority(self) -> tuple[bool, str, int]:
        witness = self._read_authority_witness()
        if witness in ("corrupt", "unavailable"):
            return True, "", 0
        if isinstance(witness, dict) and witness.get("destination") and witness.get("have_synced"):
            return True, str(witness.get("destination")), int(witness.get("consented_at_ms") or 0)
        ledger = self._load_ledger()
        if ledger.get("destination"):
            entries = ledger.get("entries", {})
            has_synced_entry = any(
                int(e.get("written_generation") or 0) > 0 or e.get("status") == "synced"
                for e in entries.values()
            )
            if has_synced_entry:
                consented_at = 0
                if isinstance(witness, dict):
                    consented_at = int(witness.get("consented_at_ms") or 0)
                return True, str(ledger.get("destination")), consented_at
        return False, "", 0

    def _read_dest_binding(self) -> dict | str:
        p = self._dest_binding_path()
        dest_str = str(self.consent.destination) if self.consent and self.consent.destination else ""
        try:
            present = p.is_file()
        except OSError:
            return "unavailable"
        if not present:
            has_prior, prior_dest, prior_consented_at = self._has_prior_authority()
            if has_prior and not self._newer_consent_authorizes_dest_change(prior_dest, prior_consented_at, dest_str):
                return "missing"
            return {}
        try:
            raw = p.read_text(encoding="utf-8")
            if not raw.strip():
                return "corrupt"
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError, UnicodeError, TypeError):
            return "corrupt"
        if not isinstance(data, dict) or not isinstance(data.get("destination"), str) or not data.get("destination"):
            return "corrupt"
        return data

    def _write_dest_binding(self, dest: str, marker: str, have_synced: bool) -> None:
        p = self._dest_binding_path()
        w = self._authority_witness_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "destination": dest,
            "marker": marker,
            "have_synced": have_synced,
            "consented_at_ms": self._consent_time_ms(),
        }, ensure_ascii=False, sort_keys=True)
        try:
            binding_existed = p.is_file()
        except OSError:
            binding_existed = False
        try:
            witness_existed = w.is_file()
        except OSError:
            witness_existed = False
        try:
            self._write_authority_witness(dest, marker, have_synced)
            self._atomic_local(p, payload.encode("utf-8"))
            with open(p, "r+b") as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            if not binding_existed:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            if not witness_existed:
                try:
                    w.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    # ---- ledger --------------------------------------------------------
    def _ledger_path(self) -> Path:
        return self.ledger_dir / "ledger.json"

    def _empty_ledger(self) -> dict:
        dest = self.consent.destination if self.consent else ""
        marker = self.consent.marker if self.consent else ""
        return {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "destination": dest,
            "marker": marker,
            "exports_paused": False,
            "pause_reason": None,
            "entries": {},
            "purged": {},
        }

    def _load_ledger(self) -> dict:
        path = self._ledger_path()
        try:
            if not path.exists():
                return self._empty_ledger()
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._empty_ledger()
            data.setdefault("entries", {})
            data.setdefault("purged", {})
            if not isinstance(data["entries"], dict):
                data["entries"] = {}
            if not isinstance(data["purged"], dict):
                data["purged"] = {}
            return data
        except (OSError, json.JSONDecodeError, UnicodeError, TypeError):
            return self._empty_ledger()

    def _save_ledger(self, ledger: dict) -> None:
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        path = self._ledger_path()
        payload = json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        self._atomic_local(path, payload)

    def _atomic_local(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + "." + secrets.token_hex(12) + ".tmp")
        try:
            with open(tmp, "xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
            tmp = None
        finally:
            if tmp is not None:
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _intent_dir(self) -> Path:
        return self.ledger_dir / "intents"

    def _intent_path(self, key: str) -> Path:
        name = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._intent_dir() / f"{name}.json"

    def _write_intent(self, key: str, payload: dict) -> None:
        path = self._intent_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_local(path, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))

    def _clear_intent(self, key: str) -> None:
        try:
            self._intent_path(key).unlink()
        except OSError:
            pass

    def _load_intents(self) -> dict[str, dict]:
        folder = self._intent_dir()
        out: dict[str, dict] = {}
        try:
            if not folder.exists():
                return out
            for path in folder.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, UnicodeError):
                    continue
                if isinstance(data, dict) and isinstance(data.get("key"), str):
                    out[data["key"]] = data
        except OSError:
            return out
        return out

    def _ensure_entry(self, ledger: dict, key: str, *, kind: str, identity: str, relpath: str) -> dict:
        entries = ledger.setdefault("entries", {})
        entry = entries.get(key)
        if not isinstance(entry, dict):
            entry = {
                "kind": kind,
                "identity": identity,
                "relpath": relpath,
                "desired_generation": 0,
                "written_generation": 0,
                "dependency_hash": "",
                "last_file_hash": "",
                "status": "pending",
                "pending_action": "none",
            }
            entries[key] = entry
        entry.setdefault("relpath", relpath)
        entry.setdefault("kind", kind)
        entry.setdefault("identity", identity)
        return entry

    def _record_event(self, kind: str, *, video_id: str | None = None,
                      shelf_id: str | None = None, brief_hash: str | None = None) -> None:
        ledger = self._load_ledger()
        if self.consent:
            ledger["destination"] = self.consent.destination
            ledger["marker"] = self.consent.marker
        if kind in _PURGE_KINDS and video_id:
            self._record_purge(ledger, video_id)
        elif kind in _TOMBSTONE_KINDS and video_id:
            self._record_tombstone(ledger, video_id)
        elif kind == "restore" and video_id:
            self._record_restore(ledger, video_id)
        elif kind == "brief_published" and brief_hash:
            self._record_brief(ledger, brief_hash)
        else:
            if video_id:
                self._record_item_write(ledger, video_id, kind=kind)
            if shelf_id:
                self._record_shelf_write(ledger, shelf_id)
            if kind in ("apply", "undo", "pin") and video_id and not shelf_id:
                self._record_related_shelves(ledger, video_id)
            if kind in ("source_refresh", "apply", "undo") and not video_id:
                scope = self.consent.scope if self.consent else SCOPE_ALL
                allow = self.consent.allowlist if self.consent else ()
                for item in self._in_scope_items(scope, allow):
                    self._record_item_write(ledger, item["video_id"], kind=kind)
                for shelf in self._in_scope_shelves(scope, allow, self._in_scope_items(scope, allow)):
                    self._record_shelf_write(ledger, shelf["shelf_id"])
        self._save_ledger(ledger)

    def _record_item_write(self, ledger: dict, video_id: str, *, kind: str) -> None:
        if not self._in_scope_id(video_id):
            # Out of scope: if we previously owned a file, schedule cleanup.
            key = item_key(video_id)
            if key in ledger.get("entries", {}):
                self._record_scope_removal(ledger, video_id)
            return
        key = item_key(video_id)
        purged = ledger.get("purged") or {}
        if key in purged and kind != "restore":
            item, _clips = self._item_snapshot(video_id)
            if item is None or item.get("deleted_at") is not None:
                return
            purged.pop(key, None)
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "write"
        entry["status"] = "pending"
        self._bump_index(ledger)

    def _record_tombstone(self, ledger: dict, video_id: str) -> None:
        key = item_key(video_id)
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "tombstone"
        entry["status"] = "deletion_pending"
        self._bump_index(ledger)
        self._invalidate_dependents(ledger, video_id)

    def _record_scope_removal(self, ledger: dict, video_id: str) -> None:
        key = item_key(video_id)
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "purge"
        entry["status"] = "deletion_pending"
        self._bump_index(ledger)
        self._invalidate_dependents(ledger, video_id)

    def _record_purge(self, ledger: dict, video_id: str) -> None:
        key = item_key(video_id)
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "purge"
        entry["status"] = "deletion_pending"
        ledger.setdefault("purged", {})[key] = {
            "identity": video_id,
            "relpath": entry.get("relpath"),
            "generation": entry["desired_generation"],
            "purged_at": _utc_iso(self._wall()),
        }
        self._bump_index(ledger)
        self._invalidate_dependents(ledger, video_id)

    def _record_restore(self, ledger: dict, video_id: str) -> None:
        key = item_key(video_id)
        purged = ledger.get("purged") or {}
        if key in purged:
            item, _clips = self._item_snapshot(video_id)
            if item is None or item.get("deleted_at") is not None:
                return
            purged.pop(key, None)
        if not self._in_scope_id(video_id):
            return
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "write"
        entry["status"] = "pending"
        self._bump_index(ledger)

    def _record_shelf_write(self, ledger: dict, shelf_id: str) -> None:
        key = shelf_key(shelf_id)
        entry = self._ensure_entry(ledger, key, kind="shelf", identity=shelf_id, relpath=shelf_relpath(shelf_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "write"
        entry["status"] = "pending"
        self._bump_index(ledger)

    def _record_brief(self, ledger: dict, brief_hash: str) -> None:
        date = _utc_date(self._wall())
        rec = None
        store = self.brief_store
        if store is not None and hasattr(store, "latest_valid"):
            try:
                rec = store.latest_valid(date)
            except Exception:
                rec = None
        if isinstance(rec, dict) and rec.get("date"):
            date = rec["date"]
            brief_hash = rec.get("brief_hash") or brief_hash
        if not _DATE_RE.match(str(date)) or not _HEX64_RE.match(str(brief_hash)):
            return
        deps = []
        if store is not None and hasattr(store, "validated_dependencies"):
            try:
                deps = store.validated_dependencies(date, brief_hash)
            except Exception:
                deps = []
        if not deps and isinstance(rec, dict):
            deps = rec.get("dependencies") or rec.get("source_item_ids") or []
        key = brief_key(date, brief_hash)
        entry = self._ensure_entry(
            ledger, key, kind="brief", identity=f"{date}/{brief_hash}",
            relpath=brief_relpath(date, brief_hash),
        )
        if deps:
            entry["dependencies"] = [d for d in deps if isinstance(d, str)]
        scope = self.consent.scope if self.consent else SCOPE_ALL
        allow = self.consent.allowlist if self.consent else ()
        if scope != SCOPE_ALL and deps:
            allowed = set(allow)
            if not all(d in allowed for d in deps):
                entry["pending_action"] = "purge"
                entry["status"] = "deletion_pending"
                entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
                self._bump_index(ledger)
                return
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "write"
        entry["status"] = "pending"
        entry["date"] = date
        entry["brief_hash"] = brief_hash
        self._bump_index(ledger)

    def _reconcile_desired_state(self, ledger: dict) -> None:
        if not self.consent:
            return
        scope = self.consent.scope
        allow = self.consent.allowlist
        entries = ledger.setdefault("entries", {})
        purged = ledger.get("purged") or {}

        live_items = self._live_items()
        live_by_id = {item["video_id"]: item for item in live_items}

        for vid, item in live_by_id.items():
            if not self._in_scope_id(vid, scope, allow):
                continue
            key = item_key(vid)
            if key in purged:
                purged.pop(key, None)
            entry = entries.get(key)
            dest = Path(self.consent.destination) if self.consent and self.consent.destination else None
            needs_write = (entry is None or
                           int(entry.get("written_generation") or 0) == 0 or
                           entry.get("status") == "purged" or
                           (dest is not None and not (dest / MIRROR_ROOT / entry.get("relpath", "")).is_file()))
            if needs_write:
                self._record_item_write(ledger, vid, kind="source_refresh")
            else:
                content, dep_new, reason = self._build_item_document(vid)
                if reason == "deleted":
                    self._record_tombstone(ledger, vid)
                elif content is not None and dep_new and dep_new != entry.get("dependency_hash"):
                    self._record_item_write(ledger, vid, kind="source_refresh")

        shelves = self._in_scope_shelves(scope, allow, live_items)
        active_sids = {s["shelf_id"] for s in shelves}
        for s in shelves:
            sid = s["shelf_id"]
            skey = shelf_key(sid)
            sentry = entries.get(skey)
            if sentry is None or int(sentry.get("written_generation") or 0) == 0 or sentry.get("status") == "purged":
                self._record_shelf_write(ledger, sid)
            else:
                content, dep_new = self._build_shelf_document(sid, set(allow) if scope != SCOPE_ALL else None)
                if dep_new and dep_new != sentry.get("dependency_hash"):
                    self._record_shelf_write(ledger, sid)

        brief_list = self._in_scope_briefs(scope, allow)
        active_bkeys = set()
        for b in brief_list:
            bkey = brief_key(b["date"], b["brief_hash"])
            active_bkeys.add(bkey)
            bentry = entries.get(bkey)
            if bentry is None or int(bentry.get("written_generation") or 0) == 0 or bentry.get("status") == "purged":
                self._record_brief(ledger, b["brief_hash"])

        for key, entry in list(entries.items()):
            kind = entry.get("kind")
            ident = entry.get("identity") or ""
            if kind == "item":
                if ident in live_by_id and not self._in_scope_id(ident, scope, allow):
                    if entry.get("pending_action") != "purge" and entry.get("status") != "purged":
                        self._record_scope_removal(ledger, ident)
                elif ident not in live_by_id:
                    if entry.get("pending_action") not in ("purge", "tombstone") and entry.get("status") != "purged":
                        item_snap, _ = self._item_snapshot(ident)
                        if item_snap and item_snap.get("deleted_at") is not None:
                            self._record_tombstone(ledger, ident)
                        else:
                            self._record_purge(ledger, ident)
            elif kind == "shelf":
                if ident not in active_sids:
                    if entry.get("pending_action") != "purge" and entry.get("status") != "purged":
                        entry["pending_action"] = "purge"
                        entry["status"] = "deletion_pending"
                        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
                        self._bump_index(ledger)
            elif kind == "brief":
                if key not in active_bkeys:
                    if entry.get("pending_action") != "purge" and entry.get("status") != "purged":
                        entry["pending_action"] = "purge"
                        entry["status"] = "deletion_pending"
                        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
                        self._bump_index(ledger)
                else:
                    deps = entry.get("dependencies") or []
                    if not deps and hasattr(self.brief_store, "validated_dependencies"):
                        date, bhash = ident.split("/", 1) if "/" in ident else (entry.get("date", ""), entry.get("brief_hash", ""))
                        try:
                            deps = self.brief_store.validated_dependencies(date, bhash)
                        except Exception:
                            deps = []
                    if deps:
                        invalid = any(d not in live_by_id or not self._in_scope_id(d, scope, allow) for d in deps)
                        if invalid:
                            if entry.get("pending_action") != "purge":
                                entry["pending_action"] = "purge"
                                entry["status"] = "deletion_pending"
                                entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
                                self._bump_index(ledger)
                            entry["status"] = "deletion_pending"
                            entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
                            self._bump_index(ledger)

    def _record_related_shelves(self, ledger: dict, video_id: str) -> None:
        rows = self._sql("SELECT DISTINCT shelf_id FROM item_shelves WHERE video_id=?", (video_id,))
        for row in rows:
            sid = row.get("shelf_id")
            if isinstance(sid, str) and sid:
                self._record_shelf_write(ledger, sid)

    def _invalidate_dependents(self, ledger: dict, video_id: str) -> None:
        self._record_related_shelves(ledger, video_id)
        for key, entry in list((ledger.get("entries") or {}).items()):
            if entry.get("kind") != "brief":
                continue
            deps = entry.get("dependencies") or []
            if video_id in deps:
                entry["pending_action"] = "purge"
                entry["status"] = "deletion_pending"
                entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1

    def _bump_index(self, ledger: dict) -> None:
        entry = self._ensure_entry(
            ledger, index_key(), kind="index", identity="Library.md", relpath=LIBRARY_INDEX_REL,
        )
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        if entry.get("pending_action") != "purge":
            entry["pending_action"] = "write"
            if entry.get("status") != "user_edit_conflict":
                entry["status"] = "pending"

    # ---- resync (under exclusive lock) --------------------------------
    def _resync_locked(self, *, max_files: int, budget_s: float) -> dict:
        dest = Path(self.consent.destination)
        if not self._destination_exists(dest):
            ledger = self._load_ledger()
            pending = sum(
                1 for e in ledger.get("entries", {}).values()
                if (e.get("pending_action") or "none") != "none"
            )
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                destination_state="unavailable",
                pending=pending,
                synced=0,
            )
        ledger = self._load_ledger()
        if self.consent:
            ledger["destination"] = self.consent.destination
            ledger["marker"] = self.consent.marker
        dest_binding = self._read_dest_binding()
        dest_str = str(dest)
        if dest_binding in ("corrupt", "unavailable", "missing"):
            return _mirror_refusal(
                "invalid_request",
                "The mirror destination binding needs reconciliation.",
                details={"reason": "reconciliation", "what": "destination_binding"},
                reconciliation=True,
                synced=0,
            )
        bound_dest = dest_binding.get("destination") if isinstance(dest_binding, dict) else None
        dest_matches = bool(
            bound_dest
            and os.path.normcase(os.path.realpath(bound_dest))
            == os.path.normcase(os.path.realpath(dest_str))
        )
        have_synced = bool(isinstance(dest_binding, dict) and dest_matches and dest_binding.get("have_synced"))
        if isinstance(dest_binding, dict) and dest_binding.get("destination") and not dest_matches:
            user_auth_change = bool(
                self.consent
                and int(self.consent.consented_at_ms or 0) > int(dest_binding.get("consented_at_ms") or 0)
            )
            if not user_auth_change:
                return _mirror_refusal(
                    "destination_unavailable",
                    "The mirror destination is unavailable.",
                    retryable=True,
                    destination_unavailable=True,
                    details={"reason": "destination_binding_mismatch"},
                    synced=0,
                )
        if not have_synced:
            try:
                self._write_dest_binding(
                    dest_str, self.consent.marker if self.consent else "", have_synced=False,
                )
            except OSError as exc:
                return _mirror_refusal(
                    "destination_unavailable",
                    "The mirror destination is unavailable.",
                    retryable=True,
                    destination_unavailable=True,
                    details={"reason": type(exc).__name__},
                    synced=0,
                )

        marker_state = self._marker_state(dest)
        if marker_state == "mismatch" or (marker_state == "missing" and have_synced):
            reason = "volume_marker_mismatch" if marker_state == "mismatch" else "volume_marker_missing"
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                details={"reason": reason},
                synced=0,
            )
        uoink = dest / MIRROR_ROOT
        manifest_state = self._read_manifest_bytes(uoink)
        if manifest_state == "corrupt" or (manifest_state is None and have_synced):
            return _mirror_refusal(
                "invalid_request",
                "The mirror ownership manifest needs reconciliation.",
                details={"reason": "reconciliation", "what": "manifest"},
                reconciliation=True,
                synced=0,
            )
        self._reconcile_desired_state(ledger)
        paused = bool(ledger.get("exports_paused")) or not self.enabled
        plan = self._build_plan(ledger, manifest_state if isinstance(manifest_state, dict) else None, paused)
        # Persist intents before vault replacement. Keep outstanding temp records
        # across generations; do not hash Library.md until its exact bytes exist.
        existing_intents = self._load_intents()
        for op in plan["ops"]:
            if op["action"] in ("write", "tombstone") and op.get("content") is not None:
                payload = {
                    "key": op["key"],
                    "relpath": op["relpath"],
                    "content_hash": _sha256_bytes(op["content"]),
                    "generation": op["generation"],
                    "action": op["action"],
                    "identity": op.get("identity"),
                    "kind": op.get("kind"),
                    "pending_temps": _pending_temps_from_intent(existing_intents.get(op["key"])),
                }
                self._write_intent(op["key"], payload)
                existing_intents[op["key"]] = payload
        recovered = self._load_intents()
        plan["intents"] = recovered
        plan["expected_marker"] = self.consent.marker if self.consent else ""
        plan["write_marker"] = marker_state == "missing" and not have_synced
        plan["have_synced"] = have_synced
        plan["max_files"] = max(0, int(max_files))
        plan["dest"] = str(dest)
        cancel_event = threading.Event()
        plan["cancelled"] = cancel_event

        def work():
            return self._vault_work(plan)

        try:
            self._start_vault_io(dest_str)
        except OSError as exc:
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
                details={"reason": type(exc).__name__, "what": "vault_io_worker"},
            )
        deadline = float(self._clock()) + max(0.0, float(budget_s))
        plan["deadline_mono"] = deadline
        remaining = max(0.01, deadline - float(self._clock()))
        try:
            result, err = self._run_cancellable(work, remaining)
            if err == "timeout" or result is None:
                cancel_event.set()
                self._kill_vault_io()
                return _mirror_refusal(
                    "destination_unavailable",
                    "The mirror destination is unavailable.",
                    retryable=True,
                    destination_unavailable=True,
                    synced=0,
                )
            if isinstance(err, Exception):
                cancel_event.set()
                log.exception("mirror vault worker failed")
                return _mirror_refusal(
                    "destination_unavailable",
                    "The mirror destination is unavailable.",
                    retryable=True,
                    destination_unavailable=True,
                    synced=0,
                    details={"reason": type(err).__name__},
                )
            return self._apply_receipts(ledger, result)
        finally:
            self._stop_vault_io()

    def _marker_state(self, dest: Path) -> str:
        expected = (self.consent.marker if self.consent else "") or ""
        paths = [dest / VOLUME_MARKER_NAME, dest / MIRROR_ROOT / VOLUME_MARKER_NAME]

        def read_one(path: Path) -> str | None:
            try:
                if not path.exists() or not path.is_file():
                    return None
                if _is_reparse(path):
                    return None
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                return None

        values = []
        for path in paths:
            value, err = self._run_cancellable(lambda p=path: read_one(p), 2.0)
            if err == "timeout":
                return "mismatch"
            if isinstance(value, str):
                values.append(value)
        if not values:
            return "missing"
        if expected and any(v != expected for v in values):
            return "mismatch"
        return "ok"

    def _read_manifest_bytes(self, uoink: Path):
        path = uoink / ".uoink-mirror" / "manifest.json"

        def load():
            if not path.exists():
                return None
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError, UnicodeError):
                return "corrupt"
            if not isinstance(data, dict):
                return "corrupt"
            ownership = data.get("ownership") or data.get("by_path")
            if ownership is None:
                data["ownership"] = {}
                return data
            if not isinstance(ownership, dict):
                return "corrupt"
            data["ownership"] = ownership
            return data

        value, err = self._run_cancellable(load, 2.0)
        if err == "timeout":
            return "corrupt"
        if err is not None:
            return "corrupt"
        return value

    def _build_plan(self, ledger: dict, manifest: dict | None, paused: bool) -> dict:
        ownership = (manifest or {}).get("ownership") or {}
        ops: list[dict] = []
        allowed_ids = None
        if self.consent and self.consent.scope != SCOPE_ALL:
            allowed_ids = set(self.consent.allowlist)
        # Deletions first.
        for key, entry in list(ledger.get("entries", {}).items()):
            action = entry.get("pending_action") or "none"
            if action not in ("purge", "tombstone"):
                continue
            rel = entry.get("relpath") or ""
            if not _rel_is_allowed(rel):
                continue
            owned = False
            rec = ownership.get(rel)
            if isinstance(rec, dict) and rec.get("key") == key:
                owned = True
            if entry.get("last_file_hash"):
                owned = True
            content = None
            if action == "tombstone" and entry.get("kind") == "item":
                content = self._build_tombstone_document(entry.get("identity") or "")
            ops.append({
                "action": action,
                "key": key,
                "kind": entry.get("kind"),
                "identity": entry.get("identity"),
                "relpath": rel,
                "generation": int(entry.get("desired_generation") or 0),
                "expected_hash": entry.get("last_file_hash") or (rec.get("file_hash") if isinstance(rec, dict) else ""),
                "owned": owned,
                "content": content,
            })
        if not paused:
            for key, entry in list(ledger.get("entries", {}).items()):
                action = entry.get("pending_action") or "none"
                if action != "write":
                    continue
                if entry.get("kind") == "index":
                    continue
                rel = entry.get("relpath") or ""
                if not _rel_is_allowed(rel):
                    continue
                purged = ledger.get("purged") or {}
                if key in purged and entry.get("kind") == "item":
                    continue
                content = None
                dep = entry.get("dependency_hash") or ""
                kind = entry.get("kind")
                if kind == "item":
                    vid = entry.get("identity") or ""
                    content, dep_new, reason = self._build_item_document(vid)
                    if reason == "deleted":
                        content = self._build_tombstone_document(vid)
                        ops.append({
                            "action": "tombstone",
                            "key": key,
                            "kind": kind,
                            "identity": vid,
                            "relpath": rel,
                            "generation": int(entry.get("desired_generation") or 0),
                            "expected_hash": entry.get("last_file_hash") or "",
                            "owned": bool(entry.get("last_file_hash") or ownership.get(rel)),
                            "content": content,
                            "dependencies": [],
                        })
                        continue
                    if content is None:
                        continue
                    dep = dep_new or dep
                    entry["dependency_hash"] = dep
                elif kind == "shelf":
                    content, dep_new = self._build_shelf_document(entry.get("identity") or "", allowed_ids)
                    if content is None:
                        continue
                    dep = dep_new or dep
                    entry["dependency_hash"] = dep
                elif kind == "brief":
                    date = entry.get("date") or ""
                    bhash = entry.get("brief_hash") or ""
                    if "/" in str(entry.get("identity") or ""):
                        date, bhash = str(entry["identity"]).split("/", 1)
                    content, deps, bound_deps, report_bindings = self._build_brief_document(date, bhash)
                    if content is None:
                        continue
                    if allowed_ids is not None and deps and not all(d in allowed_ids for d in deps):
                        continue
                    entry["dependencies"] = deps
                else:
                    continue
                rec = ownership.get(rel)
                owned = isinstance(rec, dict) and rec.get("key") == key
                if entry.get("last_file_hash"):
                    owned = True
                ops.append({
                    "action": "write",
                    "key": key,
                    "kind": kind,
                    "identity": entry.get("identity"),
                    "relpath": rel,
                    "date": date if kind == "brief" else "",
                    "brief_hash": bhash if kind == "brief" else "",
                    "generation": int(entry.get("desired_generation") or 0),
                    "expected_hash": entry.get("last_file_hash") or (rec.get("file_hash") if isinstance(rec, dict) else ""),
                    "owned": owned,
                    "content": content,
                    "dependency_hash": dep,
                    "dependencies": list(entry.get("dependencies") or (deps if kind == "brief" else [])),
                    "bound_dependencies": bound_deps if kind == "brief" else [],
                    "report_bindings": report_bindings if kind == "brief" else {},
                })
        catalog = []
        for key, entry in (ledger.get("entries") or {}).items():
            if entry.get("kind") != "item":
                continue
            if (entry.get("pending_action") or "none") in ("purge", "tombstone"):
                continue
            if key in (ledger.get("purged") or {}):
                continue
            title = ""
            item, _c = self._item_snapshot(entry.get("identity") or "")
            if item:
                title = item.get("title") or ""
            catalog.append({
                "key": key,
                "identity": entry.get("identity"),
                "relpath": entry.get("relpath"),
                "title": title,
            })
        shelf_catalog = []
        for key, entry in (ledger.get("entries") or {}).items():
            if entry.get("kind") == "shelf" and (entry.get("pending_action") or "none") != "purge":
                shelf_catalog.append({
                    "key": key,
                    "identity": entry.get("identity"),
                    "relpath": entry.get("relpath"),
                    "title": entry.get("identity"),
                })
        brief_catalog = []
        for key, entry in (ledger.get("entries") or {}).items():
            if entry.get("kind") == "brief" and (entry.get("pending_action") or "none") != "purge":
                brief_catalog.append({
                    "key": key,
                    "identity": entry.get("identity"),
                    "relpath": entry.get("relpath"),
                })
        index_entry = (ledger.get("entries") or {}).get(index_key())
        plan = {
            "ops": ops,
            "catalog": catalog,
            "shelf_catalog": shelf_catalog,
            "brief_catalog": brief_catalog,
            "index_expected_hash": (index_entry or {}).get("last_file_hash") or "",
            "index_generation": int((index_entry or {}).get("desired_generation") or 0),
            "rewrite_index": bool(index_entry and (index_entry.get("pending_action") == "write") and not paused),
        }
        self._save_ledger(ledger)
        return plan

    def _vault_work(self, plan: dict) -> dict:
        self._active_plan = plan
        self._active_key = None
        dest = Path(plan["dest"])
        try:
            if not dest.exists() or not dest.is_dir():
                return {"ok": False, "code": "destination_unavailable", "receipts": []}
        except OSError:
            return {"ok": False, "code": "destination_unavailable", "receipts": []}
        uoink = dest / MIRROR_ROOT
        try:
            if not uoink.exists():
                self._io_mkdir(uoink, exist_ok=False)
        except OSError:
            return {"ok": False, "code": "destination_unavailable", "receipts": []}
        if not _contained(dest, uoink) or _escaping_reparse(dest, uoink):
            return {"ok": False, "code": "destination_unavailable", "receipts": []}
        if plan.get("write_marker"):
            marker_path = uoink / VOLUME_MARKER_NAME
            expected = plan.get("expected_marker") or ""
            if expected and not marker_path.exists():
                try:
                    self._io_write_file(marker_path, expected.encode("utf-8"))
                except OSError:
                    pass
        manifest_path = uoink / ".uoink-mirror" / "manifest.json"
        ownership, manifest_error = self._load_ownership(manifest_path)
        if manifest_error == "corrupt":
            return {"ok": False, "code": "reconciliation", "receipts": [], "synced": 0}
        receipts: list[dict] = []
        self._recover_intents(uoink, plan.get("intents") or {}, ownership, receipts)
        self._cleanup_owned_temps(uoink, ownership, plan)
        used = 0
        max_files = int(plan.get("max_files") or 0)
        deadline = float(plan.get("deadline_mono") or 0)

        def budget_left() -> bool:
            return float(self._clock()) <= deadline and used < max_files

        # Deletions / tombstones first.
        for op in plan["ops"]:
            if not budget_left():
                break
            if op["action"] not in ("purge", "tombstone"):
                continue
            receipt = self._apply_op(uoink, op, ownership, plan=plan)
            receipts.append(receipt)
            if receipt.get("counted"):
                used += 1
            if receipt.get("code") == "purge_blocked_user_edit":
                return {
                    "ok": False,
                    "code": "purge_blocked_user_edit",
                    "purge_blocked_user_edit": True,
                    "receipts": receipts,
                    "ownership": ownership,
                    "used": used,
                }
        for op in plan["ops"]:
            if not budget_left():
                break
            if op["action"] != "write":
                continue
            receipt = self._apply_op(uoink, op, ownership, plan=plan)
            receipts.append(receipt)
            if receipt.get("counted"):
                used += 1
        if plan.get("rewrite_index") and budget_left():
            live = []
            for row in plan.get("catalog") or []:
                rel = row.get("relpath") or ""
                rec = ownership.get(rel)
                path = uoink / rel
                if not isinstance(rec, dict):
                    continue
                if rec.get("key") != row.get("key"):
                    continue
                if rec.get("tombstone"):
                    continue
                try:
                    if path.exists():
                        live.append(row)
                except OSError:
                    continue
            shelves = []
            for row in plan.get("shelf_catalog") or []:
                rec = ownership.get(row.get("relpath") or "")
                if isinstance(rec, dict) and rec.get("key") == row.get("key"):
                    shelves.append(row)
            briefs = []
            for row in plan.get("brief_catalog") or []:
                rec = ownership.get(row.get("relpath") or "")
                if isinstance(rec, dict) and rec.get("key") == row.get("key"):
                    briefs.append(row)
            omitted = max(0, len(plan.get("catalog") or []) - len(live))
            content = self._build_library_index(live, omitted, shelves, briefs)
            index_payload = {
                "key": index_key(),
                "relpath": LIBRARY_INDEX_REL,
                "content_hash": _sha256_bytes(content),
                "generation": int(plan.get("index_generation") or 0),
                "action": "write",
                "identity": "Library.md",
                "kind": "index",
                "pending_temps": _pending_temps_from_intent(self._load_intents().get(index_key())),
            }
            self._write_intent(index_key(), index_payload)
            index_op = {
                "action": "write",
                "key": index_key(),
                "kind": "index",
                "identity": "Library.md",
                "relpath": LIBRARY_INDEX_REL,
                "generation": int(plan.get("index_generation") or 0),
                "expected_hash": plan.get("index_expected_hash") or "",
                "owned": LIBRARY_INDEX_REL in ownership or bool(plan.get("index_expected_hash")),
                "content": content,
            }
            receipt = self._apply_op(uoink, index_op, ownership, plan=plan)
            receipts.append(receipt)
            if receipt.get("counted"):
                used += 1
        try:
            self._write_manifest(manifest_path, uoink, ownership)
        except OSError as exc:
            return {
                "ok": False,
                "code": "destination_unavailable",
                "manifest_failed": True,
                "receipts": receipts,
                "ownership": ownership,
                "used": used,
                "reason": type(exc).__name__,
            }
        return {"ok": True, "receipts": receipts, "ownership": ownership, "used": used}

    def _load_ownership(self, manifest_path: Path) -> tuple[dict, str | None]:
        if not manifest_path.exists():
            return {}, None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return {}, "corrupt"
        if not isinstance(data, dict):
            return {}, "corrupt"
        ownership = data.get("ownership") or data.get("by_path") or {}
        if not isinstance(ownership, dict):
            return {}, "corrupt"
        return ownership, None

    def _write_manifest(self, manifest_path: Path, uoink: Path, ownership: dict) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "ownership": ownership,
        }
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        self._atomic_vault(manifest_path, data, uoink, recheck=lambda: True)

    def _recover_intents(self, uoink: Path, intents: dict, ownership: dict, receipts: list) -> None:
        for key, intent in intents.items():
            rel = intent.get("relpath") or ""
            if not _rel_is_allowed(rel):
                continue
            path = uoink / rel
            try:
                if not path.exists():
                    continue
            except OSError:
                continue
            digest = _sha256_file(path)
            if digest and digest == intent.get("content_hash"):
                ownership[rel] = {
                    "key": key,
                    "kind": intent.get("kind"),
                    "identity": intent.get("identity"),
                    "file_hash": digest,
                    "generation": intent.get("generation"),
                    "tombstone": intent.get("action") == "tombstone",
                }
                receipts.append({
                    "key": key,
                    "action": "recover",
                    "ok": True,
                    "file_hash": digest,
                    "generation": intent.get("generation"),
                    "relpath": rel,
                    "counted": False,
                })

    def _try_unlink_recorded_temp(
        self,
        uoink: Path,
        rel: str,
        expected_hash: str,
        expected_file_id: int | None = None,
        expected_volume_id: int | None = None,
    ) -> str:
        """Delete only the recorded file. Returns gone, not_ours, or failed."""
        path = _safe_temp_path(uoink, rel)
        if path is None:
            return "not_ours"
        if not expected_file_id:
            return "failed"
        if not expected_hash:
            return "not_ours"
        self._unlink_expected = {
            "path": str(path),
            "file_id": int(expected_file_id),
            "volume_id": int(expected_volume_id) if expected_volume_id is not None else None,
            "hash": str(expected_hash),
        }
        try:
            unlink_res = self._io_unlink(path)
            if isinstance(unlink_res, dict):
                if unlink_res.get("not_ours"):
                    return "not_ours"
                if unlink_res.get("gone") or unlink_res.get("ok"):
                    return "gone"
            return "gone"
        except OSError:
            return "failed"
        finally:
            self._unlink_expected = None

    def _cleanup_intent_temps(self, uoink: Path, key: str, intent: dict | None) -> list[dict]:
        kept: list[dict] = []
        for item in _pending_temps_from_intent(intent):
            rel = str(item.get("rel") or "")
            digest = str(item.get("hash") or "")
            fid = _optional_int(item.get("file_id"))
            vol = _optional_int(item.get("volume_id"))
            status = self._try_unlink_recorded_temp(
                uoink, rel, digest, expected_file_id=fid, expected_volume_id=vol,
            )
            if status == "failed":
                kept_entry: dict[str, Any] = {"rel": rel, "hash": digest}
                if fid:
                    kept_entry["file_id"] = fid
                if vol is not None:
                    kept_entry["volume_id"] = vol
                kept.append(kept_entry)
        return kept

    def _retain_or_clear_intent(self, key: str, uoink: Path | None = None) -> None:
        intent = self._load_intents().get(key)
        if not intent:
            return
        dest = uoink
        if dest is None and self.consent and self.consent.destination:
            dest = Path(self.consent.destination) / MIRROR_ROOT
        kept = self._cleanup_intent_temps(dest, key, intent) if dest is not None else _pending_temps_from_intent(intent)
        if kept:
            stub = dict(intent)
            stub["key"] = key
            stub["action"] = stub.get("action") or "cleanup"
            stub.pop("temp_rel", None)
            stub.pop("temp_hash", None)
            stub.pop("temp_file_id", None)
            stub.pop("temp_volume_id", None)
            stub["pending_temps"] = kept
            self._write_intent(key, stub)
        else:
            self._clear_intent(key)

    def _record_allocated_temp(
        self,
        key: str,
        temp_rel: str,
        temp_hash: str,
        file_id: int | None = None,
        volume_id: int | None = None,
    ) -> None:
        if not key:
            raise OSError("temp allocation is missing an intent key")
        if not temp_rel or not temp_hash:
            raise OSError("temp allocation is missing path or content identity")
        if not file_id:
            dest = None
            if self.consent and self.consent.destination:
                dest = Path(self.consent.destination) / MIRROR_ROOT
            elif getattr(self, "_vault_io", None) and getattr(self._vault_io, "dest", None):
                dest = Path(self._vault_io.dest) / MIRROR_ROOT
            if dest is not None:
                path = _safe_temp_path(dest, temp_rel)
                if path is not None:
                    try:
                        file_id, volume_id = self._io_file_identity(path)
                    except OSError:
                        file_id, volume_id = None, None
        intent = self._load_intents().get(key) or {"key": key}
        pending = _pending_temps_from_intent(intent)
        entry: dict[str, Any] = {"rel": temp_rel, "hash": temp_hash}
        if file_id:
            entry["file_id"] = int(file_id)
        if volume_id is not None:
            entry["volume_id"] = int(volume_id)
        updated = False
        for item in pending:
            if item.get("rel") == temp_rel:
                item["hash"] = temp_hash
                if file_id:
                    item["file_id"] = int(file_id)
                if volume_id is not None:
                    item["volume_id"] = int(volume_id)
                updated = True
                break
        if not updated:
            pending.append(entry)
        intent["pending_temps"] = pending
        intent["temp_rel"] = temp_rel
        intent["temp_hash"] = temp_hash
        if file_id:
            intent["temp_file_id"] = int(file_id)
        else:
            intent.pop("temp_file_id", None)
        if volume_id is not None:
            intent["temp_volume_id"] = int(volume_id)
        else:
            intent.pop("temp_volume_id", None)
        self._write_intent(key, intent)

    def _clear_current_temp_rel(self, key: str) -> None:
        intent = self._load_intents().get(key)
        if not intent:
            return
        pending = _pending_temps_from_intent(intent)
        current = intent.get("temp_rel")
        if current:
            pending = [item for item in pending if item.get("rel") != current]
        intent.pop("temp_rel", None)
        intent.pop("temp_hash", None)
        intent.pop("temp_file_id", None)
        intent.pop("temp_volume_id", None)
        intent["pending_temps"] = pending
        self._write_intent(key, intent)

    def _cleanup_owned_temps(self, uoink: Path, ownership: dict, plan: dict) -> None:
        intents = self._load_intents()
        for key, intent in list(intents.items()):
            kept = self._cleanup_intent_temps(uoink, key, intent)
            if kept:
                intent = dict(intent)
                intent.pop("temp_rel", None)
                intent.pop("temp_hash", None)
                intent.pop("temp_file_id", None)
                intent.pop("temp_volume_id", None)
                intent["pending_temps"] = kept
                self._write_intent(key, intent)
            elif intent.get("temp_rel") or intent.get("pending_temps"):
                intent = dict(intent)
                intent.pop("temp_rel", None)
                intent.pop("temp_hash", None)
                intent.pop("temp_file_id", None)
                intent.pop("temp_volume_id", None)
                intent["pending_temps"] = []
                if intent.get("content_hash"):
                    self._write_intent(key, intent)
                else:
                    self._clear_intent(key)

    def _apply_op(self, uoink: Path, op: dict, ownership: dict, plan: dict | None = None) -> dict:
        rel = op["relpath"]
        dest = uoink / rel
        key = op["key"]
        if not _rel_is_allowed(rel):
            return {"key": key, "ok": False, "code": "path_collision", "counted": False, "relpath": rel}
        if _path_too_long(dest):
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False}
        try:
            self._io_mkdir(dest.parent, exist_ok=True)
        except OSError as exc:
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False,
                    "reason": type(exc).__name__}
        if not _contained(uoink, dest.parent) or _escaping_reparse(uoink, dest.parent):
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False}
        existing = dest.exists()
        current_hash = _sha256_file(dest) if existing else None
        rec = ownership.get(rel)
        owned = bool(op.get("owned"))
        if isinstance(rec, dict) and rec.get("key") == key:
            owned = True
        if isinstance(rec, dict) and rec.get("key") not in (None, key):
            return {"key": key, "ok": False, "code": "path_collision", "counted": False, "relpath": rel}
        if existing and not owned:
            return {
                "key": key, "ok": False, "code": "unmanaged_conflict",
                "unmanaged_conflict": True, "counted": False, "relpath": rel,
            }
        if existing and _hardlink_conflict(dest):
            return {"key": key, "ok": False, "code": "unmanaged_conflict", "counted": False, "relpath": rel}
        expected = op.get("expected_hash") or ""
        content = op.get("content")
        desired_hash = _sha256_bytes(bytes(content)) if isinstance(content, (bytes, bytearray)) else None
        if existing and desired_hash and current_hash == desired_hash and op["action"] in ("write", "tombstone"):
            ownership[rel] = {
                "key": key, "kind": op.get("kind"), "identity": op.get("identity"),
                "file_hash": current_hash, "generation": op.get("generation"),
                "tombstone": op["action"] == "tombstone",
            }
            return {"key": key, "ok": True, "action": op["action"], "counted": False,
                    "file_hash": current_hash, "generation": op.get("generation"), "relpath": rel,
                    "dependency_hash": op.get("dependency_hash") or ""}
        if existing and owned and expected and current_hash and current_hash != expected:
            code = "purge_blocked_user_edit" if op["action"] == "purge" else "user_edit_conflict"
            return {
                "key": key, "ok": False, "code": code,
                "user_edit_conflict": code == "user_edit_conflict",
                "purge_blocked_user_edit": code == "purge_blocked_user_edit",
                "counted": False, "relpath": rel,
            }

        if op["action"] == "purge":
            if existing:
                recheck_hash = _sha256_file(dest)
                if expected and recheck_hash and recheck_hash != expected:
                    return {
                        "key": key, "ok": False, "code": "purge_blocked_user_edit",
                        "purge_blocked_user_edit": True, "counted": False, "relpath": rel,
                    }
                try:
                    self._io_unlink(dest)
                except OSError as exc:
                    return {"key": key, "ok": False, "code": "destination_unavailable",
                            "counted": False, "reason": type(exc).__name__}
            ownership.pop(rel, None)
            self._cleanup_one_temp(dest, uoink, key=key)
            return {"key": key, "ok": True, "action": "purge", "counted": True, "relpath": rel,
                    "generation": op.get("generation")}

        if not isinstance(content, (bytes, bytearray)):
            return {"key": key, "ok": False, "code": "internal_error", "counted": False}

        initial_dest_hash = current_hash

        def recheck() -> bool:
            if plan is not None:
                cancelled = plan.get("cancelled")
                if isinstance(cancelled, threading.Event) and cancelled.is_set():
                    return False
                deadline = float(plan.get("deadline_mono") or 0)
                if deadline and float(self._clock()) > deadline:
                    return False
            if not getattr(self, "_lock_acquired", False):
                return False

            # Re-read ledger generation; refuse to publish an older generation.
            try:
                data = json.loads(self._ledger_path().read_text(encoding="utf-8"))
                entry = (data.get("entries") or {}).get(key) or {}
                desired = int(entry.get("desired_generation") or 0)
                pending = entry.get("pending_action") or "none"
                if desired > int(op.get("generation") or 0):
                    return False
                if op["action"] == "write" and pending == "purge":
                    return False
            except Exception:
                pass

            # Authoritative deletion / scope / dependency check
            kind = op.get("kind")
            ident = op.get("identity") or ""
            if kind == "item":
                item_snap, _ = self._item_snapshot(ident)
                if op.get("action") == "tombstone":
                    if item_snap is not None and item_snap.get("deleted_at") is None:
                        return False
                else:
                    if item_snap is None or item_snap.get("deleted_at") is not None:
                        return False
                    if not self._in_scope_id(ident):
                        return False
            elif kind == "brief":
                deps = op.get("dependencies") or []
                if not deps:
                    return False
                for d in deps:
                    item_snap, _ = self._item_snapshot(d)
                    if item_snap is None or item_snap.get("deleted_at") is not None:
                        return False
                    if not self._in_scope_id(d):
                        return False
                # Revalidate complete bound dependency state (evidence revisions & report bindings)
                store = self.brief_store
                date = op.get("date") or ""
                bhash = op.get("brief_hash") or ""
                if not date or not bhash:
                    ident = op.get("identity") or ""
                    if "/" in str(ident):
                        date, bhash = str(ident).split("/", 1)
                checked = False
                if store is not None and hasattr(store, "_load_artifact") and hasattr(store, "_check_dependencies"):
                    try:
                        if date and bhash:
                            with store.reader._operation() as fresh_op:
                                manifest, _doc, _cits, packet = store._load_artifact(date, bhash)
                                store._check_dependencies(fresh_op, manifest, packet=packet)
                                checked = True
                    except Exception:
                        return False
                if not checked:
                    bound_deps = op.get("bound_dependencies") or []
                    for bdep in bound_deps:
                        vid = bdep.get("item_id")
                        if not isinstance(vid, str):
                            continue
                        item_snap, clips = self._item_snapshot(vid)
                        if item_snap is None or item_snap.get("deleted_at") is not None:
                            return False
                        card = library_cards.build_card(item_snap, clips)
                        if card is None:
                            return False
                        if (card.get("source_revision") != bdep.get("source_revision") or
                                card.get("card_hash") != bdep.get("card_hash")):
                            return False
                    rep_bindings = op.get("report_bindings") or {}
                    proj = rep_bindings.get("projection_revision")
                    if proj is not None and hasattr(self.idx, "_conn"):
                        try:
                            row = self.idx._conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()
                            if row and int(row[0]) != proj:
                                return False
                        except Exception:
                            pass

            # Target bytes check immediately before replace
            now_exists = dest.exists()
            if now_exists:
                now_h = _sha256_file(dest)
                if initial_dest_hash is not None and now_h != initial_dest_hash:
                    return False
                if initial_dest_hash is None and now_h is not None:
                    return False
            elif initial_dest_hash is not None:
                return False

            return True

        self._active_plan = plan
        self._active_key = key
        try:
            digest = self._atomic_vault(dest, bytes(content), uoink, recheck=recheck)
        except _AbortedWrite:
            if dest.exists():
                now_h = _sha256_file(dest)
                desired = _sha256_bytes(bytes(content)) if isinstance(content, (bytes, bytearray)) else None
                if desired and now_h == desired:
                    # We replaced but will not acknowledge; intent recovers these bytes.
                    return {"key": key, "ok": False, "code": "stale", "counted": False, "relpath": rel}
                if initial_dest_hash and now_h != initial_dest_hash:
                    return {
                        "key": key, "ok": False, "code": "user_edit_conflict",
                        "user_edit_conflict": True, "counted": False, "relpath": rel,
                    }
            return {"key": key, "ok": False, "code": "stale", "counted": False, "relpath": rel}
        except OSError as exc:
            return {"key": key, "ok": False, "code": "destination_unavailable",
                    "counted": False, "reason": type(exc).__name__, "relpath": rel}
        finally:
            self._active_key = None
        if digest is None:
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False}
        on_disk = _sha256_file(dest)
        if on_disk != digest:
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False}
        ownership[rel] = {
            "key": key,
            "kind": op.get("kind"),
            "identity": op.get("identity"),
            "file_hash": digest,
            "generation": op.get("generation"),
            "tombstone": op["action"] == "tombstone",
        }
        return {
            "key": key, "ok": True, "action": op["action"], "counted": True,
            "file_hash": digest, "generation": op.get("generation"), "relpath": rel,
            "dependency_hash": op.get("dependency_hash") or "",
        }

    def _cleanup_one_temp(self, dest: Path, uoink: Path, key: str | None = None) -> None:
        if not key:
            return
        intent = self._load_intents().get(key)
        kept = self._cleanup_intent_temps(uoink, key, intent)
        if kept:
            stub = {"key": key, "action": "cleanup", "pending_temps": kept}
            if intent:
                for field in ("relpath", "content_hash", "generation", "identity", "kind"):
                    if field in intent:
                        stub[field] = intent[field]
            self._write_intent(key, stub)
        elif intent:
            intent = dict(intent)
            intent.pop("temp_rel", None)
            intent.pop("temp_hash", None)
            intent.pop("temp_file_id", None)
            intent.pop("temp_volume_id", None)
            intent["pending_temps"] = []
            self._write_intent(key, intent)

    def _write_cancelled(self, plan: dict | None) -> bool:
        if plan is not None:
            cancelled = plan.get("cancelled")
            if isinstance(cancelled, threading.Event) and cancelled.is_set():
                return True
            deadline = float(plan.get("deadline_mono") or 0)
            if deadline and float(self._clock()) > deadline:
                return True
        session = getattr(self, "_vault_io", None)
        if session is not None and not session.alive:
            return True
        return not getattr(self, "_lock_acquired", False)

    def _atomic_vault(self, dest: Path, data: bytes, uoink: Path, *, recheck: Callable[[], bool]) -> str:
        plan = getattr(self, "_active_plan", None)
        key = getattr(self, "_active_key", None)
        self._io_mkdir(dest.parent, exist_ok=True)
        tmp = dest.with_name(dest.name + "." + secrets.token_hex(12) + ".tmp")
        if not _contained(uoink, tmp) or _escaping_reparse(uoink, dest.parent):
            raise OSError("temp path escapes mirror root")
        if _path_too_long(tmp):
            raise OSError("temp path too long")
        digest = _sha256_bytes(data)
        rel = str(tmp.relative_to(uoink))
        if key:
            self._record_allocated_temp(key, rel, digest)
        try:
            write_res = self._io_write_file(tmp, data)
            file_id = None
            volume_id = None
            if isinstance(write_res, dict):
                file_id = _optional_int(write_res.get("file_id"))
                volume_id = _optional_int(write_res.get("volume_id"))
            if key:
                if not file_id:
                    raise OSError("temp allocation is missing file identity")
                self._record_allocated_temp(
                    key, rel, digest, file_id=file_id, volume_id=volume_id,
                )
            if not recheck():
                raise _AbortedWrite()
            self._io_replace(tmp, dest)
            tmp = None
            if key:
                self._clear_current_temp_rel(key)
            if self._write_cancelled(plan):
                # Do not roll back over whatever now occupies dest.
                raise _AbortedWrite("cancelled or lock released")
            return _sha256_bytes(data)
        finally:
            if tmp is not None:
                try:
                    self._io_unlink(tmp)
                except OSError:
                    pass

    def _apply_receipts(self, ledger: dict, result: dict) -> dict:
        if result.get("ok") is False and result.get("code") == "reconciliation":
            return _mirror_refusal(
                "invalid_request",
                "The mirror ownership manifest needs reconciliation.",
                details={"reason": "reconciliation"},
                reconciliation=True,
                synced=0,
            )
        if result.get("ok") is False and (result.get("code") == "destination_unavailable" or result.get("manifest_failed")):
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
                details={"reason": result.get("reason", "destination_unavailable")},
            )
        receipts = result.get("receipts") or []
        paused = bool(ledger.get("exports_paused"))
        synced = 0
        conflicts: list[dict] = []
        blocked = False
        for receipt in receipts:
            key = receipt.get("key")
            if not key:
                continue
            entry = (ledger.get("entries") or {}).get(key)
            if entry is None and receipt.get("ok"):
                continue
            if entry is None:
                continue
            code = receipt.get("code")
            if receipt.get("ok") and receipt.get("action") == "purge":
                entry["pending_action"] = "none"
                entry["status"] = "purged"
                entry["last_file_hash"] = ""
                entry["written_generation"] = int(receipt.get("generation") or entry.get("desired_generation") or 0)
                self._retain_or_clear_intent(key)
                if receipt.get("counted"):
                    synced += 1
            elif receipt.get("ok"):
                entry["pending_action"] = "none"
                entry["status"] = "synced"
                if receipt.get("file_hash"):
                    entry["last_file_hash"] = receipt["file_hash"]
                entry["written_generation"] = int(receipt.get("generation") or entry.get("desired_generation") or 0)
                if receipt.get("dependency_hash"):
                    entry["dependency_hash"] = receipt["dependency_hash"]
                self._retain_or_clear_intent(key)
                if receipt.get("counted"):
                    synced += 1
            elif code == "purge_blocked_user_edit":
                entry["status"] = "user_edit_conflict"
                ledger["exports_paused"] = True
                ledger["pause_reason"] = "purge_blocked_user_edit"
                paused = True
                blocked = True
                conflicts.append({"key": key, "code": code, "path": entry.get("relpath")})
            elif code in ("user_edit_conflict", "unmanaged_conflict", "path_collision"):
                entry["status"] = code
                conflicts.append({"key": key, "code": code, "path": entry.get("relpath")})
            elif code == "stale":
                entry["status"] = "stale"
        binding_failed = False
        if result.get("ok") and self.consent and self.consent.destination:
            try:
                self._write_dest_binding(
                    str(self.consent.destination), self.consent.marker or "", have_synced=True,
                )
            except OSError:
                binding_failed = True
                result = dict(result)
                result["ok"] = False
                result["code"] = "destination_unavailable"
                result["reason"] = "destination_binding"
        self._save_ledger(ledger)
        if result.get("ok") is False and result.get("code") == "reconciliation":
            return _mirror_refusal(
                "invalid_request",
                "The mirror ownership manifest needs reconciliation.",
                details={"reason": "reconciliation"},
                reconciliation=True,
                synced=0,
            )
        if result.get("code") == "destination_unavailable":
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
            )
        payload = _ok(
            synced=synced,
            conflicts=conflicts,
            exports_paused=paused,
            files=result.get("used") or 0,
        )
        if blocked:
            payload["ok"] = False
            payload["purge_blocked_user_edit"] = True
            payload["error"] = {
                "code": "purge_blocked_user_edit",
                "message": "A user-edited mirror file blocked hard purge.",
                "retryable": False,
                "details": {},
            }
        if binding_failed:
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
            )
        if any(c.get("code") == "user_edit_conflict" for c in conflicts):
            payload["user_edit_conflict"] = True
        if any(c.get("code") == "unmanaged_conflict" for c in conflicts):
            payload["unmanaged_conflict"] = True
        return payload

    def _scan_conflicts(self, dest: Path, ledger: dict) -> tuple[list, list, list]:
        unmanaged: list[dict] = []
        collisions: list[dict] = []
        user_edits: list[dict] = []
        uoink = dest / MIRROR_ROOT
        ownership = {}
        manifest_state = self._read_manifest_bytes(uoink)
        if isinstance(manifest_state, dict):
            ownership = manifest_state.get("ownership") or {}
        scope = self.consent.scope if self.consent else SCOPE_ALL
        allow = self.consent.allowlist if self.consent else ()
        for item in self._in_scope_items(scope, allow):
            rel = item_relpath(item["video_id"])
            path = uoink / rel
            try:
                exists = path.exists() and path.is_file()
            except OSError:
                continue
            if not exists:
                continue
            rec = ownership.get(rel)
            key = item_key(item["video_id"])
            if not isinstance(rec, dict):
                entry = (ledger.get("entries") or {}).get(key) or {}
                if entry.get("last_file_hash"):
                    digest = _sha256_file(path)
                    if digest and digest != entry.get("last_file_hash"):
                        user_edits.append({"path": rel, "identity": item["video_id"], "code": "user_edit_conflict"})
                    continue
                unmanaged.append({"path": rel, "identity": item["video_id"], "code": "unmanaged_conflict"})
            elif rec.get("key") not in (None, key):
                collisions.append({"path": rel, "identity": item["video_id"], "code": "path_collision"})
            else:
                entry = (ledger.get("entries") or {}).get(key) or {}
                expected = entry.get("last_file_hash") or rec.get("file_hash")
                digest = _sha256_file(path)
                if expected and digest and digest != expected:
                    user_edits.append({"path": rel, "identity": item["video_id"], "code": "user_edit_conflict"})
        return unmanaged, collisions, user_edits

    # ---- locking / worker ---------------------------------------------
    def _start_vault_io(self, dest: str) -> None:
        self._stop_vault_io()
        session = _VaultIoSession.start(dest)
        self._vault_io = session
        self._vault_io_startup_s = float(session.startup_s)

    def _kill_vault_io(self) -> None:
        session = self._vault_io
        self._vault_io = None
        if session is not None:
            session.terminate()

    def _stop_vault_io(self) -> None:
        session = self._vault_io
        self._vault_io = None
        if session is None:
            return
        if session.alive:
            session.shutdown()
        else:
            session.terminate()

    def _require_vault_io(self) -> _VaultIoSession:
        session = self._vault_io
        if session is None or not session.alive:
            raise OSError("vault io worker is not running")
        return session

    def _io_mkdir(self, path: Path, exist_ok: bool = True) -> None:
        self._require_vault_io().mkdir(str(path), exist_ok=exist_ok)

    def _io_write_file(self, path: Path, data: bytes) -> dict:
        return self._require_vault_io().write_file(str(path), data)

    def _io_replace(self, src: Path, dst: Path) -> None:
        self._require_vault_io().replace(str(src), str(dst))

    def _io_unlink(self, path: Path) -> dict:
        session = self._require_vault_io()
        expected = self._unlink_expected
        expected_file_id = None
        expected_hash = None
        expected_volume_id = None
        if expected and expected.get("path") == str(path):
            expected_file_id = _optional_int(expected.get("file_id"))
            expected_volume_id = _optional_int(expected.get("volume_id"))
            raw_hash = expected.get("hash")
            expected_hash = str(raw_hash) if raw_hash else None
        return session.unlink(
            str(path),
            expected_file_id=expected_file_id,
            expected_hash=expected_hash,
            expected_volume_id=expected_volume_id,
        )

    def _io_file_identity(self, path: Path) -> tuple[int | None, int | None]:
        return self._require_vault_io().file_identity(str(path))

    def _io_file_id(self, path: Path) -> int | None:
        fid, _vol = self._io_file_identity(path)
        return fid

    def _io_sha256(self, path: Path) -> str | None:
        session = self._vault_io
        if session is None or not session.alive:
            return _sha256_file(path)
        return session.sha256(str(path))

    def _run_cancellable(self, fn: Callable[[], Any], budget_s: float) -> tuple[Any, Any]:
        box: dict[str, Any] = {}
        done = threading.Event()

        def runner() -> None:
            try:
                box["value"] = fn()
            except _AbortedWrite as exc:
                box["error"] = exc
            except Exception as exc:
                box["error"] = exc
            finally:
                done.set()

        thread = threading.Thread(target=runner, name="uoink-mirror-io", daemon=True)
        thread.start()
        if not done.wait(timeout=max(0.001, float(budget_s))):
            self._kill_vault_io()
            done.wait(2.0)
            return None, "timeout"
        if "error" in box:
            return None, box["error"]
        return box.get("value"), None

    def _lock_path(self) -> Path:
        if self.consent and self.consent.destination:
            canonical = os.path.normcase(os.path.realpath(str(self.consent.destination)))
            dest_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            lock_dir = Path(tempfile.gettempdir()) / "uoink-mirror-locks"
            lock_dir.mkdir(parents=True, exist_ok=True)
            return lock_dir / f"{dest_key}.lock"
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        return self.ledger_dir / ".writer.lock"

    @contextlib.contextmanager
    def _exclusive(self, timeout: float = 10.0) -> Iterator[None]:
        path = self._lock_path()
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            fd = os.open(path, os.O_RDWR)
        acquired = False
        try:
            try:
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
            except OSError:
                pass
            until = time.monotonic() + max(0.05, float(timeout))
            if os.name == "nt":
                import msvcrt
                while not acquired:
                    try:
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= until:
                            raise _LockTimeout()
                        time.sleep(0.01)
            else:
                import fcntl
                while not acquired:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= until:
                            raise _LockTimeout()
                        time.sleep(0.01)
            self._lock_acquired = True
            try:
                yield
            finally:
                self._lock_acquired = False
        finally:
            if acquired:
                try:
                    if os.name == "nt":
                        import msvcrt
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            try:
                os.close(fd)
            except OSError:
                pass


class _LockTimeout(Exception):
    pass


class _AbortedWrite(Exception):
    pass


class _BudgetOp:
    """Minimal operation object for reusing LibraryReader._shelf_snapshot."""

    def __init__(self, reader, deadline_at: float):
        self.reader = reader
        self.deadline_at = deadline_at
        self.cache: dict[str, Any] = {}

    def check(self) -> None:
        if float(self.reader._clock()) > self.deadline_at:
            raise ResourceError("deadline_exceeded", details={"deadline_s": getattr(self.reader, "deadline_s", 2.0)})


# Silence unused-import lint for the optional briefs module and shared contract pin.
_ = (_library_briefs, _RESOURCES_CONTRACT, LIMITS)
