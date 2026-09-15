"""AS-6 checks AT-6 child-record validation and ownership cleanup.

All process liveness and launches are fixtures. Server definitions are compiled
unchanged from this worktree; no helper, network, model or live index is used.
"""

import pytest

from test_phase3_acceptance5 import _load_server
from test_phase3_repairs import podcast_attempt, production_backend, production_start
from test_phase3_support import (
    item_rows, ledger, migration_dir, phase3_isolation, phase3_module, rig, source_row,
)


@pytest.mark.parametrize('damage', [
    'boolean_exit', 'text_exit', 'missing_child_identity', 'invalid_launch_flag',
])
def test_as6_s13_malformed_child_fields_cannot_certify_exit(rig, monkeypatch, damage):
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    incarnation = rig.module.process_incarnation(rig.root)
    assert backend.claim_execution(start, incarnation.identity)['outcome'] == 'claimed'
    monkeypatch.setattr(rig.module, '_process_created_ms', lambda _: 123)
    rig.module.record_child_start(rig.root, start['start_id'], 424242, incarnation.identity)
    path = rig.module._ownership_path(rig.root, rig.module.CHILD_OWNERSHIP_DIR, start['start_id'])
    record = rig.module._read_ownership_record(path)
    if damage == 'boolean_exit':
        record['children'][0]['ended_ms'] = False
    elif damage == 'text_exit':
        record['children'][0]['ended_ms'] = 'not-an-exit-time'
    elif damage == 'missing_child_identity':
        record['children'][0] = {'ended_ms': 456}
    else:
        # A damaged unresolved launch marker cannot prove no child was created.
        record.update(children=[], unresolved_launch=[], unresolved_ms=456,
                      unresolved_instance=incarnation.identity)
    rig.module._write_ownership_record(path, record)
    monkeypatch.setattr(rig.module, '_process_alive', lambda *_: 'alive')
    monkeypatch.setattr(rig.module, 'instance_liveness', lambda *_: 'dead')
    before = dict(children=rig.module.child_ownership_liveness(rig.root, start['start_id']),
                  probe=backend.probe(start))
    result = rig.svc.fail_capture(start['start_id'], start['owner_token'], 'damaged_child_fields')
    after = ledger(rig.idx, sid)[0]
    observed = dict(before=before, outcome=result['outcome'], state=after['state'],
                    claim_retained=backend.execution_claim(start) is not None)
    assert result['outcome'] == 'worker_not_stopped', (damage, observed)
    assert before['children'] == 'unknown' and before['probe'] == 'unknown'
    assert after['state'] == 'uncertain' and observed['claim_retained']


@pytest.mark.parametrize('helper', ['record_child_launch_intent', 'record_child_start'])
def test_as6_s13_write_helpers_preserve_schema_invalid_child_evidence(rig, monkeypatch, helper):
    start_id = 'st_as6_damaged_child'
    path = rig.module._ownership_path(rig.root, rig.module.CHILD_OWNERSHIP_DIR, start_id)
    rig.module._write_ownership_record(path, {'start_id': 'another-start', 'children': []})
    from pathlib import Path
    original = Path(path).read_bytes()
    monkeypatch.setattr(rig.module, '_process_created_ms', lambda _: 123)
    args = (rig.root, start_id, 'fixture-instance') if helper.endswith('intent') else (
        rig.root, start_id, 424242, 'fixture-instance')
    with pytest.raises(OSError, match='damaged'):
        getattr(rig.module, helper)(*args)
    assert Path(path).read_bytes() == original
    assert rig.module.child_ownership_liveness(rig.root, start_id) == 'unknown'


@pytest.mark.parametrize('worker', ['youtube', 'podcast_callback'])
def test_as6_s15_settlement_exception_retains_dispatcher_ownership(rig, monkeypatch, worker):
    if worker == 'youtube':
        sid = rig.enrolled(1)
        ns, backend = production_backend(rig)
        rig.svc.service.instance_id = ns['_source_instance_id']()
        assert rig.svc.advance_source(sid)['outcome'] == 'in_flight'
        start = ledger(rig.idx, sid)[0]
    else:
        sid, start, _ = podcast_attempt(rig)
        ns, backend = production_backend(rig)
        assert backend.claim_execution(start, ns['_source_instance_id']())['outcome'] == 'claimed'
        assert backend.acquire(start, item_rows(rig.idx, sid)[0], source_row(rig.idx, sid)) is None

    def failure(*args, **kwargs):
        raise OSError('AS6 settlement unavailable')

    monkeypatch.setattr(rig.svc.service, 'fail_capture', failure)
    try:
        if worker == 'youtube':
            registered = ns['_source_capture_threads'][start['start_id']]
            ns['threading'].current_thread = lambda: registered
            ns.update(_fetch_metadata=failure, _is_youtube_rate_limit=lambda _: False,
                      _sanitize_error=str)
            ns['launches'][0]['target']()
        else:
            ns['_jobs']['finished'] = dict(source_start_id=start['start_id'],
                                           _source_owner_token=start['owner_token'], state='failed')
            _load_server(ns, '_settle_source_capture')
            ns['_settle_source_capture']('finished', video_id=None, failure_code='fixture_failure')
        assert backend.owns(start['capture_key'])
        assert backend.execution_claim(start) is not None
        assert ledger(rig.idx, sid)[0]['state'] in ('started', 'uncertain')
        contender = rig.module.CaptureLock.try_acquire(rig.root, start['capture_key'])
        if contender is not None:
            contender.release()
        assert contender is None
        assert ns['_extract_lock'].locked() == (worker == 'youtube')
    finally:
        backend.release(start)


def test_as6_s15_stale_release_cannot_unlock_another_start(rig):
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    assert backend.acquire(start, item_rows(rig.idx, sid)[0], source_row(rig.idx, sid)) is None
    try:
        backend.release(dict(start, start_id='st_obsolete'))
        assert backend.owns(start['capture_key']) and ns['_extract_lock'].locked()
        contender = rig.module.CaptureLock.try_acquire(rig.root, start['capture_key'])
        if contender is not None:
            contender.release()
        assert contender is None
        backend.release(start)
        backend.release(start)
        assert not backend.owns(start['capture_key']) and not ns['_extract_lock'].locked()
    finally:
        backend.release(start)
