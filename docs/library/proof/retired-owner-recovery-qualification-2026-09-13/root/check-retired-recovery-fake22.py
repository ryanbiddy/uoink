"""Read only fixed generated qualification text; never import candidate modules."""
import hashlib
import json
import os
from pathlib import Path

assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
ROOTS = [ROOT / '_scratch/windows-retired-owner-recovery-proposal01', ROOT / '_scratch/astra-retired-recovery-confirmation01']
MAP_SHA = 'f7c3b964ed77a681ed71d9b03fee934cf402721bc232d869e5ee42c9f564e3a1'
ADMISSION_SHA = '4571e6fbfaf41fd9dc4bf9ebe90166ff511888203e91534d6b4182c92628e526'

def raw(path):
    with path.open('rb') as stream:
        data = stream.read(1048577)
    assert len(data) <= 1048576
    data.decode('utf-8-sig')
    return data

def digest(data):
    return hashlib.sha256(data).hexdigest()

def document(path):
    return json.loads(raw(path))

results = []
case_objects = []
for source in ROOTS:
    run = source / 'retired-recovery-fake01'
    pins_raw = raw(source / 'PINS.json')
    assert digest(pins_raw) == MAP_SHA
    pins = json.loads(pins_raw)['files']
    assert len(pins) == len({r['path'] for r in pins}) == 26
    expected = document(source / 'EXPECTED-CASES.json')
    assert len(expected) == len(set(expected)) == 22
    assert sum(i.startswith('test_retired_owner_recovery.') for i in expected) == 10
    for row in pins:
        assert '/' not in row['path'] and '\\' not in row['path']
        for base in (source, run):
            data = raw(base / row['path'])
            assert len(data) == row['bytes'] and digest(data) == row['sha256']
    for base in (source, run):
        assert digest(raw(base / 'PINS.json')) == MAP_SHA
        assert digest(raw(base / 'ROOT-ADMISSION.json')) == ADMISSION_SHA
    check = document(run / 'input-check.json')
    assert check['inputs_unchanged'] is True
    assert len(check['inputs']) == 26 and len(check['controls']) == 3
    assert all(r['unchanged'] is True and r['original'] == r['copy'] for r in check['inputs'] + check['controls'])
    exit_doc = document(run / 'exit.json')
    native = document(run / 'native-exit.json')
    assert type(native['native_exit']) is int and native['native_exit'] == 0
    assert all(exit_doc[k] is True for k in ('valid', 'inputs_unchanged', 'membership_valid', 'guards_valid'))
    assert exit_doc['native_exit'] == exit_doc['qualification_exit'] == 0
    receipt_raw = raw(run / 'stdout.json')
    receipt = json.loads(receipt_raw)
    assert raw(run / 'stderr.log') == b''
    assert receipt['count'] == receipt['passed'] == 22
    assert receipt['failed'] == receipt['skipped'] == receipt['qualification_exit'] == 0
    assert receipt['guard_valid'] is True and receipt['membership_valid'] is True
    assert len(receipt['guards']) == 10 and all(v is True for v in receipt['guards'].values())
    assert receipt['guard_denials'] == receipt['registry_denials'] == receipt['heavy_roots_loaded'] == []
    assert receipt['metadata_trap_count'] == 12 and receipt['registry_trap_count'] == 25
    assert receipt['expected_cases'] == expected == [c['id'] for c in receipt['cases']]
    child_inputs = {r['path']:r['sha256'] for r in pins if r['path'].endswith('.py') or r['path'] == 'EXPECTED-CASES.json'}
    assert len(child_inputs) == 23 and receipt['input_sha256'] == child_inputs
    subtests = [s for c in receipt['cases'] for s in c['subtests']]
    assert all(c['passed'] is True and c['skipped'] is False and c['errors'] == [] for c in receipt['cases'])
    assert all(s['passed'] is True for s in subtests)
    case_objects.append(receipt['cases'])
    results.append({'root':str(source), 'passed':22, 'failed':0, 'skipped':0, 'passing_subtests':len(subtests), 'guards':10, 'metadata_traps':12, 'registry_traps':25, 'fixed_inputs':26, 'controls':3, 'child_inputs':23, 'stdout_bytes':len(receipt_raw), 'stdout_sha256':digest(receipt_raw), 'native_exit':native['native_exit']})
assert case_objects[0] == case_objects[1]
print(json.dumps({'runs':results, 'case_objects_identical':True, 'historical_cases_per_run':12, 'new_cases_per_run':10, 'candidate_executions_by_this_checker':0, 'native_recovery_qualified':False}, indent=2))
