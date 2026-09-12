"""Stage exact sealed payloads, accounting for global ignores and Git conversion."""
from pathlib import Path
import datetime as dt,hashlib,json,subprocess
r=Path(__file__).resolve().parents[1]
folders=['ryan-agent-installed-08-2026-09-12','native-gui-package08-2026-09-12']
expected={};counts={}
def git(*args):return subprocess.check_output(['git',*args],cwd=r)
assert git('branch','--show-current').decode().strip()=='cc/living-library-candidate'
assert not git('diff','--cached','--name-only','-z'), 'Review any prior staging before adding these proofs'
for name in folders:
    folder=r/'docs/library/proof'/name
    seal=json.loads((folder/'SHA256.json').read_text(encoding='utf8'))['files'];counts[name]=len(seal)
    for relative,row in seal.items():
        p=(folder/relative).resolve();assert p.is_relative_to(folder.resolve())
        b=p.read_bytes();assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
        expected[p.relative_to(r).as_posix()]=row
    p=folder/'SHA256.json';b=p.read_bytes()
    expected[p.relative_to(r).as_posix()]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
git('add','--',*[str(Path('docs/library/proof')/x) for x in folders])
staged=set(git('diff','--cached','--name-only','-z').decode('utf8').split('\0'))-{''}
forced=sorted(set(expected)-staged)
for name in forced:git('add','-f','--',name)
staged=set(git('diff','--cached','--name-only','-z').decode('utf8').split('\0'))-{''}
assert staged==set(expected), sorted(staged^set(expected))
for name,row in expected.items():
    b=git('show',':'+name);assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],name
report={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'PASS','proof_payloads':counts,'staged_files_including_seals':len(expected),'force_added_exact_paths':forced,'comparison':'Every raw disk payload and actual staged Git blob matches its declared length and SHA-256; no newline normalization.'}
with (r/'_scratch/installed08-staged-proof-check.json').open('x',encoding='utf8') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
