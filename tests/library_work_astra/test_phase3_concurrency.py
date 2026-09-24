"""Contract gates S04/S05/S09/S10/S12. See support module for assumed seams.

Two independent Index connections share one disposable WAL database. Event
barriers force both revocation orderings and hold network I/O outside the write
transaction. No sleeps, live clock, resident helper, or production adapter runs.
"""

import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_phase3_support import (
    DAY, MINUTE, at, cursor_row, item_rows, ledger, migration_dir, observation,
    ok, phase3_isolation, phase3_module, race, rig, rows, snapshot, source_row,
)


def next_poll(rig, sid):
    rig.clock.now = max(rig.clock(), cursor_row(rig.idx, sid)['next_poll_at_ms'])


def charge_failures(rig, sid, count):
    items = sorted(item_rows(rig.idx, sid), key=lambda row: row['entry_id'])
    for item in items[:count]:
        start = rig.start(sid, item)
        rig.failed(start)
        rig.allowance(sid)
        rig.clock.advance(15 * MINUTE)
    return items[count:]


def test_s04_on_restart_reserve_off_restart_fences_old_epoch(rig):
    sid = rig.register()
    on, request = rig.consent(sid, 'on', 'durable-on')
    assert on['changed'] and on['boundary'] == 'initial'
    rig.restart()
    assert source_row(rig.idx, sid)['consent_state'] == 'on'
    assert source_row(rig.idx, sid)['initial_enrollment_completed_ms'] is None
    rig.feed.responses[sid] = snapshot([observation(n) for n in range(3)])
    rig.svc.poll_source(sid)
    first = rig.reserve(sid)
    off, _ = rig.consent(sid, 'off', 'durable-off')
    assert off['released_reservations'] == 1
    before = source_row(rig.idx, sid)
    rig.clock.advance(6 * MINUTE)  # Consumed on-token has expired.
    rig.restart()
    assert ok(rig.svc.set_source_consent(rig.context, request)) == on
    rig.svc.dispatch_capture(first['start_id'], first['owner_token'])
    row = ledger(rig.idx, sid)[0]
    assert row['state'] == 'released' and row['started_at_ms'] is None
    assert row['release_or_failure_code']
    assert rig.backend.launches == []
    after = source_row(rig.idx, sid)
    for key in ('consent_state', 'revision', 'consent_epoch', 'back_catalog_enrolled', 'initial_enrollment_completed_ms'):
        assert after[key] == before[key]
    assert after['consent_state'] == 'off' and after['back_catalog_enrolled'] == 3
    assert len(rows(rig.idx, 'source_consent_receipts')) == 2
    assert rig.allowance(sid)['charged'] == 0


def test_s04_same_on_and_resume_never_refill_or_promote_off_observations(rig):
    sid = rig.enrolled(3)
    original = source_row(rig.idx, sid)
    same, _ = rig.consent(sid, 'on')
    assert same['changed'] is False
    assert same['after_revision'] == original['revision']
    assert same['consent_epoch'] == original['consent_epoch']
    rig.consent(sid, 'off')
    next_poll(rig, sid)
    rig.feed.responses[sid] = snapshot([observation(100)])
    rig.svc.poll_source(sid)
    rig.consent(sid, 'on')
    assert source_row(rig.idx, sid)['boundary'] == 'resume'
    before = ledger(rig.idx)
    rig.svc.reserve_capture(sid, item_rows(rig.idx, sid)[0]['item_id'])
    assert ledger(rig.idx) == before, 'Pending resume boundary authorized a start'
    next_poll(rig, sid)
    rig.feed.responses[sid] = snapshot([observation(100), observation(101)])
    rig.svc.poll_source(sid)
    known = {row['entry_id']: row for row in item_rows(rig.idx, sid)}
    assert all(known[observation(n)['entry_id']]['eligibility'] == 'none' for n in (100, 101))
    assert all(known[observation(n)['entry_id']]['eligibility'] == 'back_catalog' for n in range(3))
    assert source_row(rig.idx, sid)['back_catalog_enrolled'] == 3
    next_poll(rig, sid)
    rig.feed.responses[sid] = snapshot([observation(102)])
    rig.svc.poll_source(sid)
    newest = next(row for row in item_rows(rig.idx, sid) if row['entry_id'] == observation(102)['entry_id'])
    assert newest['eligibility'] == 'future'
    assert source_row(rig.idx, sid)['back_catalog_enrolled'] == 3


def test_s05_off_committed_on_other_connection_before_start_means_zero_dispatch(rig):
    sid = rig.enrolled()
    start = rig.reserve(sid)
    other_idx, other = rig.open()
    assert other_idx._conn is not rig.idx._conn
    request = rig.operation(sid, 'off')
    ok(other.set_source_consent(rig.context, request))
    rig.svc.dispatch_capture(start['start_id'], start['owner_token'])
    assert rig.backend.launches == []
    assert ledger(rig.idx, sid)[0]['state'] == 'released'
    assert all(row['actual_starts'] == 0 for row in item_rows(rig.idx, sid))


