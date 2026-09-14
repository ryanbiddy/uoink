"""Data-only verification of fixed completed receipts; no candidate imports or runs."""
from pathlib import Path
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
SCRATCH = ROOT / '_scratch'
OUT = SCRATCH / 'windows-reservation02-final-list01'
AUTHOR = SCRATCH / 'windows-reservation-implementation-proposal02'
INDEPENDENT = SCRATCH / 'astra-windows-reservation-confirmation02'
OLD = ROOT / 'docs/library/proof/windows-reservation-failed-2026-09-13'
PIN_SHA = '1f21c3951e4efa67309a31fa3acb42dafd0a5d3b3ea8020035206d33827a7d9f'
OLD_PIN_SHA = '4f5cd502c563f7dc23b3be81bffd93429eea8c30434e56da96b4d49f5cc42ee7'
PEER = SCRATCH / 'windows-reservation-source-review01/CORRECTION02-SOURCE-VERDICT.md'
PEER_SHA = '6f46d20685dabacce6069b127689eb93b016a5999937fa474066bb875a528650'
ACTUAL_NAMES = (
    'WINDOWS-RESERVATION02-ADMISSION-ACTUAL.json',
    'WINDOWS-RESERVATION02-AUTHOR-ACTUAL.json',
    'WINDOWS-RESERVATION02-INDEPENDENT-ACTUAL.json',
    'WINDOWS-RESERVATION02-INDEPENDENT-PREPARATION-ACTUAL.json',
)
GUARDS = {
    'startup_bound', 'content_reads_closed', 'audit_identity_unchanged',
    'metadata_traps_installed', 'baseline_winreg_identity_unchanged',
    'registry_namespace_unchanged', 'registry_traps_installed',
    'captures_installed', 'capture_valid', 'real_entrypoints_unchanged',
}

def blob(path):
    assert not path.is_symlink() and path.is_file(), str(path)
    raw = path.read_bytes()
    assert len(raw) < 2_000_000, str(path)
    return raw

def fingerprint(path):
    raw = blob(path)
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def read(path):
    return json.loads(blob(path))

def write(name, value):
    with (OUT / name).open('xb') as stream:
        stream.write((json.dumps(value, indent=2) + '\n').encode())

pins = read(AUTHOR / 'PINS.json')
assert fingerprint(AUTHOR / 'PINS.json')['sha256'] == PIN_SHA
assert pins['count'] == len(pins['files']) == 28
names = {row['path'] for row in pins['files']}
assert len(names) == 28
expected = read(AUTHOR / 'EXPECTED-CASES.json')
assert len(expected) == len(set(expected)) == 65
correction = read(AUTHOR / 'CORRECTION-BINDINGS.json')
old_pins = read(AUTHOR / 'before/PINS.json')
assert fingerprint(AUTHOR / 'before/PINS.json')['sha256'] == OLD_PIN_SHA
assert len(old_pins['files']) == 28
for row in old_pins['files']:
    assert fingerprint(AUTHOR / 'before' / row['path']) == {k: row[k] for k in ('bytes', 'sha256')}
assert {row['path'] for row in correction['files'] if row['changed']} == {
    'BRIEF.md', 'QUALIFICATION-PROTOCOL.md', 'run_preflight01.ps1', 'test_windows_reservations.py'}
for row in correction['files']:
    assert fingerprint(AUTHOR / row['path']) == {'bytes': row['after_bytes'], 'sha256': row['after_sha256']}
    assert fingerprint(AUTHOR / 'before' / row['path']) == {'bytes': row['before_bytes'], 'sha256': row['before_sha256']}
old_test = blob(AUTHOR / 'before/test_windows_reservations.py')
first = b'with self.assertRaises(AssertionError):'
second = b'with self.assertRaisesRegex(AssertionError, "current_retired_lifetime_required"):'
assert old_test.count(first) == old_test.count(second) == 1
corrected = old_test.replace(first, b'with self.assertRaises(actual_flow.operation_flow.adoption_flow.KernelUnconfirmed):')
corrected = corrected.replace(second, b'with self.assertRaisesRegex(actual_flow.operation_flow.adoption_flow.KernelUnconfirmed, "current_retired_lifetime_required"):')
assert blob(AUTHOR / 'test_windows_reservations.py') == corrected
patch = fingerprint(AUTHOR / 'RYAN-APPROVED.patch.txt')
assert patch['sha256'] == 'ab91127a9fc3826d2fbb6d0c83be7c6bd905e2a181f01dd3beb36be6fc4ccd73'
assert patch == fingerprint(OLD / 'preparation/fixture-correction.UNAPPLIED.patch.txt')
assert read(AUTHOR / 'ACTUAL-PREPARATION01-FAILURE.json')['exit_code'] == 1
assert read(AUTHOR / 'ACTUAL-PREPARATION02-SUCCESS.json')['exit_code'] == 0

