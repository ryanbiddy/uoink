"""Seal the review-kit delivery records without copying the installer into Git."""
from pathlib import Path
import hashlib
import json
import shutil

r = Path(__file__).resolve().parents[1]
bundle = r / 'build/Uoink-Living-Library-3-8-0-Review-Kit-07-2026-09-12'
out = r / 'docs/library/proof/ryan-review-bundle-07-2026-09-12'
out.mkdir(exist_ok=False)
(out / '.gitattributes').write_text('* -text\n', encoding='utf8', newline='\n')
shutil.copyfile(bundle.with_suffix('.receipt.json'), out / 'delivery.json')
for name in ('BUNDLE-SHA256.json', 'release-state.json', 'START-HERE.md', 'historical-data-omissions.json'):
    shutil.copyfile(bundle / name, out / name)
for name in ('build_release_bundle07.py', 'review_bundle07.py', 'seal_review_bundle07.py',
             'review-bundle07-build.log', 'review-bundle07-inspection.json',
             'package07-git-proof-check01.json', 'verify_committed_package07_proofs.py',
             'runbook07-syntax.json', 'check_runbook07.ps1',
             'prepare_delivery07.py', 'repair_delivery07_preflight.py', 'delivery07-preflight-failures.json',
             'stage_installed07.py', 'stage_installed07_02.py', 'stage_installed07_02.py.diff',
             'installed07-staged-proof-check.json', 'run_bundle07_once.py',
             'build_release_bundle07.py.diff', 'review_bundle07.py.diff',
             'seal_review_bundle07.py.diff'):
    shutil.copyfile(r / '_scratch' / name, out / name)
files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(out.rglob('*')) if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'algorithm': 'sha256', 'files': files}, indent=2) + '\n', encoding='utf8')
print(json.dumps({'delivery_payloads': len(files), 'zip': str(bundle.with_suffix('.zip'))}))
