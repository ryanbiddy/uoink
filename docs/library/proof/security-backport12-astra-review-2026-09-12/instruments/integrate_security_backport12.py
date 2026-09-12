import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\940c7fc1-f40\gemini')
name='docs/library/SECURITY-BACKPORT-FEASIBILITY-2026-09-12.md'
assert subprocess.check_output(['git','diff','--name-only'],cwd=w,text=True).strip()==name
p=r/'docs/library/proof/security-backport12-astra-review-2026-09-12';p.mkdir(exist_ok=False)
(p/'.gitattributes').write_text('* -text\n',encoding='utf8')
def copy(src,dest):
    q=p/dest;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,q)
for f in (r/'_scratch/security-backport12-review02').rglob('*'):
    if f.is_file():copy(f,'review/'+f.relative_to(r/'_scratch/security-backport12-review02').as_posix())
for row in json.loads((p/'review/source-bindings.json').read_text(encoding='utf8')):
    data=(r/row['path']).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
meta=r/'docs/library/proof/security-repair-gemini-2026-09-12'
for rel,row in json.loads((meta/'SHA256.json').read_text(encoding='utf8')).items():
    data=(meta/rel).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
for item in ('review_security_backport12.py','review_security_backport12_02.py','review_security_backport12_02.diff','repair_security_backport_reader12.py','integrate_security_backport12.py'):
    copy(r/'_scratch'/item,'instruments/'+item)
copy(r/'_scratch/security-backport12-review/reader-failure.json','reader-failure.json')
patch=subprocess.check_output(['git','diff','--binary','--',name],cwd=w)
assert patch==(p/'review/worker-original.patch').read_bytes()
result=subprocess.run(['git','apply','--3way',str(p/'review/worker-original.patch')],cwd=r,capture_output=True)
(p/'apply.stdout').write_bytes(result.stdout);(p/'apply.stderr').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
report=r/name
text=report.read_text(encoding='utf8')
report.write_text('> Retained worker analysis, not an approved repair plan. Several reachability,\n> dependency and proposed-test claims are corrected in\n> ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md. Read that review first.\n\n'+'\n'.join(line.rstrip() for line in text.splitlines())+'\n',encoding='utf8',newline='\n')
shutil.copyfile(r/'_scratch/ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.next.md',r/'docs/library/ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md')
shutil.copyfile(r/'_scratch/SECURITY-BACKPORT-FEASIBILITY-BRIEF-2026-09-12.md',r/'docs/library/SECURITY-BACKPORT-FEASIBILITY-BRIEF-2026-09-12.md')
files={q.relative_to(p).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(p.rglob('*')) if q.is_file()}
(p/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
docs=[name,'docs/library/ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md','docs/library/SECURITY-BACKPORT-FEASIBILITY-BRIEF-2026-09-12.md']
subprocess.run(['git','add','--',*docs],cwd=r,check=True)
allpaths=[(p/f).relative_to(r).as_posix() for f in [*files,'SHA256.json']]
subprocess.run(['git','add','-f','--',*allpaths],cwd=r,check=True)
for name in allpaths:assert subprocess.check_output(['git','show',':'+name],cwd=r)==(r/name).read_bytes()
subprocess.run(['git','diff','--cached','--check','--',*docs],cwd=r,check=True)
subprocess.run(['git','commit','-m','docs(library): correct Gemini backport feasibility review [940c7fc1]'],cwd=r,check=True)
print(json.dumps({'payloads':len(files),'primary_payloads_verified':35,'inspected_source_files_verified':13,'product_changed':False}))