results, comparisons = [], []
for base, actual_name, chunk, stdout_size in (
    (AUTHOR, ACTUAL_NAMES[1], 'f480a2', 30685),
    (INDEPENDENT, ACTUAL_NAMES[2], '503555', 30686),
):
    run = base / 'windows-reservation02'
    assert fingerprint(base / 'PINS.json')['sha256'] == PIN_SHA
    for row in pins['files']:
        wanted = {k: row[k] for k in ('bytes', 'sha256')}
        assert fingerprint(base / row['path']) == fingerprint(run / row['path']) == wanted
    admission = read(base / 'ROOT-ADMISSION.json')
    assert admission == {'approved': True, 'label': 'windows-reservation02',
                         'scope': 'generated_bytes_and_fake_ports_only', 'pins_sha256': PIN_SHA}
    assert blob(base / 'ROOT-ADMISSION.json') == blob(run / 'ROOT-ADMISSION.json')
    required = names | {'PINS.json', 'ROOT-ADMISSION.json', 'plan.json', 'native-exit.json',
                        'stdout.json', 'stderr.log', 'input-check.json', 'exit.json'}
    assert len(required) == 36 and {p.name for p in run.iterdir()} == required
    result, native, exit_result = read(run / 'stdout.json'), read(run / 'native-exit.json'), read(run / 'exit.json')
    assert result['schema'] == 'uoink.windows-reservation-fake-preflight.v1'
    assert (result['count'], result['passed'], result['failed'], result['skipped']) == (65, 65, 0, 0)
    assert result['expected_cases'] == [row['id'] for row in result['cases']] == expected
    assert all(row['passed'] is True and row['skipped'] is False and row['errors'] == [] for row in result['cases'])
    subtests = [sub for row in result['cases'] for sub in row['subtests']]
    assert len(subtests) == 33 and all(row['passed'] is True for row in subtests)
    assert set(result['guards']) == GUARDS and all(value is True for value in result['guards'].values())
    assert result['guard_valid'] is True and result['membership_valid'] is True
    assert result['guard_denials'] == result['registry_denials'] == result['heavy_roots_loaded'] == []
    assert result['metadata_trap_count'] == 12 and result['registry_trap_count'] == 25
    assert len(result['input_sha256']) == 19
    for name, sha in result['input_sha256'].items():
        assert fingerprint(base / name)['sha256'] == sha
    assert type(native['native_exit']) is int and native['native_exit'] == 0
    assert result['qualification_exit'] == exit_result['native_exit'] == exit_result['qualification_exit'] == 0
    assert all(exit_result[key] is True for key in ('valid', 'inputs_unchanged', 'membership_valid', 'guards_valid'))
    assert (exit_result['passed'], exit_result['failed'], exit_result['skipped']) == (65, 0, 0)
    assert exit_result['stdout_bytes'] == fingerprint(run / 'stdout.json')['bytes'] == stdout_size
    assert exit_result['stderr_bytes'] == fingerprint(run / 'stderr.log')['bytes'] == 0
    checks = read(run / 'input-check.json')
    assert checks['inputs_unchanged'] is True and len(checks['inputs']) == 28 and len(checks['controls']) == 3
    assert {r['name'] for r in checks['inputs']} == names
    assert {r['name'] for r in checks['controls']} == {'PINS.json', 'ROOT-ADMISSION.json', 'run_preflight01.ps1'}
    for row in checks['inputs'] + checks['controls']:
        assert row['unchanged'] is True
        assert row['original'] == row['copy'] == fingerprint(base / row['name']) == fingerprint(run / row['name'])
    actual = read(SCRATCH / actual_name)
    assert actual['chunk_id'] == chunk and type(actual['exit_code']) is int and actual['exit_code'] == 0
    results.append(result)
    comparisons.append({'root': str(base), 'actual_tool': actual_name, 'chunk_id': chunk,
                        'outer_exit': 0, 'native_exit': 0, 'passed': 65, 'failed': 0, 'skipped': 0,
                        'nested_subtests': 33, 'all_nested_passed': True,
                        'case_elapsed_seconds': result['elapsed_seconds'],
                        'launcher_elapsed_seconds': exit_result['elapsed_seconds'],
                        'outer_elapsed_seconds': actual['wall_time_seconds'],
                        'stdout': fingerprint(run / 'stdout.json'), 'stderr_bytes': 0,
                        'input_comparisons': 28, 'control_comparisons': 3,
                        'all_current_bytes_match_receipts': True, 'all_ten_guards_true': True})
