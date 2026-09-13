"""Copy exact reviewed B3 inputs for independent synthetic qualification."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / '_scratch/companion-b3-builder01'
raw_seal = (source / 'SHA256.json').read_bytes()
assert hashlib.sha256(raw_seal).hexdigest() == '07e4ac3373142058da95b97568b9a8542b8c42942f8e8f877f00fabc7f97c142'
doc = json.loads(raw_seal)
rows = doc.get('payloads', doc.get('files'))
if isinstance(rows, list):
    rows = {row.get('file', row.get('path')): row for row in rows}
assert len(rows) == 56
qualified_raw = (source / 'QUALIFIED-INPUTS.json').read_bytes()
assert hashlib.sha256(qualified_raw).hexdigest() == rows['QUALIFIED-INPUTS.json']['sha256']
inputs = json.loads(qualified_raw)['payloads']
assert len(inputs) == 24 and len({row['file'] for row in inputs}) == 24
out = root / '_scratch/astra-b3-builder01'
out.mkdir(exist_ok=False)
for row in inputs:
    name = row['file']
    assert rows[name]['sha256'] == row['sha256'] and rows[name]['bytes'] == row['bytes']
    path = (source / name).resolve(strict=True)
    assert path.is_relative_to(source)
    raw = path.read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
(out / 'ROOT-REVIEW.json').write_text(json.dumps({
    'purpose': 'Independent exact 68-case B3 builder qualification',
    'review': 'Root read full builder delta, two inherited expectation changes, six added cases, NOTICE, guard and launcher; prior B2 source/protocol previously reviewed',
    'scope': 'Synthetic ZIPs only; no real wheel, model, runtime or installation',
    'exact_copied_inputs': inputs,
}, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'directory': str(out), 'exact_copied_inputs': len(inputs)}))
