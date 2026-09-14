"""Read exact completed text receipts and extend the fixed archival input list."""
from pathlib import Path
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch')
OUT = ROOT / 'worker-bootstrap-owner-final-list01'
PREP = ROOT / 'worker-bootstrap-owner-archive-plan01/PREPARATION-COPY-LIST.json'
PREP_SHA = '1d3c4c88ff70de1749f5762e7512e2fde6c4d46d2e92a37ee9528e7b33ff9b0b'
RUNS = ('worker-bootstrap-owner-instrument01', 'astra-worker-bootstrap-owner-confirmation01')
ACTUALS = ('WORKER-BOOTSTRAP01-ADMISSION-ACTUAL.json', 'WORKER-BOOTSTRAP01-AUTHOR-INITIAL-ACTUAL.json',
           'WORKER-BOOTSTRAP01-AUTHOR-FINAL-ACTUAL.json', 'WORKER-BOOTSTRAP01-INDEPENDENT-ADMISSION-ACTUAL.json',
           'WORKER-BOOTSTRAP01-INDEPENDENT-INITIAL-ACTUAL.json', 'WORKER-BOOTSTRAP01-INDEPENDENT-FINAL-ACTUAL.json')
GUARDS = ('metadata_traps_installed', 'content_reads_closed', 'baseline_winreg_identity_unchanged',
          'registry_namespace_unchanged', 'registry_traps_installed', 'captures_installed', 'capture_valid',
          'methods_unchanged', 'closed_entries_unchanged', 'owner_binding_valid', 'guard_valid')

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    with path.open('xb') as stream: stream.write((json.dumps(value, indent=2) + '\n').encode())

assert digest(PREP) == PREP_SHA
prior = read(PREP)
assert prior['file_count'] == len(prior['files']) == 75
paths = {}
for row in prior['files']:
    path = Path(row['source'])
    assert path == ROOT / row['relative_path']
    raw = path.read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    paths[row['relative_path']] = path

comparisons = []
results = []
for run_name in RUNS:
    base = ROOT / run_name
    run = base / 'runs/wbo01'
    admission = read(base / 'ROOT-ADMISSION.json')
    assert admission['root_reviewed'] is True and len(admission['input_sha256']) == 19
    assert digest(run / 'ROOT-ADMISSION.json') == digest(base / 'ROOT-ADMISSION.json')
    expected = read(run / 'EXPECTED-CASES.json')['ordered_cases']
    assert len(expected) == 17 and expected == admission['expected_cases']
    required = set(admission['input_sha256']) | {'ROOT-ADMISSION.json', 'plan.json', 'native-exit.json',
                                                'stdout.json', 'stderr.log', 'after.json', 'exit.json'}
    assert len(required) == 26
    assert {path.name for path in run.iterdir()} == required
    result, native, outcome = read(run / 'stdout.json'), read(run / 'native-exit.json'), read(run / 'exit.json')
    assert result['schema'] == 'uoink.worker-bootstrap-synthetic.v1'
    assert (result['count'], result['passed'], result['failed'], result['skipped']) == (17, 17, 0, 0)
    assert result['cases'] == [{'name': name, 'passed': True} for name in expected]
    assert result['expected_cases'] == expected and all(result[name] is True for name in GUARDS)
    assert result['metadata_trap_count'] == 12 and result['registry_trap_count'] == 25
    assert result['guard_denials'] == result['registry_denials'] == result['heavy_roots_loaded'] == []
    assert native['child_returned'] is True and native['native_exit'] == outcome['native_exit'] == outcome['outer_exit'] == 0
    assert result['native_exit'] == 0 and outcome['receipt_valid'] is True and outcome['inputs_unchanged'] is True
    assert outcome['stdout_bytes'] == len((run / 'stdout.json').read_bytes()) == 7211
    assert outcome['stderr_bytes'] == len((run / 'stderr.log').read_bytes()) == 0
    after = read(run / 'after.json')
    plan = read(run / 'plan.json')
    assert len(after) == 20 and len(plan['inputs']) == 19
    assert {row['name'] for row in after} == set(admission['input_sha256']) | {'ROOT-ADMISSION.json'}
    for row in after:
        assert row['before_sha256'] == row['copy_after_sha256'] == row['source_after_sha256']
        assert digest(run / row['name']) == row['before_sha256']
    for row in plan['inputs']:
        source = Path(row['source'])
        assert source.parent in (ROOT / 'worker-runtime-owner-proposal02', ROOT / 'worker-bootstrap-owner-migration01', base)
        assert row['sha256'] == digest(source) == digest(run / row['name']) == admission['input_sha256'][row['name']]
    assert len(result['input_sha256']) == 17
    for name, value in result['input_sha256'].items(): assert digest(run / name) == value
    for name in sorted(required): paths[(run / name).relative_to(ROOT).as_posix()] = run / name
    paths[(base / 'ROOT-ADMISSION.json').relative_to(ROOT).as_posix()] = base / 'ROOT-ADMISSION.json'
    results.append(result)
    comparisons.append({'root': run_name, 'cases': 17, 'passed': 17, 'failed': 0, 'skipped': 0,
        'elapsed_seconds': result['elapsed_seconds'], 'native_exit': 0, 'outer_exit': 0,
        'stdout_bytes': 7211, 'stderr_bytes': 0, 'guard_valid': True, 'inputs_unchanged': True,
        'admission_sha256': digest(base / 'ROOT-ADMISSION.json')})
assert results[0]['cases'] == results[1]['cases']
assert results[0]['input_sha256'] == results[1]['input_sha256']
for name in ACTUALS:
    value = read(ROOT / name)
    if 'INITIAL' in name:
        assert 'exit_code' not in value and type(value['session_id']) is int
    else:
        assert value['exit_code'] == 0
    paths[name] = ROOT / name
for name in ('WORKER-BOOTSTRAP01-ROOT-REVIEW.md',
             'worker-bootstrap-owner-archive-plan01/PREPARATION-COPY-LIST.json',
             'worker-bootstrap-owner-archive-plan01/ACTUAL-LIST-PREPARATION-TOOL.json'):
    paths[name] = ROOT / name
write(OUT / 'RECEIPT-COMPARISON.json', {'candidate_execution': False, 'distinct_cases': 17,
    'observations': comparisons, 'exact_ordered_case_objects_equal': True, 'all_seventeen_child_hashes_equal': True,
    'preparation75_verified_unchanged': True})
(OUT / '.gitattributes').write_bytes(b'* -text\n')
for name in ('VERDICT.md', 'write_final_list.py', 'RECEIPT-COMPARISON.json', '.gitattributes'):
    paths[(OUT / name).relative_to(ROOT).as_posix()] = OUT / name
rows = []
for name, path in sorted(paths.items()):
    raw = path.read_bytes()
    rows.append({'source': str(path), 'relative_path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
record = {'schema': 'uoink.worker-bootstrap-final-fixed-copy-list.v1', 'files': rows,
          'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows),
          'preparation_manifest_sha256': PREP_SHA, 'distinct_cases': 17, 'successful_observations': 2,
          'candidate_execution': False, 'run_trees_complete': True}
write(OUT / 'FIXED-COPY-LIST.json', record)
print(json.dumps({'files': record['file_count'], 'bytes': record['bytes'],
                 'sha256': digest(OUT / 'FIXED-COPY-LIST.json'),
                 'verdict_sha256': digest(OUT / 'VERDICT.md'),
                 'receipt_comparison_sha256': digest(OUT / 'RECEIPT-COMPARISON.json')}))
