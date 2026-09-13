"""Static B3 source/recipe/assertion review only; does not execute builder/tests."""
import ast
import base64
import csv
import difflib
import hashlib
import io
import json
from pathlib import Path
out = Path(__file__).absolute().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
before = (out / 'prior-inputs/B2-tests.py.txt').read_text(encoding='utf-8')
retained = (out / 'tests-retained62.py.txt').read_text(encoding='utf-8')
expected = before.replace('changed = {"faster_whisper/transcribe.py",', 'changed = {"faster_whisper/utils.py", "faster_whisper/transcribe.py",').replace('1.2.1+uoink.localassets1', '1.2.1+uoink.localassets2')
assert retained == expected
full = (out / 'tests-synthetic.py').read_text(encoding='utf-8')
assert full == retained + '\n' + (out / 'new-contracts.py.txt').read_text(encoding='utf-8')
def assertions(text):
    return [ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr.startswith('assert')]
assert assertions(before) == assertions(retained.replace('1.2.1+uoink.localassets2', '1.2.1+uoink.localassets1'))
new_methods = [node.name for node in ast.parse((out / 'new-contracts.py.txt').read_bytes()).body if isinstance(node, ast.FunctionDef)]
assert len(new_methods) == 6
parsed = []
for name in ['build_faster_whisper_localassets_wheel.py', 'tests-synthetic.py', 'run-synthetic.py', 'launch.py', 'prepare.py', 'static-preflight.py']:
    raw = (out / name).read_bytes()
    ast.parse(raw, filename=str(out / name))
    parsed.append({'file': name, 'sha256': sha(raw)})
tree = ast.parse((out / 'build_faster_whisper_localassets_wheel.py').read_bytes())
constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {'RECIPE_HASHES', 'RECIPE_SIZES', 'EXPECTED_WHEEL_SHA256', 'EXPECTED_WHEEL_SIZE', 'OUTPUT_VERSION', 'INPUT_UTILS_SHA256'}}
assert constants['OUTPUT_VERSION'] == '1.2.1+uoink.localassets2'
assert constants['EXPECTED_WHEEL_SHA256'] == '79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7'
assert constants['EXPECTED_WHEEL_SIZE'] == 1118909
assert len(constants['RECIPE_HASHES']) == len(constants['RECIPE_SIZES']) == 5
for name, digest in constants['RECIPE_HASHES'].items():
    raw = (out / 'recipe' / name).read_bytes()
    assert sha(raw) == digest and len(raw) == constants['RECIPE_SIZES'][name]
utils_before = (out / 'fixtures/upstream-text/faster_whisper/utils.py.txt').read_bytes()
utils_after = (out / 'recipe/utils.py.txt').read_bytes()
assert sha(utils_before) == constants['INPUT_UTILS_SHA256']
assert utils_before.replace(b'        kwargs["local_dir_use_symlinks"] = False\n', b'') == utils_after
hub_patch = ''.join(difflib.unified_diff(utils_before.decode().splitlines(True), utils_after.decode().splitlines(True), 'a/faster_whisper/utils.py', 'b/faster_whisper/utils.py')).encode()
assert sha(hub_patch) == 'd083b6647a89c70529e328a977ea4ba2a14cbfa101cdd944df75a852ac736aee'
assert (out / 'recipe/patch.txt').read_bytes() == (out.parent / 'companion-b2-builder01/recipe/patch.txt').read_bytes() + hub_patch
manifest = json.loads((out / 'recipe/member-manifest.json').read_bytes())
assert manifest['output_wheel_sha256'] is None and manifest['output_wheel_built'] is False
assert len(manifest['members']) == len({row['member'] for row in manifest['members']}) == 16
record = (out / 'proposed-text/RECORD.txt').read_bytes()
rows = list(csv.reader(io.StringIO(record.decode()), strict=True))
rowmap = {row['member']: row for row in manifest['members']}
assert len(rows) == len(rowmap) == 16 and {row[0] for row in rows} == set(rowmap)
for name, hashed, size in rows:
    entry = rowmap[name]
    if name.endswith('/RECORD'):
        assert hashed == size == '' and sha(record) == entry['sha256'] and len(record) == entry['bytes']
    else:
        assert hashed == 'sha256=' + base64.urlsafe_b64encode(bytes.fromhex(entry['sha256'])).decode().rstrip('=') and size == str(entry['bytes'])
receipt = {'status': 'STATIC_PREFLIGHT_ONLY', 'scripts_parsed': parsed, 'inherited_test_ids_expected': 62,
    'inherited_assertion_calls_preserved_except_version_literal': len(assertions(before)), 'new_test_methods': new_methods,
    'recipe_hashes': constants['RECIPE_HASHES'], 'actual_wheel_or_asset_read': False, 'builder_or_protocol_executed': False}
(out / 'STATIC-PREFLIGHT.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8', newline='\n')
print(json.dumps({'static_preflight': 'passed', 'new_test_methods': len(new_methods), 'builder_sha256': parsed[0]['sha256'], 'tests_sha256': parsed[1]['sha256']}))
