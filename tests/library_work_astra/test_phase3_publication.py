"""S16/S17: durable publication prefixes and real Phase 2 prepare_run replay.

These tests exercise subscription reconciliation against fake publication
completion evidence. They do not certify production file/extractor crash safety;
AN must test the real publication adapter and interprocess execution lock.
Taxonomy approval and prepare_run below are real local Phase 2 operations. There
is no assignment claim, client, reasoning, label submission, or apply operation.
"""

import copy
import json

import pytest

from test_phase3_support import (
    Crash, Publication, digest, item_rows, ledger, migration_dir, ok,
    phase3_isolation, phase3_module, race, rig, rows,
)

PROMPT_HASH = digest('Astra fixture assignment prompt; never executed.')


def configure(rig):
    library = rig.idx.library_service()
    approved = library.approve_taxonomy(rig.library_context, dict(
        version_id='astra-standing-v1', nodes=[dict(
            shelf_id='astra-testing', path=['Testing'], definition='Fixture tests',
            include=['test evidence'], exclude=['unrelated material'])]))
    assert approved['ok'], approved
    ok(rig.svc.configure_classification_policy(rig.context, dict(
        version_id='astra-standing-v1', prompt_hash=PROMPT_HASH)))
    return library


def one_handoff(rig, key, vid):
    outbox = rows(rig.idx, 'source_classification_outbox', 'capture_key=?', (key,))
    assert len(outbox) == 1
    out = outbox[0]
    assert out['state'] == 'enqueued'
    assert out['run_id'] == 'ss_' + digest(key)
    assert out['video_id'] == vid and out['version_id'] == 'astra-standing-v1'
    assert out['prompt_hash'] == PROMPT_HASH
    runs = rows(rig.idx, 'library_runs', 'run_id=?', (out['run_id'],))
    manifest = rows(rig.idx, 'library_manifest', 'run_id=?', (out['run_id'],))
    work = rows(rig.idx, 'library_work', 'run_id=?', (out['run_id'],))
    assert len(runs) == len(manifest) == len(work) == 1
    assert runs[0]['version_id'] == out['version_id']
    assert json.loads(runs[0]['policy_json'])['prompt_hash'] == out['prompt_hash']
    assert manifest[0]['video_id'] == work[0]['video_id'] == vid
    assert manifest[0]['source_revision'] == out['source_revision']
    assert work[0]['work_id'] == out['work_id'] and work[0]['state'] == 'ready'
    packet = json.loads(work[0]['packet_json'])
    assert packet['source_revision'] == out['source_revision']
    assert rows(rig.idx, 'library_attempts') == rows(rig.idx, 'item_shelves') == []
    return out


@pytest.mark.parametrize('boundary', Publication.stages)
def test_s16_each_publication_prefix_waits_for_complete_evidence(rig, boundary):
    configure(rig)
    sid = rig.enrolled(1)
    start = rig.start(sid)
    vid = rig.publication.stage(rig.idx, start, through=boundary)
    rig.backend.workers[start['backend_id']] = 'unknown'
    rig.restart()
    rig.svc.dispatch_classification()
    if boundary != 'complete_publication':
        assert rows(rig.idx, 'source_classification_outbox') == []
        assert rows(rig.idx, 'library_work') == []
        assert ledger(rig.idx, sid)[0]['state'] in ('started', 'uncertain')
        assert item_rows(rig.idx, sid)[0]['state'] != 'committed'
        # The original worker can finish local publication; this is not recapture.
        rig.publication.stage(rig.idx, start)
    rig.backend.workers[start['backend_id']] = 'stopped'
    rig.svc.reconcile()
    rig.svc.dispatch_classification()
    one_handoff(rig, start['capture_key'], vid)
    assert len(rig.backend.launches) == len(ledger(rig.idx, sid)) == 1
    assert ledger(rig.idx, sid)[0]['started_at_ms'] == start['started_at_ms']
    assert ledger(rig.idx, sid)[0]['state'] == 'succeeded'
    assert item_rows(rig.idx, sid)[0]['state'] == 'committed'
    item = rows(rig.idx, 'yoinks', 'video_id=?', (vid,))[0]
    assert (item['source_type'], item['platform']) == ('video', 'youtube')
    url = f'https://www.youtube.com/watch?v={vid}'
    assert json.loads(item['metadata_json'])['url'] == url
    citation = rows(rig.idx, 'citations', 'video_id=?', (vid,))[0]
    clip = rows(rig.idx, 'clips', 'video_id=?', (vid,))[0]
    assert citation['source_url'] == url
    assert (citation['timestamp_start'], citation['timestamp_end']) == (12.5, 21.75)
    assert (clip['start'], clip['end']) == (12.5, 21.75)
    status = ok(rig.svc.source_status(rig.context, {'source_id': sid}))
    assert status['items'][0]['classification']['state'] == 'waiting_for_client'


