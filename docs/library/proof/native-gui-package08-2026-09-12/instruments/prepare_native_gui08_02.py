"""Prepare a new installed operator fixture; never start a GUI or a model."""
import datetime as dt, hashlib, json, os, subprocess, sys
from pathlib import Path
assert sys.flags.isolated and sys.flags.no_site
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08\native-gui02')
root.mkdir(exist_ok=False)
app=root.parent/'app'; profile=root/'p4/profile'
seal=repo/'docs/library/proof/candidate-package-08-2026-09-12'
for key in tuple(os.environ):
 if key.startswith(('ANTHROPIC_','OPENAI_','GEMINI_','GOOGLE_API_','GROK_','XAI_','CLAUDE_CODE_USE_')):
  os.environ.pop(key,None)
os.environ.update(IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
os.environ.pop('PYTHONPATH',None)
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP'):
 path=root/'environment'/key;path.mkdir(parents=True);os.environ[key]=str(path)
command=[sys.executable,'-I','-S','-B',str(repo/'scripts/install_receipt/p4_operator.py'),'prepare','--isolated-profile',str(profile),'--isolated-port','18484','--installed-app',str(app),'--installed-interpreter',str(app/'python/python.exe'),'--package-manifest',str(seal/'package-manifest.json'),'--receipt-root',str(root/'p4'),'--package-path',str(repo/'build/Uoink-Setup-3.8.0.exe'),'--source-bindings',str(seal/'source-bindings.json'),'--forbid-checkout',str(repo),'--runtime-mode','installed','--timeout-seconds','300']
record={'utc_start':dt.datetime.now(dt.timezone.utc).isoformat(),'command':command,'purpose':'new native GUI operator fixture; existing acceptance fixtures unchanged'}
with (root/'prepare.stdout').open('xb') as out,(root/'prepare.stderr').open('xb') as err:
 result=subprocess.run(command,cwd=repo,env=dict(os.environ),stdout=out,stderr=err,timeout=360)
record.update(exit_code=result.returncode,utc_end=dt.datetime.now(dt.timezone.utc).isoformat())
(root/'prepare.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record,indent=2))
raise SystemExit(result.returncode)
