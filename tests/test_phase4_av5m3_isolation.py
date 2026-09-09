"""AV-5m3 focused tests: isolated vault I/O, independent edits, temp identity.

Does not edit or replace the frozen AW-3 D13 cases. Those remain observations
for Ryan: both parametrized branches share one post-timeout os.replace wrapper.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import library_briefs as briefs
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


def test_vault_io_worker_startup_and_terminate_are_real(tmp_path_factory):
    root = tmp_path_factory.mktemp("w")
    dest = root / "v"
    dest.mkdir()
    src = root / "src.bin"
    dst = root / "dst.bin"
    src.write_bytes(b"new-bytes")
    dst.write_bytes(b"old-bytes")
    started = time.monotonic()
    session = mirror._VaultIoSession.start(str(dest))
    startup_s = session.startup_s
    assert startup_s >= 0
    assert time.monotonic() - started >= startup_s
    pid = session.pid
    assert session.alive and mirror._pid_is_alive(pid)
    mutate_started = time.monotonic()
    session.replace(str(src), str(dst))
    mutate_s = time.monotonic() - mutate_started
    assert dst.read_bytes() == b"new-bytes"
    session.terminate()
    assert not session.alive
    assert not mirror._pid_is_alive(pid)
    assert mutate_s < 2.0
    src.write_bytes(b"after-kill")
    with pytest.raises(OSError):
        session.replace(str(src), str(dst))
    assert dst.read_bytes() == b"new-bytes"


def test_timeout_kills_worker_and_keeps_independent_user_edit(env, monkeypatch):
    env.mirror._clock = time.monotonic
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    target = item_file(env)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = env.mirror._atomic_vault
    original_work = env.mirror._vault_work
    personal = b"INDEPENDENT USER EDITOR AFTER TIMEOUT"

    def complete_work(plan):
        try:
            return original_work(plan)
        finally:
            finished.set()

    def blocked(dest, data, root, *, recheck):
        if dest != target:
            return original(dest, data, root, recheck=recheck)
        entered.set()
        assert release.wait(3)
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", blocked)
    monkeypatch.setattr(env.mirror, "_vault_work", complete_work)
    try:
        t0 = time.monotonic()
        result = env.mirror.resync(budget_s=0.2)
        cancel_s = time.monotonic() - t0
        assert entered.is_set() and not result["ok"]
        startup_s = float(getattr(env.mirror, "_vault_io_startup_s", 0.0) or 0.0)
        assert cancel_s >= 0.2
        target.write_bytes(personal)
    finally:
        release.set()
        assert finished.wait(5)
    assert target.read_bytes() == personal
    assert not mirror._foreign_vault_worker_alive(str(env.vault))
    assert env.mirror._vault_io is None


def test_live_worker_lease_blocks_a_second_mirror(env):
    export(env)
    dummy = subprocess.Popen(
        [sys.executable, "-B", "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        mirror._write_dest_lease(str(env.vault), {
            "pid": dummy.pid, "destination": str(env.vault),
        })
        other = _other_mirror(env, env.root / "o")
        other._clock = time.monotonic
        result = other.resync(budget_s=0.3)
        assert not result["ok"]
        assert result.get("destination_unavailable") or result.get("error", {}).get("code") == "destination_unavailable"
        assert item_file(env).read_bytes()
    finally:
        dummy.kill()
        dummy.wait(3)
        mirror._clear_dest_lease(str(env.vault), dummy.pid)


def test_recorded_temp_hash_does_not_delete_user_bytes(env):
    export(env)
    uoink = env.vault / mirror.MIRROR_ROOT
    owned = uoink / "Library" / "owned-temp.tmp"
    owned.write_bytes(b"OWNED TEMP CONTENT")
    digest = hashlib.sha256(owned.read_bytes()).hexdigest()
    env.mirror._start_vault_io(str(env.vault))
    try:
        env.mirror._record_allocated_temp(mirror.item_key("a"), str(owned.relative_to(uoink)), digest)
        owned.write_bytes(b"USER REPLACED THE RECORDED TEMP PATH")
        env.mirror._cleanup_owned_temps(uoink, {}, {})
        assert owned.read_bytes() == b"USER REPLACED THE RECORDED TEMP PATH"
        intent = env.mirror._load_intents().get(mirror.item_key("a")) or {}
        pending = mirror._pending_temps_from_intent(intent)
        assert not any(item.get("rel") == str(owned.relative_to(uoink)) and item.get("hash") == digest for item in pending)
    finally:
        env.mirror._stop_vault_io()


def test_failed_replace_retains_temp_generation(env, monkeypatch):
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    target = item_file(env)
    original_replace = env.mirror._io_replace
    original_unlink = env.mirror._io_unlink
    leftover = []

    def fail_item(src, dst):
        if Path(dst) == target:
            leftover.append(Path(src))
            raise OSError("isolated replace failed")
        return original_replace(src, dst)

    def fail_cleanup(path):
        if Path(path) in leftover:
            raise OSError("isolated temp cleanup failed")
        return original_unlink(path)

    monkeypatch.setattr(env.mirror, "_io_replace", fail_item)
    monkeypatch.setattr(env.mirror, "_io_unlink", fail_cleanup)
    env.mirror.resync()
    assert len(leftover) == 1 and leftover[0].is_file()
    uoink = env.vault / mirror.MIRROR_ROOT
    intent = env.mirror._load_intents()[mirror.item_key("a")]
    assert uoink / intent["temp_rel"] == leftover[0]
    assert intent.get("temp_hash") == hashlib.sha256(leftover[0].read_bytes()).hexdigest()
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    env.mirror.resync()
    pending = mirror._pending_temps_from_intent(env.mirror._load_intents().get(mirror.item_key("a")))
    assert any(item.get("rel") == intent["temp_rel"] for item in pending) or leftover[0].exists()
    user_bytes = b"USER FILE AT OLD TEMP PATH"
    leftover[0].write_bytes(user_bytes)
    env.mirror._start_vault_io(str(env.vault))
    try:
        env.mirror._cleanup_owned_temps(uoink, {}, {})
    finally:
        env.mirror._stop_vault_io()
    assert leftover[0].is_file() and leftover[0].read_bytes() == user_bytes


def test_sqlite_writer_exclusion_preserves_caller_transaction(env):
    conn = env.idx._conn
    with env.idx.write_transaction() as txn:
        txn.execute("CREATE TABLE IF NOT EXISTS av5m3_sentinel (id INTEGER)")
        txn.execute("INSERT INTO av5m3_sentinel (id) VALUES (7)")
        assert conn.in_transaction
        with env.store._sqlite_writer_exclusion():
            assert conn.in_transaction
            row = txn.execute("SELECT id FROM av5m3_sentinel").fetchone()
            assert row[0] == 7
        assert conn.in_transaction
        row = txn.execute("SELECT id FROM av5m3_sentinel").fetchone()
        assert row[0] == 7
    assert not conn.in_transaction
    row = conn.execute("SELECT id FROM av5m3_sentinel").fetchone()
    assert row[0] == 7


def test_publication_still_excludes_idle_connection_writers(env, monkeypatch):
    """Independent SQLite exclusion is unchanged when no caller transaction is open."""
    original = briefs.os.replace
    committed_before_replace = []

    def replace_after_external_writer(src, dst):
        if Path(src).name.startswith(".tmp-") and Path(dst).parent.name == "2026-09-08":
            import sqlite3
            committed = threading.Event()

            def writer():
                conn = sqlite3.connect(env.root / "index.db", timeout=0.08)
                try:
                    conn.execute("UPDATE yoinks SET deleted_at='2026-09-08T12:00:00' WHERE video_id='b'")
                    conn.commit()
                    committed.set()
                except sqlite3.OperationalError:
                    conn.rollback()
                finally:
                    conn.close()

            thread = threading.Thread(target=writer)
            thread.start()
            thread.join(1)
            committed_before_replace.append(committed.is_set())
        return original(src, dst)

    monkeypatch.setattr(briefs.os, "replace", replace_after_external_writer)
    packet = env.store.prepare_input("2026-09-08", "aw-run")
    entry = next(e for e in packet["cards"] if e["item_id"] == "b")
    quote = entry["card"]["excerpts"][0]
    citation = dict(item_id="b", source_revision=entry["source_revision"],
                    card_hash=entry["card_hash"], excerpt_id=quote["excerpt_id"],
                    quote=quote["text"], evidence_kind=quote["evidence_kind"],
                    start=quote["start"], end=quote["end"])
    try:
        receipt = env.store.publish(
            job_key=packet["job_key"], input_hash=packet["input_hash"],
            input_packet=packet, submission_key="av5m3-brief",
            document="Original evidence b.", citations=[citation],
            usage=None, client_identity="av5m3")
    except resources.ResourceError as error:
        assert error.code in {"stale_brief", "revision_unavailable", "resource_deleted"}
        return
    assert committed_before_replace
    assert not (receipt["ok"] and any(committed_before_replace))
