"""Independent S13/S14/S15 restart, queue, fencing and deduplication cases.

Crash injection abandons service calls and reopens every connection. Fake worker
liveness is deliberately independent of wall time: lease expiry cannot prove death.
The aligned driver uses the public API described in test_phase3_support.py.
"""

import copy

import pytest

from test_phase3_support import (
    Crash, DAY, MINUTE, item_rows, ledger, migration_dir, observation, ok,
    phase3_isolation, phase3_module, race, rig, rows, snapshot, source_row,
)

IMMUTABLE = ('start_id', 'source_id', 'item_id', 'capture_key', 'consent_epoch',
             'utc_day', 'slot', 'reserved_at_ms', 'reservation_expires_ms')


def saved(rig, start):
    return rows(rig.idx, 'source_capture_starts', 'start_id=?', (start['start_id'],))[0]


@pytest.mark.parametrize('elapsed', [1_000, 120_001])
def test_s13_restart_after_reservation_commit_does_not_duplicate_or_charge(rig, elapsed):
    sid = rig.enrolled()
    reservation = rig.reserve(sid)
    rig.clock.advance(elapsed)
    rig.restart()
    recovered = saved(rig, reservation)
    assert all(recovered[key] == reservation[key] for key in IMMUTABLE)
    assert recovered['started_at_ms'] is None
    assert rig.backend.launches == []
    assert item_rows(rig.idx, sid)[0]['actual_starts'] == 0
    if elapsed > 120_000:
        assert recovered['state'] == 'released'
        rig.svc.dispatch_capture(reservation['start_id'], reservation['owner_token'])
        assert rig.backend.launches == []
        replacement = rig.reserve(sid)
        assert replacement['start_id'] != reservation['start_id']
    else:
        assert recovered['state'] == 'reserved'
        rig.svc.dispatch_capture(recovered['start_id'], recovered['owner_token'])
        rig.svc.dispatch_capture(recovered['start_id'], recovered['owner_token'])
        assert len(ledger(rig.idx, sid)) == len(rig.backend.launches) == 1
        assert rig.allowance(sid)['charged'] == 1


def test_s13_restart_after_started_commit_before_backend_ack_keeps_uncertain_charge(rig):
    sid = rig.enrolled()
    reservation = rig.reserve(sid)
    rig.faults.crash_at = 'after_started_commit'
    with pytest.raises(Crash, match='after_started_commit'):
        rig.svc.dispatch_capture(reservation['start_id'], reservation['owner_token'])
    first = saved(rig, reservation)
    assert first['state'] == 'started' and first['started_at_ms'] is not None
    assert rig.backend.launches == []
    rig.clock.advance(DAY)
    rig.restart()
    recovered = saved(rig, reservation)
    assert recovered['state'] == 'uncertain'
    assert recovered['started_at_ms'] == first['started_at_ms']
    assert all(recovered[key] == reservation[key] for key in IMMUTABLE)
    rig.svc.dispatch_capture(reservation['start_id'], reservation['owner_token'])
    for item in item_rows(rig.idx, sid):
        rig.svc.reserve_capture(sid, item['item_id'])
    assert rig.backend.launches == [] and len(ledger(rig.idx, sid)) == 1
    assert sum(row['actual_starts'] for row in item_rows(rig.idx, sid)) == 1
    assert ledger(rig.idx, sid)[0]['utc_day'] == '2026-09-07'


@pytest.mark.parametrize('liveness', ['unknown', 'alive'])
def test_s13_surviving_or_unknown_worker_blocks_replacement_after_lease_expiry(rig, liveness):
    sid = rig.enrolled()
    start = rig.start(sid)
    rig.backend.workers[start['backend_id']] = liveness
    rig.clock.advance(2 * DAY)
    rig.restart()
    recovered = saved(rig, start)
    assert recovered['state'] in ('started', 'uncertain')
    before = copy.deepcopy(ledger(rig.idx, sid))
    # A failure callback without proof that the worker stopped cannot free it.
    rig.svc.fail_capture(start['start_id'], recovered['owner_token'], code='download_failed')
    for item in item_rows(rig.idx, sid):
        rig.svc.reserve_capture(sid, item['item_id'])
    assert saved(rig, start)['state'] in ('started', 'uncertain')
    assert len(ledger(rig.idx, sid)) == len(before) == len(rig.backend.launches) == 1
    assert saved(rig, start)['started_at_ms'] == start['started_at_ms']
    rig.backend.workers[start['backend_id']] = 'stopped'
    rig.svc.fail_capture(start['start_id'], recovered['owner_token'], code='download_failed')
    assert saved(rig, start)['state'] == 'failed'
    rig.clock.advance(15 * MINUTE)
    retry_item = next(row for row in item_rows(rig.idx, sid) if row['item_id'] == start['item_id'])
    retry = rig.start(sid, retry_item)
    assert retry['start_id'] != start['start_id']
    assert retry['utc_day'] != start['utc_day']


