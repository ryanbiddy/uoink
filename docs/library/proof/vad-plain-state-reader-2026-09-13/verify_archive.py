"""Read-only documentary verifier; never import or execute archived source."""
import argparse
import hashlib
import json
from pathlib import Path

root = Path(__file__).absolute().parent
parser = argparse.ArgumentParser()
parser.add_argument('--check-source-disk', action='store_true')
args = parser.parse_args()
sha = lambda raw: hashlib.sha256(raw).hexdigest()
manifest_raw = (root / 'SHA256.json').read_bytes()
manifest = json.loads(manifest_raw)
expected = {row['path'] for row in manifest['files']}
assert len(expected) == len(manifest['files']) == manifest['payload_count']
actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
assert actual == expected | {'SHA256.json'}
for row in manifest['files']:
    relative = Path(row['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    path = root / relative
    assert not path.is_symlink()
    raw = path.read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
validation = json.loads((root / 'VALIDATION.json').read_bytes())
for original in validation['prior_seals']:
    child = root / original['copy']
    raw = (child / 'SHA256.json').read_bytes()
    assert sha(raw) == original['manifest_sha256']
    nested = json.loads(raw)
    assert nested['payload_count'] == original['payload_count']
    names = {row['path'] for row in nested['files']}
    actual_names = {path.relative_to(child).as_posix() for path in child.rglob('*') if path.is_file()}
    assert len(names) == len(nested['files']) == original['payload_count']
    assert actual_names == names | {'SHA256.json'}
    for row in nested['files']:
        content = (child / row['path']).read_bytes()
        assert len(content) == row['bytes'] and sha(content) == row['sha256']
copies = json.loads((root / 'COPY-MANIFEST.json').read_bytes())
for row in copies['files']:
    content = (root / row['path']).read_bytes()
    assert len(content) == row['bytes'] and sha(content) == row['sha256']
    if args.check_source_disk:
        assert Path(row['source']).read_bytes() == content
author = json.loads((root / 'author-vpr03/run-vpr03/stdout.json').read_bytes())
independent = json.loads((root / 'root-vpr04/runs/vpr04/stdout.json').read_bytes())
assert author['cases'] == independent['cases']
assert len(author['cases']) == len({row['case'] for row in author['cases']}) == 82
assert all(row['passed'] is True for row in author['cases'])
assert author['input_sha256'] == independent['input_sha256']
assert author['canonical_fixture_sha256'] == independent['canonical_fixture_sha256']
print(json.dumps({'payload_count': manifest['payload_count'],
                  'manifest_sha256': sha(manifest_raw), 'exact_membership': True,
                  'all_payloads_verified': True, 'original_seals_verified': 6,
                  'copied_source_disk_compared': args.check_source_disk,
                  'distinct_cases': 82, 'successful_runs': 2}))
