"""Heartbeat semantics (Astra finding 6, 2026-09-04).

Before: `_last_successful_tick_at` advanced at the end of every scheduler
pass, including a pass in which every feed poll raised. After: four separate
stamps (tick completion, successful tick, successful poll, ingest completion)
plus a freshness state, surfaced under `heartbeat` in /health and reported
by `uoink doctor` off the same fields. A failed poll never advances a
success stamp.
"""
from __future__ import annotations

import json

import pytest

import server


_FRESH_STATE = {
    "last_tick_completed_at": None,
    "last_tick_ok": None,
    "last_tick_polls": 0,
    "last_tick_failed_polls": 0,
    "last_successful_poll_at": None,
    "last_failed_poll_at": None,
    "last_poll_error": None,
    "last_ingest_completed_at": None,
    "ticks_completed": 0,
    "polls_ok": 0,
    "polls_failed": 0,
    "ingests_completed": 0,
}


@pytest.fixture(autouse=True)
def _reset_heartbeat(monkeypatch):
    monkeypatch.setattr(server, "_last_successful_tick_at", None)
    with server._heartbeat_lock:
        saved = dict(server._heartbeat)
        assert set(saved) == set(_FRESH_STATE), "heartbeat fields drifted"
        server._heartbeat.update(_FRESH_STATE)
    yield
    with server._heartbeat_lock:
        server._heartbeat.update(saved)


def _clock(monkeypatch, stamps: list[str]):
    """suite_service.utc_now() returns the given stamps in order, then the
    last one forever."""
    remaining = list(stamps)

    def utc_now():
        if len(remaining) > 1:
            return remaining.pop(0)
        return remaining[0]
    monkeypatch.setattr(server.suite_service, "utc_now", utc_now)


def _feeds(monkeypatch, feed_ids: list[int]):
    """Phase 3 (run AM): the tick claims due standing-source polls through
    ``_standing_due_polls`` and runs each through ``_poll_source_for_watch``;
    the capture pass and outbox dispatch are separate, non-polling steps."""
    monkeypatch.setattr(server, "_standing_due_polls",
                        lambda: [{"source_id": fid} for fid in feed_ids])
    monkeypatch.setattr(server, "_standing_capture_pass", lambda: [])
    monkeypatch.setattr(server, "_get_index", lambda: object())
    monkeypatch.setattr(server, "_source_service", lambda: type(
        "S", (), {"dispatch_classification_outbox": staticmethod(lambda: [])})())


def _poll(monkeypatch, fn):
    monkeypatch.setattr(server, "_poll_source_for_watch",
                        lambda claim: fn(claim["source_id"]))


def test_clean_pass_advances_every_success_stamp(monkeypatch):
    _clock(monkeypatch, ["2026-09-04T16:30:00Z"])
    _feeds(monkeypatch, [1])
    _poll(monkeypatch, lambda fid: {"ok": True, "feed_id": fid, "inserted": 0})

    results = server._podcast_feed_scheduler_tick()
    assert results == [{"ok": True, "feed_id": 1, "inserted": 0}]
    hb = server._heartbeat_payload(now="2026-09-04T16:30:04Z")
    assert hb["last_tick_completed_at"] == "2026-09-04T16:30:00Z"
    assert hb["last_successful_tick_at"] == "2026-09-04T16:30:00Z"
    assert server._last_successful_tick_at == "2026-09-04T16:30:00Z"
    assert hb["last_successful_poll_at"] == "2026-09-04T16:30:00Z"
    assert hb["last_failed_poll_at"] is None
    assert hb["last_ingest_completed_at"] is None
    assert hb["last_tick"] == {"ok": True, "polls": 1, "failed_polls": 0}
    assert hb["counts"] == {"ticks": 1, "polls_ok": 1, "polls_failed": 0, "ingests": 0}
    assert hb["freshness"] == {"state": "fresh", "age_sec": 4.0,
                               "stale_after_sec": server._HEARTBEAT_STALE_AFTER_SEC}


def test_failed_poll_does_not_advance_success_stamps(monkeypatch):
    """The exact Astra repro: a forced feed exception returned ok=false yet
    used to set _last_successful_tick_at."""
    _clock(monkeypatch, ["2026-09-04T16:30:00Z"])
    _feeds(monkeypatch, [7])

    def boom(_fid):
        raise RuntimeError("feed exploded: https://user:pw@show.example/feed")
    _poll(monkeypatch, boom)

    results = server._podcast_feed_scheduler_tick()
    assert results[0]["ok"] is False and results[0]["source_id"] == 7
    hb = server._heartbeat_payload(now="2026-09-04T16:30:01Z")
    # The loop completed ...
    assert hb["last_tick_completed_at"] == "2026-09-04T16:30:00Z"
    assert hb["last_tick"] == {"ok": False, "polls": 1, "failed_polls": 1}
    # ... but nothing succeeded.
    assert hb["last_successful_tick_at"] is None
    assert server._last_successful_tick_at is None
    assert hb["last_successful_poll_at"] is None
    assert hb["last_failed_poll_at"] == "2026-09-04T16:30:00Z"
    # Public probe: the failure kind only, never the raw exception text.
    assert hb["last_poll_error"] == "RuntimeError"
    assert "show.example" not in json.dumps(hb)
    assert hb["counts"]["polls_failed"] == 1 and hb["counts"]["polls_ok"] == 0
    assert hb["freshness"]["state"] == "fresh"


