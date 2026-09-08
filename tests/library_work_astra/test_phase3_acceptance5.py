"""AS-5: remaining AT-5 ownership and manual-publication boundaries.

Pytest uses the production service and unchanged server definitions with fixture
I/O only; Popen and liveness are injected. The explicit --execute-launch-probe
command separately validates the interruption with one bounded Python child.
"""

import ast
import contextlib
import json
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_phase3_acceptance3 import _load_manual_dispatch
from test_phase3_repairs import podcast_attempt, production_backend, production_start
from test_phase3_support import (
    ROOT, Crash, item_rows, ledger, migration_dir, phase3_isolation, phase3_module, rig, source_row,
)


def _load_server(ns, name):
    path = ROOT / 'server.py'
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    node = next(n for n in tree.body if getattr(n, 'name', None) == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)


def _subprocess_namespace(ns, popen):
    ns.update(subprocess=SimpleNamespace(Popen=popen, CompletedProcess=subprocess.CompletedProcess),
              threading=threading, time=time, SUBPROCESS_KW={}, _raise_if_cancelled=lambda _: None)
    _load_server(ns, '_run_subprocess')


def test_as5_s13_interruption_inside_popen_retains_launch_uncertainty(rig, monkeypatch):
    """Popen raising BaseException is not proof that no child was created."""
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    incarnation = rig.module.process_incarnation(rig.root)
    assert backend.claim_execution(start, incarnation.identity)['outcome'] == 'claimed'
    spawned = []

    def interrupted_popen(*args, **kwargs):
        assert rig.module.child_ownership_liveness(rig.root, start['start_id']) == 'unknown'
        spawned.append(424242)
        # Models an interrupt after the OS created the child, before Popen
        # returned the handle. Unlike AS-4, registration is never reached.
        raise Crash('child exists; Popen has not returned')

    _subprocess_namespace(ns, interrupted_popen)
    with rig.module.capture_context(start['start_id'], incarnation), pytest.raises(Crash):
        ns['_run_subprocess'](['fixture-child'])
    assert spawned == [424242]
    monkeypatch.setattr(rig.module, 'instance_liveness', lambda *_: 'dead')
    observed = dict(children=rig.module.child_ownership_liveness(rig.root, start['start_id']),
                    probe=backend.probe(start))
    result = rig.svc.fail_capture(start['start_id'], start['owner_token'], 'parent_interrupted')
    assert result['outcome'] == 'worker_not_stopped', (observed, result)
    assert ledger(rig.idx, sid)[0]['state'] == 'uncertain'


@pytest.mark.parametrize('damage', ['missing_children', 'invalid_child', 'wrong_start'])
def test_as5_s13_structurally_damaged_child_record_is_not_absence(rig, monkeypatch, damage):
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    assert backend.claim_execution(start, ns['_source_instance_id']())['outcome'] == 'claimed'
    record = {'start_id': start['start_id'], 'children': []}
    if damage == 'missing_children':
        record.pop('children')
    elif damage == 'invalid_child':
        record['children'] = [None]
    else:
        record['start_id'] = 'another-start'
    path = rig.module._ownership_path(rig.root, rig.module.CHILD_OWNERSHIP_DIR, start['start_id'])
    rig.module._write_ownership_record(path, record)
    monkeypatch.setattr(rig.module, 'instance_liveness', lambda *_: 'dead')
    observed = dict(children=rig.module.child_ownership_liveness(rig.root, start['start_id']),
                    probe=backend.probe(start))
    result = rig.svc.fail_capture(start['start_id'], start['owner_token'], 'damaged_ownership')
    assert result['outcome'] == 'worker_not_stopped', (damage, observed, result)
    assert backend.execution_claim(start) is not None and Path(path).exists()


@pytest.mark.parametrize('write_boundary', ['intent', 'registration'])
def test_as5_s13_child_record_write_failure_is_surfaced(rig, monkeypatch, write_boundary):
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    incarnation = rig.module.process_incarnation(rig.root)
    spawned = []
    original_write = rig.module._write_ownership_record

    def write(path, record):
        if write_boundary == 'intent' or record.get('children'):
            raise OSError('fixture disk failure')
        return original_write(path, record)

    def popen(*args, **kwargs):
        spawned.append(424242)
        return SimpleNamespace(pid=424242)

    _subprocess_namespace(ns, popen)
    monkeypatch.setattr(rig.module, '_write_ownership_record', write)
    monkeypatch.setattr(rig.module, '_process_created_ms', lambda _: 123)
    with rig.module.capture_context(start['start_id'], incarnation), pytest.raises(OSError, match='fixture disk failure'):
        ns['_run_subprocess'](['fixture-child'])
    assert bool(spawned) == (write_boundary == 'registration')
    if spawned:
        monkeypatch.setattr(rig.module, 'instance_liveness', lambda *_: 'dead')
        assert backend.probe(start) == 'unknown'


