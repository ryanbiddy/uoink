import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\c1008e0b-74f\gemini')
original=w/'docs/library/proof/gemini-mirror-authority-repair-2026-09-13'
checked=0
for record in json.loads((original/'SHA256.json').read_text(encoding='utf-8-sig')):
    source=w/record['File'].replace('\\','/').removeprefix('./')
    assert source.resolve().is_relative_to(original.resolve())
    assert hashlib.sha256(source.read_bytes()).hexdigest()==record['Hash'],str(source)
    checked+=1
out=w/'docs/library/proof/astra-authority-c1008-review-2026-09-13';out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
def copy(src,rel):
    dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
for p in original.rglob('*'):
    if p.is_file():copy(p,Path('worker-proof')/p.relative_to(original))
for name in ['library_mirror.py','tests/test_library_mirror_process_authority.py','tests/test_mirror_process_identity_boundaries.py','docs/library/MIRROR-PROCESS-AUTHORITY-REPAIR-GEMINI-2026-09-13.md','_scratch/ASTRA-AUTHORITY-BOUNDARY-BRIEF.md']:
    copy(w/name,Path('reviewed-proposal')/name)
for label in ['astra-authority-worker01','astra-authority-boundary01']:
    for p in (w/'_scratch'/label).rglob('*'):
        if p.is_file() and p.suffix in ('.py','.json','.xml','.log'):copy(p,Path(label)/p.relative_to(w/'_scratch'/label))
for name in ['archive_authority_repair_c1008.py','run_process_authority_repair_verification.ps1','integrator_verify.py']:
    copy(r/'_scratch'/name,Path('instruments')/name)
subprocess.run(['git','add','-N','tests/test_library_mirror_process_authority.py','tests/test_mirror_process_identity_boundaries.py'],cwd=w,check=True)
(out/'proposed-product-and-tests.diff').write_bytes(subprocess.check_output(['git','diff','--binary','--','library_mirror.py','tests/test_library_mirror_process_authority.py','tests/test_mirror_process_identity_boundaries.py'],cwd=w))
(out/'summary.json').write_text(json.dumps({'worker_run':'c1008e0b-74f3-4662-ba89-ad4668775921','worker_base':'4b949e2c7c4073c756adab986b5c2b44a6d0b811','verified_original_payloads':checked,'worker_attempts':[{'passed':2,'failed':9},{'passed':10,'failed':1},{'passed':11,'failed':0}],'astra_worker_cases':{'passed':11,'failed':0},'astra_boundary_cases':{'passed':0,'failed':10},'product_accepted':False,'real_process_tests_executed':False,'tree08_cause_established':False},indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
subprocess.run(['git','add','-N','-f',str(out)],cwd=w,check=True)
patch=r/'_scratch/authority-c1008-rejected-evidence.diff'
patch.write_bytes(subprocess.check_output(['git','diff','--binary','--',str(out)],cwd=w))
print(json.dumps({'payloads':len(files),'original_payloads_verified':checked,'patch':str(patch),'accepted':False}))
