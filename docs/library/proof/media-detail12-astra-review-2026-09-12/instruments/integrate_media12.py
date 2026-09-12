import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini')
p=r/'_scratch/media-detail12-review'
names=['server.py','assets/dashboard/index.html','tests/test_dashboard_media_detail_truth.py','tests/test_media_detail_boundaries.py']
for name in names[2:]:
    assert (r/name).read_bytes()==(w/name).read_bytes()
    subprocess.run(['git','add','-N','--',name],cwd=w,check=True)
patch=subprocess.check_output(['git','diff','--binary','--',*names],cwd=w)
(p/'accepted.patch').write_bytes(patch)
for name in names[2:]:
    shutil.copyfile(r/name,p/(Path(name).name+'.accepted.txt'))
    assert (r/name).resolve().parent==(r/'tests').resolve()
    (r/name).unlink()
result=subprocess.run(['git','apply','--3way',str(p/'accepted.patch')],cwd=r,capture_output=True)
(p/'apply.stdout').write_bytes(result.stdout);(p/'apply.stderr').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
checks=[]
for name in names:
    git=subprocess.check_output(['git','show',':'+name],cwd=r)
    local=(r/name).read_bytes();worker=(w/name).read_bytes()
    assert git==worker.replace(b'\r\n',b'\n')==local.replace(b'\r\n',b'\n')
    checks.append({'path':name,'git_sha256':hashlib.sha256(git).hexdigest(),'normalized_worker_and_checkout_match':True})
(p/'transport-byte-verification.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf8')
print('Three-way media patch applied; staged and both-root source bytes verified.')