@pytest.mark.parametrize('worker', ['youtube', 'podcast_callback'])
@pytest.mark.parametrize('child_state', ['alive', 'unknown'])
def test_as5_s15_worker_exit_retains_locks_while_child_unsettled(rig, monkeypatch, worker, child_state):
    if worker == 'youtube':
        sid = rig.enrolled(1)
        ns, backend = production_backend(rig)
        rig.svc.service.instance_id = ns['_source_instance_id']()
        result = rig.svc.advance_source(sid)
        assert result['outcome'] == 'in_flight'
        start = ledger(rig.idx, sid)[0]
    else:
        sid, start, _episode_id = podcast_attempt(rig)
        ns, backend = production_backend(rig)
        start['owner_instance'] = ns['_source_instance_id']()
        with rig.idx.write_transaction() as conn:
            conn.execute('UPDATE source_capture_starts SET owner_instance=? WHERE start_id=?',
                         (start['owner_instance'], start['start_id']))
        assert backend.claim_execution(start, start['owner_instance'])['outcome'] == 'claimed'
        assert backend.acquire(start, item_rows(rig.idx, sid)[0], source_row(rig.idx, sid)) is None
    assert backend.owns(start['capture_key'])
    assert ns['_extract_lock'].locked() == (worker == 'youtube')
    monkeypatch.setattr(rig.module, 'child_ownership_liveness', lambda *_: child_state)
    try:
        if worker == 'youtube':
            # Run the actual registered closure synchronously; extraction
            # fails before fixture I/O while child termination is unavailable.
            registered = ns['_source_capture_threads'][start['start_id']]
            ns['threading'].current_thread = lambda: registered

            def fail_metadata(_):
                raise OSError('fixture worker failure')

            ns.update(_fetch_metadata=fail_metadata, _is_youtube_rate_limit=lambda _: False,
                      _sanitize_error=str)
            ns['launches'][0]['target']()
        else:
            # Execute the production callback on a real podcast ledger row.
            ns['_jobs']['finished'] = dict(source_start_id=start['start_id'],
                                           _source_owner_token=start['owner_token'], state='failed')
            _load_server(ns, '_settle_source_capture')
            ns['_settle_source_capture']('finished', video_id=None, failure_code='fixture_failure')
        after = ledger(rig.idx, sid)[0]
        assert after['state'] == 'uncertain' and backend.execution_claim(start) is not None
        contender = rig.module.CaptureLock.try_acquire(rig.root, start['capture_key'])
        available = contender is not None
        if contender is not None:
            contender.release()
        assert not available and backend.owns(start['capture_key']), (worker, child_state, after['state'], available)
        if worker == 'youtube':
            assert ns['_extract_lock'].locked()
    finally:
        backend.release(start)


@pytest.mark.parametrize('publication', ['absent', 'complete'])
def test_as5_s15_reconciliation_settles_and_releases_retained_locks(rig, monkeypatch, publication):
    sid = rig.enrolled(1)
    ns, backend = production_backend(rig)
    rig.svc.service.instance_id = ns['_source_instance_id']()
    monkeypatch.setattr(backend, '_run_youtube',
                        lambda *_: rig.module.CaptureOutcome('failed', code='fixture_failure'))
    monkeypatch.setattr(rig.module, 'child_ownership_liveness', lambda *_: 'unknown')
    first = rig.svc.advance_source(sid)
    assert first['outcome'] == 'worker_not_stopped'
    start = ledger(rig.idx, sid)[0]
    assert backend.owns(start['capture_key']) and ns['_extract_lock'].locked()
    try:
        monkeypatch.setattr(rig.module, 'child_ownership_liveness', lambda *_: 'dead')
        ns['_iter_corpus_folders'] = lambda: []
        if publication == 'complete':
            rig.publication.stage(rig.idx, start)
        assert backend.probe(start) == 'stopped'
        result = rig.svc.reconcile_start(start['start_id'])
        assert result['outcome'] == ('failed' if publication == 'absent' else 'succeeded'), result
        assert backend.execution_claim(start) is None
        assert not backend.owns(start['capture_key']) and not ns['_extract_lock'].locked(), result
    finally:
        backend.release(start)


