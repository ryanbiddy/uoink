from pathlib import Path
import hashlib,json,shutil,subprocess
from xml.etree import ElementTree as ET
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\c52710a3-21e\gemini')
out=r/'docs/library/proof/sqlite-deadline-cleanup-2026-09-12'
assert not out.exists()
groups={'old':r/'_scratch/sqlite-cleanup-old02','worker':w/'_scratch/sqlite-cleanup-worker01',
        'checkout':r/'_scratch/sqlite-cleanup-checkout01'}
counts={}
for name,folder in groups.items():
    cases=list(ET.parse(folder/'tests.xml').getroot().iter('testcase'))
    counts[name]={'passed':sum(not list(c) for c in cases),'failed':sum(c.find('failure') is not None for c in cases),
                  'errors':sum(c.find('error') is not None for c in cases),'cases':len(cases)}
assert counts['old']=={'passed':1,'failed':4,'errors':0,'cases':5}
assert counts['worker']==counts['checkout']=={'passed':97,'failed':0,'errors':0,'cases':97}
assert (r/'_scratch/sqlite-cleanup-old-input01/test_sqlite_deadline_cleanup.py').read_bytes()==(w/'tests/test_sqlite_deadline_cleanup.py').read_bytes()
assert (r/'tests/test_sqlite_deadline_cleanup.py').read_text()==(w/'tests/test_sqlite_deadline_cleanup.py').read_text()
assert not subprocess.check_output(['git','diff','--diff-filter=CDMRTUXB','7109182','--','tests','scripts/install_receipt/p4_prepare_fixture.py'],cwd=r)
out.mkdir();(out/'.gitattributes').write_bytes(b'* -text\n')
def cp(p,n):
    target=out/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
for name,folder in groups.items():
    for p in folder.rglob('*'):
        if p.is_file() and p.suffix in ('.json','.xml','.log','.py'):cp(p,Path(name)/p.relative_to(folder))
for name in ('sqlite-cleanup-gemini-original.patch','sqlite-cleanup-control-room-report.txt','seal_sqlite_cleanup.py'):
    cp(r/'_scratch'/name,Path('instruments')/name)
cp(r/'_scratch/sqlite-cleanup-old-input01/test_sqlite_deadline_cleanup.py',Path('instruments/old-code-test-input.py'))
summary={'counts':counts,'worker':'c52710a3','old_source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),
         'production_sha256':hashlib.sha256((r/'library_resources.py').read_bytes()).hexdigest(),
         'scope':'One-line production repair; five new regressions. Original tests/fixtures unchanged. Old-code result retained; both-root union verified.',
         'prelaunch_refusal':'First old-code launch omitted IG_FORBIDDEN_LIVE; startup guard raised KeyError before runner/collection. Explicit path environment repaired the invocation.'}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
       for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'counts':counts},indent=2))