def test_s16_real_podcast_upsert_crash_does_not_enqueue(rig, monkeypatch):
    """Real publisher, transcript and files; stop before its citation/clip commit."""
    import podcasts
    from test_phase3_support import snapshot

    configure(rig)
    sid = ok(rig.svc.register_source(rig.context, dict(
        kind='podcast_rss', url='https://show.example/feed.xml')))['source']['source_id']
    rig.consent(sid, 'on')
    rig.feed.responses[sid] = snapshot([dict(
        entry_id='publication-fixture', title='Publication fixture',
        canonical_url='https://show.example/episode',
        metadata=dict(identity_method='guid', audio_url='https://show.example/fixture.mp3'))])
    rig.svc.poll_source(sid)
    start = rig.start(sid)
    episode_id = item_rows(rig.idx, sid)[0]['legacy_episode_id']
    transcript = rig.root / 'synthetic.transcript.json'
    transcript.write_text(json.dumps(dict(model='synthetic', language='en', segments=[dict(
        start=12.5, end=21.75, text='Durable publication fixture.')])), encoding='utf-8')
    with rig.idx.write_transaction() as conn:
        conn.execute("UPDATE podcast_episodes SET transcript_status='done', transcript_local_path=? WHERE id=?",
                     (str(transcript), episode_id))

    def stop_before_citations(*args, **kwargs):
        raise Crash('real_podcast_after_upsert')

    with monkeypatch.context() as patch:
        patch.setattr(rig.idx, 'insert_citations', stop_before_citations)
        with pytest.raises(Crash, match='real_podcast_after_upsert'):
            podcasts.episode_to_corpus(rig.idx, episode_id, data_root=rig.root)
    assert len(rows(rig.idx, 'yoinks')) == 1
    assert rows(rig.idx, 'citations') == rows(rig.idx, 'clips') == []
    rig.backend.workers[start['backend_id']] = 'unknown'
    rig.restart()
    rig.svc.dispatch_classification()
    assert rows(rig.idx, 'source_classification_outbox') == rows(rig.idx, 'library_work') == []
    assert ledger(rig.idx, sid)[0]['state'] in ('started', 'uncertain')


def test_s16_outbox_write_failure_keeps_published_item_visible_and_repairs_once(rig):
    configure(rig)
    sid = rig.enrolled(1)
    start = rig.start(sid)
    vid = rig.publication.stage(rig.idx, start)
    rig.backend.workers[start['backend_id']] = 'stopped'
    with rig.idx.write_transaction() as conn:
        conn.execute("""CREATE TRIGGER astra_fail_outbox BEFORE INSERT ON source_classification_outbox
                        BEGIN SELECT RAISE(ABORT, 'fixture outbox unavailable'); END""")
    try:
        # Storage failures may be surfaced as an error envelope or sqlite3.Error.
        import sqlite3
        try:
            rig.svc.complete_capture(start['start_id'], start['owner_token'])
        except sqlite3.Error:
            pass
        assert rows(rig.idx, 'yoinks', 'video_id=?', (vid,))
        assert rows(rig.idx, 'source_classification_outbox') == rows(rig.idx, 'library_work') == []
        assert len(ledger(rig.idx, sid)) == 1 and ledger(rig.idx, sid)[0]['started_at_ms'] is not None
    finally:
        with rig.idx.write_transaction() as conn:
            conn.execute('DROP TRIGGER astra_fail_outbox')
    rig.restart()
    rig.svc.dispatch_classification()
    original = copy.deepcopy(one_handoff(rig, start['capture_key'], vid))
    rig.restart()
    rig.svc.dispatch_classification()
    assert one_handoff(rig, start['capture_key'], vid) == original
    assert len(rig.backend.launches) == 1


def test_s16_crash_after_outbox_commit_replays_without_second_handoff(rig):
    configure(rig)
    sid = rig.enrolled(1)
    start = rig.start(sid)
    vid = rig.publication.stage(rig.idx, start)
    rig.backend.workers[start['backend_id']] = 'stopped'
    rig.faults.crash_at = 'after_outbox_commit'
    with pytest.raises(Crash, match='after_outbox_commit'):
        rig.svc.complete_capture(start['start_id'], start['owner_token'])
    assert len(rows(rig.idx, 'source_classification_outbox')) == 1
    assert ledger(rig.idx, sid)[0]['state'] == 'succeeded'
    rig.restart()
    rig.svc.dispatch_classification()
    one_handoff(rig, start['capture_key'], vid)
    rig.svc.reconcile()
    rig.svc.dispatch_classification()
    assert len(rows(rig.idx, 'source_classification_outbox')) == len(rows(rig.idx, 'library_work')) == 1


