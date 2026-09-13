"""Data-only preparation seal. Never import or execute proposed reader code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

root = Path(__file__).absolute().parent
manifest_path = root / 'SHA256.json'
if manifest_path.exists():
    raise SystemExit('Preparation already sealed; preserve it unchanged')
rows = []
for path in sorted(root.rglob('*')):
    if path.is_symlink():
        raise ValueError('No alias paths in preparation seal')
    if path.is_file():
        raw = path.read_bytes()
        rows.append({'path': path.relative_to(root).as_posix(), 'bytes': len(raw),
                     'sha256': hashlib.sha256(raw).hexdigest()})
manifest = {'schema': 'uoink.documentary-payload-manifest.v1',
            'prepared_utc': datetime.now(timezone.utc).isoformat(),
            'payload_count': len(rows), 'payload_bytes': sum(row['bytes'] for row in rows),
            'qualification_executed': False, 'actual_artifact_access': False,
            'files': rows}
raw = (json.dumps(manifest, indent=2) + '\n').encode('utf-8')
with manifest_path.open('xb') as stream:
    stream.write(raw)
for row in rows:
    content = (root / row['path']).read_bytes()
    assert len(content) == row['bytes'] and hashlib.sha256(content).hexdigest() == row['sha256']
print(json.dumps({'payload_count': len(rows), 'payload_bytes': manifest['payload_bytes'],
                  'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                  'all_payloads_verified': True, 'proposal_executed': False}))
