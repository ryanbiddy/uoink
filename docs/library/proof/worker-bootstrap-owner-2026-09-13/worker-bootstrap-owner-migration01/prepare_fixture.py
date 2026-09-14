"""Factor only generated fixture driver text; candidate code is never run."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
OUT = ROOT / '_scratch/worker-bootstrap-owner-migration01'
ORIGINAL = ROOT / '_scratch/worker-runtime-owner-proposal02/generated_factory_fixture.py'
raw = ORIGINAL.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '1c60507a82c238116b630f146c44e7a81fdc57eb74f05841489c3128f150eb6f'
(OUT / 'before/generated_factory_fixture.py').write_bytes(raw)
old = raw.decode()
assert old.count('    bootstrap = object()\n') == 1
prefix = old[:old.index('    bootstrap = object()\n')]
new = prefix + (OUT / 'fixture_tail.proposal.txt').read_text()
new = new.replace('import types\n', 'import types\nimport owned_generation_protocol as protocol\n', 1)
old_ast, new_ast = ast.parse(old), ast.parse(new)
def named(tree, name):
    return next(node for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == name)
unchanged = ('FakeVoiceParent', 'FakeVoiceActivitySegmentation', 'FakePyanNet', 'Device', 'isfinite', 'act', 'pattern')
assert all(ast.dump(named(old_ast, name), include_attributes=False) == ast.dump(named(new_ast, name), include_attributes=False) for name in unchanged)
assert new[:new.index('    generation = protocol.GenerationBinding')].replace('import owned_generation_protocol as protocol\n', '') == prefix
new_raw = new.encode()
(OUT / 'generated_bootstrap_fixture.py').write_bytes(new_raw)
(OUT / 'generated_bootstrap_fixture.py.diff').write_text(''.join(difflib.unified_diff(
    old.splitlines(keepends=True), new.splitlines(keepends=True),
    fromfile='retained/generated_factory_fixture.py', tofile='proposal/generated_bootstrap_fixture.py')), encoding='utf-8', newline='')
cases_path = OUT / 'connection_cases.py'
cases_ast = ast.parse(cases_path.read_bytes())
case_ids = ['connection_cases.BootstrapContracts.' + node.name for node in named(cases_ast, 'BootstrapContracts').body if isinstance(node, ast.FunctionDef)]
expected = ast.literal_eval(next(node.value for node in cases_ast.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'EXPECTED_CASES' for target in node.targets)))
assert tuple(case_ids) == expected and len(case_ids) == 6
legacy = ROOT / '_scratch/worker-runtime-owner-proposal02/generated_unit_cases.py'
assert hashlib.sha256(legacy.read_bytes()).hexdigest() == '58ce1ba84b4baa457c3973cea5745ad3be94caa4ce627da732d67e9c8e148979'
map_input = json.loads((ROOT / '_scratch/generated-actual-adapter-native-proposal01/SOURCE-INPUTS.json').read_bytes())
lifecycle_source = Path(map_input['source_paths']['snapshot_lifecycle.py'])
lifecycle_raw = lifecycle_source.read_bytes()
assert hashlib.sha256(lifecycle_raw).hexdigest() == map_input['source_sha256']['snapshot_lifecycle.py']
(OUT / 'snapshot_lifecycle.py').write_bytes(lifecycle_raw)
record = {'candidate_execution': False, 'case_count': 6, 'expected_cases': case_ids,
    'unchanged_fake_definitions': unchanged, 'input_preparation_prefix_unchanged': True,
    'original_eleven_case_source_unchanged': True,
    'fixture_sha256': hashlib.sha256(new_raw).hexdigest(),
    'cases_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(),
    'lifecycle_sha256': hashlib.sha256(lifecycle_raw).hexdigest(),
    'lifecycle_source': str(lifecycle_source)}
(OUT / 'CONNECTION-STATIC.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
