"""Transport accepted documentary evidence while retaining rejected worker artifacts."""
import hashlib,json,shutil,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
worker=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\0ee38a14-5a9\gemini')
proof=repo/'docs/library/proof/security12-astra-review-2026-09-12';proof.mkdir(exist_ok=False)
def git(args,cwd=worker):return subprocess.run(['git',*args],cwd=cwd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
attr='docs/library/proof/security-repair-gemini-2026-09-12/** -text\n'
with (worker/'.gitattributes').open('a',encoding='utf8') as f:f.write('\n'+attr)
git(['add','-N','--','.gitattributes','docs/library/SECURITY-REPAIR-WORKER-2026-09-12.md','docs/library/proof/security-repair-gemini-2026-09-12','tests/security/test_dependency_repair_constraints.py'])
(proof/'worker-full-with-transport-attributes.patch').write_bytes(git(['diff','--binary']))
(proof/'accepted-documentary.patch').write_bytes(git(['diff','--binary','--','.gitattributes','docs/library/SECURITY-REPAIR-WORKER-2026-09-12.md','docs/library/proof/security-repair-gemini-2026-09-12']))
shutil.copyfile(worker/'tests/security/test_dependency_repair_constraints.py',proof/'rejected-new-tests.py.txt')
shutil.copyfile(worker/'docs/library/SECURITY-REPAIR-WORKER-2026-09-12.md',proof/'worker-report-original.md.txt')
for name in ('review_security12.py','review_security12_02.py','integrate_security12.py'):
 shutil.copyfile(repo/'_scratch'/name,proof/name)
for name in ('security12-review01','security12-review02'):
 for p in (repo/'_scratch'/name).glob('*.json'):shutil.copyfile(p,proof/(name+'-'+p.name))
attempts=[]
for d in sorted((worker/'_scratch').iterdir()):
 if d.is_dir() and (d.name.startswith('gemini-suites-') or d.name=='astra-security12-worker01'):
  files=[]
  for p in sorted(d.iterdir()):
   if p.is_file() and p.suffix in ('.json','.log'):
    target=proof/(d.name+'-'+p.name);shutil.copyfile(p,target);files.append(target.name)
  attempts.append({'label':d.name,'retained_files':files})
(proof/'attempt-inventory.json').write_text(json.dumps(attempts,indent=2)+'\n',encoding='utf8')
result=subprocess.run(['git','apply','--3way',str(proof/'accepted-documentary.patch')],cwd=repo,capture_output=True)
(proof/'apply.stdout').write_bytes(result.stdout);(proof/'apply.stderr').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
print('Documentary patch applied; no new worker tests entered the active test tree.')