def test_s04_receipt_token_consent_and_releases_rollback_together(rig):
    sid = rig.enrolled()
    rig.reserve(sid)
    request = rig.operation(sid, 'off')
    tables = ('source_subscriptions', 'source_consent_receipts', 'source_user_intents',
              'source_capture_starts', 'source_items')
    before = {name: rows(rig.idx, name) for name in tables}
    with rig.idx.write_transaction() as conn:
        conn.execute("""CREATE TRIGGER astra_fail_consent BEFORE INSERT ON source_consent_receipts
                        BEGIN SELECT RAISE(ABORT, 'fixture receipt unavailable'); END""")
    try:
        try:
            result = rig.svc.set_source_consent(rig.context, request)
            assert result['ok'] is False, result
        except sqlite3.Error:
            pytest.fail('Registry tool leaked a SQLite exception instead of its error envelope')
        assert {name: rows(rig.idx, name) for name in tables} == before
        assert rig.backend.launches == []
    finally:
        with rig.idx.write_transaction() as conn:
            conn.execute('DROP TRIGGER astra_fail_consent')
    receipt = ok(rig.svc.set_source_consent(rig.context, request))
    assert receipt['released_reservations'] == 1 and receipt['consent_state'] == 'off'


def test_s05_before_started_commit_holds_write_lock_and_has_no_side_effect(rig):
    sid = rig.enrolled()
    reservation = rig.reserve(sid)
    other_idx, other = rig.open()
    request = rig.operation(sid, 'off')
    rig.faults.pause_at = 'before_started_commit'
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(rig.svc.dispatch_capture, reservation['start_id'], reservation['owner_token'])
        try:
            assert rig.faults.entered.wait(5), 'Missing before_started_commit hook'
            # Readers see the prior commit and no acquisition has occurred.
            visible = ledger(other_idx, sid)[0]
            assert visible['state'] == 'reserved' and visible['started_at_ms'] is None
            assert rig.backend.launches == []
            off = other.set_source_consent(rig.context, request)
            assert off['ok'] is False and off['error']['code'] == 'storage_busy', off
            assert off['error']['retryable'] is True
        finally:
            rig.faults.release.set()
        pending.result(timeout=5)
    rig.faults.pause_at = None
    ok(other.set_source_consent(rig.context, request))
    assert source_row(rig.idx, sid)['consent_state'] == 'off'
    assert len(rig.backend.launches) == 1 and rig.allowance(sid)['charged'] == 1


@pytest.mark.parametrize('outcome', ['complete', 'failure'])
def test_s05_start_committed_before_off_can_finish_but_failure_cannot_retry(rig, outcome):
    sid = rig.enrolled()
    start = rig.reserve(sid)
    _, other = rig.open()
    request = rig.operation(sid, 'off')
    rig.faults.pause_at = 'after_started_commit'
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(rig.svc.dispatch_capture, start['start_id'], start['owner_token'])
        try:
            assert rig.faults.entered.wait(5), 'Missing after_started_commit hook'
            receipt = ok(other.set_source_consent(rig.context, request))
            assert receipt['released_reservations'] == 0
            assert rig.allowance(sid)['charged'] == 1
        finally:
            rig.faults.release.set()
        pending.result(timeout=5)
    rig.faults.pause_at = None
    start = ledger(rig.idx, sid)[0]
    assert len(rig.backend.launches) == 1
    if outcome == 'complete':
        vid = rig.complete(start)
        assert rows(rig.idx, 'yoinks', 'video_id=?', (vid,))
        assert next(row for row in item_rows(rig.idx, sid) if row['item_id'] == start['item_id'])['state'] == 'committed'
    else:
        rig.failed(start)
        rig.clock.advance(DAY)
        rig.svc.reserve_capture(sid, start['item_id'])
        assert len(ledger(rig.idx, sid)) == 1
    assert source_row(rig.idx, sid)['consent_state'] == 'off'
    assert ledger(rig.idx, sid)[0]['started_at_ms'] == start['started_at_ms']


def test_s05_simultaneous_revocation_and_dispatch_only_admits_valid_outcomes(rig):
    sid = rig.enrolled()
    start = rig.reserve(sid)
    _, other = rig.open()
    request = rig.operation(sid, 'off')
    _, off = race(lambda: rig.svc.dispatch_capture(start['start_id'], start['owner_token']),
                  lambda: other.set_source_consent(rig.context, request))
    if not off['ok']:
        assert off['error']['code'] == 'storage_busy' and off['error']['retryable'] is True
        off = other.set_source_consent(rig.context, request)
    ok(off)
    stored = ledger(rig.idx, sid)[0]
    assert source_row(rig.idx, sid)['consent_state'] == 'off'
    assert (stored['state'], len(rig.backend.launches), stored['started_at_ms'] is not None) in (
        ('released', 0, False), ('started', 1, True))
    assert rig.allowance(sid)['charged'] == len(rig.backend.launches)


