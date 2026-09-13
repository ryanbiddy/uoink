"""Seal documentary payloads only; no archived source execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

root = Path(__file__).absolute().parent
target = root / 'SHA256.json'
assert not target.exists()
rows = []
for path in sorted(root.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        raw = path.read_bytes()
        rows.append({'path': path.relative_to(root).as_posix(), 'bytes': len(raw),
                     'sha256': hashlib.sha256(raw).hexdigest()})
manifest = {'schema': 'uoink.documentary-payload-manifest.v1',
            'sealed_utc': datetime.now(timezone.utc).isoformat(),
            'payload_count': len(rows), 'payload_bytes': sum(row['bytes'] for row in rows),
            'distinct_synthetic_cases': 82, 'successful_repetitions': 2,
            'prior_seals_preserved': 6, 'actual_artifact_or_runtime_qualified': False,
            'files': rows}
raw = (json.dumps(manifest, indent=2) + '\n').encode('utf-8')
with target.open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(rows), 'payload_bytes': manifest['payload_bytes'],
                  'manifest_sha256': hashlib.sha256(raw).hexdigest()}))
