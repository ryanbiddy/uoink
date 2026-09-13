"""Verify text receipts and freeze this proof; execute no captured/test code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
out = Path(__file__).absolute().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
preflight = json.loads((out / 'PREQUALIFICATION.json').read_text(encoding='utf-8'))
receipt = json.loads((out / 'runs/pc01/result.json').read_text(encoding='utf-8'))
launch = json.loads((out / 'launch-pc01/result.json').read_text(encoding='utf-8'))
outer = json.loads((out / 'launch-pc01/root-outer-exit.json').read_text(encoding='utf-8-sig'))
plan = json.loads((out / 'launch-pc01/plan.json').read_text(encoding='utf-8'))
for row in preflight['inputs']:
    raw = (out / row['file']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
for name, digest in plan['input_hashes'].items(): assert sha((out / name).read_bytes()) == digest
for name, digest in receipt['input_hashes'].items(): assert sha((out / name).read_bytes()) == digest
assert {row['id'] for row in preflight['cases']} == {row['id'] for row in receipt['observations']}
assert len(receipt['observations']) == 23 and all(row['status'] == 'passed' for row in receipt['observations'])
assert (receipt['tests_run'], receipt['passed'], receipt['failed'], receipt['errors'], receipt['skipped'], receipt['exit']) == (23, 23, 0, 0, 0, 0)
assert receipt['fatal'] is None and receipt['guard']['valid']
assert not receipt['guard']['forbidden_pipeline_initializer_calls']
assert receipt['guard']['finder_installed_at_finish'] and receipt['guard']['profile_installed_at_finish']
assert not receipt['guard']['violations'] and not receipt['guard']['preloaded_heavy'] and not receipt['guard']['postloaded_heavy']
assert len(receipt['selected_method_call_counts']) == 18 and 'Pipeline.__init__' not in receipt['selected_method_call_counts']
assert launch['actual_child_exit'] == launch['launcher_exit'] == outer['actual_outer_exit'] == 0
assert launch['inputs_unchanged']
assert receipt['diagnostics'] == [{'input': 'direct empty list', 'expected_if_supported': [], 'exception_type': 'IndexError',
    'message': 'list index out of range', 'status': 'UNACCEPTED_OPTIONAL_API_DEFECT', 'source': 'base.py.txt', 'line': 1242}]
checks = {'verified_utc': datetime.now(timezone.utc).isoformat(), 'cases': 23, 'passed': 23, 'failed': 0, 'errors': 0, 'skipped': 0,
    'child_exit': 0, 'launcher_exit': 0, 'actual_outer_exit': 0, 'guard_valid': True, 'inputs_unchanged': True,
    'case_ids_match_preflight': True, 'selected_bodies_executed': 18, 'captured_pipeline_initializer_executed': False,
    'unaccepted_diagnostics': receipt['diagnostics'], 'new_test_or_captured_execution_by_this_checker': False}
(out / 'QUALIFICATION-CHECKS.json').write_text(json.dumps(checks, indent=2)+'\n', encoding='utf-8', newline='\n')
payloads = []
for path in sorted(out.rglob('*')):
    if not path.is_file() or path.name == 'SHA256.json': continue
    raw = path.read_bytes()
    payloads.append({'file': path.relative_to(out).as_posix(), 'bytes': len(raw), 'sha256': sha(raw)})
manifest = {'created_utc': datetime.now(timezone.utc).isoformat(), 'payload_count': len(payloads), 'payloads': payloads,
    'scope': 'Captured source text, synthetic AST contracts and exact receipts; no packages, model artifacts, binaries, source/pin/staging edits or runtime acceptance.'}
raw = (json.dumps(manifest, indent=2)+'\n').encode('utf-8')
(out / 'SHA256.json').write_bytes(raw)
print(json.dumps({'payload_count': len(payloads), 'manifest_sha256': sha(raw), 'verified_cases': 23,
    'optional_empty_list': 'UNACCEPTED_INDEXERROR', 'additional_tests_run': False}))
