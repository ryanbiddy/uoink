"""Legacy writers release failed transactions without changing commit ownership."""
from __future__ import annotations

import logging
import sqlite3
from types import SimpleNamespace

import pytest

import clips
import index as index_mod
import library_media as media
import memory_layer
import mobile_playlists
from test_upsert_rollback import _assert_usable, _record


@pytest.fixture
def library(tmp_path):
    path = tmp_path / "index.db"
    with index_mod.Index.open(path) as idx:
        idx.upsert_yoink(_record("video", "video"), content="original")
        idx.insert_citations("video", [{
            "kind": "transcript_chunk", "seq": 0, "timestamp_start": 0,
            "timestamp_end": 10, "text": "Original transcript.",
        }])
        idx.upsert_job({"job_id": "job", "kind": "extract", "status": "completed"})
        idx.enqueue_pending("https://example.test/old", 30, "2000-01-01")
        with idx.write_transaction() as conn:
            conn.execute("UPDATE pending_yoinks SET status='failed'")
            conn.execute(
                "INSERT INTO monitored_playlists (playlist_url, added_at) "
                "VALUES ('https://example.test/playlist', 'fixture')")
        yield idx, path


def _fail_trigger(conn, table, event):
    # RAISE(FAIL) preserves changes already made by this statement. A rollback
    # must undo them as well as release the write reservation.
    conn.execute(
        f"CREATE TEMP TRIGGER fail_writer AFTER {event} ON {table} "
        "BEGIN SELECT RAISE(FAIL, 'forced writer failure'); END")


def _rows(conn, table):
    return [tuple(row) for row in conn.execute(f"SELECT * FROM {table}")]


CASES = [
    ("update_content_paths", "yoinks", "UPDATE",
     lambda idx: idx.update_content_paths("video", corpus_path="new", sidecar_path="new")),
    ("log_engagement", "engagement_events", "INSERT",
     lambda idx: idx.log_engagement("video", "opened", "dashboard")),
    ("set_facets", "yoinks", "UPDATE", lambda idx: idx.set_facets("video", topic="new")),
    ("soft_delete_yoink", "yoinks", "UPDATE", lambda idx: idx.soft_delete_yoink("video")),
    ("restore_yoink", "yoinks", "UPDATE", lambda idx: idx.restore_yoink("video")),
    ("enqueue_pending", "pending_yoinks", "INSERT",
     lambda idx: idx.enqueue_pending("https://example.test/new", 30, "2000-01-01")),
    ("set_pending_error", "pending_yoinks", "UPDATE",
     lambda idx: idx.set_pending_error(1, "new error")),
    ("retry_pending_now", "pending_yoinks", "UPDATE", lambda idx: idx.retry_pending_now(1)),
    ("insert_citations", "citations", "INSERT",
     lambda idx: idx.insert_citations("video", [
         {"kind": "transcript_chunk", "seq": 0, "text": "replacement"},
         {"kind": "transcript_chunk", "seq": 1, "text": "second"}])),
    ("insert_citations_empty", "citations", "DELETE", lambda idx: idx.insert_citations("video", [])),
    ("upsert_job", "jobs", "INSERT",
     lambda idx: idx.upsert_job({"job_id": "new", "kind": "extract", "status": "pending"})),
    ("delete_job", "jobs", "DELETE", lambda idx: idx.delete_job("job")),
    ("prune_jobs", "jobs", "DELETE", lambda idx: idx.prune_jobs(0)),
    ("upsert_taxonomy", "taxonomy", "INSERT",
     lambda idx: idx.upsert_taxonomy({"video_id": "video", "hook_type": "demo"})),
    ("set_anchor", "memory_layer", "INSERT",
     lambda idx: memory_layer.set_anchor(idx, memory_layer.ANCHOR_SECTIONS[0], "new")),
    ("_write_taste_anchors", "memory_layer", "INSERT",
     lambda idx: memory_layer._write_taste_anchors(idx, {"best": ["video"]})),
]


@pytest.mark.parametrize("site,table,event,write", CASES, ids=[c[0] for c in CASES])
def test_legacy_statement_failure_rolls_back(library, monkeypatch, site, table, event, write):
    idx, path = library
    if site == "enqueue_pending":
        monkeypatch.setattr(index_mod, "_PENDING_TABLE_CAP", 1)
    if site in {"set_pending_error", "restore_yoink"}:
        with idx.write_transaction() as conn:
            conn.execute("UPDATE pending_yoinks SET status='pending'")
            conn.execute("UPDATE yoinks SET deleted_at='fixture'")
    before = _rows(idx._conn, table)
    _fail_trigger(idx._conn, table, event)
    with idx._lock:
        if site == "enqueue_pending":
            # poll_playlist can already have implicit work under this RLock.
            idx._conn.execute(
                "INSERT INTO memory_layer (key, value, updated_at) "
                "VALUES ('caller', 'earlier work', 'fixture')")
        with pytest.raises(sqlite3.IntegrityError, match="forced writer failure"):
            write(idx)
    _assert_usable(idx, path)
    assert _rows(idx._conn, table) == before
    if site == "enqueue_pending":
        assert not _rows(idx._conn, "memory_layer")


