"""Preserve limited qualification, actual dependency resolution and native failure."""
import hashlib,json,re,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\c7a2ded2-a2b\gemini')
out=r/'docs/library/proof/ryan-python313-qualification-2026-09-09';out.mkdir(exist_ok=False)
def cp(source,name):
 target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for name in ('breakdown_summary.txt','pip_dryrun_summary.json','pypi_qualification_summary.json','qualification_report.json','requirements_140.txt'):
 cp(w/'_scratch'/name,'worker/'+name)
for base,labels,section in ((w,['astra-python313-w1'],'worker'),(r,['astra-python313-c1','astra-python313-c2'],'checkout')):
 for label in labels:
  for name in ('tests.log','tests.xml','results.json','guard/sitecustomize.py','guard/ig_paths.py'):cp(base/'_scratch'/label/name,f'{section}/{label}/{name}')
for dirname in ('native-binary-candidates-03','native-scan-python-03','python313-runtime-probe-01'):
 for q in (r/'_scratch'/dirname).iterdir():
  if q.is_file() and q.suffix!='.zip':cp(q,'native/'+dirname+'/'+q.name)
for q in (r/'_scratch/python313-graph-01').iterdir():
 if q.is_file():cp(q,'actual-graph/'+q.name)
for name in ('PYTHON-313-QUALIFICATION-BRIEF-2026-09-09.md','PYTHON-313-UPGRADE-BRIEF-2026-09-09.md','PYTHON-INTEGRATION-CONFLICT-REPAIR-2026-09-09.md','TORCHCODEC-DLL-REPAIR-BRIEF-2026-09-09.md','gemini-python313-qualification-2026-09-09.patch','astra-python313-upgrade-2026-09-09.patch','fetch_python313_candidate.py','qualify_python313_graph.py','inspect_python313_resolution.py','install_python313_qualification.py','python313_runtime_probe.py','run_python313_probe.ps1'):
 cp(r/'_scratch'/name,'instruments/'+name)
if (r/'_scratch/python313-conflicted-application.patch').is_file():cp(r/'_scratch/python313-conflicted-application.patch','instruments/python313-conflicted-application.patch')
cp(Path(__file__),Path(__file__).name)
norm=lambda name:re.sub(r'[-_.]+','-',name).lower()
installed={norm(k):v for k,v in json.loads((r/'_scratch/python313-runtime-probe-01/inventory.json').read_text(encoding='utf8')).items()}
tools={k:installed.pop(k) for k in ('pip','setuptools','wheel')}
locked={norm(line.split('==')[0]):line.split('==')[1] for line in (r/'requirements-installer-lock.txt').read_text(encoding='utf8').splitlines() if line and not line.startswith('#')}
assert installed==locked and len(installed)==139
summary={'source_before_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),'target_python':'3.13.15','exact_runtime_packages':139,'runtime_inventory_equals_proposed_lock':True,'separate_build_tools':tools,'worker_build_suites':{'passed':36,'seconds':2.43},'premature_conflicted_checkout_suites':{'passed':36,'seconds':1.97,'accepted_for_build':False},'resolved_checkout_suites':{'passed':36,'seconds':1.95},'native_probe':{'passed':15,'failed':1,'failure':'torchcodec native shared library dependency','guard_refusals':1},'scope':'Dependency graph and build configuration accepted; native failure remains repair work. No model/inference/diarization/Setup. No existing acceptance test changed.'}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
files={q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(out.rglob('*')) if q.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8');print(json.dumps({'files':len(files),'summary':summary},indent=2))
