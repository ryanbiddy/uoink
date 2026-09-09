"""Observe original staged C22 runtime with disposable fixtures; never run Setup."""
import argparse,collections,datetime as dt,hashlib,json,os,subprocess,sys,traceback
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--label',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git',*args],cwd=r,text=True).strip()
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,obj):path.write_text(json.dumps(obj,indent=2,default=str)+'\n',encoding='utf8',newline='\n')
assert git('rev-parse','HEAD')==a.source and not git('status','--porcelain','--untracked-files=no')
assert a.label.replace('-','').isalnum()
o=r/'_scratch'/a.label;o.mkdir(exist_ok=False)
app=r/'installer/staging';marker=app/'isolated-install.json';guard=app/'python/Lib/site-packages/sitecustomize.py'
assert not marker.exists() and not guard.exists(),'Pre-existing instrumentation must be reviewed, not overwritten'
pths={str(q):sha(q) for q in (app/'python').glob('*._pth')};assert pths
package=json.loads((r/'docs/library/proof/candidate-package-02-2026-09-09/package-manifest.json').read_text(encoding='utf8'))
exe=r/'build'/package['package_name'];assert sha(exe)==package['package_sha256']
def bindings():
 for row in package['files']:
  assert sha(app/row['staged_path'])==row['checkout_and_staged_sha256'],row['staged_path']
  assert sha(r/row['source_path'])==row['checkout_and_staged_sha256'],row['source_path']
 return len(package['files'])
report={'source':a.source,'build_source':package['build_source'],'scope':'Original staged runtime; pre-Inno synthetic acquisition and transcript; no installed/client/visual acceptance',
         'utc_start':dt.datetime.now(dt.timezone.utc).isoformat(),'package_sha256':sha(exe),'before_bindings':bindings(),
         'guard_before':'absent','marker_before':'absent','pth_before':pths,'setup_executed':False,'installed_credit':False}
save(o/'observation.json',report)
for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','XAI_API_KEY','GROK_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY'):os.environ.pop(key,None)
os.environ['IG_FORBIDDEN_LIVE']=r'C:\Users\hello\AppData\Local\Uoink\index.db'
for key in ('USERPROFILE','LOCALAPPDATA','APPDATA','TEMP','TMP'):
 q=o/'environment'/key;q.mkdir(parents=True);os.environ[key]=str(q)
os.environ.update(PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
sys.path.insert(0,str(r/'scripts'))
from install_receipt.runner import OperatorRunner
from install_receipt.scenarios import ScenarioRunner
from install_receipt.constants import SCENARIO_IDS
from install_receipt.evidence import build_verdict
from install_receipt.browser_checkpoint import run_checkpoint
from install_receipt.process_identity import liveness
runner=None;scenarios=None
try:
 runner=OperatorRunner.create(receipt_root=o/'receipt',installed_app_path=app,package_path=exe,
  package_sha256=package['package_sha256'],isolated_profile=o/'receipt/profiles/empty',isolated_port=18331,
  synthetic=True,require_space=False,require_bundled_python=True,skip_ordinary_user_check=True)
 scenarios=ScenarioRunner(runner,fixture_port=18332);scenarios.prepare_profiles()
 for name in SCENARIO_IDS:
  result=scenarios.run_one(name);print(name,result['status'],result.get('error',''),flush=True)
 report['verdict']=build_verdict(runner.receipt_root,scenarios.outcomes,synthetic=True)
 scenarios.close()
 if not report['verdict']['counts']['fail']:
  report['browser']=run_checkpoint(runner,profile_name='child-life',hold_seconds=0)
except BaseException as exc:
 report['error']=type(exc).__name__+': '+str(exc);report['traceback']=traceback.format_exc();print(report['traceback'],flush=True)
finally:
 if scenarios:scenarios.close()
 try:
  report['after_bindings']=bindings();report['package_after']=sha(exe)
  report['pth_after']={str(q):sha(q) for q in (app/'python').glob('*._pth')}
  report['guard_after']='present' if guard.exists() else 'absent'
  assert report['pth_after']==pths and not guard.exists(),'Instrumentation restoration not affirmed'
  identities=[]
  for q in (o/'receipt/commands').glob('*.json'):
   data=json.loads(q.read_text(encoding='utf8'))
   if data.get('child'):identities.append(data['child'])
  report['command_identity_liveness']=[{'identity':i,'observed':liveness(i['pid'],i.get('created_ms'))} for i in identities]
  assert identities and all(i['observed']=='dead' for i in report['command_identity_liveness']),'Owned command identity still live or unknown'
  if marker.exists():
   data=marker.read_bytes();value=json.loads(data)
   assert Path(value['profile']).resolve().is_relative_to((o/'receipt/profiles').resolve()) and value['port']==18331
   save(o/'created-marker.json',{'path':str(marker),'sha256':hashlib.sha256(data).hexdigest(),'contents':value})
   assert marker.read_bytes()==data
   marker.unlink();report['marker_after']='removed only this observation-created marker after owned processes dead'
 except BaseException as exc:report['restoration_error']=type(exc).__name__+': '+str(exc)
 report['utc_end']=dt.datetime.now(dt.timezone.utc).isoformat();save(o/'observation.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('browser','traceback')},indent=2),flush=True)
raise SystemExit(1 if report.get('error') or report.get('restoration_error') or report.get('verdict',{}).get('counts',{}).get('fail',1) else 0)
