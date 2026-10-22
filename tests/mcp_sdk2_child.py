"""Fault injection for M4 subprocess tests. Never a product launch mode."""
import ctypes
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

assert os.environ.get("UOINK_ISOLATED_PROFILE")
assert os.environ.get("UOINK_ISOLATED_APP_DIR")
assert os.environ.get("UOINK_ISOLATED_PORT") not in (None, "5179")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import library_resources as lr
import uoink_mcp as u
from mcp import types

mode = sys.argv.pop(1)
root = Path(os.environ["UOINK_ISOLATED_PROFILE"])
original = u.mcp.get_request_handler("tools/call")
guard = lr.process_guard()
release_count = 0
original_release = guard.release


def counted_release():
    global release_count
    assert guard._active > 0, "Admission released more than once"
    release_count += 1
    original_release()


guard.release = counted_release


async def injected(ctx, params):
    if mode == "noise":
        print("M4 Python output", flush=True)
        os.write(1, b"M4 native CRT output\n")
        if os.name == "nt":
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetStdHandle.argtypes = [wintypes.DWORD]
            kernel.GetStdHandle.restype = wintypes.HANDLE
            kernel.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
            written = wintypes.DWORD()
            text = b"M4 Win32 output\n"
            assert kernel.WriteFile(kernel.GetStdHandle(-11), text, len(text), ctypes.byref(written), None)
        subprocess.run([sys.executable, "-B", "-c",
                        "import sys; print('M4 child output', flush=True); assert sys.stdin.read() == ''"],
                       check=True, timeout=5)
    elif mode == "sql":
        conn = sqlite3.connect(root / "sql-fixture.db")
        conn.execute("CREATE TABLE IF NOT EXISTS fixture(v)")
        conn.commit()
        locked = threading.Event()

        def blocker():
            other = sqlite3.connect(root / "sql-fixture.db")
            try:
                other.execute("BEGIN EXCLUSIVE")
                locked.set()
                deadline = time.monotonic() + 4
                while not (root / "release-sql").exists() and time.monotonic() < deadline:
                    time.sleep(0.005)
            finally:
                other.rollback()
                other.close()

        worker = threading.Thread(target=blocker)
        worker.start()
        assert locked.wait(2)
        reader = lr.LibraryReader(index=SimpleNamespace(_conn=conn, _lock=threading.RLock()), data_root=root)
        scope = lr.transport_scope(ctx.request_id)
        (root / "sql-wait").write_text("locked", encoding="utf-8")
        try:
            with lr._BoundedLock(reader, reader.index._lock, scope.deadline_at):
                reader._storage(lambda: conn.execute("SELECT * FROM fixture").fetchall())
        finally:
            conn.close()
            worker.join(5)
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps({"ok": True}))], is_error=False)


u.mcp.add_request_handler("tools/call", original.params_type, injected)
try:
    u.main()
finally:
    # Report after all transport cleanup, independently of the wire writer.
    print(json.dumps({"m4_active": lr.process_guard()._active,
                      "m4_scopes": len(lr._TRANSPORT_SCOPES)}), file=sys.stderr, flush=True)
    print(json.dumps({"m4_releases": release_count}), file=sys.stderr, flush=True)
