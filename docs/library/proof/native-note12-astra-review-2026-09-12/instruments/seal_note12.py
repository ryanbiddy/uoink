import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\d8840cdd-c3a\gemini')
p=r/'docs/library/proof/native-note12-astra-review-2026-09-12';p.mkdir(exist_ok=False)
(p/'.gitattributes').write_text('* -text\n',encoding='utf8')
def copy(src,dest):
    q=p/dest;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,q)
for f in (r/'_scratch/native-note12-review').iterdir():
    if f.is_file():copy(f,'transport/'+f.name)
checks=[]
for name in ('assets/dashboard/index.html','notes.py','server.py','tests/test_note_readiness_truth.py'):
    index=subprocess.check_output(['git','show',':'+name],cwd=r)
    worker=(w/name).read_bytes().replace(b'\r\n',b'\n')
    local=(r/name).read_bytes()
    assert index==worker==local.replace(b'\r\n',b'\n')
    checks.append({'path':name,'git_sha256':hashlib.sha256(index).hexdigest(),'worker_normalized_matches':True,'checkout_normalized_matches':True,'checkout_exact_matches':index==local})
(p/'transport-byte-verification.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf8')
attempts=[(w,n) for n in ('baseline-01','verify-01','verify-02','verify-03','verify-04','astra-native12-worker01','astra-note12-negative02','astra-note12-repair-worker02')]+[(r,n) for n in ('astra-note12-negative01','astra-note12-repair-checkout01')]
for root,label in attempts:
    for f in (root/'_scratch'/label).glob('*'):
        if f.is_file() and f.suffix in ('.json','.log','.xml'):copy(f,'attempts/'+label+'/'+f.name)
for name in ('prepare_note_review12.py','repair_note_review12.py','integrate_note12.py','seal_note12.py','integrator_verify.py'):
    copy(r/'_scratch'/name,'instruments/'+name)
files={q.relative_to(p).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(p.rglob('*')) if q.is_file()}
(p/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'source_transport_verified':True}))
