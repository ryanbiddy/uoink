"""Documentary byte archive only. Never execute or import preserved sources."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch')
AUTHOR = ROOT / 'vad-owned-factory-port-proposal01'
INDEPENDENT = ROOT / 'astra-owned-factory-qualification01'
PREPARATION = ROOT / 'vad-owned-factory-proof-proposal01'
DEST = ROOT / 'vad-owned-factory-final-proof01'
ROOTS = {'author': AUTHOR, 'root': INDEPENDENT, 'preparation': PREPARATION}
PINS_SHA = 'bd7c9375e5c3e4678969a1746a99aab47109fa3ae47c1c998287d9dd9e19f2f1'
CONTROL_SHA = '154aac6563f86c40a3ef3c55616f0d9f6961192e7f4a9d6177c24aa0acf1f0d6'
ADMISSIONS = {'author': '25035bd7ba064ae4d8dd15d95d6206ac7f329e4582e5c58da1bd91556ebf6efa',
    'root': '7572c61d525ece445064d109fd43134c644d5045e1e31d27f0595cbbfb2d140e'}
STDOUTS = {'author': 'd2c4321b31abd0181a58e51064414b24e2918e1b0f98480a951daa220a96fd75',
    'root': '3e14cb7e203c9e1990801c400aaf2282c23d4d10d15738b01da12c15e1ae4f3b'}
GUARDS = ('metadata_wrappers_intact', 'realpath_wrapper_intact', 'content_access_closed',
    'reader_real_profile_closed', 'real_profile_attributes_absent', 'owned_runtime_closed_after_cases',
    'implementation_methods_intact', 'implementation_helpers_intact', 'native_packages_absent',
    'environment_restored')
COPIES = {'plain_state_reader.py': 'context/plain_state_reader.py',
    'state_bridge.py': 'context/state_bridge.py', 'owned_cpu_tensor_port.py': 'context/owned_cpu_tensor_port.py',
    'model_binding_registry.py': 'model_binding_registry.py', 'owned_factory_port.py': 'owned_factory_port.py',
    'owned_guard.py': 'context/owned_guard.py', 'fake_torch_support.py': 'fake_torch_support.py',
    'literal_parity.py': 'literal_parity.py', 'fixed-factory.proposal.txt': 'context/fixed-factory.proposal.txt',
    'owned-pyannote.reference.txt': 'context/owned-pyannote.reference.txt',
    'qualify_factory.py': 'qualify_factory.py', 'EXPECTED-CASES.json': 'EXPECTED-CASES.json'}
EXECUTED_SHA = {
    'owned_factory_port.py': '2569853c7634b795e3d2cf717129ec3dbc4e11d96ddb347098dcc4fbc532f0d4',
    'model_binding_registry.py': '48567add0f0ac2ac9140e9aa86b06f077454c98e2f0773100da5ba070f7b3deb',
    'qualify_factory.py': '162b7a297b0a94ef579a3ba0590406417bd91b4882bd0747e70f9a4365ebf1c7',
    'plain_state_reader.py': '3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c',
    'state_bridge.py': 'b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2',
    'owned_cpu_tensor_port.py': 'ac9eb28194723ffaf2d98bb2cd691a7b27b0a1638694fdfd8cb198c3084e8964'}
SUFFIXES = {'.py', '.ps1', '.json', '.md', '.txt', '.log'}
MAX_FILES = 300
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_UNIQUE_BYTES = 4 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse(data):
    return json.loads(data.decode('utf-8-sig'))


def relative(text):
    require(type(text) is str and '\\' not in text and ':' not in text, 'Noncanonical logical path')
    path = PurePosixPath(text)
    require(not path.is_absolute() and path.parts
        and all(part not in ('', '.', '..') for part in path.parts)
        and path.as_posix() == text, 'Escaping or ambiguous logical path')
    return path


def ordinary_ancestors(path):
    for parent in reversed(path.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, 'st_file_attributes', 0) & 0x400, 'Reparse or non-directory ancestor')


def read(path):
    ordinary_ancestors(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not getattr(before, 'st_file_attributes', 0) & 0x400,
        'Ordinary documentary file required')
    require(before.st_size <= MAX_FILE_BYTES, 'Documentary file byte bound')
    data = path.read_bytes()
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns) ==
        (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns)
        and len(data) == after.st_size, 'Documentary file changed during read')
    data.decode('utf-8-sig')
    return data


def files(directory):
    ordinary_ancestors(directory)
    result, pending, entries = [], [directory], 0
    while pending:
        current = pending.pop()
        info = current.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, 'st_file_attributes', 0) & 0x400, 'Ordinary directory required')
        for path in sorted(current.iterdir()):
            entries += 1
            require(entries <= 2 * MAX_FILES, 'Documentary tree entry bound')
            info = path.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Reparse tree entry refused')
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode)
                    and (path.suffix in SUFFIXES or path.name == '.gitattributes'), 'Unknown documentary file')
                result.append(path)
                require(len(result) <= MAX_FILES, 'Documentary file count bound')
    return sorted(result)


def compare_runs(logical):
    summaries, case_sets, copy_checks = [], [], []
    for owner in ('author', 'root'):
        prefix = owner + '/'
        run = 'factory-preflight01/'
        def data(name): return logical[prefix + name]
        def get(name): return parse(data(name))
        require(sha(data('PINS.json')) == PINS_SHA, 'Original PINS changed')
        pins = get('PINS.json')
        require(pins['file_count'] == len(pins['files']) == 31, 'Original 31-input membership')
        require(len({entry['path'] for entry in pins['files']}) == 31, 'Duplicate pin path')
        for entry in pins['files']:
            relative(entry['path'])
            payload = data(entry['path'])
            require(len(payload) == entry['bytes'] and sha(payload) == entry['sha256'], 'Pinned source mismatch')
        require(sha(data(run + 'stdout.json')) == STDOUTS[owner], 'Raw stdout changed')
        report, native, exits = get(run + 'stdout.json'), get(run + 'NATIVE-RETURN.json'), get(run + 'actual-exit.json')
        checked, plan, control = get(run + 'checked-result.json'), get(run + 'plan.json'), get(run + 'INPUTS.json')
        outer_path = run + 'outer-tool-result.json' if owner == 'author' else 'ACTUAL-QUALIFICATION-FINAL.json'
        outer = get(outer_path)
        admission = get('ROOT-ADMISSION.json')
        require(sha(data('ROOT-ADMISSION.json')) == ADMISSIONS[owner]
            and data('ROOT-ADMISSION.json') == data(run + 'root-admission.json')
            and admission['admitted'] is True
            and admission['scope'] == 'generated-state-fake-factory-and-worker-registry-only'
            and admission['label'] == 'factory-preflight01' and admission['pins_sha256'] == PINS_SHA
            and plan['admission_sha256'] == ADMISSIONS[owner], 'Distinct exact admission binding')
        require(report['passed'] == checked['passed'] == 59
            and report['failed'] == report['skipped'] == checked['failed'] == 0
            and report['qualification_exit'] == native['native_exit'] == exits['native_exit']
            == checked['qualification_exit'] == checked['native_exit'] == outer['exit_code'] == 0
            and checked['complete'] is True and checked['stdout_sha256'] == STDOUTS[owner], 'Complete actual result required')
        require(report['startup_binding'] is True and report['guard_integrity'] is True
            and set(report['guard_fields']) == set(GUARDS)
            and all(report['guard_fields'][name] is True for name in GUARDS)
            and report['audit_denials'] == [] and data(run + 'stderr.log') == b'', 'Guard or stderr mismatch')
        require(exits['inputs_unchanged'] is True and checked['inputs_unchanged'] is True
            and exits['generated_input_control_unchanged'] is True
            and exits['admission_copy_unchanged'] is True and exits['capture_size_bound_met'] is True,
            'Run integrity receipt mismatch')
        require(sha(data(run + 'INPUTS.json')) == CONTROL_SHA == plan['generated_input_control_sha256']
            == checked['generated_input_control_sha256'], 'Original generated control mismatch')
        require(plan['pins_sha256'] == control['pins_sha256'] == PINS_SHA
            and len(plan['inputs']) == 12 and {row['name'] for row in plan['inputs']} == set(COPIES)
            and set(control['child_files']) == set(report['source_sha256']) == set(COPIES), 'Executed copy membership')
        for row in plan['inputs']:
            name = row['name']
            payload = data(run + name)
            require(payload == data(COPIES[name]) and sha(payload) == row['sha256']
                == control['child_files'][name] == report['source_sha256'][name], 'Executed copy differs')
            copy_checks.append({'owner': owner, 'name': name, 'sha256': sha(payload), 'source_and_copy_equal': True})
        for name, digest in EXECUTED_SHA.items():
            require(report['source_sha256'][name] == digest, 'Executed implementation binding')
        expected = get(run + 'EXPECTED-CASES.json')
        cases = report['cases']
        require(data(run + 'EXPECTED-CASES.json') == data('EXPECTED-CASES.json')
            and len(cases) == len({row['name'] for row in cases}) == expected['case_count'] == 59
            and [row['name'] for row in cases] == expected['cases']
            and all(row['status'] == 'passed' for row in cases), 'Exact ordered case membership')
        require(report['native_qualified'] is checked['native_qualified'] is False
            and report['release_approved'] is checked['release_approved'] is False
            and control['native_approved'] is control['release_approved'] is False
            and plan['native_or_factory_execution_approved'] is exits['native_or_factory_execution_approved'] is False,
            'Native/release scope overstated')
        case_sets.append(cases)
        summaries.append({'owner': owner, 'passed': 59, 'failed': 0, 'skipped': 0,
            'elapsed_seconds': report['elapsed_seconds'], 'qualification_exit': 0, 'native_exit': 0,
            'actual_outer_exit': outer['exit_code'], 'actual_outer_logical_path': prefix + outer_path,
            'actual_outer_sha256': sha(data(outer_path)), 'stdout_sha256': STDOUTS[owner],
            'original_admission_sha256': ADMISSIONS[owner], 'input_control_sha256': CONTROL_SHA,
            'guard_fields': report['guard_fields']})
    require(case_sets[0] == case_sets[1], 'Complete author/root case objects differ')
    root_copy = parse(logical['root/ROOT-COPY-BINDINGS.json'])
    require(root_copy['pins_sha256'] == PINS_SHA and root_copy['source_edits'] == root_copy['launcher_edits'] == 0
        and len(root_copy['files']) == 31, 'Root preparation control mismatch')
    expected_paths = {row['path'] for row in parse(logical['author/PINS.json'])['files']}
    require({row['name'] for row in root_copy['files']} == expected_paths, 'Root prepared source membership')
    for row in root_copy['files']:
        relative(row['name'])
        payload = logical['author/' + row['name']]
        require(payload == logical['root/' + row['name']] and len(payload) == row['bytes']
            and sha(payload) == row['author_sha256'] == row['root_sha256'], 'Root exact preparation bytes')
    require(parse(logical['root/ACTUAL-PREPARE-TOOL.json'])['exit_code'] == 0, 'Actual root preparation failed')
    return {'scope': 'Same 59 factory/registry cases with fake services; native factory not executed',
        'distinct_cases': 59, 'exact_ordered_case_objects_equal': True, 'runs': summaries,
        'copied_input_checks': copy_checks, 'pin_entries_checked_per_root': 31,
        'root_preparation_rows_checked': 31, 'cases': case_sets[0],
        'native_qualified': False, 'release_approved': False}


def inventory_check(logical):
    inventory = parse(logical['preparation/INPUT-INVENTORY.json'])
    rows = inventory['files']
    require(len(rows) == inventory['file_count'] and len(rows) < MAX_FILES, 'Inventory count')
    require(len({row['logical_path'] for row in rows}) == len(rows), 'Duplicate input inventory path')
    require(set(logical) == {row['logical_path'] for row in rows} | {'preparation/INPUT-INVENTORY.json'},
        'Logical input inventory membership mismatch')
    for row in rows:
        relative(row['logical_path'])
        payload = logical[row['logical_path']]
        require(sha(payload) == row['sha256'] and len(payload) == row['bytes'], 'Input inventory bytes mismatch')


def write_json(path, value):
    with path.open('xb') as output:
        output.write((json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))


def verify():
    raw_manifest = read(DEST / 'SHA256.json')
    manifest = parse(raw_manifest)
    paths = [entry['path'] for entry in manifest['files']]
    require(len(paths) == len(set(paths)) == manifest['payload_count'], 'Outer manifest membership')
    actual = {path.relative_to(DEST).as_posix() for path in files(DEST)}
    require(actual == set(paths) | {'SHA256.json'}, 'Missing or unlisted physical file')
    for entry in manifest['files']:
        relative(entry['path'])
        payload = read(DEST / entry['path'])
        require(len(payload) == entry['bytes'] and sha(payload) == entry['sha256'], 'Physical file bytes mismatch')
    tree = parse(read(DEST / 'SOURCE-TREE.json'))
    logical, objects = {}, set()
    require(len(tree['sources']) == tree['logical_source_count'] <= MAX_FILES, 'Source tree count')
    for entry in tree['sources']:
        relative(entry['logical_path'])
        require(entry['logical_path'] not in logical, 'Duplicate logical source')
        require(entry['object'] == 'objects/' + entry['sha256'] + '.txt', 'Content object path mismatch')
        payload = read(DEST / entry['object'])
        require(len(payload) == entry['bytes'] and sha(payload) == entry['sha256'], 'Logical content mismatch')
        logical[entry['logical_path']] = payload
        objects.add(entry['object'])
    require({path for path in actual if path.startswith('objects/')} == objects, 'Unmapped content object')
    inventory_check(logical)
    require(compare_runs(logical) == parse(read(DEST / 'RUN-COMPARISON.json')), 'Derived comparison mismatch')
    require(read(DEST / 'REPORT.md') == logical['preparation/REPORT.md']
        and read(DEST / 'build_verify.py') == logical['preparation/build_verify.py'], 'Published report/builder mismatch')
    return {'verification_exit': 0, 'proof_path': str(DEST), 'logical_sources': len(logical),
        'unique_content_objects': len(objects), 'payload_count': len(paths), 'total_files': len(actual),
        'manifest_sha256': sha(raw_manifest), 'no_unlisted_files': True,
        'all_logical_and_physical_hashes_match': True}


def build():
    require(not DEST.exists(), 'Fresh documentary proof required')
    inventory_path = PREPARATION / 'INPUT-INVENTORY.json'
    raw_inventory = read(inventory_path)
    inventory = parse(raw_inventory)
    inputs = []
    for row in inventory['files']:
        path = relative(row['logical_path'])
        require(path.parts[0] in ROOTS and len(path.parts) > 1, 'Unknown documentary root')
        original = ROOTS[path.parts[0]].joinpath(*path.parts[1:])
        inputs.append((original, row['logical_path']))
    inputs.append((inventory_path, 'preparation/INPUT-INVENTORY.json'))
    require(len(inputs) <= MAX_FILES and len({name for _, name in inputs}) == len(inputs), 'Input mapping count')
    for owner, directory in ROOTS.items():
        actual = {owner + '/' + path.relative_to(directory).as_posix() for path in files(directory)}
        require(actual == {name for _, name in inputs if name.startswith(owner + '/')}, 'Original file set changed')
    logical, sources, objects, total = {}, [], {}, 0
    for path, name in inputs:
        payload = read(path)
        digest = sha(payload)
        if digest in objects:
            require(objects[digest] == payload, 'Digest collision')
        else:
            total += len(payload)
            require(total <= MAX_UNIQUE_BYTES, 'Aggregate unique documentary byte bound')
            objects[digest] = payload
        logical[name] = payload
        sources.append({'logical_path': name, 'original_path': str(path), 'bytes': len(payload),
            'sha256': digest, 'object': 'objects/' + digest + '.txt'})
    inventory_check(logical)
    comparison = compare_runs(logical)
    ordinary_ancestors(DEST)
    DEST.mkdir()
    (DEST / 'objects').mkdir()
    for digest, payload in sorted(objects.items()):
        with (DEST / 'objects' / (digest + '.txt')).open('xb') as output:
            output.write(payload)
    write_json(DEST / 'SOURCE-TREE.json', {'logical_source_count': len(sources), 'sources': sources})
    write_json(DEST / 'RUN-COMPARISON.json', comparison)
    for name in ('REPORT.md', 'build_verify.py'):
        with (DEST / name).open('xb') as output:
            output.write(logical['preparation/' + name])
    with (DEST / '.gitattributes').open('xb') as output:
        output.write(b'* -text\n')
    for entry, (original, name) in zip(sources, inputs, strict=True):
        require(read(original) == logical[name] == read(DEST / entry['object']), 'Source changed while archiving')
    write_json(DEST / 'COPY-VERIFICATION.json', {'verification_precedes_outer_seal': True,
        'original_and_object_bytes_match': True, 'logical_sources': len(sources),
        'unique_content_objects': len(objects), 'input_inventory_sha256': sha(raw_inventory),
        'all_source_paths_recorded_in': 'SOURCE-TREE.json'})
    payloads = []
    for path in files(DEST):
        payload = read(path)
        payloads.append({'path': path.relative_to(DEST).as_posix(), 'bytes': len(payload), 'sha256': sha(payload)})
    write_json(DEST / 'SHA256.json', {'schema': 1, 'excluded': ['SHA256.json'],
        'payload_count': len(payloads), 'files': payloads})
    return verify()


if __name__ == '__main__':
    require(sys.argv[1:] in (['--build'], ['--verify']), 'Use fixed --build or --verify mode')
    print(json.dumps(build() if sys.argv[1] == '--build' else verify(), indent=2))
