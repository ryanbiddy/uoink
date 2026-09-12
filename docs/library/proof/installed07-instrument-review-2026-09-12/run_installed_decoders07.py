"""Reviewed no-site observation using installed binaries; restore exact startup bytes."""
import argparse,datetime as dt,hashlib,json,os,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path);args=p.parse_args()
root=args.root.resolve();assert root.is_relative_to(Path(r'E:\AI\projects\uoink\installation-receipts'));app=root/'app'
seal=json.loads((r/'docs/library/proof/candidate-package-07-2026-09-12/package-manifest.json').read_text())
for label in ('install','same-version-reinstall'):
 record=json.loads((root/(label+'.json')).read_text());assert record['exit']==0 and record['package_sha256']==seal['package_sha256']
comparison=json.loads((root/'installed-file-comparison.json').read_text())
assert not comparison['failures'] and comparison['compared']==comparison['expected_installed']
pth=app/'python/python313._pth';original=pth.read_bytes()
assert original.count(b'import site')==1 and not (app/'python/Lib/site-packages/sitecustomize.py').exists()
modified=original.replace(b'import site',b'# import site disabled for this bounded decoder observation')
out=root/'decoder-commands-02.json';assert not out.exists()
env=os.environ.copy()
for key in list(env):
 if key.endswith(('API_KEY','_TOKEN','_SECRET')) or key.startswith('CLAUDE_CODE_USE_') or key in ('GOOGLE_APPLICATION_CREDENTIALS','PYTHONPATH','ANTHROPIC_BASE_URL'):env.pop(key,None)
profile=root/'decoder-environment-03';profile.mkdir(exist_ok=False)
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP','XDG_DATA_HOME','UOINK_OUTPUT_DIR','HF_HOME','TORCH_HOME','MPLCONFIGDIR'):env[key]=str(profile)
env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',UOINK_INDEX_PATH=str(profile/'unused-index.db'))
system_root=os.environ['SystemRoot'];assert (Path(system_root)/'System32').is_dir()
env['PATH']=str(app/'bin')+os.pathsep+str(Path(system_root)/'System32')+os.pathsep+system_root
report={'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'startup_original_sha256':hashlib.sha256(original).hexdigest(),'startup_observation_sha256':hashlib.sha256(modified).hexdigest(),'commands':[],'status':'running'}
failure=0
try:
 pth.write_bytes(modified)
 for script,label in [('package_decoder_probe.py','decoder-probe-02'),('installed_codec_probe.py','codec-probe-02')]:
  command=[str(app/'python/python.exe'),'-I','-S','-B',str(r/'_scratch'/script),'--app',str(app),'--out',str(root/label)]
  row={'command':command,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'instrument':script}
  with (root/(label+'.stdout')).open('xb') as stdout,(root/(label+'.stderr')).open('xb') as stderr:
   result=subprocess.run(command,cwd=root,env=env,stdout=stdout,stderr=stderr,timeout=90)
  row.update(exit=result.returncode,finished_utc=dt.datetime.now(dt.timezone.utc).isoformat());report['commands'].append(row)
  print(json.dumps(row),flush=True)
  if result.returncode:failure=result.returncode;break
 report['status']='passed' if failure==0 else 'failed'
finally:
 pth.write_bytes(original)
 report.update(startup_restored=pth.read_bytes()==original,finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
 out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
assert report['startup_restored']
raise SystemExit(failure)
