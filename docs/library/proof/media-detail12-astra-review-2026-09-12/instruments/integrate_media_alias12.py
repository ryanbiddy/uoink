import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini')
p=r/'_scratch/media-detail12-review';tmp=r/'_scratch/media-alias-diff12';tmp.mkdir(exist_ok=False)
patch=b''
for name in ('server.py','tests/test_media_detail_boundaries.py'):
    a=tmp/'a'/name;b=tmp/'b'/name
    a.parent.mkdir(parents=True,exist_ok=True);b.parent.mkdir(parents=True,exist_ok=True)
    a.write_bytes(subprocess.check_output(['git','show',':'+name],cwd=r))
    b.write_bytes((w/name).read_bytes().replace(b'\r\n',b'\n'))
    result=subprocess.run(['git','-c','core.autocrlf=false','diff','--no-index','--binary','--full-index','--','a/'+name,'b/'+name],cwd=tmp,capture_output=True)
    assert result.returncode==1,result.stderr
    delta=result.stdout.replace(('a/a/'+name).encode(),('a/'+name).encode()).replace(('b/b/'+name).encode(),('b/'+name).encode())
    patch+=delta
(p/'alias-accepted.patch').write_bytes(patch)
result=subprocess.run(['git','apply','--3way',str(p/'alias-accepted.patch')],cwd=r,capture_output=True)
(p/'alias-apply.stdout').write_bytes(result.stdout);(p/'alias-apply.stderr').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
for name in ('server.py','assets/dashboard/index.html','tests/test_media_detail_boundaries.py','tests/test_dashboard_media_detail_truth.py'):
    assert subprocess.check_output(['git','show',':'+name],cwd=r)==(w/name).read_bytes().replace(b'\r\n',b'\n')==(r/name).read_bytes().replace(b'\r\n',b'\n')
(p/'final-accepted.patch').write_bytes(subprocess.check_output(['git','diff','--binary','--','server.py','assets/dashboard/index.html','tests/test_dashboard_media_detail_truth.py','tests/test_media_detail_boundaries.py'],cwd=w))
print('Timestamp delta applied by raw Git diff / three-way apply; all final bytes match.')
