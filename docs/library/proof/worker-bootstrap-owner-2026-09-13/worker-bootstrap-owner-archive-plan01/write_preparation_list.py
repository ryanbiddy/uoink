"""List fixed existing text preparation files; never import a candidate."""
from pathlib import Path
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch')
OUT = ROOT / 'worker-bootstrap-owner-archive-plan01'
directories = ('worker-bootstrap-owner-migration01', 'worker-bootstrap-owner-instrument01',
               'worker-bootstrap-owner-confirmation-preparation01', 'astra-worker-bootstrap-owner-confirmation01')
references = {
    'worker-bootstrap-owner-review01/VERDICT.md': '0f360b573076bdcd1e51355e00ddfbc602211d9480e9d3a08d075e1709611f8b',
    'runtime-owner-archive-list01/FIXED-COPY-LIST.json': '0b8811541ee5c662fb45290b0c79e0c15c6ebf5f1277369689d5096fcd88d92a',
}
paths = []
for directory in directories:
    base = ROOT / directory
    for path in base.rglob('*'):
        if 'runs' in path.relative_to(base).parts:
            continue
        assert not path.is_symlink()
        if path.is_file():
            assert path.suffix in ('.py', '.ps1', '.json', '.md', '.diff', '.txt', '.log') or path.name == '.gitattributes'
            paths.append(path)
for name, expected in references.items():
    path = ROOT / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    paths.append(path)
paths.extend(OUT / name for name in ('ARCHIVE-PLAN.md', 'SOURCE-PREPARATION-HISTORY.md', 'write_preparation_list.py'))
rows = []
for path in sorted(paths):
    raw = path.read_bytes()
    rows.append({'source': str(path), 'relative_path': path.relative_to(ROOT).as_posix(),
                 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
assert len({row['relative_path'] for row in rows}) == len(rows)
record = {'schema': 'uoink.worker-bootstrap-preparation-copy-list.v1', 'candidate_execution': False,
    'run_receipts_included': False, 'files': rows, 'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows)}
with (OUT / 'PREPARATION-COPY-LIST.json').open('xb') as stream:
    stream.write((json.dumps(record, indent=2) + '\n').encode())
print(json.dumps({'files': record['file_count'], 'bytes': record['bytes'],
                 'sha256': hashlib.sha256((OUT / 'PREPARATION-COPY-LIST.json').read_bytes()).hexdigest()}))
