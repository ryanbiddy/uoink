"""Acquire official Python archive and its public SBOM without executing it."""
import datetime as dt,hashlib,json,urllib.request
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/native-binary-candidates-03';out.mkdir(exist_ok=False)
name='python-3.13.15-embed-amd64.zip';base='https://www.python.org/ftp/python/3.13.15/'
expected='d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'
rows=[]
for filename,limit in ((name+'.spdx.json',1000000),(name,11009825)):
 row={'url':base+filename,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'executed':False}
 with urllib.request.urlopen(urllib.request.Request(base+filename,headers={'User-Agent':'Uoink-release-review'}),timeout=60) as response:
  data=response.read(limit+1);assert len(data)<=limit;row['http_status']=response.status
 (out/filename).write_bytes(data);row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),finished_utc=dt.datetime.now(dt.timezone.utc).isoformat());rows.append(row)
 if filename.endswith('.json'):
  package=next(x for x in json.loads(data)['packages'] if x['SPDXID']=='SPDXRef-PACKAGE-cpython')
  assert package['versionInfo']=='3.13.15' and package['downloadLocation']==base+name
  assert any(x['algorithm']=='SHA256' and x['checksumValue']==expected for x in package['checksums'])
 else:assert row['sha256']==expected and row['bytes']==11009825
(out/'download.json').write_text(json.dumps({'files':rows,'official_sbom_matches_archive':True,'scope':'Software dependency candidate only; not executed'},indent=2)+'\n',encoding='utf8')
print(json.dumps(rows,indent=2))