def test_s14_crash_between_queue_insert_and_binding_has_no_orphan_launch(rig):
    sid = rig.enrolled()
    reservation = rig.reserve(sid)
    rig.faults.crash_at = 'after_backend_insert_before_binding'
    with pytest.raises(Crash, match='after_backend_insert_before_binding'):
        rig.svc.dispatch_capture(reservation['start_id'], reservation['owner_token'])
    assert 'after_backend_insert_before_binding' in rig.faults.seen
    assert rows(rig.idx, 'astra_fake_jobs') == [], 'Durable queue insertion escaped rollback'
    assert rig.backend.launches == []
    stored = saved(rig, reservation)
    assert stored['backend_id'] is None and stored['backend_kind'] is None
    rig.restart()
    recovered = saved(rig, reservation)
    if recovered['started_at_ms'] is None:
        rig.svc.dispatch_capture(recovered['start_id'], recovered['owner_token'])
        assert len(rows(rig.idx, 'astra_fake_jobs')) == len(rig.backend.launches) == 1
    else:
        assert recovered['state'] == 'uncertain'
        assert rig.backend.launches == []
        assert rig.allowance(sid)['charged'] == 1


def test_s14_replayed_start_has_one_durable_job_and_one_actual_start(rig):
    sid = rig.enrolled()
    reservation = rig.reserve(sid)
    _, other = rig.open()
    race(lambda: rig.svc.dispatch_capture(reservation['start_id'], reservation['owner_token']),
         lambda: other.dispatch_capture(reservation['start_id'], reservation['owner_token']))
    start = saved(rig, reservation)
    assert start['started_at_ms'] is not None
    assert len(rig.backend.launches) == len(rows(rig.idx, 'astra_fake_jobs')) == 1
    assert rows(rig.idx, 'astra_fake_jobs')[0]['start_id'] == reservation['start_id']
    assert start['backend_id'] == reservation['start_id']
    rig.svc.dispatch_capture(reservation['start_id'], reservation['owner_token'])
    assert saved(rig, reservation)['started_at_ms'] == start['started_at_ms']
    assert sum(row['actual_starts'] for row in item_rows(rig.idx, sid)) == 1
    assert all(saved(rig, reservation)[key] == reservation[key] for key in IMMUTABLE)


def test_s14_obsolete_owner_cannot_dispatch_fail_or_publish_current_attempt(rig):
    sid = rig.enrolled()
    reservation = rig.reserve(sid)
    stale = 'z' * 43
    assert stale != reservation['owner_token']
    before = copy.deepcopy(saved(rig, reservation))
    rig.svc.dispatch_capture(reservation['start_id'], stale)
    assert saved(rig, reservation) == before and rig.backend.launches == []
    rig.svc.dispatch_capture(reservation['start_id'], reservation['owner_token'])
    start = saved(rig, reservation)
    rig.publication.stage(rig.idx, start)
    before = copy.deepcopy(saved(rig, start))
    rig.backend.workers[start['backend_id']] = 'stopped'
    rig.svc.complete_capture(start['start_id'], stale)
    rig.svc.fail_capture(start['start_id'], stale, code='download_failed')
    assert saved(rig, start) == before
    assert rows(rig.idx, 'source_classification_outbox') == []
    rig.svc.complete_capture(start['start_id'], start['owner_token'])
    assert saved(rig, start)['state'] == 'succeeded'


