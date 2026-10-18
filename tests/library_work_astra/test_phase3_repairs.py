"""AS-2 regressions for incomplete AS-01/02/03/06 repairs.

Uses the existing guarded rig and unchanged production class bodies. No helper,
network, child process or model runs. Assertions express the contract; known
candidate failures are deliberately neither skipped nor marked xfail.
"""

import json

import pytest

from test_phase3_integration import server_parts
from test_phase3_support import (
    Crash, item_rows, ledger, migration_dir, ok, phase3_isolation,
    phase3_module, rig, rows, snapshot,
)


def production_backend(rig):
    ns = server_parts(rig)
    backend = ns['_ServerCaptureBackend']()
    rig.svc.service.backend = backend
    return ns, backend


def production_start(rig, sid):
    ns, backend = production_backend(rig)
    claim = rig.reserve(sid)
    started = rig.svc.mark_started(claim['start_id'], claim['owner_token'])
    assert started['outcome'] == 'started'
    return started['start'], ns, backend


@pytest.mark.parametrize('damage', ['sidecar', 'provenance', 'timing', 'clips'])
def test_as2_s16_production_inspection_rejects_invalid_evidence(rig, damage):
    """A row count and file existence cannot certify the required artifacts."""
    sid = rig.enrolled(1)
    start, ns, _backend = production_start(rig, sid)
    vid = rig.publication.stage(rig.idx, start)
    if damage == 'sidecar':
        rig.publication.paths(vid)[1].write_text('{broken JSON', encoding='utf-8')
    else:
        with rig.idx.write_transaction() as conn:
            if damage == 'provenance':
                conn.execute("UPDATE yoinks SET metadata_json='{}', source_type='episode', "
                             "platform='podcast' WHERE video_id=?", (vid,))
            elif damage == 'timing':
                conn.execute('UPDATE citations SET timestamp_start=-9, timestamp_end=-10 '
                             'WHERE video_id=?', (vid,))
            else:
                conn.execute('UPDATE clips SET start=99, end=100, text=? WHERE video_id=?',
                             ('Unrelated to the 12.5-21.75 second citation.', vid))
    ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='completed')
    result = rig.svc.service.complete_capture(start['start_id'], start['owner_token'], vid)
    assert result['outcome'] != 'succeeded', result
    assert rows(rig.idx, 'source_classification_outbox') == []


def test_as2_s16_timed_screenshot_does_not_get_the_no_timed_evidence_exception(rig):
    """The v1 exception says no timed evidence, not no transcript citations."""
    sid = rig.enrolled(1)
    start, ns, _backend = production_start(rig, sid)
    vid = rig.publication.stage(rig.idx, start)
    shot = rig.root / 'frame.jpg'
    shot.write_bytes(b'synthetic screenshot fixture')
    with rig.idx.write_transaction() as conn:
        conn.execute('DELETE FROM clips WHERE video_id=?', (vid,))
        conn.execute("UPDATE citations SET kind='screenshot', text=NULL, timestamp_end=NULL, "
                     'file_path=? WHERE video_id=?', (str(shot), vid))
    ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='completed')
    result = rig.svc.service.complete_capture(start['start_id'], start['owner_token'], vid)
    assert result['outcome'] != 'succeeded', result
    assert rows(rig.idx, 'source_classification_outbox') == []


def test_as2_s13_publication_does_not_release_an_unknown_executor(rig):
    sid = rig.enrolled(2)
    start, _ns, backend = production_start(rig, sid)
    vid = rig.publication.stage(rig.idx, start)
    assert backend.probe(start) == 'unknown'
    result = rig.svc.service.complete_capture(start['start_id'], start['owner_token'], vid)
    assert ledger(rig.idx, sid)[0]['state'] in ('started', 'uncertain'), result
    rig.clock.advance(15 * 60_000)
    assert rig.svc.claim_start(sid)['outcome'] == 'in_flight'


def test_as2_s13_empty_registry_does_not_verify_worker_finished_proof(rig):
    sid = rig.enrolled(1)
    start, _ns, backend = production_start(rig, sid)
    assert backend.probe(start) == 'unknown'
    proof = rig.module.CompletionProof(
        start['start_id'], start['owner_token'], backend.kind, 'worker_finished')
    result = rig.svc.fail_capture(start['start_id'], start['owner_token'],
                                  'late_callback', proof=proof)
    assert result['outcome'] == 'worker_not_stopped', result
    assert ledger(rig.idx, sid)[0]['state'] == 'uncertain'


def test_as2_s13_duck_backend_fallback_does_not_certify_a_running_worker(rig):
    """The supplied asynchronous fake is the backend affected by Fable's fallback."""
    sid = rig.enrolled(1)
    start = rig.start(sid)
    assert rig.backend.probe(start) == 'running'
    proof = rig.module.CompletionProof(
        start['start_id'], start['owner_token'], rig.backend.kind, 'unsupported_claim')
    result = rig.svc.fail_capture(start['start_id'], start['owner_token'],
                                  'late_callback', proof=proof)
    assert result['outcome'] == 'worker_not_stopped', result
    assert ledger(rig.idx, sid)[0]['state'] == 'uncertain'


