"""Observes mirror state without changing cleanup, return values or authority."""
import datetime as dt, json, threading, traceback
from pathlib import Path
import pytest
import library_mirror as m
log=None
def record(kind,**fields):
 with log.open('a',encoding='utf-8',newline='\n') as f:
  f.write(json.dumps({'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'kind':kind,**fields},default=str)+'\n')
def snapshot(kind,nodeid):
 with m._dest_hold_guard:
  sessions=list(m._retained_sessions);owners=list(m._live_owners);holds=dict(m._dest_holds)
 values=[]
 for s in sessions:
  try:physical=s.physical_liveness()
  except BaseException as e:physical=repr(e)
  values.append({'id':id(s),'dest':s.dest,'pid':s.pid,'writer_pid':s.writer_pid,'physical':physical,'dead':s._dead,'launching':s._launching,'popen_in_progress':s._popen_in_progress,'owner':id(s._exclusion_owner),'origin_thread':str(s._origin_thread)})
 ctx=getattr(m._IO_CTX,'session',None)
 context=None if ctx is None else {'id':id(ctx),'dest':ctx.dest,'pid':ctx.pid,'writer_pid':ctx.writer_pid,'physical':ctx.physical_liveness(),'dead':ctx._dead,'origin':str(ctx._origin_thread)}
 record(kind,nodeid=nodeid,sessions=values,io_context=context,io_plan=getattr(m._IO_CTX,'plan',None),holds=holds,context_owner=id(getattr(m._EXCL_CTX,'owner',None)),owners=[{'id':id(o),'dest':o.dest,'key':o.key,'held':o.held,'exclusive_holds':o._exclusive_holds,'stop':o._stop.is_set(),'done':o._done.is_set(),'thread_alive':o._thread.is_alive(),'thread_ident':o._thread.ident,'sessions':[id(s) for s in o.sessions]} for o in owners])
def pytest_sessionstart(session):
 global log
 base=Path(session.config.getoption('basetemp')).resolve()
 assert base.parent.name=='_scratch'
 log=base.parent/(base.name+'-mirror-state.jsonl')
 with log.open('x',encoding='utf-8'):pass
 original=m.Mirror._start_vault_io
 def observed(self,*a,**kw):
  try:return original(self,*a,**kw)
  except BaseException:
   record('start_error',dest=a[0] if a else None,traceback=traceback.format_exc());raise
 m.Mirror._start_vault_io=observed
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item,nextitem):
 yield
 snapshot('after_teardown',item.nodeid)
def pytest_runtest_setup(item):snapshot('before_setup',item.nodeid)