def test_s09_one_due_poll_across_tick_status_and_manual_refresh(rig):
    sid = rig.register()
    rig.feed.responses[sid] = snapshot([observation(1)])
    _, other = rig.open()
    rig.feed.block = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(rig.svc.poll_source, sid)
        try:
            assert rig.feed.entered.wait(5)
            before = cursor_row(rig.idx, sid)
            assert before['poll_owner_token'] and before['poll_lease_expires_ms'] == rig.clock() + 120_000
            assert other.source_status(rig.context, {'source_id': sid})['ok']
            other.poll_source(sid, manual=True)
            other.detection_tick()
            assert len(rig.feed.calls) == 1
            assert cursor_row(rig.idx, sid)['last_poll_success_ms'] is None
            # This write must succeed while the adapter is blocked: I/O is outside BEGIN.
            ok(other.register_source(rig.context, dict(kind='youtube_playlist',
                url='https://www.youtube.com/playlist?list=PL0000000099')))
        finally:
            rig.feed.release.set()
        pending.result(timeout=5)
    after = cursor_row(rig.idx, sid)
    assert after['revision'] == 1 and after['last_poll_success_ms'] == rig.clock()
    assert after['next_poll_at_ms'] >= rig.clock() + 15 * MINUTE
    assert len(item_rows(rig.idx, sid)) == 1
    for _ in range(3):
        rig.svc.poll_source(sid, manual=True)
        ok(rig.svc.source_status(rig.context, {'source_id': sid}))
    assert len(rig.feed.calls) == 1
    assert cursor_row(rig.idx, sid) == after
    assert rig.backend.launches == []


def test_s09_expired_poll_owner_cannot_commit_late_result(rig):
    sid = rig.register()
    rig.feed.responses[sid] = snapshot([observation(1)], etag='obsolete')
    _, other = rig.open()
    rig.feed.block = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(rig.svc.poll_source, sid)
        try:
            assert rig.feed.entered.wait(5)
            rig.clock.advance(120_001)
            other.reconcile()
            next_poll(rig, sid)
            rig.feed.block = False
            rig.feed.responses[sid] = snapshot([observation(2)], etag='current')
            other.poll_source(sid)
            assert len(rig.feed.calls) == 2
            before = cursor_row(rig.idx, sid)
        finally:
            rig.feed.release.set()
        pending.result(timeout=5)
    assert cursor_row(rig.idx, sid) == before
    assert before['etag'] == 'current'
    assert [row['entry_id'] for row in item_rows(rig.idx, sid)] == [observation(2)['entry_id']]


def test_s09_consent_changed_during_poll_retains_metadata_without_enrollment(rig):
    sid = rig.register()
    rig.consent(sid, 'on')
    rig.feed.responses[sid] = snapshot([observation(1)])
    _, other = rig.open()
    request = rig.operation(sid, 'off')
    rig.feed.block = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(rig.svc.poll_source, sid)
        try:
            assert rig.feed.entered.wait(5)
            ok(other.set_source_consent(rig.context, request))
        finally:
            rig.feed.release.set()
        pending.result(timeout=5)
    item = item_rows(rig.idx, sid)[0]
    assert item['eligibility'] == 'none' and item['first_seen_consent_epoch'] is None
    assert source_row(rig.idx, sid)['initial_enrollment_completed_ms'] is None
    assert ledger(rig.idx, sid) == []


def test_s10_nine_charged_two_connections_race_last_slot_and_no_eleventh(rig):
    sid = rig.enrolled(12)
    remaining = charge_failures(rig, sid, 9)
    assert rig.allowance(sid)['charged'] == 9
    _, other = rig.open()
    before = {row['start_id'] for row in ledger(rig.idx, sid)}
    race(lambda: rig.svc.reserve_capture(sid, remaining[0]['item_id']),
         lambda: other.reserve_capture(sid, remaining[1]['item_id']))
    added = [row for row in ledger(rig.idx, sid) if row['start_id'] not in before]
    assert len(added) == 1 and added[0]['state'] == 'reserved'
    assert rig.allowance(sid)['remaining'] == 0
    winner = added[0]
    rig.svc.dispatch_capture(winner['start_id'], winner['owner_token'])
    winner = rows(rig.idx, 'source_capture_starts', 'start_id=?', (winner['start_id'],))[0]
    rig.failed(winner)
    rig.clock.advance(15 * MINUTE)
    # Remove the one-active-source explanation: the tenth pipeline is now terminal.
    race(lambda: rig.svc.reserve_capture(sid, remaining[2]['item_id']),
         lambda: other.reserve_capture(sid, remaining[1]['item_id']))
    assert len(ledger(rig.idx, sid)) == len(rig.backend.launches) == 10
    assert len({row['slot'] for row in ledger(rig.idx, sid)}) == 10
    assert rig.allowance(sid)['charged'] == 10
    second = rig.enrolled(number=2, entries=[observation(100)])
    rig.start(second)
    assert rig.allowance(second)['charged'] == 1


