"""Phase 3 gates S01 (migration and rerun) and S02 (default off, legacy
conversion). Contract: docs/library/PHASE3-CONTRACT-2026-09-07.md.

Run: python -m pytest -q tests/test_source_subscriptions_migration.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    Clock, DAY_MS, FEED_URL, FakeAdapter, FakeBackend, OPERATOR, PLAYLIST_URL, REGISTRY, T0,
    make_service, open_index, register, rows, snapshot, status, turn_on, vid,
)

import index as index_mod  # noqa: E402
import mobile_playlists  # noqa: E402
import podcasts  # noqa: E402
import source_subscriptions as ss  # noqa: E402

TABLES = ("source_subscriptions", "source_consent_receipts", "source_user_intents",
          "source_detection_cursors", "source_items", "source_capture_starts",
          "source_classification_policy", "source_classification_outbox")
INDEXES = ("source_detection_due", "source_items_capture_key", "source_items_ready",
           "source_daily_slot", "source_one_active_source", "source_one_active_capture",
           "source_starts_item", "source_classification_pending")


def _names(conn, kind):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type=?", (kind,)).fetchall()}


# ---- S01 --------------------------------------------------------------------
def test_s01_migration_0028_is_latest_and_applies_through_the_runner(tmp_path):
    idx = open_index(tmp_path)
    assert index_mod.latest_schema_version() == 28
    assert idx.schema_version() == 28
    conn = idx._conn
    assert set(TABLES) <= _names(conn, "table")
    assert set(INDEXES) <= _names(conn, "index")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # No automatic work: every new table is empty after migration.
    for table in TABLES:
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    idx.close()


def test_s01_rerun_is_idempotent_and_preserves_import_receipt_and_hold(tmp_path):
    idx = open_index(tmp_path)
    feed = podcasts.add_feed(idx, FEED_URL, poll_interval_min=60)
    # A pre-Phase-3 explicit opt-in, set directly (the old route now refuses).
    with idx.write_transaction() as conn:
        conn.execute("UPDATE podcast_feeds SET auto_ingest=1 WHERE id=?", (feed["id"],))
        conn.execute("DELETE FROM source_detection_cursors WHERE source_id IN "
                     "(SELECT source_id FROM source_subscriptions WHERE legacy_feed_id=?)",
                     (feed["id"],))
        conn.execute("DELETE FROM source_subscriptions WHERE legacy_feed_id=?", (feed["id"],))
    podcasts.upsert_episodes(idx, feed["id"], [
        {"guid": f"g{i}", "title": f"Ep {i}", "audio_url": f"https://cdn.example/{i}.mp3",
         "published_at": f"2026-08-{i + 1:02d}T00:00:00Z"} for i in range(3)])
    clock = Clock()
    service = make_service(idx, clock=clock)
    first = service.import_legacy_registries()
    assert first["feeds_imported"] == 1 and first["items_imported"] == 3
    source = rows(service, "SELECT * FROM source_subscriptions")[0]
    receipt = rows(service, "SELECT * FROM source_consent_receipts")[0]
    hold = source["accounting_hold_until_ms"]
    assert hold == ss.next_utc_midnight_ms(T0)
    assert receipt["authority"] == "legacy_explicit_opt_in"
    assert source["consent_state"] == "on" and source["boundary"] == "initial"
    idx.close()

    # Re-open: migrations rerun through the real runner (schema_version already
    # 28 -> no-op), then the import reruns and must change nothing.
    clock.advance(DAY_MS)
    idx = open_index(tmp_path)
    service = make_service(idx, clock=clock)
    second = service.import_legacy_registries()
    assert second["feeds_imported"] == 0 and second["skipped"] == 1
    again = rows(service, "SELECT * FROM source_subscriptions")[0]
    assert again["accounting_hold_until_ms"] == hold, "rerun must not postpone the hold"
    assert rows(service, "SELECT COUNT(*) AS n FROM source_consent_receipts")[0]["n"] == 1
    assert again["revision"] == source["revision"] and again["consent_epoch"] == source["consent_epoch"]
    assert rows(service, "SELECT COUNT(*) AS n FROM source_items")[0]["n"] == 3
    # Migration replay directly through the runner on the same file is a no-op.
    raw = sqlite3.connect(str(tmp_path / "index.db"))
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys=ON")
    assert index_mod._run_migrations(raw) == 28
    assert raw.execute("SELECT COUNT(*) FROM schema_version WHERE version=28").fetchone()[0] == 1
    raw.close()
    idx.close()


def test_s01_ddl_backstops_slot_active_and_capture_uniqueness(tmp_path):
    idx = open_index(tmp_path)
    service = make_service(idx)
    source = register(service)
    conn = idx._conn
    sid = source["source_id"]
    now = T0
    conn.execute(
        "INSERT INTO source_items (item_id, source_id, entry_id, capture_key, first_seen_ms, "
        "last_seen_ms, first_scan_revision, metadata_json) VALUES ('si_a', ?, 'e1', 'youtube:e1', ?, ?, 1, '{}')",
        (sid, now, now))
    conn.execute(
        "INSERT INTO source_items (item_id, source_id, entry_id, capture_key, first_seen_ms, "
        "last_seen_ms, first_scan_revision, metadata_json) VALUES ('si_b', ?, 'e2', 'youtube:e2', ?, ?, 1, '{}')",
        (sid, now, now))
    day = ss.utc_day(now)
    token = "t" * 43

    def insert(start_id, item, key, slot, state):
        conn.execute(
            "INSERT INTO source_capture_starts (start_id, source_id, item_id, capture_key, consent_epoch, "
            "utc_day, slot, state, reserved_at_ms, reservation_expires_ms, owner_token, owner_instance, "
            "started_at_ms) VALUES (?,?,?,?,1,?,?,?,?,?,?,'x',?)",
            (start_id, sid, item, key, day, slot, state, now, now + 120_000, token,
             now if state in ("started", "succeeded", "failed") else None))

    insert("st_1", "si_a", "youtube:e1", 1, "succeeded")
    with pytest.raises(sqlite3.IntegrityError):
        insert("st_2", "si_b", "youtube:e2", 1, "reserved")  # slot 1 occupied today
    with pytest.raises(sqlite3.IntegrityError):
        insert("st_3", "si_b", "youtube:e1", 2, "reserved")  # capture key already succeeded
    insert("st_4", "si_b", "youtube:e2", 2, "reserved")
    with pytest.raises(sqlite3.IntegrityError):
        insert("st_5", "si_b", "youtube:e2", 3, "reserved")  # one active per source
    conn.rollback()
    idx.close()


# ---- S02 --------------------------------------------------------------------
def test_s02_new_sources_default_off_with_due_cursor_and_no_network(tmp_path):
    idx = open_index(tmp_path)
    adapter = FakeAdapter([snapshot([vid(1)])])
    service = make_service(idx, adapter=adapter)
    for kind, url in (("podcast_rss", FEED_URL),
                      ("youtube_channel", "https://www.youtube.com/channel/UC" + "c" * 22),
                      ("youtube_playlist", PLAYLIST_URL)):
        source = register(service, kind, url)
        assert source["consent_state"] == "off" and source["revision"] == 0
        assert source["consent_epoch"] == 0 and source["boundary"] == "none"
        assert source["enrollment"]["initial_completed"] is False
        assert source["enrollment"]["remaining_initial_slots"] == 25
        assert source["poll_interval_min"] == 60
        assert source["detection"]["next_poll_at_ms"] <= T0
    assert adapter.calls == [], "registration performs no network I/O"
    # A metadata-only poll happens while off and creates no eligibility.
    results = service.detection_pass()
    assert len(results) == 3 and all(r["ok"] for r in results)
    for row in rows(service, "SELECT * FROM source_items"):
        assert row["eligibility"] == "none" and row["state"] == "observed"
        assert row["first_seen_consent_epoch"] is None
    assert service.capture_pass() == []
    idx.close()


def test_s02_legacy_conversion_transfers_only_explicit_podcast_opt_in(tmp_path):
    idx = open_index(tmp_path)
    with idx.write_transaction() as conn:
        conn.execute("INSERT INTO podcast_feeds (feed_url, poll_interval_min, auto_ingest, added_at) "
                     "VALUES (?, 60, 1, '2026-08-01T00:00:00Z')", ("https://opted.example/feed.xml",))
        conn.execute("INSERT INTO podcast_feeds (feed_url, poll_interval_min, auto_ingest, enabled, added_at) "
                     "VALUES (?, 30, 0, 0, '2026-08-01T00:00:00Z')", ("https://plain.example/feed.xml",))
        conn.execute("INSERT INTO monitored_playlists (playlist_url, name, poll_interval_min, enabled, "
                     "added_at, last_seen_video_ids) VALUES (?, 'mobile', 5, 1, '2026-08-01T00:00:00Z', ?)",
                     (PLAYLIST_URL, json.dumps([vid(1), vid(2), "bad id"])))
        conn.execute("INSERT INTO monitored_playlists (playlist_url, name, poll_interval_min, enabled, "
                     "added_at) VALUES (?, 'wl', 5, 1, '2026-08-01T00:00:00Z')",
                     ("https://www.youtube.com/playlist?list=WL",))
    clock = Clock()
    service = make_service(idx, clock=clock)
    report = service.import_legacy_registries()
    assert report["feeds_imported"] == 2 and report["playlists_imported"] == 1
    assert report["items_imported"] == 2
    assert [c["reason"] for c in report["conflicts"]] == ["unsupported_source"]

    by_kind = {(r["kind"], r["canonical_url"]): r for r in rows(service, "SELECT * FROM source_subscriptions")}
    opted = by_kind[("podcast_rss", "https://opted.example/feed.xml")]
    plain = by_kind[("podcast_rss", "https://plain.example/feed.xml")]
    playlist = by_kind[("youtube_playlist", PLAYLIST_URL)]
    assert opted["consent_state"] == "on" and opted["boundary"] == "initial"
    assert opted["revision"] == 1 and opted["consent_epoch"] == 1
    assert plain["consent_state"] == "off" and plain["detection_enabled"] == 0
    assert playlist["consent_state"] == "off", "enabled=1 never infers consent"
    assert playlist["poll_interval_min"] == 15, "5-minute legacy interval normalizes to the floor"
    for row in (opted, plain, playlist):
        assert row["accounting_hold_until_ms"] == ss.next_utc_midnight_ms(T0)
    receipts = rows(service, "SELECT * FROM source_consent_receipts")
    assert [r["authority"] for r in receipts] == ["legacy_explicit_opt_in"]
    assert receipts[0]["source_id"] == opted["source_id"]

    # Status reports the cutover hold separately from ledger counts, and the
    # hold blocks starts on the cutover day even for the opted-in feed.
    summary = status(service, opted["source_id"])["source"]
    assert summary["allowance"]["hold_reason"] == "legacy_accounting_hold"
    assert summary["allowance"]["hold_until_ms"] == ss.next_utc_midnight_ms(T0)
    assert summary["allowance"]["charged"] == 0 and summary["allowance"]["reserved"] == 0
    assert summary["capture_status"] == "legacy_accounting_hold"
    assert service.claim_start(opted["source_id"])["outcome"] == "legacy_accounting_hold"
    idx.close()


def test_s02_global_flag_and_old_boolean_cannot_start_an_off_source(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    backend = FakeBackend()
    adapter = FakeAdapter([snapshot([vid(1), vid(2)])])
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    # Old playlist route: enabled=1 by default, projected as an off source.
    playlist = mobile_playlists.add_playlist(
        idx, PLAYLIST_URL, name="mobile", poll_interval_min=1,
        normalize_playlist_url=lambda raw: raw)
    assert playlist["poll_interval_min"] == 15
    source_id = ss.legacy_source_id(idx._conn, playlist_id=int(playlist["id"]))
    assert source_id is not None
    # Old feed route with auto_ingest=True: stored as 0 and flagged.
    feed = podcasts.add_feed(idx, FEED_URL, auto_ingest=True)
    assert feed["auto_ingest"] == 0 and feed["consent_required"] is True
    with pytest.raises(podcasts.ManagedBySubscription):
        podcasts.set_feed_auto_ingest(idx, feed["id"], True)
    assert rows(service, "SELECT consent_state FROM source_subscriptions WHERE legacy_feed_id=?",
                (feed["id"],))[0]["consent_state"] == "off"
    # Detection runs (source is on for detection) but nothing captures.
    service.detection_pass()
    assert service.capture_pass() == [] and backend.runs == []
    # The old poll path cannot enqueue for a linked playlist without the gate.
    refused = mobile_playlists.poll_playlist(
        idx, int(playlist["id"]), normalize_video_to_canonical_url=lambda v: f"u:{v}")
    assert refused["ok"] is False and refused["error"] == "managed_by_subscription"
    assert idx._conn.execute("SELECT COUNT(*) FROM pending_yoinks").fetchone()[0] == 0
    # Only the confirmed consent operation turns capture on.
    turn_on(service, source_id)
    assert rows(service, "SELECT consent_state FROM source_subscriptions WHERE source_id=?",
                (source_id,))[0]["consent_state"] == "on"
    idx.close()


def test_s02_old_delete_routes_archive_and_preserve_rows(tmp_path):
    idx = open_index(tmp_path)
    service = make_service(idx)
    feed = podcasts.add_feed(idx, FEED_URL)
    source_id = feed["source_id"]
    turn_on(service, source_id)
    assert podcasts.remove_feed(idx, feed["id"]) is True
    assert podcasts.get_feed(idx, feed["id"]) is not None, "referenced feed row is preserved"
    source = rows(service, "SELECT * FROM source_subscriptions WHERE source_id=?", (source_id,))[0]
    assert source["archived"] == 1 and source["consent_state"] == "off"
    assert source["detection_enabled"] == 0 and source["boundary"] == "none"
    receipts = rows(service, "SELECT authority FROM source_consent_receipts WHERE source_id=? "
                             "ORDER BY created_at_ms", (source_id,))
    assert [r["authority"] for r in receipts] == ["local_user", "archive"]
    # Re-registering unarchives with capture off and a receipt.
    again = service.register_source(REGISTRY, {"kind": "podcast_rss", "url": FEED_URL})
    assert again["ok"] and again["created"] is False
    assert again["source"]["archived"] is False and again["source"]["consent_state"] == "off"
    assert again["receipt"]["authority"] == "archive"
    idx.close()
