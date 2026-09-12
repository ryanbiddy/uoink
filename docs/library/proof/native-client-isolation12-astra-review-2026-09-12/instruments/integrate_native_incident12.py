"""Integrate the static worker review after the frozen package-input seal exists."""
import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
assert (r/'docs/library/proof/candidate-package-08-2026-09-12/SHA256.json').is_file()
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\46e8e6dc-ea4\gemini')
name='docs/library/NATIVE-CLIENT-ISOLATION-WORKER-2026-09-12.md'
assert subprocess.check_output(['git','diff','--name-only'],cwd=w,text=True).strip()==name
p=r/'docs/library/proof/native-client-isolation12-astra-review-2026-09-12';p.mkdir(exist_ok=False)
(p/'.gitattributes').write_bytes(b'* -text\n')
def copy(src,rel):
 target=p/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
for f in (s/'native-client-incident12-review02').rglob('*'):
 if f.is_file():copy(f,'review/'+f.relative_to(s/'native-client-incident12-review02').as_posix())
for f in (s/'native08-preexecution-corrections').rglob('*'):
 if f.is_file():copy(f,'unused-native08-correction/'+f.relative_to(s/'native08-preexecution-corrections').as_posix())
for item in ('review_native_incident12.py','review_native_incident12_02.py','review_native_incident12_02.diff','repair_native_incident_reader12.py','integrate_native_incident12.py','prepare_native08_safety_correction.py','native_gui08_driver.py','build_native_gui08_launchers.py','native_media08_seed.py'):
 copy(s/item,'instruments/'+item)
copy(s/'native-client-incident12-review/reader-failure.json','reader-failure.json')
record=json.loads((p/'review/independent-review.json').read_text())
for row in record['source_bindings']:
 data=(r/row['path']).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
patch=subprocess.check_output(['git','diff','--binary','--',name],cwd=w)
assert patch==(p/'review/worker-original.patch').read_bytes()
result=subprocess.run(['git','apply','--3way',str(p/'review/worker-original.patch')],cwd=r,capture_output=True)
(p/'apply.stdout').write_bytes(result.stdout);(p/'apply.stderr').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
report=r/name;original=report.read_text(encoding='utf8')
report.write_text('> Retained static worker review. Read ASTRA-NATIVE-CLIENT-ISOLATION-REVIEW-2026-09-12.md first: it corrects cleanup scope/time, inherited-environment assumptions and prohibited probe suggestions. No live-index or port probe is authorized.\n\n'+'\n'.join(line.rstrip() for line in original.splitlines())+'\n',encoding='utf8',newline='\n')
docs=[name]
for old,new in [('ASTRA-NATIVE-CLIENT-ISOLATION-REVIEW-2026-09-12.next.md','ASTRA-NATIVE-CLIENT-ISOLATION-REVIEW-2026-09-12.md'),('NATIVE-CLIENT-ISOLATION-INCIDENT-2026-09-12.md','NATIVE-CLIENT-ISOLATION-INCIDENT-2026-09-12.md'),('NATIVE-CLIENT-ISOLATION-REVIEW-BRIEF-2026-09-12.md','NATIVE-CLIENT-ISOLATION-REVIEW-BRIEF-2026-09-12.md')]:
 shutil.copyfile(s/old,r/'docs/library'/new);docs.append('docs/library/'+new)
legacy=r/'docs/library/NATIVE-GUI-PACKAGE-07-OBSERVATION-2026-09-12.md'
prior=legacy.read_text(encoding='utf8')
legacy.write_text('> Correction, 2026-09-12: the Desktop isolation claim below is withdrawn. Packaged Claude discarded the proposed user-data override and launched ordinary configured connectors. Their earlier live-index/port effects are unknown; owned cleanup only proves termination. The Uoink dashboard observations remain distinct. Read [the incident](NATIVE-CLIENT-ISOLATION-INCIDENT-2026-09-12.md) and [Astra review](ASTRA-NATIVE-CLIENT-ISOLATION-REVIEW-2026-09-12.md). The original sealed observation is preserved unchanged.\n\n'+prior,encoding='utf8',newline='\n')
docs.append(legacy.relative_to(r).as_posix())
files={q.relative_to(p).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(p.rglob('*')) if q.is_file()}
(p/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
subprocess.run(['git','add','--',*docs],cwd=r,check=True)
paths=[(p/f).relative_to(r).as_posix() for f in [*files,'SHA256.json']]
subprocess.run(['git','add','-f','--',*paths],cwd=r,check=True)
for path in paths:assert subprocess.check_output(['git','show',':'+path],cwd=r)==(r/path).read_bytes()
subprocess.run(['git','diff','--cached','--check','--',*docs],cwd=r,check=True)
subprocess.run(['git','commit','-m','docs(library): withdraw Desktop isolation claim after Gemini review [46e8e6dc]'],cwd=r,check=True)
print(json.dumps({'payloads':len(files),'source_bindings':len(record['source_bindings']),'product_changed':False,'desktop_acceptance':False}))
