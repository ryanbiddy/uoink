"""Explicit package-bound, same-account installed receipt observation. Never runs Setup."""
import argparse, datetime as dt, hashlib, json, os, stat, subprocess, sys, time, traceback
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','c22','browser','p4-prepare','p4-check','p4-prepare-client','p4-collect'])
p.add_argument('--root',required=True,type=Path);p.add_argument('--seal',required=True,type=Path);p.add_argument('--package',required=True,type=Path)
a=p.parse_args();r=Path(__file__).resolve().parents[1]
assert a.stage in ('p4-prepare','p4-check','p4-prepare-client'), 'Fresh client fixture must remain uncollected'
assert sys.flags.isolated and sys.flags.no_site
root=a.root.resolve();seal=a.seal.resolve();exe=a.package.resolve()
assert root.is_relative_to(Path(r'E:\AI\projects\uoink\installation-receipts')) and ' ' in str(root)
assert not root.is_relative_to(r),'Installed provenance must be outside the checkout'
for entry in (a.root.absolute(),*a.root.absolute().parents):
 if entry.exists():assert not entry.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,entry
assert seal.is_relative_to(r/'docs/library/proof')
def sha(q):
 with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(q,value):
 with q.open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2,default=str)+'\n')
package=json.loads((seal/'package-manifest.json').read_text(encoding='utf8'))
sealed_files=json.loads((seal/'SHA256.json').read_text(encoding='utf8'))['files']
assert isinstance(sealed_files,dict)
for name,row in sealed_files.items():
 q=(seal/name).resolve();assert q.is_relative_to(seal)
 assert q.stat().st_size==row['bytes'] and sha(q)==row['sha256'],name
assert sha(exe)==package['package_sha256'] and exe.stat().st_size==package['package_bytes']
for row in package['files']:assert sha(r/row['source_path'])==row['checkout_and_staged_sha256'],row['source_path']
for key in ('ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY','OPENAI_API_KEY','XAI_API_KEY','GROK_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','PYTHONPATH','UOINK_ISOLATED_APP_DIR'):
 os.environ.pop(key,None)
