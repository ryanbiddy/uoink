import json
from pathlib import Path
import subprocess
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\ecbf6acd-847\gemini')
out=root / '_scratch/nltk12-integration01'
out.mkdir(exist_ok=False)
paths=['scripts/prepare_nltk_pathsec_backport.py','tests/test_nltk_pathsec_backport.py',
 'tests/test_nltk_preparation_boundaries.py','vendor/nltk-pathsec',
 'docs/library/NLTK-PATHSEC-BACKPORT-2026-09-12.md',
 'docs/library/NLTK-PATHSEC-PREPARATION-REVIEW-2026-09-12.md']
subprocess.run(['git','add','-N','-f','--',*paths],cwd=worker,check=True,capture_output=True)
patch=subprocess.check_output(['git','diff','--binary','--',*paths],cwd=worker)
(out / 'worker.patch').write_bytes(patch)
applied=subprocess.run(['git','apply','--3way',str(out / 'worker.patch')],cwd=root,capture_output=True)
(out / 'apply.stdout').write_bytes(applied.stdout)
(out / 'apply.stderr').write_bytes(applied.stderr)
(out / 'result.json').write_text(json.dumps({'worker':str(worker),'scope':paths,'exit':applied.returncode})+'\n',encoding='utf8')
print(json.dumps({'patch_bytes':len(patch),'exit':applied.returncode}))
raise SystemExit(applied.returncode)