class FailStatement:
    def __init__(self, conn, prefix, error):
        self.conn, self.prefix, self.error = conn, prefix, error
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def execute(self, sql, params=()):
        if " ".join(sql.split()).startswith(self.prefix):
            assert self.conn.in_transaction, "failure must follow earlier work"
            self.failed = True
            raise self.error
        return self.conn.execute(sql, params)


def test_taxonomy_fts_failure_rolls_back(library, monkeypatch):
    idx, path = library
    before = _rows(idx._conn, "yoinks")
    conn = FailStatement(idx._conn, "UPDATE yoinks_fts", RuntimeError("FTS failure"))
    monkeypatch.setattr(idx, "_conn", conn)
    with pytest.raises(RuntimeError, match="FTS failure") as raised:
        idx.update_taxonomy("video", platform="youtube", author="new", channel="new")
    assert raised.value is conn.error and conn.failed
    _assert_usable(idx, path)
    assert _rows(idx._conn, "yoinks") == before


def test_import_memory_failure_rolls_back_prior_rows(library):
    idx, path = library
    _fail_trigger(idx._conn, "memory_layer", "INSERT")
    before = _rows(idx._conn, "yoink_tags")
    with pytest.raises(sqlite3.IntegrityError, match="forced writer failure"):
        idx.import_payload({"format": idx.EXPORT_FORMAT, "tables": {
            "yoink_tags": [{"video_id": "video", "tag": "new", "source": "agent", "added_at": "fixture"}],
            "memory_layer": [{"key": "taste.test", "value": "new", "updated_at": "fixture"}],
        }})
    _assert_usable(idx, path)
    assert _rows(idx._conn, "yoink_tags") == before
    assert not _rows(idx._conn, "memory_layer")


def test_add_playlist_registration_failure_rolls_back(library, monkeypatch):
    idx, path = library
    error = RuntimeError("registration failed")

    def fail(*args, **kwargs):
        assert idx._conn.in_transaction
        raise error

    monkeypatch.setattr(mobile_playlists._subscriptions(), "legacy_register", fail)
    before = _rows(idx._conn, "monitored_playlists")
    with pytest.raises(RuntimeError) as raised:
        mobile_playlists.add_playlist(idx, "https://example.test/new", normalize_playlist_url=lambda url: url)
    assert raised.value is error
    _assert_usable(idx, path)
    assert _rows(idx._conn, "monitored_playlists") == before


@pytest.mark.parametrize("enqueue", [False, True], ids=["events-only", "nested-enqueue"])
def test_poll_failure_rolls_back_since_last_commit(library, monkeypatch, enqueue):
    idx, path = library
    monkeypatch.setattr(mobile_playlists._subscriptions(), "tables_present", lambda conn: False)
    _fail_trigger(idx._conn, "monitored_playlists", "UPDATE")
    with pytest.raises(sqlite3.IntegrityError, match="forced writer failure"):
        mobile_playlists.poll_playlist(
            idx, 1, ytdlp_cmd=["unused"],
            normalize_video_to_canonical_url=(lambda vid: "https://example.test/" + vid) if enqueue else None,
            fetch_entries=lambda url: [{"video_id": "one"}, {"video_id": "two"}])
    _assert_usable(idx, path)
    # The second enqueue still commits the first discovery, just as before.
    events = idx._conn.execute("SELECT video_id FROM mobile_queue_events").fetchall()
    assert [row[0] for row in events] == (["one"] if enqueue else [])
    assert idx._conn.execute("SELECT last_polled_at FROM monitored_playlists").fetchone()[0] is None


@pytest.mark.parametrize("empty", [False, True], ids=["replace", "clear"])
def test_citation_owner_rolls_back_clip_failure(library, monkeypatch, empty):
    idx, path = library
    error = BaseException("clip projection interrupted")
    before = _rows(idx._conn, "citations")

    def fail(conn, video_id, *, commit):
        assert commit is False and conn.in_transaction
        conn.execute("DELETE FROM clips WHERE video_id=?", (video_id,))
        raise error

    monkeypatch.setattr(clips, "build_clips_for_video", fail)
    with pytest.raises(BaseException) as raised:
        idx.insert_citations("video", [] if empty else [{"kind": "transcript_chunk", "seq": 0, "text": "new"}])
    assert raised.value is error
    _assert_usable(idx, path)
    assert _rows(idx._conn, "citations") == before
    assert _rows(idx._conn, "clips")


