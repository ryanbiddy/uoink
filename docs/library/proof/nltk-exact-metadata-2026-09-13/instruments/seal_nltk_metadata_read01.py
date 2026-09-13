"""Seal exact retained reader evidence; no artifact read, imports or test rerun."""
from pathlib import Path, PurePosixPath
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
BASE = ROOT / '_scratch/nltk-local-metadata-reader01'
OUT = ROOT / '_scratch/nltk-metadata-read-proof01'
MANIFEST_SHA = '3f570a81d22b348e58e000097c122d0c6caf18825366813302b1969390ca8b3e'

def read(path):
    with path.open('rb') as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    return raw

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

manifest = read(BASE / 'INPUT-HASHES.json')
assert sha(manifest) == MANIFEST_SHA
source_rows = json.loads(manifest)
assert len(source_rows) == 11
payloads = {'preparation/INPUT-HASHES.json': manifest, '.gitattributes': b'* -text\n'}
for row in source_rows:
    name = row['path']
    rel = PurePosixPath(name)
    assert name == rel.as_posix() and not rel.is_absolute() and '..' not in rel.parts
    assert '\\' not in name and ':' not in name
    raw = read(BASE / name)
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    key = 'preparation/' + name
    assert key not in payloads
    payloads[key] = raw
for name in ('plan.json', 'actual-native-exit.json', 'result.json', 'stdout.log', 'stderr.log'):
    payloads['launch/' + name] = read(BASE / 'launch-read01' / name)
for name in ('receipt.json', 'nltk-local-METADATA.txt'):
    payloads['results/' + name] = read(BASE / 'results/read01' / name)
payloads['actual-tool.json'] = read(ROOT / '_scratch/NLTK-LOCAL-METADATA-READ01-ACTUAL.json')
payloads['root-admission.json'] = read(ROOT / '_scratch/GRAPH02-AND-NLTK-READ01-ROOT-ADMISSION.json')
payloads['instruments/seal_nltk_metadata_read01.py'] = read(Path(__file__))
assert len(payloads) == 23
actual = json.loads(payloads['actual-tool.json'])
launch = json.loads(payloads['launch/result.json'])
native = json.loads(payloads['launch/actual-native-exit.json'])
receipt = json.loads(payloads['results/receipt.json'])
assert actual['exit_code'] == launch['actual_native_exit'] == launch['intended_outer_exit'] == native['actual_native_exit'] == receipt['exit'] == 0
assert launch['instrumentation_verdict'] == 'VALID' and launch['postcheck_error'] is None
assert launch['input_hashes_before'] == launch['input_hashes_after'] == source_rows
assert payloads['launch/stderr.log'] == b''
for row in launch['process_log_checks']:
    raw = payloads['launch/' + row['path']]
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
assert receipt['status'] == 'PASS' and receipt['guard_violations'] == []
assert receipt['artifact_verified_in_this_invocation'] is True
assert receipt['runtime_accepted'] is receipt['model_execution'] is receipt['wheel_member_imports'] is False
assert receipt['archive']['members'] == receipt['archive']['record_rows'] == 512
assert receipt['archive']['other_payload_record_hashes_recomputed'] is False
metadata = payloads['results/nltk-local-METADATA.txt']
assert sha(metadata) == receipt['metadata_sha256'] == '58ba0717917015b5fd7a2416d52d2ab7952eacfddcbe22797cbb566fba864234'
assert len(metadata) == receipt['metadata_bytes'] == 3245
assert receipt['exact_version_only_transformation'] is True
assert metadata == payloads['preparation/inputs/upstream-METADATA.txt'].replace(b'Version: 3.10.3\n', b'Version: 3.10.3+uoink.pathsec1\n', 1)
assert not OUT.exists()
OUT.mkdir()
for name, raw in sorted(payloads.items()):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
rows = [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(payloads.items())]
seal = (json.dumps({'payload_count': len(rows), 'payload_bytes': sum(row['bytes'] for row in rows), 'files': rows}, indent=2) + '\n').encode()
with (OUT / 'SHA256.json').open('xb') as stream:
    stream.write(seal)
print(json.dumps({'payloads': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'seal': sha(seal), 'tests_executed': 0, 'artifact_read_by_sealer': False}))