os.environ.update(IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
# Preserve the actual USERPROFILE identity; isolate mutable child environment paths.
if a.stage=='prepare':root.mkdir(parents=True,exist_ok=False)
else:assert root.is_dir()
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP'):
 q=root/'environment'/key;q.mkdir(parents=True,exist_ok=True);os.environ[key]=str(q)
app=root/'app';c22=root/'c22';profile=c22/'profiles/empty';port=18081
record_path=root/('fresh-client-'+a.stage+'-observation.json');assert not record_path.exists()
record={'stage':a.stage,'utc_start':dt.datetime.now(dt.timezone.utc).isoformat(),'actual_userprofile':os.environ.get('USERPROFILE'),'account_isolation':'same account, separate app/data/credential namespace; not OS-wide containment','throwaway_account':False,'package_sha256':sha(exe),'package_source':package['build_source'],'active_package_seal':str(seal),'source_bindings':len(package['files']),'installed_credit':False}
sys.path.insert(0,str(r/'scripts'))
import install_receipt.manifest as manifest
# The compatibility loader has a historical default. Bind its data directory to
# this explicitly selected seal, retaining all package/source integrity checks.
manifest.CANDIDATE_PACKAGE_02_DIR=seal
from install_receipt.runner import OperatorRunner
from install_receipt.scenarios import ScenarioRunner
from install_receipt.evidence import build_verdict
from install_receipt.constants import SCENARIO_IDS
from install_receipt.process_identity import liveness
from install_receipt.receipt_integrity import verify_installed_bindings
runner=None;scenarios=None
pth_before={str(q):sha(q) for q in (app/'python').glob('*._pth')} if app.exists() else {}
guard=app/'python/Lib/site-packages/sitecustomize.py'
assert not guard.exists(),'Existing runtime instrumentation must be reviewed first'
try:
 if a.stage=='prepare':
  assert not app.exists()
  value=manifest.example_manifest();value.update(sealed_by='Astra',expected_package_sha256=package['package_sha256'],candidate_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),installer_source_sha=package['build_source'])
  save(root/'c22-operator-manifest.json',value)
  runner=OperatorRunner.prepare_before_install(receipt_root=c22,intended_app_path=app,package_path=exe,package_sha256=package['package_sha256'],isolated_profile=profile,isolated_port=port,manifest_path=root/'c22-operator-manifest.json',synthetic=False,require_space=True,skip_ordinary_user_check=True)
  record['authorized_account_exception']='Ryan delegated same-account isolation after review; API skip_ordinary_user_check used, actual identity retained'
  scenarios=ScenarioRunner(runner,fixture_port=18080);record['prepared']=scenarios.prepare_profiles();scenarios.close()
 else:
  for label in ('install','same-version-reinstall'):
   observed=json.loads((root/(label+'.json')).read_text(encoding='utf8'))
   assert observed['exit']==0 and observed['package_sha256']==package['package_sha256']
   assert (root/(label+'.shortcuts.json')).is_file()
  record['installed_binding_report_before']=verify_installed_bindings(app,manifest.load_candidate_package_02())
  assert record['installed_binding_report_before']['ok'],record['installed_binding_report_before']
  if a.stage in ('c22','browser'):
   runner=OperatorRunner.continue_existing(receipt_root=c22,installed_app_path=app,package_path=exe,package_sha256=package['package_sha256'],isolated_profile=profile,isolated_port=port,synthetic=False,require_space=True,require_bundled_python=True)
   if a.stage=='c22':
    assert not runner.completed_scenario_ids(),'Fresh scenario results required'
    scenarios=ScenarioRunner(runner,fixture_port=18080);scenarios.prepare_profiles()
    for name in SCENARIO_IDS:
     result=scenarios.run_one(name);print(name,result['status'],result.get('error',''),flush=True)
    record['verdict']=build_verdict(c22,scenarios.outcomes,synthetic=False)
    scenarios.close()
    assert not record['verdict']['counts']['fail'],'Scenario failure retained'
   else:
    from install_receipt.browser_checkpoint import run_checkpoint
    def observe(state):
     deadline=time.monotonic()+900
     while time.monotonic()<deadline:
      if (c22/'artifacts/browser-observation-complete.json').exists():return
      time.sleep(.5)
     raise TimeoutError('Browser observation deadline; preserve missing evidence')
    record['browser']=run_checkpoint(runner,profile_name='child-life',observe=observe)
  else:
   stage=a.stage.removeprefix('p4-');p4=root/'p4-client';p4.mkdir(exist_ok=True)
   command=[sys.executable,'-I','-S','-B',str(r/'scripts/install_receipt/p4_operator.py'),stage,
    '--isolated-profile',str(p4/'profile'),'--isolated-port','18282','--installed-app',str(app),'--installed-interpreter',str(app/'python/python.exe'),
    '--package-manifest',str(seal/'package-manifest.json'),'--receipt-root',str(p4),'--package-path',str(exe),'--source-bindings',str(seal/'source-bindings.json'),
    '--forbid-checkout',str(r),'--runtime-mode','installed','--timeout-seconds','300']
   if stage=='collect':command+=['--operator-json',str(p4/'profile/operator.json')]
   record['command']=command
   with (root/('fresh-client-'+a.stage+'.stdout')).open('xb') as out,(root/('fresh-client-'+a.stage+'.stderr')).open('xb') as err:
    result=subprocess.run(command,cwd=r,env=dict(os.environ),stdout=out,stderr=err,timeout=360)
   record['exit']=result.returncode;assert result.returncode==0,'Original installed stage failed'
  record['installed_binding_report_after']=verify_installed_bindings(app,manifest.load_candidate_package_02())
  record['source_bindings_after']=record['installed_binding_report_after']['ok']
  assert record['source_bindings_after']
 record['status']='completed_pending_independent_review'
except BaseException as exc:
 record.update(status='failed',error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc());print(record['traceback'],flush=True)
finally:
 if scenarios:scenarios.close()
 if app.exists():
  record['pth_before']=pth_before;record['pth_after']={str(q):sha(q) for q in (app/'python').glob('*._pth')}
  record['guard_absent_after']=not guard.exists()
  if record['pth_after']!=pth_before or not record['guard_absent_after']:
   record.update(status='failed',restoration_error='Original interpreter paths/guard restoration not affirmed')
 if a.stage=='c22':
  identities=[];unexpected=[]
  for q in (c22/'commands').glob('*.json'):
   value=json.loads(q.read_text(encoding='utf8'))
   if value.get('child'):identities.append(value['child'])
  record['owned_command_liveness']=[{'identity':i,'observed':liveness(i['pid'],i.get('created_ms'))} for i in identities]
  if not identities or any(i['observed']!='dead' for i in record['owned_command_liveness']):record.update(status='failed',cleanup_error='Owned command identities not all proven dead')
  import re
  for q in (c22/'commands').glob('*helper-*.log'):
   for line in q.read_text(encoding='utf8',errors='replace').splitlines():
    if ' ERROR ' not in line and ' CRITICAL ' not in line:continue
    expected=('helper-child-interrupt.' in q.name or 'helper-child-regfail.' in q.name) and re.search(r' ERROR capture backend raised for st_[a-z0-9]+$',line)
    if not expected:unexpected.append({'path':str(q),'line':line})
  record['unexpected_runtime_errors']=unexpected
  if unexpected:record.update(status='failed',runtime_error='Unexpected helper errors retained')
 record['utc_end']=dt.datetime.now(dt.timezone.utc).isoformat();save(record_path,record)
print(json.dumps(record,indent=2,default=str),flush=True)
raise SystemExit(0 if record['status']=='completed_pending_independent_review' else 1)