def test_ok_false_result_counts_as_failed_poll(monkeypatch):
    _clock(monkeypatch, ["2026-09-04T16:30:00Z"])
    _feeds(monkeypatch, [1, 2])
    _poll(monkeypatch,
          lambda fid: {"ok": fid == 1, "feed_id": fid, "error": None if fid == 1 else "HTTP 500"})
    server._podcast_feed_scheduler_tick()
    hb = server._heartbeat_payload(now="2026-09-04T16:30:00Z")
    assert hb["last_tick"] == {"ok": False, "polls": 2, "failed_polls": 1}
    assert hb["last_successful_poll_at"] == "2026-09-04T16:30:00Z"
    assert hb["last_failed_poll_at"] == "2026-09-04T16:30:00Z"
    assert hb["last_poll_error"] == "poll returned ok=false"
    assert hb["last_successful_tick_at"] is None


def test_mixed_history_keeps_older_success_stamp(monkeypatch):
    _clock(monkeypatch, ["2026-09-04T16:30:00Z", "2026-09-04T16:30:00Z",
                         "2026-09-04T16:30:30Z", "2026-09-04T16:30:30Z"])
    _feeds(monkeypatch, [1])
    outcomes = iter([{"ok": True, "feed_id": 1}, {"ok": False, "feed_id": 1}])
    _poll(monkeypatch, lambda _fid: next(outcomes))
    server._podcast_feed_scheduler_tick()
    server._podcast_feed_scheduler_tick()
    hb = server._heartbeat_payload(now="2026-09-04T16:30:31Z")
    assert hb["last_tick_completed_at"] == "2026-09-04T16:30:30Z"
    assert hb["last_successful_tick_at"] == "2026-09-04T16:30:00Z"
    assert hb["last_successful_poll_at"] == "2026-09-04T16:30:00Z"
    assert hb["last_failed_poll_at"] == "2026-09-04T16:30:30Z"
    assert hb["counts"] == {"ticks": 2, "polls_ok": 1, "polls_failed": 1, "ingests": 0}


def test_freshness_never_then_fresh_then_stale(monkeypatch):
    assert server._heartbeat_payload(now="2026-09-04T16:30:00Z")["freshness"] == {
        "state": "never", "age_sec": None,
        "stale_after_sec": server._HEARTBEAT_STALE_AFTER_SEC}
    _clock(monkeypatch, ["2026-09-04T16:30:00Z"])
    _feeds(monkeypatch, [])
    server._podcast_feed_scheduler_tick()  # zero due feeds is a clean pass
    fresh = server._heartbeat_payload(now="2026-09-04T16:34:59Z")["freshness"]
    assert fresh["state"] == "fresh" and fresh["age_sec"] == 299.0
    stale = server._heartbeat_payload(now="2026-09-04T16:35:01Z")["freshness"]
    assert stale["state"] == "stale" and stale["age_sec"] == 301.0
    # A clock that went backwards never reports a negative age.
    assert server._heartbeat_payload(now="2026-09-04T16:29:00Z")["freshness"]["age_sec"] == 0.0


def test_ingest_completion_is_its_own_stamp(monkeypatch):
    _clock(monkeypatch, ["2026-09-04T16:31:00Z"])
    server._heartbeat_note_ingest()
    hb = server._heartbeat_payload(now="2026-09-04T16:31:00Z")
    assert hb["last_ingest_completed_at"] == "2026-09-04T16:31:00Z"
    assert hb["counts"]["ingests"] == 1
    # An ingest is not a tick and not a poll.
    assert hb["last_tick_completed_at"] is None
    assert hb["last_successful_poll_at"] is None


