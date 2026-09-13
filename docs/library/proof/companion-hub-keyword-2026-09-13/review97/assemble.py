"""Preserve the complete narrow diagnosis/qualification chain without reruns."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

out = Path(__file__).absolute().parent
scratch = out.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
original = scratch / 'companion-hub-keyword01'
snapshot = scratch / 'companion-hub-keyword-diagnostic01/original-copy-manifest.json'
for row in json.loads(snapshot.read_text(encoding='utf-8'))['payloads']:
    raw = (original / row['file']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']

copies = []
for name, directory in [('original', original), ('diagnostic01', scratch / 'companion-hub-keyword-diagnostic01'),
                        ('diagnostic02', scratch / 'companion-hub-keyword-diagnostic02'),
                        ('qualification', scratch / 'companion-hub-keyword-qualified01')]:
    for source in sorted(directory.rglob('*')):
        if not source.is_file():
            continue
        raw = source.read_bytes()
        target = out / name / source.relative_to(directory)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
        copies.append({'source': str(source), 'target': str(target.relative_to(out)).replace('\\', '/'), 'bytes': len(raw), 'sha256': sha(raw)})

classes = []
for name in ['original', 'diagnostic01', 'diagnostic02', 'qualification']:
    text = (out / name / 'qualify.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'Contracts')
    classes.append({'source': name + '/qualify.py', 'class_ast_sha256': sha(ast.dump(node, include_attributes=False).encode()),
                    'class_source_sha256_normalized_lf': sha(ast.get_source_segment(text, node).encode())})
assert len({row['class_ast_sha256'] for row in classes}) == 1
assert len({row['class_source_sha256_normalized_lf'] for row in classes}) == 1

summary = []
for prefix, label, valid, passed, errors in [('original', 'baseline01', False, 4, 4), ('original', 'baseline02', False, 4, 4),
    ('diagnostic01', 'diagnostic01', True, 4, 4), ('diagnostic02', 'diagnostic02', False, 4, 4),
    ('qualification', 'baseline03', True, 4, 4), ('qualification', 'patched03', True, 8, 0)]:
    root = out / prefix
    receipt = json.loads((root / label / 'result.json').read_text(encoding='utf-8'))
    assert (receipt['tests_run'], receipt['passed'], receipt['errors'], receipt['failures'], receipt['skipped'], receipt['guard_valid']) == (8, passed, errors, 0, 0, valid)
    if prefix == 'original':
        outer = json.loads((root / label / 'outer-exit.json').read_text(encoding='utf-8'))['actual_outer_exit']
        child = receipt['exit']
    else:
        actual = json.loads((root / ('launch-' + label) / 'result.json').read_text(encoding='utf-8'))
        child, outer = actual['actual_child_exit'], actual['actual_outer_exit']
    expected_exit = 0 if label == 'patched03' else 1
    assert child == outer == receipt['exit'] == expected_exit
    log = (root / label / 'tests.log').read_text(encoding='utf-8')
    ids = re.findall(r'^(test_\w+) \(__main__\.Contracts\.(test_\w+)\)', log, flags=re.M)
    assert len(ids) == 8 and all(left == right for left, right in ids)
    summary.append({'attempt': prefix + '/' + label, 'passed': passed, 'errors': errors, 'failures': 0, 'skipped': 0,
                    'guard_valid': valid, 'actual_child_exit': child, 'actual_outer_exit': outer, 'case_ids': [left for left, _ in ids]})
assert all(row['case_ids'] == summary[0]['case_ids'] for row in summary)
baseline = (out / 'qualification/baseline03/tests.log').read_text(encoding='utf-8')
assert baseline.count("TypeError: got an unexpected keyword argument 'local_dir_use_symlinks'") == 4
before = (out / 'qualification/utils-before.py.txt').read_bytes()
after = (out / 'qualification/utils-after.py.txt').read_bytes()
line = b'        kwargs["local_dir_use_symlinks"] = False\n'
assert before.count(line) == 1 and before.replace(line, b'') == after

(out / 'VERIFICATION.json').write_text(json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'original18_unchanged': True,
    'contract_classes': classes, 'attempts': summary, 'exact_removed_line_bytes': len(line), 'proposed_source_sha256': sha(after),
    'prior_python313_preparation_sha256': sha((scratch / 'b2-python313-reproduction-preparation01/SHA256.json').read_bytes()),
    'no_additional_execution_during_assembly': True}, indent=2)+'\n', encoding='utf-8', newline='\n')
(out / 'COPY-RECEIPT.json').write_text(json.dumps({'payloads': copies}, indent=2)+'\n', encoding='utf-8', newline='\n')
rows = []
for path in sorted(out.rglob('*')):
    if path.is_file() and path != out / 'SHA256.json':
        raw = path.read_bytes()
        rows.append({'file': str(path.relative_to(out)).replace('\\', '/'), 'bytes': len(raw), 'sha256': sha(raw)})
raw = (json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'payload_count': len(rows), 'payloads': rows}, indent=2)+'\n').encode()
with (out / 'SHA256.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(rows), 'manifest_sha256': sha(raw), 'original_unchanged': True, 'contracts_identical': True}))
