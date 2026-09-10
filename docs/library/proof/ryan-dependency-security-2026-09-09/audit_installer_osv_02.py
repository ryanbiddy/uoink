"""Read-only public package/version audit; no product imports or source uploads."""
import datetime as dt,hashlib,json,re,subprocess,sys,urllib.request
from pathlib import Path
r=Path(__file__).resolve().parents[1];o=r/'_scratch/installer-osv-02';o.mkdir(exist_ok=False)
lock=r/'requirements-installer-lock.txt';raw=lock.read_bytes();queries=[]
for line in raw.decode('utf8').splitlines():
 line=line.strip()
 if not line or line.startswith('#'):continue
 m=re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s;]+)',line);assert m,line
 queries.append({'package':{'ecosystem':'PyPI','name':m[1]},'version':m[2]})
def save(name,data):(o/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf8')
save('request.json',{'queries':queries})
summary={'source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),'utc_start':dt.datetime.now(dt.timezone.utc).isoformat(),'lock_sha256':hashlib.sha256(raw).hexdigest(),'packages':len(queries),'endpoint':'https://api.osv.dev/v1/querybatch','scope':'Only public PyPI names and versions sent; no source, library, paths or credentials. Version database matches do not prove exploitability or absence of unknown vulnerabilities.','complete':False}
save('summary.json',summary)
try:
 pending=list(enumerate(queries));results=[[] for _ in queries];page=0
 while pending:
  page+=1;assert page<20,'Pagination bound reached'
  data=json.dumps({'queries':[q for _,q in pending]}).encode()
  request=urllib.request.Request(summary['endpoint'],data=data,headers={'Content-Type':'application/json','User-Agent':'Uoink-release-package-audit/1'},method='POST')
  with urllib.request.urlopen(request,timeout=45) as response:
   body=response.read(32*1024*1024+1);assert len(body)<=32*1024*1024
   (o/f'response-{page}.json').write_bytes(body)
  batch=json.loads(body)['results'];assert len(batch)==len(pending)
  nxt=[]
  for (idx,q),result in zip(pending,batch):
   results[idx].extend(result.get('vulns',[]))
   if result.get('next_page_token'):nxt.append((idx,{**queries[idx],'page_token':result['next_page_token']}))
  pending=nxt
 findings=[{**q,'vulns':v} for q,v in zip(queries,results) if v]
 save('findings.json',findings)
 summary.update(complete=True,pages=page,affected_packages=len(findings),advisory_matches=sum(len(v) for v in results),findings=findings)
except Exception as exc:
 summary['error']=type(exc).__name__+': '+str(exc)
finally:
 summary['utc_end']=dt.datetime.now(dt.timezone.utc).isoformat();save('summary.json',summary)
print(json.dumps(summary,indent=2))
raise SystemExit(0 if summary['complete'] else 1)
