import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];folder='docs/library/proof/ryan-p4-embedded-probe-2026-09-10'
manifest=json.loads((r/folder/'SHA256.json').read_text());rows=[]
for name,expected in manifest['files'].items():
 raw=subprocess.check_output(['git','show','HEAD:'+folder+'/'+name],cwd=r)
 rows.append({'path':name,'expected_sha256':expected['sha256'],'committed_sha256':hashlib.sha256(raw).hexdigest(),'matches':hashlib.sha256(raw).hexdigest()==expected['sha256']})
report={'source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),'status':'PASS' if all(x['matches'] for x in rows) else 'FAIL','files':rows,'repair_if_needed':'Set -text for this new hash-sealed proof path and re-add original working bytes after the active complete tree finishes. No tests or measurements rerun; preserve this first byte audit.'}
(r/'_scratch/probe-proof-git-first-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps({'status':report['status'],'mismatches':[x['path'] for x in rows if not x['matches']]}))