def test_watch_publish_path_marks_ingest(monkeypatch):
    """Phase 3 (run AM): a standing capture that the capture pass reports as
    succeeded stamps last_ingest_completed_at; a failed capture does not.
    (The pre-Phase-3 publish-from-poll path no longer exists: capture runs
    only after an atomic start reservation, never from detection.)"""
    _clock(monkeypatch, ["2026-09-04T16:32:00Z"])
    outcomes = [{"outcome": "succeeded", "start_id": "st_1", "video_id": "podcast_5"}]

    class Service:
        @staticmethod
        def capture_pass(limit=1):
            return list(outcomes)
    monkeypatch.setattr(server, "_source_service", lambda: Service())
    assert server._standing_capture_pass()[0]["video_id"] == "podcast_5"
    assert server._heartbeat_payload()["last_ingest_completed_at"] == "2026-09-04T16:32:00Z"

    outcomes[:] = [{"outcome": "failed", "start_id": "st_2", "code": "download_failed"}]
    _clock(monkeypatch, ["2026-09-04T16:33:00Z"])
    assert server._standing_capture_pass()[0]["outcome"] == "failed"
    assert server._heartbeat_payload()["last_ingest_completed_at"] == "2026-09-04T16:32:00Z"
    assert server._heartbeat_payload()["counts"]["ingests"] == 1


def test_health_exposes_heartbeat_block(monkeypatch):
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server.whisper_runner, "is_whisperx_available", lambda: False)
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda *_a: False)
    monkeypatch.setattr(server, "_path_integrity_status",
                        lambda: {"ok": True, "checked": 0, "missing": 0})
    _clock(monkeypatch, ["2026-09-04T16:30:00Z"])
    _feeds(monkeypatch, [])
    server._podcast_feed_scheduler_tick()

    class Probe:
        path = "/health"
        client_address = ("127.0.0.1", 1)

        @staticmethod
        def _reject_bad_host() -> bool:
            return False

        def _send_json(self, status, payload):
            self.status, self.payload = status, payload

    probe = Probe()
    server.Handler.do_GET(probe)
    assert probe.status == 200
    hb = probe.payload["heartbeat"]
    assert probe.payload["last_successful_tick_at"] == hb["last_successful_tick_at"] == "2026-09-04T16:30:00Z"
    assert set(hb) == {
        "last_tick_completed_at", "last_successful_tick_at",
        "last_successful_poll_at", "last_failed_poll_at", "last_poll_error",
        "last_ingest_completed_at", "last_tick", "counts",
        "tick_interval_sec", "freshness"}
    assert hb["tick_interval_sec"] == server._PODCAST_FEED_TICK_SEC


def _doctor_with_health(monkeypatch, health: dict):
    monkeypatch.setattr(server, "_diagnose_payload", lambda: {"ok": True})
    monkeypatch.setattr(server.migrate_install, "migration_status", lambda: {})
    monkeypatch.setattr(server, "_mcp_stdio_selfcheck", lambda: {"ok": True})
    monkeypatch.setattr(server, "_path_integrity_status", lambda force=False: {"ok": True})
    monkeypatch.setattr(server, "_podcast_corpus_reconciliation_status", lambda: {"ok": True})
    monkeypatch.setattr(server.index, "schema_migration_status",
                        lambda _path: {"current": 26, "latest": 26, "pending": False})
    monkeypatch.setattr(server, "_helper_health_status", lambda: health)
    return server.doctor_payload()


def test_doctor_reads_the_same_heartbeat_fields_and_fails_on_stale(monkeypatch):
    fresh_block = {"last_tick_completed_at": "2026-09-04T16:30:00Z",
                   "freshness": {"state": "fresh", "age_sec": 3.0, "stale_after_sec": 300}}
    doctor = _doctor_with_health(monkeypatch, {
        "ok": True, "url": "http://127.0.0.1:5179/health", "status": 200,
        "payload": {"ok": True, "heartbeat": fresh_block}})
    assert doctor["ok"] is True
    assert doctor["heartbeat"]["available"] is True
    assert doctor["heartbeat"]["stale"] is False
    assert doctor["heartbeat"]["last_tick_completed_at"] == "2026-09-04T16:30:00Z"
    assert doctor["heartbeat"]["freshness"] == fresh_block["freshness"]

    stale_block = {**fresh_block,
                   "freshness": {"state": "stale", "age_sec": 1200.0, "stale_after_sec": 300}}
    doctor = _doctor_with_health(monkeypatch, {
        "ok": True, "url": "http://127.0.0.1:5179/health", "status": 200,
        "payload": {"ok": True, "heartbeat": stale_block}})
    assert doctor["ok"] is False
    assert doctor["heartbeat"]["stale"] is True

    # A helper that did not answer, or predates the block: no heartbeat,
    # and the doctor's verdict comes from the other checks alone.
    doctor = _doctor_with_health(monkeypatch, {"ok": True})
    assert doctor["ok"] is True
    assert doctor["heartbeat"] == {"available": False, "stale": False}


def test_docs_describe_the_heartbeat_fields():
    for rel in ("README_server.md", "docs/v2-api.md"):
        text = (server.HERE / rel).read_text(encoding="utf-8")
        for field in ("last_tick_completed_at", "last_successful_poll_at",
                      "last_ingest_completed_at", "freshness"):
            assert field in text, f"{rel} lacks {field}"
        assert "never advances" in text, rel
