"""Run the reviewed documentary ZIP builder once and retain its complete output."""
from pathlib import Path
import json,os,subprocess,sys
r=Path(__file__).resolve().parents[1]
expected=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
check=json.loads((r/'_scratch/package08-git-proof-check01.json').read_text())
assert check['source']==expected and check['result']=='PASS'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()==expected
assert not subprocess.check_output(['git','status','--porcelain'],cwd=r,text=True).strip()
env=os.environ.copy()
for key in list(env):
    if key.endswith(('API_KEY','_TOKEN','_SECRET')) or key.startswith('CLAUDE_CODE_USE_') or key in ('ANTHROPIC_BASE_URL','PYTHONPATH'):env.pop(key,None)
command=[sys.executable,'-I','-S','-B',str(r/'_scratch/build_release_bundle08.py'),
    '--source',expected,'--validation-source','b8e44fbc0a16950a22b29ead66951fcb80b2d6e8',
    '--validation-proof','ryan-final-partitioned-06-2026-09-12',
    '--out',str(r/'build/Uoink-Living-Library-3-8-0-Review-Kit-08-2026-09-12')]
with (r/'_scratch/review-bundle08-build.log').open('xb') as f:
    completed=subprocess.run(command,cwd=r,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900)
print(json.dumps({'exit_code':completed.returncode,'log':'_scratch/review-bundle08-build.log'}))
raise SystemExit(completed.returncode)