assert results[0]['cases'] == results[1]['cases']
assert results[0]['input_sha256'] == results[1]['input_sha256']
copies = read(INDEPENDENT / 'COPY-BINDINGS.json')
assert copies['candidate_executed'] is False and copies['exact_input_count'] == len(copies['files']) == 28
assert copies['launcher_changes'] == 0
for row in copies['files']:
    assert row['name'] in names
    assert Path(row['source']) == AUTHOR / row['name'] and Path(row['copy']) == INDEPENDENT / row['name']
    assert fingerprint(Path(row['source'])) == fingerprint(Path(row['copy'])) == {k: row[k] for k in ('bytes', 'sha256')}
assert fingerprint(INDEPENDENT / 'COPY-BINDINGS.json')['sha256'] == '799558594f363696f86994d64ebee21b54db944532e1a8b6125561ae735bff11'
assert fingerprint(PEER)['sha256'] == PEER_SHA
for name in ACTUAL_NAMES:
    assert read(SCRATCH / name)['exit_code'] == 0

paths = {}
def add(source, relative):
    assert relative not in paths
    assert source.suffix.lower() in {'.py', '.ps1', '.json', '.md', '.txt', '.diff', '.log'} or source.name == '.gitattributes'
    blob(source).decode('utf-8-sig')
    paths[relative] = source

for base, prefix in ((AUTHOR, 'author'), (INDEPENDENT, 'independent')):
    for path in sorted(base.rglob('*')):
        assert not path.is_symlink(), str(path)
        if path.is_file():
            add(path, prefix + '/' + path.relative_to(base).as_posix())
for name in ACTUAL_NAMES:
    add(SCRATCH / name, 'actual/' + name)
add(SCRATCH / 'WINDOWS-RESERVATION02-ROOT-REVIEW.md', 'review/ROOT-REVIEW.md')
add(PEER, 'review/CORRECTION02-SOURCE-VERDICT.md')
prior_refs = []
for source in (OLD / 'SHA256.json', OLD / 'FIXED-COPY-LIST.json', OLD / 'ASTRA-VERDICT.md',
               ROOT / 'docs/library/ASTRA-WINDOWS-RESERVATION-FAILED-VERDICT-2026-09-13.md'):
    add(source, 'prior-58335df/' + source.name)
    prior_refs.append({'commit': '58335df', 'path': source.relative_to(ROOT).as_posix(), **fingerprint(source)})
comparison = {'review_scope': 'Read-only completed text receipts and byte comparisons; no test execution',
              'exact_case_objects_equal': True, 'distinct_top_level_cases': 65,
              'observations': comparisons, 'original_failure_status': '63 passed / 2 failed, unchanged',
              'only_approved_two_test_expressions_changed': True, 'original_42_bodies_unchanged': True,
              'independent_launcher_changes': 0, 'original_proof_references': prior_refs}
write('RECEIPT-COMPARISON.json', comparison)
for name in ('.gitattributes', 'VERDICT.md', 'write_fixed_list.py', 'RECEIPT-COMPARISON.json'):
    add(OUT / name, 'review/' + name if name != '.gitattributes' else name)
rows = [{'source': str(source), 'relative_path': relative, **fingerprint(source)}
        for relative, source in sorted(paths.items())]
fixed = {'schema': 'uoink.fixed-documentary-copy-list.v1',
         'purpose': 'Windows reservation02 corrected qualification; fixed known text inputs and completed receipts',
         'file_count': len(rows), 'total_bytes': sum(row['bytes'] for row in rows),
         'prior_large_proof_is_referenced_only': '58335df', 'files': rows}
write('FIXED-COPY-LIST.json', fixed)
print(json.dumps({'file_count': fixed['file_count'], 'total_bytes': fixed['total_bytes'],
                  'fixed_copy_list': fingerprint(OUT / 'FIXED-COPY-LIST.json'),
                  'comparison': fingerprint(OUT / 'RECEIPT-COMPARISON.json'),
                  'verdict': fingerprint(OUT / 'VERDICT.md'), 'candidate_executed': False}, indent=2))
