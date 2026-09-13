import json
from pathlib import Path
import subprocess

root = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker = Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\e922b3bf-3d8\gemini')
out = root / '_scratch/signing-review12-integration01'
out.mkdir(exist_ok=False)
path = 'docs/library/GEMINI-SIGNING-REVIEW-2026-09-12.md'
subprocess.run(['git','add','-N','-f','--',path],cwd=worker,check=True,capture_output=True)
patch = subprocess.run(['git','diff','--binary','--',path],cwd=worker,check=True,capture_output=True).stdout
(out / 'worker.patch').write_bytes(patch)
result = subprocess.run(['git','apply','--3way',str(out / 'worker.patch')],cwd=root,capture_output=True)
(out / 'apply.stdout').write_bytes(result.stdout)
(out / 'apply.stderr').write_bytes(result.stderr)
(out / 'result.json').write_text(json.dumps({'worker':str(worker),'scope':[path],'exit':result.returncode,'reproduction_module_integrated':False})+'\n',encoding='utf8')
print(json.dumps({'patch_bytes':len(patch),'exit':result.returncode}))
raise SystemExit(result.returncode)
