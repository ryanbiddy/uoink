import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\d8840cdd-c3a\gemini')
p=r/'_scratch/native-note12-review'
name='tests/test_note_readiness_truth.py'
assert (r/name).read_bytes()==(w/name).read_bytes()
subprocess.run(['git','add','-N','--',name],cwd=w,check=True)
patch=subprocess.check_output(['git','diff','--binary','--','assets/dashboard/index.html','server.py','notes.py',name],cwd=w)
(p/'accepted.patch').write_bytes(patch)
shutil.copyfile(r/name,p/'accepted-new-tests.py.txt')
# This is the newly created integrator test only; its exact bytes are retained above.
assert (r/name).resolve().parent==(r/'tests').resolve()
(r/name).unlink()
result=subprocess.run(['git','apply','--3way',str(p/'accepted.patch')],cwd=r,capture_output=True)
(p/'apply.stdout').write_bytes(result.stdout);(p/'apply.stderr').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
assert (r/name).read_bytes()==(w/name).read_bytes()
print('Accepted patch applied with three-way verification.')
