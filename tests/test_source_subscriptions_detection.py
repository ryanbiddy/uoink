"""Phase 3 detection gates: S03 (initial cohort), S06 (resume gap), S07
(durable independent detection), S08 (poll failure and coverage), S09
(due-time concurrency). Contract: docs/library/PHASE3-CONTRACT-2026-09-07.md.

Run: python -m pytest -q tests/test_source_subscriptions_detection.py
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    CHANNEL_ID, Clock, DAY_MS, FEED_URL, FakeAdapter, FakeBackend, FakeFetch, MINUTE_MS,
    PLAYLIST_URL, REGISTRY, T0, atom_feed, error, http, items, make_service, not_modified,
    open_index, publish, register, rows, rss_feed, snapshot, starts, status, turn_off, turn_on,
    vid,
)

import source_subscriptions as ss  # noqa: E402


def _cursor(service, sid):
    return rows(service, "SELECT * FROM source_detection_cursors WHERE source_id=?", (sid,))[0]


def _eligible(service, sid):
    return sorted(r["entry_id"] for r in items(service, sid) if r["state"] == "eligible")


# ---- S03 initial cohort -----------------------------------------------------
def test_s03_initial_cohort_is_deterministic_capped_and_never_refilled(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    ids = [vid(n) for n in range(80)]
    published = {}
    for n, entry in enumerate(ids):
        if n % 10 == 3:
            published[entry] = None            # invalid/missing date sorts last
        elif n % 10 == 4:
            published[entry] = T0 - 5 * DAY_MS  # ties broken by first-seen then entry id
        else:
            published[entry] = T0 - n * 3_600_000
    # Two polls while off build known metadata; then a limited window at opt-in.
    adapter = FakeAdapter([snapshot(ids[:60], published=published, coverage="complete"),
                           snapshot(ids[40:80], published=published, coverage="complete"),
                           snapshot(ids[70:80] + [vid(500)], published=published, coverage="window")])
    backend = FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    sid = register(service)["source_id"]
    # Precommitted and deleted items are excluded from the cohort. Run AT
    # (AS-01): only a complete manual publication links as committed; a
    # soft-deleted row is a tombstone whatever its completeness.
    publish(idx, vid(0), backend=backend)
    idx.upsert_yoink(dict(video_id=vid(1), slug="s1", title="t", topic="x", yoinked_at="2026",
                          corpus_path="", sidecar_path=""))
    idx.soft_delete_yoink(vid(1))
    service.detection_pass()
    clock.advance(61 * MINUTE_MS)
    service.detection_pass()
    known = items(service, sid)
    assert len(known) == 80 and all(r["eligibility"] == "none" for r in known)
    assert {r["entry_id"]: r["state"] for r in known}[vid(0)] == "committed"
    assert {r["entry_id"]: r["state"] for r in known}[vid(1)] == "deleted"
    assert status(service, sid)["source"]["enrollment"] == {
        "cap": 25, "enrolled": 0, "initial_completed": False, "known_candidates": 78,
        "pending": False, "remaining_initial_slots": 25, "coverage": "complete",
        "initial_completed_ms": None}

    turn_on(service, sid)
    pending = status(service, sid)["source"]["enrollment"]
    assert pending["pending"] is True and pending["remaining_initial_slots"] == 25
    assert status(service, sid)["source"]["capture_status"] == "enrollment_pending"
    assert service.claim_start(sid)["outcome"] == "enrollment_pending"
    clock.advance(61 * MINUTE_MS)
    result = service.detection_pass()[0]
    assert result["enrollment"]["boundary"] == "initial" and result["enrollment"]["enrolled"] == 25
    assert adapter.calls[-1]["conditional"] is False, "no conditional headers while a boundary is pending"

    candidates = [r for r in known if r["state"] == "observed"] + [
        r for r in items(service, sid) if r["entry_id"] == vid(500)]
    expected = sorted(candidates, key=ss._published_sort_key)[:25]
    cohort = [r for r in items(service, sid) if r["eligibility"] == "back_catalog"]
    assert sorted(r["entry_id"] for r in cohort) == sorted(r["entry_id"] for r in expected)
    assert all(r["enrolled_epoch"] == 1 and r["state"] == "eligible" for r in cohort)
    assert vid(0) not in {r["entry_id"] for r in cohort} and vid(1) not in {r["entry_id"] for r in cohort}
    enrollment = status(service, sid)["source"]["enrollment"]
    assert enrollment["enrolled"] == 25 and enrollment["initial_completed"] is True
    assert enrollment["remaining_initial_slots"] == 0 and enrollment["coverage"] == "window"

    # Failure, deletion and unavailability never refill the cohort.
    claim = service.claim_start(sid)
    assert claim["outcome"] == "reserved"
    started = service.mark_started(claim["start_id"], claim["owner_token"])
    assert started["outcome"] == "started"
    service.fail_capture(claim["start_id"], claim["owner_token"], "download_failed", terminal=True)
    service.note_corpus_deleted([vid(0)])
    clock.advance(61 * MINUTE_MS)
    service.detection_pass()
    assert sum(1 for r in items(service, sid) if r["eligibility"] == "back_catalog") == 25
    assert status(service, sid)["source"]["enrollment"]["enrolled"] == 25
    idx.close()


def test_s03_empty_initial_snapshot_enrolls_zero_and_completes(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([], coverage="window")])
    service = make_service(idx, clock=clock, adapter=adapter)
    sid = register(service)["source_id"]
    turn_on(service, sid)
    result = service.detection_pass()[0]
    assert result["ok"] and result["enrollment"] == {"boundary": "initial", "enrolled": 0, "cohort": []}
    enrollment = status(service, sid)["source"]["enrollment"]
    assert enrollment["initial_completed"] is True and enrollment["enrolled"] == 0
    assert enrollment["remaining_initial_slots"] == 0
    # A malformed response never masquerades as an empty source.
    adapter.results = [error("malformed_feed")]
    clock.advance(61 * MINUTE_MS)
    bad = service.detection_pass()[0]
    assert bad["ok"] is False and bad["code"] == "malformed_feed"
    idx.close()


def test_s03_first_snapshot_with_eight_usable_items_ends_at_eight(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([vid(n) for n in range(8)], coverage="window"),
                           snapshot([vid(n) for n in range(30)], coverage="window")])
    service = make_service(idx, clock=clock, adapter=adapter)
    sid = register(service)["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    assert status(service, sid)["source"]["enrollment"]["enrolled"] == 8
    clock.advance(61 * MINUTE_MS)
    result = service.detection_pass()[0]
    assert result["enrollment"] == {"boundary": "none", "enrolled": 22}
    by_eligibility = {}
    for row in items(service, sid):
        by_eligibility[row["eligibility"]] = by_eligibility.get(row["eligibility"], 0) + 1
    assert by_eligibility == {"back_catalog": 8, "future": 22}
    assert status(service, sid)["source"]["enrollment"]["enrolled"] == 8, "future never consumes slots"
    idx.close()


# ---- S06 resume gap ---------------------------------------------------------
def test_s06_resume_boundary_keeps_gap_items_metadata_only(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([vid(1), vid(2)], coverage="window")])
    backend = FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    sid = register(service)["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    assert _eligible(service, sid) == sorted([vid(1), vid(2)])
    # Capture one, leave one unfinished, then turn off.
    outcome = service.advance_source(sid)
    assert outcome["outcome"] == "succeeded"
    turn_off(service, sid)
    # Polls while off see new items; several polls are missed entirely.
    adapter.results = [snapshot([vid(3), vid(4)], coverage="window")]
    clock.advance(61 * MINUTE_MS)
    service.detection_pass()
    clock.advance(5 * DAY_MS)
    adapter.results = [snapshot([vid(5), vid(6)], coverage="window")]
    # Re-enable: a resume boundary is pending until one complete snapshot.
    on = turn_on(service, sid, operation_key="on-2")
    assert on["boundary"] == "resume" and on["consent_epoch"] == 2
    assert service.claim_start(sid)["outcome"] == "enrollment_pending"
    service.detection_pass()
    states = {r["entry_id"]: (r["state"], r["eligibility"]) for r in items(service, sid)}
    assert states[vid(2)] == ("eligible", "back_catalog") or states[vid(2)][1] == "back_catalog"
    for gap in (vid(3), vid(4), vid(5), vid(6)):
        assert states[gap] == ("observed", "none"), gap
    assert status(service, sid)["source"]["enrollment"]["enrolled"] == 2, "old cohort count fixed"
    assert status(service, sid)["source"]["boundary"] == "none"
    # Genuinely new later ids become future-eligible.
    adapter.results = [snapshot([vid(5), vid(6), vid(7)], coverage="window")]
    clock.advance(61 * MINUTE_MS)
    result = service.detection_pass()[0]
    assert result["enrollment"] == {"boundary": "none", "enrolled": 1}
    states = {r["entry_id"]: (r["state"], r["eligibility"]) for r in items(service, sid)}
    assert states[vid(7)] == ("eligible", "future")
    assert states[vid(5)] == ("observed", "none")
    idx.close()


# ---- S07 durable independent detection --------------------------------------
def test_s07_observations_persist_independently_of_capture_capacity(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    ids = [vid(n) for n in range(60)]
    adapter = FakeAdapter([snapshot(ids, coverage="window")])
    backend = FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    sid = register(service)["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    assert len(items(service, sid)) == 60
    assert sum(1 for r in items(service, sid) if r["eligibility"] == "back_catalog") == 25
    # Capacity for one capture: the cursor advanced regardless.
    assert service.advance_source(sid)["outcome"] == "succeeded"
    assert _cursor(service, sid)["revision"] == 1 and _cursor(service, sid)["observed_count"] == 60
    # Reordered and repeated ids, removal and re-addition: no new identity.
    adapter.results = [snapshot(list(reversed(ids[:30])) + ids[:5], coverage="window")]
    clock.advance(61 * MINUTE_MS)
    result = service.detection_pass()[0]
    assert result["inserted"] == 0 and result["updated"] == 30
    assert len(items(service, sid)) == 60
    adapter.results = [snapshot(ids[30:60] + [vid(999)], coverage="window")]
    clock.advance(61 * MINUTE_MS)
    result = service.detection_pass()[0]
    assert result["inserted"] == 1 and len(items(service, sid)) == 61
    assert {r["entry_id"]: r["eligibility"] for r in items(service, sid)}[vid(999)] == "future"
    idx.close()


def test_s07_missing_identity_and_conflicting_duplicates_are_reported_not_stored(tmp_path):
    idx = open_index(tmp_path)
    fetch = FakeFetch([http(200, atom_feed(
        [vid(1), vid(1)], titles={vid(1): "A"},
        extra_entries=(
            f'<entry><id>yt:video:{vid(1)}</id><yt:videoId>{vid(1)}</yt:videoId><title>B</title></entry>'
            '<entry><id>yt:video:short</id><title>bad</title></entry>'
            '<entry><title>no id at all</title></entry>')))])
    adapters = ss.default_adapters(fetch)
    service = ss.SourceSubscriptionService(index=idx, clock=Clock(), adapters=adapters,
                                           backend=FakeBackend(), instance_id="t")
    sid = register(service)["source_id"]
    result = service.detection_pass()[0]
    assert result["ok"] and result["rejected"] == 2 and result["conflicts"] == 1
    assert [r["entry_id"] for r in items(service, sid)] == [vid(1)]
    assert fetch.requests[0]["url"] == f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    assert fetch.requests[0]["headers"]["User-Agent"] == ss.FEED_USER_AGENT
    idx.close()


def test_s07_podcast_identity_fallback_and_control_characters(tmp_path):
    idx = open_index(tmp_path)
    body = rss_feed([
        {"guid": " guid-1 ", "title": "One", "enclosure": "https://cdn.example/1.mp3",
         "pubDate": "Mon, 01 Sep 2026 00:00:00 GMT"},
        {"guid": None, "link": "https://show.example/ep2", "title": "Two",
         "enclosure": "https://cdn.example/2.mp3"},
        {"guid": None, "link": None, "title": "Three", "enclosure": "https://cdn.example/3.mp3"},
        {"guid": "bad\tguid", "title": "Four"},  # tab: XML-legal, but a control character under the identity rule
        {"guid": "guid-1", "title": "One again", "enclosure": "https://cdn.example/1b.mp3"},
    ])
    fetch = FakeFetch([http(200, body, {"ETag": "W/\"abc\"", "Last-Modified": "Mon, 01 Sep 2026 00:00:00 GMT"})])
    service = ss.SourceSubscriptionService(index=idx, clock=Clock(), adapters=ss.default_adapters(fetch),
                                           backend=FakeBackend(), instance_id="t")
    sid = register(service, "podcast_rss", FEED_URL)["source_id"]
    result = service.detection_pass()[0]
    assert result["ok"] and result["rejected"] == 2 and result["conflicts"] == 1
    stored = {r["entry_id"]: r for r in items(service, sid)}
    assert set(stored) == {"guid-1", "https://show.example/ep2"}
    assert stored["guid-1"]["published_at_ms"] == ss.parse_published_ms("Mon, 01 Sep 2026 00:00:00 GMT")
    assert '"identity_method":"guid"' in stored["guid-1"]["metadata_json"]
    assert '"identity_method":"link"' in stored["https://show.example/ep2"]["metadata_json"]
    assert stored["guid-1"]["capture_key"] == ss.capture_key_for("podcast_rss", FEED_URL, "guid-1")
    cursor = _cursor(service, sid)
    assert cursor["etag"] == 'W/"abc"' and cursor["coverage"] == "complete"
    # The legacy projection carries the episode row for the old pipeline.
    episodes = rows(service, "SELECT guid, audio_url, auto_ingest_requested FROM podcast_episodes ORDER BY id")
    assert [e["guid"] for e in episodes] == ["guid-1", "https://show.example/ep2"]
    assert all(e["auto_ingest_requested"] == 0 for e in episodes)
    idx.close()


def test_s07_consent_change_during_delayed_poll_grants_no_stale_eligibility(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([vid(1), vid(2)], coverage="window")])
    service = make_service(idx, clock=clock, adapter=adapter)
    sid = register(service)["source_id"]
    # Claim the poll while off, turn on before the result commits.
    claim = service.claim_poll(sid)
    assert claim is not None and claim["consent_epoch"] == 0
    turn_on(service, sid)
    result = service.run_claimed_poll(claim)
    assert result["ok"] and result["stale_epoch"] is True and result["enrollment"] is None
    assert all(r["eligibility"] == "none" and r["first_seen_consent_epoch"] is None
               for r in items(service, sid))
    assert status(service, sid)["source"]["boundary"] == "initial", "boundary not completed by a stale poll"
    assert _cursor(service, sid)["next_poll_at_ms"] == clock.now, "next due poll uses the current epoch"
    # The next poll completes the boundary with the current epoch.
    result = service.detection_pass()[0]
    assert result["stale_epoch"] is False and result["enrollment"]["enrolled"] == 2
    idx.close()


def test_s07_partial_batch_staged_then_completed_by_a_later_full_poll(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([vid(1)], coverage="window")])
    service = make_service(idx, clock=clock, adapter=adapter)
    sid = register(service, "youtube_playlist", PLAYLIST_URL)["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    assert _cursor(service, sid)["revision"] == 1
    # A partial listing persists metadata only, advances no cursor, backs off.
    adapter.results = [snapshot([vid(2), vid(3)], coverage="partial", truncated=True)]
    clock.advance(61 * MINUTE_MS)
    partial = service.detection_pass()[0]
    assert partial["ok"] is False and partial["outcome"] == "partial"
    cursor = _cursor(service, sid)
    assert cursor["revision"] == 1 and cursor["coverage"] == "partial" and cursor["truncated"] == 1
    assert cursor["error_count"] == 1 and cursor["last_error_code"] == "partial_listing"
    assert cursor["last_poll_success_ms"] == T0
    staged = {r["entry_id"]: r for r in items(service, sid)}
    assert staged[vid(2)]["eligibility"] == "none" and staged[vid(2)]["first_scan_revision"] == 2
    assert staged[vid(2)]["first_seen_consent_epoch"] == 1
    assert service.claim_start(sid)["outcome"] in ("reserved", "idle")
    # A later complete poll grants future eligibility to the staged items.
    adapter.results = [snapshot([vid(1), vid(2), vid(3)], coverage="window")]
    clock.advance(int(cursor["next_poll_at_ms"] - clock.now) + 1)
    full = service.detection_pass()[0]
    assert full["ok"] and full["enrollment"]["enrolled"] == 2
    granted = {r["entry_id"]: r["eligibility"] for r in items(service, sid)}
    assert granted[vid(2)] == "future" and granted[vid(3)] == "future"
    # Staged partial observations whose revision was committed by a 304 stay metadata.
    adapter.results = [snapshot([vid(4)], coverage="partial")]
    clock.advance(61 * MINUTE_MS)
    service.detection_pass()
    adapter.results = [not_modified()]
    clock.advance(int(_cursor(service, sid)["next_poll_at_ms"] - clock.now) + 1)
    assert service.detection_pass()[0]["outcome"] == "not_modified"
    adapter.results = [snapshot([vid(1), vid(4)], coverage="window")]
    clock.advance(61 * MINUTE_MS)
    assert service.detection_pass()[0]["enrollment"]["enrolled"] == 0
    assert {r["entry_id"]: r["eligibility"] for r in items(service, sid)}[vid(4)] == "none"
    idx.close()


def test_s07_capture_enqueue_failure_does_not_touch_the_cursor(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([vid(1)], coverage="window")])
    backend = FakeBackend(bind_fail=True)
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    sid = register(service)["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    before = _cursor(service, sid)
    with pytest.raises(RuntimeError):
        service.advance_source(sid)
    assert _cursor(service, sid) == before
    # The started transaction rolled back with the failed bind: the row is
    # still an unstarted reservation, nothing is charged, and it expires.
    ledger = starts(service, sid)
    assert len(ledger) == 1 and ledger[0]["state"] == "reserved"
    assert ledger[0]["started_at_ms"] is None and ledger[0]["backend_id"] is None
    assert status(service, sid)["source"]["allowance"] == {
        **status(service, sid)["source"]["allowance"], "reserved": 1, "charged": 0}
    clock.advance(ss.RESERVATION_TTL_MS + 1)
    assert service.reconcile_on_startup()["released"] == 1
    assert starts(service, sid)[0]["state"] == "released"
    assert starts(service, sid)[0]["release_or_failure_code"] == "expired"
    assert {r["state"] for r in items(service, sid)} == {"eligible"}
    idx.close()


# ---- S08 poll failure and coverage ------------------------------------------
def test_s08_only_valid_snapshots_advance_success_and_validators(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([vid(1)], coverage="window", etag="W/1", last_modified="Mon")])
    service = make_service(idx, clock=clock, adapter=adapter)
    sid = register(service, poll_interval_min=15)["source_id"]
    service.detection_pass()
    good = _cursor(service, sid)
    assert good["etag"] == "W/1" and good["last_poll_success_ms"] == T0 and good["revision"] == 1
    assert good["next_poll_at_ms"] == T0 + 15 * MINUTE_MS

    # 304: success and sequence advance, no observations, validators kept.
    adapter.results = [not_modified("W/2")]
    clock.advance(15 * MINUTE_MS)
    assert service.detection_pass()[0]["outcome"] == "not_modified"
    cursor = _cursor(service, sid)
    assert cursor["revision"] == 2 and cursor["last_poll_success_ms"] == clock.now
    assert cursor["etag"] == "W/2" and len(items(service, sid)) == 1

    # Failures: attempt time and error fields move, success and validators stay,
    # backoff doubles per failure and Retry-After may only extend it.
    failures = [error("malformed_feed"), error("feed_too_large"), error("poll_timeout"),
                error("rate_limited", retry_after_ms=10 * 60 * MINUTE_MS)]
    expected_delays = [15, 30, 60, max(120, 600)]
    success_ms = cursor["last_poll_success_ms"]
    for n, (failure, delay) in enumerate(zip(failures, expected_delays), start=1):
        adapter.results = [failure]
        clock.advance(int(_cursor(service, sid)["next_poll_at_ms"] - clock.now) + 1)
        result = service.detection_pass()[0]
        assert result["ok"] is False and result["code"] == failure.error_code
        cursor = _cursor(service, sid)
        assert cursor["error_count"] == n and cursor["last_error_code"] == failure.error_code
        assert cursor["last_poll_attempt_ms"] == clock.now
        assert cursor["last_poll_success_ms"] == success_ms and cursor["etag"] == "W/2"
        assert cursor["revision"] == 2
        assert cursor["next_poll_at_ms"] == clock.now + delay * MINUTE_MS
    detection = status(service, sid)["source"]["detection"]
    assert detection["consecutive_failures"] == 4
    assert detection["error"] == {"code": "rate_limited", "message": "boom"}
    # Backoff is capped at 1440 minutes.
    adapter.results = [error("feed_unreachable")]
    for _ in range(10):
        clock.advance(int(_cursor(service, sid)["next_poll_at_ms"] - clock.now) + 1)
        service.detection_pass()
    assert _cursor(service, sid)["next_poll_at_ms"] - clock.now <= 1440 * MINUTE_MS
    idx.close()


def test_s08_real_adapters_report_http_and_size_failures(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    too_big = b"<feed>" + b"x" * (ss.FEED_MAX_BYTES + 1) + b"</feed>"
    fetch = FakeFetch([http(200, b"<not xml"), http(500, b""), http(429, b"", {"Retry-After": "120"}),
                       http(200, too_big), TimeoutError("read timed out"),
                       http(200, b'{"json": "not a feed"}'),
                       http(304, b"", {"ETag": "W/9"})])
    service = ss.SourceSubscriptionService(index=idx, clock=clock, adapters=ss.default_adapters(fetch),
                                           backend=FakeBackend(), instance_id="t")
    sid = register(service, poll_interval_min=15)["source_id"]
    codes = []
    for _ in range(7):
        clock.advance(int(_cursor(service, sid)["next_poll_at_ms"] - clock.now) + 1)
        result = service.detection_pass()[0]
        codes.append(result.get("code") or result["outcome"])
    assert codes == ["malformed_feed", "http_500", "rate_limited", "feed_too_large", "poll_timeout",
                     "malformed_feed", "not_modified"]
    cursor = _cursor(service, sid)
    assert cursor["error_count"] == 0 and cursor["etag"] == "W/9" and cursor["revision"] == 1
    assert len(items(service, sid)) == 0
    # A 304 while a boundary is pending completes nothing.
    turn_on(service, sid)
    fetch.responses = [http(304, b"", {"ETag": "W/9"})]
    clock.advance(int(_cursor(service, sid)["next_poll_at_ms"] - clock.now) + 1)
    service.detection_pass()
    assert "If-None-Match" not in fetch.requests[-1]["headers"]
    assert status(service, sid)["source"]["boundary"] == "initial"
    idx.close()


# ---- S09 due-time concurrency -----------------------------------------------
def test_s09_two_schedulers_one_network_poll_and_stale_owner_rejected(tmp_path):
    idx = open_index(tmp_path)
    db = tmp_path / "index.db"
    clock = Clock()
    gate = threading.Event()
    adapter_a = FakeAdapter([snapshot([vid(1)], coverage="window")], gate=gate)
    adapter_b = FakeAdapter([snapshot([vid(2)], coverage="window")])
    service_a = make_service(idx, clock=clock, adapter=adapter_a, instance_id="a")
    service_b = make_service(path=db, clock=clock, adapter=adapter_b, instance_id="b")
    sid = register(service_a)["source_id"]
    results_a: list = []
    thread = threading.Thread(target=lambda: results_a.extend(service_a.detection_pass()))
    thread.start()
    # Wait until A holds the lease (its adapter blocks on the gate).
    for _ in range(200):
        if adapter_a.calls:
            break
        threading.Event().wait(0.01)
    assert adapter_a.calls, "scheduler A never claimed"
    # B sees the row owned and does nothing; status/refresh cannot bypass.
    assert service_b.detection_pass() == [] and adapter_b.calls == []
    refresh = service_b.refresh_source(REGISTRY, {"source_id": sid})
    assert refresh["ok"] and refresh["outcome"] == "not_due" and refresh["poll_in_progress"] is True
    assert adapter_b.calls == []
    gate.set()
    thread.join(timeout=5)
    assert results_a and results_a[0]["ok"]
    assert len(items(service_b, sid)) == 1
    # Not due for either scheduler now; a manual refresh returns the due time.
    assert service_b.detection_pass() == []
    refresh = service_b.refresh_source(REGISTRY, {"source_id": sid})
    assert refresh["outcome"] == "not_due" and refresh["next_poll_at_ms"] == T0 + 60 * MINUTE_MS
    # A late result from an expired/replaced owner is rejected.
    clock.advance(61 * MINUTE_MS)
    stale_claim = service_b.claim_poll(sid)
    assert stale_claim is not None
    clock.advance(ss.POLL_LEASE_MS + 1)
    service_a.detection_pass()  # reaps the expired lease as a poll_timeout
    late = service_b.commit_poll(sid, stale_claim["owner_token"], snapshot([vid(3)], coverage="window"))
    assert late["ok"] is False and late["outcome"] == "stale_owner"
    assert vid(3) not in {r["entry_id"] for r in items(service_b, sid)}
    cursor = _cursor(service_b, sid)
    assert cursor["last_error_code"] == "poll_timeout" and cursor["error_count"] == 1
    service_b.close()
    idx.close()


def test_s09_exhausted_capture_allowance_never_suppresses_polling(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([vid(n) for n in range(15)], coverage="window")])
    backend = FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    sid = register(service, poll_interval_min=15)["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    charged = 0
    while charged < 10:
        with idx.write_transaction() as conn:
            conn.execute("UPDATE source_subscriptions SET capture_not_before_ms=0 WHERE source_id=?", (sid,))
        assert service.advance_source(sid)["outcome"] == "succeeded"
        charged += 1
    assert status(service, sid)["source"]["allowance"]["remaining"] == 0
    with idx.write_transaction() as conn:
        conn.execute("UPDATE source_subscriptions SET capture_not_before_ms=0 WHERE source_id=?", (sid,))
    assert service.claim_start(sid)["outcome"] == "allowance_exhausted"
    assert status(service, sid)["source"]["capture_status"] == "allowance_exhausted"
    adapter.results = [snapshot([vid(n) for n in range(20)], coverage="window")]
    clock.advance(15 * MINUTE_MS)
    result = service.detection_pass()[0]
    assert result["ok"] and result["inserted"] == 5 and result["enrollment"]["enrolled"] == 5
    assert len(items(service, sid)) == 20
    idx.close()
