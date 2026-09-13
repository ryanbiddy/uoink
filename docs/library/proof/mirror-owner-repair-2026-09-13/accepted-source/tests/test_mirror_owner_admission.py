"""Controlled admission boundaries with no OS mutex or process launch."""
import threading

import pytest

import library_mirror as m


@pytest.fixture
def inert_gate(monkeypatch):
    calls = []
    monkeypatch.setattr(m, '_win_acquire_dest_mutex_result',
                        lambda dest, timeout: (object(), m._admission_gate_key(dest), False))
    monkeypatch.setattr(m, '_win_release_dest_mutex',
                        lambda handle, key=None: calls.append(threading.get_ident()))
    monkeypatch.setattr(m._DestExclusionOwner, '_posix_hold', lambda self: None)
    monkeypatch.setattr(m._DestExclusionOwner, '_posix_release',
                        lambda self: calls.append(threading.get_ident()))
    return calls


def test_sweep_cannot_release_acquired_owner_before_session_attachment(inert_gate, monkeypatch, tmp_path):
    original = m._exclusion_for_dest
    owners = []
    def interleaved(dest, timeout):
        owner = original(dest, timeout)
        owners.append(owner)
        m._release_proven_dead_owners()
        return owner
    monkeypatch.setattr(m, '_exclusion_for_dest', interleaved)
    session = m._VaultIoSession.prepare(str(tmp_path/'vault'))
    try:
        assert owners[0].held and not owners[0]._stop.is_set()
        assert session._exclusion_owner is owners[0]
        assert not inert_gate
    finally:
        assert session.terminate()
    assert owners[0]._done.is_set() and len(inert_gate) == 1


@pytest.mark.parametrize('failure_site', ['replacement', 'attach', 'retain'])
def test_prepare_failure_releases_its_reservation(inert_gate, monkeypatch, tmp_path, failure_site):
    owners = []
    original = m._exclusion_for_dest
    def observe(dest, timeout):
        owner = original(dest, timeout)
        owners.append(owner)
        return owner
    def fail(*args):
        raise OSError('injected preparation failure')
    monkeypatch.setattr(m, '_exclusion_for_dest', observe)
    if failure_site == 'replacement':
        monkeypatch.setattr(m, '_owner_blocks_replacement', fail)
    elif failure_site == 'attach':
        monkeypatch.setattr(m._DestExclusionOwner, 'attach', fail)
    else:
        monkeypatch.setattr(m, '_retain_session', fail)
    with pytest.raises(OSError, match='injected preparation failure'):
        m._VaultIoSession.prepare(str(tmp_path/'vault'))
    assert owners[0]._done.is_set() and not owners[0].sessions
    assert len(inert_gate) == 1


@pytest.mark.parametrize('admission', ['reservation', 'attachment'])
def test_sweep_snapshot_cannot_release_new_admission(inert_gate, monkeypatch, tmp_path, admission):
    owner = m._acquire_dest_exclusion(str(tmp_path/'vault'), 0.1, exclusive=True)
    stale = m._VaultIoSession()
    incoming = m._VaultIoSession()
    incoming._launching = True
    entered = threading.Event()
    resume = threading.Event()
    def stale_liveness():
        entered.set()
        assert resume.wait(3)
        return False
    monkeypatch.setattr(stale, 'physically_alive', stale_liveness)
    owner.attach(stale)
    owner.drop_exclusive()
    errors = []
    def sweep_once():
        try:
            owner.release_if_unneeded()
        except BaseException as exc:
            errors.append(exc)
    sweep = threading.Thread(target=sweep_once)
    sweep.start()
    try:
        assert entered.wait(3)
        if admission == 'reservation':
            owner.reserve()
        else:
            owner.attach(incoming)
        resume.set()
        sweep.join(3)
        assert not sweep.is_alive()
        assert not errors
        assert owner.held and not owner._stop.is_set()
        assert not inert_gate
    finally:
        resume.set()
        sweep.join(3)
        if admission == 'reservation':
            owner.drop_exclusive()
        owner.detach(stale)
        incoming._launching = False
        owner.detach(incoming)
        owner.release_if_unneeded()
    assert owner._done.is_set() and len(inert_gate) == 1


def test_stopping_owner_refuses_reservation_and_attachment(inert_gate, tmp_path):
    owner = m._acquire_dest_exclusion(str(tmp_path/'vault'), 0.1, exclusive=True)
    session = m._VaultIoSession()
    owner.release()
    try:
        with pytest.raises(OSError, match='destination exclusion unavailable'):
            owner.reserve()
        with pytest.raises(OSError, match='destination exclusion unavailable'):
            owner.attach(session)
        assert session._exclusion_owner is None
    finally:
        owner.drop_exclusive()


def test_stale_session_cleanup_does_not_reenter_global_guard(inert_gate, monkeypatch, tmp_path):
    class StrictGuard:
        def __init__(self):
            self.lock = threading.Lock()
            self.local = threading.local()
        def __enter__(self):
            assert not getattr(self.local, 'held', False), 'recursive global guard acquisition'
            self.lock.acquire()
            self.local.held = True
            return self
        def __exit__(self, *args):
            self.local.held = False
            self.lock.release()
    monkeypatch.setattr(m, '_dest_hold_guard', StrictGuard())
    owner = m._acquire_dest_exclusion(str(tmp_path/'vault'), 0.1, exclusive=True)
    session = m._VaultIoSession()
    owner.attach(session)
    owner.drop_exclusive()
    try:
        owner.release_if_unneeded()
        assert owner._done.is_set() and session._exclusion_owner is None
        assert not owner.sessions and len(inert_gate) == 1
    finally:
        owner.detach(session)
        owner.release_if_unneeded()


def test_unknown_child_keeps_owner_after_preparation_reservation_ends(inert_gate, monkeypatch, tmp_path):
    session = m._VaultIoSession.prepare(str(tmp_path/'vault'))
    owner = session._exclusion_owner
    session._launching = False
    state = {'value': 'unknown'}
    monkeypatch.setattr(session, 'physical_liveness', lambda: state['value'])
    try:
        owner.release_if_unneeded()
        assert owner.held and session in owner.sessions and not inert_gate
    finally:
        state['value'] = 'dead'
        assert session.terminate()
    assert owner._done.is_set() and len(inert_gate) == 1


def test_prepared_cancel_releases_and_never_enters_popen(inert_gate, monkeypatch, tmp_path):
    session = m._VaultIoSession.prepare(str(tmp_path/'vault'))
    owner = session._exclusion_owner
    entered = []
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *a, **k: entered.append(True))
    assert session.terminate()
    with pytest.raises(OSError, match='vault io worker cancelled'):
        session.launch()
    assert owner._done.is_set() and not entered and len(inert_gate) == 1


def test_refused_replacement_drops_only_incoming_reservation(inert_gate, monkeypatch, tmp_path):
    session = m._VaultIoSession.prepare(str(tmp_path/'vault'))
    owner = session._exclusion_owner
    monkeypatch.setattr(m._EXCL_CTX, 'owner', owner, raising=False)
    try:
        with pytest.raises(OSError, match='vault io worker still live'):
            m._VaultIoSession.prepare(str(tmp_path/'vault'))
        owner.release_if_unneeded()
        assert owner.held and session in owner.sessions and not inert_gate
        assert owner._exclusive_holds == 0
    finally:
        assert session.terminate()
