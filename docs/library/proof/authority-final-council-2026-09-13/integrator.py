import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\6bbf0095-0d8\gemini')
report='docs/library/COUNCIL-AUTHORITY-FINAL-REVIEW-2026-09-13.md'
def git(root,*args):return subprocess.check_output(['git',*args],cwd=root)
assert git(w,'rev-parse','HEAD').decode().strip()=='4067de31e0ab3f0d1c1377b60c8a3db1fa6c76ed'
assert git(w,'status','--porcelain').decode().splitlines()==['?? '+report]
source=git(w,'show','HEAD:library_mirror.py')
assert git(w,'rev-parse','HEAD:library_mirror.py').decode().strip()=='cac85ac0b3937de8df542de9586a45723971594f'
assert source==git(r,'show','HEAD:library_mirror.py')
assert hashlib.sha256(source).hexdigest()=='843a08b1fba0364c2233fabb127197a0b2ca2be50c62930897666c3cfe220cdd'
assert hashlib.sha256((w/'library_mirror.py').read_bytes()).hexdigest()=='fd6db91a0a188eee16383e8a12b7fcb4bedf6edbba90b3840aa11e4087fab135'
dispatch=r/'_scratch/authority-final-council01-dispatch'
assert json.loads((dispatch/'exit.json').read_bytes())['exit']==0
out=r/'docs/library/proof/authority-final-council-2026-09-13';out.mkdir(exist_ok=False)
def put(rel,raw):
    target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
put('.gitattributes',b'* -text\n')
put('worker-report-original.md',(w/report).read_bytes())
put('library_mirror.git.py',source)
put('review-brief.md',(r/'docs/library/COUNCIL-AUTHORITY-FINAL-REVIEW-BRIEF-2026-09-13.md').read_bytes())
put('integrator.py',Path(__file__).read_bytes())
for f in dispatch.iterdir():
    if f.is_file():put('dispatch/'+f.name,f.read_bytes())
git(w,'add','-N','--',report)
patch=git(w,'diff','--binary','HEAD','--',report);put('worker.patch',patch)
process=subprocess.run(['git','apply','--3way',str(out/'worker.patch')],cwd=r,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
put('apply.log',process.stdout);assert process.returncode==0
assert git(w,'hash-object','--path='+report,report)==git(r,'hash-object','--path='+report,report)
put('receipt.json',(json.dumps({'run_id':'6bbf0095-0d82-4afa-b523-db16db5bb5d2','engine':'gemini-3.8-flash-high@high via Antigravity','transport_exit':0,'source_git_blob':'cac85ac0b3937de8df542de9586a45723971594f','source_changes':False,'worker_test_runs':0,'verdict':'No actionable finding in bounded process authority source review','release_ready':False},indent=2)+'\n').encode())
files={f.relative_to(out).as_posix():{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in out.rglob('*') if f.is_file()}
(out/'SHA256.json').write_text(json.dumps({'files':files},indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'payloads':len(files),'source_blob_verified':True,'three_way_apply_exit':0}))
