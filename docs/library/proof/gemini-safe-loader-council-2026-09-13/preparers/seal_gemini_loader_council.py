"""Seal existing documentary review evidence only."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).absolute().parents[1]
scratch = root / '_scratch'
out = root / 'docs/library/proof/gemini-safe-loader-council-2026-09-13'
out.mkdir(exist_ok=False)
copies = []
def copy(source, relative):
    assert source.resolve().is_relative_to(root.resolve())
    before = source.read_bytes()
    destination = out / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(before)
    assert destination.read_bytes() == source.read_bytes() == before
    copies.append({'source':str(source),'path':relative,'bytes':len(before),
                   'sha256':hashlib.sha256(before).hexdigest()})

for directory, prefix in (
 ('gemini-safe-loader-council-c5c89d60','preparation01'),
 ('gemini-safe-loader-council-c5c89d60-02','preparation02'),
 ('gemini-safe-loader-council-c5c89d60-03','accepted-receipts')):
    source = scratch / directory
    for file in sorted(source.rglob('*')):
        if file.is_file():
            copy(file,prefix+'/'+file.relative_to(source).as_posix())
for name in ('prepare_gemini_loader_council_receipts.py',
             'prepare_gemini_loader_council_receipts02.py',
             'prepare_gemini_loader_council_receipts03.py',
             'seal_gemini_loader_council.py'):
    copy(scratch/name,'preparers/'+name)
copy(root/'docs/library/ASTRA-SAFE-LOADER-COUNCIL-VERDICT-2026-09-13.md','ASTRA-VERDICT.md')
(out/'.gitattributes').write_bytes(b'* -text\n')
(out/'COPY-MANIFEST.json').write_text(json.dumps({'files':copies},indent=2)+'\n',encoding='utf-8')
rows = []
for file in sorted(out.rglob('*')):
    if file.is_file():
        raw=file.read_bytes()
        rows.append({'path':file.relative_to(out).as_posix(),'bytes':len(raw),
                     'sha256':hashlib.sha256(raw).hexdigest()})
manifest={'schema':'uoink.documentary-payload-sha256.v1','payload_count':len(rows),
          'payload_bytes':sum(row['bytes'] for row in rows),'excluded_only':'SHA256.json','files':rows}
raw=(json.dumps(manifest,indent=2)+'\n').encode('ascii')
(out/'SHA256.json').write_bytes(raw)
assert {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()} == {r['path'] for r in rows}|{'SHA256.json'}
for row in rows:
    content=(out/row['path']).read_bytes()
    assert len(content)==row['bytes'] and hashlib.sha256(content).hexdigest()==row['sha256']
print(json.dumps({'proof':str(out),'payloads':len(rows),'bytes':manifest['payload_bytes'],
                  'copied_files':len(copies),'manifest_sha256':hashlib.sha256(raw).hexdigest()}))
