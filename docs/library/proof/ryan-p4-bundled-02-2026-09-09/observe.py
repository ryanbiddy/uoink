"""Observe reviewed P4 driver against original staged bundled bytes. No install/client."""
import datetime as dt,hashlib,json,os,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
root=r/'_scratch/p4-bundled-02';root.mkdir(exist_ok=False)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,indent=2,default=str)+'\n',encoding='utf8',newline='\n')
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=r,text=True)
seal=r/'docs/library/proof/candidate-package-02-2026-09-09'
package=json.loads((seal/'package-manifest.json').read_text())
stage=r/'installer/staging';exe=stage/'python/python.exe';installer=r/'build'/package['package_name']
assert sha(installer)==package['package_sha256']
for row in package['files']:assert sha(stage/row['staged_path'])==row['checkout_and_staged_sha256'],row
pth=stage/'python/python311._pth';pth_before=pth.read_bytes()
guard=stage/'python/Lib/site-packages/sitecustomize.py';assert not guard.exists()
profile=root/'profile';operator=root/'operator.json';save(operator,{})
env=dict(os.environ)
for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','XAI_API_KEY','GROK_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','PYTHONPATH','UOINK_ISOLATED_APP_DIR'):
 env.pop(key,None)
for name in ('user','user/local','user/roaming','tmp'):(root/name).mkdir(exist_ok=True,parents=True)
env.update(IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db',
 USERPROFILE=str(root/'user'),LOCALAPPDATA=str(root/'user/local'),APPDATA=str(root/'user/roaming'),
 TEMP=str(root/'tmp'),TMP=str(root/'tmp'),PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
base=['--isolated-profile',str(profile),'--isolated-port','18232','--installed-app',str(stage),
 '--installed-interpreter',str(exe),'--package-manifest',str(seal/'package-manifest.json'),
 '--receipt-root',str(root),'--package-path',str(installer),'--source-bindings',str(seal/'source-bindings.json'),
 '--forbid-checkout',str(r),'--runtime-mode','source-runtime','--timeout-seconds','180']
results=[]
for name in ('prepare','check','prepare-client','collect'):
 command=[r'C:\Python314\python.exe','-I','-S','-B',str(r/'scripts/install_receipt/p4_operator.py'),name,*base]
 if name=='collect':command += ['--operator-json',str(operator)]
 with (root/(name+'.stdout')).open('xb') as out,(root/(name+'.stderr')).open('xb') as err:
  started=dt.datetime.now(dt.timezone.utc)
  result=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=err,timeout=240)
  ended=dt.datetime.now(dt.timezone.utc)
 row={'stage':name,'command':command,'exit_code':result.returncode,'start':str(started),'end':str(ended),'seconds':(ended-started).total_seconds()}
 results.append(row);print(json.dumps(row),flush=True)
 if result.returncode:break
after={'pth_unchanged':pth.read_bytes()==pth_before,'guard_removed':not guard.exists(),
       'package_unchanged':sha(installer)==package['package_sha256'],
       'all_142_source_bindings_unchanged':all(sha(stage/row['staged_path'])==row['checkout_and_staged_sha256'] for row in package['files'])}
save(root/'observation.json',{'source':source,'build_source':package['build_source'],'scope':'original bundled P4 kit stages; source-runtime, no Setup/client/model','installed_credit':False,'results':results,'after':after})
print(json.dumps(after),flush=True)
raise SystemExit(0 if len(results)==4 and all(row['exit_code']==0 for row in results) and all(after.values()) else 1)
