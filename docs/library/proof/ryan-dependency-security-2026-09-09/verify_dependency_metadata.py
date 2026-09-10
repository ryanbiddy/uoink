import json, urllib.request, concurrent.futures, datetime, hashlib
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'_scratch/dependency-metadata-01';out.mkdir(exist_ok=False)
specs=['pillow/12.3.0','nltk/3.10.3','cryptography/50.0.1','mcp/1.28.1','whisperx','lightning','torch','transformers/5.10.0','pyannote-audio','pyopenssl/26.3.0']
def fetch(spec):
 url='https://pypi.org/pypi/'+spec+'/json'
 try:
  with urllib.request.urlopen(url,timeout=30) as f: raw=f.read()
  (out/(spec.replace('/','-')+'.json')).write_bytes(raw)
  j=json.loads(raw);i=j['info']
  return dict(spec=spec,url=url,version=i['version'],requires_python=i.get('requires_python'),requires_dist=i.get('requires_dist'),wheels=[x['filename'] for x in j['urls'] if ('win_amd64' in x['filename'] and ('cp311' in x['filename'] or 'abi3' in x['filename'])) or 'none-any' in x['filename']],releases=list(j.get('releases',{})))
 except Exception as e:return dict(spec=spec,url=url,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: results=list(pool.map(fetch,specs))
(out/'summary.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),results=results),indent=2)+'\n',encoding='utf8')
ad=r/'docs/library/proof/ryan-installer-advisories-2026-09-09/advisories'
parents={}
def find(x):
 parents.setdefault(x,x)
 if parents[x]!=x:parents[x]=find(parents[x])
 return parents[x]
for p in ad.glob('*.json'):
 j=json.loads(p.read_text(encoding='utf8'));ids=[j['id']]+j.get('aliases',[])
 for x in ids:parents[find(x)]=find(ids[0])
components={}
for x in parents:components.setdefault(find(x),[]).append(x)
(out/'aliases.json').write_text(json.dumps(list(components.values()),indent=2)+'\n',encoding='utf8')
print('alias components',len(components))
for x in results:print(x['spec'],x.get('version',x.get('error')),len(x.get('wheels',[])),'compatible-tag wheels')
