import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
base=r/'docs/library/proof/astra-authority-c1008-review-2026-09-13'
seal=json.loads((base/'SHA256.json').read_text())
for name,info in seal['files'].items():
    p=base/name
    assert hashlib.sha256(p.read_bytes()).hexdigest()==info['sha256'],str(p)
    assert hashlib.sha256(subprocess.check_output(['git','show',':'+p.relative_to(r).as_posix()],cwd=r)).hexdigest()==info['sha256'],str(p)
print(json.dumps({'git_and_disk_verified':len(seal['files']),'product_accepted':False}))
