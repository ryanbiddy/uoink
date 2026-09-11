import hashlib,json,re
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'_scratch/package06-preinstall-review-01';out.mkdir(exist_ok=False)
seal=r/'docs/library/proof/candidate-package-06-2026-09-11'
lock=r/'requirements-installer-lock.txt'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def norm(s):return re.sub(r'[-_.]+','-',s.lower())
actual={norm(k):v for k,v in json.loads((seal/'runtime-distributions.json').read_text()).items()}
expected={}
for line in lock.read_text().splitlines():
 line=line.split('#')[0].strip()
 if not line:continue
 match=re.fullmatch(r'([\w.-]+)==([\w.+-]+)',line);assert match,line
 key=norm(match[1]);assert key not in expected
 expected[key]=match[2]
assert len(expected)==140
rows=[{'package':k,'locked':v,'actual':actual.get(k,{}).get('version'),'matches':actual.get(k,{}).get('version')==v} for k,v in sorted(expected.items())]
checkpoint=r/'installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin'
report={'scope':'All pinned versions in actual staging metadata. Installed bytes are still a separate pending observation. No model executed.','lock_sha256':sha(lock),'pins':len(rows),'passed':sum(row['matches'] for row in rows),'rows':rows,'unlocked_distributions':{k:v['version'] for k,v in actual.items() if k not in expected},'whisperx_checkpoint':{'path':str(checkpoint),'bytes':checkpoint.stat().st_size,'sha256':sha(checkpoint),'same_as_package03':sha(checkpoint)=='0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea'}}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8',newline='\n')
assert report['passed']==140,report
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
