"""Copy exact reviewed builder inputs for independent synthetic qualification."""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / '_scratch/companion-b2-builder01'
manifest = (source / 'SHA256.json').read_bytes()
assert hashlib.sha256(manifest).hexdigest() == 'ac31912d51a4a6b38c8e028e65bd005e9fedcd7125d51f219ca51973b834fc8f'
document = json.loads(manifest)
rows = document.get('files', document.get('payloads'))
if isinstance(rows, list):
    rows = {row.get('path', row.get('file')): row for row in rows}
assert len(rows) == 63
names = ['build_faster_whisper_localassets_wheel.py', 'tests-synthetic.py', 'run-synthetic.py', 'launch.py', 'BRIEF.md', 'REPAIR-BEFORE-BW03.md']
names += [name for name in rows if name.startswith(('recipe/', 'fixtures/'))]
out = root / '_scratch/astra-b2-builder01'
out.mkdir(exist_ok=False)
copied = {}
for name in names:
    path = (source / name).resolve(strict=True)
    assert path.is_relative_to(source)
    raw = path.read_bytes()
    assert len(raw) == rows[name]['bytes'] and hashlib.sha256(raw).hexdigest() == rows[name]['sha256']
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    copied[name] = rows[name]
assert copied['build_faster_whisper_localassets_wheel.py']['sha256'] == 'ef7189180bc443f7b0b68386b8452d0b57b2be4beca3eee9d81409a7658b4c3f'
assert copied['tests-synthetic.py']['sha256'] == '4850a083264e305871b81a9ae5a16390b63950ce9b9efca630c7aa89fd153417'
(out / 'ROOT-REVIEW.json').write_text(json.dumps({'purpose': 'Independent unchanged 62-case synthetic builder qualification',
    'review': 'Root read original utility, both final repairs, full test protocol, guarded runner and launcher',
    'scope': 'Synthetic ZIPs only; no real wheel, model asset, model execution or installation',
    'prior_attempts_retained': ['bw01: 61 passed, 1 failed', 'bw02: 61 passed, 1 failed'],
    'exact_copied_inputs': copied}, indent=2) + '\n', encoding='utf8')
print(json.dumps({'directory': str(out), 'exact_copied_inputs': len(names)}))
