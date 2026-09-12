"""Independent offline verification of the Gemini primary-source security packet."""
import datetime as dt, hashlib, json, subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
worker=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\0ee38a14-5a9\gemini')
proof=worker/'docs/library/proof/security-repair-gemini-2026-09-12'
out=repo/'_scratch/security12-review02';out.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((proof/'SHA256.json').read_text(encoding='utf8'))
for name,row in manifest.items():
 path=(proof/name).resolve();assert path.is_relative_to(proof)
 assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],name
queries=json.loads((proof/'osv/request.json').read_text(encoding='utf8'))['queries']
response=json.loads((proof/'osv/response.json').read_text(encoding='utf8'))['results']
pins=[line.strip().split('==') for line in (repo/'requirements-installer-lock.txt').read_text(encoding='utf8').splitlines() if line.strip() and not line.startswith('#')]
assert len(queries)==len(response)==len(pins)==140
assert [(q['package']['name'],q['version']) for q in queries]==[tuple(x) for x in pins]
entries=[(q['package']['name'],v['id']) for q,r in zip(queries,response) for v in r.get('vulns',[])]
sets=[]
for ident in sorted({ident for _,ident in entries}):
 rec=json.loads((proof/'osv/advisories'/f'{ident}.json').read_text(encoding='utf8'));assert rec['id']==ident
 group={ident,*rec.get('aliases',[])}
 overlap=[s for s in sets if s&group]
 for s in overlap:sets.remove(s);group|=s
 sets.append(group)
by_package={name:[ident for package,ident in entries if package==name] for name in sorted({name for name,_ in entries})}
for name,row in json.loads((proof/'pypi_summary.json').read_text(encoding='utf8')).items():
 assert sha(proof/row['saved_file'])==row['sha256']
 data=json.loads((proof/row['saved_file']).read_text(encoding='utf8'));assert data['info']['version']==row['latest_version']
wx=json.loads((proof/'pypi/whisperx.json').read_text(encoding='utf8'))['info']
assert 'torch~=2.8.0' in wx['requires_dist'] and 'huggingface-hub<1.0.0' in wx['requires_dist']
record={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'worker_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=worker,text=True).strip(),'checkout_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'sealed_payloads_verified':len(manifest),'pins_matched':len(pins),'raw_entries':len(entries),'alias_groups':len(sets),'by_package':by_package,'lightning_raw_entries':len(by_package['lightning']),'non_lightning_raw_entries':len(entries)-len(by_package['lightning']),'non_lightning_alias_groups':len([s for s in sets if 'GHSA-qqmf-gpg7-g8gw' not in s]),'whisperx_current_constraints':wx['requires_dist'],'clean':False,'new_product_repair':False,'rejected_new_tests':'All four omitted from active suite. Two freeze current pins/constraints without testing upstream metadata, one duplicates missing-runtime coverage, and the supposed redirected-DLL regression ends with isinstance(res, object), which is always true. Worker bytes and independent 25-pass run remain as reviewed evidence.','corrections':['19 minus one Lightning entry is 18, not the worker-reported 17. Raw scan remains 19/15.','No claim that every issue fixes in Torch 2.9/2.10 or Transformers 5.0; advisory-specific fixed versions differ.','Default installer root is LOCALAPPDATA/Uoink, not LOCALAPPDATA/Programs/Uoink.','Metadata is evidence against a drop-in update for the retained stack, not proof that every possible migration or backport is impossible.','Low exposure labels are not accepted security ratings; limited observed call paths do not erase retained findings.']}
assert len(entries)==19 and len(sets)==15
(out/'review.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k not in ['whisperx_current_constraints','by_package']},indent=2))
