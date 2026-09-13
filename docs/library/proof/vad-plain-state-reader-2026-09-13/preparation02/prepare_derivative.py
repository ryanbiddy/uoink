"""Data-only instrument repair preparation; execute no proposed reader/harness."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
previous = out.parent / 'vad-plain-state-reader-proposal01'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
manifest_raw = (previous / 'SHA256.json').read_bytes()
assert sha(manifest_raw) == 'd2bf7531d5f89a50d80d7260e993954b81a56e4c6fa4457d08c770b8c728a0bf'
manifest = json.loads(manifest_raw)
assert len(manifest['files']) == 26
for row in manifest['files']:
    raw = (previous / row['path']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']

def write(name, raw):
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)

def save(name, obj):
    write(name, (json.dumps(obj, indent=2) + '\n').encode('utf-8'))

copy_names = ('plain_state_reader.py', 'fixed-plan.json', 'launch.py', 'run-root.ps1',
              'BRIEF.md', 'SOURCE-BINDINGS.json', 'EXPECTED-CASES.json',
              'context/fixed_converter.py.txt', 'context/fixed-factory.proposal.txt',
              'context/root-brief.md', 'CANONICAL-LAYOUT.json', '.gitattributes')
for name in copy_names:
    raw = (previous / name).read_bytes()
    if (out / name).exists():
        assert (out / name).read_bytes() == raw
    else:
        write(name, raw)
before = (previous / 'qualify_reader.py').read_bytes()
old = b'import encodings.utf_8_sig\n'
new = old + b'import encodings.utf_16_le\n'
assert before.count(old) == 1
after = before.replace(old, new, 1)
write('before/qualify_reader.py', before)
write('qualify_reader.py', after)
before_tree, after_tree = ast.parse(before), ast.parse(after)
additions = [node for node in after_tree.body if isinstance(node, ast.Import)
             and len(node.names) == 1 and node.names[0].name == 'encodings.utf_16_le']
assert len(additions) == 1
after_tree.body.remove(additions[0])
assert ast.dump(before_tree, include_attributes=False) == ast.dump(after_tree, include_attributes=False)
write('HARNESS-REPAIR.patch', ''.join(difflib.unified_diff(
    before.decode('utf-8').splitlines(keepends=True),
    after.decode('utf-8').splitlines(keepends=True),
    fromfile='proposal01/qualify_reader.py', tofile='proposal02/qualify_reader.py')).encode('utf-8'))
inputs = json.loads((previous / 'INPUTS.json').read_bytes())
inputs['child_files']['qualify_reader.py'] = sha(after)
save('INPUTS.json', inputs)
admission = json.loads((previous / 'ROOT-ADMISSION.TEMPLATE.json').read_bytes())
admission['label'] = 'vpr02'
admission['review_document'] = 'ROOT MUST REVIEW THE EXPLICIT CODEC PRELOAD REPAIR BEFORE RUNNING'
for name in admission['source_hashes']:
    admission['source_hashes'][name] = sha((out / name).read_bytes())
assert admission['root_reviewed'] is False
save('ROOT-ADMISSION.TEMPLATE.json', admission)
save('PREPARATION-CHECK.json', {
    'original_preparation_manifest_sha256': sha(manifest_raw),
    'original_preparation_payloads_verified': 26,
    'failure_manifest_sha256': '89b90577f401955b4faa0d440118632b2b0cb2e4e7a1a976a702c85d7cbc008b',
    'original_reader_unchanged': True,
    'reader_sha256': sha((out / 'plain_state_reader.py').read_bytes()),
    'harness_before_sha256': sha(before), 'harness_after_sha256': sha(after),
    'only_ast_change': 'Import encodings.utf_16_le before guard closure',
    'case_assertions_and_ids_unchanged': True,
    'case_count': len(json.loads((out / 'EXPECTED-CASES.json').read_bytes())),
    'reader_or_harness_executed_during_repair': False})
print(json.dumps({'harness_sha256': sha(after),
                  'inputs_sha256': sha((out / 'INPUTS.json').read_bytes()),
                  'admission_template_sha256': sha((out / 'ROOT-ADMISSION.TEMPLATE.json').read_bytes()),
                  'only_ast_change': 'Explicit UTF-16LE codec preload', 'cases_unchanged': 76}))
