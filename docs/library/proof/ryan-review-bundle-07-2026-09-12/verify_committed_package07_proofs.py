"""Verify every current proof payload against actual Git blob bytes."""
from pathlib import Path
import hashlib
import json
import subprocess

r = Path(__file__).resolve().parents[1]
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=r, text=True).strip()
names = ['ryan-final-partitioned-04-2026-09-12', 'candidate-package-07-2026-09-12',
         'repaired-lock-audit-2026-09-11', 'ryan-agent-installed-07-2026-09-12',
         'installed07-instrument-review-2026-09-12', 'sqlite-deadline-cleanup-2026-09-12',
         'ryan-installed-client-06-2026-09-12']
counts = {}
for name in names:
    folder = r / 'docs/library/proof' / name
    files = json.loads((folder / 'SHA256.json').read_text(encoding='utf8'))['files']
    for relative, row in files.items():
        path = (folder / relative).relative_to(r).as_posix()
        data = subprocess.check_output(['git', 'show', head + ':' + path], cwd=r)
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], path
    counts[name] = len(files)
report = {'source': head, 'result': 'PASS', 'payloads': sum(counts.values()), 'proofs': counts,
          'scope': 'Git blob bytes, not only working-tree files. Any ignored paths are staged explicitly after disk-seal verification; old failures retained separately.'}
out = r / '_scratch/package07-git-proof-check01.json'
with out.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
