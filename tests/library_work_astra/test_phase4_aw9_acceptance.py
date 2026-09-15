"""Integrator diagnostic of B4 physical death and destination exclusion."""
import json, subprocess, sys, threading
from types import SimpleNamespace
import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env

def test_unknown_writer_after_launcher_exit_is_retained(env, monkeypatch):
    session=mirror._VaultIoSession()
    session.proc=SimpleNamespace(poll=lambda:0,pid=424240)
    session.writer_pid=424241
    session.dest=str(env.vault)
    env.mirror._vault_io=session
    monkeypatch.setattr(mirror,'_process_liveness',lambda *a,**k:'unknown')
    def uncertain():
        session._dead=True
        return False
    monkeypatch.setattr(session,'terminate',uncertain)
    env.mirror._kill_vault_io(session)
    assert env.mirror._vault_io is session, 'Unknown writer was forgotten after its launcher exited'

def test_destination_exclusion_survives_owning_thread_exit_before_lease(env):
    sessions=[];errors=[]
    def own():
        try:
            with env.mirror._exclusive(timeout=0.5):
                session=mirror._VaultIoSession.start(str(env.vault))
                sessions.append(session)
                env.mirror._vault_io=session
                assert not session._lease_written
                # The original caller returns while physical death is unresolved.
                # The actual child remains able to perform isolated operations.
        except BaseException as exc:errors.append(repr(exc))
    thread=threading.Thread(target=own);thread.start();thread.join(8)
    try:
        assert not thread.is_alive() and not errors,errors
        session=sessions[0]
        assert session.physically_alive() and not session._lease_written
        source='''import json,sys,os
import library_mirror as m
try:
 h,k=m._win_acquire_dest_mutex(sys.argv[1],0.25)
except m._LockTimeout:
 print(json.dumps({'acquired':False,'pid':os.getpid()}))
else:
 print(json.dumps({'acquired':True,'pid':os.getpid()}))
 m._win_release_dest_mutex(h,k)
'''
        child=subprocess.run([sys.executable,'-B','-c',source,str(env.vault)],capture_output=True,text=True,timeout=8)
        assert child.returncode==0,child.stderr
        observed=json.loads(child.stdout.strip())
        observed.update(original_writer=session.writer_pid,original_writer_alive=session.physically_alive(),lease_written=session._lease_written)
        assert not observed['acquired'],observed
    finally:
        for session in sessions:session.terminate()
        env.mirror._vault_io=None
