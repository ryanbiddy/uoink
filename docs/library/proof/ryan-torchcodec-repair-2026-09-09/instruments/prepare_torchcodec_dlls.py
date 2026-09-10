import hashlib,json,zipfile
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/torchcodec-native-01';out.mkdir(exist_ok=False)
scan=json.loads((r/'_scratch/native-scan-shared-04/scan.json').read_text(encoding='utf-8-sig'));archive=Path(scan['file'])
assert scan['exit']==0 and scan['sha256']==scan['sha256_after']=='0f376f96fb38554ccefb1b2ae9c7c6a7b351f0e60a372b38262c320e8392c5d0'
with archive.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==scan['sha256']
rows=[]
with zipfile.ZipFile(archive) as z:
 names=[x for x in z.infolist() if '/bin/' in x.filename and x.filename.endswith('.dll')]
 assert names and len({Path(x.filename).name for x in names})==len(names)
 for member in names:
  assert member.filename.startswith('ffmpeg-n7.1.5-12-g1fdbca85aa-win64-lgpl-shared-7.1/bin/')
  dest=out/Path(member.filename).name;data=z.read(member);dest.write_bytes(data)
  rows.append({'path':str(dest),'member':member.filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(out/'receipt.json').write_text(json.dumps({'archive_sha256':scan['sha256'],'files':rows,'executed':False},indent=2)+'\n',encoding='utf8');print(json.dumps(rows,indent=2))
