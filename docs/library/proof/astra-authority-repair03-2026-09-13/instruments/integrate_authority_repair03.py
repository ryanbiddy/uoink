import hashlib,json,subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\a5e7ba0d-26f\grok')
paths=['library_mirror.py','tests/test_library_mirror_process_authority.py','tests/test_mirror_process_identity_boundaries.py','tests/test_mirror_process_handle_lifetime.py','tests/test_mirror_authority_review02.py','tests/test_mirror_stable_handle_discovery.py','tests/_mirror_stable_native_fixture.py']
def git(root,*args):return subprocess.check_output(['git',*args],cwd=root)
assert git(r,'rev-parse','HEAD').decode().strip()=='099a72408f63e6cdb227322e137da428f6c3a1d7'
assert not git(r,'status','--porcelain')
assert hashlib.sha256((w/'library_mirror.py').read_bytes()).hexdigest()=='67432bf13905b8c28c2048ce51bbebd74490d463f8b1a4e08fdd3ce4e53a0a23'
assert not git(w,'diff','HEAD','--diff-filter=CDMRTUXB','--','tests')
result=json.loads((w/'_scratch/a3w02/results.json').read_bytes())
assert len(result)==1 and result[0]['exit']==0
suite=ET.fromstring((w/'_scratch/a3w02/tests.xml').read_bytes())
cases=suite.findall('.//testcase')
assert len(cases)==233 and all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases)
out=r/'_scratch/authority-repair03-integration01';out.mkdir(exist_ok=False)
patch=git(w,'diff','--binary','HEAD','--',*paths)
assert set(git(w,'diff','--name-only','HEAD','--',*paths).decode().splitlines())==set(paths)
patchpath=out/'worker.patch';patchpath.write_bytes(patch)
before=git(r,'rev-parse','HEAD').decode().strip()
for args,name in [(['apply','--check','--3way',str(patchpath)],'check'),(['apply','--3way',str(patchpath)],'apply')]:
    process=subprocess.run(['git',*args],cwd=r,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (out/(name+'.log')).write_bytes(process.stdout)
    assert process.returncode==0,process.stdout.decode(errors='replace')
for name in paths:
    assert git(w,'hash-object','--path='+name,name)==git(r,'hash-object','--path='+name,name),name
assert not git(r,'diff','HEAD','--diff-filter=CDMRTUXB','--','tests')
record={'checkout_before':before,'worker_base':git(w,'rev-parse','HEAD').decode().strip(),'worker_source_sha256':hashlib.sha256((w/'library_mirror.py').read_bytes()).hexdigest(),'patch_sha256':hashlib.sha256(patch).hexdigest(),'paths':paths,'worker_passed':233,'existing_test_changes':False,'normalized_source_test_equality':True,'checkout_tests_run':False}
(out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record))
