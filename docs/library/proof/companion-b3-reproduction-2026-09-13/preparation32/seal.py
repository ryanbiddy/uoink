"""Static-only verification and seal; never invoke a launcher/runtime/builder."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
out = Path(__file__).absolute().parent
scratch = out.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
prior = {'b2-real-wheel-preparation01': 'ebab6c9180c7c8f230e55b619d1cc469d7043f1a43e197a3a8abd126f7eb7484',
    'b2-python313-reproduction-preparation01': '0b1cb98b296f34965d8bcebe8a67755bb5315df1a3663b479e282da630346f4c',
    'companion-b3-builder01': '07e4ac3373142058da95b97568b9a8542b8c42942f8e8f877f00fabc7f97c142',
    'companion-b3-combined-review01': '2e982651021232121fd87d058b02b75c2361ff985af230695921397f101bd127'}
for name, expected in prior.items():
    source = scratch / name
    raw = (source / 'SHA256.json').read_bytes()
    assert sha(raw) == expected
    for row in json.loads(raw)['payloads']:
        data = (source / row['file']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
    if name == 'companion-b3-combined-review01':
        with (out / 'prior-seals/B3-combined95-SHA256.json').open('xb') as stream:
            stream.write(raw)
bindings = json.loads((out / 'INPUT-BINDINGS.json').read_text(encoding='utf-8'))
for row in bindings['bindings']:
    raw = (out / row['target']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
assert bindings['B3_first_output_sha256'] is None and bindings['B3_first_output_built'] is False
adaptations = json.loads((out / 'child-adaptation-reasons.json').read_text(encoding='utf-8'))
for label in ('314', '313'):
    before = (out / ('prior-protocols/build-guarded' + label + '.py.txt')).read_text(encoding='utf-8')
    for change in adaptations:
        if change['child'] == label:
            assert before.count(change['before']) == 1
            before = before.replace(change['before'], change['after'])
    assert before == (out / ('build-guarded' + label + '.py')).read_text(encoding='utf-8')
old = (out / 'prior-protocols/copy-and-launch.py.txt').read_text(encoding='utf-8')
new = (out / 'launch.py').read_text(encoding='utf-8')
old_tree, new_tree = ast.parse(old), ast.parse(new)
for name in ['no_links', 'bounded', 'write_json', 'verify_preparation', 'plan', 'verify_runtime', 'fresh']:
    before = next(node for node in old_tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    after = next(node for node in new_tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    assert ast.get_source_segment(old, before) == ast.get_source_segment(new, after)
assert not any(isinstance(node, ast.FunctionDef) and node.name == 'copy_runtime' for node in new_tree.body)
assert 'd64027be41a352117199ecedfa1e9eed48d323140aa4e2c77065111f288b7883' not in (new + (out / 'build-guarded313.py').read_text(encoding='utf-8'))
builder = (out / 'inputs/build_faster_whisper_localassets_wheel.py').read_bytes()
assert len(builder) == 16660 and sha(builder) == 'f25530a3ee58169c049e63c2e6bfff444061f2c04c9a87ec2af43c8850b81892'
tree = ast.parse(builder)
hashes = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'RECIPE_HASHES' for target in node.targets)))
assert len(hashes) == 5
for name, digest in hashes.items():
    assert sha((out / 'inputs/recipe' / name).read_bytes()) == digest
parsed = []
for source in sorted(out.rglob('*.py')):
    raw = source.read_bytes()
    ast.parse(raw, filename=str(source))
    parsed.append({'file': str(source.relative_to(out)).replace('\\', '/'), 'bytes': len(raw), 'sha256': sha(raw)})
receipt = {'status': 'PREPARED_NOT_INVOKED', 'created_utc': datetime.now(timezone.utc).isoformat(),
    'parsed_source_files': parsed, 'prior_seals_unchanged': prior, 'builder_sha256': sha(builder), 'recipe_hashes': hashes,
    'shared_validation_helpers_unchanged': 7, 'runtime_copy_action_absent': True,
    'preparation_actual_exit': 0, 'real_build_commands_run': 0, 'private_runtime_accessed': False,
    'upstream_or_output_wheel_accessed': False, 'model_or_asset_accessed': False, 'B3_first_output_sha256': None}
(out / 'PREPARATION-RECEIPT.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8', newline='\n')
payloads = []
for source in sorted(out.rglob('*')):
    if source.is_file() and source != out / 'SHA256.json':
        raw = source.read_bytes()
        payloads.append({'file': str(source.relative_to(out)).replace('\\', '/'), 'bytes': len(raw), 'sha256': sha(raw)})
raw = (json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'payload_count': len(payloads), 'payloads': payloads}, indent=2)+'\n').encode()
with (out / 'SHA256.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(payloads), 'manifest_sha256': sha(raw), 'source_files_parsed': len(parsed), 'real_builds_invoked': 0}))
