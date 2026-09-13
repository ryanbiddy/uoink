"""Compress exact approved documentary bytes. No test or product execution."""
from datetime import datetime,timezone
import hashlib,json,zipfile
from pathlib import Path
OUT=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
listing=json.loads((OUT/'INPUT-LIST.json').read_bytes())
rows=listing['entries']
assert len(rows)==listing['file_count']==563
assert sum(row['bytes'] for row in rows)==listing['total_uncompressed_bytes']==7194435
for row in rows:
    raw=Path(row['source']).read_bytes()
    assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],row['member']
with zipfile.ZipFile(OUT/'receipts.zip','x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for row in rows:
        raw=Path(row['source']).read_bytes()
        assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],row['member']
        info=zipfile.ZipInfo(row['member'],date_time=(1980,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        info.create_system=3
        info.external_attr=0o100644<<16
        archive.writestr(info,raw,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
with (OUT/'ZIP-MEMBERS-SHA256.json').open('x',encoding='utf-8',newline='\n') as stream:
    stream.write(json.dumps({'member_count':len(rows),
        'total_uncompressed_bytes':sum(row['bytes'] for row in rows),
        'members':[{key:row[key] for key in ['member','bytes','sha256']} for row in rows]},indent=2)+'\n')
for row in rows:
    raw=Path(row['source']).read_bytes()
    assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],row['member']
raw=(OUT/'receipts.zip').read_bytes()
receipt={'finished_utc':datetime.now(timezone.utc).isoformat(),'member_count':len(rows),
    'uncompressed_bytes':listing['total_uncompressed_bytes'],'zip_bytes':len(raw),
    'zip_sha256':sha(raw),'source_bytes_unchanged_before_after':True,
    'tests_or_product_executed':False,'redacted_or_excluded_for_credentials':[]}
with (OUT/'ARCHIVE-RECEIPT.json').open('x',encoding='utf-8',newline='\n') as stream:
    stream.write(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
