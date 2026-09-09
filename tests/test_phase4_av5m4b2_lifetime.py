"""AV-5m4b2 focused tests: AW-5 exclusion, cancellable dest lease, late intent.

Does not edit frozen AW/AW-3/AW-4/AW-5 cases.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

import pytest

import library_mirror as mirror
import library_resources as resources
from tests.library_work_astra.test_phase4_aw_acceptance import (
    env, export, item_file, mutate_clip,
)
from tests.test_phase4_av5m4b_lifetime import _freeze_session, _other_mirror


def test_deferred_read_with_foreign_writer_refuses_without_rollback(env):
    conn = env.idx._conn
    conn.execute("PRAGMA journal_mode=WAL")
    other = sqlite3.connect(str(env.idx._path), timeout=0)
    try:
        conn.execute("BEGIN DEFERRED")
        count = conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()[0]
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(resources.ResourceError) as caught:
            with env.store._sqlite_writer_exclusion():
                raise AssertionError("foreign reserved lock must not certify our deferred read")
        assert caught.value.code == "stale_brief"
        assert conn.in_transaction
        assert other.in_transaction
        assert conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()[0] == count
    finally:
        other.rollback()
        other.close()
        conn.rollback()


def test_write_transaction_is_reused_for_exclusion(env):
    conn = env.idx._conn
    with env.idx.write_transaction() as txn:
        txn.execute("CREATE TABLE IF NOT EXISTS av5m4b2_sentinel (id INTEGER)")
        txn.execute("INSERT INTO av5m4b2_sentinel (id) VALUES (3)")
        with env.store._sqlite_writer_exclusion():
            assert conn.in_transaction
            assert txn.execute("SELECT id FROM av5m4b2_sentinel").fetchone()[0] == 3
        assert conn.in_transaction
    row = conn.execute("SELECT id FROM av5m4b2_sentinel").fetchone()
    assert row[0] == 3


def test_stalled_dest_lease_write_is_inside_cancellation(env, monkeypatch):
    export(env)
    env.mirror._clock = time.monotonic
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    original_write = mirror._write_dest_lease
    results = []

    def stalled(*args, **kwargs):
        entered.set()
        release.wait(12)
        return original_write(*args, **kwargs)

    def resync():
        try:
            results.append(env.mirror.resync(budget_s=0.1))
        finally:
            done.set()

    monkeypatch.setattr(mirror, "_write_dest_lease", stalled)
    thread = threading.Thread(target=resync, daemon=True)
    thread.start()
    try:
        assert entered.wait(3), "The destination lease write was not reached"
        assert done.wait(5), "Destination lease I/O trapped resync outside cancellation"
        assert results and not results[0]["ok"]
        details = (results[0].get("error") or {}).get("details") or {}
        assert "startup_s" in details or results[0].get("destination_unavailable")
    finally:
        release.set()
        thread.join(8)
        assert not thread.is_alive()


def test_late_intent_write_cannot_replace_newer_generation(env):
    session = mirror._VaultIoSession.start(str(env.vault))
    env.mirror._lock_acquired = True
    env.mirror._lock_generation = 4
    env.mirror._op_seq = 10
    plan = {"op_id": 10, "lock_generation": 4, "io": session}
    mirror._IO_CTX.plan = plan
    mirror._IO_CTX.session = session
    session.bind_operation(plan)
    try:
        env.mirror._write_intent("item:a", {"key": "item:a", "generation": 1, "mark": "first"})
        loaded = env.mirror._load_intents()
        assert loaded["item:a"]["mark"] == "first"
        env.mirror._op_seq = 11
        env.mirror._lock_generation = 5
        env.mirror._write_intent("item:a", {"key": "item:a", "generation": 2, "mark": "late"})
        env.mirror._clear_intent("item:a")
        loaded = env.mirror._load_intents()
        assert loaded["item:a"]["mark"] == "first"
        assert loaded["item:a"]["generation"] == 1
    finally:
        session.terminate()
        mirror._IO_CTX.plan = None
        mirror._IO_CTX.session = None
        mirror._IO_CTX.token = None


def test_unknown_lease_liveness_refuses_destination(env, monkeypatch):
    export(env)
    path = mirror._dest_lease_path(str(env.vault))
    path.write_text(json.dumps({
        "pid": 2_000_000_000, "created_ms": 1, "token": "foreign-unknown",
    }), encoding="utf-8")
    monkeypatch.setattr(mirror, "_process_liveness", lambda *a, **k: "unknown")
    other = _other_mirror(env, env.root / "o2")
    other._clock = time.monotonic
    result = other.resync(budget_s=0.3)
    assert not result["ok"]
    assert result.get("destination_unavailable") or (result.get("error") or {}).get("code") == "destination_unavailable"
    assert item_file(env).is_file()


def test_lease_write_failure_after_startup_does_not_leak_child(env, monkeypatch):
    env.mirror._clock = time.monotonic
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    original_start = env.mirror._start_vault_io
    held = {}

    def start_and_hold(dest):
        original_start(dest)
        session = env.mirror._vault_io
        held["session"] = session
        held["pid"] = session.pid
        held["created"] = session.created_ms

    monkeypatch.setattr(env.mirror, "_start_vault_io", start_and_hold)
    monkeypatch.setattr(mirror, "_write_dest_lease", lambda *a, **k: (_ for _ in ()).throw(OSError("lease write failed")))
    result = env.mirror.resync(budget_s=0.4)
    assert not result["ok"]
    session = held["session"]
    assert not session.alive
    assert not mirror._pid_is_alive(held["pid"], held["created"])
    assert not mirror._foreign_vault_worker_alive(str(env.vault))


def test_frozen_child_timeout_cannot_return_success(env, monkeypatch):
    env.mirror._clock = time.monotonic
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    original_start = env.mirror._start_vault_io
    held = {}

    def start_and_freeze(dest):
        original_start(dest)
        session = env.mirror._vault_io
        held["session"] = session
        held["stall"] = _freeze_session(session)

    monkeypatch.setattr(env.mirror, "_start_vault_io", start_and_freeze)
    t0 = time.monotonic()
    result = env.mirror.resync(budget_s=0.1)
    total_s = time.monotonic() - t0
    assert result.get("ok") is not True
    assert not result["ok"]
    assert held["stall"]["stalled"]
    assert held["session"] and not held["session"].alive
    assert total_s < 5.0
    details = (result.get("error") or {}).get("details") or {}
    assert details.get("reason") == "timeout" or result.get("destination_unavailable")
    startup_s = float(held["session"].startup_s or 0.0)
    termination_s = float(held["session"].termination_s or 0.0)
    assert startup_s <= 2.0
    assert termination_s <= 2.5
    personal = b"COMBINED SUITE USER EDITOR"
    item_file(env).write_bytes(personal)
    assert item_file(env).read_bytes() == personal