def test_as2_s14_terminal_start_payload_cannot_dispatch_again(rig):
    sid = rig.enrolled(1)
    ns, backend = production_backend(rig)
    claim = rig.reserve(sid)
    started = rig.svc.mark_started(claim['start_id'], claim['owner_token'])
    # A terminal result arrives before a delayed dispatcher uses its old payload.
    ns['_jobs']['finished'] = dict(source_start_id=claim['start_id'], state='completed')
    assert rig.svc.fail_capture(claim['start_id'], claim['owner_token'],
                               'worker_lost')['outcome'] == 'failed'
    try:
        rig.svc.execute_started(started)
        assert ns['launches'] == [], 'The real backend scheduled a terminal attempt'
    finally:
        backend.release(started['start'])


def test_as2_s15_lock_error_keeps_start_uncharged(rig, monkeypatch):
    sid = rig.enrolled(1)
    ns, backend = production_backend(rig)

    def unavailable(*args, **kwargs):
        raise PermissionError('fixture capture lock directory unavailable')

    monkeypatch.setattr(rig.module.CaptureLock, 'try_acquire', unavailable)
    try:
        result = rig.svc.advance_source(sid)
        assert result['outcome'] == 'capture_busy', result
        assert all(row['started_at_ms'] is None for row in ledger(rig.idx, sid))
        assert ns['launches'] == []
    finally:
        for row in ledger(rig.idx, sid):
            backend.release(row)


def podcast_attempt(rig):
    sid = ok(rig.svc.register_source(rig.context, dict(
        kind='podcast_rss', url='https://show.example/as2.xml')))['source']['source_id']
    rig.consent(sid, 'on')
    rig.feed.responses[sid] = snapshot([dict(
        entry_id='as2-guid', title='AS-2 synthetic episode',
        canonical_url='https://show.example/as2',
        metadata=dict(identity_method='guid', audio_url='https://show.example/as2.mp3'))])
    rig.svc.poll_source(sid)
    start = rig.start(sid)
    episode_id = item_rows(rig.idx, sid)[0]['legacy_episode_id']
    transcript = rig.root / 'as2.transcript.json'
    transcript.write_text(json.dumps(dict(model='synthetic', segments=[dict(
        start=12.5, end=21.75, text='AS-2 local publication evidence.')])), encoding='utf-8')
    with rig.idx.write_transaction() as conn:
        conn.execute("UPDATE podcast_episodes SET transcript_status='done', "
                     'transcript_local_path=? WHERE id=?', (str(transcript), episode_id))
    return sid, start, episode_id


def test_as2_s16_recovery_reuses_valid_files_before_corpus_upsert(rig, monkeypatch):
    import podcasts

    sid, start, episode_id = podcast_attempt(rig)

    def crash_before_upsert(*args, **kwargs):
        raise Crash('as2_before_corpus_upsert')

    with monkeypatch.context() as patch:
        patch.setattr(rig.idx, 'upsert_yoink', crash_before_upsert)
        with pytest.raises(Crash, match='as2_before_corpus_upsert'):
            podcasts.episode_to_corpus(rig.idx, episode_id, data_root=rig.root)
    assert rows(rig.idx, 'yoinks') == []
    assert list(rig.root.rglob('*.md')), 'The real publisher wrote its corpus file'
    ns, _backend = production_backend(rig)
    ns['podcasts'] = podcasts
    ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='completed')
    result = rig.svc.reconcile_start(start['start_id'])
    assert result['outcome'] == 'succeeded', result
    assert len(ledger(rig.idx, sid)) == 1
    assert len(rows(rig.idx, 'source_classification_outbox')) == 1


def test_as2_s15_podcast_publisher_checks_reverse_legacy_episode_link(rig):
    import podcasts

    _sid, _start, episode_id = podcast_attempt(rig)
    incoming = podcasts.get_episode_with_feed(rig.idx, episode_id)
    vid, _suffix = podcasts._episode_corpus_id(incoming)
    other_feed = podcasts.add_feed(rig.idx, 'https://other.example/as2.xml')['id']
    podcasts.upsert_episodes(rig.idx, other_feed, [dict(
        guid='different-guid', title='Other episode', audio_url='https://other.example/e.mp3')])
    other = podcasts.list_episodes(rig.idx, feed_id=other_feed)[0]
    rig.idx.upsert_yoink(dict(video_id=vid, slug=vid, title='Existing legacy episode',
        topic='Unfiled', yoinked_at='2026-09-07', source_type='episode', platform='podcast',
        corpus_path=str(rig.root / 'other.md'), sidecar_path=str(rig.root / 'other.json'),
        metadata_json='{}'))
    with rig.idx.write_transaction() as conn:
        conn.execute('UPDATE podcast_episodes SET yoink_video_id=? WHERE id=?', (vid, other['id']))
    before = rig.idx.get_yoink(vid)
    with pytest.raises(podcasts.CorpusIdentityConflict):
        podcasts.episode_to_corpus(rig.idx, episode_id, data_root=rig.root)
    assert rig.idx.get_yoink(vid) == before
