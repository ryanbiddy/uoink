import json,subprocess
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
tree=root / '_scratch/wheel-integrator13'
out=root / '_scratch/nltk-binding13-integration01';out.mkdir(exist_ok=False)
paths=['build.ps1','requirements-installer-lock.txt','THIRD-PARTY-NOTICES.md','scripts/gen_third_party_notices.py',
       'docs/build-installer.md','docs/security.md']
patch=subprocess.check_output(['git','diff','--binary','--',*paths],cwd=tree)
(out/'worker.patch').write_bytes(patch)
applied=subprocess.run(['git','apply','--3way',str(out/'worker.patch')],cwd=root,capture_output=True)
(out/'apply.stdout').write_bytes(applied.stdout);(out/'apply.stderr').write_bytes(applied.stderr)
(out/'result.json').write_text(json.dumps({'scope':paths,'worktree':str(tree),'exit':applied.returncode})+'\n',encoding='utf8')
print(json.dumps({'patch_bytes':len(patch),'exit':applied.returncode}))
raise SystemExit(applied.returncode)
