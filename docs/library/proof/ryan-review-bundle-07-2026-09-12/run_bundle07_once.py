"""Run the reviewed documentary ZIP builder once and retain its complete output."""
from pathlib import Path
import json,os,subprocess,sys
r=Path(__file__).resolve().parents[1]
expected='81e4495fdcf5d6365587e407e7e61c68440b9e01'
check=json.loads((r/'_scratch/package07-git-proof-check01.json').read_text())
assert check['source']==expected and check['result']=='PASS'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()==expected
assert not subprocess.check_output(['git','status','--porcelain'],cwd=r,text=True).strip()
env=os.environ.copy()
for key in list(env):
    if key.endswith(('API_KEY','_TOKEN','_SECRET')) or key.startswith('CLAUDE_CODE_USE_') or key in ('ANTHROPIC_BASE_URL','PYTHONPATH'):env.pop(key,None)
command=[sys.executable,'-I','-S','-B',str(r/'_scratch/build_release_bundle07.py'),
    '--source',expected,'--validation-source','6a89189d601467eeff33d304c2c9b69cdd2e6d0b',
    '--validation-proof','ryan-final-partitioned-04-2026-09-12',
    '--out',str(r/'build/Uoink-Living-Library-3-8-0-Review-Kit-07-2026-09-12')]
with (r/'_scratch/review-bundle07-build.log').open('xb') as f:
    completed=subprocess.run(command,cwd=r,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900)
print(json.dumps({'exit_code':completed.returncode,'log':'_scratch/review-bundle07-build.log'}))
raise SystemExit(completed.returncode)
