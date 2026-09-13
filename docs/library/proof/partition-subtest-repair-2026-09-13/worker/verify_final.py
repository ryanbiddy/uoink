"""Read retained synthetic receipts and instrument bytes; execute no tests."""
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = Path(__file__).resolve().parent
OUT = HERE / 'FINAL-VERIFICATION.json'
assert not OUT.exists()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


spec = importlib.util.spec_from_file_location('partition_exit_contract', ROOT/'_scratch/partition_exit_contract.py')
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)
results = {}
for mode in ('native02','native03','native04','unit01','unit03','pass01'):
    folder = HERE/(mode+'-partition')
    raw = ROOT/('_scratch/partition-subtest-'+mode)
    report_rows = lines(folder/'reports.jsonl')
    actual = helper.validate_partition(selected=read(folder/'membership.json'), reports=report_rows,
        session=read(folder/'session.json'), verifier_results=read(raw/'results.json'),
        outer_exit=read(HERE/(mode+'-launch/result.json'))['exit'], junit_xml=(raw/'tests.xml').read_bytes())
    results[mode] = {k:v for k,v in actual.items() if k not in ('cases','failed_phases','failed_subtests')}
    if (HERE/(mode+'-heavy.json')).exists():
        results[mode]['heavy_guard'] = helper.validate_heavy_guard(read(HERE/(mode+'-heavy.json')),actual['pytest_exit'])
    if (HERE/(mode+'-mirror.jsonl')).exists():
        observations = lines(HERE/(mode+'-mirror.jsonl'))
        needed = Counter((r['nodeid'],r['when'],r['outcome']) for r in report_rows if r['outcome']=='failed')
        captured = Counter((r['report']['nodeid'],r['report']['when'],r['report']['outcome']) for r in observations if r['event']=='mirror_state')
        assert captured == needed
        assert observations[0]['event']=='observer_started' and observations[-1]['event']=='observer_finished'
        assert all(r['event'] in ('observer_started','mirror_state','observer_finished') for r in observations)
        end = observations[-1]
        assert end['diagnostic_complete'] and end['observer_errors']==0
        assert end['pytest_exitstatus']==actual['pytest_exit'] and end['observation_attempts']==sum(needed.values())
        results[mode]['mirror_captures'] = sum(needed.values())
assert results['unit01']['counts']=={'passed':93}
assert results['unit03']['counts']=={'passed':116}
assert results['pass01']['counts']=={'passed':3} and results['pass01']['subtest_counts']=={'passed':4,'failed':0,'skipped':0}
assert results['native04']['counts']=={'passed':5,'failed':6,'error':3}
assert results['native04']['subtest_counts']=={'passed':8,'failed':8,'skipped':2}
assert results['native04']['raw_failed_report_count']==14 and results['native04']['reported_failed_report_count']==16
assert results['native04']['junit']['raw_suite_counts']=={'tests':34,'failures':13,'errors':3,'skipped':3}
assert results['native04']['junit']['case_elements']==16 and results['native04']['mirror_captures']==16
collection = read(HERE/'collect01-partition/session.json')
assert collection == {'exit':0,'tests_collected':13,'tests_failed':0,'reports':0}
assert read(ROOT/'_scratch/partition-subtest-collect01/results.json')[0]['exit']==0
assert read(HERE/'collect01-launch/result.json')['exit']==0
results['collect01']={'collection':collection,'heavy_guard':helper.validate_heavy_guard(read(HERE/'collect01-heavy.json'),0)}
partial_raw = read(ROOT/'_scratch/partition-subtest-unit02/results.json')[0]['exit']
assert partial_raw==1 and not (HERE/'unit02-partition/session.json').exists()
assert 'invalid destination reached open' in (ROOT/'_scratch/partition-subtest-unit02/tests.log').read_text()
results['unit02']={'result':'INCOMPLETE','raw_pytest_exit':partial_raw,'partition_session_receipt_present':False,'completed_case_counts':None,'reason':'Path.open replacement interrupted report callback; preserved instrument failure'}
original = HERE/'native01-original-partition'
try:
    helper.validate_partition(selected=read(original/'membership.json'),reports=lines(original/'reports.jsonl'),
        session=read(original/'session.json'),verifier_results=read(ROOT/'_scratch/partition-subtest-native01/results.json'),
        outer_exit=1,junit_xml=(ROOT/'_scratch/partition-subtest-native01/tests.xml').read_bytes())
except helper.PartitionContractError as error:
    results['native01_legacy_refusal']=str(error)
else:
    raise AssertionError('Untyped subtest evidence must not be silently reclassified')
for folder in sorted(HERE.glob('*-launch')):
    plan, after = read(folder/'plan.json'), read(folder/'result.json')
    assert plan['inputs']==after['after_inputs'], 'Inputs changed during '+folder.name
before = read(HERE/'before/SHA256.json')
for row in before['payloads']:
    assert sha(HERE/'before'/row['file'])==row['sha256']
old_proof = ROOT/'docs/library/proof/partition-exit-repair-2026-09-13'
assert sha(old_proof/'SHA256.json')==sha(HERE/'before/ORIGINAL-PARTITION-EXIT-REPAIR-SHA256.json')
for name,row in read(old_proof/'SHA256.json')['files'].items():
    target=(old_proof/name).resolve(strict=True)
    assert target.is_relative_to(old_proof.resolve()) and sha(target)==row['sha256']
assert sha(ROOT/'_scratch/test_partition_exit_contract.py')==sha(HERE/'before/instruments/test_partition_exit_contract.py')
assert sha(ROOT/'_scratch/test_mirror_state_receipt_plugin.py')==sha(HERE/'integration-before/test_mirror_state_receipt_plugin.py')
assert sha(ROOT/'_scratch/agw_heavy_import_guard.py')==sha(HERE/'integration-before/agw_heavy_import_guard.py')
instruments = ('partition_receipt_plugin.py','partition_exit_contract.py','mirror_state_receipt_plugin.py','run_partitioned_mirror_tree09.py','seal_partitioned_mirror_tree09.py','agw_heavy_import_guard.py')
for name in instruments:
    ast.parse((ROOT/'_scratch'/name).read_text(encoding='utf-8'))
results['final_instrument_sha256']={name:sha(ROOT/'_scratch'/name) for name in instruments}
results['before_payloads_verified']=before['payload_count']
results['prior_partition_exit_seal_payloads_verified']=len(read(old_proof/'SHA256.json')['files'])
results['unchanged_legacy_unit_cases']=53
results['unchanged_mirror_unit_cases']=15
results['verification_result']='PASS'
results['scope']='Synthetic receipt interpretation and passive instrument checks only; no product/full-tree/model execution'
OUT.write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in results.items() if k not in ('native02','native03','unit01','unit03')},indent=2))
