"""Combine exact B3 synthetic evidence without execution or large prior trees."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
out = Path(__file__).absolute().parent
scratch = out.parent
old = scratch / 'companion-b3-builder01'
root = scratch / 'astra-b3-builder01'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
copies = []
def copy(source, target, expected=None, size=None):
    raw = source.read_bytes()
    assert len(raw) < 1024 * 1024
    if expected is not None:
        assert sha(raw) == expected
    if size is not None:
        assert len(raw) == size
    dest = out / target
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('xb') as stream:
        stream.write(raw)
    copies.append({'source': str(source), 'target': target, 'bytes': len(raw), 'sha256': sha(raw)})
    return raw
seal = copy(old / 'SHA256.json', 'original56/SHA256.json', '07e4ac3373142058da95b97568b9a8542b8c42942f8e8f877f00fabc7f97c142')
for row in json.loads(seal)['payloads']:
    copy(old / row['file'], 'original56/' + row['file'], row['sha256'], row['bytes'])
qualified = json.loads((old / 'QUALIFIED-INPUTS.json').read_text(encoding='utf-8'))['payloads']
review = json.loads((root / 'ROOT-REVIEW.json').read_text(encoding='utf-8'))
assert review['exact_copied_inputs'] == qualified
for row in qualified:
    copy(root / row['file'], 'independent-root01/' + row['file'], row['sha256'], row['bytes'])
for name in ['ROOT-REVIEW.json', 'runs/b3w01/result.json', 'runs/b3w01/tests.log', 'launch-b3w01/plan.json',
             'launch-b3w01/console.log', 'launch-b3w01/result.json', 'root-outer-exit.json']:
    copy(root / name, 'independent-root01/' + name)
copy(scratch / 'prepare_b3_builder_astra01.py', 'root-preparation/prepare_b3_builder_astra01.py')
copy(scratch / 'companion-b3-independent-review01/VERDICT.md', 'peer-review/VERDICT.md', 'bb7a19fee15ed9f39343f13964cabf033d27731f19131439d40c63fa46c1bdae')
observed = []
for directory in [old, root]:
    receipt = json.loads((directory / 'runs/b3w01/result.json').read_text(encoding='utf-8'))
    outer = json.loads((directory / 'launch-b3w01/result.json').read_text(encoding='utf-8'))
    assert (receipt['tests_run'], receipt['passed'], receipt['failed'], receipt['errors'], receipt['skipped'], receipt['exit']) == (68, 68, 0, 0, 0, 0)
    assert receipt['guard'] == {'preloaded_heavy': [], 'postloaded_heavy': [], 'violations': [], 'finder_installed_at_finish': True, 'valid': True}
    assert outer['actual_child_exit'] == outer['actual_outer_exit'] == 0 and outer['inputs_unchanged']
    observed.append({'source_sha256': receipt['source_sha256'], 'protocol_sha256': receipt['protocol_sha256'],
                     'case_ids': [row['id'] for row in receipt['observations']]})
assert observed[0] == observed[1]
assert json.loads((root / 'root-outer-exit.json').read_text(encoding='utf-8'))['actual_outer_exit'] == 0
(out / 'COPY-AND-VERIFICATION.json').write_text(json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(),
    'copies': copies, 'exact_common_qualification': observed[0], 'runs_passed': [68, 68],
    'original56_unchanged': True, 'older_payload_trees_not_nested': True, 'no_execution_during_assembly': True}, indent=2)+'\n', encoding='utf-8', newline='\n')
payloads = []
for path in sorted(out.rglob('*')):
    if path.is_file() and path != out / 'SHA256.json':
        raw = path.read_bytes()
        payloads.append({'file': str(path.relative_to(out)).replace('\\', '/'), 'bytes': len(raw), 'sha256': sha(raw)})
raw = (json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'payload_count': len(payloads), 'payloads': payloads}, indent=2)+'\n').encode()
with (out / 'SHA256.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(payloads), 'manifest_sha256': sha(raw), 'matching_cases': 68}))