@pytest.mark.parametrize('publication', ['item_upsert', 'damaged_sidecar'])
def test_as5_s15_manual_waiter_does_not_report_partial_capture_success(rig, publication):
    sid = rig.enrolled(1)
    start, ns, backend = production_start(rig, sid)
    vid = start['capture_key'].split(':', 1)[1]
    _load_manual_dispatch(ns)

    @contextlib.contextmanager
    def partial_publication_during_wait():
        assert rig.idx.get_yoink(vid) is None
        rig.publication.stage(rig.idx, start,
                              'item_upsert' if publication == 'item_upsert' else 'complete_publication')
        if publication == 'damaged_sidecar':
            rig.publication.paths(vid)[1].write_text('{broken', encoding='utf-8')
        ns['_jobs']['finished'] = dict(source_start_id=start['start_id'], state='failed')
        settled = rig.svc.service.complete_capture(start['start_id'], start['owner_token'], vid)
        assert settled['outcome'] == 'failed', settled
        yield

    ns['_extract_lock'] = partial_publication_during_wait()
    with ns['_manual_extraction_ownership'](rig.module.video_watch_url(vid)) as ownership:
        assert ownership.reused is None, (publication, ownership.reused)


def run_real_launch_probe():
    """Opt-in Windows process evidence; no helper, model, socket or index."""
    import hashlib
    import logging
    import os
    import sys
    import tempfile

    if sys.platform != 'win32':
        raise RuntimeError('This receipt procedure targets Windows Popen')
    scratch = ROOT / '_scratch/as5'
    scratch.mkdir(parents=True, exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix='launch-interrupt-', dir=scratch))
    for key in ('LOCALAPPDATA', 'APPDATA', 'TEMP', 'TMP', 'UOINK_OUTPUT_DIR', 'UOINK_DATA_ROOT'):
        os.environ[key] = str(fixture)
    sys.path.insert(0, str(ROOT))
    import source_subscriptions as ss

    inc = ss.process_incarnation(fixture)
    start = dict(start_id='st_as5_real_interrupt', owner_token='fixture-owner',
                 capture_key='youtube:v0000000001', owner_instance=inc.identity)
    assert ss.claim_execution_record(fixture, start, inc)['outcome'] == 'claimed'
    ns = dict(source_subscriptions=ss, DATA_ROOT=fixture, threading=threading, time=time,
              subprocess=subprocess, SUBPROCESS_KW={'creationflags': subprocess.CREATE_NO_WINDOW},
              _raise_if_cancelled=lambda _: None, log=logging.getLogger('as5-real'),
              _source_capture_threads={}, _source_capture_threads_lock=threading.RLock(),
              _jobs={'job': dict(source_start_id=start['start_id'], state='failed')},
              _jobs_lock=threading.RLock(), _JOB_TERMINAL_STATES={'failed', 'completed', 'cancelled'})
    for name in ('_run_subprocess', '_ServerCaptureBackend', '_find_job_for_start', '_source_instance_id'):
        _load_server(ns, name)
    created = []
    original = subprocess.Popen._execute_child

    def interrupt_after_os_creation(self, *args, **kwargs):
        original(self, *args, **kwargs)
        created.append(self)
        raise KeyboardInterrupt('AS5 injection after real OS child creation')

    receipt = dict(procedure='AS5 real child: interruption inside Popen',
                   command=[sys.executable, '-B', *sys.argv], python=sys.version,
                   input_hashes={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in ('server.py', 'source_subscriptions.py',
                                              'tests/library_work_astra/test_phase3_acceptance5.py')})
    try:
        subprocess.Popen._execute_child = interrupt_after_os_creation
        try:
            with ss.capture_context(start['start_id'], inc):
                ns['_run_subprocess']([sys.executable, '-B', '-c', 'import time; time.sleep(15)'])
        except KeyboardInterrupt:
            receipt['interrupt_propagated'] = True
        finally:
            subprocess.Popen._execute_child = original
        assert len(created) == 1
        child = created[0]
        receipt.update(child_pid=child.pid, real_child_running=child.poll() is None,
                       child_status=ss.child_ownership_liveness(fixture, start['start_id']),
                       probe=ns['_ServerCaptureBackend']().probe(start))
        assert receipt['real_child_running']
    finally:
        for child in created:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
        receipt['all_created_children_reaped'] = all(c.poll() is not None for c in created)
        (scratch / 'real-launch-interrupt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['probe'] != 'stopped' else 1


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-launch-probe', action='store_true')
    if not parser.parse_args().execute_launch_probe:
        parser.error('Use pytest for fixtures, or explicitly select --execute-launch-probe')
    raise SystemExit(run_real_launch_probe())
