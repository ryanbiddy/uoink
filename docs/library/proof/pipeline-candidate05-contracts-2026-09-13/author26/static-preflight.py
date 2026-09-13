"""Parse and bind code without executing captured methods or fake test bodies."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
out = Path(__file__).absolute().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
bindings = json.loads((out / 'SOURCE-BINDINGS.json').read_text(encoding='utf-8'))
trees, files, cases = {}, [], []
for row in bindings['bindings']:
    raw = (out / 'inputs' / row['file']).read_bytes()
    assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
    trees[row['file']] = ast.parse(raw)
for row in bindings['selected_bodies']:
    parent = trees[row['file']]
    if row['class'] is not None:
        parent = next(node for node in parent.body if isinstance(node, ast.ClassDef) and node.name == row['class'])
    method = next(node for node in parent.body if isinstance(node, ast.FunctionDef) and node.name == row['method'])
    assert sha(ast.dump(ast.Module(body=method.body, type_ignores=[]), include_attributes=False).encode()) == row['body_ast_sha256']
for name in ('seams.py', 'tests.py', 'run.py', 'launch.py', 'static-preflight.py', 'prepare.py'):
    raw = (out / name).read_bytes()
    tree = ast.parse(raw)
    compile(tree, str(out / name), 'exec')
    files.append({'file': name, 'bytes': len(raw), 'sha256': sha(raw)})
    if name == 'tests.py':
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef) and cls.name.endswith('Contracts'):
                for method in cls.body:
                    if isinstance(method, ast.FunctionDef) and method.name.startswith('test_'):
                        cases.append({'id': 'synthetic_pipeline_contracts.' + cls.name + '.' + method.name,
                            'body_ast_sha256': sha(ast.dump(ast.Module(body=method.body, type_ignores=[]), include_attributes=False).encode())})
assert len(cases) == 23 and len({case['id'] for case in cases}) == 23
assert len(bindings['selected_bodies']) == 19
receipt = {'created_utc': datetime.now(timezone.utc).isoformat(), 'source_count': 3, 'selected_bodies': 19,
    'captured_pipeline_initializer': 'Defined unchanged with signature annotations removed; profile guard prohibits body execution.',
    'captured_bodies_executed': False, 'synthetic_bodies_executed': False, 'cases': cases, 'inputs': files,
    'source_review': 'Selected method bodies, scoped fakes, 23 assertions, source-free formatter, profile/file/import/network guards and launcher read before first execution.',
    'empty_list': 'Separate diagnostic; no accepted pass credit.',
    'fake_limits': 'No real tensor, loader workers, model, feature extractor, tokenizer, device, full module or package execution.'}
(out / 'PREQUALIFICATION.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8', newline='\n')
print(json.dumps({'source_count': 3, 'selected_bodies': 19, 'contracts': 23, 'captured_bodies_executed': False, 'inputs': files[:4]}))
