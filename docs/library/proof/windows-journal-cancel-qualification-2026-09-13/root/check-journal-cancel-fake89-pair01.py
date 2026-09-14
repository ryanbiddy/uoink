import hashlib
import json
import os
from pathlib import Path
import sys
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
root = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
sources = [root / '_scratch/windows-journal-cancel-fake-proposal01', root / '_scratch/astra-journal-cancel-confirmation01']
actuals = ['JOURNAL-CANCEL-FAKE89-AUTHOR-ACTUAL01.json', 'JOURNAL-CANCEL-FAKE89-INDEPENDENT-ACTUAL01.json']
observations = []
case_sets = []
for source, actual_name in zip(sources, actuals):
    run = source / 'journal-cancel-fake01'
    raw = (run / 'stdout.json').read_bytes()
    result = json.loads(raw)
    receipt = json.loads((run / 'exit.json').read_bytes())
    native = json.loads((run / 'native-exit.json').read_bytes())
    actual = json.loads((root / '_scratch' / actual_name).read_bytes())
    expected = json.loads((source / 'EXPECTED-CASES.json').read_bytes())
    assert actual['exit_code'] == native['native_exit'] == receipt['native_exit'] == result['qualification_exit'] == 0
    assert result['count'] == result['passed'] == receipt['passed'] == len(result['cases']) == 89
    assert result['failed'] == result['skipped'] == receipt['failed'] == receipt['skipped'] == 0
    assert result['guard_valid'] is True and result['membership_valid'] is True
    assert len(result['guards']) == 10 and all(value is True for value in result['guards'].values())
    assert result['registry_trap_count'] == 25 and not result['guard_denials'] and not result['registry_denials']
    assert [row['id'] for row in result['cases']] == expected
    assert (run / 'stderr.log').read_bytes() == b''
    assert len(raw) == receipt['stdout_bytes']
    assert all(receipt[key] is True for key in ('valid', 'inputs_unchanged', 'membership_valid', 'guards_valid'))
    nested = [sub for row in result['cases'] for sub in row['subtests']]
    assert len(nested) == 86 and all(sub['passed'] is True for sub in nested)
    checks = json.loads((run / 'input-check.json').read_bytes())
    assert checks['inputs_unchanged'] is True and len(checks['inputs']) == 33 and len(checks['controls']) == 3
    for row in checks['inputs'] + checks['controls']:
        assert row['unchanged'] is True and row['original'] == row['copy']
        name = row['name']
        assert '/' not in name and '\\' not in name and name not in ('.', '..')
        for folder in (source, run):
            data = (folder / name).read_bytes()
            assert len(data) == row['original']['bytes'] and hashlib.sha256(data).hexdigest() == row['original']['sha256']
    case_sets.append(result['cases'])
    observations.append({'source': str(source), 'actual_tool_chunk': actual['chunk_id'], 'actual_outer_exit': 0, 'native_exit': 0,
                         'qualification_exit': 0, 'passed': 89, 'failed': 0, 'skipped': 0, 'passing_subtests': 86,
                         'valid_guards': 10, 'registry_traps': 25, 'stdout_bytes': len(raw),
                         'stdout_sha256': hashlib.sha256(raw).hexdigest(), 'case_elapsed_seconds': result['elapsed_seconds'],
                         'launcher_elapsed_seconds': receipt['elapsed_seconds'], 'source_and_control_bindings_unchanged': True})
assert case_sets[0] == case_sets[1]
out = {'scope': 'generated cancellation driver and observer only', 'exact_ordered_case_objects_match': True,
       'distinct_cases': 89, 'observations': observations, 'native_cancellation_executed': False, 'runtime_or_release_approved': False}
with (root / '_scratch/JOURNAL-CANCEL-FAKE89-PAIR-CHECK01.json').open('xb') as stream:
    stream.write((json.dumps(out, indent=2) + '\n').encode())
print(json.dumps(out))
