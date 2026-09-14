"""Transform reviewed text instruments only; never import candidate source."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
OLD = ROOT / '_scratch/worker-runtime-owner-instrument01'
OWNER = ROOT / '_scratch/worker-runtime-owner-proposal02'
MIGRATION = ROOT / '_scratch/worker-bootstrap-owner-migration01'
OUT = ROOT / '_scratch/worker-bootstrap-owner-instrument01'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def js(path, value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value, indent=2) + '\n').encode())
def delta(name, old, new):
    (OUT / (name + '.diff')).write_text(''.join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile='before/' + name, tofile='proposal/' + name)), encoding='utf-8', newline='')

guard_raw = (OLD / 'qualify_owner.py').read_bytes()
launcher_raw = (OLD / 'run_owner01.ps1').read_bytes()
assert sha(guard_raw) == 'e08653d576dd3ca8367efde9e9438f485de5835f3831e0f7a1f8571fefa6acc1'
assert sha(launcher_raw) == '36d3b09eeec3f2d69b1b6b16019fd52ed2dd6e27189e64b431499971035a21be'
(OUT / 'before').mkdir()
(OUT / 'before/qualify_owner.py').write_bytes(guard_raw)
(OUT / 'before/run_owner01.ps1').write_bytes(launcher_raw)
old_map = json.loads((OLD / 'SOURCE-INPUTS.json').read_bytes())
sources = {name: row for name, row in old_map['sources'].items() if name not in ('qualify_owner.py', 'EXPECTED-CASES.json')}
additions = {
    'snapshot_lifecycle.py': 'a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd',
    'owned_generation_protocol.py': '0a56116d51e50f881f6366f17628bb99ec4f400cb680814a37f9d1d66da263ba',
    'generated_bootstrap_fixture.py': '6ea5e4e7cebff54380193b1ad0cc1b1cf08e4a7f34a8162d2f0f6ce73371d469',
    'connection_cases.py': '2e598f26c7edd2e60b06495a62a350411ceb0a60ed6fd3486c1a1294d04cbea6',
}
for name, expected in additions.items():
    source = MIGRATION / name
    assert sha(source.read_bytes()) == expected
    sources[name] = {'path': str(source), 'sha256': expected}
for row in sources.values():
    assert sha(Path(row['path']).read_bytes()) == row['sha256']
original_cases = json.loads((OLD / 'EXPECTED-CASES.json').read_bytes())['ordered_cases']
connection_tree = ast.parse((MIGRATION / 'connection_cases.py').read_bytes())
connection_cases = ast.literal_eval(next(node.value for node in connection_tree.body
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'EXPECTED_CASES' for t in node.targets)))
cases = tuple(original_cases) + connection_cases
assert len(original_cases) == 11 and len(connection_cases) == 6 and len(set(cases)) == 17
js(OUT / 'EXPECTED-CASES.json', {'schema': 'uoink.worker-bootstrap-expected-cases.v1', 'count': 17, 'ordered_cases': cases})
expected_sha = sha((OUT / 'EXPECTED-CASES.json').read_bytes())
modules = tuple(name[:-3] for name in sources)
assert modules.index('snapshot_lifecycle') < modules.index('owned_generation_protocol') < modules.index('generated_bootstrap_fixture') < modules.index('connection_cases')
assert modules.index('worker_runtime_owner') < modules.index('owned_generation_protocol')
input_names = tuple(sources) + ('qualify_owner.py', 'EXPECTED-CASES.json')
assert len(input_names) == 17
pins = {name: row['sha256'] for name, row in sources.items()}
pins['EXPECTED-CASES.json'] = expected_sha
guard = guard_raw.decode()
lines = guard.splitlines(keepends=True)
for prefix, value in (
    ('INPUTS = ', repr(input_names)),
    ('ALLOWED_IMPORTS = ', 'set(sys.modules) | set(' + repr(modules) + ')'),
    ('SOURCE_PINS = ', repr(pins)),
    ('EXPECTED_CASES = ', repr(cases)),
    ('MODULES = ', repr(modules)),
):
    matched = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    assert len(matched) == 1
    lines[matched[0]] = prefix + value + '\n'
guard = ''.join(lines)
guard = guard.replace('"uoink.runtime-owner-expected-cases.v1", "count": 11',
                      '"uoink.worker-bootstrap-expected-cases.v1", "count": 17')
start = guard.index("assert guard_module._RUNTIME is None and fixture_module.Model is object\n")
end = guard.index('CLASSES = ', start)
guard = guard[:start] + '''protocol_module = sys.modules['owned_generation_protocol']
bootstrap_fixture_module = sys.modules['generated_bootstrap_fixture']
connection_module = sys.modules['connection_cases']
assert guard_module._RUNTIME is None and fixture_module.Model is object and bootstrap_fixture_module.Model is object
CASE_GROUPS = ((case_module, case_module.OwnerContracts, EXPECTED_CASES[:11]),
               (connection_module, connection_module.BootstrapContracts, EXPECTED_CASES[11:]))
CASE_CLASSES = {}
for module, case_class, expected_group in CASE_GROUPS:
    assert tuple(module.EXPECTED_CASES) == expected_group
    prefix = module.__name__ + '.' + case_class.__name__ + '.'
    assert tuple(prefix + name for name in vars(case_class) if name.startswith('test_')) == expected_group
    assert not any(name in vars(case_class) for name in ('setUp', 'tearDown', 'setUpClass', 'tearDownClass'))
    for name in expected_group:
        CASE_CLASSES[name] = case_class
assert tuple(CASE_CLASSES) == EXPECTED_CASES
''' + guard[end:]
guard = guard.replace('           owner_module._WorkerRuntimeOwnerProposal)',
    '           owner_module._WorkerRuntimeOwnerProposal, protocol_module.GenerationChannel,\n'
    '           protocol_module.WorkerBootstrap, protocol_module.ControllerHandshake, protocol_module.GenerationBinding)')
guard = guard.replace("    (owner_module, 'open_real_runtime_owner')))",
    "    (owner_module, 'open_real_runtime_owner'), (protocol_module, 'activate_real_worker')))")
guard = guard.replace("        case = case_class(name.rsplit('.', 1)[1])", "        case = CASE_CLASSES[name](name.rsplit('.', 1)[1])")
guard = guard.replace('owner_binding_valid = (guard_module._RUNTIME is None and fixture_module.Model is object\n                       and guard_module.require_owned_runtime is ORIGINAL_REQUIRE)',
    'owner_binding_valid = (guard_module._RUNTIME is None and fixture_module.Model is object\n'
    '                       and bootstrap_fixture_module.Model is object\n'
    '                       and fixture_module.require_owned_runtime is ORIGINAL_REQUIRE\n'
    '                       and bootstrap_fixture_module.require_owned_runtime is ORIGINAL_REQUIRE\n'
    '                       and guard_module.require_owned_runtime is ORIGINAL_REQUIRE)')
guard = guard.replace('"uoink.runtime-owner-synthetic.v1"', '"uoink.worker-bootstrap-synthetic.v1"')
guard = guard.replace('Generated fake factory/tensor/ownership only; no kernel, model, decoder, filters or real-loader qualification',
    'Eleven generated owner and six actual-bootstrap cases; no kernel, model, decoder, filters or real-loader qualification')
ast.parse(guard)
# The preload block, audit implementation, metadata traps and read bounds do not change.
old_tree, new_tree = ast.parse(guard_raw), ast.parse(guard)
for name in ('deny_registry', 'registry_audit', 'audit', 'deny_metadata', 'BoundedCapture'):
    find = lambda tree: next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    assert ast.dump(find(old_tree), include_attributes=False) == ast.dump(find(new_tree), include_attributes=False)
assert guard_raw.decode().split('assert sys.flags.isolated')[0] == guard.split('assert sys.flags.isolated')[0]
(OUT / 'qualify_owner.py').write_bytes(guard.encode())
sources['qualify_owner.py'] = {'path': str(OUT / 'qualify_owner.py'), 'sha256': sha(guard.encode())}
sources['EXPECTED-CASES.json'] = {'path': str(OUT / 'EXPECTED-CASES.json'), 'sha256': expected_sha}
js(OUT / 'SOURCE-INPUTS.json', {'scope': 'worker-bootstrap-generated-17-only', 'sources': sources})
delta('qualify_owner.py', guard_raw.decode(), guard)

launcher = launcher_raw.decode()
launcher = launcher.replace(str(OLD), str(OUT)).replace('runs\\rto01', 'runs\\wbo01')
launcher = launcher.replace("'rto01'", "'wbo01'").replace('runtime-owner-generated-11-only', 'worker-bootstrap-generated-17-only')
start = launcher.index('$taskExpected=@{\n')
end = launcher.index('$taskInputNames=', start)
expected_block = '$taskExpected=@{\n' + ''.join("    '" + name + "'='" + row['sha256'] + "'\n" for name, row in sources.items()) + '}\n'
source_block = '$taskSourcePaths=@{\n' + ''.join("    '" + name + "'='" + row['path'] + "'\n" for name, row in sources.items()) + '}\n'
launcher = launcher[:start] + expected_block + source_block + launcher[end:]
outer_names = tuple(sources) + ('SOURCE-INPUTS.json', 'run_bootstrap01.ps1')
old_input_line = next(line for line in launcher.splitlines() if line.startswith('$taskInputNames='))
launcher = launcher.replace(old_input_line, '$taskInputNames=@(' + ','.join("'" + name + "'" for name in outer_names) + ')')
for old, new in (('-ne 11', '-ne 17'), ('-lt 11', '-lt 17'), ('-eq 11', '-eq 17'),
                 ('uoink.runtime-owner-expected-cases.v1', 'uoink.worker-bootstrap-expected-cases.v1'),
                 ('uoink.runtime-owner-synthetic.v1', 'uoink.worker-bootstrap-synthetic.v1'),
                 ('11 generated fake factory and owner cases only', '11 owner plus 6 actual bootstrap generated cases only')):
    launcher = launcher.replace(old, new)
block_start, block_end = '# BEGIN EXACT NATIVE RECEIPT BLOCK', '# END EXACT NATIVE RECEIPT BLOCK'
def block(text): return text[text.index(block_start):text.index(block_end) + len(block_end)]
assert block(launcher) == block(launcher_raw.decode())
assert len(sources) == 17 and len(outer_names) == 19
(OUT / 'run_bootstrap01.ps1').write_bytes(launcher.encode())
delta('run_bootstrap01.ps1', launcher_raw.decode(), launcher)
admission_pins = {name: row['sha256'] for name, row in sources.items()}
admission_pins['SOURCE-INPUTS.json'] = sha((OUT / 'SOURCE-INPUTS.json').read_bytes())
admission_pins['run_bootstrap01.ps1'] = sha(launcher.encode())
js(OUT / 'ROOT-ADMISSION.template.json', {'root_reviewed': False,
    'scope': 'worker-bootstrap-generated-17-only', 'label': 'wbo01',
    'input_sha256': admission_pins, 'expected_cases': cases,
    'notice': 'Preparation only. Seventeen generated cases; no native/real runtime or model authority. Root and peer review precede any actual admission.'})
for name, row in sources.items():
    assert sha(Path(row['path']).read_bytes()) == row['sha256']
report = {'candidate_execution': False, 'child_inputs': 17, 'outer_input_pins': 19,
    'case_groups': [11, 6], 'original_eleven_assertions_unchanged': True,
    'six_connection_assertions_unchanged': True, 'stdlib_preloads_unchanged': True,
    'metadata_registry_audit_bodies_unchanged': True, 'native_receipt_block_unchanged': True,
    'qualifier_sha256': sha(guard.encode()), 'launcher_sha256': sha(launcher.encode()),
    'map_sha256': admission_pins['SOURCE-INPUTS.json'],
    'expected_sha256': expected_sha, 'admission_template_sha256': sha((OUT / 'ROOT-ADMISSION.template.json').read_bytes())}
js(OUT / 'PREPARATION-RESULT.json', report)
(OUT / '.gitattributes').write_bytes(b'* -text\n')
print(json.dumps(report))
