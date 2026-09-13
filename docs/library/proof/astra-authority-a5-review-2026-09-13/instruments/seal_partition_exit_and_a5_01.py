"""Copy only enumerated documentary evidence and verify every preserved byte."""
from pathlib import Path, PurePosixPath
import difflib
import hashlib
import json
import stat
import sys
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / '_scratch'
PROOF = ROOT / 'docs/library/proof'
PARTITION = PROOF / 'partition-exit-repair-2026-09-13'
AUTHORITY = PROOF / 'astra-authority-a5-review-2026-09-13'
ARCHIVE = SCRATCH / 'authority-a5-review-before01'
PRELIMINARY = PROOF / 'mirror-tree09-preflight-2026-09-13'
ALLOWED_SUFFIXES = {'.py', '.ps1', '.json', '.jsonl', '.md', '.txt', '.diff', '.xml', '.log'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative_name(value):
    value = value.replace('\\', '/')
    path = PurePosixPath(value)
    assert value and not path.is_absolute() and '..' not in path.parts and ':' not in value
    assert path.suffix.lower() in ALLOWED_SUFFIXES or path.name == '.gitattributes'
    return path.as_posix()


def checked_file(path):
    assert path.is_relative_to(ROOT), 'Source escaped the checkout'
    current = path
    while True:
        info = current.lstat()
        assert not stat.S_ISLNK(info.st_mode)
        assert not getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
        if current == ROOT:
            break
        current = current.parent
    assert path.is_file()
    return path.read_bytes()


def checked_existing_manifest(folder):
    manifest_path = folder / 'SHA256.json'
    manifest_bytes = checked_file(manifest_path)
    manifest = json.loads(manifest_bytes.decode('utf-8-sig'))
    expected = {}
    for name, record in manifest['files'].items():
        name = relative_name(name)
        data = checked_file(folder / name)
        assert len(data) == record['bytes'] and digest(data) == record['sha256'], name
        expected[name] = {'bytes': len(data), 'sha256': digest(data)}
    actual = {path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()}
    assert actual == set(expected) | {'SHA256.json'}, 'Existing archive has unmanifested files'
    return {'manifest_sha256': digest(manifest_bytes), 'payloads': len(expected), 'files': expected}


def assert_unit(folder, expected):
    suites = list(ET.fromstring(checked_file(folder / 'tests.xml')).iter('testsuite'))
    assert sum(int(s.get('tests')) for s in suites) == expected
    assert all(int(s.get('failures')) == int(s.get('errors')) == int(s.get('skipped')) == 0 for s in suites)
    result = read_json(folder / 'results.json')
    assert len(result) == 1 and result[0]['exit'] == 0


assert not PARTITION.exists() and not AUTHORITY.exists(), 'Fresh seal paths required'
assert digest(checked_file(SCRATCH / 'partition_exit_contract.py')) == '2cf1bc8b0e52a15596cfed30aaee3f51ea0c4ad1ed02f338d5a210c1a0d6aa09'
assert digest(checked_file(SCRATCH / 'test_partition_exit_contract.py')) == '0331758b9370894843eaf52f64d44f5eba6ebe27e8e733afea1a3fd7a3277469'
assert_unit(SCRATCH / 'partition-exit-unit01', 51)
assert_unit(SCRATCH / 'partition-exit-unit02', 53)
assert_unit(SCRATCH / 'astra-partition-exit-contract01', 53)
preliminary_before = checked_existing_manifest(PRELIMINARY)
assert preliminary_before['payloads'] == 54
archive_before = checked_existing_manifest(ARCHIVE)
worker_before = checked_existing_manifest(ARCHIVE / 'worker-proof')

# Exact filenames from the read-only inventories; no broad scratch copying.
RUN_FILES = ['results.json', 'tests.log', 'tests.xml', 'guard/ig_paths.py', 'guard/sitecustomize.py']
FOLDERS = {
    'partition-exit-unit01': RUN_FILES,
    'partition-exit-unit02': RUN_FILES,
    'astra-partition-exit-contract01': RUN_FILES,
    'partition-contract-double01': RUN_FILES,
    'partition-contract-shutdown01': RUN_FILES,
    'partition-exit-unit01-launch': ['command.json', 'partition_exit_contract.py', 'PARTITION-EXIT-CONTRACT-REVIEW-2026-09-13.md',
                                   'result.json', 'run_partition_exit_contract01.ps1', 'test_partition_exit_contract.py'],
    'partition-exit-unit02-launch': ['command.json', 'helper-correction.diff', 'partition_exit_contract.py',
                                   'PARTITION-EXIT-CONTRACT-REVIEW-2026-09-13.md', 'result.json',
                                   'run_partition_exit_contract01.ps1', 'test_partition_exit_contract.py', 'tests-correction.diff'],
    'partition-exit-receipt-review01': ['reader.py', 'result.json', 'SHA256.json', 'summary.json'],
    'partition-contract-double01-receipt': ['launcher-result.json', 'mirror-state.jsonl', 'partition/membership.json', 'partition/reports.jsonl', 'partition/session.json'],
    'partition-contract-shutdown01-receipt': ['launcher-result.json', 'mirror-state.jsonl', 'partition/membership.json', 'partition/reports.jsonl', 'partition/session.json'],
    'partition-exit-wiring01': ['partition_exit_contract.py', 'result.json', 'run_partitioned_mirror_tree09.py',
                              'seal_partitioned_mirror_tree09.py', 'verify_partition_exit_wiring01.py'],
    'partition-exit-repair-before01': ['MIRROR-COMBINED-TREE09-BRIEF-2026-09-13.md', 'run_partitioned_mirror_tree09.py', 'seal_partitioned_mirror_tree09.py'],
}
INSTRUMENTS = [
    'partition_exit_contract.py', 'test_partition_exit_contract.py', 'run_partition_exit_contract01.ps1',
    'run_partition_exit_astra01.ps1', 'run_partition_contract_smoke.ps1', 'verify_partition_exit_wiring01.py',
    'test_phase4_partition_double_failure_smoke.py', 'test_partition_shutdown_smoke.py', 'partition_shutdown_failure_plugin.py',
    'partition_receipt_plugin.py', 'mirror_state_receipt_plugin.py', 'integrator_verify.py',
    'run_partitioned_mirror_tree09.py', 'seal_partitioned_mirror_tree09.py', 'run_complete_mirror_tree09_durable.py',
    'run_partitioned_repaired_tree.py', 'run_complete_candidate_durable.py',
    'run_partitioned_mirror_tree09.py.diff', 'run_complete_mirror_tree09_durable.py.diff',
    'mirror-tree09-instrument-preparation.json', 'prepare_mirror_tree09_observer.py',
    'MIRROR-COMBINED-TREE09-BRIEF-2026-09-13.md', 'MIRROR-PARTITION-EXIT-REPAIR-BRIEF-2026-09-13.md',
    'PARTITION-EXIT-CONTRACT-REVIEW-2026-09-13.md', Path(__file__).name,
]
partition_sources = {}
for folder, names in FOLDERS.items():
    actual = {path.relative_to(SCRATCH / folder).as_posix() for path in (SCRATCH / folder).rglob('*') if path.is_file()}
    assert actual == set(names), 'Unexpected files in named evidence directory: ' + folder
    for name in names:
        partition_sources['evidence/' + folder + '/' + relative_name(name)] = SCRATCH / folder / name
for name in INSTRUMENTS:
    partition_sources['instruments/' + relative_name(name)] = SCRATCH / name
partition_sources['reviews/MIRROR-TREE09-OBSERVER-REVIEW-2026-09-13.md'] = ROOT / 'docs/library/MIRROR-TREE09-OBSERVER-REVIEW-2026-09-13.md'

authority_sources = {name: ARCHIVE / name for name in archive_before['files']}
authority_sources['ARCHIVE-ORIGINAL-SHA256.json'] = ARCHIVE / 'SHA256.json'
authority_sources['reviews/ASTRA-AUTHORITY-A5-REVIEW-2026-09-13.md'] = ROOT / 'docs/library/ASTRA-AUTHORITY-A5-REVIEW-2026-09-13.md'
authority_sources['reviews/MIRROR-AUTHORITY-ASTRA-REPAIR03-BRIEF-2026-09-13.md'] = ROOT / 'docs/library/MIRROR-AUTHORITY-ASTRA-REPAIR03-BRIEF-2026-09-13.md'
authority_sources['instruments/' + Path(__file__).name] = Path(__file__).resolve()


def prepare(sources):
    result = {}
    for name, source in sources.items():
        relative_name(name)
        data = checked_file(source)
        result[name] = {'source': source, 'data': data, 'bytes': len(data), 'sha256': digest(data)}
    return result


partition_inputs = prepare(partition_sources)
authority_inputs = prepare(authority_sources)


def seal(destination, inputs, context, extra=None):
    destination.mkdir(exist_ok=False)
    (destination / '.gitattributes').write_bytes(b'* -text\n')
    inventory = {}
    for name, row in inputs.items():
        target = destination / name
        assert target.is_relative_to(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(row['data'])
        assert target.read_bytes() == row['data']
        assert digest(checked_file(row['source'])) == row['sha256'], 'Source changed while copied'
        inventory[name] = {'source': row['source'].relative_to(ROOT).as_posix(), 'bytes': row['bytes'], 'sha256': row['sha256']}
    if extra:
        for name, data in extra.items():
            target = destination / relative_name(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
    (destination / 'COPY-VERIFICATION.json').write_text(json.dumps({
        'scope': 'Documentary copy and hash verification only; no product execution',
        'release_ready': False, 'copied_files': len(inventory), 'every_copy_sha256_verified': True,
        'context': context, 'files': inventory,
    }, indent=2) + '\n', encoding='utf8')
    files = {path.relative_to(destination).as_posix(): {'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes())}
             for path in sorted(destination.rglob('*')) if path.is_file()}
    manifest = {'algorithm': 'sha256', 'files': files}
    (destination / 'SHA256.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    verified = checked_existing_manifest(destination)
    return {'path': str(destination), 'copied_files': len(inventory), 'payloads': len(files),
            'manifest_sha256': verified['manifest_sha256'], 'every_payload_verified': True}


diffs = {}
for name in ['run_partitioned_mirror_tree09.py', 'seal_partitioned_mirror_tree09.py', 'MIRROR-COMBINED-TREE09-BRIEF-2026-09-13.md']:
    before = partition_inputs['evidence/partition-exit-repair-before01/' + name]['data'].decode('utf-8-sig')
    after = partition_inputs['instruments/' + name]['data'].decode('utf-8-sig')
    diff = ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                      fromfile='before/' + name, tofile='after/' + name))
    assert diff, 'Expected instrument repair diff is empty'
    diffs['diffs/' + name + '.diff'] = diff.encode('utf8')
partition_result = seal(PARTITION, partition_inputs, {
    'unit01_passed': 51, 'unit02_passed': 53, 'independent_unit_passed': 53,
    'deliberate_smoke_failures_preserved': True, 'shutdown_disagreement_refused': True,
    'original_tree08_counts_unchanged': {'passed': 2675, 'failed': 51, 'skipped': 3},
    'preliminary_seal': {key: preliminary_before[key] for key in ('manifest_sha256', 'payloads')},
}, diffs)
authority_result = seal(AUTHORITY, authority_inputs, {
    'snapshot': 'authority-a5-review-before01', 'source_payloads': archive_before['payloads'],
    'original_manifest_preserved_as': 'ARCHIVE-ORIGINAL-SHA256.json',
    'original_manifest_sha256': archive_before['manifest_sha256'],
    'worker_manifest_sha256': worker_before['manifest_sha256'],
    'proposal_accepted': False, 'active_worker_accessed': False,
})
assert checked_existing_manifest(PRELIMINARY) == preliminary_before
assert checked_existing_manifest(ARCHIVE) == archive_before
assert checked_existing_manifest(ARCHIVE / 'worker-proof') == worker_before
receipt = {'partition': partition_result, 'authority': authority_result,
           'preliminary_54_payload_seal_unchanged': True, 'frozen_archive_unchanged': True,
           'product_execution': False, 'git_stage_or_commit': False}
output = SCRATCH / 'partition-exit-and-a5-seal01.json'
with output.open('x', encoding='utf8') as stream:
    stream.write(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
