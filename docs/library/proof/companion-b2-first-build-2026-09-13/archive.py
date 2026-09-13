"""Preserve sealed builder preparations and the first actual build receipts."""
import hashlib
import json
from pathlib import Path
import stat

root = Path(__file__).resolve().parents[1]
dest = root / 'docs/library/proof/companion-b2-first-build-2026-09-13'
dest.mkdir(exist_ok=False)
(dest / '.gitattributes').write_bytes(b'* -text\n')

def copy(source, target, size=None, digest=None):
    info = source.lstat()
    assert stat.S_ISREG(info.st_mode) and not getattr(info, 'st_reparse_tag', 0)
    assert info.st_size <= 2 * 1024 * 1024
    raw = source.read_bytes()
    assert size is None or len(raw) == size
    assert digest is None or hashlib.sha256(raw).hexdigest() == digest
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    assert target.read_bytes() == raw

for name, folder, seal in [
    ('builder100', 'companion-b2-builder-combined01', '063159c7b97b1f871947a2916c48cfdb7ea6c93246815719115789335fc57963'),
    ('preparation21', 'b2-real-wheel-preparation01', 'ebab6c9180c7c8f230e55b619d1cc469d7043f1a43e197a3a8abd126f7eb7484'),
]:
    source = root / '_scratch' / folder
    manifest = source / 'SHA256.json'
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == seal
    doc = json.loads(manifest.read_bytes())
    rows = doc.get('payloads', doc.get('files'))
    assert isinstance(rows, list)
    names = set()
    for row in rows:
        rel = row.get('file', row.get('path'))
        assert rel not in names and not Path(rel).is_absolute() and '..' not in Path(rel).parts
        names.add(rel)
        copy(source / rel, dest / name / rel, row['bytes'], row['sha256'])
    assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == names | {'SHA256.json'}
    copy(manifest, dest / name / 'SHA256.json')

run = root / '_scratch/b2-real-wheel-py314-01'
for rel in ['root-outer-exit.json', 'launch-result.json', 'launch-plan.json', 'console.log', 'build-result.json', 'artifact/provenance.json']:
    copy(run / rel, dest / 'actual-py314-01' / rel)
copy(root / '_scratch/B2-REAL-WHEEL-ROOT-DECISION-2026-09-13.md', dest / 'ROOT-DECISION.md')
copy(Path(__file__), dest / 'archive.py')
rows = []
for path in sorted(p for p in dest.rglob('*') if p.is_file()):
    raw = path.read_bytes()
    rows.append({'file': path.relative_to(dest).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
manifest = json.dumps({'payload_count': len(rows), 'payloads': rows}, indent=2).encode() + b'\n'
(dest / 'SHA256.json').write_bytes(manifest)
print(json.dumps({'payloads': len(rows), 'manifest_sha256': hashlib.sha256(manifest).hexdigest(), 'wheel_archived': False}))
