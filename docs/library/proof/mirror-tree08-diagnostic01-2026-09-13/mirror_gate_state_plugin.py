"""Read-only lifecycle observations; no cleanup, monkeypatch or outcome changes."""
import json, os, sys, threading, time, traceback
from pathlib import Path
import pytest

def session_row(session):
    proc=getattr(session,'proc',None)
    origin=getattr(session,'_origin_thread',None)
    return {'object_id':id(session),'pid':getattr(session,'pid',None),
            'proc_pid':getattr(proc,'pid',None),'proc_returncode':getattr(proc,'returncode',None),
            'writer_pid':getattr(session,'writer_pid',None),
            'created_ms':getattr(session,'created_ms',None),'writer_created_ms':getattr(session,'writer_created_ms',None),
            'dead':getattr(session,'_dead',None),'launching':getattr(session,'_launching',None),
            'popen_in_progress':getattr(session,'_popen_in_progress',None),'job':getattr(session,'job',None),
            'origin_ident':getattr(origin,'ident',None),'origin_name':getattr(origin,'name',None),
            'owner_id':id(getattr(session,'_exclusion_owner',None))}

def capture(node, phase):
    destination=Path(os.environ['IG_GATE_DIAGNOSTIC_OUT'])
    root=Path(__file__).resolve().parents[1]/'_scratch'
    assert destination.resolve().is_relative_to(root.resolve())
    module=sys.modules.get('library_mirror')
    if module is None:return
    try:
        owners=[]
        for owner in list(module._live_owners):
            owners.append({'object_id':id(owner),'dest':owner.dest,'key':owner.key,'held':owner.held,
                           'exclusive_holds':owner._exclusive_holds,'stop':owner._stop.is_set(),
                           'done':owner._done.is_set(),'thread_ident':owner._thread.ident,
                           'thread_alive':owner._thread.is_alive(),'sessions':[session_row(s) for s in list(owner.sessions)]})
        frames=sys._current_frames()
        threads=[{'name':t.name,'ident':t.ident,'alive':t.is_alive(),
                  'stack':traceback.format_stack(frames[t.ident]) if t.ident in frames else []}
                 for t in threading.enumerate()]
        record={'nodeid':node,'phase':phase,'monotonic':time.monotonic(),'pid':os.getpid(),
                'owners':owners,'retained_sessions':[session_row(s) for s in list(module._retained_sessions)],
                'dest_holds':dict(module._dest_holds),
                'io_session':session_row(module._io_ctx_session()) if module._io_ctx_session() is not None else None,
                'exclusion_owner_id':id(getattr(module._EXCL_CTX,'owner',None)),'threads':threads}
    except Exception as error:
        record={'nodeid':node,'phase':phase,'observer_error':type(error).__name__+': '+str(error)}
    with destination.open('a',encoding='utf8') as stream:stream.write(json.dumps(record,default=str)+'\n')

@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_setup(item):
    capture(item.nodeid,'before_setup')
    yield
    capture(item.nodeid,'after_setup')

@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_call(item):
    capture(item.nodeid,'before_call')
    yield
    capture(item.nodeid,'after_call')

@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_teardown(item):
    capture(item.nodeid,'before_teardown')
    yield
    capture(item.nodeid,'after_teardown')
