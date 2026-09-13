import hashlib,json,subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
r=Path(__file__).resolve().parents[1];w=Path('E:/AI/projects/uoink/worktrees/asset-guard-a')
paths=['whisper_runner.py','tests/test_whisper_cache_consent.py']
def git(root,*args):return subprocess.check_output(['git',*args],cwd=root)
assert git(r,'rev-parse','HEAD').decode().strip()=='0cedaa68fde378546d0389fcc2bf47099e84346e'
assert not git(r,'status','--porcelain')
assert hashlib.sha256((w/'whisper_runner.py').read_bytes()).hexdigest()=='6586d9f19fea0d20054d6e317b48b9914904e1126bbc7b788ba255633251996f'
assert hashlib.sha256((r/'whisper_runner.py').read_bytes()).hexdigest()=='71bd744fd4bc4f44243a2642a918958426dd21f0c06d341cc2c758cb27ce1ef5'
assert not git(w,'diff','HEAD','--diff-filter=CDMRTUXB','--','tests')
review=json.loads((r/'_scratch/agv01-launch/result.json').read_bytes())
assert review['verifier_exit']==0 and review['inputs_unchanged'] and review['guard_valid']
raw=json.loads((w/'_scratch/agv01/results.json').read_bytes());assert len(raw)==1 and raw[0]['exit']==0 and '--runxfail' in raw[0]['command']
xml=ET.fromstring((w/'_scratch/agv01/tests.xml').read_bytes());cases=xml.findall('.//testcase')
assert len(cases)==144 and all(not list(c) for c in cases)
assert xml.find('testsuite').attrib['tests']=='157'
out=r/'_scratch/asset-guard-a-integration01';out.mkdir(exist_ok=False)
patch=git(w,'diff','--binary','HEAD','--',*paths);(out/'worker.patch').write_bytes(patch)
for args,name in [(['apply','--check','--3way',str(out/'worker.patch')],'check'),(['apply','--3way',str(out/'worker.patch')],'apply')]:
    process=subprocess.run(['git',*args],cwd=r,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(out/(name+'.log')).write_bytes(process.stdout)
    assert process.returncode==0,process.stdout.decode(errors='replace')
for name in paths:assert git(r,'hash-object','--path='+name,name)==git(w,'hash-object','--path='+name,name)
assert not git(r,'diff','HEAD','--diff-filter=CDMRTUXB','--','tests')
guard=(w/'_scratch/agw_heavy_import_guard.py').read_bytes();target=r/'_scratch/agw_heavy_import_guard.py'
assert hashlib.sha256(guard).hexdigest()=='4a97b84d24edea4bca28958183ffc9dd442be0522f1b0a7b230e441630a879d9'
if target.exists():assert target.read_bytes()==guard
else:target.write_bytes(guard)
receipt={'paths':paths,'worker_source_sha256':hashlib.sha256((w/'whisper_runner.py').read_bytes()).hexdigest(),'patch_sha256':hashlib.sha256(patch).hexdigest(),'normalized_equality':True,'existing_test_changes':False,'worker_top_level_passes':144,'worker_passing_subtests':13,'junit_tests_attribute':157,'checkout_tests_run':False}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8');print(json.dumps(receipt))
