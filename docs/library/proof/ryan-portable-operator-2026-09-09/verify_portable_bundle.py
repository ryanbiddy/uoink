"""Extract and exercise only pre-install preparation; never invoke Setup or a client."""
import argparse,datetime as dt,hashlib,json,os,subprocess,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--zip',type=Path,required=True);p.add_argument('--label',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1]
assert a.label.replace('-','').isalnum()
out=r/'_scratch'/a.label;out.mkdir(exist_ok=False)
folder=out/'Uoink Receipt Kit';folder.mkdir()
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,obj):path.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf8')
with zipfile.ZipFile(a.zip) as z:
 for name in z.namelist():
  assert (folder/name).resolve().is_relative_to(folder.resolve()),name
 z.extractall(folder)
manifest=json.loads((folder/'BUNDLE-SHA256.json').read_text(encoding='utf8'))
def verify():
 for name,entry in manifest['files'].items():
  path=folder/name
  assert path.resolve().is_relative_to(folder.resolve()),name
  assert path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256'],name
 return len(manifest['files'])
before=verify();package=json.loads((folder/'package-manifest.json').read_text(encoding='utf8'))
env=dict(os.environ)
for key in ('ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','OPENAI_API_KEY','XAI_API_KEY','GROK_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','PYTHONPATH','UOINK_ISOLATED_APP_DIR'):
 env.pop(key,None)
for key in ('USERPROFILE','LOCALAPPDATA','APPDATA','TEMP','TMP','UOINK_DATA_ROOT','UOINK_OUTPUT_ROOT','UOINK_OUTPUT_DIR','YOINK_OUTPUT_DIR'):
 path=out/'environment'/key;path.mkdir(parents=True);env[key]=str(path)
env.update(IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',UOINK_INDEX_PATH=str(out/'unused-index.db'))
receipt=out/'receipt';app=out/'Future Installed App'
kit=folder/'scripts/install_receipt'
base=[r'C:\Python314\python.exe','-I','-S','-B']
commands=[('prepare',base+[str(kit/'cli.py'),'prepare-before-install',
 '--intended-app',str(app),'--package',str(folder/package['package_name']),
 '--package-sha256',package['package_sha256'],'--isolated-profile',str(receipt/'profiles/empty'),
 '--isolated-port','18481','--fixture-port','18480','--receipt-root',str(receipt),
 '--manifest',str(folder/'c22-operator-manifest.json'),'--synthetic','--allow-ordinary-user']),
 ('p4-help',base+[str(kit/'p4_operator.py'),'--help'])]
results=[]
for name,argv in commands:
 started=dt.datetime.now(dt.timezone.utc)
 with (out/(name+'.stdout')).open('xb') as stdout,(out/(name+'.stderr')).open('xb') as stderr:
  process=subprocess.run(argv,cwd=folder,env=env,stdout=stdout,stderr=stderr,timeout=120)
 row={'name':name,'argv':argv,'exit':process.returncode,'started_utc':started.isoformat(),'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
 results.append(row);save(out/'commands.json',results)
 print(name,process.returncode,flush=True)
 if process.returncode:break
report={'zip':str(a.zip),'zip_sha256':sha(a.zip),'bundle_source':manifest['bundle_source'],
 'validation_source':manifest['validation_source'],'payload_files_before':before,'payload_files_after':verify(),
 'app_created':app.exists(),'results':results,'setup_executed':False,'client_executed':False,'installed_credit':False,
 'profile_names':sorted(x.name for x in (receipt/'profiles').iterdir() if x.is_dir()) if (receipt/'profiles').is_dir() else []}
save(out/'observation.json',report)
assert len(results)==2 and all(x['exit']==0 for x in results) and not app.exists(),report
print(json.dumps(report,indent=2))
