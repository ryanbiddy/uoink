"""AV-5m4b4 focused tests: actual mutation, unconfirmed death, writer topology.

Does not edit frozen AW/AW-2..AW-7 cases. Original AW-8 parent-hook
failures remain failed observations of B3's parent boundaries.
"""
from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

import pytest

import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env
from tests.test_phase4_av5m4b_lifetime import _prove_real_child_stall, _writer_pid


def test_unconfirmed_child_death_is_not_forgotten(env, monkeypatch):
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(poll=lambda: None, pid=4_242_424)
    session.dest = str(env.vault)
    env.mirror._vault_io = session

    def unable_to_confirm():
        session._dead = True
        return False

    monkeypatch.setattr(session, "terminate", unable_to_confirm)
    env.mirror._kill_vault_io(session)
    assert session.proc.poll() is None
    assert session.physically_alive()
    assert env.mirror._vault_io is session, "Mirror forgot a child whose death was not confirmed"


def test_late_parent_refuses_dead_session_and_does_not_adopt_later(env):
    original = mirror._VaultIoSession.start(str(env.vault))
    later = None
    try:
        env.mirror._lock_acquired = True
        env.mirror._lock_generation = 4
        env.mirror._op_seq = 10
        plan = {"op_id": 10, "lock_generation": 4, "io": original}
        original.bind_operation(plan)
        path = env.mirror._intent_path("item:a")
        # Two live writers cannot share the admission gate. Terminate the
        # original process first; keep the stale original plan and refuse
        # adoption of the later session.
        assert original.terminate()
        original._dead = True
        later = mirror._VaultIoSession.start(str(env.vault))
        env.mirror._vault_io = later
        mirror._IO_CTX.plan = plan
        mirror._IO_CTX.session = original
        with pytest.raises(OSError, match="no longer live"):
            env.mirror._atomic_local(path, b"stale operation A")
        assert not path.is_file()
        with pytest.raises(OSError):
            original.local_put(str(path), b"stale operation A", op_id=10, lock_generation=4)
        assert env.mirror._vault_io is later
    finally:
        original.terminate()
        if later is not None:
            later.terminate()
        mirror._IO_CTX.plan = None
        mirror._IO_CTX.session = None
        env.mirror._vault_io = None


def test_inflight_isolated_intent_put_cannot_finish_after_writer_death(env):
    session = mirror._VaultIoSession.start(str(env.vault))
    try:
        env.mirror._lock_acquired = True
        env.mirror._lock_generation = 4
        env.mirror._op_seq = 10
        plan = {"op_id": 10, "lock_generation": 4, "io": session}
        mirror._IO_CTX.plan = plan
        mirror._IO_CTX.session = session
        session.bind_operation(plan)
        path = env.mirror._intent_path("item:a")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"current operation B")
        stall = _prove_real_child_stall(session)
        assert stall["stalled"]
        assert stall.get("stdout_pending") in (0, None)
        errors = []
        done = threading.Event()

        def late():
            try:
                session.local_put(str(path), b"stale operation A", op_id=10, lock_generation=4)
            except OSError as exc:
                errors.append(exc)
            finally:
                done.set()

        thread = threading.Thread(target=late, daemon=True)
        thread.start()
        assert thread.is_alive() or done.is_set()
        time.sleep(0.05)
        assert path.read_bytes() == b"current operation B"
        confirmed = session.terminate()
        assert done.wait(5)
        thread.join(2)
        assert path.read_bytes() == b"current operation B"
        assert not session.physically_alive()
        assert confirmed or not mirror._pid_is_alive(_writer_pid(session), session.writer_created_ms)
        assert errors or not session.alive
    finally:
        session.terminate()
        mirror._IO_CTX.plan = None
        mirror._IO_CTX.session = None


def test_ready_identifies_actual_writer_process(tmp_path_factory):
    dest = tmp_path_factory.mktemp("w")
    session = mirror._VaultIoSession.start(str(dest))
    try:
        who = session.call({"cmd": "whoami"})
        assert who.get("ok") and int(who["pid"]) == int(session.writer_pid)
        assert session.owns_pid(session.writer_pid)
        assert session.writer_pid in session.owned_pids()
        assert session.physically_alive()
        if session.writer_pid != session.pid:
            assert session.owns_pid(session.writer_pid)
            assert session.writer_created_ms is not None
    finally:
        assert session.terminate()
        assert not session.physically_alive()


def test_dest_mutex_does_not_block_on_parent_realpath(tmp_path_factory, monkeypatch):
    dest = tmp_path_factory.mktemp("v")

    def boom(*_a, **_k):
        raise AssertionError("parent realpath is dest filesystem I/O")

    monkeypatch.setattr(os.path, "realpath", boom)
    key = mirror._admission_gate_key(str(dest))
    assert key
    name = mirror._dest_mutex_name(str(dest))
    assert name == mirror._WRITER_ADMISSION_MUTEX
    assert name == key
    if os.name == "nt":
        handle, mutex_key = mirror._win_acquire_dest_mutex(str(dest), 0.5)
        try:
            assert mutex_key == key
        finally:
            mirror._win_release_dest_mutex(handle, mutex_key)


def test_live_worker_without_lease_is_not_forgotten(env):
    session = mirror._VaultIoSession.start(str(env.vault))
    env.mirror._vault_io = session
    try:
        assert not session._lease_written
        assert session.physically_alive()
        with pytest.raises(OSError, match="still live"):
            env.mirror._start_vault_io(str(env.vault))
        assert env.mirror._vault_io is session
    finally:
        session.terminate()
        env.mirror._forget_session(session)
