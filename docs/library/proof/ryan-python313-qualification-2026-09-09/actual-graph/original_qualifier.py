"""Resolve the real build dependency graph under a disposable official CPython 3.13."""
import datetime as dt,hashlib,json,os,re,subprocess,zipfile
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/python313-graph-01';out.mkdir(exist_ok=False)
scan=json.loads((r/'_scratch/native-scan-python-03/scan.json').read_text(encoding='utf-8-sig'))
archive=Path(scan['file']);assert scan['exit']==0 and scan['sha256']==scan['sha256_after']=='d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
assert sha(archive)==scan['sha256']
runtime=out/'python';runtime.mkdir()
with zipfile.ZipFile(archive) as z:
 for entry in z.infolist():
  assert not entry.is_dir() and not Path(entry.filename).is_absolute() and '..' not in Path(entry.filename).parts
  target=runtime/entry.filename;assert target.resolve().is_relative_to(runtime)
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as dest:dest.write(z.read(entry))
pth=runtime/'python313._pth';original=pth.read_bytes();assert b'#import site' in original
(out/'python313.original._pth').write_bytes(original)
pth.write_bytes(original.replace(b'#import site',b'import site'))
env=os.environ.copy()
for key in list(env):
 if key.endswith(('API_KEY','_TOKEN','_SECRET')) or key.startswith(('CLAUDE_CODE_USE_','PIP_')) or key=='GOOGLE_APPLICATION_CREDENTIALS':env.pop(key,None)
profile=out/'profile';profile.mkdir()
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP','XDG_DATA_HOME','UOINK_OUTPUT_DIR'):env[key]=str(profile)
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PIP_CONFIG_FILE=os.devnull,PIP_INDEX_URL='https://pypi.org/simple',PIP_CACHE_DIR=str(out/'cache'),PIP_DISABLE_PIP_VERSION_CHECK='1',UOINK_INDEX_PATH=str(profile/'unused-index.db'))
python=runtime/'python.exe';rows=[]
def run(label,argv):
 row={'label':label,'command':list(map(str,argv)),'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
 with (out/(label+'.stdout')).open('wb') as stdout,(out/(label+'.stderr')).open('wb') as stderr:
  result=subprocess.run(list(map(str,argv)),cwd=out,env=env,stdout=stdout,stderr=stderr,timeout=600)
 row.update(exit=result.returncode,finished_utc=dt.datetime.now(dt.timezone.utc).isoformat());rows.append(row)
 (out/'commands.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
 print(label,result.returncode,flush=True);assert result.returncode==0,(label,(out/(label+'.stderr')).read_text()[-2000:])
run('version',[python,'-I','-S','-B','-c','import sys,ssl,sqlite3; print(sys.version); print(ssl.OPENSSL_VERSION); print(sqlite3.sqlite_version)'])
getpip=r/'build/cache/get-pip.py';assert sha(getpip)=='a341e1a43e38001c551a1508a73ff23636a11970b61d901d9a1cad2a18f57055'
run('bootstrap',[python,'-I','-B',getpip,'--no-warn-script-location','--no-compile','pip==26.1.2','setuptools==83.0.0','wheel==0.47.0','packaging==26.2'])
build=(r/'build.ps1').read_text(encoding='utf8')
variables={'yt-dlp':'YTDLP','Pillow':'PILLOW','mcp':'MCP','keyring':'KEYRING','pystray':'PYSTRAY','pywebview':'PYWEBVIEW','pythonnet':'PYTHONNET','faster-whisper':'FASTER_WHISPER','whisperx':'WHISPERX'}
direct=[package+'=='+re.search(r'^\$'+variable+r"_VERSION\s*=\s*'([^']+)'",build,re.M).group(1) for package,variable in variables.items()]
run('resolve',[python,'-I','-B','-m','pip','install','--dry-run','--ignore-installed','--no-build-isolation','--no-compile','--report',out/'resolution.json','--constraint',r/'requirements-installer-lock.txt',*direct])
locked={line.split('==')[0].lower().replace('_','-'):line.split('==')[1] for line in (r/'requirements-installer-lock.txt').read_text().splitlines() if line and not line.startswith('#')}
report=json.loads((out/'resolution.json').read_text());actual={x['metadata']['name'].lower().replace('_','-'):x['metadata']['version'] for x in report['install']}
assert not any('-cp313t-' in x['download_info']['url'] for x in report['install'])
diff={'expected_count':len(locked),'resolved_count':len(actual),'missing':sorted(set(locked)-set(actual)),'extra':sorted(set(actual)-set(locked)),'changed':{n:[locked[n],actual[n]] for n in locked.keys()&actual.keys() if locked[n]!=actual[n]},'actual_python':report['environment'],'scope':'Real CPython 3.13 direct-build dependency resolution; not runtime/model acceptance'}
(out/'graph-diff.json').write_text(json.dumps(diff,indent=2)+'\n',encoding='utf8');print(json.dumps(diff,indent=2))
