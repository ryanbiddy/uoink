"""Copy a fixed five-file source-review brief; no candidate imports or execution."""
import hashlib
import json
import os
from pathlib import Path
import sys
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
repo=Path(__file__).resolve().parents[1]
prep=repo/'_scratch/gemini-writer-exclusion-correction02-proposal01'
proof=repo/'docs/library/proof/writer-exclusion-correction02-brief-2026-09-13'
canonical=repo/'docs/library/GEMINI-WRITER-EXCLUSION-CORRECTION02-BRIEF-2026-09-13.md'
pins={
    '.gitattributes':(8,'705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da'),
    'BRIEF.md':(3855,'755c5cd51792444f8d4418bbe4e3df5937147975c65cb5bf4093e8233fef77b3'),
    'INPUT-SELECTION.json':(2187,'173324c8aa8b66ce55c35ba151bb34b89eb5351f7bb80fa332c87340b77b62ed'),
    'MAP-PREPARATION-ACTUAL.json':(353,'6fc3b92e32420eafba2631efc179d1a97b6d5c81fcda731d9501459e229434d6'),
    'ROOT-HANDOFF.md':(1118,'4827f85a17cda456447a6cb979b2ebaec682e03387a6790890dc1d4c2d654fbd')}
def chain(path):
    for part in (path,*path.parents):
        assert not part.is_symlink() and not part.is_junction()
def read(path):
    chain(path)
    with path.open('rb') as stream:
        data=stream.read(131073)
    assert len(data)<=131072 and b'\0' not in data
    data.decode('utf-8')
    return data
def digest(data):
    return hashlib.sha256(data).hexdigest()
def write(path,data):
    chain(path.parent)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    assert read(path)==data
assert {p.name for p in prep.iterdir()}==set(pins)
cached={name:read(prep/name) for name in pins}
for name,data in cached.items():
    assert (len(data),digest(data))==pins[name]
mapping=json.loads(cached['INPUT-SELECTION.json'])
assert mapping['selected_count']==5 and mapping['selected_bytes']==120375 and mapping['selected_lines']==1773
assert [r['id'] for r in mapping['files']]==['B-01','B-02','B-03','B-04','B-05']
selected={}
for row in mapping['files']:
    path=repo/row['path']
    assert path.is_relative_to(repo/'docs/library/proof/windows-writer-exclusion-native-2026-09-13/proposal04')
    assert path.suffix in ('.py','.ps1')
    data=read(path)
    assert (len(data),digest(data))==(row['bytes'],row['sha256'])
    assert len(data.decode().split('\n'))==row['lines']
    selected[path]=data
chain(proof.parent)
chain(canonical.parent)
assert not proof.exists() and not canonical.exists()
selfdata=read(Path(__file__))
proof.mkdir()
payloads=dict(cached)
payloads['materialize-writer-correction02-brief.py']=selfdata
receipt={'scope':'Documentary copy only; source inputs unchanged; no dispatch or candidate execution',
         'selected_inputs':mapping['files'],'canonical_sha256':pins['BRIEF.md'][1]}
payloads['COPY-CHECKS.json']=(json.dumps(receipt,indent=2)+'\n').encode()
for name,data in payloads.items():
    write(proof/name,data)
write(canonical,cached['BRIEF.md'])
for name,data in cached.items():
    assert read(prep/name)==data
for path,data in selected.items():
    assert read(path)==data
assert read(Path(__file__))==selfdata
manifest={'files':[{'path':name,'bytes':len(data),'sha256':digest(data)} for name,data in sorted(payloads.items())]}
manifestdata=(json.dumps(manifest,indent=2)+'\n').encode()
write(proof/'SHA256.json',manifestdata)
assert {p.name for p in proof.iterdir()}==set(payloads)|{'SHA256.json'}
print(json.dumps({'payloads':len(payloads),'payload_bytes':sum(len(v) for v in payloads.values()),
                  'manifest_sha256':digest(manifestdata),'canonical_sha256':digest(cached['BRIEF.md']),
                  'selected_inputs':5,'selected_bytes':120375,'candidate_executed':False}))
