"""Seal only this task's documentary evidence and explicit raw receipt files."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = Path(__file__).resolve().parent
assert not (HERE/'SHA256.json').exists()
verification = json.loads((HERE/'FINAL-VERIFICATION.json').read_bytes())
assert verification['verification_result']=='PASS'
copies = []
absent = []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(source, relative):
    target = HERE/relative
    assert target.resolve().is_relative_to(HERE.resolve()) and not target.exists()
    assert source.is_file() and not source.is_symlink()
    expected = digest(source)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    assert digest(source)==digest(target)==expected
    copies.append({'source':str(source),'destination':relative,'bytes':source.stat().st_size,'sha256':expected})


for mode in ('native01','native02','native03','native04','unit01','unit02','unit03','collect01','pass01'):
    folder = ROOT/('_scratch/partition-subtest-'+mode)
    for name in ('results.json','tests.log','tests.xml','guard/sitecustomize.py','guard/ig_paths.py'):
        if (folder/name).is_file():
            copy(folder/name,'raw/'+mode+'/'+name)
        else:
            absent.append({'mode':mode,'file':name})
for name, expected in verification['final_instrument_sha256'].items():
    source = ROOT/'_scratch'/name
    assert digest(source)==expected
    copy(source,'after/'+name)
    before = HERE/'before/instruments'/name
    if not before.exists():
        before = HERE/'integration-before'/name
    difference = ''.join(difflib.unified_diff(before.read_text().splitlines(keepends=True),source.read_text().splitlines(keepends=True),fromfile='before/'+name,tofile='after/'+name))
    target=HERE/'diffs'/(name+'.diff')
    target.parent.mkdir(exist_ok=True)
    target.write_text(difference,encoding='utf-8',newline='\n')
(HERE/'.gitattributes').write_bytes(b'* -text\n')
(HERE/'COPY-VERIFICATION.json').write_text(json.dumps({'verified_utc':datetime.now(timezone.utc).isoformat(),'copies':copies,'known_absent_raw_files':absent,'hash_mismatches':0},indent=2)+'\n',encoding='utf-8')
files = {}
for path in sorted(HERE.rglob('*')):
    if path.is_file():
        assert not path.is_symlink()
        assert path.suffix.lower() in ('.py','.ps1','.md','.json','.jsonl','.xml','.log','.diff',''), path
        files[path.relative_to(HERE).as_posix()]={'bytes':path.stat().st_size,'sha256':digest(path)}
(HERE/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf-8')
for name,row in files.items():
    assert digest(HERE/name)==row['sha256']
print(json.dumps({'payload_count':len(files),'copied_files':len(copies),'hash_mismatches':0,'manifest_sha256':digest(HERE/'SHA256.json'),'known_absent_raw_files':absent},indent=2))
