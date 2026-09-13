import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'docs/library/proof/astra-mirror-authority-2026-09-13';out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
for n in ['tests.xml','tests.log','results.json']:
    shutil.copyfile(r/'_scratch/astra-gemini-authority-checkout01'/n,out/n)
for n in ['gemini-mirror-authority-reviewed.diff','seal_gemini_authority_checkout.py']:
    shutil.copyfile(r/'_scratch'/n,out/n)
for n in ['ASTRA-MIRROR-PROCESS-AUTHORITY-VERDICT-2026-09-13.md','MIRROR-PROCESS-AUTHORITY-REPAIR-BRIEF-2026-09-13.md']:
    shutil.copyfile(r/'docs/library'/n,out/n)
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
for folder in ['gemini-mirror-authority-2026-09-13','mirror-owner-admission01-2026-09-13']:
    parent=r/'docs/library/proof'/folder
    seal=json.loads((parent/'SHA256.json').read_text())
    for rel,expected in seal['files'].items():
        p=parent/rel
        assert hashlib.sha256(p.read_bytes()).hexdigest()==expected['sha256'],str(p)
        blob=subprocess.check_output(['git','show',':'+p.relative_to(r).as_posix()],cwd=r)
        assert hashlib.sha256(blob).hexdigest()==expected['sha256'],str(p)
print(json.dumps({'new_payloads':len(files),'existing_git_and_disk_seals_verified':40}))
