"""Isolated vault I/O worker for library_mirror.

One interpreter per resync operation. The parent talks JSON-lines over stdin/
stdout and kills this process (Windows job object / POSIX process group) when
the caller's deadline expires. This process is the only one that mutates the
vault, so a terminated worker cannot publish or roll back destination bytes.

Destructive unlink and publication bind a Windows handle with sharing
exclusion, then check volume/file identity and content through that handle
before deleting or renaming that file. Path-only unlink after a distant
stat/hash is not used. A failed write deletes the creating handle's file
before close; it does not unlink a pathname after the handle is gone.
POSIX has no equivalent exclusion primitive here; those commands refuse.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import sys


FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_BOUND = {
    "token": None,
    "op_id": None,
    "lock_generation": None,
    "cancelled": False,
}


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


def _kernel32():
    from ctypes import wintypes

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
    return k32


def _win_invalid_handle():
    return int(ctypes.c_void_p(-1).value)


def _win_disposition_delete(osf_handle) -> bool:
    from ctypes import wintypes

    class FILE_DISPOSITION_INFO(ctypes.Structure):
        _fields_ = [("DeleteFile", wintypes.BOOLEAN)]

    info = FILE_DISPOSITION_INFO(True)
    k32 = _kernel32()
    return bool(k32.SetFileInformationByHandle(
        osf_handle, 4, ctypes.byref(info), ctypes.sizeof(info),
    ))


def _win_rename_held(osf_handle, dest: str, replace_if_exists: bool) -> bool:
    from ctypes import wintypes

    name = dest
    nchars = len(name) + 1

    class FILE_RENAME_INFO(ctypes.Structure):
        _fields_ = [
            ("ReplaceIfExists", wintypes.DWORD),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", wintypes.WCHAR * nchars),
        ]

    info = FILE_RENAME_INFO()
    info.ReplaceIfExists = 1 if replace_if_exists else 0
    info.RootDirectory = None
    info.FileNameLength = len(name) * ctypes.sizeof(wintypes.WCHAR)
    info.FileName = name
    k32 = _kernel32()
    return bool(k32.SetFileInformationByHandle(
        osf_handle, 3, ctypes.byref(info), ctypes.sizeof(info),
    ))


def _win_create_file(path: str, access: int, share: int, disposition: int, flags: int):
    k32 = _kernel32()
    handle = k32.CreateFileW(path, access, share, None, disposition, flags, None)
    if not handle or int(handle) == _win_invalid_handle():
        return None, ctypes.get_last_error()
    return handle, 0


def _win_identity_unlink(path: str, expected_file_id, expected_volume_id, expected_hash) -> dict:
    import msvcrt

    generic_read = 0x80000000
    delete_access = 0x00010000
    file_share_read = 0x00000001
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000

    handle, err = _win_create_file(
        path,
        generic_read | delete_access,
        file_share_read,
        open_existing,
        file_flag_open_reparse_point,
    )
    if handle is None:
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
        if not _win_disposition_delete(msvcrt.get_osfhandle(fd)):
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
            _kernel32().CloseHandle(handle)


def _identity_unlink(path: str, expected_file_id, expected_volume_id, expected_hash) -> dict:
    if os.name == "nt":
        return _win_identity_unlink(path, expected_file_id, expected_volume_id, expected_hash)
    return {"ok": False, "error": "unlink_exclusion_unavailable"}


def _win_write_new(path: str, data: bytes) -> dict:
    import msvcrt

    generic_read = 0x80000000
    generic_write = 0x40000000
    delete_access = 0x00010000
    file_share_read = 0x00000001
    create_new = 1
    file_attribute_normal = 0x80
    file_flag_open_reparse_point = 0x00200000

    handle, err = _win_create_file(
        path,
        generic_read | generic_write | delete_access,
        file_share_read,
        create_new,
        file_attribute_normal | file_flag_open_reparse_point,
    )
    if handle is None:
        raise OSError(err, "CreateFileW write failed", path, err)

    fd = None
    try:
        fd = msvcrt.open_osfhandle(int(handle), os.O_RDWR)
        handle = None
        try:
            os.write(fd, data)
            os.fsync(fd)
            st = os.fstat(fd)
            file_id, volume_id = _stat_identity(st)
            if file_id == 0:
                _win_disposition_delete(msvcrt.get_osfhandle(fd))
                return {"ok": False, "error": "file_identity_unavailable"}
            return {
                "ok": True,
                "hash": hashlib.sha256(data).hexdigest(),
                "file_id": file_id,
                "volume_id": volume_id,
            }
        except Exception:
            try:
                _win_disposition_delete(msvcrt.get_osfhandle(fd))
            except OSError:
                pass
            raise
    finally:
        if fd is not None:
            os.close(fd)
        elif handle:
            _kernel32().CloseHandle(handle)


def _posix_write_new(path: str, data: bytes) -> dict:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
        st = os.fstat(fd)
        file_id, volume_id = _stat_identity(st)
        if file_id == 0:
            return {"ok": False, "error": "file_identity_unavailable"}
        return {
            "ok": True,
            "hash": hashlib.sha256(data).hexdigest(),
            "file_id": file_id,
            "volume_id": volume_id,
        }
    finally:
        os.close(fd)


def _write_new(path: str, data: bytes) -> dict:
    if os.name == "nt":
        return _win_write_new(path, data)
    return _posix_write_new(path, data)


def _win_identity_replace(src: str, dst: str, expected_file_id, expected_volume_id, expected_hash) -> dict:
    import msvcrt

    if expected_file_id is None:
        return {"ok": False, "error": "replace_exclusion_unavailable"}
    generic_read = 0x80000000
    delete_access = 0x00010000
    file_share_read = 0x00000001
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000

    handle, err = _win_create_file(
        src,
        generic_read | delete_access,
        file_share_read,
        open_existing,
        file_flag_open_reparse_point,
    )
    if handle is None:
        return {"ok": False, "error": "replace_exclusion_unavailable", "winerror": err}

    fd = None
    try:
        fd = msvcrt.open_osfhandle(int(handle), os.O_RDONLY)
        handle = None
        st = os.fstat(fd)
        if _not_ours_stat(st) or _identity_mismatch(st, expected_file_id, expected_volume_id):
            return {"ok": True, "not_ours": True}
        if expected_hash is not None and _sha256_fd(fd) != expected_hash:
            return {"ok": True, "not_ours": True}
        if not _win_rename_held(msvcrt.get_osfhandle(fd), dst, True):
            return {
                "ok": False,
                "error": "replace_exclusion_unavailable",
                "winerror": ctypes.get_last_error(),
            }
        return {"ok": True}
    finally:
        if fd is not None:
            os.close(fd)
        elif handle:
            _kernel32().CloseHandle(handle)


def _identity_replace(src: str, dst: str, expected_file_id, expected_volume_id, expected_hash) -> dict:
    if expected_file_id is None:
        # Parent publication always binds creating identity. Unbound replace
        # remains the worker's path-replace for startup/capability checks.
        os.replace(src, dst)
        return {"ok": True}
    if os.name == "nt":
        return _win_identity_replace(src, dst, expected_file_id, expected_volume_id, expected_hash)
    return {"ok": False, "error": "replace_exclusion_unavailable"}


def _bound_allows(req: dict) -> bool:
    if _BOUND.get("cancelled"):
        return False
    token = req.get("token")
    bound_token = _BOUND.get("token")
    if bound_token is not None and token is not None and token != bound_token:
        return False
    op_id = req.get("op_id")
    bound_op = _BOUND.get("op_id")
    if bound_op is not None and op_id is not None:
        try:
            if int(op_id) != int(bound_op):
                return False
        except (TypeError, ValueError):
            return False
    lock_generation = req.get("lock_generation")
    bound_gen = _BOUND.get("lock_generation")
    if bound_gen is not None and lock_generation is not None:
        try:
            if int(lock_generation) != int(bound_gen):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _atomic_put_bytes(path: str, data: bytes) -> dict:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = path + "." + os.urandom(8).hex() + ".tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(tmp, flags, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return {"ok": True}


def _handle(req: dict) -> dict:
    cmd = req.get("cmd")
    if cmd == "shutdown":
        return {"ok": True, "shutdown": True}
    if cmd == "whoami":
        return {"ok": True, "pid": os.getpid()}
    if cmd == "bind":
        if req.get("cancelled"):
            _BOUND["cancelled"] = True
            return {"ok": True, "pid": os.getpid(), "cancelled": True}
        incoming = req.get("token")
        if _BOUND.get("token") not in (None, incoming):
            return {"ok": False, "error": "operation is no longer live"}
        _BOUND["token"] = incoming
        _BOUND["op_id"] = req.get("op_id")
        _BOUND["lock_generation"] = req.get("lock_generation")
        _BOUND["cancelled"] = False
        return {"ok": True, "pid": os.getpid()}
    if cmd == "local_put":
        if not _bound_allows(req):
            return {"ok": False, "error": "operation is no longer live"}
        data = base64.b64decode(req["b64"])
        return _atomic_put_bytes(req["path"], data)
    if cmd == "local_unlink":
        if not _bound_allows(req):
            return {"ok": False, "error": "operation is no longer live"}
        path = req["path"]
        try:
            os.unlink(path)
        except FileNotFoundError:
            return {"ok": True, "gone": True}
        return {"ok": True}
    if cmd == "mkdir":
        os.makedirs(req["path"], exist_ok=bool(req.get("exist_ok", True)))
        return {"ok": True}
    if cmd == "write":
        data = base64.b64decode(req["b64"])
        return _write_new(req["path"], data)
    if cmd == "replace":
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
        return _identity_replace(
            req["src"], req["dst"], expected_file_id, expected_volume_id, expected_hash,
        )
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
    if cmd == "read":
        try:
            with open(req["path"], "rb") as stream:
                data = stream.read()
        except FileNotFoundError:
            return {"ok": True, "gone": True}
        return {"ok": True, "b64": base64.b64encode(data).decode("ascii")}
    if cmd == "lease_put":
        if not _bound_allows(req):
            return {"ok": False, "error": "operation is no longer live"}
        data = base64.b64decode(req["b64"])
        return _atomic_put_bytes(req["path"], data)
    if cmd == "lease_clear":
        path = req["path"]
        token = req.get("token")
        pid = req.get("pid")
        try:
            with open(path, "rb") as stream:
                raw = stream.read()
        except FileNotFoundError:
            return {"ok": True, "gone": True}
        except OSError as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeError, TypeError):
            return {"ok": False, "error": "lease_unavailable"}
        if not isinstance(data, dict):
            return {"ok": False, "error": "lease_unavailable"}
        if token is not None and data.get("token") not in (None, token):
            return {"ok": True, "not_ours": True}
        if pid is not None and data.get("pid") not in (None, pid):
            return {"ok": True, "not_ours": True}
        try:
            os.unlink(path)
        except FileNotFoundError:
            return {"ok": True, "gone": True}
        return {"ok": True}
    return {"ok": False, "error": "unknown_cmd"}


def main() -> int:
    sys.stdout.buffer.write((json.dumps({
        "ok": True, "ready": True, "pid": os.getpid(),
    }) + "\n").encode("utf-8"))
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
