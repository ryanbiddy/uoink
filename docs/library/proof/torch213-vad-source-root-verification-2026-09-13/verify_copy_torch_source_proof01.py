"""Root documentary verification and exact copy; no collected source execution."""
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
SOURCE = ROOT / '_scratch/torch213-vad-source-final-proof01'
DEST = ROOT / 'docs/library/proof/torch213-vad-source-2026-09-13'
EXPECTED = '290a815003a3593d0685e5570c61feccf6884edada9dae80f5cc0887665b3a74'

def read(path):
    path = Path(path)
    assert path.is_relative_to(ROOT)
    for ancestor in (path, *path.parents):
        if not ancestor.is_relative_to(ROOT):
            break
        info = ancestor.lstat()
        assert not stat.S_ISLNK(info.st_mode)
        assert not getattr(info, 'st_file_attributes', 0) & 0x400
    assert stat.S_ISREG(info := path.stat().st_mode)
    assert path.stat().st_size <= 4 * 1024 * 1024
    return path.read_bytes()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def doc(path):
    return json.loads(read(path).decode('utf-8-sig'))

seal = read(SOURCE / 'SHA256.json')
assert sha(seal) == EXPECTED
rows = doc(SOURCE / 'SHA256.json')['files']
assert len(rows) == 199
names = {row['path'] for row in rows}
assert len(names) == len(rows)
assert {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob('*') if p.is_file()} == names | {'SHA256.json'}
for row in rows:
    raw = read(SOURCE / row['path'])
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256'], row['path']
copies = doc(SOURCE / 'COPY-VERIFICATION.json')['copied_file_records']
assert len(copies) == 197
for row in copies:
    original = read(Path(row['original']))
    assert original == read(SOURCE / row['path'])
    assert len(original) == row['bytes'] and sha(original) == row['sha256']

author = doc(SOURCE / 'proposal/collector-preflight01/stdout.json')
independent = doc(SOURCE / 'independent/stdout.json')
assert author['cases'] == independent['cases']
assert len(author['cases']) == len({row['name'] for row in author['cases']}) == 40
assert all(row['status'] == 'passed' for row in author['cases'])
comparison = doc(SOURCE / 'proposal/INDEPENDENT-CASE-COMPARISON02.json')
assert comparison['cases'] == author['cases']
assert comparison['native_exits'] == comparison['actual_outer_exits'] == [0, 0]
assert comparison['author_stdout_sha256'] == sha(read(SOURCE / 'proposal/collector-preflight01/stdout.json'))
assert comparison['independent_stdout_sha256'] == sha(read(SOURCE / 'independent/stdout.json'))

pairs = 0
for label, count, total in (('resolve01', 2, 6257), ('sources01', 21, 1050728)):
    directory = SOURCE / 'proposal/retrievals' / label
    receipt = doc(directory / 'receipt.json')
    assert receipt['intended_exit'] == 0 and receipt['response_body_bytes'] == total
    assert receipt['binding']['commit'] == 'cf30153c4c131c8164ee7798e5022d810682e2cb'
    responses = sorted(directory.glob('response-*.json'))
    assert len(responses) == len(receipt['requests']) == count
    size = 0
    for file, recorded in zip(responses, receipt['requests'], strict=True):
        response = doc(file)
        assert response == recorded
        assert response['http_status'] == 200 and response['body_complete'] is True and response['truncated'] is False
        body = read(directory / response['body_file'])
        assert len(body) == response['body_bytes'] and sha(body) == response['body_sha256']
        size += len(body)
        pairs += 1
    assert size == total
    launch_exit = doc(SOURCE / 'proposal' / (label + '-launch') / 'exit.json')
    assert launch_exit['native_exit'] == 0 and launch_exit['inputs_unchanged'] is True

timestamps = []
def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith('_utc') and isinstance(item, str):
                timestamps.append(item)
            walk(item)
    elif isinstance(value, list):
        for item in value:
            walk(item)
json_files = sorted((SOURCE / 'proposal/retrievals').rglob('*.json'))
for file in json_files:
    walk(doc(file))
assert len(json_files) == 48 and len(timestamps) == 119
assert all(value.endswith('+00:00') for value in timestamps)

assert not DEST.exists(), 'Fresh destination required'
DEST.mkdir()
for name in sorted(names | {'SHA256.json'}):
    raw = read(SOURCE / name)
    target = DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    assert read(target) == raw == read(SOURCE / name)
assert {p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file()} == names | {'SHA256.json'}
print(json.dumps({'payloads': len(rows), 'original_copies_verified': len(copies),
                  'ordered_passing_cases_each_run': 40, 'http_body_pairs_verified': pairs,
                  'utc_strings_verified': len(timestamps), 'copied_files': len(names) + 1,
                  'manifest_sha256': sha(seal)}))
