"""AS-4 checks of the AT-4 ownership and manual-wait repairs.

Actual service and selected production server definitions; only fixture I/O.
Process liveness is injected. No real child, helper, network or model runs.
"""

import ast
import contextlib
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from test_phase3_acceptance3 import _load_manual_dispatch
from test_phase3_repairs import podcast_attempt, production_backend, production_start
from test_phase3_support import (
    ROOT, Crash, ledger, migration_dir, phase3_isolation, phase3_module, rig, rows,
)


@pytest.mark.parametrize('child_state', ['alive', 'unknown'])
def test_as4_s13_terminal_job_does_not_override_child_liveness(rig, monkeypatch, child_state):
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    start['owner_instance'] = ns['_source_instance_id']()
    with rig.idx.write_transaction() as conn:
        conn.execute('UPDATE source_capture_starts SET owner_instance=? WHERE start_id=?',
                     (start['owner_instance'], start['start_id']))
    ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='failed')
    monkeypatch.setattr(rig.module, 'child_ownership_liveness', lambda *_: child_state)
    proof = rig.module.CompletionProof(
        start['start_id'], start['owner_token'], backend.kind, 'job_terminal')
    observed = dict(probe=backend.probe(start), proof=backend.verify_proof(start, proof))
    result = rig.svc.fail_capture(start['start_id'], start['owner_token'], 'job_failed', proof=proof)
    assert result['outcome'] == 'worker_not_stopped', (child_state, observed, result)
    assert ledger(rig.idx, sid)[0]['state'] == 'uncertain'


def test_as4_s13_synchronous_return_does_not_prove_unknown_child_stopped(rig, monkeypatch):
    sid = rig.enrolled(1)
    ns, backend = production_backend(rig)
    rig.svc.service.instance_id = ns['_source_instance_id']()
    claim = rig.reserve(sid)
    started = rig.svc.mark_started(claim['start_id'], claim['owner_token'])
    # Observe a real backend.run invocation and return, while a child's
    # termination remains unverifiable (e.g. OS query permission denied).
    monkeypatch.setattr(backend, '_run_youtube',
                        lambda *_: rig.module.CaptureOutcome('failed', code='fixture_failure'))
    monkeypatch.setattr(rig.module, 'child_ownership_liveness', lambda *_: 'unknown')
    result = rig.svc.execute_started(started)
    assert backend._invocations[claim['start_id']]['returned']
    assert result['outcome'] == 'worker_not_stopped', result
    assert ledger(rig.idx, sid)[0]['state'] == 'uncertain'


def test_as4_s13_child_spawn_before_record_is_not_stopped(rig, monkeypatch):
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    incarnation = rig.module.process_incarnation(rig.root)
    assert backend.claim_execution(start, incarnation.identity)['outcome'] == 'claimed'
    path = ROOT / 'server.py'
    parsed = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    node = next(n for n in parsed.body if getattr(n, 'name', None) == '_run_subprocess')
    spawned = []

    def popen(*args, **kwargs):
        spawned.append(dict(pid=424242, alive=True))
        return SimpleNamespace(pid=424242)

    def crash_at_record(*args, **kwargs):
        # Parent death at this boundary leaves an already created child.
        raise Crash('after Popen, before durable child record')

    ns.update(subprocess=SimpleNamespace(Popen=popen, CompletedProcess=subprocess.CompletedProcess),
              threading=threading, time=time, SUBPROCESS_KW={}, _raise_if_cancelled=lambda _: None)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
    monkeypatch.setattr(rig.module, 'record_child_start', crash_at_record)
    with rig.module.capture_context(start['start_id'], incarnation):
        with pytest.raises(Crash):
            ns['_run_subprocess'](['fixture-child'])
    assert spawned == [dict(pid=424242, alive=True)]
    monkeypatch.setattr(rig.module, 'instance_liveness', lambda *_: 'dead')
    observed = dict(children=rig.module.child_ownership_liveness(rig.root, start['start_id']),
                    probe=backend.probe(start))
    assert observed['probe'] != 'stopped', observed


