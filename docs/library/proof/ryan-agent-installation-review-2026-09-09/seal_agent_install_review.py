import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'docs/library/proof/ryan-agent-installation-review-2026-09-09';out.mkdir(exist_ok=False)
for label in ('agent-install-review-c1','agent-install-review-c2'):
 dest=out/label;dest.mkdir()
 for name in ('tests.log','tests.xml','results.json'):shutil.copyfile(r/'_scratch'/label/name,dest/name)
 for name in ('sitecustomize.py','ig_paths.py'):shutil.copyfile(r/'_scratch'/label/'guard'/name,dest/name)
for name in ('compile.json','iscc.log'):shutil.copyfile(r/'_scratch/agent-install-compile-01'/name,out/name)
for name in ('agent-install-review.patch','agent-install-review-attempt1.patch','compile_agent_install_review.py','integrator_verify.py','seal_agent_install_review.py'):
 shutil.copyfile(r/'_scratch'/name,out/name)
subprocess.run(['git','diff','HEAD','--binary','--full-index','--output='+str(out/'final-procedure.patch'),'--','installer/uoink.iss','scripts/install_receipt/agent_install.ps1'],cwd=r,check=True)
manifest={'algorithm':'sha256','files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8');print('Sealed',len(manifest['files']),'files')
