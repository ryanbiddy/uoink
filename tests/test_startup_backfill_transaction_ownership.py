"""Startup Phase 2 author backfill owns its SQLite transaction."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from index import Index
import server
import source_subscriptions


def _flag_row(idx):
    return idx._conn.execute(
        "SELECT value FROM memory_layer WHERE key=?",
        (server._PHASE2_BACKFILL_KEY,),
    ).fetchone()


def _seed_hostname_x_row(idx, root: Path) -> None:
    folder = root / "X" / "805baf72"
    folder.mkdir(parents=True)
    sidecar = folder / "x.json"
    sidecar.write_text(json.dumps({
        "schema_version": 2, "source_type": "x_article",
        "url": "https://x.com/boardyai/article/1", "title": "t",
        "metadata": {"author_name": "Boardy", "author_handle": "boardyai"},
    }), encoding="utf-8")
    idx.upsert_yoink({
        "video_id": "x_old1", "slug": "805baf72", "channel": "x.com",
        "title": "t", "yoinked_at": "2026-01-01T00:00:00",
        "corpus_path": str(folder / "x.md"), "sidecar_path": str(sidecar),
        "source_type": "x_article"})
    idx._conn.execute(
        "UPDATE yoinks SET platform=NULL, author=NULL WHERE video_id='x_old1'")
    idx._conn.execute(
        "UPDATE yoinks SET platform='x' WHERE platform IS NULL")
    idx._conn.commit()


def test_ordinary_author_correction_and_repeat_invocation(tmp_path, monkeypatch):
    with Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        _seed_hostname_x_row(idx, tmp_path / "corpus")
        server._run_phase2_author_backfill_once()
        row = idx.get_yoink("x_old1")
        assert row["author"] == "Boardy (@boardyai)"
        assert row["channel"] == "Boardy (@boardyai)"
        assert _flag_row(idx) is not None
        assert not idx._conn.in_transaction

        def forbidden(*_a, **_k):
            raise AssertionError("phase 2 author backfill must not rerun")

        monkeypatch.setattr(server.page_extractor, "backfill_platform_author", forbidden)
        server._run_phase2_author_backfill_once()
        again = idx.get_yoink("x_old1")
        assert again["author"] == "Boardy (@boardyai)"
        assert again["channel"] == "Boardy (@boardyai)"
        assert _flag_row(idx) is not None
        assert not idx._conn.in_transaction


def test_backfill_refuses_foreign_transaction_without_absorbing_it(tmp_path, monkeypatch):
    with Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        idx._conn.execute("BEGIN IMMEDIATE")
        idx._conn.execute(
            "INSERT INTO memory_layer(key, value, updated_at) "
            "VALUES ('caller', 'uncommitted', 'fixture')")
        with pytest.raises(RuntimeError, match="transaction"):
            server._run_phase2_author_backfill_once()
        assert idx._conn.in_transaction
        assert idx._conn.execute("SELECT key FROM memory_layer").fetchall()[0][0] == "caller"
        assert _flag_row(idx) is None
        idx._conn.rollback()
        assert idx._conn.execute("SELECT COUNT(*) FROM memory_layer").fetchone()[0] == 0
        assert not idx._conn.in_transaction


def test_failed_flag_write_leaves_no_foreign_transaction_or_false_completion(
        tmp_path, monkeypatch):
    with Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        _seed_hostname_x_row(idx, tmp_path / "corpus")
        real = idx.write_transaction

        @contextmanager
        def fail_after_insert():
            with real() as conn:
                yield conn
                raise sqlite3.OperationalError("declared flag write failure")

        monkeypatch.setattr(idx, "write_transaction", fail_after_insert)
        with pytest.raises(sqlite3.OperationalError, match="declared flag write failure"):
            server._run_phase2_author_backfill_once()
        assert not idx._conn.in_transaction
        assert idx._write_txn_owner is None
        assert _flag_row(idx) is None
        row = idx.get_yoink("x_old1")
        assert row["author"] == "Boardy (@boardyai)"

        monkeypatch.setattr(idx, "write_transaction", real)
        server._run_phase2_author_backfill_once()
        flag = _flag_row(idx)
        assert flag is not None
        assert not idx._conn.in_transaction
        payload = json.loads(flag[0])
        assert payload["scanned"] >= 1
        assert idx.get_yoink("x_old1")["author"] == "Boardy (@boardyai)"
        assert idx.get_yoink("x_old1")["channel"] == "Boardy (@boardyai)"


def _hold_source_unit(store, kind, held, release, observed, errors):
    try:
        cm = store.read if kind == "read" else store.write
        with cm() as conn:
            conn.execute("SELECT 1 FROM sqlite_master")
            keys_before = {
                r[0] for r in conn.execute("SELECT key FROM memory_layer")
            }
            held.set()
            if not release.wait(timeout=5):
                raise TimeoutError("held source unit was not released")
            observed["in_transaction"] = conn.in_transaction
            observed["keys"] = {
                r[0] for r in conn.execute("SELECT key FROM memory_layer")
            }
            observed["keys_before"] = keys_before
    except Exception as exc:
        errors.append(exc)


def _run_backfill_blocked_by_held_source(tmp_path, monkeypatch, kind):
    with Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        service = source_subscriptions.SourceSubscriptionService(index=idx)
        held = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        observed = {}
        errors = []

        holder = threading.Thread(
            target=_hold_source_unit,
            args=(service.store, kind, held, release, observed, errors),
            name=f"source-{kind}-hold",
        )
        holder.start()
        assert held.wait(timeout=5)

        def run_backfill():
            try:
                server._run_phase2_author_backfill_once()
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        worker = threading.Thread(target=run_backfill, name="phase2-backfill")
        worker.start()
        assert not finished.wait(timeout=0.4)
        assert holder.is_alive() and worker.is_alive()
        assert idx._conn.in_transaction

        release.set()
        holder.join(timeout=5)
        worker.join(timeout=5)
        assert errors == []
        assert observed["in_transaction"] is True
        assert server._PHASE2_BACKFILL_KEY not in observed["keys"]
        assert finished.is_set()
        assert _flag_row(idx) is not None
        assert not idx._conn.in_transaction


def test_held_source_read_is_not_committed_or_entered_by_backfill(tmp_path, monkeypatch):
    _run_backfill_blocked_by_held_source(tmp_path, monkeypatch, "read")


def test_held_source_write_is_not_committed_or_entered_by_backfill(tmp_path, monkeypatch):
    _run_backfill_blocked_by_held_source(tmp_path, monkeypatch, "write")


def test_backfill_and_source_tick_keep_owned_transactions(tmp_path, monkeypatch):
    with Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        service = source_subscriptions.SourceSubscriptionService(index=idx)
        start = threading.Barrier(2)
        errors = []

        def tick():
            start.wait(timeout=5)
            try:
                service.expire_poll_leases()
                service.due_poll_ids(limit=8)
            except Exception as exc:
                errors.append(exc)

        watcher = threading.Thread(target=tick, name="source-watch-tick")
        watcher.start()
        start.wait(timeout=5)
        server._run_phase2_author_backfill_once()
        watcher.join(timeout=5)
        assert errors == []
        assert _flag_row(idx) is not None
        assert not idx._conn.in_transaction
        service.expire_poll_leases()
        assert service.due_poll_ids(limit=8) == []
