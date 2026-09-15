"""AV-5m4b3 focused tests: isolated lease I/O, intent mutation, SQLite owner.

Does not edit frozen AW-5 / AW-6 / AW-7 cases. Those remain observations
for Ryan or AV-5m4a3 where assigned.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import library_mirror as mirror
import library_resources as resources
from tests.library_work_astra.test_phase4_aw_acceptance import (
    env, export, item_file, mutate_clip,
)
from tests.test_phase4_av5m4b_lifetime import _freeze_session


def test_unproven_inherited_transaction_refuses_without_rollback(env):
    conn = env.idx._conn
    conn.execute("BEGIN IMMEDIATE")
    try:
        assert conn.in_transaction
        assert getattr(env.idx, "_write_txn_owner", None) is None
        with pytest.raises(resources.ResourceError) as caught:
            with env.store._sqlite_writer_exclusion():
                raise AssertionError("unproven inherited write must not certify exclusion")
        assert caught.value.code == "stale_brief"
        assert conn.in_transaction
        row = conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()
        assert row[0] >= 0
    finally:
        conn.rollback()


def test_index_write_transaction_owner_is_bound_to_connection_and_thread(env):
    conn = env.idx._conn
    with env.idx.write_transaction() as txn:
        owner = env.idx._write_txn_owner
        assert owner == (id(conn), threading.get_ident())
        txn.execute("CREATE TABLE IF NOT EXISTS av5m4b3_sentinel (id INTEGER)")
        txn.execute("INSERT INTO av5m4b3_sentinel (id) VALUES (9)")
        with env.store._sqlite_writer_exclusion():
            assert conn.in_transaction
            assert txn.execute("SELECT id FROM av5m4b3_sentinel").fetchone()[0] == 9
        assert env.idx._write_txn_owner == owner
    assert env.idx._write_txn_owner is None
    assert conn.execute("SELECT id FROM av5m4b3_sentinel").fetchone()[0] == 9


def test_late_atomic_local_cannot_finish_after_later_resync_owns_intent(env, monkeypatch):
    session = mirror._VaultIoSession.start(str(env.vault))
    try:
        _late_atomic_local_body(env, monkeypatch, session)
    finally:
        session.terminate()
        mirror._IO_CTX.plan = None
        mirror._IO_CTX.session = None


def _late_atomic_local_body(env, monkeypatch, session):
    env.mirror._lock_acquired = True
    env.mirror._lock_generation = 4
    env.mirror._op_seq = 10
    plan = {"op_id": 10, "lock_generation": 4, "io": session}
    mirror._IO_CTX.plan = plan
    mirror._IO_CTX.session = session
    session.bind_operation(plan)
    env.mirror._write_intent("item:a", {"key": "item:a", "generation": 1, "mark": "first"})
    original = env.mirror._atomic_local
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    raised = []

    def paused(path, data):
        if Path(path).parent.name == "intents":
            entered.set()
            assert release.wait(8)
            try:
                return original(path, data)
            except OSError as exc:
                raised.append(exc)
                raise
            finally:
                finished.set()
        return original(path, data)

    monkeypatch.setattr(env.mirror, "_atomic_local", paused)

    def late_write():
        mirror._IO_CTX.plan = {"op_id": 10, "lock_generation": 4}
        try:
            env.mirror._write_intent("item:a", {"key": "item:a", "generation": 2, "mark": "late"})
        except OSError:
            pass
        finally:
            if not finished.is_set():
                finished.set()

    thread = threading.Thread(target=late_write)
    thread.start()
    try:
        assert entered.wait(3)
        env.mirror._op_seq = 11
        env.mirror._lock_generation = 5
        mirror._IO_CTX.plan = {"op_id": 10, "lock_generation": 4}
    finally:
        release.set()
        thread.join(5)
        assert finished.wait(2)
    loaded = env.mirror._load_intents()
    assert loaded["item:a"]["mark"] == "first"
    assert loaded["item:a"]["generation"] == 1
    assert raised


def test_late_intent_unlink_cannot_finish_after_later_resync_owns_intent(env, monkeypatch):
    session = mirror._VaultIoSession.start(str(env.vault))
    try:
        _late_intent_unlink_body(env, monkeypatch, session)
    finally:
        session.terminate()
        mirror._IO_CTX.plan = None
        mirror._IO_CTX.session = None


def _late_intent_unlink_body(env, monkeypatch, session):
    env.mirror._lock_acquired = True
    env.mirror._lock_generation = 4
    env.mirror._op_seq = 10
    plan = {"op_id": 10, "lock_generation": 4, "io": session}
    mirror._IO_CTX.plan = plan
    mirror._IO_CTX.session = session
    session.bind_operation(plan)
    env.mirror._write_intent("item:a", {"key": "item:a", "generation": 1, "mark": "keep"})
    path = env.mirror._intent_path("item:a")
    original_unlink = env.mirror._unlink_intent_file
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    raised = []

    def paused(intent_path):
        entered.set()
        assert release.wait(8)
        try:
            return original_unlink(intent_path)
        except OSError as exc:
            raised.append(exc)
            raise
        finally:
            finished.set()

    monkeypatch.setattr(env.mirror, "_unlink_intent_file", paused)

    def late_clear():
        mirror._IO_CTX.plan = {"op_id": 10, "lock_generation": 4}
        try:
            env.mirror._clear_intent("item:a")
        except OSError:
            pass

    thread = threading.Thread(target=late_clear)
    thread.start()
    try:
        assert entered.wait(3), "intent unlink boundary was not entered"
        env.mirror._op_seq = 11
        env.mirror._lock_generation = 5
        mirror._IO_CTX.plan = {"op_id": 10, "lock_generation": 4}
    finally:
        release.set()
        thread.join(5)
        assert finished.wait(2)
    loaded = env.mirror._load_intents()
    assert loaded["item:a"]["mark"] == "keep"
    assert path.is_file()
    assert raised


def test_dead_bound_session_refuses_lease_write_before_destination(env):
    export(env)
    session = mirror._VaultIoSession.start(str(env.vault))
    lease_path = mirror._dest_lease_path(str(env.vault))
    mirror._IO_CTX.session = session
    mirror._IO_CTX.token = session.token
    session._dead = True
    before = lease_path.read_bytes() if lease_path.is_file() else None
    with pytest.raises(OSError):
        mirror._write_dest_lease(str(env.vault), {
            "pid": session.pid, "token": session.token, "destination": str(env.vault),
        })
    after = lease_path.read_bytes() if lease_path.is_file() else None
    assert after == before
    session.terminate()
    mirror._IO_CTX.session = None
    mirror._IO_CTX.token = None


def test_real_child_stall_timeout_keeps_independent_user_edit(env, monkeypatch):
    env.mirror._clock = time.monotonic
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    target = item_file(env)
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
    result = env.mirror.resync(budget_s=0.15)
    total_s = time.monotonic() - t0
    assert not result["ok"]
    assert held["stall"]["stalled"]
    assert held["stall"].get("stdout_pending") in (0, None)
    session = held["session"]
    assert not session.alive
    assert not mirror._pid_is_alive(held["pid"], session.created_ms)
    assert total_s < 5.0
    personal = b"B3 REAL CHILD STALL USER EDITOR"
    target.write_bytes(personal)
    assert target.read_bytes() == personal
    assert not mirror._foreign_vault_worker_alive(str(env.vault))


def test_parent_stub_timeout_is_a_separate_blocking_boundary(env, monkeypatch):
    """Parent-stub of session.call is not the child-stall proof; it is extra coverage."""
    env.mirror._clock = time.monotonic
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    original_start = env.mirror._start_vault_io
    held = {}

    def start_and_stub(dest):
        original_start(dest)
        session = env.mirror._vault_io
        held["session"] = session

        def hung(_req):
            until = time.monotonic() + 30
            while session.alive and time.monotonic() < until:
                time.sleep(0.02)
            raise OSError("vault io worker is not running")

        session.call = hung

    monkeypatch.setattr(env.mirror, "_start_vault_io", start_and_stub)
    result = env.mirror.resync(budget_s=0.1)
    assert not result["ok"]
    assert held["session"] and not held["session"].alive
    personal = b"PARENT STUB USER EDITOR"
    item_file(env).write_bytes(personal)
    assert item_file(env).read_bytes() == personal
