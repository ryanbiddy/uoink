"""Adapt documentary delivery instruments to exact package-07 inputs before use."""
from pathlib import Path
import ast,difflib,json
r=Path(__file__).resolve().parents[1];scratch=r/'_scratch'
def write(oldname,newname,changes):
    old=(scratch/oldname).read_text();new=old
    for before,after in changes:
        assert before in new,(oldname,before)
        new=new.replace(before,after)
    if newname.endswith('.py'):ast.parse(new)
    with (scratch/newname).open('x',encoding='utf8',newline='\n') as f:f.write(new)
    with (scratch/(newname+'.diff')).open('x',encoding='utf8',newline='\n') as f:
        f.write(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=oldname,tofile=newname)))
write('build_release_bundle06.py','build_release_bundle07.py',[
    ('candidate-package-06-2026-09-11','candidate-package-07-2026-09-12'),
    ('ryan-agent-installed-06-2026-09-11','ryan-agent-installed-07-2026-09-12'),
    ('run_installed_decoders06_portable.py','run_installed_decoders07_portable.py'),
    (" 'candidate-package-07-2026-09-12',"," 'candidate-package-07-2026-09-12','installed07-instrument-review-2026-09-12',\n 'sqlite-deadline-cleanup-2026-09-12','ryan-installed-client-06-2026-09-12',\n 'candidate-package-06-2026-09-11','ryan-agent-installed-06-2026-09-11',"),
    ('This kit contains package-06 and its measured evidence.','This kit contains package-07 and its measured evidence.'),
    ('client, security and release decisions before use.','native-client GUI, historical-evidence, security and release decisions before use.'),
    ("'review kit; see installed verdict and remaining client/release decisions'","'review kit; bounded installed CLI observations complete, GUI/historical/security release scope held'")])
write('review_bundle06.py','review_bundle07.py',[
    ('Review-Kit-06-2026-09-11','Review-Kit-07-2026-09-12'),
    ('assert len(files) == receipt[\'payload_files\'] == 1715','assert len(files) == receipt[\'payload_files\'] and len(files) > 1715'),
    ('candidate-package-06-2026-09-11','candidate-package-07-2026-09-12'),
    ('review-bundle06-inspection.json','review-bundle07-inspection.json')])
write('check_runbook06.ps1','check_runbook07.ps1',[('runbook06-syntax.json','runbook07-syntax.json')])
write('verify_committed_package06_proofs.py','verify_committed_package07_proofs.py',[
    ("names = ['ryan-final-partitioned-03-2026-09-11', 'candidate-package-06-2026-09-11',\n         'repaired-lock-audit-2026-09-11', 'ryan-agent-installed-06-2026-09-11',\n         'ryan-proof-transport-06-2026-09-11']", "names = ['ryan-final-partitioned-04-2026-09-12', 'candidate-package-07-2026-09-12',\n         'repaired-lock-audit-2026-09-11', 'ryan-agent-installed-07-2026-09-12',\n         'installed07-instrument-review-2026-09-12', 'sqlite-deadline-cleanup-2026-09-12',\n         'ryan-installed-client-06-2026-09-12']"),
    ('package06-git-proof-check02.json','package07-git-proof-check01.json'),
    ('First ignored-file failure retained separately.','Any ignored paths are staged explicitly after disk-seal verification; old failures retained separately.')])
write('seal_review_bundle06.py','seal_review_bundle07.py',[
    ('Review-Kit-06-2026-09-11','Review-Kit-07-2026-09-12'),
    ('ryan-review-bundle-06-2026-09-11','ryan-review-bundle-07-2026-09-12'),
    ('build_release_bundle06.py','build_release_bundle07.py'),('review_bundle06.py','review_bundle07.py'),
    ('seal_review_bundle06.py','seal_review_bundle07.py'),('review-bundle06-build.log','review-bundle07-build.log'),
    ('review-bundle06-inspection.json','review-bundle07-inspection.json'),
    ('package06-git-proof-check02.json','package07-git-proof-check01.json'),
    ('verify_committed_package06_proofs.py','verify_committed_package07_proofs.py'),
    ('runbook06-syntax.json','runbook07-syntax.json'),('check_runbook06.ps1','check_runbook07.ps1')])
print('Prepared package-07 delivery instruments and exact diffs. No build/install/client started.')
