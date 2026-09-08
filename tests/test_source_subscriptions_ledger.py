"""Phase 3 ledger gates: S04 (durable off/on/off), S05 (in-flight revocation
race), S10 (atomic daily allowance), S11 (failure/retry accounting), S12 (UTC
boundary and clock), S13 (restart reservation), S14 (queue atomicity and
fencing), S15 (cross-source deduplication).
Contract: docs/library/PHASE3-CONTRACT-2026-09-07.md, "Atomic starts, failure,
and restart".

Run: python -m pytest -q tests/test_source_subscriptions_ledger.py
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    CHANNEL_URL, Clock, DAY_MS, FEED_URL, FakeAdapter, FakeBackend, MINUTE_MS, PLAYLIST_URL,
    REGISTRY, T0, items, make_service, open_index, register, rows, snapshot, starts, status,
    turn_off, turn_on, vid,
)

import source_subscriptions as ss  # noqa: E402

MIDNIGHT = ss.next_utc_midnight_ms(T0)


def _source_row(service, sid):
    return rows(service, "SELECT * FROM source_subscriptions WHERE source_id=?", (sid,))[0]


def _reset_interval(idx, sid):
    with idx.write_transaction() as conn:
        conn.execute("UPDATE source_subscriptions SET capture_not_before_ms=0 WHERE source_id=?", (sid,))


def _ready_source(tmp_path, n_items=5, *, backend=None, clock=None, kind="youtube_channel",
                  url=CHANNEL_URL):
    idx = open_index(tmp_path)
    clock = clock or Clock()
    adapter = FakeAdapter([snapshot([vid(i) for i in range(1, n_items + 1)], coverage="window")])
    backend = backend or FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    sid = register(service, kind, url)["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    return idx, service, clock, adapter, backend, sid


# ---- S04 durable off/on/off ---------------------------------------------------
def test_s04_consent_and_reservations_survive_restart_and_off_releases(tmp_path):
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 3)
    on_receipt = rows(service, "SELECT * FROM source_consent_receipts")[0]
    idx.close()

    # Restart 1: receipts and consent persist; reconciliation changes nothing.
    idx = open_index(tmp_path)
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    assert service.reconcile_on_startup() == {"released": 0, "leases_expired": 0, "succeeded": 0,
                                              "failed": 0, "uncertain": 0, "outbox_repaired": 0}
    source = _source_row(service, sid)
    assert source["consent_state"] == "on" and source["consent_epoch"] == 1
    assert source["initial_enrollment_completed_ms"] is not None
    assert rows(service, "SELECT * FROM source_consent_receipts")[0] == on_receipt
    claim = service.claim_start(sid)
    assert claim["outcome"] == "reserved"
    old_token = claim["owner_token"]
    # Duplicate on: no-change receipt, no second enrollment, cohort untouched.
    again = turn_on(service, sid, operation_key="on-dup")
    assert again["changed"] is False and again["consent_epoch"] == 1
    assert status(service, sid)["source"]["enrollment"]["enrolled"] == 3
    # Off: the unstarted reservation releases in the same transaction.
    off = turn_off(service, sid)
    assert off["released_reservations"] == 1 and off["in_flight"] == []
    assert off["consent_epoch"] == 1 and off["after_revision"] == 2, "same-state receipt did not bump"
    ledger = starts(service, sid)
    assert ledger[0]["state"] == "released" and ledger[0]["release_or_failure_code"] == "consent_off"
    assert ledger[0]["started_at_ms"] is None
    # No old-epoch dispatch: the released row cannot start, and a fresh claim is refused.
    assert service.mark_started(claim["start_id"], old_token)["outcome"] == "not_reserved"
    assert service.claim_start(sid)["outcome"] == "consent_off"
    assert backend.runs == []
    idx.close()

    # Restart 2: still off, receipts intact, nothing dispatches.
    idx = open_index(tmp_path)
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    service.reconcile_on_startup()
    assert _source_row(service, sid)["consent_state"] == "off"
    assert [r["new_state"] for r in rows(service, "SELECT new_state FROM source_consent_receipts "
                                                  "ORDER BY created_at_ms")] == ["on", "on", "off"]
    assert service.capture_pass() == [] and backend.runs == []
    # On again: resume boundary, epoch 2; the old reservation stays released.
    on2 = turn_on(service, sid, operation_key="on-2")
    assert on2["boundary"] == "resume" and on2["consent_epoch"] == 2
    assert starts(service, sid)[0]["state"] == "released"
    idx.close()


# ---- S05 in-flight revocation race ---------------------------------------------
def test_s05_off_before_start_wins_zero_dispatch(tmp_path):
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 2)
    claim = service.claim_start(sid)
    assert claim["outcome"] == "reserved"
    # Pause immediately before the started transaction: off runs on a second
    # connection and commits first.
    other = make_service(path=tmp_path / "index.db", clock=clock, backend=backend, instance_id="b")
    off = turn_off(other, sid)
    assert off["released_reservations"] == 1
    started = service.mark_started(claim["start_id"], claim["owner_token"])
    assert started["outcome"] == "not_reserved"
    assert backend.runs == []
    assert status(service, sid)["source"]["allowance"]["charged"] == 0
    other.close()
    idx.close()


def test_s05_start_before_off_completes_visibly_and_cannot_retry_while_off(tmp_path):
    clock = Clock()
    outcomes = iter([ss.CaptureOutcome("failed", code="download_failed")])
    backend = FakeBackend(outcome=lambda *_: next(outcomes))
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 2, backend=backend, clock=clock)
    claim = service.claim_start(sid)
    started = service.mark_started(claim["start_id"], claim["owner_token"])
    assert started["outcome"] == "started"
    # Pause after the started transaction: off on a second connection.
    other = make_service(path=tmp_path / "index.db", clock=clock, backend=backend, instance_id="b")
    off = turn_off(other, sid)
    assert off["released_reservations"] == 0
    assert off["in_flight"] == [{"start_id": claim["start_id"], "item_id": claim["item_id"], "state": "started"}]
    summary = status(service, sid)["source"]
    assert summary["consent_state"] == "off" and summary["allowance"]["charged"] == 1
    assert summary["in_flight"][0]["state"] == "started"
    # The started pipeline may finish and publish while off.
    done = service.complete_capture(claim["start_id"], claim["owner_token"], vid(1))
    assert done["outcome"] == "succeeded"
    committed = next(i for i in status(service, sid)["items"] if i["item_id"] == claim["item_id"])
    assert committed["capture_state"] == "committed"
    # A second started pipeline fails while off: it cannot launch another attempt.
    turn_on(other, sid, operation_key="on-2")
    _reset_interval(idx, sid)
    clock.advance(61 * MINUTE_MS)
    assert service.detection_pass()[0]["enrollment"]["boundary"] == "resume"
    claim2 = service.claim_start(sid)
    assert claim2["outcome"] == "reserved"
    service.mark_started(claim2["start_id"], claim2["owner_token"])
    turn_off(other, sid, operation_key="off-2")
    failed = service.fail_capture(claim2["start_id"], claim2["owner_token"], "download_failed")
    assert failed["outcome"] == "failed" and failed["retry_at_ms"] == clock.now + 15 * MINUTE_MS
    clock.advance(20 * MINUTE_MS)
    _reset_interval(idx, sid)
    assert service.claim_start(sid)["outcome"] == "consent_off"
    assert service.capture_pass() == []
    assert status(service, sid)["source"]["allowance"]["charged"] == 2
    other.close()
    idx.close()


# ---- S10 atomic daily allowance --------------------------------------------------
def test_s10_two_schedulers_race_the_tenth_slot(tmp_path):
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 25)
    # Nine charged starts (some failed) for today.
    for n in range(9):
        _reset_interval(idx, sid)
        claim = service.claim_start(sid)
        assert claim["outcome"] == "reserved", claim
        service.mark_started(claim["start_id"], claim["owner_token"])
        if n % 3 == 0:
            service.fail_capture(claim["start_id"], claim["owner_token"], "download_failed")
        else:
            service.complete_capture(claim["start_id"], claim["owner_token"], claim["item_id"])
    allowance = status(service, sid)["source"]["allowance"]
    assert allowance["charged"] == 9 and allowance["reserved"] == 0 and allowance["remaining"] == 1
    _reset_interval(idx, sid)
    other = make_service(path=tmp_path / "index.db", clock=clock, backend=backend, instance_id="b")
    barrier = threading.Barrier(2)
    results: dict = {}

    def race(name, svc):
        barrier.wait()
        results[name] = svc.claim_start(sid)

    threads = [threading.Thread(target=race, args=("a", service)),
               threading.Thread(target=race, args=("b", other))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    outcomes = sorted(r["outcome"] for r in results.values())
    assert outcomes == ["in_flight", "reserved"] or outcomes == ["allowance_exhausted", "reserved"], results
    ledger = starts(service, sid)
    assert len([r for r in ledger if r["state"] != "released"]) == 10
    assert len({r["slot"] for r in ledger if r["state"] != "released"}) == 10
    winner = next(r for r in results.values() if r["outcome"] == "reserved")
    service_for = service if results["a"]["outcome"] == "reserved" else other
    assert service_for.mark_started(winner["start_id"], winner["owner_token"])["outcome"] == "started"
    allowance = status(service, sid)["source"]["allowance"]
    assert allowance["charged"] == 10 and allowance["remaining"] == 0
    service_for.complete_capture(winner["start_id"], winner["owner_token"], winner["item_id"])
    _reset_interval(idx, sid)
    assert service.claim_start(sid)["outcome"] == "allowance_exhausted"
    assert other.claim_start(sid)["outcome"] == "allowance_exhausted"
    # A second source keeps its own allowance.
    sid2 = register(service, "youtube_playlist", PLAYLIST_URL)["source_id"]
    turn_on(service, sid2)
    adapter.results = [snapshot([vid(100), vid(101)], coverage="window")]
    service.detection_pass()
    assert status(service, sid2)["source"]["allowance"]["remaining"] == 10
    assert service.claim_start(sid2)["outcome"] == "reserved"
    other.close()
    idx.close()


def test_s10_from_zero_through_exhaustion_counts_never_exceed_ten(tmp_path):
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 25)
    for n in range(10):
        _reset_interval(idx, sid)
        claim = service.claim_start(sid)
        assert claim["outcome"] == "reserved"
        allowance = status(service, sid)["source"]["allowance"]
        assert allowance["reserved"] + allowance["charged"] == n + 1 <= 10
        assert service.mark_started(claim["start_id"], claim["owner_token"])["outcome"] == "started"
        if n % 2:
            service.fail_capture(claim["start_id"], claim["owner_token"], "download_failed")
        else:
            service.complete_capture(claim["start_id"], claim["owner_token"], claim["item_id"])
    _reset_interval(idx, sid)
    assert service.claim_start(sid)["outcome"] == "allowance_exhausted"
    allowance = status(service, sid)["source"]["allowance"]
    assert allowance == {**allowance, "cap": 10, "charged": 10, "reserved": 0, "remaining": 0,
                         "utc_day": ss.utc_day(T0), "resets_at_ms": MIDNIGHT}
    assert len({r["slot"] for r in starts(service, sid)}) == 10
    # Preflight rejections while exhausted use no slot either.
    backend.preflight_outcome = ss.CaptureOutcome("preflight_failed", code="x")
    assert service.advance_source(sid)["outcome"] == "allowance_exhausted"
    idx.close()


# ---- S11 failure/retry accounting -------------------------------------------------
def test_s11_preflight_releases_capacity_and_actual_failures_keep_their_slot(tmp_path):
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 2)
    backend.preflight_outcome = ss.CaptureOutcome("preflight_failed", code="missing_transcription_setup")
    for n in range(3):
        _reset_interval(idx, sid)
        result = service.advance_source(sid)
        assert result["outcome"] == "released" and result["code"] == "preflight:missing_transcription_setup"
    assert status(service, sid)["source"]["allowance"]["charged"] == 0
    assert all(r["state"] == "released" for r in starts(service, sid))
    blocked = [r for r in items(service, sid) if r["preflight_failures"] == 3]
    assert len(blocked) == 1 and blocked[0]["blocked_reason"] == "preflight:missing_transcription_setup"
    assert blocked[0]["actual_starts"] == 0
    # Three consecutive preflight failures block that item until metadata changes.
    _reset_interval(idx, sid)
    other_item = service.advance_source(sid)
    assert other_item["outcome"] == "released" and other_item["item_id"] != blocked[0]["item_id"]
    backend.preflight_outcome = None
    adapter.results = [snapshot([vid(1), vid(2)], coverage="window",
                                titles={blocked[0]["entry_id"]: "renamed"})]
    clock.advance(61 * MINUTE_MS)
    service.detection_pass()
    assert {r["entry_id"]: r["preflight_failures"] for r in items(service, sid)}[blocked[0]["entry_id"]] == 0

    # Actual failures keep the slot; a retry is a new charged row on a new slot.
    backend.outcome = ss.CaptureOutcome("failed", code="download_failed")
    _reset_interval(idx, sid)
    first = service.advance_source(sid)
    assert first["outcome"] == "failed" and first["attempts"] == 1
    assert first["retry_at_ms"] == clock.now + 15 * MINUTE_MS
    assert status(service, sid)["source"]["allowance"]["charged"] == 1
    _reset_interval(idx, sid)
    assert service.claim_start(sid, item_id=first["item_id"])["outcome"] == "idle", "backoff respected"
    clock.advance(15 * MINUTE_MS)
    _reset_interval(idx, sid)
    second = service.advance_source(sid, item_id=first["item_id"])
    assert second["outcome"] == "failed" and second["attempts"] == 2
    assert second["retry_at_ms"] == clock.now + 60 * MINUTE_MS
    clock.advance(60 * MINUTE_MS)
    _reset_interval(idx, sid)
    third = service.advance_source(sid, item_id=first["item_id"])
    assert third["outcome"] == "failed" and third["attempts"] == 3 and third["retry_at_ms"] is None
    item = next(r for r in items(service, sid) if r["item_id"] == first["item_id"])
    assert item["state"] == "failed" and item["blocked_reason"] == "attempts_exhausted"
    charged = [r for r in starts(service, sid) if r["started_at_ms"] is not None]
    assert len(charged) == 3 and len({r["slot"] for r in charged}) == 3
    assert all(r["state"] == "failed" for r in charged)
    # Off/on never clears actual attempt counts; nothing bypasses them.
    turn_off(service, sid)
    turn_on(service, sid, operation_key="on-2")
    service.detection_pass()
    clock.advance(DAY_MS)
    _reset_interval(idx, sid)
    assert service.claim_start(sid, item_id=first["item_id"])["outcome"] == "idle"
    assert next(r for r in items(service, sid) if r["item_id"] == first["item_id"])["actual_starts"] == 3
    # Terminal errors block immediately and stay visible.
    backend.outcome = ss.CaptureOutcome("failed", code="unsupported_item", terminal=True)
    _reset_interval(idx, sid)
    terminal = service.advance_source(sid)
    assert terminal["outcome"] == "failed" and terminal["terminal"] is True
    record = next(i for i in status(service, sid)["items"] if i["item_id"] == terminal["item_id"])
    assert record["capture_state"] == "failed" and record["blocked_reason"] == "unsupported_item"
    assert record["actual_attempts"] == 1 and record["charged_utc_day"] == ss.utc_day(clock.now)
    idx.close()


# ---- S12 UTC boundary and clock -------------------------------------------------
def test_s12_reservation_before_midnight_cannot_start_after_it(tmp_path):
    clock = Clock(MIDNIGHT - 1000)  # 23:59:59
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 3, clock=clock)
    claim = service.claim_start(sid)
    assert claim["outcome"] == "reserved" and claim["utc_day"] == ss.utc_day(MIDNIGHT - 1000)
    clock.now = MIDNIGHT + 1000  # 00:00:01
    rolled = service.mark_started(claim["start_id"], claim["owner_token"])
    assert rolled["outcome"] == "day_rollover"
    assert starts(service, sid)[0]["state"] == "released"
    assert starts(service, sid)[0]["release_or_failure_code"] == "day_rollover"
    fresh = service.claim_start(sid)
    assert fresh["outcome"] == "reserved" and fresh["utc_day"] == ss.utc_day(MIDNIGHT + 1000)
    assert service.mark_started(fresh["start_id"], fresh["owner_token"])["outcome"] == "started"
    yesterday = status(service, sid)["source"]["allowance"]
    assert yesterday["utc_day"] == ss.utc_day(MIDNIGHT + 1000) and yesterday["charged"] == 1
    # advance_source does the same rollover in one pass.
    _reset_interval(idx, sid)
    service.complete_capture(fresh["start_id"], fresh["owner_token"], vid(1))
    clock.now = MIDNIGHT + DAY_MS - 1000
    claim2 = service.claim_start(sid)
    clock.now = MIDNIGHT + DAY_MS + 1000
    # The stale reservation is released by reconciliation and re-claimed today.
    outcome = service.advance_source(sid)
    assert outcome["outcome"] in ("in_flight", "succeeded", "day_rollover", "released")
    assert all(r["utc_day"] == ss.utc_day(r["reserved_at_ms"]) for r in starts(service, sid))
    idx.close()


def test_s12_started_work_crosses_midnight_once_and_retry_charges_new_day(tmp_path):
    clock = Clock(MIDNIGHT - 5 * MINUTE_MS)
    backend = FakeBackend(outcome=ss.CaptureOutcome("in_flight"))
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 3, clock=clock, backend=backend)
    started = service.advance_source(sid)
    assert started["outcome"] == "in_flight"
    start_id = backend.runs[0]["start_id"]
    token = backend.runs[0]["owner_token"]
    clock.now = MIDNIGHT + 5 * MINUTE_MS
    assert service.complete_capture(start_id, token, vid(1))["outcome"] == "succeeded"
    row = starts(service, sid)[0]
    assert row["utc_day"] == ss.utc_day(MIDNIGHT - 5 * MINUTE_MS) and row["state"] == "succeeded"
    today = status(service, sid)["source"]["allowance"]
    assert today["charged"] == 0, "yesterday's start is not charged again today"
    # A failed retry started today charges today.
    backend.outcome = ss.CaptureOutcome("failed", code="download_failed")
    _reset_interval(idx, sid)
    failed = service.advance_source(sid)
    assert failed["outcome"] == "failed"
    assert starts(service, sid)[-1]["utc_day"] == ss.utc_day(clock.now)
    assert status(service, sid)["source"]["allowance"]["charged"] == 1
    idx.close()


def test_s12_backwards_clock_cannot_reset_allowance_or_move_due_times(tmp_path):
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 3)
    assert service.advance_source(sid)["outcome"] == "succeeded"
    due_before = rows(service, "SELECT next_poll_at_ms FROM source_detection_cursors WHERE source_id=?",
                      (sid,))[0]["next_poll_at_ms"]
    clock.now = T0 - DAY_MS  # host clock jumps back a day (DST/misconfiguration)
    assert service.claim_start(sid)["outcome"] == "clock_regressed"
    assert service.capture_pass() == [] and len(backend.runs) == 1
    assert service.detection_pass() == []
    summary = status(service, sid)["source"]
    assert summary["allowance"]["hold_reason"] == "clock_regressed"
    assert summary["capture_status"] == "clock_regressed"
    assert rows(service, "SELECT next_poll_at_ms, last_error_code FROM source_detection_cursors "
                         "WHERE source_id=?", (sid,))[0]["next_poll_at_ms"] == due_before
    assert _source_row(service, sid)["last_observed_ms"] == T0
    # Once the clock catches up, work resumes without any refund or reset.
    clock.now = T0 + 61 * MINUTE_MS
    assert status(service, sid)["source"]["allowance"]["charged"] == 1
    assert service.advance_source(sid)["outcome"] == "succeeded"
    idx.close()


# ---- S13 restart reservation ---------------------------------------------------------
def test_s13_restart_after_reserve_after_start_and_during_execution(tmp_path):
    backend = FakeBackend(outcome=ss.CaptureOutcome("in_flight"), probe="unknown")
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 4, backend=backend)
    # (a) terminate after the reserve commit, before dispatch.
    reserved = service.claim_start(sid)
    idx.close()
    idx = open_index(tmp_path)
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    report = service.reconcile_on_startup()
    assert report["released"] == 0, "a valid unstarted row may be claimed once within its expiry"
    resumed = service.mark_started(reserved["start_id"], reserved["owner_token"])
    assert resumed["outcome"] == "started"
    # (b) terminate after the started commit, before backend acknowledgment.
    idx.close()
    idx = open_index(tmp_path)
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    report = service.reconcile_on_startup()
    assert report["uncertain"] == 1 and report["failed"] == 0 and report["succeeded"] == 0
    row = starts(service, sid)[0]
    assert row["state"] == "uncertain" and row["started_at_ms"] is not None
    assert status(service, sid)["source"]["allowance"]["charged"] == 1
    # An unknown owner blocks the source: no duplicate dispatch, no refund.
    _reset_interval(idx, sid)
    assert service.claim_start(sid)["outcome"] == "in_flight"
    assert service.capture_pass() == []
    # Lease expiry alone never proves death.
    clock.advance(DAY_MS)
    assert service.reconcile_on_startup()["uncertain"] == 1
    assert starts(service, sid)[0]["state"] == "uncertain"
    # Proof the worker stopped -> failed, charge retained, item retry-eligible.
    backend.probe_result = "stopped"
    assert service.reconcile_on_startup()["failed"] == 1
    row = starts(service, sid)[0]
    assert row["state"] == "failed" and row["release_or_failure_code"] == "worker_lost"
    item = next(i for i in items(service, sid) if i["item_id"] == row["item_id"])
    assert item["actual_starts"] == 1 and item["state"] == "eligible"
    # (c) terminate during execution; committed artifacts complete the row once.
    _reset_interval(idx, sid)
    clock.advance(DAY_MS)
    second = service.advance_source(sid)
    assert second["outcome"] == "in_flight"
    start_id = backend.runs[-1]["start_id"]
    running_entry = next(i["entry_id"] for i in items(service, sid)
                         if i["item_id"] == backend.runs[-1]["item_id"])
    idx.upsert_yoink(dict(video_id=running_entry, slug="s", title="t", topic="x", yoinked_at="2026",
                          corpus_path="", sidecar_path=""))
    idx.close()
    idx = open_index(tmp_path)
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    report = service.reconcile_on_startup()
    assert report["succeeded"] == 1 and report["outbox_repaired"] == 0
    row = next(r for r in starts(service, sid) if r["start_id"] == start_id)
    assert row["state"] == "succeeded"
    assert rows(service, "SELECT state FROM source_classification_outbox")[0]["state"] == "pending"
    assert service.reconcile_on_startup()["succeeded"] == 0
    idx.close()


# ---- S14 queue atomicity and fencing -----------------------------------------------
def test_s14_backend_binding_is_atomic_and_stale_owners_are_fenced(tmp_path):
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 3)
    backend.outcome = ss.CaptureOutcome("in_flight")
    first = service.advance_source(sid)
    assert first["outcome"] == "in_flight"
    row = starts(service, sid)[0]
    assert row["backend_kind"] == "fake" and row["backend_id"] == "job-" + row["start_id"]
    assert backend.binds == [row["start_id"]]
    token = backend.runs[0]["owner_token"]
    # Replaying the same start id creates no second binding or launch.
    assert service.mark_started(row["start_id"], token)["outcome"] == "not_reserved"
    assert len(backend.runs) == 1 and len(backend.binds) == 1
    # An obsolete callback (wrong token) cannot publish, fail or mutate.
    for stale in ("x" * 43, backend.runs[0]["owner_token"][::-1]):
        assert service.complete_capture(row["start_id"], stale, vid(1))["outcome"] == "not_owner"
        assert service.fail_capture(row["start_id"], stale, "boom")["outcome"] == "not_owner"
        assert service.mark_uncertain(row["start_id"], stale)["outcome"] == "not_owner"
    assert starts(service, sid)[0]["state"] == "started"
    # A callback for a different attempt cannot mutate this one.
    assert service.complete_capture("st_missing", token, vid(1))["outcome"] == "not_owner"
    # The owner completes exactly once; a second completion is idempotent.
    assert service.complete_capture(row["start_id"], token, vid(1))["outcome"] == "succeeded"
    assert service.complete_capture(row["start_id"], token, vid(1))["idempotent"] is True
    assert service.complete_capture(row["start_id"], token, vid(2))["outcome"] == "not_started"
    assert service.fail_capture(row["start_id"], token, "late")["outcome"] == "not_started"
    # A failed bind leaves no orphan launch and no binding.
    backend.bind_fail = True
    _reset_interval(idx, sid)
    with pytest.raises(RuntimeError):
        service.advance_source(sid)
    assert len(backend.runs) == 1 and len(backend.binds) == 1
    assert sorted(r["state"] for r in starts(service, sid)) == ["reserved", "succeeded"]
    idx.close()


# ---- S15 cross-source deduplication ----------------------------------------------------
def test_s15_same_video_in_channel_and_playlists_charges_only_the_winner(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    shared = vid(7)
    adapter = FakeAdapter([snapshot([shared, vid(8)], coverage="window")])
    backend = FakeBackend(outcome=ss.CaptureOutcome("in_flight"))
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    channel = register(service, "youtube_channel", CHANNEL_URL)["source_id"]
    playlist_a = register(service, "youtube_playlist", PLAYLIST_URL)["source_id"]
    playlist_b = register(service, "youtube_playlist", "https://www.youtube.com/playlist?list=PL" + "c" * 20)["source_id"]
    for sid in (channel, playlist_a, playlist_b):
        turn_on(service, sid)
    service.detection_pass()
    keys = {r["capture_key"] for r in rows(service, "SELECT capture_key FROM source_items WHERE entry_id=?", (shared,))}
    assert keys == {f"youtube:{shared}"}
    # Channel wins the start; both playlists keep the observation eligible.
    winner = service.advance_source(channel)
    assert winner["outcome"] == "in_flight"
    other = make_service(path=tmp_path / "index.db", clock=clock, backend=backend, instance_id="b")
    blocked = other.claim_start(playlist_a, item_id=ss.item_identity(playlist_a, shared))
    assert blocked["outcome"] == "capture_in_progress_elsewhere" and blocked["owner_source_id"] == channel
    assert service.claim_start(playlist_b, item_id=ss.item_identity(playlist_b, shared))["outcome"] == \
        "capture_in_progress_elsewhere"
    item_a = next(i for i in items(service, playlist_a) if i["entry_id"] == shared)
    assert item_a["state"] == "eligible" and item_a["blocked_reason"] == "capture_in_progress_elsewhere"
    assert status(service, playlist_a)["source"]["allowance"]["charged"] == 0
    # Commit: every matching observation links; only the channel is charged.
    start = backend.runs[0]
    assert service.complete_capture(start["start_id"], start["owner_token"], shared)["outcome"] == "succeeded"
    for sid in (channel, playlist_a, playlist_b):
        record = next(i for i in items(service, sid) if i["entry_id"] == shared)
        assert record["state"] == "committed" and record["video_id"] == shared
    assert [r["source_id"] for r in starts(service) if r["started_at_ms"]] == [channel]
    assert status(service, playlist_a)["source"]["allowance"]["charged"] == 0
    assert rows(service, "SELECT COUNT(*) AS n FROM source_classification_outbox")[0]["n"] == 1
    # Removal and re-addition never creates a new capture identity or start.
    service.archive_source(REGISTRY.__class__(authenticated=True, operator=True), {"source_id": playlist_a})
    readded = service.register_source(REGISTRY, {"kind": "youtube_playlist", "url": PLAYLIST_URL})
    assert readded["created"] is False and readded["source"]["source_id"] == playlist_a
    turn_on(service, playlist_a, operation_key="on-again")
    clock.advance(61 * MINUTE_MS)
    service.detection_pass()
    assert status(service, playlist_a)["source"]["boundary"] == "none"
    _reset_interval(idx, playlist_a)
    assert service.claim_start(playlist_a, item_id=ss.item_identity(playlist_a, shared))["outcome"] == "idle"
    # Deleted committed item is never resurrected by rediscovery.
    service.note_corpus_deleted([shared])
    clock.advance(61 * MINUTE_MS)
    service.detection_pass()
    for sid in (channel, playlist_a, playlist_b):
        record = next(i for i in items(service, sid) if i["entry_id"] == shared)
        assert record["state"] == "deleted"
        assert service.claim_start(sid, item_id=record["item_id"])["outcome"] == "idle"
    # A source seeing the deleted video for the first time links the tombstone.
    late = register(service, "youtube_playlist", "https://www.youtube.com/playlist?list=PL" + "d" * 20)["source_id"]
    service.detection_pass()
    assert next(i for i in items(service, late) if i["entry_id"] == shared)["state"] == "deleted"
    other.close()
    idx.close()


def test_s15_manual_capture_links_without_a_standing_charge(tmp_path):
    idx, service, clock, adapter, backend, sid = _ready_source(tmp_path, 2)
    # Pre-existing manual capture of vid(1): linked before any reservation.
    idx.upsert_yoink(dict(video_id=vid(1), slug="s", title="t", topic="x", yoinked_at="2026",
                          corpus_path="", sidecar_path=""))
    outcome = service.advance_source(sid)
    assert outcome["outcome"] == "linked" and outcome["video_id"] == vid(1)
    assert starts(service, sid) == [] and backend.runs == []
    record = next(i for i in status(service, sid)["items"] if i["entry_id"] == vid(1))
    assert record["capture_state"] == "committed"
    assert record["classification"] == {"state": "not_requested", "work_id": None}
    # A manual capture that completes concurrently (backend reports it) links too.
    backend.published[vid(2)] = vid(2)
    _reset_interval(idx, sid)
    outcome = service.advance_source(sid)
    assert outcome["outcome"] == "linked" and outcome["video_id"] == vid(2)
    assert status(service, sid)["source"]["allowance"]["charged"] == 0
    assert rows(service, "SELECT COUNT(*) AS n FROM source_classification_outbox")[0]["n"] == 0
    idx.close()
