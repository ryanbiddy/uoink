"""Archive sealed projection preparation plus exact actual static receipts."""
import hashlib
import json
from pathlib import Path
import stat

root = Path(__file__).resolve().parents[1]
dest = root / 'docs/library/proof/vad-selected-projection-2026-09-13'
dest.mkdir(exist_ok=False)
(dest / '.gitattributes').write_bytes(b'* -text\n')
def copy(source, target, size=None, sha=None):
    info = source.lstat()
    assert stat.S_ISREG(info.st_mode) and not getattr(info, 'st_reparse_tag', 0) and info.st_size < 2 * 1024 * 1024
    raw = source.read_bytes()
    assert size is None or len(raw) == size
    assert sha is None or hashlib.sha256(raw).hexdigest() == sha
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    assert target.read_bytes() == raw

source = root / '_scratch/vad-selected-root-projection-final-proof01'
seal = source / 'SHA256.json'
assert hashlib.sha256(seal.read_bytes()).hexdigest() == '7a3484f2b52d607c65748cb03eb13363418ff2c157e76648c1e7c1cef68d66ed'
doc = json.loads(seal.read_bytes())
rows = doc.get('payloads', doc.get('files'))
if isinstance(rows, dict):
    rows = [dict(row, file=name) for name, row in rows.items()]
names = set()
for row in rows:
    name = row.get('file', row.get('path'))
    assert name not in names and not Path(name).is_absolute() and '..' not in Path(name).parts
    names.add(name)
    copy(source / name, dest / 'preparation214' / name, row['bytes'], row['sha256'])
assert len(names) == 214
assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == names | {'SHA256.json'}
copy(seal, dest / 'preparation214/SHA256.json')
launch = root / '_scratch/vad-symbolic-projection01-launch'
for name in ['exit.json', 'independent-review.md', 'outer-exit.json', 'plan.json', 'read_symbolic_inventory.py', 'root-brief.md', 'stderr.log', 'stdout.log']:
    copy(launch / name, dest / 'actual-launch' / name)
copy(root / '_scratch/vad-symbolic-adapter-proposal01/results/symbolic-projection01.json', dest / 'symbolic-projection01.json', 190182, '60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d')
for name in ['launch_vad_projection01.py', 'prepare_projection_launcher01.py']:
    copy(root / '_scratch' / name, dest / name)
copy(Path(__file__), dest / 'archive.py')
rows = []
for path in sorted(p for p in dest.rglob('*') if p.is_file()):
    raw = path.read_bytes()
    rows.append({'file': path.relative_to(dest).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
manifest = json.dumps({'payload_count': len(rows), 'payloads': rows}, indent=2).encode() + b'\n'
(dest / 'SHA256.json').write_bytes(manifest)
print(json.dumps({'payloads': len(rows), 'manifest_sha256': hashlib.sha256(manifest).hexdigest()}))
