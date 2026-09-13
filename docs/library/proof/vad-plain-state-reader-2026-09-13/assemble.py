"""Documentary copy/hash/receipt validation only; execute no archived code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).absolute().parent
SCRATCH = OUT.parent
SHA = lambda raw: hashlib.sha256(raw).hexdigest()
SEALS = (
    ('vad-plain-state-reader-proposal01', 'preparation01', 26,
     'd2bf7531d5f89a50d80d7260e993954b81a56e4c6fa4457d08c770b8c728a0bf'),
    ('vad-plain-state-reader-vpr01-execution', 'failure-vpr01', 22,
     '89b90577f401955b4faa0d440118632b2b0cb2e4e7a1a976a702c85d7cbc008b'),
    ('vad-plain-state-reader-proposal02', 'preparation02', 25,
     '6c79c477cec73ca3b104ab9e8917ce96166328474ab7373a86cb3fba22a72b8a'),
    ('vad-plain-state-reader-vpr02-execution', 'failure-vpr02', 23,
     '771a592fe81078a18285253ddde50651ed54449dfab3202a00fadf659657c7dc'),
    ('vad-plain-state-reader-proposal03', 'preparation03', 25,
     '236a86c300a180281dabcad46f8ba371daa28e42cbf3032735013eeedca2a397'),
    ('vad-plain-state-reader-vpr03-execution', 'author-vpr03', 24,
     '2855097528e74a85f4f981777d513535fbbb9792b860eac9026ee929f1ffd9b6'),
)
ROOT_FILES = (
    'BRIEF.md', 'EXPECTED-CASES.json', 'fixed-plan.json', 'INPUTS.json',
    'launch.py', 'outer-tool-result.json', 'plain_state_reader.py', 'qualify_reader.py',
    'ROOT-ADMISSION.json', 'ROOT-ADMISSION.md', 'run-root.ps1', 'SOURCE-BINDINGS.json',
    'context/fixed_converter.py.txt', 'context/fixed-factory.proposal.txt',
    'outer/20260913T1648294852287Z/actual-exit.json',
    'outer/20260913T1648294852287Z/command.json',
    'outer/20260913T1648294852287Z/stderr.log',
    'outer/20260913T1648294852287Z/stdout.log',
    'runs/vpr04/actual-exit.json', 'runs/vpr04/checked-result.json',
    'runs/vpr04/fixed-plan.json', 'runs/vpr04/INPUTS.json',
    'runs/vpr04/launch-plan.json', 'runs/vpr04/plain_state_reader.py',
    'runs/vpr04/qualify_reader.py', 'runs/vpr04/root-admission.json',
    'runs/vpr04/stderr.log', 'runs/vpr04/stdout.json',
)

def save(name, obj):
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(obj, indent=2) + '\n')

copied = []
def copy(source, relative, expected=None, size=None):
    if source.is_symlink() or not source.is_file():
        raise ValueError('Only regular known documentary files')
    raw = source.read_bytes()
    if expected is not None:
        assert SHA(raw) == expected
    if size is not None:
        assert len(raw) == size
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    assert target.read_bytes() == raw
    copied.append({'source': str(source), 'path': relative, 'bytes': len(raw),
                   'sha256': SHA(raw)})

verified_seals = []
for directory, destination, count, digest in SEALS:
    root = SCRATCH / directory
    manifest_raw = (root / 'SHA256.json').read_bytes()
    assert SHA(manifest_raw) == digest
    manifest = json.loads(manifest_raw)
    assert manifest['payload_count'] == count and len(manifest['files']) == count
    assert len({row['path'] for row in manifest['files']}) == count
    for row in manifest['files']:
        relative = Path(row['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        copy(root / relative, destination + '/' + relative.as_posix(), row['sha256'], row['bytes'])
    copy(root / 'SHA256.json', destination + '/SHA256.json', digest)
    expected = {row['path'] for row in manifest['files']} | {'SHA256.json'}
    actual = {path.relative_to(OUT / destination).as_posix()
              for path in (OUT / destination).rglob('*') if path.is_file()}
    assert actual == expected
    verified_seals.append({'source': directory, 'copy': destination, 'payload_count': count,
                           'manifest_sha256': digest, 'all_bytes_match': True,
                           'exact_membership': True})
root = SCRATCH / 'astra-vad-reader-synthetic01'
actual_root_files = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
assert actual_root_files == set(ROOT_FILES) and len(ROOT_FILES) == 28
for name in ROOT_FILES:
    copy(root / name, 'root-vpr04/' + name)

def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))

author = read('author-vpr03/run-vpr03/stdout.json')
independent = read('root-vpr04/runs/vpr04/stdout.json')
expected_ids = read('preparation03/EXPECTED-CASES.json')
assert len(expected_ids) == len(set(expected_ids)) == 82
assert author['cases'] == independent['cases']
assert [row['case'] for row in author['cases']] == expected_ids
for report in (author, independent):
    assert (report['case_count'], report['passed'], report['failed'], report['skipped']) == (82, 82, 0, 0)
    assert all(row['passed'] is True for row in report['cases'])
    assert report['qualification_exit'] == 0
    guard = report['guard']
    assert guard['valid'] and not guard['unexpected_events']
    assert guard['inputs_unchanged'] and guard['lexical_wrappers_installed']
    assert not guard['heavy_preloaded'] and not guard['heavy_after']
    assert not report['actual_artifact_access'] and not report['model_constructed']
assert author['input_sha256'] == independent['input_sha256']
assert author['canonical_fixture_sha256'] == independent['canonical_fixture_sha256']
assert author['canonical_fixture_bytes'] == independent['canonical_fixture_bytes'] == 5896708
for name, digest in independent['input_sha256'].items():
    assert SHA((OUT / 'root-vpr04/runs/vpr04' / name).read_bytes()) == digest
    assert SHA((OUT / 'preparation03' / name).read_bytes()) == digest
admission = read('root-vpr04/ROOT-ADMISSION.json')
assert len(admission['source_hashes']) == 10
for name, digest in admission['source_hashes'].items():
    assert SHA((OUT / 'root-vpr04' / name).read_bytes()) == digest
    assert (OUT / 'root-vpr04' / name).read_bytes() == (OUT / 'preparation03' / name).read_bytes()
assert (OUT / 'root-vpr04/run-root.ps1').read_bytes() == (OUT / 'preparation03/run-root.ps1').read_bytes()
for name, field in (
    ('author-vpr03/run-vpr03/actual-exit.json', 'actual_child_exit'),
    ('author-vpr03/outer-vpr03/actual-exit.json', 'actual_outer_exit'),
    ('author-vpr03/ACTUAL-EXIT.json', 'actual_invocation_exit'),
    ('author-vpr03/TOOL-RESULT.json', 'exit_code'),
    ('root-vpr04/runs/vpr04/actual-exit.json', 'actual_child_exit'),
    ('root-vpr04/outer/20260913T1648294852287Z/actual-exit.json', 'actual_outer_exit'),
    ('root-vpr04/outer-tool-result.json', 'actual_outer_tool_exit')):
    assert read(name)[field] == 0
failure = read('failure-vpr02/run-vpr02/stdout.json')
assert (failure['passed'], failure['failed'], failure['skipped']) == (75, 1, 0)
assert failure['guard']['valid'] and failure['qualification_exit'] == 1
assert [row['case'] for row in failure['cases'] if not row['passed']] == ['json_deep-nesting']
assert (OUT / 'failure-vpr01/run-vpr01/stdout.json').read_bytes() == b''
assert 'import:encodings.utf_16_le' in (OUT / 'failure-vpr01/run-vpr01/stderr.log').read_text()
for version in ('01', '02'):
    assert read('failure-vpr'+version+'/run-vpr'+version+'/actual-exit.json')['actual_child_exit'] == 1
    assert read('failure-vpr'+version+'/outer-vpr'+version+'/actual-exit.json')['actual_outer_exit'] == 1
    assert read('failure-vpr'+version+'/ACTUAL-EXIT.json')['actual_invocation_exit'] == 1
save('COPY-MANIFEST.json', {'files': copied, 'copied_payload_count': len(copied),
                           'source_files_unchanged_and_copy_bytes_verified': True})
save('VALIDATION.json', {'checked_utc': datetime.now(timezone.utc).isoformat(),
                        'prior_seals': verified_seals, 'root_exact_file_count': 28,
                        'distinct_case_count': 82, 'successful_runs': 2,
                        'case_sequences_identical': True, 'source_and_protocol_identical': True,
                        'author_seconds': author['elapsed_seconds'],
                        'root_seconds': independent['elapsed_seconds'],
                        'all_success_actual_exits': 0, 'valid_guards': True,
                        'prior_failures_preserved': True,
                        'actual_model_or_artifact_qualified': False})
print(json.dumps({'copied_payloads': len(copied), 'prior_seals_verified': 6,
                  'root_files': 28, 'distinct_cases': 82, 'successful_runs': 2,
                  'exact_membership_and_bytes_verified': True}))
