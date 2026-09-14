"""Fixed text copies and qualification-root substitutions only."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'_scratch/vad-d2-dormant-invocation-proposal02'
DST=ROOT/'_scratch/astra-d2-fake23-confirmation01'
def sha(raw): return hashlib.sha256(raw).hexdigest()
assert not DST.exists()
original_manifest=(SRC/'QUALIFICATION-INPUTS.json').read_bytes()
assert sha(original_manifest)=='c6e83710882f413547b671f058b9190c06940291b34d882df6c25f0ed774bcad'
doc=json.loads(original_manifest)
assert len(doc['files'])==9
payloads=[]
for name,digest in doc['files'].items():
    path=SRC/name
    for part in (path,*path.parents):
        assert not part.is_symlink() and not part.is_junction()
        if part==ROOT: break
    raw=path.read_bytes()
    assert len(raw)<=65536 and sha(raw)==digest
    new=raw
    if name in ('qualify_d2.py','run_fake23_01.ps1'):
        old_path=str(SRC).encode('utf-8')
        new_path=str(DST).encode('utf-8')
        assert raw.count(old_path)==1, name
        new=raw.replace(old_path,new_path)
    payloads.append((name,raw,new))
DST.mkdir()
rows=[]
for name,raw,new in payloads:
    (DST/name).write_bytes(new)
    assert (SRC/name).read_bytes()==raw and (DST/name).read_bytes()==new
    doc['files'][name]=sha(new)
    rows.append({'name':name,'source_sha256':sha(raw),'copy_sha256':sha(new),
                 'changed':raw!=new,'change':'one fixed qualification root' if raw!=new else None})
assert sum(row['changed'] for row in rows)==2
manifest=json.dumps(doc,indent=2).encode('utf-8')+b'\n'
(DST/'QUALIFICATION-INPUTS.json').write_bytes(manifest)
admission={'root_reviewed':True,'scope':'D2_FAKE23_ONLY_NO_REAL_CONVERSION','run_id':'fake23-01',
           'input_manifest_sha256':sha(manifest)}
(DST/'ROOT-FAKE23-ADMISSION.json').write_text(json.dumps(admission,indent=2)+'\n',encoding='utf-8')
record={'scope':'Independent fake23 only; no real D2 approval','source_count':9,
        'identical_source_count':7,'qualification_root_substitutions':2,'rows':rows,
        'input_manifest_sha256':sha(manifest),
        'admission_sha256':sha((DST/'ROOT-FAKE23-ADMISSION.json').read_bytes())}
(DST/'PREPARATION.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:record[k] for k in ('scope','source_count','identical_source_count','qualification_root_substitutions','input_manifest_sha256','admission_sha256')}))
