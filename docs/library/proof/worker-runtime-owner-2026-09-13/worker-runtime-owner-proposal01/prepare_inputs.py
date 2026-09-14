"""Data-only fixed input copying/fixture extraction; no candidate execution."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path('E:/AI/projects/uoink/checkouts/Yoink-library')
OUT = ROOT / '_scratch/worker-runtime-owner-proposal01'
BASE = ROOT / '_scratch/vad-owned-factory-port-proposal01'
COPIES = {
    'plain_state_reader.py': BASE / 'context/plain_state_reader.py',
    'state_bridge.py': BASE / 'context/state_bridge.py',
    'owned_cpu_tensor_port.py': BASE / 'context/owned_cpu_tensor_port.py',
    'model_binding_registry.py': BASE / 'model_binding_registry.py',
    'owned_factory_port.py': BASE / 'owned_factory_port.py',
    'owned_guard.py': BASE / 'context/owned_guard.py',
    'fake_torch_support.py': BASE / 'factory-preflight01/fake_torch_support.py',
    'fixed-factory.proposal.txt': BASE / 'context/fixed-factory.proposal.txt',
    'original-qualify_factory.py': BASE / 'qualify_factory.py',
}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path):
    with path.open('rb') as stream:
        raw = stream.read(200_001)
    assert len(raw) <= 200_000
    return raw

def write(name, text):
    raw = text.encode('utf-8')
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return raw

def section(source, name):
    tree = ast.parse(source)
    node = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name)
    start = min([node.lineno, *(entry.lineno for entry in node.decorator_list)])
    return '\n'.join(source.splitlines()[start - 1:node.end_lineno]) + '\n'

def replace_once(source, before, after):
    assert source.count(before) == 1, before
    return source.replace(before, after, 1)

def main():
    bindings = []
    copied = {}
    for name, source in COPIES.items():
        raw = read(source)
        with (OUT / name).open('xb') as stream:
            stream.write(raw)
        copied[name] = raw
        bindings.append({'path': name, 'source': str(source), 'bytes': len(raw), 'sha256': digest(raw)})
    original = copied['original-qualify_factory.py'].decode('utf-8-sig')
    fixed = copied['fixed-factory.proposal.txt'].decode('utf-8-sig')
    code = fixed.split('----- BEGIN PROPOSED PYTHON (TEXT ONLY) -----', 1)[1].split('----- END PROPOSED PYTHON -----', 1)[0]
    helpers = '\n\n'.join(section(code, name) for name in ('_fixed_shapes', '_check_plain_state'))
    # Exact original body ASTs; formatting and removal of unrelated source only.
    for name in ('_fixed_shapes', '_check_plain_state'):
        before = ast.parse(section(code, name)).body[0]
        after = ast.parse(section(helpers, name)).body[0]
        assert ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False)
    write('fixed_schema_helpers.py', '"""Exact fixed-factory schema helpers; fake globals supplied only by reviewed fixture."""\n' + helpers)

    prefix = '''"""Adapted retained inert factory fixture; actual factory method, no native model."""
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import math
import struct
import types
import state_bridge as bridge
import owned_cpu_tensor_port as cpu
import model_binding_registry as registry_module
import owned_factory_port as factory_module
import owned_guard as guard
import fake_torch_support as support
import fixed_schema_helpers as helpers
from worker_runtime_owner import _WorkerRuntimeOwnerProposal as Registry

Factory = factory_module._OwnedFactoryPortProposal
Binding = registry_module._StateBindingProposal
PATTERN = struct.pack('<12I', 0, 0x80000000, 1, 0x80000001,
    0x007fffff, 0x807fffff, 0x00800000, 0x80800000,
    0x7f7fffff, 0xff7fffff, 0x3f800000, 0xbf800000)
Model = object
require_owned_runtime = guard.require_owned_runtime
'''
    selected = '\n\n'.join(section(original, name) for name in ('pattern', 'FakeVoiceParent', 'FakeVoiceActivitySegmentation'))
    fixture = section(original, 'fixture')
    fixture = replace_once(fixture, "    exec(HELPER_CODE, fixed.__dict__)  # Only the two pinned own-source helpers.",
        "    for helper in (helpers._fixed_shapes, helpers._check_plain_state):\n"
        "        fixed.__dict__[helper.__name__] = types.FunctionType(helper.__code__, fixed.__dict__, helper.__name__)")
    old = '''    factory = Factory(fixed, tensor_port, guard)
    capability = registry._issue_for_bootstrap(bootstrap, factory, binding, registry_module.FIXED_RECIPE_SHA256)
    factory._bind_model_capability(capability)
    value = types.SimpleNamespace(runtime=runtime, fixed=fixed, port=tensor_port, state=state,
                                  binding=binding, bootstrap=bootstrap, registry=registry,
                                  factory=factory, capability=capability)
    try:
        yield value'''
    new = '''    factory = None
    try:
        with registry.operation(bootstrap, 'issue'):
            namespace = registry.issue_generated_namespace(bootstrap, (b'config', b'generated text', b'preprocessor', b'tokens', b'vocabulary'))
            media = object()
            pcm = registry.issue_generated_pcm(bootstrap, media, struct.pack('<4f', 0.0, 0.25, -0.25, 0.0))
        with registry.operation(bootstrap, 'factory'):
            factory = Factory(fixed, tensor_port, guard)
            capability = registry._issue_for_bootstrap(bootstrap, factory, binding, registry_module.FIXED_RECIPE_SHA256)
            factory._bind_model_capability(capability)
            product = factory.build_strict_owned(state)
            registry.register_vad_product_for_bootstrap(bootstrap, factory, product, guard)
        value = types.SimpleNamespace(runtime=runtime, fixed=fixed, port=tensor_port, state=state,
                                      binding=binding, bootstrap=bootstrap, registry=registry,
                                      factory=factory, capability=capability, product=product,
                                      namespace=namespace, pcm=pcm, media=media)
        yield value'''
    fixture = replace_once(fixture, old, new)
    fixture = replace_once(fixture, '        if factory._completed is not None:', '        if factory is not None and factory._completed is not None:')
    fixture = replace_once(fixture, '        if factory._quarantined_owner is not None:', '        if factory is not None and factory._quarantined_owner is not None:')
    write('generated_factory_fixture.py', prefix + '\n\n' + selected + '\n\n' + fixture)
    # Record exact selected fake constructor/helper parity without executing it.
    checks = {}
    for name in ('pattern', 'FakeVoiceParent', 'FakeVoiceActivitySegmentation'):
        checks[name] = ast.dump(ast.parse(section(original, name)), include_attributes=False) == ast.dump(
            ast.parse(section(selected, name)), include_attributes=False)
    assert all(checks.values())
    write('INPUT-COPY-MAP.json', json.dumps({'scope': 'source-preparation-only', 'copies': bindings,
        'unchanged_selected_ast': checks, 'candidate_execution': False}, indent=2) + '\n')
    print(json.dumps({'copied_inputs': len(bindings), 'selected_ast_unchanged': checks,
                      'candidate_execution': False}))

if __name__ == '__main__':
    main()
