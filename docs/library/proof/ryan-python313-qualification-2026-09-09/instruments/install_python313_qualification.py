"""Install the real direct dependency graph into the already-scoped disposable interpreter."""
import datetime as dt,json,os,re,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/python313-graph-01'
assert json.loads((out/'graph-diff.json').read_text(encoding='utf8'))['resolved_runtime_count']==139
assert not (out/'install-command.json').exists()
env=os.environ.copy()
for key in list(env):
 if key.endswith(('API_KEY','_TOKEN','_SECRET')) or key.startswith(('CLAUDE_CODE_USE_','PIP_')) or key=='GOOGLE_APPLICATION_CREDENTIALS':env.pop(key,None)
profile=out/'profile'
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP','XDG_DATA_HOME','UOINK_OUTPUT_DIR'):env[key]=str(profile)
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PIP_CONFIG_FILE=os.devnull,PIP_INDEX_URL='https://pypi.org/simple',PIP_CACHE_DIR=str(out/'cache'),PIP_DISABLE_PIP_VERSION_CHECK='1',UOINK_INDEX_PATH=str(profile/'unused-index.db'))
build=(r/'build.ps1').read_text(encoding='utf8')
variables={'yt-dlp':'YTDLP','Pillow':'PILLOW','mcp':'MCP','keyring':'KEYRING','pystray':'PYSTRAY','pywebview':'PYWEBVIEW','pythonnet':'PYTHONNET','faster-whisper':'FASTER_WHISPER','whisperx':'WHISPERX'}
direct=[package+'=='+re.search(r'^\$'+variable+r"_VERSION\s*=\s*'([^']+)'",build,re.M).group(1) for package,variable in variables.items()]
command=[str(out/'python/python.exe'),'-I','-B','-m','pip','install','--no-warn-script-location','--no-build-isolation','--no-compile','--report',str(out/'install-report.json'),'--constraint',str(r/'requirements-installer-lock.txt'),*direct]
row={'command':command,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'Disposable software dependencies only; no model or application execution','exit':None}
try:
 with (out/'install.stdout').open('wb') as stdout,(out/'install.stderr').open('wb') as stderr:
  result=subprocess.run(command,cwd=out,env=env,stdout=stdout,stderr=stderr,timeout=1200)
 row['exit']=result.returncode
finally:
 row['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
 (out/'install-command.json').write_text(json.dumps(row,indent=2)+'\n',encoding='utf8')
print(json.dumps(row,indent=2));assert row['exit']==0