def test_s17_prepare_run_commit_before_ack_and_two_dispatcher_replay(rig):
    configure(rig)
    sid = rig.enrolled(1)
    start = rig.start(sid)
    vid = rig.complete(start)
    rig.faults.crash_at = 'after_prepare_run_before_outbox_ack'
    with pytest.raises(Crash, match='after_prepare_run_before_outbox_ack'):
        rig.svc.dispatch_classification()
    outbox = rows(rig.idx, 'source_classification_outbox')[0]
    assert outbox['state'] != 'enqueued'
    assert outbox['run_id'] == 'ss_' + digest(start['capture_key'])
    before = {name: rows(rig.idx, name) for name in ('library_runs', 'library_manifest', 'library_work')}
    assert all(len(values) == 1 for values in before.values()), 'Fault hook did not follow real prepare_run commit'
    rig.restart()
    _, other = rig.open()
    race(rig.svc.dispatch_classification, other.dispatch_classification)
    one_handoff(rig, start['capture_key'], vid)
    assert {name: rows(rig.idx, name) for name in before} == before
    assert len(rig.backend.launches) == 1


@pytest.mark.parametrize('mismatch', ['video', 'taxonomy', 'prompt', 'source_revision'])
def test_s17_conflicting_deterministic_run_is_blocked_not_adopted(rig, mismatch):
    library = configure(rig)
    sid = rig.enrolled(1)
    start = rig.start(sid)
    vid = rig.complete(start)
    run_id = 'ss_' + digest(start['capture_key'])
    target, version, prompt = vid, 'astra-standing-v1', PROMPT_HASH
    if mismatch == 'video':
        target = rig.publication.stage(rig.idx, {'capture_key': 'youtube:v0000000999'})
    if mismatch == 'taxonomy':
        result = library.approve_taxonomy(rig.library_context, dict(version_id='astra-other-v1', nodes=[dict(
            shelf_id='other', path=['Other'], definition='Different fixture taxonomy',
            include=['other'], exclude=['tests'])]))
        assert result['ok'], result
        version = 'astra-other-v1'
    if mismatch == 'prompt':
        prompt = digest('different approved fixture prompt')
    if mismatch == 'source_revision':
        # Freeze the outbox first, then alter evidence before creating the collision.
        rig.faults.crash_at = 'after_prepare_run_before_outbox_ack'
        with pytest.raises(Crash):
            rig.svc.dispatch_classification()
        # Corrupt the existing manifest binding as an adversarial recovered DB fixture.
        with rig.idx.write_transaction() as conn:
            conn.execute('UPDATE library_manifest SET source_revision=? WHERE run_id=?', ('f' * 64, run_id))
    else:
        result = library.prepare_run(rig.library_context, dict(
            run_id=run_id, version_id=version, prompt_hash=prompt, video_ids=[target]))
        assert result['ok'], result
    before = {name: rows(rig.idx, name) for name in ('library_runs', 'library_manifest', 'library_work')}
    rig.svc.dispatch_classification()
    outbox = rows(rig.idx, 'source_classification_outbox')[0]
    assert outbox['state'] == 'blocked' and outbox['last_error_code'] == 'classification_conflict'
    assert {name: rows(rig.idx, name) for name in before} == before
    assert rows(rig.idx, 'yoinks', 'video_id=?', (vid,))
    assert len(rig.backend.launches) == 1


def test_s17_frozen_existing_manifest_is_unchanged_by_new_capture(rig):
    library = configure(rig)
    existing = rig.publication.stage(rig.idx, {'capture_key': 'youtube:v0000000999'})
    result = library.prepare_run(rig.library_context, dict(
        run_id='fixture-measured-frozen', version_id='astra-standing-v1',
        prompt_hash=PROMPT_HASH, video_ids=[existing]))
    assert result['ok'], result
    before = {table: rows(rig.idx, table, 'run_id=?', ('fixture-measured-frozen',))
              for table in ('library_runs', 'library_manifest', 'library_work')}
    sid = rig.enrolled(1)
    start = rig.start(sid)
    vid = rig.complete(start)
    rig.svc.dispatch_classification()
    one_handoff(rig, start['capture_key'], vid)
    after = {table: rows(rig.idx, table, 'run_id=?', ('fixture-measured-frozen',)) for table in before}
    assert after == before
    assert len(rows(rig.idx, 'library_manifest')) == len(rows(rig.idx, 'library_work')) == 2
