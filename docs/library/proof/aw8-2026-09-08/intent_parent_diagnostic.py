import os
import threading
from pathlib import Path
from tests.library_work_astra.test_phase4_aw_acceptance import env
import library_mirror as mirror

def test_old_intent_replace_cannot_complete_over_new_operation(env, monkeypatch):
    path=env.mirror._intent_path("item:a")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b"before")
    entered,release,done=threading.Event(),threading.Event(),threading.Event()
    real_replace=os.replace
    errors=[]
    def held_replace(src,dst,*args,**kwargs):
        if Path(dst)==path and threading.current_thread().name=="old-intent-writer":
            entered.set()
            assert release.wait(8)
        return real_replace(src,dst,*args,**kwargs)
    monkeypatch.setattr(os,"replace",held_replace)
    env.mirror._op_seq=10
    env.mirror._lock_generation=4
    def old():
        mirror._IO_CTX.plan={"op_id":10,"lock_generation":4}
        try: env.mirror._atomic_local(path,b"stale operation A")
        except OSError as exc: errors.append(str(exc))
        finally: done.set()
    t=threading.Thread(target=old,name="old-intent-writer",daemon=True)
    t.start()
    try:
        assert entered.wait(3), "Diagnostic requires the final parent replace boundary"
        env.mirror._op_seq=11
        env.mirror._lock_generation=5
        path.write_bytes(b"current operation B")
    finally:
        release.set()
        assert done.wait(5)
    assert path.read_bytes()==b"current operation B", "Old parent replaced a newer operation's durable intent"
