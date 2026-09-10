"""Download two immutable, checksum-bound dependency candidates; do not execute."""
import concurrent.futures,datetime as dt,hashlib,json,urllib.request
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/native-binary-candidates-01';out.mkdir(exist_ok=False)
releases=json.loads((r/'_scratch/native-release-metadata-01/btbn-releases.json').read_text())
release=next(x for x in releases if x['tag_name']=='autobuild-2026-09-09-14-51')
names={'lgpl':'ffmpeg-n8.1.2-51-g7ba069f4f1-win64-lgpl-8.1.zip','gpl':'ffmpeg-n8.1.2-51-g7ba069f4f1-win64-gpl-8.1.zip','checksums':'checksums.sha256'}
assets={role:next(x for x in release['assets'] if x['name']==name) for role,name in names.items()}
def fetch(role):
 row=assets[role];target=out/row['name'];record={'role':role,'url':row['browser_download_url'],'metadata_sha256':row['digest'],'declared_bytes':row['size'],'start_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'executed':False}
 h=hashlib.sha256();size=0
 try:
  req=urllib.request.Request(row['browser_download_url'],headers={'User-Agent':'Uoink-release-review'})
  with urllib.request.urlopen(req,timeout=60) as response,target.open('xb') as stream:
   record['http_status']=response.status
   while block:=response.read(1024*1024):
    size+=len(block);assert size<=row['size'],'Oversized response'
    stream.write(block);h.update(block)
  record.update(bytes=size,sha256=h.hexdigest())
  assert size==row['size'] and row['digest']=='sha256:'+h.hexdigest()
  record['status']='hash-verified; not executed'
 except BaseException as exc:
  record.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
 finally:
  record['end_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
  (out/(role+'-download.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf8',newline='\n')
 return record
checksum=fetch('checksums')
declared={line.split()[1].lstrip('*'):line.split()[0] for line in (out/'checksums.sha256').read_text().splitlines() if line.strip()}
for role in ('lgpl','gpl'):assert assets[role]['digest']=='sha256:'+declared[names[role]]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(fetch,('lgpl','gpl')))
(out/'selection.json').write_text(json.dumps({'release':release['html_url'],'checksum_download':checksum,'candidates':results,'scope':'Public dependency candidates only. GPL is a private test prerequisite, not a shipping-license change. No binary executed.'},indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(results,indent=2))
