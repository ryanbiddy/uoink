"""Request the existing isolated Desktop main window via its second-instance handler."""
import datetime as dt, json, os, subprocess, sys
from pathlib import Path
assert sys.flags.isolated and sys.flags.no_site
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07\native-gui01')
run=root/'desktop';profile=root/'p4/profile';app=root.parent/'app'
assert not (run/'result.json').exists(),'Initial owned desktop run already ended'
assert (app/'python/Lib/site-packages/sitecustomize.py').is_file()
ready=json.loads((run/'ready.json').read_text());data=Path(ready['desktop_data_dir'])
assert data==run/'user-data'
record={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'diagnosis':'Initial isolated Desktop process remains running but Sky exposes no window. Shipped index.chunk-BRN0sgAk.js calls bW() unconditionally in its second-instance handler before argv handling. This activation reuses the same isolated user-data path and no new fixture or login credentials.','prior_pid':ready['processes'][0]['pid']}
with (run/'activation-plan.json').open('x') as f:json.dump(record,f,indent=2)
env=dict(os.environ)
for key in tuple(env):
 if key.startswith(('ANTHROPIC_','OPENAI_','GEMINI_','GOOGLE_API_','GROK_','XAI_','CLAUDE_CODE_USE_','UOINK_')):env.pop(key,None)
env.update(json.loads((profile/'mcp.json').read_text())['mcpServers']['uoink']['env'])
env['CLAUDE_USER_DATA_DIR']=str(data)
env['IG_FORBIDDEN_LIVE']=r'C:\Users\hello\AppData\Local\Uoink\index.db'
env['HF_HUB_OFFLINE']='1';env['TRANSFORMERS_OFFLINE']='1'
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP'):env[key]=str(root/'environment'/key)
sys.path.insert(0,str(repo/'scripts/install_receipt'))
from p4_session import spawn_owned
with (run/'activation.stdout').open('xb') as out,(run/'activation.stderr').open('xb') as err:
 child=spawn_owned([ready['processes'][0]['argv'][0]],cwd=profile,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,label='desktop07-second-instance')
 try:
  record['pid']=child.pid
  record['exit_code']=child.wait(timeout=15)
 except subprocess.TimeoutExpired:record['error']='Second instance did not exit within 15 seconds'
 finally:record['cleanup']=child.terminate_tree(timeout=5)
with (run/'activation-result.json').open('x') as f:json.dump(record,f,indent=2)
