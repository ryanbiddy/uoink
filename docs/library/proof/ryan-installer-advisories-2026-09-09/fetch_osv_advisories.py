import concurrent.futures,datetime as dt,json,re,urllib.request
from pathlib import Path
r=Path(__file__).resolve().parents[1];parent=r/'_scratch/installer-osv-01';out=parent/'advisories';out.mkdir(exist_ok=False)
findings=json.loads((parent/'findings.json').read_text(encoding='utf8'))
ids=sorted({v['id'] for f in findings for v in f['vulns']})
def fetch(key):
 assert re.fullmatch(r'[A-Z0-9a-z-]+',key)
 try:
  with urllib.request.urlopen('https://api.osv.dev/v1/vulns/'+key,timeout=30) as response:data=response.read(4*1024*1024)
  obj=json.loads(data);assert obj['id']==key
  (out/(key+'.json')).write_bytes(data)
  return {'id':key,'complete':True,'summary':obj.get('summary'),'aliases':obj.get('aliases',[]),'withdrawn':obj.get('withdrawn'),'severity':obj.get('severity',[]),'affected':obj.get('affected',[])}
 except Exception as exc:return {'id':key,'complete':False,'error':type(exc).__name__+': '+str(exc)}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(fetch,ids))
(parent/'advisory-summary.json').write_text(json.dumps({'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'rows':rows},indent=2)+'\n',encoding='utf8')
print('Fetched',sum(x['complete'] for x in rows),'of',len(ids),'advisories')
for f in findings:
 keys={v['id'] for v in f['vulns']};related=[x for x in rows if x['id'] in keys]
 fixed=sorted({e['fixed'] for x in related for a in x.get('affected',[]) if a.get('package',{}).get('name','').lower()==f['package']['name'].lower() for rang in a.get('ranges',[]) for e in rang.get('events',[]) if 'fixed' in e})
 print(f['package']['name'],f['version'],'fixed event versions:',','.join(fixed))
raise SystemExit(int(any(not x['complete'] for x in rows)))
