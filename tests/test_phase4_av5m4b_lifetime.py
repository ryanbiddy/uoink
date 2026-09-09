"""AV-5m4b focused tests: child lifetime, session ownership, dest-stable exclusion.

Does not edit frozen AW/AW-3/AW-4 cases. Those remain observations for Ryan
or repairs assigned to AV-5m4a.
"""
from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

import library_mirror as mirror
import library_resources as resources
from tests.library_work_astra.test_phase4_aw_acceptance import (
    env, export, item_file, mutate_clip,
)


def _other_mirror(env, data_root: Path) -> mirror.Mirror:
    data_root.mkdir(parents=True, exist_ok=True)
    return mirror.Mirror(
        env.idx, env.reader, env.store, data_root=data_root,
        consent=env.mirror.consent, enabled=True,
        clock=time.monotonic, wall_clock=time.time,
    )


def _win_fn(dll, name, restype, argtypes):
    return ctypes.WINFUNCTYPE(restype, *argtypes)((name, dll))


def _suspend_pid(pid: int) -> dict:
    """Suspend the real child without rewriting production kernel32 signatures.

    Original AV-5m4b assigned OpenProcess.argtypes on the interned WinDLL
    object. Combined-union runs share that object with production job APIs;
    a truncated or overwritten HANDLE is not a demonstrated stall. This
    helper uses production OpenProcess (pointer-sized) and a bound
    NtSuspendProcess callable that does not clobber kernel32.OpenProcess.
    """
    evidence = {"pid": pid, "suspended": False, "platform": os.name}
    if not isinstance(pid, int) or pid <= 0:
        return evidence
    if os.name != "nt":
        os.kill(pid, signal.SIGSTOP)
        evidence["suspended"] = True
        evidence["ntstatus"] = 0
        return evidence
    from ctypes import wintypes
    k32 = mirror._kernel32()
    ntdll = ctypes.WinDLL("ntdll")
    nt_suspend = _win_fn(ntdll, "NtSuspendProcess", ctypes.c_long, [wintypes.HANDLE])
    handle = k32.OpenProcess(0x0800 | 0x1000, False, int(pid))
    evidence["open_error"] = ctypes.get_last_error()
    if not handle:
        return evidence
    try:
        status = int(nt_suspend(handle))
        evidence["ntstatus"] = status
        evidence["suspended"] = status == 0
        return evidence
    finally:
        k32.CloseHandle(handle)


def _stdout_pending_bytes(proc) -> int | None:
    if proc is None or proc.stdout is None:
        return None
    if os.name != "nt":
        import select
        ready, _, _ = select.select([proc.stdout], [], [], 0)
        return 1 if ready else 0
    import msvcrt
    handle = msvcrt.get_osfhandle(proc.stdout.fileno())
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    peek = _win_fn(
        k32, "PeekNamedPipe", ctypes.c_int,
        [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
         ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p],
    )
    avail = ctypes.c_uint32(0)
    if not peek(handle, None, 0, None, ctypes.byref(avail), None):
        return None
    return int(avail.value)


def _writer_pid(session) -> int:
    writer = getattr(session, "writer_pid", None)
    if isinstance(writer, int) and writer > 0:
        return writer
    return int(session.pid)


def _owned_stall_pids(session) -> list[int]:
    if hasattr(session, "owned_pids"):
        pids = [int(pid) for pid in session.owned_pids() if isinstance(pid, int) and pid > 0]
    else:
        pids = [int(session.pid)] if session.pid else []
    writer = _writer_pid(session)
    if writer not in pids:
        pids.append(writer)
    verified = []
    for pid in pids:
        if hasattr(session, "owns_pid"):
            if session.owns_pid(pid) or pid == session.pid or pid == writer:
                verified.append(pid)
        else:
            verified.append(pid)
    return verified


