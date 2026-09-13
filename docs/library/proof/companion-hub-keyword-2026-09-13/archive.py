"""Preserve original Hub findings, instrument failures and independent contracts."""
import hashlib
import json
from pathlib import Path
import stat

root = Path(__file__).resolve().parents[1]
dest = root / 'docs/library/proof/companion-hub-keyword-2026-09-13'
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

source = root / '_scratch/companion-hub-keyword-review01'
seal = source / 'SHA256.json'
assert hashlib.sha256(seal.read_bytes()).hexdigest() == 'b08fb56fe9d76ca3d289105c206cfbfd584b12f87608ddf285172b58b8c2fc33'
doc = json.loads(seal.read_bytes())
rows = doc.get('payloads', doc.get('files'))
if isinstance(rows, dict):
    rows = [dict(row, file=name) for name, row in rows.items()]
names = set()
for row in rows:
    name = row.get('file', row.get('path'))
    assert name not in names and not Path(name).is_absolute() and '..' not in Path(name).parts
    names.add(name)
    copy(source / name, dest / 'review97' / name, row['bytes'], row['sha256'])
assert len(names) == 97
assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == names | {'SHA256.json'}
copy(seal, dest / 'review97/SHA256.json')
independent = root / '_scratch/astra-hub-keyword01'
for source_file in sorted(p for p in independent.rglob('*') if p.is_file()):
    copy(source_file, dest / 'root-independent' / source_file.relative_to(independent))
copy(root / '_scratch/qualify_hub_keyword_astra01.py', dest / 'root-qualifier.py')
copy(Path(__file__), dest / 'archive.py')
(dest / 'README.md').write_text('''# Optional Hub keyword repair: root verdict

Root accepts the one-line inert source repair for its narrow forwarding contract.
Author and root each reproduce four passed/four TypeError errors on the unchanged
baseline, then eight passed with zero errors, failures or skips on the patch.
Actual child exits are one and zero; both corrected guards are valid and input
hashes remain unchanged. The root comparison wrapper exits zero because those
recorded outcomes match its declared checks; that does not turn the baseline
child's failure into a pass.

The proposed utils.py removes only the obsolete local_dir_use_symlinks keyword.
Its 4,897 bytes have SHA256
ecec29ad34688e2d559218685672c3c2f1086f524d78bcfd53e633a5739d5b19.
The helper still forwards local-only policy, destination, revision, cache and
token arguments to a fake callable bound to the captured candidate Hub signature.
No Hub implementation, package, model, fetch or real wheel build ran here.

All original invalid-guard attempts and the insufficient compile-filename repair
remain preserved. A path-only diagnostic reproduced denied lexical <unknown>
reads during failure formatting. The corrected unittest formatter records raw
frames and exception type/message without source lookup; all eight assertion
bodies and file allowlists remain unchanged. Read review97/VERDICT.md for the
six earlier outcomes and their limits.

This proposal is separate from the reproducible, uninstalled B2 wheel. The next
combined derivative is localassets2; its source, recipe and packaging require
their own review and qualification. Runtime, installation and market acceptance
remain open. Production source and the full-tree result are unchanged.
''', encoding='utf-8', newline='\n')
rows = []
for path in sorted(p for p in dest.rglob('*') if p.is_file()):
    raw = path.read_bytes()
    rows.append({'file': path.relative_to(dest).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
manifest = json.dumps({'payload_count': len(rows), 'payloads': rows}, indent=2).encode() + b'\n'
(dest / 'SHA256.json').write_bytes(manifest)
print(json.dumps({'payloads': len(rows), 'manifest_sha256': hashlib.sha256(manifest).hexdigest()}))