def test_s09_s10_failure_exhaustion_does_not_suppress_detection(rig):
    sid = rig.enrolled(12)
    remaining = charge_failures(rig, sid, 10)
    before = ledger(rig.idx, sid)
    rig.svc.reserve_capture(sid, remaining[0]['item_id'])
    assert ledger(rig.idx, sid) == before
    next_poll(rig, sid)
    rig.feed.responses[sid] = snapshot([observation(n) for n in range(100, 160)])
    revision = cursor_row(rig.idx, sid)['revision']
    rig.svc.poll_source(sid)
    assert cursor_row(rig.idx, sid)['revision'] == revision + 1
    assert len(item_rows(rig.idx, sid)) == 72, 'Capture capacity discarded observations'
    assert len(ledger(rig.idx, sid)) == 10
    assert rig.allowance(sid)['remaining'] == 0


@pytest.mark.parametrize('instant', [
    '2026-09-07T23:59:59Z',
    '2026-03-08T23:59:59Z',  # US DST transition day.
    '2026-11-01T23:59:59Z',  # US DST rollback day.
])
def test_s12_reservation_cannot_cross_utc_midnight(rig, monkeypatch, instant):
    monkeypatch.setenv('TZ', 'America/Los_Angeles')
    rig.clock.now = at(instant)
    sid = rig.enrolled()
    old = rig.reserve(sid)
    rig.clock.advance(2_000)
    rig.svc.dispatch_capture(old['start_id'], old['owner_token'])
    assert rig.backend.launches == []
    saved = ledger(rig.idx, sid)[0]
    assert saved['state'] == 'released' and saved['started_at_ms'] is None
    new = rig.start(sid)
    assert new['start_id'] != old['start_id'] and new['utc_day'] != old['utc_day']
    assert new['reserved_at_ms'] == new['started_at_ms'] == rig.clock()
    assert rig.allowance(sid)['charged'] == 1


def test_s12_started_pipeline_crosses_midnight_without_second_charge(rig):
    rig.clock.now = at('2026-09-07T23:59:59Z')
    sid = rig.enrolled()
    start = rig.start(sid)
    rig.clock.advance(2_000)
    rig.complete(start)
    saved = ledger(rig.idx, sid)
    assert len(saved) == 1 and saved[0]['utc_day'] == '2026-09-07'
    assert saved[0]['started_at_ms'] == start['started_at_ms']
    assert rig.allowance(sid)['charged'] == 0


def test_s12_failed_retry_charges_its_actual_new_day(rig):
    rig.clock.now = at('2026-09-07T23:59:59Z')
    sid = rig.enrolled(1)
    first = rig.start(sid)
    rig.failed(first)
    rig.clock.advance(15 * MINUTE)
    second = rig.start(sid, item_rows(rig.idx, sid)[0])
    assert first['utc_day'] == '2026-09-07' and second['utc_day'] == '2026-09-08'
    assert first['start_id'] != second['start_id']
    assert item_rows(rig.idx, sid)[0]['actual_starts'] == 2
    assert rig.allowance(sid)['charged'] == 1


def test_s12_clock_rollback_blocks_starts_and_cannot_reuse_newer_day(rig):
    rig.clock.now = at('2026-09-08T01:00:00Z')
    sid = rig.enrolled(3)
    first = rig.start(sid)
    rig.failed(first)
    before_source = copy.deepcopy(source_row(rig.idx, sid))
    before_cursor = copy.deepcopy(cursor_row(rig.idx, sid))
    rig.clock.now = at('2026-09-07T01:00:00Z')
    other = next(row for row in item_rows(rig.idx, sid) if row['item_id'] != first['item_id'])
    rig.svc.reserve_capture(sid, other['item_id'])
    rig.svc.poll_source(sid, manual=True)
    assert len(ledger(rig.idx, sid)) == len(rig.backend.launches) == 1
    assert source_row(rig.idx, sid)['capture_not_before_ms'] >= before_source['capture_not_before_ms']
    assert cursor_row(rig.idx, sid)['next_poll_at_ms'] >= before_cursor['next_poll_at_ms']
    status = ok(rig.svc.source_status(rig.context, {'source_id': sid}))
    assert 'clock_regressed' in str(status)
    rig.clock.now = before_source['capture_not_before_ms']
    rig.start(sid, other)
