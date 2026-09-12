"""Seal the review-kit delivery records without copying the installer into Git."""
from pathlib import Path
import hashlib
import json
import shutil

r = Path(__file__).resolve().parents[1]
bundle = r / 'build/Uoink-Living-Library-3-8-0-Review-Kit-08-2026-09-12'
out = r / 'docs/library/proof/ryan-review-bundle-08-2026-09-12'
out.mkdir(exist_ok=False)
(out / '.gitattributes').write_text('* -text\n', encoding='utf8', newline='\n')
shutil.copyfile(bundle.with_suffix('.receipt.json'), out / 'delivery.json')
for name in ('BUNDLE-SHA256.json', 'release-state.json', 'START-HERE.md', 'historical-data-omissions.json'):
    shutil.copyfile(bundle / name, out / name)
for name in ('build_release_bundle08.py', 'review_bundle08.py', 'seal_review_bundle08.py',
             'review-bundle08-build.log', 'review-bundle08-inspection.json',
             'package08-git-proof-check01.json', 'verify_committed_package08_proofs.py',
             'runbook08-syntax.json', 'check_runbook08.ps1',
             'prepare_delivery08.py', 'delivery08-adaptation-review.json',
             'installed08-staged-proof-check.json', 'run_bundle08_once.py',
             'build_release_bundle08.py.diff', 'review_bundle08.py.diff',
             'seal_review_bundle08.py.diff', 'seal_review_bundle08.py.extension.diff',
             'extend_delivery08_instruments.py','delivery08-instrument-extension.json',
             'DELIVERY08-PREFLIGHT-REPAIR.md','delivery08-preflight01.json',
             'delivery08_preflight02.py','delivery08-preflight02.json',
             'update_release08_documents.py','stage_installed08_proofs.py'):
    shutil.copyfile(r / '_scratch' / name, out / name)
files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(out.rglob('*')) if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'algorithm': 'sha256', 'files': files}, indent=2) + '\n', encoding='utf8')
print(json.dumps({'delivery_payloads': len(files), 'zip': str(bundle.with_suffix('.zip'))}))
