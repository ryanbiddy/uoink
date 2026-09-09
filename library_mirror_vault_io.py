"""Isolated vault I/O worker for library_mirror.

One interpreter per resync operation. The parent talks JSON-lines over stdin/
stdout and kills this process (Windows job object / POSIX process group) when
the caller's deadline expires. This process is the only one that mutates the
vault, so a terminated worker cannot publish or roll back destination bytes.

Destructive unlink binds a handle (Windows sharing exclusion) or an equivalent
POSIX rename-verify, then checks volume/file identity and content through that
binding before deleting that file. Path-only unlink after a distant stat/hash
is not used. If the platform cannot provide exclusion, the command refuses.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import sys


FILE_ATTRIBUTE_REPARSE_POINT = 0x400


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


def _sha256_fd(fd: int) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 64)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _stat_identity(st: os.stat_result) -> tuple[int, int]:
    return int(st.st_ino), int(st.st_dev)


def _identity_mismatch(st: os.stat_result, expected_file_id, expected_volume_id) -> bool:
    file_id, volume_id = _stat_identity(st)
    if expected_file_id is not None and file_id != int(expected_file_id):
        return True
    if expected_volume_id is not None and volume_id != int(expected_volume_id):
        return True
    return False


def _not_ours_stat(st: os.stat_result) -> bool:
    attrs = int(getattr(st, "st_file_attributes", 0) or 0)
    if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
        return True
    nlink = getattr(st, "st_nlink", 1)
    return isinstance(nlink, int) and nlink > 1


def _win_identity_unlink(path: str, expected_file_id, expected_volume_id, expected_hash) -> dict:
    import msvcrt
    from ctypes import wintypes

    generic_read = 0x80000000
    delete_access = 0x00010000
    file_share_read = 0x00000001
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_disposition_info = 4

    class FILE_DISPOSITION_INFO(ctypes.Structure):
        _fields_ = [("DeleteFile", wintypes.BOOLEAN)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    k32.SetFileInformationByHandle.restype = wintypes.BOOL

    handle = k32.CreateFileW(
        path,
        generic_read | delete_access,
        file_share_read,
        None,
        open_existing,
        file_flag_open_reparse_point,
        None,
    )
    invalid = int(ctypes.c_void_p(-1).value)
    if not handle or int(handle) == invalid:
        err = ctypes.get_last_error()
        if err in (2, 3):
            return {"ok": True, "gone": True}
        return {"ok": False, "error": "unlink_exclusion_unavailable", "winerror": err}

    fd = None
    try:
        fd = msvcrt.open_osfhandle(int(handle), os.O_RDONLY)
        handle = None
        st = os.fstat(fd)
        if _not_ours_stat(st) or _identity_mismatch(st, expected_file_id, expected_volume_id):
            return {"ok": True, "not_ours": True}
        if expected_hash is not None and _sha256_fd(fd) != expected_hash:
            return {"ok": True, "not_ours": True}
        info = FILE_DISPOSITION_INFO(True)
        ok = k32.SetFileInformationByHandle(
            msvcrt.get_osfhandle(fd),
            file_disposition_info,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            return {
                "ok": False,
                "error": "unlink_exclusion_unavailable",
                "winerror": ctypes.get_last_error(),
            }
        return {"ok": True}
    finally:
        if fd is not None:
            os.close(fd)
        elif handle:
            k32.CloseHandle(handle)


def _posix_identity_unlink(path: str, expected_file_id, expected_volume_id, expected_hash) -> dict:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return {"ok": True, "gone": True}
    unique = None
    try:
        st = os.fstat(fd)
        if _not_ours_stat(st) or _identity_mismatch(st, expected_file_id, expected_volume_id):
            return {"ok": True, "not_ours": True}
        if expected_hash is not None and _sha256_fd(fd) != expected_hash:
            return {"ok": True, "not_ours": True}
        parent = os.path.dirname(path) or "."
        unique = os.path.join(parent, ".uoink-unlink-" + os.urandom(12).hex())
        try:
            os.rename(path, unique)
        except OSError:
            return {"ok": False, "error": "unlink_exclusion_unavailable"}
        try:
            st2 = os.stat(unique)
        except OSError:
            return {"ok": False, "error": "unlink_exclusion_unavailable"}
        if int(st2.st_ino) != int(st.st_ino) or int(st2.st_dev) != int(st.st_dev):
            try:
                os.rename(unique, path)
            except OSError:
                pass
            unique = None
            return {"ok": True, "not_ours": True}
        os.unlink(unique)
        unique = None
        return {"ok": True}
    finally:
        os.close(fd)
        if unique is not None:
            try:
                os.rename(unique, path)
            except OSError:
                pass


def _identity_unlink(path: str, expected_file_id, expected_volume_id, expected_hash) -> dict:
    if os.name == "nt":
        return _win_identity_unlink(path, expected_file_id, expected_volume_id, expected_hash)
    return _posix_identity_unlink(path, expected_file_id, expected_volume_id, expected_hash)


def _handle(req: dict) -> dict:
    cmd = req.get("cmd")
    if cmd == "shutdown":
        return {"ok": True, "shutdown": True}
    if cmd == "mkdir":
        os.makedirs(req["path"], exist_ok=bool(req.get("exist_ok", True)))
        return {"ok": True}
    if cmd == "write":
        data = base64.b64decode(req["b64"])
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(req["path"], flags, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
            st = os.fstat(fd)
            file_id, volume_id = _stat_identity(st)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            fd = None
            try:
                os.unlink(req["path"])
            except OSError:
                pass
            raise
        else:
            os.close(fd)
            fd = None
            if file_id == 0:
                try:
                    os.unlink(req["path"])
                except OSError:
                    pass
                return {"ok": False, "error": "file_identity_unavailable"}
            return {
                "ok": True,
                "hash": hashlib.sha256(data).hexdigest(),
                "file_id": file_id,
                "volume_id": volume_id,
            }
        finally:
            if fd is not None:
                os.close(fd)
    if cmd == "replace":
        os.replace(req["src"], req["dst"])
        return {"ok": True}
    if cmd == "file_id":
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(req["path"], flags)
            try:
                st = os.fstat(fd)
            finally:
                os.close(fd)
            file_id, volume_id = _stat_identity(st)
            if file_id == 0:
                return {"ok": False, "error": "file_identity_unavailable"}
            return {"ok": True, "file_id": file_id, "volume_id": volume_id}
        except OSError as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    if cmd == "unlink":
        expected_file_id = req.get("expected_file_id")
        expected_volume_id = req.get("expected_volume_id")
        expected_hash = req.get("expected_hash")
        if expected_file_id is not None:
            try:
                expected_file_id = int(expected_file_id)
            except (TypeError, ValueError):
                return {"ok": True, "not_ours": True}
            if expected_file_id == 0:
                return {"ok": False, "error": "file_identity_unavailable"}
        if expected_volume_id is not None:
            try:
                expected_volume_id = int(expected_volume_id)
            except (TypeError, ValueError):
                return {"ok": True, "not_ours": True}
        if expected_hash is not None:
            expected_hash = str(expected_hash)
        return _identity_unlink(req["path"], expected_file_id, expected_volume_id, expected_hash)
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
