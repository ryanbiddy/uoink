"""Phase 0 podcast backlog protections, restated under the Phase 3 contract.

The protections survive with a new authority (contract phase3-v1-2026-09-07,
"Consent and enrollment", "Atomic starts, failure, and restart", migration
section):

* the bounded back catalog (at most 25 per source, chosen once and never
  refilled) is the subscription service's initial enrollment cohort;
* the daily cap (10 starts per source per UTC day) is counted only from the
  capture ledger, never inferred from download/transcript timestamps;
* a pre-cutover ``auto_ingest=1`` feed is imported as an explicit opt-in with
  a receipt and holds new starts until the next UTC day;
* later discoveries become future-eligible without consuming cohort slots.

The old episode marker (``auto_ingest_requested``), the evidence-based daily
counter and the repair pass no longer authorize anything.

Run: python -m pytest -q tests/test_phase0_podcast_repair.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    Clock, DAY_MS, FakeAdapter, FakeBackend, MINUTE_MS, T0, items, make_service, rows, snapshot,
    starts, status, turn_off, turn_on,
)

import index as index_mod  # noqa: E402
import podcasts  # noqa: E402
import source_subscriptions as ss  # noqa: E402

FEED_URL = "https://show.example/feed.xml"
HOUR_MS = 60 * MINUTE_MS
# 2026-08-01T00:00:00Z, derived from the fixtures' T0 (2026-09-07T12:00:00Z).
AUG1_MS = T0 - 37 * DAY_MS - 12 * HOUR_MS


def _guid(number: int) -> str:
    return f"episode-{number}"


def _published_ms(number: int) -> int:
    """Distinct valid publication times, one hour apart from 2026-08-01."""
    return AUG1_MS + number * HOUR_MS


def _published_iso(number: int) -> str:
    return datetime.fromtimestamp(_published_ms(number) / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _episode(number: int) -> dict:
    return {
        "guid": _guid(number),
        "title": f"Episode {number}",
        "audio_url": f"https://cdn.example/{number}.mp3",
        "published_at": _published_iso(number),
    }


def _feed_snapshot(numbers) -> ss.AdapterResult:
    ids = [_guid(n) for n in numbers]
    return snapshot(
        ids, coverage="complete",
        published={_guid(n): _published_ms(n) for n in numbers},
        titles={_guid(n): f"Episode {n}" for n in numbers},
        urls={_guid(n): f"https://show.example/{_guid(n)}" for n in numbers})


def _wall_clock() -> Clock:
    """``add_feed`` stamps its projected source with the real clock; the
    service clock must start at or after that instant."""
    return Clock(int(time.time() * 1000))


def _now_dt(clock: Clock) -> datetime:
    return datetime.fromtimestamp(clock.now / 1000, tz=timezone.utc)


def _watched_feed(tmp_path, count: int, *, backend=None):
    idx = index_mod.Index.open(tmp_path / "index.db")
    feed = podcasts.add_feed(idx, FEED_URL)
    clock = _wall_clock()
    adapter = FakeAdapter([_feed_snapshot(range(count))])
    backend = backend or FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    return idx, feed, service, clock, adapter, backend


def _reset_interval(idx, source_id: str) -> None:
    """Skip the one-start-per-interval clock so consecutive starts can be
    exercised within one UTC day (the allowance is what is under test)."""
    with idx.write_transaction() as conn:
        conn.execute("UPDATE source_subscriptions SET capture_not_before_ms=0 WHERE source_id=?",
                     (source_id,))


def _marker_count(idx, feed_id: int) -> int:
    return int(idx._conn.execute(
        "SELECT COUNT(*) FROM podcast_episodes WHERE feed_id=? AND auto_ingest_requested=1",
        (feed_id,)).fetchone()[0])


def test_initial_cohort_is_bounded_and_the_repair_pass_no_longer_marks_anything(tmp_path):
    idx, feed, service, clock, adapter, backend = _watched_feed(tmp_path, 40)
    sid = feed["source_id"]
    try:
        turn_on(service, sid)
        assert status(service, sid)["source"]["enrollment"]["pending"] is True
        result = service.detection_pass()
        assert result[0]["ok"] is True and result[0]["inserted"] == 40
        assert result[0]["enrollment"]["boundary"] == "initial"
        assert result[0]["enrollment"]["enrolled"] == 25
        enrollment = status(service, sid)["source"]["enrollment"]
        assert enrollment["cap"] == 25 and enrollment["enrolled"] == 25
        assert enrollment["initial_completed"] is True
        assert enrollment["remaining_initial_slots"] == 0 and enrollment["pending"] is False
        assert enrollment["known_candidates"] == 40
        cohort = [r for r in items(service, sid) if r["eligibility"] == "back_catalog"]
        assert len(cohort) == 25 and all(r["state"] == "eligible" for r in cohort)
        assert sorted(r["entry_id"] for r in cohort) == sorted(_guid(n) for n in range(15, 40)), \
            "the newest 25 by publication time"
        rest = [r for r in items(service, sid) if r["eligibility"] == "none"]
        assert len(rest) == 15 and all(r["state"] == "observed" for r in rest)

        # The old episode rows exist for the legacy pipeline, the marker is
        # never set, and the repair pass is report-only and delegated.
        assert len(podcasts.list_episodes(idx, feed_id=feed["id"], limit=100)) == 40
        assert _marker_count(idx, feed["id"]) == 0
        repair = podcasts.repair_stranded_auto_ingest(idx, feed_id=feed["id"], now=_now_dt(clock))
        assert repair["dry_run"] is True and repair["delegated_to"] == "source_subscriptions"
        assert repair["marked_eligible"] == 0 and repair["feeds_considered"] == 0
        assert _marker_count(idx, feed["id"]) == 0

        # The old helpers may act only on an episode whose ledger row is started.
        backend.outcome = ss.CaptureOutcome("in_flight")
        first = service.advance_source(sid)
        assert first["outcome"] == "in_flight"
        started = starts(service, sid)
        assert len(started) == 1 and started[0]["state"] == "started"
        item = next(r for r in items(service, sid) if r["item_id"] == started[0]["item_id"])
        assert item["entry_id"] == _guid(39), "the newest cohort item starts first"
        candidates = podcasts.list_auto_ingest_candidates(
            idx, feed_id=feed["id"], limit=50, now=_now_dt(clock))
        assert [c["id"] for c in candidates] == [item["legacy_episode_id"]]
        assert candidates[0]["guid"] == _guid(39)
        done = service.complete_capture(started[0]["start_id"], started[0]["owner_token"],
                                        item["entry_id"])
        assert done["outcome"] == "succeeded"
        assert podcasts.list_auto_ingest_candidates(
            idx, feed_id=feed["id"], limit=50, now=_now_dt(clock)) == []

        # Off: no candidate, no reservation, and the cohort is neither refilled nor reset.
        turn_off(service, sid)
        _reset_interval(idx, sid)
        assert service.advance_source(sid)["outcome"] == "consent_off"
        assert podcasts.list_auto_ingest_candidates(
            idx, feed_id=feed["id"], limit=50, now=_now_dt(clock)) == []
        assert status(service, sid)["source"]["enrollment"]["enrolled"] == 25
        assert len(starts(service, sid)) == 1
    finally:
        idx.close()


def test_pre_cutover_opt_in_enrolls_a_bounded_backlog_under_the_cutover_hold(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        # A feed opted in before Phase 3: the old boolean, set before any source
        # row existed (the old route refuses this on a managed tree).
        with idx.write_transaction() as conn:
            cur = conn.execute(
                "INSERT INTO podcast_feeds (feed_url, poll_interval_min, auto_ingest, added_at) "
                "VALUES (?, 60, 1, '2026-08-01T00:00:00Z')", ("https://new.example/feed.xml",))
            feed_id = int(cur.lastrowid)
        podcasts.upsert_episodes(idx, feed_id, [_episode(n) for n in range(50)])
        assert _marker_count(idx, feed_id) == 0, "the first response is a back catalog"
        clock = _wall_clock()
        adapter = FakeAdapter([_feed_snapshot(range(50))])
        backend = FakeBackend()
        service = make_service(idx, clock=clock, adapter=adapter, backend=backend)

        report = service.import_legacy_registries()
        assert report["feeds_imported"] == 1 and report["items_imported"] == 50
        sid = ss.legacy_source_id(idx._conn, feed_id=feed_id)
        assert sid is not None
        summary = status(service, sid)["source"]
        assert summary["consent_state"] == "on" and summary["boundary"] == "initial"
        assert summary["revision"] == 1 and summary["consent_epoch"] == 1
        assert summary["enrollment"]["pending"] is True
        assert summary["enrollment"]["enrolled"] == 0, "no invented count before a valid snapshot"
        assert summary["enrollment"]["remaining_initial_slots"] == 25, "'up to 25' until enrolled"
        assert [r["authority"] for r in rows(
            service, "SELECT authority FROM source_consent_receipts")] == ["legacy_explicit_opt_in"]
        hold_until = ss.next_utc_midnight_ms(clock.now)
        assert summary["allowance"]["hold_reason"] == "legacy_accounting_hold"
        assert summary["allowance"]["hold_until_ms"] == hold_until
        assert summary["allowance"]["charged"] == 0 and summary["allowance"]["reserved"] == 0
        assert summary["capture_status"] == "legacy_accounting_hold"
        assert service.advance_source(sid)["outcome"] == "legacy_accounting_hold"

        # The first valid snapshot enrolls at most 25 of the 50 known entries.
        result = service.detection_pass()
        assert result[0]["ok"] is True
        assert result[0]["inserted"] == 0 and result[0]["updated"] == 50
        assert result[0]["enrollment"]["boundary"] == "initial"
        assert result[0]["enrollment"]["enrolled"] == 25
        enrollment = status(service, sid)["source"]["enrollment"]
        assert enrollment["enrolled"] == 25 and enrollment["initial_completed"] is True
        assert enrollment["remaining_initial_slots"] == 0
        cohort = [r["entry_id"] for r in items(service, sid) if r["eligibility"] == "back_catalog"]
        assert sorted(cohort) == sorted(_guid(n) for n in range(25, 50))
        assert _marker_count(idx, feed_id) == 0, "the old marker stays unset on a managed tree"

        # The cutover hold still blocks starts on the cutover day.
        assert service.advance_source(sid)["outcome"] == "legacy_accounting_hold"
        assert backend.runs == [] and starts(service, sid) == []
        assert podcasts.list_auto_ingest_candidates(idx, feed_id=feed_id, limit=50) == []

        # After the next UTC midnight the cohort starts gradually under the ledger.
        clock.now = hold_until
        first = service.advance_source(sid)
        assert first["outcome"] == "succeeded"
        assert len(backend.runs) == 1
        allowance = status(service, sid)["source"]["allowance"]
        assert allowance["hold_reason"] is None and allowance["charged"] == 1
        assert allowance["utc_day"] == ss.utc_day(hold_until)

        # A rerun of the import never postpones the hold or re-enrolls.
        again = service.import_legacy_registries()
        assert again["feeds_imported"] == 0 and again["skipped"] == 1
        source = rows(service, "SELECT accounting_hold_until_ms, back_catalog_enrolled "
                               "FROM source_subscriptions WHERE source_id=?", (sid,))[0]
        assert source["accounting_hold_until_ms"] == hold_until
        assert source["back_catalog_enrolled"] == 25
        assert rows(service, "SELECT COUNT(*) AS n FROM source_consent_receipts")[0]["n"] == 1
    finally:
        idx.close()


def test_daily_cap_counts_ledger_charges_not_timestamp_evidence(tmp_path):
    idx, feed, service, clock, adapter, backend = _watched_feed(tmp_path, 12)
    sid = feed["source_id"]
    try:
        turn_on(service, sid)
        assert service.detection_pass()[0]["enrollment"]["enrolled"] == 12
        for n in range(10):
            _reset_interval(idx, sid)
            assert service.advance_source(sid)["outcome"] == "succeeded", n
            allowance = status(service, sid)["source"]["allowance"]
            assert allowance["charged"] == n + 1 and allowance["remaining"] == 9 - n
        _reset_interval(idx, sid)
        assert service.advance_source(sid)["outcome"] == "allowance_exhausted"
        allowance = status(service, sid)["source"]["allowance"]
        assert allowance["cap"] == 10 and allowance["charged"] == 10
        assert allowance["reserved"] == 0 and allowance["remaining"] == 0
        assert len({r["slot"] for r in starts(service, sid)}) == 10
        assert podcasts.list_auto_ingest_candidates(
            idx, feed_id=feed["id"], limit=50, now=_now_dt(clock)) == []

        # The old evidence-based counter sees none of these starts and, once
        # the projection rows carry today's timestamps, over-counts them.
        # Neither reading changes the ledger's allowance.
        assert podcasts.count_daily_ingest_starts(idx, feed["id"], now=_now_dt(clock)) == 0
        today = _now_dt(clock).strftime("%Y-%m-%dT%H:%M:%SZ")
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_episodes SET audio_downloaded_at=? WHERE feed_id=?",
                         (today, feed["id"]))
        assert podcasts.count_daily_ingest_starts(idx, feed["id"], now=_now_dt(clock)) == 12
        assert status(service, sid)["source"]["allowance"]["charged"] == 10
        _reset_interval(idx, sid)
        assert service.advance_source(sid)["outcome"] == "allowance_exhausted"
        with idx.write_transaction() as conn:
            conn.execute("UPDATE podcast_episodes SET audio_downloaded_at='2026-01-01T01:00:00Z' "
                         "WHERE feed_id=?", (feed["id"],))
        assert podcasts.count_daily_ingest_starts(idx, feed["id"], now=_now_dt(clock)) == 0
        _reset_interval(idx, sid)
        assert service.advance_source(sid)["outcome"] == "allowance_exhausted", \
            "yesterday's timestamps refund nothing"

        # Only the UTC day boundary renews the allowance; yesterday's rows stay.
        clock.now = ss.next_utc_midnight_ms(clock.now)
        allowance = status(service, sid)["source"]["allowance"]
        assert allowance["charged"] == 0 and allowance["remaining"] == 10
        assert allowance["utc_day"] == ss.utc_day(clock.now)
        backend.outcome = ss.CaptureOutcome("failed", code="download_failed")
        _reset_interval(idx, sid)
        failed = service.advance_source(sid)
        assert failed["outcome"] == "failed" and failed["attempts"] == 1
        assert failed["retry_at_ms"] == clock.now + 15 * MINUTE_MS
        assert status(service, sid)["source"]["allowance"]["charged"] == 1, \
            "a failed actual start keeps its charge"
        charged = [r for r in starts(service, sid) if r["started_at_ms"] is not None]
        assert len(charged) == 11 and len({r["utc_day"] for r in charged}) == 2
    finally:
        idx.close()


def test_later_discoveries_are_future_eligible_after_backlog_enrollment(tmp_path):
    idx, feed, service, clock, adapter, backend = _watched_feed(tmp_path, 30)
    sid = feed["source_id"]
    try:
        turn_on(service, sid)
        assert service.detection_pass()[0]["enrollment"]["enrolled"] == 25
        before = {r["entry_id"]: r for r in items(service, sid)}
        assert sum(1 for r in before.values() if r["eligibility"] == "back_catalog") == 25
        assert sorted(e for e, r in before.items() if r["eligibility"] == "none") == \
            sorted(_guid(n) for n in range(5))

        # A later snapshot with one genuinely new entry.
        adapter.results = [_feed_snapshot(list(range(30)) + [99])]
        clock.advance(60 * MINUTE_MS)
        result = service.detection_pass()
        assert result[0]["ok"] is True and result[0]["inserted"] == 1
        assert result[0]["enrollment"] == {"boundary": "none", "enrolled": 1}
        after = {r["entry_id"]: r for r in items(service, sid)}
        new = after[_guid(99)]
        assert new["eligibility"] == "future" and new["state"] == "eligible"
        assert new["enrolled_epoch"] == 1 and new["first_seen_consent_epoch"] == 1
        # Future eligibility consumes no back-catalog slot, and the five
        # observed-only back-catalog entries are never pulled in later.
        source = status(service, sid)["source"]
        assert source["enrollment"]["enrolled"] == 25
        assert source["enrollment"]["remaining_initial_slots"] == 0
        for n in range(5):
            assert after[_guid(n)]["eligibility"] == "none"
            assert after[_guid(n)]["state"] == "observed"
        # The old episode row is projected for the pipeline, still without a marker.
        episode = next(e for e in podcasts.list_episodes(idx, feed_id=feed["id"], limit=100)
                       if e["guid"] == _guid(99))
        assert episode["auto_ingest_requested"] == 0
        assert new["legacy_episode_id"] == episode["id"]
        # The newest eligible item, the future one, starts first through the ledger.
        outcome = service.advance_source(sid)
        assert outcome["outcome"] == "succeeded" and outcome["item_id"] == new["item_id"]
    finally:
        idx.close()
