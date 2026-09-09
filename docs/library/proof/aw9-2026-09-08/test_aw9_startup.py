"""AW-9 startup failure diagnostic; actual owned worker, simulated uncertain death."""
import json, subprocess, sys, threading
import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env

def test_startup_failure_keeps_exclusion_until_child_death(env, monkeypatch):
    sessions=[]; errors=[]
    original_terminate=mirror._VaultIoSession.terminate
    def no_ready(session, timeout=None):
        sessions.append(session)
        return None
    def uncertain(session):
        session._dead=True
        return False
    monkeypatch.setattr(mirror._VaultIoSession, '_readline', no_ready)
    monkeypatch.setattr(mirror._VaultIoSession, 'terminate', uncertain)
    def own():
        try:
            with env.mirror._exclusive(timeout=0.5):
                env.mirror._start_vault_io(str(env.vault))
        except OSError as exc:
            errors.append(str(exc))
    thread=threading.Thread(target=own); thread.start(); thread.join(8)
    try:
        assert not thread.is_alive() and sessions and errors
        session=sessions[0]
        assert session.proc.poll() is None and not session._lease_written
        source="""import json, sys
import library_mirror as m
try:
 h,k=m._win_acquire_dest_mutex(sys.argv[1],0.25)
except m._LockTimeout:
 print(json.dumps({'acquired':False}))
else:
 print(json.dumps({'acquired':True}))
 m._win_release_dest_mutex(h,k)
"""
        child=subprocess.run([sys.executable,'-B','-c',source,str(env.vault)],capture_output=True,text=True,timeout=8)
        assert child.returncode==0,child.stderr
        observed=json.loads(child.stdout.strip())
        observed.update(original_session_pid=session.pid, parent_retained=env.mirror._vault_io is session, launcher_alive=session.proc.poll() is None, lease_written=session._lease_written)
        assert not observed['acquired'],observed
    finally:
        monkeypatch.setattr(mirror._VaultIoSession, 'terminate', original_terminate)
        for session in sessions: original_terminate(session)
        env.mirror._vault_io=None
