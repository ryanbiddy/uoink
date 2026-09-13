"""Data-only source/diff/case binding; never execute proposed reader or harness."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
previous = out.parent / 'vad-plain-state-reader-proposal02'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
manifest_raw = (previous / 'SHA256.json').read_bytes()
assert sha(manifest_raw) == '6c79c477cec73ca3b104ab9e8917ce96166328474ab7373a86cb3fba22a72b8a'
manifest = json.loads(manifest_raw)
assert len(manifest['files']) == 25
for row in manifest['files']:
    raw = (previous / row['path']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']

def write(name, raw):
    with (out / name).open('xb') as stream:
        stream.write(raw)

def save(name, obj):
    write(name, (json.dumps(obj, indent=2) + '\n').encode('utf-8'))

before_harness = (out / 'before/qualify_reader.py').read_bytes()
after_harness = (out / 'qualify_reader.py').read_bytes()
assert before_harness == (previous / 'qualify_reader.py').read_bytes()
before_tree, after_tree = ast.parse(before_harness), ast.parse(after_harness)
added = [node for node in after_tree.body if isinstance(node, ast.FunctionDef)
         and node.name in {'scanner_boundary', 'scanner_next_level', 'scanner_strings',
                          'scanner_after_string', 'scanner_deadline', 'scanner_unmatched_close'}]
assert len(added) == 6
new_ids = [ast.literal_eval(node.decorator_list[0].args[0]) for node in added]
for node in added:
    after_tree.body.remove(node)
assert ast.dump(before_tree, include_attributes=False) == ast.dump(after_tree, include_attributes=False)
old_ids = json.loads((out / 'before/EXPECTED-CASES.json').read_bytes())
assert len(old_ids) == 76
all_ids = old_ids + new_ids
assert len(all_ids) == 82 and len(set(all_ids)) == 82
assert (out / 'EXPECTED-CASES.json').read_bytes() == (out / 'before/EXPECTED-CASES.json').read_bytes()
(out / 'EXPECTED-CASES.json').write_bytes((json.dumps(all_ids, indent=2) + '\n').encode('utf-8'))

before_reader = (out / 'before/plain_state_reader.py').read_bytes()
after_reader = (out / 'plain_state_reader.py').read_bytes()
assert before_reader == (previous / 'plain_state_reader.py').read_bytes()
assert sha(before_reader) == '296dec43cf7fbdefec54ae1ae321c48e98351152d723cc8f5849c6b6972bfef6'
ast.parse(after_reader)
for stem, before, after in [('READER-REPAIR', before_reader, after_reader),
                            ('SCANNER-CONTRACT-ADDITIONS', before_harness, after_harness)]:
    write(stem+'.patch', ''.join(difflib.unified_diff(
        before.decode('utf-8').splitlines(keepends=True),
        after.decode('utf-8').splitlines(keepends=True),
        fromfile='proposal02/'+('plain_state_reader.py' if stem=='READER-REPAIR' else 'qualify_reader.py'),
        tofile='proposal03/'+('plain_state_reader.py' if stem=='READER-REPAIR' else 'qualify_reader.py'))).encode('utf-8'))
inputs = json.loads((previous / 'INPUTS.json').read_bytes())
inputs['child_files']['plain_state_reader.py'] = sha(after_reader)
inputs['child_files']['qualify_reader.py'] = sha(after_harness)
save('INPUTS.json', inputs)
admission = json.loads((previous / 'ROOT-ADMISSION.TEMPLATE.json').read_bytes())
admission['label'] = 'vpr03'
admission['review_document'] = 'ROOT MUST REVIEW THE BOUNDED JSON DEPTH REPAIR AND SIX NEW CONTRACTS'
for name in admission['source_hashes']:
    admission['source_hashes'][name] = sha((out / name).read_bytes())
assert admission['root_reviewed'] is False
save('ROOT-ADMISSION.TEMPLATE.json', admission)
save('REPAIR-SOURCE-BINDINGS.json', {
    'previous_preparation_manifest_sha256': sha(manifest_raw),
    'previous_preparation_payloads_verified': 25,
    'vpr02_failure_manifest_sha256': '771a592fe81078a18285253ddde50651ed54449dfab3202a00fadf659657c7dc',
    'reader_before_sha256': sha(before_reader), 'reader_after_sha256': sha(after_reader),
    'harness_before_sha256': sha(before_harness), 'harness_after_sha256': sha(after_harness),
    'frozen_76_assertions_and_ids_unchanged': True, 'added_cases': new_ids,
    'new_expected_case_count': 82, 'proposed_source_or_harness_executed': False})
print(json.dumps({'reader_sha256': sha(after_reader), 'harness_sha256': sha(after_harness),
                  'inputs_sha256': sha((out / 'INPUTS.json').read_bytes()),
                  'admission_template_sha256': sha((out / 'ROOT-ADMISSION.TEMPLATE.json').read_bytes()),
                  'original_cases_unchanged': 76, 'added_cases': 6, 'expected_cases': 82}))
