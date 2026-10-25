"""A failed yoink write must not leave the shared connection in a transaction.

Upgrading a real library to 3.11.1 hit UNIQUE(yoinks.slug) during the startup
backfill. upsert_yoink raised without rolling back its implicit BEGIN, so every
later write_transaction and read_snapshot on the helper refused to start.
"""
from __future__ import annotations

import sqlite3

import pytest

import index as index_mod


def _record(video_id, slug):
    return {
        "video_id": video_id,
        "slug": slug,
        "channel": "TestChannel",
        "title": "Rollback test",
        "topic": "AI and ML",
        "hook_type": "demo",
        "yoinked_at": "2026-10-25T02:19:00",
        "corpus_path": "",
        "sidecar_path": "",
        "source_type": "youtube",
    }


def _assert_usable(idx, path):
    assert not idx._conn.in_transaction
    with idx.write_transaction() as conn:
        conn.execute("SELECT 1")
    with idx.read_snapshot() as conn:
        conn.execute("SELECT 1")
    outsider = sqlite3.connect(path, timeout=0.5)
    try:
        outsider.execute("BEGIN IMMEDIATE")
        outsider.rollback()
    finally:
        outsider.close()


def test_slug_conflict_rolls_back_and_keeps_index_usable(tmp_path):
    path = tmp_path / "index.db"
    idx, _ = index_mod.Index.open_or_recover(path)
    try:
        idx.upsert_yoink(_record("first", "same-slug"), content="one")
        with pytest.raises(sqlite3.IntegrityError):
            idx.upsert_yoink(_record("second", "same-slug"), content="two")
        _assert_usable(idx, path)
        assert idx.get_yoink("second") is None
        assert idx.get_yoink("first")["slug"] == "same-slug"
        # The next write still lands and persists.
        idx.upsert_yoink(_record("third", "other-slug"), content="three")
    finally:
        idx.close()
    idx, _ = index_mod.Index.open_or_recover(path)
    try:
        assert idx.get_yoink("third") is not None
        assert idx.get_yoink("second") is None
    finally:
        idx.close()


def test_failed_delete_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "index.db"
    idx, _ = index_mod.Index.open_or_recover(path)
    try:
        idx.upsert_yoink(_record("doomed", "doomed"), content="body")
        real_conn = idx._conn
        calls = {"n": 0}

        class FailSecond:
            def __getattr__(self, name):
                return getattr(real_conn, name)

            def execute(self, sql, params=()):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise sqlite3.OperationalError("simulated FTS failure")
                return real_conn.execute(sql, params)

        monkeypatch.setattr(idx, "_conn", FailSecond())
        with pytest.raises(sqlite3.OperationalError):
            idx.delete_yoink("doomed")
        monkeypatch.setattr(idx, "_conn", real_conn)
        _assert_usable(idx, path)
        assert idx.get_yoink("doomed") is not None
    finally:
        idx.close()
