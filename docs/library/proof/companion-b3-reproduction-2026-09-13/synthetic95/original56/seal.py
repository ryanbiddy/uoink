"""Freeze qualified B3 inputs and retained evidence without another execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
prior_expected = {'companion-b2-builder01': 'ac31912d51a4a6b38c8e028e65bd005e9fedcd7125d51f219ca51973b834fc8f',
                  'companion-hub-keyword-review01': 'b08fb56fe9d76ca3d289105c206cfbfd584b12f87608ddf285172b58b8c2fc33'}
prior_checked = []
for name, expected in prior_expected.items():
    directory = out.parent / name
    raw = (directory / 'SHA256.json').read_bytes()
    assert sha(raw) == expected
    manifest = json.loads(raw)
    for row in manifest['payloads']:
        data = (directory / row['file']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
    prior_checked.append({'directory': name, 'manifest_sha256': expected, 'payloads_unchanged': len(manifest['payloads'])})
result = json.loads((out / 'runs/b3w01/result.json').read_text(encoding='utf-8'))
actual = json.loads((out / 'launch-b3w01/result.json').read_text(encoding='utf-8'))
assert (result['tests_run'], result['passed'], result['failed'], result['errors'], result['skipped'], result['exit']) == (68, 68, 0, 0, 0, 0)
assert result['guard'] == {'preloaded_heavy': [], 'postloaded_heavy': [], 'violations': [], 'finder_installed_at_finish': True, 'valid': True}
assert actual['actual_child_exit'] == actual['actual_outer_exit'] == 0 and actual['inputs_unchanged'] is True
old = json.loads((out.parent / 'companion-b2-builder01/runs/bw03/result.json').read_text(encoding='utf-8'))
old_ids = {row['id'] for row in old['observations']}
new_ids = {row['id'] for row in result['observations']}
assert len(old_ids) == 62 and len(new_ids) == 68 and old_ids < new_ids and len(new_ids - old_ids) == 6
review = json.loads((out / 'PREQUALIFICATION-REVIEW.json').read_text(encoding='utf-8'))
for field, name in [('builder_sha256', 'build_faster_whisper_localassets_wheel.py'), ('protocol_sha256', 'tests-synthetic.py'),
                    ('runner_sha256', 'run-synthetic.py'), ('launcher_sha256', 'launch.py'), ('member_manifest_sha256', 'recipe/member-manifest.json')]:
    assert sha((out / name).read_bytes()) == review[field]
paths = [out / name for name in ('build_faster_whisper_localassets_wheel.py', 'tests-synthetic.py', 'run-synthetic.py', 'launch.py', 'BRIEF.md')]
paths.extend(path for name in ('recipe', 'fixtures') for path in sorted((out / name).rglob('*')) if path.is_file())
inputs = []
launched = json.loads((out / 'launch-b3w01/plan.json').read_text(encoding='utf-8'))['input_hashes']
for path in paths:
    raw = path.read_bytes()
    assert sha(raw) == launched[str(path)]
    inputs.append({'file': str(path.relative_to(out)).replace('\\', '/'), 'bytes': len(raw), 'sha256': sha(raw)})
assert len(inputs) == 24
(out / 'QUALIFIED-INPUTS.json').write_text(json.dumps({'payload_count': len(inputs), 'payloads': inputs}, indent=2)+'\n', encoding='utf-8', newline='\n')
(out / 'QUALIFICATION-CHECKS.json').write_text(json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(),
    'prior_evidence': prior_checked, 'inherited_case_ids': sorted(old_ids), 'new_case_ids': sorted(new_ids - old_ids),
    'actual_child_exit': 0, 'actual_outer_exit': 0, 'qualified_input_count': len(inputs),
    'root_independent_run': 'PENDING', 'actual_B3_wheel_build': False,
    'no_new_execution_during_sealing': True}, indent=2)+'\n', encoding='utf-8', newline='\n')
rows = []
for path in sorted(out.rglob('*')):
    if path.is_file() and path != out / 'SHA256.json':
        raw = path.read_bytes()
        rows.append({'file': str(path.relative_to(out)).replace('\\', '/'), 'bytes': len(raw), 'sha256': sha(raw)})
raw = (json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'payload_count': len(rows), 'payloads': rows}, indent=2)+'\n').encode()
with (out / 'SHA256.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(rows), 'manifest_sha256': sha(raw), 'qualified_inputs': len(inputs), 'passed': 68, 'prior_evidence_unchanged': True}))
