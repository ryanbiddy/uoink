"""Seal the finished documentary proof; no product/model/test execution."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
OUT=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
payloads=[]
for path in sorted(OUT.iterdir()):
    assert path.is_file(),path
    raw=path.read_bytes()
    payloads.append({'file':path.name,'bytes':len(raw),'sha256':sha(raw)})
with (OUT/'SHA256.json').open('x',encoding='utf-8',newline='\n') as stream:
    stream.write(json.dumps({'created_utc':datetime.now(timezone.utc).isoformat(),
        'payload_count':len(payloads),'scope':'Documentary reliability integration evidence; 563 separately hash-bound ZIP members',
        'payloads':payloads},indent=2)+'\n')
print(json.dumps({'outer_payload_count':len(payloads),'outer_payload_bytes':sum(row['bytes'] for row in payloads),
    'outer_manifest_sha256':sha((OUT/'SHA256.json').read_bytes()),
    'zip_members':563,'zip_bytes':(OUT/'receipts.zip').stat().st_size,
    'zip_sha256':sha((OUT/'receipts.zip').read_bytes()),
    'validator_sha256':sha((OUT/'verify_archive.py').read_bytes())}))
