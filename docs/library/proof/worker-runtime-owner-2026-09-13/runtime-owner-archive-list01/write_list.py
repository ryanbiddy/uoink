"""Data-only fixed receipt inventory; no candidate import or test execution."""
from pathlib import Path
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
OUT = ROOT / '_scratch/runtime-owner-archive-list01'
DIRECTORIES = (
    'worker-runtime-owner-proposal01', 'worker-runtime-owner-proposal02',
    'worker-runtime-owner-instrument01', 'worker-runtime-owner-confirmation-preparation01',
    'astra-worker-runtime-owner-confirmation01',
)
ACTUALS = (
    'RUNTIME-OWNER-ADMISSION01-ACTUAL.json', 'RUNTIME-OWNER-ADMISSION02-ACTUAL.json',
    'RUNTIME-OWNER-AUTHOR01-FINAL-ACTUAL.json', 'RUNTIME-OWNER-AUTHOR01-INITIAL-ACTUAL.json',
    'RUNTIME-OWNER-INDEPENDENT-ADMISSION-ACTUAL.json',
    'RUNTIME-OWNER-INDEPENDENT01-FINAL-ACTUAL.json', 'RUNTIME-OWNER-INDEPENDENT01-INITIAL-ACTUAL.json',
)
def read_json(path):
    return json.loads(path.read_bytes())

results = []
for name in (DIRECTORIES[2], DIRECTORIES[4]):
    run = ROOT / '_scratch' / name / 'runs/rto01'
    result = read_json(run / 'stdout.json')
    outcome = read_json(run / 'exit.json')
    native = read_json(run / 'native-exit.json')
    assert (result['count'], result['passed'], result['failed'], result['skipped']) == (11, 11, 0, 0)
    assert result['guard_valid'] is True and result['guard_denials'] == result['registry_denials'] == result['heavy_roots_loaded'] == []
    assert result['metadata_trap_count'] == 12 and result['registry_trap_count'] == 25
    assert outcome['native_exit'] == outcome['outer_exit'] == native['native_exit'] == 0
    assert outcome['inputs_unchanged'] is True and outcome['receipt_valid'] is True
    assert outcome['stdout_bytes'] == 5359 and outcome['stderr_bytes'] == 0
    after = read_json(run / 'after.json')
    assert len(after) == 16
    assert all(row['before_sha256'] == row['copy_after_sha256'] == row['source_after_sha256'] for row in after)
    results.append(result)
assert results[0]['cases'] == results[1]['cases']
paths = []
for name in DIRECTORIES:
    base = ROOT / '_scratch' / name
    for path in base.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            assert path.suffix in ('.py', '.ps1', '.json', '.md', '.diff', '.txt', '.log') or path.name == '.gitattributes'
            paths.append(path)
paths.extend(ROOT / '_scratch' / name for name in ACTUALS)
paths.extend((OUT / 'VERDICT.md', OUT / 'write_list.py'))
rows = []
for path in sorted(paths):
    raw = path.read_bytes()
    rows.append({'source': str(path), 'relative_path': path.relative_to(ROOT / '_scratch').as_posix(),
                 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
assert len({row['relative_path'] for row in rows}) == len(rows)
record = {'schema': 'uoink.runtime-owner-fixed-archive-inputs.v1',
          'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows),
          'distinct_case_count': 11, 'successful_observations': 2,
          'exact_ordered_case_results_equal': True, 'candidate_execution': False, 'files': rows}
with (OUT / 'FIXED-COPY-LIST.json').open('xb') as stream:
    stream.write((json.dumps(record, indent=2) + '\n').encode())
print(json.dumps({'files': record['file_count'], 'bytes': record['bytes'],
                 'sha256': hashlib.sha256((OUT / 'FIXED-COPY-LIST.json').read_bytes()).hexdigest()}))
