import hashlib,json,shutil,subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
r=Path(__file__).resolve().parents[1]
w=Path(r'E:\AI\projects\uoink\worktrees\mirror-owner-admission-repair')
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
assert source=='4b949e2c7c4073c756adab986b5c2b44a6d0b811'
observations=[(w,'owner-repair01',11),(w,'owner-repair02',12),(w,'owner-repair03',12),(w,'owner-phase4-worker01',184),(r,'owner-checkout01',12),(r,'owner-phase4-checkout01',184)]
for root,label,expected in observations:
    suites=list(ET.parse(root/'_scratch'/label/'tests.xml').getroot().iter('testsuite'))
    assert sum(int(s.get('tests',0)) for s in suites)==expected,label
    assert not sum(int(s.get(k,0)) for s in suites for k in ['failures','errors','skipped']),label
    assert json.loads((root/'_scratch'/label/'results.json').read_text())[0]['exit']==0,label
for name in ['library_mirror.py','tests/test_mirror_owner_admission.py']:
    def blob(root):return subprocess.check_output(['git','hash-object','--path='+name,name],cwd=root,text=True).strip()
    assert blob(w)==blob(r),name
assert not subprocess.check_output(['git','diff','HEAD','--diff-filter=CDMRTUXB','--','tests'],cwd=r)
out=r/'docs/library/proof/mirror-owner-repair-2026-09-13';out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
def copy(src,rel):
    target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
for root,label,expected in observations:
    for p in (root/'_scratch'/label).rglob('*'):
        if p.is_file() and p.suffix in ('.py','.log','.xml','.json'):copy(p,Path(label)/p.relative_to(root/'_scratch'/label))
    events=root/'_scratch'/(label+'-original-events.json')
    if events.exists():copy(events,events.name)
for name in ['mirror-owner-reviewed.diff','library_mirror.owner-repair01.py','test_mirror_owner_admission.owner-repair01.py','test_mirror_owner_admission.owner-repair02.py','MIRROR-OWNER-REPAIR02-REVIEW.md','owner-repair01-launch-refusal.md','run_mirror_owner_verification.ps1','integrator_verify.py','seal_mirror_owner_repair.py']:
    copy(r/'_scratch'/name,Path('instruments-and-drafts')/name)
for name in ['library_mirror.py','tests/test_mirror_owner_admission.py']:
    copy(r/name,Path('accepted-source')/name)
copy(r/'docs/library/ASTRA-MIRROR-OWNER-REPAIR-VERDICT-2026-09-13.md','ASTRA-MIRROR-OWNER-REPAIR-VERDICT-2026-09-13.md')
(out/'summary.json').write_text(json.dumps({'source_before_patch':source,'worker_base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=w,text=True).strip(),'worker_focused':12,'checkout_focused':12,'worker_phase4':184,'checkout_phase4':184,'failures':0,'skipped':0,'new_tests':11,'original_diagnostic_in_focused':1,'existing_tests_modified':False,'full_tree_requalified':False,'release_ready':False},indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'worker_phase4':184,'checkout_phase4':184,'source_before_patch':source}))