def test_s14_late_callback_cannot_reset_terminal_row_or_mutate_new_attempt(rig):
    sid = rig.enrolled(1)
    first = rig.start(sid)
    rig.failed(first)
    rig.clock.advance(15 * MINUTE)
    second = rig.start(sid, item_rows(rig.idx, sid)[0])
    before = copy.deepcopy(ledger(rig.idx, sid))
    rig.svc.dispatch_capture(first['start_id'], first['owner_token'])
    rig.svc.complete_capture(first['start_id'], first['owner_token'])
    rig.svc.fail_capture(first['start_id'], first['owner_token'], code='obsolete')
    assert ledger(rig.idx, sid) == before
    assert saved(rig, second)['state'] == 'started'
    assert len(rig.backend.launches) == 2
    assert rows(rig.idx, 'source_classification_outbox') == []


def test_s04_s13_restart_and_toggle_preserve_three_actual_attempt_limit(rig):
    sid = rig.enrolled(1)
    starts = []
    for attempt in range(3):
        item = item_rows(rig.idx, sid)[0]
        start = rig.start(sid, item)
        starts.append(start)
        rig.failed(start)
        assert item_rows(rig.idx, sid)[0]['actual_starts'] == attempt + 1
        rig.consent(sid, 'off')
        rig.restart()
        assert item_rows(rig.idx, sid)[0]['actual_starts'] == attempt + 1
        rig.consent(sid, 'on')
        rig.clock.advance((15 if attempt == 0 else 60) * MINUTE)
        rig.svc.poll_source(sid)  # Complete resume without enlarging the cohort.
    rig.clock.advance(DAY)
    rig.svc.reserve_capture(sid, item_rows(rig.idx, sid)[0]['item_id'])
    assert len(ledger(rig.idx, sid)) == len(rig.backend.launches) == 3
    assert item_rows(rig.idx, sid)[0]['actual_starts'] == 3
    assert source_row(rig.idx, sid)['back_catalog_enrolled'] == 1
    assert all(saved(rig, start)['state'] == 'failed' for start in starts)
    assert all(saved(rig, start)['started_at_ms'] == start['started_at_ms'] for start in starts)


def three_sources(rig):
    return [rig.enrolled(number=n, kind=kind, entries=[observation(7)]) for n, kind in (
        (1, 'youtube_channel'), (2, 'youtube_playlist'), (3, 'youtube_playlist'))]


def test_s15_same_video_channel_two_playlists_race_and_charge_only_winner(rig):
    sources = three_sources(rig)
    _, other = rig.open()
    race(lambda: rig.svc.reserve_capture(sources[0], item_rows(rig.idx, sources[0])[0]['item_id']),
         lambda: other.reserve_capture(sources[1], item_rows(rig.idx, sources[1])[0]['item_id']))
    starts = ledger(rig.idx)
    assert len(starts) == 1 and starts[0]['state'] == 'reserved'
    winner = starts[0]
    losing_sources = [sid for sid in sources if sid != winner['source_id']]
    for sid in losing_sources:
        rig.svc.reserve_capture(sid, item_rows(rig.idx, sid)[0]['item_id'])
        item = item_rows(rig.idx, sid)[0]
        assert item['state'] == 'eligible' and item['blocked_reason'] == 'capture_in_progress_elsewhere'
        assert rig.allowance(sid)['charged'] == 0
    rig.svc.dispatch_capture(winner['start_id'], winner['owner_token'])
    winner = saved(rig, winner)
    vid = rig.complete(winner)
    rig.svc.reconcile()
    for sid in sources:
        rig.svc.reserve_capture(sid, item_rows(rig.idx, sid)[0]['item_id'])
        item = item_rows(rig.idx, sid)[0]
        assert item['state'] == 'committed' and item['video_id'] == vid
        assert rig.allowance(sid)['charged'] == int(sid == winner['source_id'])
    assert len(ledger(rig.idx)) == len(rows(rig.idx, 'yoinks')) == len(rig.backend.launches) == 1
    assert ledger(rig.idx)[0]['state'] == 'succeeded'
    assert len(rows(rig.idx, 'source_classification_outbox')) == 1


