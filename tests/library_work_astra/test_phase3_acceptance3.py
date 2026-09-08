"""AS-3 regressions: verify the AT-3 repairs against the AS-2 specification.

Only synthetic fixture artifacts and selected, unchanged server definitions run.
No HTTP helper, acquisition subprocess, network request or model is executed.
"""

import ast
import contextlib
import json
from types import SimpleNamespace

import pytest

from test_phase3_repairs import podcast_attempt, production_backend, production_start
from test_phase3_support import (
    ROOT, ledger, migration_dir, phase3_isolation, phase3_module, rig, rows,
)


@pytest.mark.parametrize('damage', [
    'clip_word_substitution', 'clip_word_order', 'clip_interval',
    'sidecar_text', 'sidecar_timing', 'missing_start',
])
def test_as3_s16_publication_requires_artifact_and_clip_agreement(rig, damage):
    """Matching row counts and word sets do not establish source derivation."""
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    vid = rig.publication.stage(rig.idx, start)
    text = 'one two three four five six seven eight nine ten'
    rig.publication.paths(vid)[0].write_text(text + '\n', encoding='utf-8')
    sidecar_path = rig.publication.paths(vid)[1]
    sidecar = json.loads(sidecar_path.read_text(encoding='utf-8'))
    sidecar['transcript'] = [dict(start=12.5, end=21.75, text=text)]
    with rig.idx.write_transaction() as conn:
        conn.execute('UPDATE citations SET text=? WHERE video_id=?', (text, vid))
        conn.execute('UPDATE clips SET text=? WHERE video_id=?', (text, vid))
        if damage == 'clip_word_substitution':
            conn.execute('UPDATE clips SET text=? WHERE video_id=?',
                         (text.replace('ten', 'invented'), vid))
        elif damage == 'clip_word_order':
            conn.execute('UPDATE clips SET text=? WHERE video_id=?',
                         (' '.join(reversed(text.split())), vid))
        elif damage == 'clip_interval':
            conn.execute('UPDATE clips SET start=0, end=99999 WHERE video_id=?', (vid,))
        elif damage == 'sidecar_text':
            sidecar['transcript'][0]['text'] = 'The source says something entirely different.'
        elif damage == 'sidecar_timing':
            sidecar['transcript'][0].update(start=100, end=110)
        elif damage == 'missing_start':
            conn.execute('UPDATE citations SET timestamp_start=NULL WHERE video_id=?', (vid,))
            conn.execute('DELETE FROM clips WHERE video_id=?', (vid,))
    sidecar_path.write_text(json.dumps(sidecar), encoding='utf-8')
    ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='completed')
    assert backend.probe(start) == 'stopped'
    result = rig.svc.service.complete_capture(start['start_id'], start['owner_token'], vid)
    outbox = rows(rig.idx, 'source_classification_outbox')
    assert result['outcome'] != 'succeeded' and outbox == [], (damage, result, outbox)


def test_as3_s16_real_coarse_clip_slices_are_valid_derivation(rig):
    """The stated reason for 90 percent tolerance still fails real clips.py output."""
    import clips

    sid = rig.enrolled(1)
    start, ns, _backend = production_start(rig, sid)
    vid = rig.publication.stage(rig.idx, start)
    text = 'a' * (clips.MAX_COARSE_CHARS + 300)
    rig.publication.paths(vid)[0].write_text(text + '\n', encoding='utf-8')
    sidecar_path = rig.publication.paths(vid)[1]
    sidecar = json.loads(sidecar_path.read_text(encoding='utf-8'))
    sidecar['transcript'] = [dict(start=12.5, end=200, text=text)]
    sidecar_path.write_text(json.dumps(sidecar), encoding='utf-8')
    with rig.idx.write_transaction() as conn:
        conn.execute('UPDATE citations SET timestamp_end=200, text=? WHERE video_id=?', (text, vid))
        assert clips.build_clips_for_video(conn, vid, commit=False) == 2
    derived = rig.idx._conn.execute('SELECT text FROM clips WHERE video_id=? ORDER BY seq', (vid,)).fetchall()
    assert ''.join(row[0] for row in derived) == text
    ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='completed')
    result = rig.svc.service.complete_capture(start['start_id'], start['owner_token'], vid)
    assert result['outcome'] == 'succeeded', result


def test_as3_s13_empty_registry_does_not_verify_executor_returned(rig):
    """An evidence label must not turn a current but unknown executor into death."""
    sid = rig.enrolled(1)
    ns, backend = production_backend(rig)
    rig.svc.service.instance_id = ns['_source_instance_id']()
    claim = rig.reserve(sid)
    started = rig.svc.mark_started(claim['start_id'], claim['owner_token'])
    start = started['start']
    assert backend.probe(start) == 'unknown'
    proof = rig.module.CompletionProof(
        start['start_id'], start['owner_token'], backend.kind, 'executor_returned')
    result = rig.svc.fail_capture(start['start_id'], start['owner_token'],
                                  'unsupported_callback', proof=proof)
    assert result['outcome'] == 'worker_not_stopped', result
    assert ledger(rig.idx, sid)[0]['state'] == 'uncertain'


