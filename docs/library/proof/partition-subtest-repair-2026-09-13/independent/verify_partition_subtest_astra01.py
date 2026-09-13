"""Independent synthetic qualification; never execute product/model suites."""
import hashlib, importlib.util, json, os, subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
assert sys.flags.isolated and sys.flags.no_site
out = root / '_scratch/astra-partition-subtest01-launch'
out.mkdir(exist_ok=False)
files = ['partition_receipt_plugin.py', 'partition_exit_contract.py',
         'mirror_state_receipt_plugin.py', 'agw_heavy_import_guard.py',
         'test_partition_exit_contract.py', 'test_mirror_state_receipt_plugin.py',
         'partition-subtest-repair01/test_subtest_contract.py', 'integrator_verify.py']
before = {name: hashlib.sha256((root/'_scratch'/name).read_bytes()).hexdigest() for name in files}
assert before['partition_receipt_plugin.py'] == 'e9eb059fd73488f561a60d8d14f63692b2e2c5d2885322ae39507c608b098f94'
assert before['partition_exit_contract.py'] == '6d835ee91985616f135984ff81032173c1917ca1dc71449db973e694f142f171'
assert before['mirror_state_receipt_plugin.py'] == '292f398ad5963e92c5dc622fd7a354e1839770b9f7edb2ecc9bb394423af0300'
env = os.environ.copy()
for key in list(env):
    upper = key.upper()
    if any(s in upper for s in ('API_KEY','AUTH_TOKEN','ACCESS_TOKEN','BASE_URL','OAUTH_TOKEN')) or upper.startswith(('ANTHROPIC_','OPENAI_','GOOGLE_API_','GEMINI_API_','XAI_','GROK_','CLAUDE_CODE_USE_')):
        env.pop(key, None)
env.update(IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db',
           PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
           IG_PARTITION_RECEIPT_PATH=str(out/'partition'),
           AGW_HEAVY_GUARD_RECEIPT=str(out/'heavy-guard.json'),
           SUBTEST_PROBE_RECEIPT=str(out/'probe'))
command = [sys.executable,'-B',str(root/'_scratch/integrator_verify.py'),
           '--root',str(root),'--label','astra-partition-subtest01',
           '_scratch/test_partition_exit_contract.py',
           '_scratch/partition-subtest-repair01/test_subtest_contract.py',
           '_scratch/test_mirror_state_receipt_plugin.py', '--runxfail',
           '-p','_scratch.partition_receipt_plugin','-p','_scratch.agw_heavy_import_guard']
def save(name, value):
    (out/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
save('plan.json', {'command':command,'input_sha256':before,'scope':'Synthetic instruments only; no product/model tests'})
with (out/'stdout.log').open('xb') as stdout, (out/'stderr.log').open('xb') as stderr:
    run = subprocess.run(command,cwd=root,env=env,stdout=stdout,stderr=stderr)
save('actual-exit.json',{'outer_verifier_exit':run.returncode})
after = {name: hashlib.sha256((root/'_scratch'/name).read_bytes()).hexdigest() for name in files}
save('after.json',after)
assert before == after
spec = importlib.util.spec_from_file_location('independent_contract',root/'_scratch/partition_exit_contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
raw = root/'_scratch/astra-partition-subtest01'
verifier = json.loads((raw/'results.json').read_bytes())
result = module.validate_partition(
    selected=json.loads((out/'partition/membership.json').read_bytes()),
    reports=[json.loads(line) for line in (out/'partition/reports.jsonl').read_text().splitlines()],
    session=json.loads((out/'partition/session.json').read_bytes()),
    verifier_results=verifier,outer_exit=run.returncode,junit_xml=(raw/'tests.xml').read_bytes())
guard = module.validate_heavy_guard(json.loads((out/'heavy-guard.json').read_bytes()),verifier[0]['exit'])
save('validated.json',result)
save('guard-validation.json',guard)
print(json.dumps({'case_count':result['case_count'],'counts':result['counts'],
                  'subtest_count':result['subtest_count'],'pytest_exit':result['pytest_exit'],
                  'outer_exit':run.returncode,'guard':guard,'unchanged_inputs':True}))
raise SystemExit(run.returncode)
