import hashlib,json,shutil,xml.etree.ElementTree as ET
from pathlib import Path
r=Path(__file__).resolve().parents[1];w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\4d4cc9ce-a39\gemini')
out=r/'docs/library/proof/ryan-dependency-security-2026-09-09';out.mkdir(exist_ok=False)
for base,label in [(w,x) for x in ('baseline-check','baseline-check-ig2','dep-repair-g1','dep-repair-final','dependency-w1')]+[(r,'dependency-c1')]:
 dest=out/label;dest.mkdir()
 for rel in ('tests.log','tests.xml','results.json','guard/sitecustomize.py','guard/ig_paths.py'):
  src=base/'_scratch'/label/rel
  if src.is_file():
   target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
for folder in ('dependency-resolve-01','dependency-resolve-02','dependency-resolve-03','dependency-metadata-01','installer-osv-02'):
 dest=out/folder;dest.mkdir()
 for src in (r/'_scratch'/folder).iterdir():
  if src.is_file() and src.suffix in ('.json','.txt','.log'):shutil.copyfile(src,dest/src.name)
for name in ('dependency-integrated.patch','advisory-triage.patch','audit_installer_osv_02.py','verify_dependency_metadata.py','prepare_dependency_resolution.py','integrator_verify.py','seal_dependency_integration.py'):
 shutil.copyfile(r/'_scratch'/name,out/name)
manifest={'algorithm':'sha256','files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print('Sealed',len(manifest['files']),'payloads')
