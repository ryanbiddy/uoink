"""Inspect captured wheel bytes independently of the worker's builder; no imports."""
import base64,csv,email,hashlib,io,json,re,zipfile
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker=root / '_scratch/wheel-integrator13'
out=root / '_scratch/nltk-wheel-astra-artifact02'
out.mkdir(exist_ok=False)
up_name='nltk-3.10.3-py3-none-any.whl'
local_name='nltk-3.10.3+uoink.pathsec1-py3-none-any.whl'
up=(worker / '_scratch/upstream' / up_name).read_bytes()
local=(worker / 'vendor/nltk-pathsec/dist' / local_name).read_bytes()
assert len(up)==1798643 and hashlib.sha256(up).hexdigest()=='ff9598a8e20518ee0d557745890cc4435b9578489e2dcbc69c4f81fa060caf7c'
(out / up_name).write_bytes(up);(out / local_name).write_bytes(local)
(out / 'worker-provenance.json').write_bytes((worker / 'vendor/nltk-pathsec/dist/provenance.json').read_bytes())
def inspect(raw,dist):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=[n.filename for n in archive.infolist()]
        assert len(names)==len(set(n.casefold() for n in names))
        assert all(not n.endswith('/') for n in names)
        payloads={n:archive.read(n) for n in names}
        rows=list(csv.reader(io.StringIO(payloads[dist+'/RECORD'].decode('utf8'))))
        assert len(rows)==len({n[0] for n in rows})
        assert {r[0] for r in rows}==set(payloads)
        for name,digest,size in rows:
            if name==dist+'/RECORD':assert not digest and not size;continue
            content=payloads[name]
            assert digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b'=').decode()
            assert size==str(len(content))
        meta=email.message_from_bytes(payloads[dist+'/METADATA'])
        assert meta.get_all('Name')==['nltk']
        return payloads,meta
original,ometa=inspect(up,'nltk-3.10.3.dist-info')
patched,pmeta=inspect(local,'nltk-3.10.3+uoink.pathsec1.dist-info')
with zipfile.ZipFile(io.BytesIO(local)) as stored:
    assert all(i.compress_type==zipfile.ZIP_STORED and i.create_system==3 and i.date_time==(2026,9,12,0,0,0) for i in stored.infolist())
assert hashlib.sha256(local).hexdigest()=='969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8'
assert ometa.get_all('Version')==['3.10.3'] and pmeta.get_all('Version')==['3.10.3+uoink.pathsec1']
assert ometa.get_all('Requires-Dist')==pmeta.get_all('Requires-Dist')
changes={
 'nltk/classify/maxent.py':'60645d1be785066c083f2458153f7e83931ebd8db20d976a8d34dea100f83f3c',
 'nltk/parse/transitionparser.py':'8dcc54a30557450084858b3ed7f559697f945593f50a2fdc9f4a08e3bbbbdd60',
 'nltk/tag/perceptron.py':'31d1577b9b04b22aace4fdead2b3f7bcb48864af45bfa5210f1e1d32a3cb81b9'}
mapped={k.replace('nltk-3.10.3.dist-info/','nltk-3.10.3+uoink.pathsec1.dist-info/'):v for k,v in original.items()}
assert set(mapped)==set(patched)
different=[]
for name,data in patched.items():
    if mapped[name]==data:continue
    different.append(name)
    if name in changes:assert hashlib.sha256(data).hexdigest()==changes[name]
    elif name=='nltk/VERSION':assert data==b'3.10.3+uoink.pathsec1\n'
    elif name.endswith('.dist-info/METADATA'):
        assert data==mapped[name].replace(b'Version: 3.10.3\n',b'Version: 3.10.3+uoink.pathsec1\n',1)
    else:assert name=='nltk-3.10.3+uoink.pathsec1.dist-info/RECORD'
assert len(different)==6
provenance=json.loads((out/'worker-provenance.json').read_text())
assert provenance['output_wheel']['sha256']==hashlib.sha256(local).hexdigest()
report={'scope':'Repaired stored wheel, independently inspected after both-root tests; no packaging utility or NLTK execution.',
 'upstream_sha256':hashlib.sha256(up).hexdigest(),'wheel_sha256':hashlib.sha256(local).hexdigest(),
 'wheel_bytes':len(local),'members':len(patched),'changed_members':different,
 'all_record_entries_verified':True,'dependency_metadata_unchanged':True,
 'all_other_payload_bytes_unchanged':True,'model_imports':False,'release_ready':False}
(out / 'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report))
