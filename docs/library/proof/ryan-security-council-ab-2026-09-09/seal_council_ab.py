import hashlib,json,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'docs/library/proof/ryan-security-council-ab-2026-09-09';out.mkdir(exist_ok=False)
workers={'a':Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\b5c7290c-a7c\gemini'),'b':Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\8e109b99-190\gemini')}
for role in ('a','b'):
 for kind,base in (('w',workers[role]),('c',r)):
  label=f'council-{role}-{kind}1';dest=out/label;dest.mkdir()
  for name in ('tests.log','tests.xml','results.json'):shutil.copyfile(base/'_scratch'/label/name,dest/name)
  for name in ('sitecustomize.py','ig_paths.py'):shutil.copyfile(base/'_scratch'/label/'guard'/name,dest/name)
 shutil.copyfile(r/'_scratch'/f'council-{role}.patch',out/f'council-{role}.patch')
for folder,names in [('installer-security-01',['preflight.json','scan.log','scan.json']),('installer-osv-01',['request.json','response-1.json','findings.json','summary.json'])]:
 dest=out/folder;dest.mkdir()
 for name in names:shutil.copyfile(r/'_scratch'/folder/name,dest/name)
for name in ('integrator_verify.py','audit_installer_osv.py','seal_council_ab.py'):shutil.copyfile(r/'_scratch'/name,out/name)
manifest={'algorithm':'sha256','files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8');print('Sealed',len(manifest['files']),'files')
