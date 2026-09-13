"""Documentary byte archive only; never execute preserved inputs."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch')
AUTHOR = ROOT / 'vad-native-state-bridge-proposal01'
INDEPENDENT = ROOT / 'astra-native-state-bridge-qualification01'
PREPARATION = ROOT / 'vad-native-state-bridge-proof-proposal01'
DEST = ROOT / 'vad-native-state-bridge-final-proof01'
PINS_SHA = '2e126d468dc48da025894a1f90a40a7476eaa039496861c3e1cec37087123e07'
BRIDGE_SHA = 'b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2'
HARNESS_SHA = '2533c990e1396f5b8265e42d9073adc49e7bd035efda97098b8fbd3f4f22e389'
READER_SHA = '3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c'
GUARDS = ('metadata_wrappers_intact', 'realpath_wrapper_intact', 'content_access_closed',
    'reader_real_profile_closed', 'bridge_real_profile_absent')
SUFFIXES = {'.py', '.ps1', '.json', '.md', '.txt', '.log'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not getattr(before, 'st_file_attributes', 0) & 0x400,
        'Only ordinary contained documentary files are accepted')
    require(before.st_size <= 2 * 1024 * 1024, 'Documentary input size bound')
    data = path.read_bytes()
    after = path.lstat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) ==
        (after.st_ino, after.st_size, after.st_mtime_ns) and len(data) == after.st_size,
        'Documentary source changed during read')
    data.decode('utf-8-sig')
    return data


def parse(data):
    return json.loads(data.decode('utf-8-sig'))


def relative(text):
    require(type(text) is str and '\\' not in text, 'Noncanonical logical path')
    path = PurePosixPath(text)
    require(not path.is_absolute() and path.parts and all(part not in ('', '.', '..') for part in path.parts)
        and ':' not in text, 'Escaping logical path')
    require(path.as_posix() == text, 'Ambiguous logical path')
    return path


def files(directory):
    root_info = directory.lstat()
    require(stat.S_ISDIR(root_info.st_mode) and not getattr(root_info, 'st_file_attributes', 0) & 0x400,
        'Ordinary source directory required')
    result = []
    for path in sorted(directory.rglob('*')):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
            'Reparse tree entry refused')
        if stat.S_ISREG(info.st_mode):
            require(path.suffix in SUFFIXES or path.name == '.gitattributes', 'Unknown documentary suffix')
            result.append(path)
        else:
            require(stat.S_ISDIR(info.st_mode), 'Unexpected tree entry')
    require(len(result) <= 300, 'Documentary file-count bound')
    return result


def compare_runs(logical):
    summaries = []
    all_cases = []
    input_checks = []
    for owner in ('author', 'root'):
        def get(name):
            return parse(logical[owner + '/' + name])
        require(sha(logical[owner + '/PINS.json']) == PINS_SHA, 'Final pin bytes changed')
        pins = get('PINS.json')
        require(len(pins['files']) == 11, 'Expected eleven frozen source inputs')
        for entry in pins['files']:
            relative(entry['path'])
            data = logical[owner + '/' + entry['path']]
            require(sha(data) == entry['sha256'] and len(data) == entry['bytes'], 'Pinned source mismatch')
        run = 'bridge-preflight01/'
        report = get(run + 'stdout.json')
        native = get(run + 'NATIVE-RETURN.json')
        exit_record = get(run + 'actual-exit.json')
        outer = get(run + 'outer-tool-result.json')
        checked = get(run + 'checked-result.json')
        expected = get(run + 'EXPECTED-CASES.json')
        plan = get(run + 'plan.json')
        require(report['passed'] == 61 and report['failed'] == report['skipped'] == 0,
            'Synthetic case result mismatch')
        require(report['qualification_exit'] == native['native_exit'] == exit_record['native_exit'] == outer['exit_code'] == 0,
            'Actual exit mismatch')
        require(checked['complete'] is True and checked['stdout_sha256'] == sha(logical[owner + '/' + run + 'stdout.json']),
            'Checked result does not bind raw stdout')
        require(report['guard_integrity'] is True and report['startup_binding'] is True
            and all(report['guard_fields'][name] is True for name in GUARDS)
            and report['audit_denials'] == [] and logical[owner + '/' + run + 'stderr.log'] == b'',
            'Guard or stderr mismatch')
        require(exit_record['inputs_unchanged'] is True and report['bridge_sha256'] == BRIDGE_SHA
            and report['harness_sha256'] == HARNESS_SHA and report['reader_sha256'] == READER_SHA,
            'Executed source identities mismatch')
        cases = report['cases']
        require(len(cases) == 61 and len({item['name'] for item in cases}) == 61
            and [item['name'] for item in cases] == expected['cases']
            and all(item['status'] == 'passed' for item in cases), 'Exact case membership mismatch')
        require(len(plan['inputs']) == 5, 'Expected five copied source inputs')
        for entry in plan['inputs']:
            require(relative(entry['name']).name == entry['name'], 'Unexpected copied-input path')
            data = logical[owner + '/' + run + entry['name']]
            require(sha(data) == entry['sha256'], 'Executed copy changed')
            input_checks.append({'owner': owner, 'name': entry['name'], 'before_sha256': entry['sha256'],
                'after_sha256': sha(data), 'match': True})
        all_cases.append(cases)
        summaries.append({'owner': owner, 'passed': 61, 'failed': 0, 'skipped': 0,
            'elapsed_seconds': report['elapsed_seconds'], 'native_exit': native['native_exit'],
            'qualification_exit': report['qualification_exit'], 'actual_outer_exit': outer['exit_code'],
            'outer_tool_result_sha256': sha(logical[owner + '/' + run + 'outer-tool-result.json']),
            'stdout_sha256': sha(logical[owner + '/' + run + 'stdout.json']),
            'generated_INPUTS_final_sha256': sha(logical[owner + '/' + run + 'INPUTS.json']),
            'guard_fields': report['guard_fields']})
    require(all_cases[0] == all_cases[1], 'Author/root case records differ')
    return {'scope': 'Same 61 fake-port cases repeated; no native-model qualification',
        'distinct_cases': 61, 'exact_ordered_cases_equal': True, 'runs': summaries,
        'copied_input_checks': input_checks, 'original_pin_entries_checked_per_root': 11,
        'generated_INPUTS_limit': 'No separate pre-run hash was recorded for generated INPUTS.json itself',
        'cases': all_cases[0], 'native_qualified': False, 'release_approved': False}


def write_json(path, value):
    with path.open('xb') as output:
        output.write((json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))


def verify():
    manifest_bytes = read(DEST / 'SHA256.json')
    manifest = parse(manifest_bytes)
    paths = [entry['path'] for entry in manifest['files']]
    require(len(paths) == len(set(paths)) == manifest['payload_count'], 'Manifest membership mismatch')
    actual = {p.relative_to(DEST).as_posix() for p in files(DEST)}
    require(actual == set(paths) | {'SHA256.json'}, 'Missing or unlisted physical payload')
    for entry in manifest['files']:
        relative(entry['path'])
        data = read(DEST / entry['path'])
        require(len(data) == entry['bytes'] and sha(data) == entry['sha256'], 'Physical payload mismatch')
    tree = parse(read(DEST / 'SOURCE-TREE.json'))
    logical = {}
    objects = set()
    for entry in tree['sources']:
        relative(entry['logical_path'])
        require(entry['logical_path'] not in logical, 'Duplicate logical source')
        require(entry['object'] == 'objects/' + entry['sha256'] + '.txt', 'Object path mismatch')
        data = read(DEST / entry['object'])
        require(sha(data) == entry['sha256'] and len(data) == entry['bytes'], 'Logical source object mismatch')
        logical[entry['logical_path']] = data
        objects.add(entry['object'])
    require({p for p in actual if p.startswith('objects/')} == objects, 'Unmapped content object')
    require(compare_runs(logical) == parse(read(DEST / 'RUN-COMPARISON.json')), 'Derived run comparison mismatch')
    return {'verification_exit': 0, 'proof_path': str(DEST), 'logical_sources': len(logical),
        'unique_content_objects': len(objects), 'payload_count': len(paths), 'total_files': len(actual),
        'manifest_sha256': sha(manifest_bytes), 'no_unlisted_files': True,
        'all_logical_and_physical_hashes_match': True}


def build():
    require(not DEST.exists(), 'Fresh documentary proof required')
    inputs = []
    for directory, owner in ((AUTHOR, 'author'), (INDEPENDENT, 'root')):
        inputs.extend((path, owner + '/' + path.relative_to(directory).as_posix()) for path in files(directory))
    for name in ('BRIEF.md', 'REPORT.md', 'ROOT-REPORTED-OPERATIONS.json', 'build_verify.py'):
        inputs.append((PREPARATION / name, 'preparation/' + name))
    require(len(inputs) <= 300 and len({logical for _, logical in inputs}) == len(inputs), 'Input mapping bound')
    logical = {}
    sources = []
    objects = {}
    for path, name in inputs:
        data = read(path)
        require(sum(map(len, objects.values())) + len(data) <= 4 * 1024 * 1024, 'Archive byte bound')
        digest = sha(data)
        if digest in objects:
            require(objects[digest] == data, 'Digest collision')
        else:
            objects[digest] = data
        logical[name] = data
        sources.append({'logical_path': name, 'original_path': str(path), 'bytes': len(data),
            'sha256': digest, 'object': 'objects/' + digest + '.txt'})
    comparison = compare_runs(logical)
    DEST.mkdir()
    (DEST / 'objects').mkdir()
    for digest, data in sorted(objects.items()):
        with (DEST / 'objects' / (digest + '.txt')).open('xb') as output:
            output.write(data)
    write_json(DEST / 'SOURCE-TREE.json', {'logical_source_count': len(sources), 'sources': sources})
    write_json(DEST / 'RUN-COMPARISON.json', comparison)
    with (DEST / 'REPORT.md').open('xb') as output:
        output.write(logical['preparation/REPORT.md'])
    with (DEST / 'build_verify.py').open('xb') as output:
        output.write(logical['preparation/build_verify.py'])
    with (DEST / '.gitattributes').open('xb') as output:
        output.write(b'* -text\n')
    for entry, (original, name) in zip(sources, inputs, strict=True):
        require(read(original) == logical[name] == read(DEST / entry['object']), 'Copy changed source or object')
    write_json(DEST / 'COPY-VERIFICATION.json', {'verification_precedes_outer_seal': True,
        'original_and_object_bytes_match': True, 'logical_sources': len(sources),
        'unique_content_objects': len(objects), 'all_source_paths_recorded_in': 'SOURCE-TREE.json'})
    payloads = []
    for path in files(DEST):
        data = read(path)
        payloads.append({'path': path.relative_to(DEST).as_posix(), 'bytes': len(data), 'sha256': sha(data)})
    write_json(DEST / 'SHA256.json', {'schema': 1, 'excluded': ['SHA256.json'],
        'payload_count': len(payloads), 'files': payloads})
    return verify()


if __name__ == '__main__':
    require(sys.argv[1:] in (['--build'], ['--verify']), 'Use fixed --build or --verify mode')
    print(json.dumps(build() if sys.argv[1] == '--build' else verify(), indent=2))