def test_s15_preexisting_manual_capture_links_without_charge_or_new_handoff(rig):
    vid = rig.publication.stage(rig.idx, {'capture_key': 'youtube:' + observation(7)['entry_id']})
    sid = rig.enrolled(entries=[observation(7)])
    item = item_rows(rig.idx, sid)[0]
    rig.svc.reserve_capture(sid, item['item_id'])
    linked = item_rows(rig.idx, sid)[0]
    assert linked['state'] == 'committed' and linked['video_id'] == vid
    assert ledger(rig.idx) == rows(rig.idx, 'source_classification_outbox') == []
    status = ok(rig.svc.source_status(rig.context, {'source_id': sid}))
    assert status['items'][0]['classification']['state'] == 'not_requested'
    assert rig.backend.launches == []


def test_s15_concurrent_manual_capture_lock_waits_then_links_without_charge(rig):
    from test_phase3_integration import server_parts
    sid = rig.enrolled(entries=[observation(7)])
    item = item_rows(rig.idx, sid)[0]
    ns = server_parts(rig)
    backend = ns['_ServerCaptureBackend']()
    service = rig.module.SourceSubscriptionService(
        rig.idx, clock=rig.clock, adapters=rig.svc.adapters, backend=backend)
    ns['_source_service'] = lambda: service
    # The existing manual dispatcher holds this lock through extraction.
    # A dormant thread records scheduling without running extraction or a model.
    with ns['_extract_lock']:
        service.advance_source(sid, item_id=item['item_id'])
        assert all(row['started_at_ms'] is None for row in ledger(rig.idx, sid)), (
            'Standing capture charged while manual extraction owns the dispatcher')
        assert ns['launches'] == []
        vid = rig.publication.stage(rig.idx, {'capture_key': item['capture_key']})
    service.reconcile_on_startup()
    service.claim_start(sid, item_id=item['item_id'])
    linked = item_rows(rig.idx, sid)[0]
    assert linked['state'] == 'committed' and linked['video_id'] == vid
    assert rig.allowance(sid)['charged'] == 0
    assert rows(rig.idx, 'source_classification_outbox') == []


@pytest.mark.parametrize('standing_won', [True, False], ids=['standing-success', 'manual-no-ledger'])
def test_s15_deletion_archive_and_reregistration_preserve_tombstones(rig, standing_won):
    if not standing_won:
        rig.publication.stage(rig.idx, {'capture_key': 'youtube:' + observation(7)['entry_id']})
    sid = rig.enrolled(entries=[observation(7)])
    if standing_won:
        start = rig.start(sid)
        vid = rig.complete(start)
    else:
        rig.svc.reserve_capture(sid, item_rows(rig.idx, sid)[0]['item_id'])
        vid = item_rows(rig.idx, sid)[0]['video_id']
    before = source_row(rig.idx, sid)
    charged = sum(row['started_at_ms'] is not None for row in ledger(rig.idx))
    with rig.idx.write_transaction() as conn:
        conn.execute('DELETE FROM yoinks WHERE video_id=?', (vid,))
    rig.svc.corpus_deleted(vid)
    assert item_rows(rig.idx, sid)[0]['state'] == 'deleted'
    rig.svc.archive_source(rig.context, {'source_id': sid})
    assert source_row(rig.idx, sid)['archived'] == 1
    assert rig.register() == sid
    restored = source_row(rig.idx, sid)
    assert restored['archived'] == 0 and restored['consent_state'] == 'off'
    assert restored['back_catalog_enrolled'] == before['back_catalog_enrolled']
    rig.consent(sid, 'on')
    rig.clock.advance(DAY)
    rig.feed.responses[sid] = snapshot([observation(7)])
    rig.svc.poll_source(sid)
    rig.svc.reserve_capture(sid, item_rows(rig.idx, sid)[0]['item_id'])
    another = rig.enrolled(number=2, entries=[observation(7)])
    rig.svc.reserve_capture(another, item_rows(rig.idx, another)[0]['item_id'])
    rig.restart()
    assert rows(rig.idx, 'yoinks', 'video_id=?', (vid,)) == []
    assert len(rig.backend.launches) == charged
    assert sum(row['started_at_ms'] is not None for row in ledger(rig.idx)) == charged
    assert sum(row['state'] == 'succeeded' for row in ledger(rig.idx)) == int(standing_won)
    assert item_rows(rig.idx, sid)[0]['state'] == 'deleted'
