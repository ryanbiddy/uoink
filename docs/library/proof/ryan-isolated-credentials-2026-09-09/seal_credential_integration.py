import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\4c02e121-2b3\gemini')
out=r/'docs/library/proof/ryan-isolated-credentials-2026-09-09';out.mkdir(exist_ok=False)
labels=['iso-c01','iso-cred-verified-01','isolated-cred-companions-01','isolated-cred-corrected-01','isolated-cred-negative-01','test-av5m3-check','test-doc-contracts','test-iso-av5m3-pair','test-iso-quad','test-pair-cred-av5m3','test-trio-check','credential-w1','credential-w2']
for base,label in [(w,x) for x in labels]+[(r,'credential-c2')]:
 dest=out/label;dest.mkdir()
 for name in ('tests.log','tests.xml','results.json'):shutil.copyfile(base/'_scratch'/label/name,dest/name)
 for name in ('sitecustomize.py','ig_paths.py'):shutil.copyfile(base/'_scratch'/label/'guard'/name,dest/name)
for name in ('credential-worker-original.patch','credential-integrated.patch','integrator_verify.py','seal_credential_integration.py'):
 shutil.copyfile(r/'_scratch'/name,out/name)
manifest={'algorithm':'sha256','files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print('Sealed',len(manifest['files']),'files')
