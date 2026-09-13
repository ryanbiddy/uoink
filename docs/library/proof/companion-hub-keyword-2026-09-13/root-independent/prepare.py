import ast
import difflib
import hashlib
import json
from pathlib import Path
out = Path(__file__).absolute().parent
old = out.parent / 'companion-hub-keyword-diagnostic02'
before = (old / 'qualify.py').read_text(encoding='utf-8')
after = before.replace("('diagnostic02', 'unused-patched')", "('baseline03', 'patched03')").replace("label == 'diagnostic02'", "label == 'baseline03'").replace("'INPUT-DIAGNOSTIC.json'", "'INPUT-QUALIFICATION.json'")
marker = "with (run / 'tests.log').open('x', encoding='utf-8') as stream:"
formatter = '''class SourceFreeResult(unittest.TextTestResult):
    def _exc_info_to_string(self, err, test):
        kind, value, frame = err
        lines = ['Traceback (frame locations; source lookup disabled):']
        while frame is not None:
            code = frame.tb_frame.f_code
            lines.append(f'  File {code.co_filename!r}, line {frame.tb_lineno}, in {code.co_name}')
            frame = frame.tb_next
        lines.append(f'{kind.__name__}: {value}')
        return '\\n'.join(lines) + '\\n'

'''
assert after.count(marker) == 1
after = after.replace(marker, formatter + marker)
assert after.count('unittest.TextTestRunner(stream=stream, verbosity=2)') == 1
after = after.replace('unittest.TextTestRunner(stream=stream, verbosity=2)', 'unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=SourceFreeResult)')
def contract(raw):
    return ast.dump(next(n for n in ast.parse(raw).body if isinstance(n, ast.ClassDef) and n.name == 'Contracts'), include_attributes=False)
assert contract(before) == contract(after)
assert contract(after) == contract((out.parent / 'companion-hub-keyword01/qualify.py').read_text(encoding='utf-8'))
for name in ('utils-before.py.txt', 'utils-after.py.txt', 'hub-signature-source.py.txt', 'patch.txt'):
    with (out / name).open('xb') as stream:
        stream.write((old / name).read_bytes())
(out / 'qualify.py').write_text(after, encoding='utf-8', newline='\n')
(out / 'formatter-repair.patch.txt').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='diagnostic02/qualify.py', tofile='qualified/qualify.py')), encoding='utf-8', newline='\n')
(out / 'assertion-preservation.json').write_text(json.dumps({'contracts_class_ast_unchanged_from_original': True, 'contracts_ast_sha256': hashlib.sha256(contract(after).encode()).hexdigest(), 'test_method_names': [n.name for n in next(n for n in ast.parse(after).body if isinstance(n, ast.ClassDef) and n.name == 'Contracts').body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]}, indent=2)+'\n', encoding='utf-8', newline='\n')
rows = []
for path in sorted(out.iterdir()):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({'file': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
(out / 'INPUT-QUALIFICATION.json').write_text(json.dumps({'payloads': rows}, indent=2)+'\n', encoding='utf-8', newline='\n')