def _prove_real_child_stall(session) -> dict:
    """Suspend the actual writer (or owned tree) and observe a pending RPC.

    Integrator Windows venv: Popen PID can be a launcher. The retained AW-8
    topology recorded session 72308 launching writer 60848. Suspending only
    the launcher is not a writer stall. Original failed stall observations
    remain in docs/library/proof/aw8-2026-09-08/.
    """
    assert session is not None
    assert session.physically_alive() if hasattr(session, "physically_alive") else session.alive
    writer = _writer_pid(session)
    assert session.owns_pid(writer) if hasattr(session, "owns_pid") else True
    owned = _owned_stall_pids(session)
    tree = []
    for pid in owned:
        item = _suspend_pid(pid)
        tree.append(item)
    writer_ev = next((item for item in tree if item.get("pid") == writer), None)
    evidence = dict(writer_ev or _suspend_pid(writer))
    evidence["session_pid"] = session.pid
    evidence["writer_pid"] = writer
    evidence["owned"] = tree
    evidence["topology"] = "launcher+writer" if writer != session.pid else "direct"
    assert evidence.get("suspended"), evidence
    ping = json.dumps({"cmd": "exists", "path": session.dest}).encode("utf-8") + b"\n"
    session.proc.stdin.write(ping)
    session.proc.stdin.flush()
    t0 = time.monotonic()
    until = t0 + 0.2
    pending = 0
    while time.monotonic() < until:
        pending = _stdout_pending_bytes(session.proc)
        if pending:
            break
        time.sleep(0.01)
    stall_s = time.monotonic() - t0
    writer_alive = mirror._pid_is_alive(writer, getattr(session, "writer_created_ms", None))
    physical = session.physically_alive() if hasattr(session, "physically_alive") else session.alive
    evidence.update({
        "stall_s": stall_s,
        "stdout_pending": pending,
        "child_alive": bool(physical and writer_alive),
        "stalled": bool(physical and writer_alive and pending == 0),
    })
    assert evidence["stalled"], evidence
    session._stall_evidence = evidence
    return evidence


def _freeze_session(session) -> dict:
    """Real-child stall. Does not replace session.call with a parent wait."""
    return _prove_real_child_stall(session)


