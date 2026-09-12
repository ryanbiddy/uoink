import hashlib,json,shutil,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'docs/library/proof/candidate-package-07-2026-09-12'
assert not (out/'SHA256.json').exists()
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf8',newline='\n')
scan=r/'_scratch/candidate-package07-scan-01'
obs=json.loads((scan/'scan.json').read_text(encoding='utf8'))
assert obs['exit']==0 and obs['package_sha256']==obs['package_sha256_after']
assert 'found no threats' in (scan/'scan.stdout').read_text(encoding='utf8').lower()
for name in ('scan.json','scan.stdout','scan.stderr'):shutil.copyfile(scan/name,out/name)
for name in ('scan_candidate_package.ps1','check_installed_package_inputs.py','package_decoder_probe.py','run_bound_c22.py','finalize_package07.py'):
 shutil.copyfile(r/'_scratch'/name,out/name)
shutil.copyfile(r/'_scratch/review_package07_notices.py',out/'review_package07_notices.py')
shutil.copyfile(r/'_scratch/compare_package07_repair_wheels.py',out/'compare_package07_repair_wheels.py')
shutil.copyfile(r/'_scratch/package07-wheel-bindings-01/result.json',out/'repair-wheel-bindings.json')
for source in (r/'_scratch/package07-notices-review-01').rglob('*'):
 if source.is_file():
  target=out/'notices-review'/source.relative_to(r/'_scratch/package07-notices-review-01')
  target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
shutil.copyfile(r/'THIRD-PARTY-NOTICES.md',out/'THIRD-PARTY-NOTICES.md')
versions={}
site=r/'installer/staging/python/Lib/site-packages'
for p in site.glob('*.dist-info/METADATA'):
 rows=p.read_text(encoding='utf8').splitlines()
 name=next(x[6:] for x in rows if x.startswith('Name: '))
 version=next(x[9:] for x in rows if x.startswith('Version: '))
 versions[name.lower()]={'version':version,'metadata_sha256':sha(p)}
for name,version in {'pillow':'12.3.0','mcp':'1.28.1','cryptography':'50.0.1','nltk':'3.10.3','lightning':'2.6.6','pytorch-lightning':'2.6.6','setuptools':'83.0.0'}.items():assert versions[name]['version']==version
assert len(versions)==140
save(out/'runtime-distributions.json',versions)
subprocess.run([sys.executable,'-I','-S','-B',str(r/'_scratch/review_package07_pins.py')],cwd=r,check=True)
for folder,label in [('package07-runtime-graph-01','runtime-graph'),('package07-preinstall-review-01','preinstall-pins')]:
 for source in (r/'_scratch'/folder).iterdir():
  if source.is_file():
   target=out/label/source.name;target.parent.mkdir(exist_ok=True)
   shutil.copyfile(source,target)
for name in ('verify_package07_graph.py','review_package07_pins.py'):
 shutil.copyfile(r/'_scratch'/name,out/name)
for name in ('package07-instrument-adaptations.json','package07-finalizer-review.json',
             'package07-finalizer-review.diff','finalize_package07_initial_draft.py'):
 shutil.copyfile(r/'_scratch'/name,out/name)
inventory=json.loads((out/'staged-inventory.json').read_text())['files']
private=r/'_scratch/package07-static-bin';private.mkdir(exist_ok=False)
bins=[]
for name in ('ffmpeg.exe','ffprobe.exe'):
 rel='bin/'+name
 expected=next(x for x in inventory if x['path']==rel)
 src=r/'installer/staging'/rel
 assert sha(src)==expected['sha256']
 target=private/name;shutil.copyfile(src,target)
 assert sha(target)==expected['sha256']
 bins.append({'path':str(target),'sha256':sha(target),'bytes':target.stat().st_size,'sealed_input':rel})
save(out/'final-native-media-environment.json',{'reason':'Retain the shipping LGPL CLI binaries separately from the private GPL final-test tools','files':bins})
save(out/'SHA256.json',{'algorithm':'sha256','files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.rglob('*')) if p.is_file()}})
print(json.dumps({'payloads':len(json.loads((out/'SHA256.json').read_text())['files']),'compiler_inputs':len(inventory),'installed_inputs':sum(x['install_role']=='installed' for x in inventory),'private_ffmpeg':bins,'scan':'zero exit, no threats reported, unsigned'},indent=2))
