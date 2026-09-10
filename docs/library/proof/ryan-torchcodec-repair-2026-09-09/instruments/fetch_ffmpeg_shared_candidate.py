"""Fetch a compatible patched LGPL shared runtime, using exact release metadata."""
import datetime as dt,hashlib,json,urllib.request
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/native-binary-candidates-04';out.mkdir(exist_ok=False)
tag='autobuild-2026-07-31-14-10'
def fetch(url,name,limit):
 row={'url':url,'start_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'executed':False}
 h=hashlib.sha256();size=0
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Uoink-release-review'}),timeout=60) as response,(out/name).open('xb') as stream:
  row['http_status']=response.status
  while chunk:=response.read(1024*1024):
   size+=len(chunk);assert size<=limit;stream.write(chunk);h.update(chunk)
 row.update(bytes=size,sha256=h.hexdigest(),end_utc=dt.datetime.now(dt.timezone.utc).isoformat())
 (out/(name+'.download.json')).write_text(json.dumps(row,indent=2)+'\n',encoding='utf8');return row
fetch('https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/'+tag,'release.json',2000000)
release=json.loads((out/'release.json').read_text(encoding='utf8'))
choices=[x for x in release['assets'] if x['name'].endswith('-win64-lgpl-shared-7.1.zip')];assert len(choices)==1
asset=choices[0];assert 'n7.1.5-' in asset['name'] and asset['digest'].startswith('sha256:')
checks=next(x for x in release['assets'] if x['name']=='checksums.sha256')
fetch(checks['browser_download_url'],'checksums.sha256',100000)
declared={line.split()[1].lstrip('*'):line.split()[0] for line in (out/'checksums.sha256').read_text().splitlines() if line.strip()}
assert asset['digest']=='sha256:'+declared[asset['name']]
row=fetch(asset['browser_download_url'],asset['name'],asset['size'])
assert row['bytes']==asset['size'] and row['sha256']==declared[asset['name']]
(out/'selection.json').write_text(json.dumps({'tag':tag,'name':asset['name'],'archive':row,'both_published_digests_match':True,'scope':'Patched LGPL shared software candidate only; not executed'},indent=2)+'\n',encoding='utf8')
print(json.dumps(row,indent=2))
