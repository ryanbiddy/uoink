"""Data-only source splice and binding; no candidate import or execution."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
OUT = ROOT / '_scratch/worker-bootstrap-owner-migration01'
BASE = ROOT / '_scratch/child-readset-adoption-proposal02/owned_generation_protocol.py'
raw = BASE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '437e0880e10c91555df61b3c07c8be665430098c54c7d6ef687a99a0aa4a79d9'
(OUT / 'before').mkdir()
(OUT / 'before/owned_generation_protocol.py').write_bytes(raw)
source = raw.decode('utf-8')
start = source.index('class WorkerBootstrap:')
end = source.index('class ControllerHandshake:')
replacement = (OUT / 'WorkerBootstrap.proposal.txt').read_text(encoding='utf-8')
new = source[:start] + replacement + '\n\n' + source[end:]
anchor = 'from snapshot_lifecycle import Phase\n'
assert new.count(anchor) == 1
new = new.replace(anchor, anchor + 'from worker_runtime_owner import _WorkerRuntimeOwnerProposal\nfrom owned_factory_port import _OwnedFactoryPortProposal\n')
ast.parse(new)
before_ast = ast.parse(source)
after_ast = ast.parse(new)
def definitions(tree):
    return {n.name: ast.dump(n, include_attributes=False) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
old_defs, new_defs = definitions(before_ast), definitions(after_ast)
assert set(old_defs) == set(new_defs)
assert all(old_defs[name] == new_defs[name] for name in old_defs if name != 'WorkerBootstrap')
new_raw = new.encode('utf-8')
(OUT / 'owned_generation_protocol.py').write_bytes(new_raw)
(OUT / 'owned_generation_protocol.py.diff').write_text(''.join(difflib.unified_diff(
    source.splitlines(keepends=True), new.splitlines(keepends=True),
    fromfile='before/owned_generation_protocol.py', tofile='proposal/owned_generation_protocol.py')), encoding='utf-8', newline='')
pins = {'before_protocol': hashlib.sha256(raw).hexdigest(), 'proposed_protocol': hashlib.sha256(new_raw).hexdigest()}
for name in ('worker_runtime_owner.py', 'model_binding_registry.py', 'owned_factory_port.py', 'owned_guard.py'):
    p = ROOT / '_scratch/worker-runtime-owner-proposal02' / name
    b = p.read_bytes()
    (OUT / name).write_bytes(b)
    pins[name] = hashlib.sha256(b).hexdigest()
record = {'candidate_execution': False, 'all_other_protocol_definitions_AST_identical': True,
          'source_sha256': pins, 'case_execution': 0}
(OUT / 'SOURCE-BINDINGS.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
(OUT / '.gitattributes').write_bytes(b'* -text\n')
print(json.dumps(record))
