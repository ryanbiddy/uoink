"""Compare staged wheel payloads with the independently verified repair downloads."""
import hashlib
import json
import zipfile
from pathlib import Path

r = Path(__file__).resolve().parents[1]
site = r / 'installer/staging/python/Lib/site-packages'
out = r / '_scratch/package07-wheel-bindings-01'
out.mkdir(exist_ok=False)
inputs = [
    ('dependency-closure-astra-01/lightning-2.6.6-py3-none-any.whl', '2bcbd6ee840071cd076c7dc9953d7ac1040df92f1c5fa76583aae644f037ab85'),
    ('dependency-closure-astra-01/pytorch_lightning-2.6.6-py3-none-any.whl', '71f95c7b22f25c4f91cc659e1734bcdc6c69c8b66543f2ed2d78dbe29ce2f167'),
    ('setuptools-runtime-01/setuptools-83.0.0-py3-none-any.whl', '29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3')]
reports = []
for name, digest in inputs:
    wheel = r / '_scratch' / name
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == digest
    rows = []
    excluded = []
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if info.filename.endswith('.dist-info/RECORD'):
                excluded.append({'path': info.filename, 'reason': 'pip installation/build intentionally rewrites RECORD'})
                continue
            target = (site / info.filename).resolve()
            assert target.is_relative_to(site)
            expected = hashlib.sha256(archive.read(info)).hexdigest()
            actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
            rows.append({'path': info.filename, 'expected_sha256': expected,
                         'staged_sha256': actual, 'matches': expected == actual})
    reports.append({'wheel': name, 'wheel_sha256': digest, 'compared': len(rows),
                    'failed': sum(not row['matches'] for row in rows), 'excluded': excluded, 'files': rows})
result = {'scope': 'Actual staged payload bytes versus separately verified PyPI repair wheels; only installation-rewritten RECORD files excluded. No checkpoint or inference.',
          'compared': sum(row['compared'] for row in reports),
          'failed': sum(row['failed'] for row in reports), 'wheels': reports}
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
print(json.dumps({'compared': result['compared'], 'failed': result['failed'],
                  'wheels': [{k: v for k, v in row.items() if k != 'files'} for row in reports]}, indent=2))
raise SystemExit(int(bool(result['failed'])))
