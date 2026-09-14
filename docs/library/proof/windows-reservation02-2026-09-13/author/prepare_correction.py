"""Apply the exact approved text patch and label controls; never execute source."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
import re

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
OLD = ROOT / '_scratch/windows-reservation-implementation-proposal01'
PROOF = ROOT / 'docs/library/proof/windows-reservation-failed-2026-09-13'
FROZEN = PROOF / 'proposal'
OUT = ROOT / '_scratch/windows-reservation-implementation-proposal02'
PATCH = PROOF / 'preparation/fixture-correction.UNAPPLIED.patch.txt'
OLD_PINS_SHA = '4f5cd502c563f7dc23b3be81bffd93429eea8c30434e56da96b4d49f5cc42ee7'
PATCH_SHA = 'ab91127a9fc3826d2fbb6d0c83be7c6bd905e2a181f01dd3beb36be6fc4ccd73'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def save_json(path, data):
    with path.open('xb') as stream: stream.write((json.dumps(data, indent=2) + '\n').encode())
def write_new(path, raw):
    with path.open('xb') as stream: stream.write(raw)

pins_raw = (FROZEN / 'PINS.json').read_bytes()
assert sha(pins_raw) == OLD_PINS_SHA and (OLD / 'PINS.json').read_bytes() == pins_raw
pins = json.loads(pins_raw)
assert pins['count'] == len(pins['files']) == 28
patch_raw = PATCH.read_bytes()
assert sha(patch_raw) == PATCH_SHA
originals = {}
for row in pins['files']:
    name = row['path']
    assert re.fullmatch(r'[A-Za-z0-9_.-]+', name)
    raw = (FROZEN / name).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    assert (OLD / name).read_bytes() == raw
    originals[name] = raw

raw = originals['test_windows_reservations.py']
base_lines = raw.splitlines(keepends=True)
patch_lines = patch_raw.decode().splitlines()
assert patch_lines[:2] == ['--- a/test_windows_reservations.py', '+++ b/test_windows_reservations.py']
headers = [i for i, line in enumerate(patch_lines) if line.startswith('@@ ')]
assert len(headers) == 2
out_lines, cursor, removed, added = [], 0, [], []
for h, position in enumerate(headers):
    match = re.fullmatch(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@.*', patch_lines[position])
    assert match
    old_start, old_count, new_start, new_count = map(int, match.groups())
    start = old_start - 1
    assert cursor <= start
    out_lines.extend(base_lines[cursor:start])
    cursor = start
    before_used = after_used = 0
    stop = headers[h + 1] if h + 1 < len(headers) else len(patch_lines)
    newline = b'\n'
    for line in patch_lines[position + 1:stop]:
        assert line and line[0] in ' +-'
        content = line[1:].encode()
        if line[0] in ' -':
            actual = base_lines[cursor]
            assert actual.rstrip(b'\r\n') == content
            newline = actual[len(content):]
            assert newline in (b'\n', b'\r\n')
            cursor += 1
            before_used += 1
        if line[0] == ' ':
            out_lines.append(actual)
            after_used += 1
        elif line[0] == '-':
            removed.append(content.decode())
        else:
            out_lines.append(content + newline)
            added.append(content.decode())
            after_used += 1
    assert (before_used, after_used) == (old_count, new_count)
out_lines.extend(base_lines[cursor:])
corrected = b''.join(out_lines)
assert len(removed) == len(added) == 2
assert all(after == before.replace('AssertionError', 'actual_flow.operation_flow.adoption_flow.KernelUnconfirmed', 1)
           for before, after in zip(removed, added))
exact_diff = ''.join(difflib.unified_diff(raw.decode().splitlines(keepends=True), corrected.decode().splitlines(keepends=True),
    fromfile='a/test_windows_reservations.py', tofile='b/test_windows_reservations.py'))
def canonical_hunk_headers(text):
    return re.sub(r'(?m)^(@@ -\d+,\d+ \+\d+,\d+ @@)[^\n]*', r'\1', text.replace('\r\n', '\n')).rstrip('\n')
assert canonical_hunk_headers(exact_diff) == canonical_hunk_headers(patch_raw.decode())
old_tree, new_tree = ast.parse(raw), ast.parse(corrected)
expression = 'actual_flow.operation_flow.adoption_flow.KernelUnconfirmed'
replacements = 0
for node in ast.walk(new_tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('assertRaises', 'assertRaisesRegex'):
        if node.args and ast.unparse(node.args[0]) == expression:
            node.args[0] = ast.Name(id='AssertionError', ctx=ast.Load())
            replacements += 1
assert replacements == 2
assert ast.dump(new_tree, include_attributes=False) == ast.dump(old_tree, include_attributes=False)
case_ids = json.loads(originals['EXPECTED-CASES.json'])
assert len(case_ids) == len(set(case_ids)) == 65
original_tree = ast.parse(originals['test_reservations.py'])
original_case_bodies = [node for cls in original_tree.body if isinstance(cls, ast.ClassDef)
                        for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]
assert len(original_case_bodies) == 42

before = OUT / 'before'
before.mkdir()
for name, original in originals.items(): write_new(before / name, original)
write_new(before / 'PINS.json', pins_raw)
template_raw = (FROZEN / 'ROOT-ADMISSION-TEMPLATE.json').read_bytes()
assert template_raw == (OLD / 'ROOT-ADMISSION-TEMPLATE.json').read_bytes()
write_new(before / 'ROOT-ADMISSION-TEMPLATE.json', template_raw)
write_new(OUT / 'RYAN-APPROVED.patch.txt', patch_raw)
write_new(OUT / 'test_windows_reservations.py.diff', exact_diff.encode())
new_files = {}
label_changes = {}
for name, original in originals.items():
    if name == 'test_windows_reservations.py':
        new = corrected
    elif name in ('run_preflight01.ps1', 'QUALIFICATION-PROTOCOL.md'):
        count = original.count(b'windows-reservation01')
        assert count > 0
        new = original.replace(b'windows-reservation01', b'windows-reservation02')
        label_changes[name] = count
        diff = ''.join(difflib.unified_diff(original.decode().splitlines(keepends=True), new.decode().splitlines(keepends=True),
            fromfile='before/' + name, tofile='proposal02/' + name))
        write_new(OUT / (name + '.diff'), diff.encode())
    elif name == 'BRIEF.md':
        new = (OUT / name).read_bytes()
    else:
        new = original
    if name != 'BRIEF.md': write_new(OUT / name, new)
    new_files[name] = new
changed = {name for name in originals if new_files[name] != originals[name]}
assert changed == {'test_windows_reservations.py', 'run_preflight01.ps1', 'QUALIFICATION-PROTOCOL.md', 'BRIEF.md'}
assert new_files['test_reservations.py'] == originals['test_reservations.py']
assert new_files['EXPECTED-CASES.json'] == originals['EXPECTED-CASES.json']
new_pins = {'schema': pins['schema'], 'count': 28,
            'files': [{'path': row['path'], 'bytes': len(new_files[row['path']]), 'sha256': sha(new_files[row['path']])} for row in pins['files']]}
save_json(OUT / 'PINS.json', new_pins)
template = json.loads(template_raw)
assert template['approved'] is False and template['label'] == 'windows-reservation01' and template['pins_sha256'] == OLD_PINS_SHA
template['label'] = 'windows-reservation02'
template['pins_sha256'] = sha((OUT / 'PINS.json').read_bytes())
save_json(OUT / 'ROOT-ADMISSION-TEMPLATE.json', template)
bindings = []
for name, original in originals.items():
    assert (FROZEN / name).read_bytes() == (OLD / name).read_bytes() == original
    assert (OUT / name).read_bytes() == new_files[name]
    bindings.append({'path': name, 'before_bytes': len(original), 'before_sha256': sha(original),
                     'after_bytes': len(new_files[name]), 'after_sha256': sha(new_files[name]),
                     'changed': original != new_files[name]})
assert (FROZEN / 'PINS.json').read_bytes() == (OLD / 'PINS.json').read_bytes() == pins_raw
assert PATCH.read_bytes() == patch_raw
record = {'candidate_execution': False, 'ryan_approval': 'Root relayed explicit approval of exact two-line patch from 58335df on 2026-09-13',
    'original_result': {'passed': 63, 'failed': 2, 'skipped': 0, 'nested_subtests': 33, 'failed_nested_subtests': 6, 'status': 'failed'},
    'original_pins_sha256': OLD_PINS_SHA, 'approved_patch_sha256': PATCH_SHA,
    'exact_patch_applied': True, 'only_two_exception_AST_expressions_changed': True,
    'original42_case_bodies_byte_unchanged': True, 'all65_case_ids_unchanged': True,
    'message_fault_and_retention_assertions_unchanged': True,
    'all_product_port_and_qualifier_bytes_unchanged': True, 'original_proof_and_proposal01_unchanged': True,
    'label_substitution_counts': label_changes, 'files': bindings,
    'pins_sha256': template['pins_sha256'], 'template_approved': False}
save_json(OUT / 'CORRECTION-BINDINGS.json', record)
write_new(OUT / '.gitattributes', b'* -text\n')
print(json.dumps({'candidate_execution': False, 'files': 28, 'case_ids': 65, 'original_case_bodies': 42,
    'changed_input_names': sorted(changed), 'label_substitutions': label_changes,
    'test_sha256': sha(corrected), 'launcher_sha256': sha(new_files['run_preflight01.ps1']),
    'protocol_sha256': sha(new_files['QUALIFICATION-PROTOCOL.md']), 'pins_sha256': template['pins_sha256'],
    'template_sha256': sha((OUT / 'ROOT-ADMISSION-TEMPLATE.json').read_bytes()),
    'bindings_sha256': sha((OUT / 'CORRECTION-BINDINGS.json').read_bytes())}))
