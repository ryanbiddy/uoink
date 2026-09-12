"""Stage only the reviewed seal and notes, handling exact known ignore matches."""
from pathlib import Path
import hashlib,json,subprocess
r=Path(__file__).resolve().parents[1]
seal=r/'docs/library/proof/ryan-agent-installed-07-2026-09-12'
files=json.loads((seal/'SHA256.json').read_text())['files'];paths=[]
for name,row in files.items():
    p=(seal/name).resolve();assert p.is_relative_to(seal)
    data=p.read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
    paths.append(p.relative_to(r).as_posix())
docs=['ASTRA-INSTALLED-PACKAGE-07-VERDICT-2026-09-12.md','INSTALLED-07-NATIVE-PROMPT-OBSERVATION-2026-09-12.md',
      'INSTALLED-07-REVIEW-PATH-CORRECTION-2026-09-12.md','INSTALL-RECEIPT-RUNBOOK-2026-09-09.md',
      'ORCHESTRATION-HANDOFF-2026-09-08.md','RELEASE-NOTES-LIVING-LIBRARY.md']
subprocess.run(['git','add','--',seal.relative_to(r).as_posix(),*['docs/library/'+n for n in docs]],cwd=r,check=True,capture_output=True)
ignored=subprocess.run(['git','check-ignore','-z','--stdin'],cwd=r,input='\0'.join(paths)+'\0',text=True,capture_output=True)
assert ignored.returncode in (0,1)
ignored_paths=[p for p in ignored.stdout.split('\0') if p]
assert all(p in paths for p in ignored_paths)
if ignored_paths:subprocess.run(['git','add','-f','--',*ignored_paths],cwd=r,check=True,capture_output=True)
for path in paths:
    data=subprocess.check_output(['git','show',':'+path],cwd=r)
    row=files[str(Path(path).relative_to(seal.relative_to(r))).replace('\\','/')]
    assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],path
report={'seal':seal.name,'payloads':len(paths),'staged_blob_hashes_match':True,'exact_force_adds':ignored_paths}
with (r/'_scratch/installed07-staged-proof-check.json').open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
