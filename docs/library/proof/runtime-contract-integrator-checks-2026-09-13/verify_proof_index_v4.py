"""Compare a documentary seal with disk and the Git index; execute no payload."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

p = argparse.ArgumentParser()
p.add_argument('relative')
p.add_argument('--manifest', default='SHA256.json')
a = p.parse_args()
r = Path(__file__).resolve().parents[1]
folder = (r / a.relative).resolve(strict=True)
assert folder.is_relative_to(r / 'docs/library/proof')
assert a.manifest in ('SHA256.json', 'SHA256-MANIFEST.json')
manifest_path = folder / a.manifest
manifest = manifest_path.read_bytes()
doc = json.loads(manifest)
entries = doc if isinstance(doc, list) else doc.get('files', doc.get('payloads', doc.get('records')))
assert isinstance(entries, (list, dict))
rows = {}
if isinstance(entries, dict):
    rows = entries
else:
    for row in entries:
        keys = [key for key in ('file', 'path') if key in row]
        assert len(keys) == 1
        name = row[keys[0]]
        assert isinstance(name, str) and name not in rows
        rows[name] = row
assert {f.relative_to(folder).as_posix() for f in folder.rglob('*') if f.is_file()} == set(rows) | {a.manifest}
total = 0
for name, row in rows.items():
    assert name and '\\' not in name and ':' not in name and not name.startswith('/')
    assert PurePosixPath(name).as_posix() == name and '..' not in PurePosixPath(name).parts
    f = (folder / name).resolve(strict=True)
    assert f.is_relative_to(folder) and not (folder / name).is_symlink()
    raw = f.read_bytes()
    git = subprocess.check_output(['git', 'show', ':' + f.relative_to(r).as_posix()], cwd=r)
    assert raw == git and hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'], name
    total += len(raw)
assert subprocess.check_output(['git', 'show', ':' + manifest_path.relative_to(r).as_posix()], cwd=r) == manifest
print(json.dumps({'proof': a.relative, 'payloads_matching_disk_and_git': len(rows), 'bytes': total,
                  'manifest_sha256': hashlib.sha256(manifest).hexdigest()}))
