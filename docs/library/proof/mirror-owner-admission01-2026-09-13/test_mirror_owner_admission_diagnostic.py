"""New controlled owner-handoff probe; no OS mutex or child process is used."""
import json, os, threading
from pathlib import Path
import library_mirror as mirror

def test_new_admission_cannot_reap_owner_before_session_attachment(monkeypatch, tmp_path):
    events=[]
    def acquire(dest, timeout):
        events.append({'event':'acquire','thread':threading.get_ident()})
        return object(), mirror._admission_gate_key(dest), False
    def release(handle, key=None):
        events.append({'event':'release','thread':threading.get_ident()})
    monkeypatch.setattr(mirror,'_win_acquire_dest_mutex_result',acquire)
    monkeypatch.setattr(mirror,'_win_release_dest_mutex',release)
    original=mirror._exclusion_for_dest
    def interleaved(dest, timeout):
        owner=original(dest,timeout)
        events.append({'event':'before_sweep','held':owner.held,'exclusive':owner._exclusive_holds,'sessions':len(owner.sessions)})
        mirror._release_proven_dead_owners()
        events.append({'event':'after_sweep','held':owner.held,'done':owner._done.is_set()})
        return owner
    monkeypatch.setattr(mirror,'_exclusion_for_dest',interleaved)
    session=None
    try:
        session=mirror._VaultIoSession.prepare(str(tmp_path/'vault'))
        owner=session._exclusion_owner
        assert owner is not None
        events.append({'event':'prepared','held':owner.held,'launching':session._launching,'sessions':len(owner.sessions)})
        assert owner.held and not owner._done.is_set(), 'Prepared writer lost exclusion before attachment'
    finally:
        if session is not None:session.terminate()
        target=Path(os.environ['IG_OWNER_DIAGNOSTIC_OUT'])
        assert target.resolve().is_relative_to(Path(__file__).resolve().parent)
        target.write_text(json.dumps(events,indent=2)+'\n',encoding='utf8')