def test_lease_and_lock_paths_ignore_temp_roots(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("d")
    dest = root / "v"
    dest.mkdir()
    t1 = root / "t1"
    t2 = root / "t2"
    t1.mkdir()
    t2.mkdir()
    monkeypatch.setenv("TEMP", str(t1))
    monkeypatch.setenv("TMP", str(t1))
    tempfile.tempdir = None
    lease1 = mirror._dest_lease_path(str(dest))
    lock1 = mirror._dest_lock_path(str(dest))
    mutex1 = mirror._dest_mutex_name(str(dest)) if os.name == "nt" else None
    monkeypatch.setenv("TEMP", str(t2))
    monkeypatch.setenv("TMP", str(t2))
    tempfile.tempdir = None
    lease2 = mirror._dest_lease_path(str(dest))
    lock2 = mirror._dest_lock_path(str(dest))
    mutex2 = mirror._dest_mutex_name(str(dest)) if os.name == "nt" else None
    assert lease1 == lease2
    assert lock1 == lock2
    dest_r = dest.resolve()
    assert lease1.parent.resolve() == dest_r
    assert lock1.parent.resolve() == dest_r
    # Exclusive live lock is a shared Windows admission gate (not a TEMP lock
    # file and not a dest-hash name). The dest-local path helper remains
    # dest-stable for POSIX flock fallback and for tests that inspect the
    # namespace; Windows resync does not open it.
    if mutex1 is not None:
        assert mutex1 == mutex2
        assert mutex1 == mirror._WRITER_ADMISSION_MUTEX
        assert str(t1) not in mutex1 and str(t2) not in mutex1
    assert t1.resolve() not in lease1.resolve().parents
    assert t2.resolve() not in lease1.resolve().parents


@pytest.mark.skipif(os.name != "nt", reason="Windows kill-on-close job assignment")
def test_job_assignment_failure_refuses_before_mutation(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("j")
    dest = root / "v"
    dest.mkdir()
    src = root / "src.bin"
    dst = root / "dst.bin"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    monkeypatch.setattr(mirror, "_win_assign_job", lambda job, proc: False)
    with pytest.raises(OSError):
        mirror._VaultIoSession.start(str(dest))
    assert dst.read_bytes() == b"old"
    assert not mirror._foreign_vault_worker_alive(str(dest))
    lease = mirror._read_dest_lease(str(dest))
    assert lease in (None, "corrupt", "unavailable") or lease == {}


def test_child_boundary_timeout_confirms_death_and_keeps_user_edit(env, monkeypatch):
    env.mirror._clock = time.monotonic
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    target = item_file(env)
    before = target.read_bytes()
    original_start = env.mirror._start_vault_io
    held = {}

    def start_and_freeze(dest):
        original_start(dest)
        session = env.mirror._vault_io
        held["session"] = session
        held["pid"] = session.pid
        held["stall"] = _freeze_session(session)

    monkeypatch.setattr(env.mirror, "_start_vault_io", start_and_freeze)
    t0 = time.monotonic()
    result = env.mirror.resync(budget_s=0.25)
    total_s = time.monotonic() - t0
    assert not result["ok"]
    session = held["session"]
    assert held["stall"]["stalled"]
    assert held["stall"].get("ntstatus", 0) == 0
    assert not session.alive
    assert not mirror._pid_is_alive(held["pid"], session.created_ms)
    startup_s = float(session.startup_s or 0.0)
    termination_s = float(session.termination_s or 0.0)
    assert startup_s >= 0 and termination_s >= 0
    assert startup_s <= 2.0
    assert total_s + 0.05 >= startup_s + 0.25
    personal = b"INDEPENDENT USER EDITOR AT CHILD BOUNDARY"
    target.write_bytes(personal)
    assert not mirror._foreign_vault_worker_alive(str(env.vault))
    assert target.read_bytes() == personal
    assert before != personal


def test_timed_out_parent_cannot_use_later_resync_session(env, monkeypatch):
    env.mirror._clock = time.monotonic
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    target = item_file(env)
    original_start = env.mirror._start_vault_io
    first = {}

    def start_and_freeze(dest):
        original_start(dest)
        session = env.mirror._vault_io
        if "session" not in first:
            first["session"] = session
            _freeze_session(session)

    monkeypatch.setattr(env.mirror, "_start_vault_io", start_and_freeze)
    result1 = env.mirror.resync(budget_s=0.25)
    assert not result1["ok"]
    sess1 = first["session"]
    assert not sess1.alive
    personal = b"PARENT LOSS USER BYTES"
    target.write_bytes(personal)
    monkeypatch.setattr(env.mirror, "_start_vault_io", original_start)
    result2 = env.mirror.resync(budget_s=2.0)
    assert sess1 is not env.mirror._vault_io
    with pytest.raises(OSError):
        sess1.replace(str(target), str(target))
    assert target.read_bytes() == personal


def test_second_process_with_different_temp_root_is_excluded(env, tmp_path_factory):
    export(env)
    session = mirror._VaultIoSession.start(str(env.vault))
    session.claim_lease()
    try:
        other_temp = tmp_path_factory.mktemp("ot")
        other_root = tmp_path_factory.mktemp("or")
        script = (
            "import json, sys, tempfile, time\n"
            "from pathlib import Path\n"
            "import library_briefs as briefs\n"
            "import library_mirror as mirror\n"
            "from library_resources import LibraryReader\n"
            "from tests.phase4_fixtures import make_disposable_index\n"
            "dest = Path(sys.argv[1])\n"
            "root = Path(sys.argv[2])\n"
            "print('tempdir', tempfile.gettempdir(), flush=True)\n"
            "print('lease', mirror._dest_lease_path(str(dest)), flush=True)\n"
            "idx = make_disposable_index(root)\n"
            "try:\n"
            "    reader = LibraryReader(idx, data_root=root / 'd', clock=time.monotonic, wall_clock=time.time)\n"
            "    store = briefs.BriefStore.for_reader(reader)\n"
            "    consent = mirror.MirrorConsent(str(dest), mirror.SCOPE_ALL, (), 1, 'aw-volume')\n"
            "    other = mirror.Mirror(idx, reader, store, data_root=root / 'd', consent=consent,\n"
            "                          enabled=True, clock=time.monotonic, wall_clock=time.time)\n"
            "    result = other.resync(budget_s=0.4)\n"
            "    print('RESULT', json.dumps({'ok': result.get('ok'),\n"
            "        'code': (result.get('error') or {}).get('code'),\n"
            "        'destination_unavailable': result.get('destination_unavailable')}), flush=True)\n"
            "finally:\n"
            "    idx.close()\n"
        )
        env_vars = os.environ.copy()
        env_vars["TEMP"] = str(other_temp)
        env_vars["TMP"] = str(other_temp)
        env_vars["TMPDIR"] = str(other_temp)
        env_vars["PYTHONDONTWRITEBYTECODE"] = "1"
        env_vars.pop("ANTHROPIC_API_KEY", None)
        worktree = str(Path(mirror.__file__).resolve().parent)
        import site
        path_parts = [worktree, site.getusersitepackages(), str(Path(sys.prefix) / "Lib" / "site-packages")]
        extra = env_vars.get("PYTHONPATH")
        if extra:
            path_parts.append(extra)
        env_vars["PYTHONPATH"] = os.pathsep.join(path_parts)
        proc = subprocess.run(
            [sys.executable, "-B", "-c", script, str(env.vault), str(other_root)],
            capture_output=True, text=True, timeout=25, env=env_vars, cwd=worktree,
        )
        assert "RESULT" in proc.stdout, proc.stdout + proc.stderr
        payload = json.loads(proc.stdout.strip().split("RESULT")[-1].strip())
        assert payload["ok"] is False
        assert payload.get("destination_unavailable") or payload.get("code") == "destination_unavailable"
        assert str(other_temp) in proc.stdout
        lease_line = next(line for line in proc.stdout.splitlines() if line.startswith("lease "))
        child_lease = Path(lease_line.split(" ", 1)[1])
        assert child_lease.name == ".uoink-mirror-writer.lease"
        assert other_temp.resolve() not in child_lease.resolve().parents
        assert child_lease.parent.resolve() == Path(env.vault).resolve()
    finally:
        session.terminate()
        assert not session.alive


def test_corrupt_lease_does_not_grant_destination(env):
    export(env)
    path = mirror._dest_lease_path(str(env.vault))
    path.write_text("{not-json", encoding="utf-8")
    other = _other_mirror(env, env.root / "o")
    other._clock = time.monotonic
    result = other.resync(budget_s=0.3)
    assert not result["ok"]
    assert result.get("destination_unavailable") or (result.get("error") or {}).get("code") == "destination_unavailable"
    assert item_file(env).is_file()


def test_inherited_deferred_read_transaction_does_not_roll_back_or_exclude(env):
    conn = env.idx._conn
    conn.execute("BEGIN DEFERRED")
    count = conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()[0]
    assert conn.in_transaction
    with pytest.raises(resources.ResourceError) as caught:
        with env.store._sqlite_writer_exclusion():
            raise AssertionError("deferred read must not claim writer exclusion")
    assert caught.value.code == "stale_brief"
    assert conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()[0] == count
    import sqlite3
    other = sqlite3.connect(str(env.idx._path), timeout=0.2)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.execute("UPDATE yoinks SET title=title WHERE 0")
        other.commit()
    finally:
        other.close()
    conn.rollback()
    assert not conn.in_transaction
