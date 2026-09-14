"""Fixed text transformation only. Does not import/run the qualifier or cases."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path('E:/AI/projects/uoink/checkouts/Yoink-library')
HERE = ROOT / '_scratch/worker-runtime-owner-instrument01'
PROPOSAL = ROOT / '_scratch/worker-runtime-owner-proposal02'
MODULES = ('plain_state_reader', 'state_bridge', 'owned_cpu_tensor_port', 'model_binding_registry',
           'owned_factory_port', 'owned_guard', 'fake_torch_support', 'fixed_schema_helpers',
           'worker_runtime_owner', 'generated_factory_fixture', 'generated_unit_cases')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write(name, value):
    raw = value if type(value) is bytes else value.encode('utf-8')
    with (HERE / name).open('xb') as stream:
        stream.write(raw)
    return sha(raw)

def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)

def main():
    case_tree = ast.parse((PROPOSAL / 'generated_unit_cases.py').read_text(encoding='utf-8'))
    cases = ast.literal_eval(next(n.value for n in case_tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'EXPECTED_CASES' for t in n.targets)))
    assert len(cases) == 11
    expected = {'schema': 'uoink.runtime-owner-expected-cases.v1', 'count': 11, 'ordered_cases': cases}
    expected_hash = write('EXPECTED-CASES.json', json.dumps(expected, indent=2) + '\n')
    pins = {name + '.py': sha((PROPOSAL / (name + '.py')).read_bytes()) for name in MODULES}
    pins['EXPECTED-CASES.json'] = expected_hash
    original = (HERE / 'before/qualify_namespace.py').read_text(encoding='utf-8')
    prefix = original[:original.index("for module_name in ('snapshot_lifecycle'")]
    prefix = replace(prefix, 'import dataclasses\n',
        'import dataclasses\nimport unittest\nimport collections\nimport copy\nimport weakref\nimport typing\nimport re\nimport encodings.utf_8_sig\n')
    start = prefix.index('INPUTS = '); end = prefix.index('\nREADS = ', start)
    inputs = tuple(name + '.py' for name in MODULES) + ('qualify_owner.py', 'EXPECTED-CASES.json')
    prefix = prefix[:start] + 'INPUTS = ' + repr(inputs) + prefix[end:]
    start = prefix.index('ALLOWED_IMPORTS = '); end = prefix.index('\nDENIALS = ', start)
    prefix = prefix[:start] + 'ALLOWED_IMPORTS = set(sys.modules) | set(' + repr(MODULES) + ')' + prefix[end:]
    prefix = replace(prefix, 'HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}\n',
        'HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}\n'
        + 'SOURCE_PINS = ' + repr(pins) + '\n'
        + 'assert all(HASHES[name] == expected for name, expected in SOURCE_PINS.items())\n'
        + 'EXPECTED_CASES = ' + repr(cases) + '\n'
        + 'expected_file = json.loads(RAW["EXPECTED-CASES.json"].decode("utf-8"))\n'
        + 'assert expected_file == {"schema": "uoink.runtime-owner-expected-cases.v1", "count": 11, "ordered_cases": list(EXPECTED_CASES)}\n')
    body = '''
for module_name in MODULES:
    module = types.ModuleType(module_name)
    module.__file__ = os.path.join(HERE, module_name + '.py')
    sys.modules[module_name] = module
    exec(compile(RAW[module_name + '.py'], module.__file__, 'exec'), module.__dict__)

registry_module = sys.modules['model_binding_registry']
factory_module = sys.modules['owned_factory_port']
cpu_module = sys.modules['owned_cpu_tensor_port']
bridge_module = sys.modules['state_bridge']
owner_module = sys.modules['worker_runtime_owner']
guard_module = sys.modules['owned_guard']
fixture_module = sys.modules['generated_factory_fixture']
case_module = sys.modules['generated_unit_cases']
assert guard_module._RUNTIME is None and fixture_module.Model is object
assert tuple(case_module.EXPECTED_CASES) == EXPECTED_CASES
case_class = case_module.OwnerContracts
assert tuple('generated_unit_cases.OwnerContracts.' + name for name in vars(case_class) if name.startswith('test_')) == EXPECTED_CASES
assert not any(name in vars(case_class) for name in ('setUp', 'tearDown', 'setUpClass', 'tearDownClass'))
CLASSES = (registry_module._WorkerModelRegistryProposal, registry_module._FactoryModelCapability,
           registry_module._ModelRegistrationLease, factory_module._OwnedFactoryPortProposal,
           factory_module._FactoryOwner, cpu_module._OwnedCPUTorchPortProposal,
           owner_module._WorkerRuntimeOwnerProposal)
METHODS = tuple((cls, name, value) for cls in CLASSES for name, value in vars(cls).items()
                if callable(value) or isinstance(value, (property, staticmethod, classmethod)))
CLOSED = tuple((module, name, getattr(module, name)) for module, name in (
    (registry_module, 'open_real_model_registry'), (factory_module, 'open_real_factory_port'),
    (cpu_module, 'open_real_tensor_port'), (bridge_module, 'build_real_vad'),
    (owner_module, 'open_real_runtime_owner')))
ORIGINAL_REQUIRE = guard_module.require_owned_runtime
results = []
started = time.perf_counter()
for name in EXPECTED_CASES:
    try:
        case = case_class(name.rsplit('.', 1)[1])
        getattr(case, name.rsplit('.', 1)[1])()
        results.append({"name": name, "passed": True})
    except BaseException as exc:
        results.append({"name": name, "passed": False, "exception": type(exc).__name__, "message": str(exc)[:512]})
'''
    suffix = original[original.index('elapsed = time.perf_counter() - started'):]
    suffix = replace(suffix, 'valid = (not DENIALS',
        'methods_unchanged = all(vars(cls).get(name) is value for cls, name, value in METHODS)\n'
        'closed_entries_unchanged = all(getattr(module, name, None) is value for module, name, value in CLOSED)\n'
        'owner_binding_valid = (guard_module._RUNTIME is None and fixture_module.Model is object\n'
        '                       and guard_module.require_owned_runtime is ORIGINAL_REQUIRE)\n'
        'valid = (methods_unchanged and closed_entries_unchanged and owner_binding_valid and not DENIALS')
    suffix = replace(suffix, '"schema": "uoink.worker-namespace-synthetic.v1"', '"schema": "uoink.runtime-owner-synthetic.v1"')
    suffix = replace(suffix, '"guard_valid": valid,',
        '"methods_unchanged": methods_unchanged, "closed_entries_unchanged": closed_entries_unchanged,\n'
        '                  "owner_binding_valid": owner_binding_valid, "guard_valid": valid,')
    suffix = replace(suffix, 'Generated-memory fake API seams only; no kernel, model, factory or native-loader qualification',
        'Generated fake factory/tensor/ownership only; no kernel, model, decoder, filters or real-loader qualification')
    qualifier = prefix + 'MODULES = ' + repr(MODULES) + '\n' + body + '\n' + suffix
    ast.parse(qualifier)
    qualifier_hash = write('qualify_owner.py', qualifier)
    mapping = {'scope': 'runtime-owner-generated-11-only', 'sources': {
        name: {'path': str(PROPOSAL / name), 'sha256': value} for name, value in pins.items() if name.endswith('.py')}}
    mapping['sources']['qualify_owner.py'] = {'path': str(HERE / 'qualify_owner.py'), 'sha256': qualifier_hash}
    mapping['sources']['EXPECTED-CASES.json'] = {'path': str(HERE / 'EXPECTED-CASES.json'), 'sha256': expected_hash}
    map_hash = write('SOURCE-INPUTS.json', json.dumps(mapping, indent=2) + '\n')
    write('qualify_owner.py.diff', ''.join(difflib.unified_diff(original.splitlines(True), qualifier.splitlines(True),
          fromfile='before/qualify_namespace.py', tofile='qualify_owner.py')))
    write('GUARD-PREPARATION.json', json.dumps({'candidate_execution': False, 'expected_cases': len(cases),
        'qualifier_sha256': qualifier_hash, 'source_map_sha256': map_hash,
        'expected_cases_sha256': expected_hash, 'original_guard_sha256': sha((HERE/'before/qualify_namespace.py').read_bytes())}, indent=2) + '\n')
    print(json.dumps({'qualifier_sha256': qualifier_hash, 'source_map_sha256': map_hash, 'candidate_execution': False}))

if __name__ == '__main__':
    main()
