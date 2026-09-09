"""New synthetic production-lifecycle control, not a replacement acceptance test."""
import datetime as dt, hashlib, json, os, sys
from pathlib import Path
repo=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
root=repo/'_scratch/mirror-lifecycle-control-01';root.mkdir(exist_ok=False)
os.environ.pop('ANTHROPIC_API_KEY',None)
os.environ['IG_FORBIDDEN_LIVE']=r'C:\Users\hello\AppData\Local\Uoink\index.db'
for name in ('LOCALAPPDATA','APPDATA','TEMP','TMP','XDG_DATA_HOME','UOINK_OUTPUT_DIR','UOINK_DATA_ROOT','UOINK_OUTPUT_ROOT'):os.environ[name]=str(root)
os.environ['UOINK_INDEX_PATH']=str(root/'unused.db')
sys.path.insert(0,str(repo))
guard=repo/'_scratch/igc1/guard/sitecustomize.py';exec(compile(guard.read_text(),str(guard),'exec'),{})
import library_mirror as m
from tests.library_work_astra.test_phase4_aw_acceptance import env,export,item_file
class Factory:
 n=0
 def mktemp(self,name):
  self.n+=1;p=root/(name+str(self.n));p.mkdir();return p
factory=Factory();generators=[];events=[]
def fixture():
 g=env.__wrapped__(factory);generators.append(g);return next(g)
def context():
 s=getattr(m._IO_CTX,'session',None)
 return {'io_context':None if s is None else {'dest':s.dest,'dead':s._dead,'physical':s.physical_liveness()},'retained_sessions':len(m._retained_sessions),'live_owners':len(m._live_owners),'mutex_holds':len(m._dest_holds)}
try:
 for i in range(2):
  f=fixture();export(f)
  events.append({'case':'ordinary_public_event_resync','iteration':i,'file_sha256':hashlib.sha256(item_file(f).read_bytes()).hexdigest(),'state':context()})
  assert context()=={'io_context':None,'retained_sessions':0,'live_owners':0,'mutex_holds':0}
 helper=fixture();helper.mirror._start_vault_io(str(helper.vault));session=helper.mirror._vault_io
 assert session is not None and session.alive
 writer=session.writer_pid;helper.mirror._stop_vault_io(session)
 events.append({'case':'originating_private_helper_production_stop','writer_pid':writer,'physical_after':session.physical_liveness(),'state':context()})
 assert session.physical_liveness()=='dead' and context()['io_context'] is None
 f=fixture();export(f)
 events.append({'case':'ordinary_export_after_production_stop','file_sha256':hashlib.sha256(item_file(f).read_bytes()).hexdigest(),'state':context()})
 assert context()=={'io_context':None,'retained_sessions':0,'live_owners':0,'mutex_holds':0}
 result={'status':'four independent lifecycle observations succeeded','scope':'Synthetic production event/resync and stop paths; original AW-11 teardown remains unchanged and failed in its order diagnostic','utc':dt.datetime.now(dt.timezone.utc).isoformat(),'events':events,'global_state_reset':False,'tests_changed':False}
finally:
 for g in generators:
  try:next(g)
  except StopIteration:pass
(root/'receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(result))
