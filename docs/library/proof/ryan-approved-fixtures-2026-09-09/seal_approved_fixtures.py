import hashlib,json,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'docs/library/proof/ryan-approved-fixtures-2026-09-09'
out.mkdir(exist_ok=False)
for label in ('approved-mirror-01','approved-read-01'):
 d=out/label;d.mkdir()
 for name in ('tests.log','tests.xml','results.json'):
  shutil.copyfile(r/'_scratch'/label/name,d/name)
 for name in ('sitecustomize.py','ig_paths.py'):
  shutil.copyfile(r/'_scratch'/label/'guard'/name,d/name)
for name in ('assertions.json','applied.patch'):
 shutil.copyfile(r/'_scratch/approved-fixtures-audit-01'/name,out/name)
shutil.copyfile(r/'_scratch/integrator_verify.py',out/'integrator_verify.py')
shutil.copyfile(__file__,out/'seal_approved_fixtures.py')
manifest={'algorithm':'sha256','files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print('Sealed',len(manifest['files']),'files')