@pytest.mark.parametrize("rebuild_all", [False, True], ids=["build_clips_for_video", "rebuild_all_clips"])
def test_clip_failure_respects_commit_owner(library, rebuild_all):
    idx, path = library
    before = _rows(idx._conn, "clips")
    _fail_trigger(idx._conn, "clips", "INSERT")
    # A borrowed connection must remain owned by its caller, even on failure.
    with pytest.raises(sqlite3.IntegrityError, match="forced writer failure"):
        clips.build_clips_for_video(idx._conn, "video", commit=False)
    assert idx._conn.in_transaction
    idx._conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="forced writer failure"):
        if rebuild_all:
            clips.rebuild_all_clips(idx._conn)
        else:
            clips.build_clips_for_video(idx._conn, "video")
    _assert_usable(idx, path)
    assert _rows(idx._conn, "clips") == before


@pytest.mark.parametrize("site", ["store_snapshot", "rebuild_item", "publish_transcript"])
@pytest.mark.parametrize("error_type", [RuntimeError, BaseException])
def test_media_unexpected_failure_rolls_back(library, tmp_path, monkeypatch, site, error_type):
    from test_phase6_evaluation import _fixture, _seed

    idx, path = library
    fixture = _fixture(SimpleNamespace(root=tmp_path), key="media-rollback", publication_conn=idx._conn)
    _seed(idx._conn, fixture, materialized=False)
    before = {table: _rows(idx._conn, table) for table in ("citations", "clips", "media_depth")}
    error = error_type("clip write failed")
    conn = FailStatement(idx._conn, "DELETE FROM clips", error)
    # In clip-only rebuild the DELETE is the first write; reconstruction and
    # publication have already written citations before reaching this seam.
    monkeypatch.setattr(idx, "_conn", conn)
    if site == "store_snapshot":
        with pytest.raises(error_type) as raised:
            media.store_snapshot(conn, fixture.item, fixture.cues, fixture.block, commit=False)
        assert raised.value is error and conn.in_transaction
        conn.rollback()
    with pytest.raises(error_type) as raised:
        if site == "store_snapshot":
            idx.store_media_snapshot(fixture.item["video_id"], fixture.cues, fixture.block)
        elif site == "rebuild_item":
            idx.rebuild_media_item(fixture.item["video_id"], sidecar=fixture.sidecar)
        else:
            idx.publish_media_snapshot(
                fixture.item["video_id"], cues=fixture.cues, media_block=fixture.block,
                artifacts=fixture.files, ticket=fixture.publication_ticket)
    assert raised.value is error and conn.failed
    _assert_usable(idx, path)
    for table, rows in before.items():
        assert _rows(idx._conn, table) == rows


@pytest.mark.parametrize("boundary", ["write_transaction", "read_snapshot"])
def test_boundary_still_refuses_an_open_transaction_without_touching_it(library, boundary):
    # A caller up the stack may still own this work, so the boundary neither
    # commits nor discards it. Writers roll back their own failures instead.
    idx, path = library
    idx._conn.execute("UPDATE yoinks SET title='caller work' WHERE video_id='video'")
    with pytest.raises(RuntimeError, match="another transaction is active"):
        with getattr(idx, boundary)():
            pytest.fail("entered over an open transaction")
    assert idx._conn.in_transaction
    assert idx._conn.execute("SELECT title FROM yoinks").fetchone()[0] == "caller work"
    idx._conn.rollback()
    _assert_usable(idx, path)


@pytest.mark.parametrize("boundary", ["_rollback_on_error", "write_transaction", "read_snapshot"])
def test_rollback_failure_does_not_hide_original_exception(library, monkeypatch, boundary):
    idx, path = library
    real = idx._conn
    error = ValueError("original failure")

    class BrokenRollback:
        def __getattr__(self, name):
            return getattr(real, name)

        def rollback(self):
            raise sqlite3.OperationalError("rollback itself failed")

    monkeypatch.setattr(idx, "_conn", BrokenRollback())
    try:
        with pytest.raises(ValueError) as raised:
            with idx._lock, getattr(idx, boundary)():
                real.execute("UPDATE yoinks SET title='uncommitted'")
                raise error
        assert raised.value is error
    finally:
        monkeypatch.setattr(idx, "_conn", real)
        real.rollback()
    _assert_usable(idx, path)
