import ast
import difflib
import hashlib
import json
from pathlib import Path
out = Path(__file__).absolute().parent
old = out.parent / 'companion-hub-keyword-diagnostic01'
before = (old / 'qualify.py').read_text(encoding='utf-8')
after = before.replace('diagnostic01', 'diagnostic02')
def contract(raw):
    return ast.dump(next(node for node in ast.parse(raw).body if isinstance(node, ast.ClassDef) and node.name == 'Contracts'), include_attributes=False)
assert contract(before) == contract(after)
for name in ('utils-before.py.txt', 'utils-after.py.txt', 'hub-signature-source.py.txt', 'patch.txt'):
    with (out / name).open('xb') as stream:
        stream.write((old / name).read_bytes())
(out / 'qualify.py').write_text(after, encoding='utf-8', newline='\n')
(out / 'label-only.patch.txt').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='diagnostic01/qualify.py', tofile='diagnostic02/qualify.py')), encoding='utf-8', newline='\n')
rows = []
for path in sorted(out.iterdir()):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({'file': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
(out / 'INPUT-DIAGNOSTIC.json').write_text(json.dumps({'payloads': rows}, indent=2)+'\n', encoding='utf-8', newline='\n')
