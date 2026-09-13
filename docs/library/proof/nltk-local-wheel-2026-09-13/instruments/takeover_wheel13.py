import hashlib,json,shutil,subprocess
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\a332397f-bac\gemini')
target=root / '_scratch/wheel-integrator13'
archive=root / '_scratch/nltk-wheel-worker-original13'
archive.mkdir(exist_ok=False)
paths=['scripts/build_nltk_pathsec_wheel.py','tests/test_nltk_local_wheel.py',
       'vendor/nltk-pathsec/dist/nltk-3.10.3+uoink.pathsec1-py3-none-any.whl',
       'vendor/nltk-pathsec/dist/nltk-3.10.3+uoink.pathsec1-py3-none-any.whl.provenance.json',
       'vendor/nltk-pathsec/dist/provenance.json']
for rel in paths:
    p=archive / rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((worker / rel).read_bytes())
for directory in ['_scratch/attempts','_scratch/gemini-wheel-verify01']:
    for p in (worker / directory).glob('*'):
        if p.is_file():
            dst=archive / directory / p.name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(p.read_bytes())
for p in (worker / '_scratch').glob('attempt*.*'):
    dst=archive / '_scratch' / p.name;dst.write_bytes(p.read_bytes())
for label in ['build_attempt1','build_attempt2','build_clean01','build_clean02','build_py314']:
    for p in (worker / '_scratch' / label).glob('*'):
        if p.is_file():
            dst=archive / '_scratch' / label / p.name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(p.read_bytes())
report={'scope':'Snapshot after print timeout and completed Control Room transport; provider terminal success was not established.',
 'worker':str(worker),'detached_takeover':str(target),'report_delivered':(worker / 'docs/library/NLTK-LOCAL-WHEEL-REVIEW-2026-09-12.md').exists(),
 'file_hashes':{rel:hashlib.sha256((archive / rel).read_bytes()).hexdigest() for rel in paths}}
subprocess.run(['git','worktree','add','--detach',str(target),'HEAD'],cwd=root,check=True,capture_output=True)
for rel in paths:
    p=target / rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((archive / rel).read_bytes())
upstream=target / '_scratch/upstream/nltk-3.10.3-py3-none-any.whl'
upstream.parent.mkdir(parents=True,exist_ok=True)
upstream.write_bytes((root / '_scratch/nltk-wheel-astra-artifact01/nltk-3.10.3-py3-none-any.whl').read_bytes())
(archive / 'snapshot.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report))