def test_as4_s15_off_after_lock_releases_dispatcher_ownership(rig, monkeypatch):
    sid = rig.enrolled(1)
    ns, backend = production_backend(rig)
    acquire = backend.acquire

    def off_after_acquire(start, item, source):
        result = acquire(start, item, source)
        assert result is None and backend.owns(start['capture_key'])
        rig.consent(sid, 'off')
        return result

    monkeypatch.setattr(backend, 'acquire', off_after_acquire)
    try:
        result = rig.svc.advance_source(sid)
        row = ledger(rig.idx, sid)[0]
        assert row['state'] == 'released' and row['started_at_ms'] is None, (result, row)
        assert ns['launches'] == []
        assert not backend.owns(row['capture_key']) and not ns['_extract_lock'].locked(), result
    finally:
        for row in ledger(rig.idx, sid):
            backend.release(row)


def test_as4_s15_manual_wait_on_process_lock_reuses_completion(rig):
    sid = rig.enrolled(1)
    start, ns, _backend = production_start(rig, sid)
    vid = start['capture_key'].split(':', 1)[1]
    _load_manual_dispatch(ns)

    @contextlib.contextmanager
    def completed_during_process_lock_wait():
        assert rig.idx.get_yoink(vid) is None
        rig.publication.stage(rig.idx, start)
        ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='completed')
        assert rig.svc.service.complete_capture(
            start['start_id'], start['owner_token'], vid)['outcome'] == 'succeeded'
        yield

    # The first lock in the production wrapper is _extract_lock. A standing
    # YouTube capture holds it, so its publication precedes __enter__ returning.
    ns['_extract_lock'] = completed_during_process_lock_wait()
    with ns['_manual_extraction_ownership'](rig.module.video_watch_url(vid)) as ownership:
        assert ownership.reused is not None, dict(
            already_captured=ownership.already_captured,
            completed_while_waiting=ownership.completed_while_waiting)


@pytest.mark.parametrize('owner_liveness,expected', [('current', 'uncertain'), ('dead', 'failed')])
def test_as4_s13_unclaimed_intent_keeps_charge_without_redispatch(
        rig, monkeypatch, owner_liveness, expected):
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    assert backend.execution_claim(start) is None
    ns['_iter_corpus_folders'] = lambda: []
    monkeypatch.setattr(rig.module, 'instance_liveness', lambda *_: owner_liveness)
    result = rig.svc.reconcile_start(start['start_id'])
    assert result['outcome'] == expected, result
    after = ledger(rig.idx, sid)
    assert len(after) == 1 and after[0]['started_at_ms'] == start['started_at_ms']
    assert after[0]['slot'] == start['slot'] and after[0]['utc_day'] == start['utc_day']
    assert ns['launches'] == []


def test_as4_s16_local_recovery_uses_capture_lock_without_execution_claim(rig, monkeypatch):
    import podcasts

    sid, start, episode_id = podcast_attempt(rig)
    ns, backend = production_backend(rig)
    ns['podcasts'] = podcasts
    ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='completed')
    original = podcasts.episode_to_corpus
    observations = []

    def publisher(idx, requested_id, **kwargs):
        assert requested_id == episode_id and backend.owns(start['capture_key'])
        assert backend.execution_claim(start) is None
        observations.append(requested_id)
        return original(idx, requested_id, **kwargs)

    monkeypatch.setattr(podcasts, 'episode_to_corpus', publisher)
    result = rig.svc.reconcile_start(start['start_id'])
    assert result['outcome'] == 'succeeded', result
    assert observations == [episode_id] and ns['launches'] == []
    assert not backend.owns(start['capture_key'])
    assert len(ledger(rig.idx, sid)) == len(rows(rig.idx, 'source_classification_outbox')) == 1
    assert ledger(rig.idx, sid)[0]['started_at_ms'] == start['started_at_ms']
