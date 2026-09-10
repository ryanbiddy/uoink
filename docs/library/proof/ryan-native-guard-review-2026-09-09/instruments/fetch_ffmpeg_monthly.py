"""Fetch the reviewed, retained monthly shipping archive, with two hash authorities."""
import datetime as dt,hashlib,json,urllib.request
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'_scratch/native-binary-candidates-02';out.mkdir(exist_ok=False)
tag='autobuild-2026-08-31-13-27'
name='ffmpeg-n8.1.2-50-g1a748fe2cd-win64-lgpl-8.1.zip'
expected='f6274bbd9c247f9e90c1bbed066b03ed4a3907cece2fb91be6dd352393936365'
def fetch(url,path,limit):
 request=urllib.request.Request(url,headers={'User-Agent':'Uoink-release-review'})
 record={'url':url,'start_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'executed':False}
 h=hashlib.sha256();size=0
 try:
  with urllib.request.urlopen(request,timeout=60) as response,path.open('xb') as stream:
   record['http_status']=response.status
   while block:=response.read(1024*1024):
    size+=len(block);assert size<=limit
    stream.write(block);h.update(block)
  record.update(bytes=size,sha256=h.hexdigest(),status='downloaded')
 except BaseException as exc:
  record.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
 finally:
  record['end_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
  (out/(path.name+'.download.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
 return record
fetch('https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/'+tag,out/'release.json',2000000)
release=json.loads((out/'release.json').read_text())
asset=next(x for x in release['assets'] if x['name']==name)
checks=next(x for x in release['assets'] if x['name']=='checksums.sha256')
assert asset['digest']=='sha256:'+expected
fetch(checks['browser_download_url'],out/'checksums.sha256',100000)
declared={line.split()[1].lstrip('*'):line.split()[0] for line in (out/'checksums.sha256').read_text().splitlines() if line.strip()}
assert declared[name]==expected
record=fetch(asset['browser_download_url'],out/name,asset['size'])
assert record['sha256']==expected and record['bytes']==asset['size']
(out/'selection.json').write_text(json.dumps({'tag':tag,'role':'shipping LGPL candidate; not executed','archive':record,'github_digest':asset['digest'],'checksums_match':True},indent=2)+'\n',encoding='utf8')
print(json.dumps(record,indent=2))
