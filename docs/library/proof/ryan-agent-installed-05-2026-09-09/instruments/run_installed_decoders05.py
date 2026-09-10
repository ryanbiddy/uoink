"""Run the two reviewed installed-decoder instruments after verified Setup."""
import datetime as dt,json,os,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 05');app=root/'app'
seal=json.loads((r/'docs/library/proof/candidate-package-05-2026-09-09/package-manifest.json').read_text(encoding='utf8'))
for stage in ('install','same-version-reinstall'):
 record=json.loads((root/(stage+'.json')).read_text(encoding='utf8'))
 assert record['exit']==0 and record['package_sha256']==seal['package_sha256']
comparison=json.loads((root/'installed-file-comparison.json').read_text(encoding='utf8'))
assert not comparison['failures'] and comparison['compared']==comparison['expected_installed']==32054
out=root/'decoder-commands.json';assert not out.exists()
env=os.environ.copy()
for key in list(env):
 if key.endswith(('API_KEY','_TOKEN','_SECRET')) or key.startswith('CLAUDE_CODE_USE_') or key in ('GOOGLE_APPLICATION_CREDENTIALS','PYTHONPATH'):env.pop(key,None)
profile=root/'decoder-environment';profile.mkdir(exist_ok=False)
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP','XDG_DATA_HOME','UOINK_OUTPUT_DIR','HF_HOME','TORCH_HOME','MPLCONFIGDIR'):env[key]=str(profile)
env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',UOINK_INDEX_PATH=str(profile/'unused-index.db'))
env['PATH']=str(app/'bin')+os.pathsep+env['SystemRoot']+'\\System32'+os.pathsep+env['SystemRoot']
rows=[]
for script,label in [('package_decoder_probe.py','decoder-probe'),('installed_codec_probe05.py','codec-probe')]:
 command=[str(app/'python/python.exe'),'-I','-S','-B',str(r/'_scratch'/script),'--app',str(app),'--out',str(root/label)]
 row={'command':command,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'instrument':script}
 with (root/(label+'.stdout')).open('xb') as stdout,(root/(label+'.stderr')).open('xb') as stderr:
  result=subprocess.run(command,cwd=root,env=env,stdout=stdout,stderr=stderr,timeout=90)
 row.update(exit=result.returncode,finished_utc=dt.datetime.now(dt.timezone.utc).isoformat());rows.append(row)
 out.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
 print(json.dumps(row,indent=2),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