def test_as3_s14_two_service_instances_cannot_dispatch_one_start_twice(rig):
    """The execution claim must be durable across service instances/connections."""
    sid = rig.enrolled(1)
    ns, backend = production_backend(rig)
    claim = rig.reserve(sid)
    started = rig.svc.mark_started(claim['start_id'], claim['owner_token'])
    _idx2, second = rig.open()
    second.service.backend = backend
    try:
        first_result = rig.svc.execute_started(started)
        second_result = second.execute_started(started)
        assert len(ns['launches']) == 1, (first_result, second_result, ns['launches'])
    finally:
        backend.release(started['start'])


def _load_manual_dispatch(ns):
    """Compile actual manual ownership and handler bodies; replace I/O only."""
    path = ROOT / 'server.py'
    parsed = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    names = {'_ManualOwnership', '_manual_capture_key', '_manual_extraction_ownership'}
    nodes = [node for node in parsed.body if getattr(node, 'name', None) in names]
    handler = next(node for node in parsed.body if getattr(node, 'name', None) == 'Handler')
    nodes.append(next(node for node in handler.body if getattr(node, 'name', None) == '_handle_extract'))
    assert len(nodes) == 4
    ns['contextlib'] = contextlib
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)


def test_as3_s15_manual_waiter_reuses_standing_completion(rig, monkeypatch):
    """A manual request waiting behind standing publication must consume its recheck."""
    sid = rig.enrolled(1)
    start, ns, _backend = production_start(rig, sid)
    vid = start['capture_key'].split(':', 1)[1]
    url = rig.module.video_watch_url(vid)
    _load_manual_dispatch(ns)
    acquire = rig.module.CaptureLock.acquire

    def completed_during_wait(root, key, **kwargs):
        # The standing worker finishes while this manual request waits.
        assert key == start['capture_key']
        rig.publication.stage(rig.idx, start)
        ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='completed')
        result = rig.svc.service.complete_capture(start['start_id'], start['owner_token'], vid)
        assert result['outcome'] == 'succeeded', result
        return acquire(root, key, **kwargs)

    monkeypatch.setattr(rig.module.CaptureLock, 'acquire', completed_during_wait)
    acquisitions = []

    def fetch(url):
        acquisitions.append(url)
        raise RuntimeError('Fixture stops duplicate acquisition before any I/O')

    ns.update(DESKTOP_ROOT=rig.root, _now_iso=lambda: '2026-09-08T00:00:00Z',
              _normalize_long_video_mode=lambda mode: mode, _fetch_metadata=fetch,
              _is_youtube_rate_limit=lambda exc: False, friendly_error=str,
              machine_error_detail=str, _failure_phase=lambda exc, phase: phase,
              _record_single_extract_job=lambda *args, **kwargs: None)
    handler = SimpleNamespace(_validate_url_interval=lambda body: (url, 30, None),
                              _send_json=lambda status, body: (status, body))
    response = ns['_handle_extract'](handler, dict(url=url))
    assert acquisitions == [], (acquisitions, response)
    assert len(ledger(rig.idx, sid)) == 1


@pytest.mark.parametrize('field,value', [
    ('feed_url', 'https://other.example/contradictory.xml'),
    ('guid', 'contradictory-guid'),
])
def test_as3_s15_podcast_publisher_checks_each_available_identity_field(rig, field, value):
    """One agreeing capture key does not erase a contradictory partial provenance."""
    import podcasts

    _sid, _start, episode_id = podcast_attempt(rig)
    incoming = podcasts.get_episode_with_feed(rig.idx, episode_id)
    vid, _suffix = podcasts._episode_corpus_id(incoming)
    _feed, _guid, capture_key = podcasts._episode_full_identity(incoming)
    rig.idx.upsert_yoink(dict(
        video_id=vid, slug=vid, title='Preserve existing identity', topic='Unfiled',
        yoinked_at='2026-09-07', source_type='episode', platform='podcast',
        corpus_path=str(rig.root / 'existing.md'), sidecar_path=str(rig.root / 'existing.json'),
        metadata_json=json.dumps(dict(capture_key=capture_key, **{field: value}))))
    before = rig.idx.get_yoink(vid)
    with pytest.raises(podcasts.CorpusIdentityConflict):
        podcasts.episode_to_corpus(rig.idx, episode_id, data_root=rig.root)
    assert rig.idx.get_yoink(vid) == before
