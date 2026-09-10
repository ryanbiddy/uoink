"""Extract two scanned native tools to a private fresh directory and observe versions."""
import argparse,datetime as dt,hashlib,json,os,subprocess,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--scan',required=True);p.add_argument('--out',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1];out=r/'_scratch'/a.out
assert out.parent==r/'_scratch' and a.out.startswith('native-bin-')
scan_path=r/'_scratch'/a.scan/'scan.json';scan=json.loads(scan_path.read_text(encoding='utf-8-sig'))
assert scan['exit']==0 and scan['sha256']==scan['sha256_after']
archive=Path(scan['file']);assert archive.is_relative_to(r/'_scratch')
with archive.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==scan['sha256']
out.mkdir(exist_ok=False)
record={'archive':str(archive),'archive_sha256':scan['sha256'],'scan':str(scan_path),'start_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'files':[]}
env=os.environ.copy()
for key in list(env):
 if key.endswith('API_KEY') or key=='ANTHROPIC_AUTH_TOKEN' or key.startswith('CLAUDE_CODE_USE_'):env.pop(key,None)
with zipfile.ZipFile(archive) as z:
 for name in ('ffmpeg.exe','ffprobe.exe'):
  choices=[x for x in z.infolist() if x.filename.endswith('/bin/'+name)]
  assert len(choices)==1
  member=choices[0];assert member.file_size<300000000
  target=out/name
  with z.open(member) as source,target.open('xb') as dest:
   while chunk:=source.read(1024*1024):dest.write(chunk)
  with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
  result=subprocess.run([str(target),'-version'],capture_output=True,env=env,timeout=20)
  (out/(name+'.version.stdout')).write_bytes(result.stdout);(out/(name+'.version.stderr')).write_bytes(result.stderr)
  row={'path':str(target),'zip_member':member.filename,'bytes':target.stat().st_size,'sha256':digest,'version_exit':result.returncode,'version_first_line':result.stdout.decode('utf8','replace').splitlines()[0]}
  record['files'].append(row);assert result.returncode==0
  with target.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==digest
record['end_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
(out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record,indent=2))
