import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\213914a5-528\gemini')
rel=Path('docs/library/proof/gemini-mirror-authority-2026-09-13')
before=r/'_scratch/authority-proof-copy01-before';before.mkdir(exist_ok=False)
seal=json.loads((w/rel/'SHA256.json').read_text())
changes=[]
for name,info in seal['files'].items():
    original=(w/rel/name).read_bytes()
    assert hashlib.sha256(original).hexdigest()==info['sha256'],name
    destination=r/rel/name
    actual=destination.read_bytes()
    if actual != original:
        saved=before/name;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(actual)
        changes.append({'path':name,'before_sha256':hashlib.sha256(actual).hexdigest(),'expected_sha256':info['sha256'],'line_ending_conversion_only':actual.replace(b'\r\n',b'\n')==original.replace(b'\r\n',b'\n')})
        assert changes[-1]['line_ending_conversion_only'],name
        destination.write_bytes(original)
shutil.copyfile(w/rel/'SHA256.json',r/rel/'SHA256.json')
subprocess.run(['git','add','-f',str(rel)],cwd=r,check=True)
for name,info in seal['files'].items():
    assert hashlib.sha256((r/rel/name).read_bytes()).hexdigest()==info['sha256']
    assert hashlib.sha256(subprocess.check_output(['git','show',':'+(rel/name).as_posix()],cwd=r)).hexdigest()==info['sha256']
record={'failed_preflight':'seal_gemini_authority_checkout.py asserted at .gitattributes after writing its draft manifest; no success reported','reason':'Git apply materialized new proof files before their new binary attributes controlled working-tree checkout; changed line endings only','repair':'restore only the mismatched proof copies from the worker bytes already bound by its seal; preserve changed copies; stage and verify Git/disk hashes','changed':changes,'verified_payloads':len(seal['files'])}
(before/'repair.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
out=r/'docs/library/proof/astra-mirror-authority-2026-09-13'
shutil.copyfile(out/'SHA256.json',before/'preflight-draft-SHA256.json')
shutil.copytree(before,out/'copy-preflight')
shutil.copyfile(Path(__file__),out/Path(__file__).name)
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'SHA256.json'}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'restored_copies':len(changes),'verified_worker_payloads':len(seal['files']),'astra_payloads':len(files)}))
