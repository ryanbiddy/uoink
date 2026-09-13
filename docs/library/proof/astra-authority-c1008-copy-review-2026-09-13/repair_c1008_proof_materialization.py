import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\c1008e0b-74f\gemini')
rel=Path('docs/library/proof/astra-authority-c1008-review-2026-09-13')
out=r/'docs/library/proof/astra-authority-c1008-copy-review-2026-09-13';out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
seal=json.loads((w/rel/'SHA256.json').read_text());changes=[]
for name,info in seal['files'].items():
    src=(w/rel/name).read_bytes();p=r/rel/name;actual=p.read_bytes()
    assert hashlib.sha256(src).hexdigest()==info['sha256']
    if actual!=src:
        assert actual.replace(b'\r\n',b'\n')==src.replace(b'\r\n',b'\n'),name
        dest=out/'converted-copies'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(actual)
        changes.append({'path':name,'actual_sha256':hashlib.sha256(actual).hexdigest(),'original_sha256':info['sha256']})
        p.write_bytes(src)
subprocess.run(['git','add','-f',str(rel)],cwd=r,check=True)
subprocess.run([str(r/'_scratch/ig-native/Scripts/python.exe'),'-B',str(r/'_scratch/verify_authority_c1008_proof.py')],cwd=r,check=True)
(out/'repair.json').write_text(json.dumps({'observed_failure':'copy verification asserted on .gitattributes before any commit','attempted_prevention':'git -c core.autocrlf=false apply --3way','finding':'That setting alone did not preserve every new proof working-file line ending; root text=auto and new nested attributes must be accounted for. Future proof application must stage the attributes before applying payloads or explicitly verify/copy from the bound originals.','repair':'Retain converted copies; restore only EOL-only mismatches from verified worker bytes; restage and compare every payload in Git and disk.','tests_rerun':False,'changes':changes},indent=2)+'\n',encoding='utf8')
for name in ['repair_c1008_proof_materialization.py','verify_authority_c1008_proof.py']:
    shutil.copyfile(r/'_scratch'/name,out/name)
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'repaired_copies':len(changes),'audit_payloads':len(files)}))
