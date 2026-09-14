"""Fixed documentary inventory; native support paths are compared as strings only."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
SCRATCH = ROOT / '_scratch'
SOURCE = SCRATCH / 'windows-reservation-native-drain-proposal01'
RUN = SCRATCH / 'windows-reservation-native-drain01'
PEER = SCRATCH / 'windows-reservation-native-review01'
OUT = SCRATCH / 'windows-journal-native01-final-list01'
PRIOR = ROOT / 'docs/library/proof/windows-creation-transfer-2026-09-13'
GENERATED = ('config.json', 'model.bin', 'preprocessor_config.json', 'tokenizer.json', 'vocabulary.json')
GENERATED_BYTES = {name: ('Uoink generated adoption fixture: ' + name + '. No model data.\n').encode('ascii') for name in GENERATED}
JOURNAL_NAME = '4640b95540b94d05-79692100000001000000000000000000.journal'
JOURNAL = RUN / 'registry' / JOURNAL_NAME
JOURNAL_SHA = 'b6b59a4bf7845eb45bc0039874388b175b98d2d3fe2c39daa009cb8d9f170cc9'
SOURCE_NAMES = {'reservation_file_port.py', 'snapshot_reservations.py', 'snapshot_lifecycle.py',
    'durable_lifecycle.py', 'win32_worker_connection.py', 'windows_reservation_port.py',
    'owned_generation_protocol.py', 'win32_private_pipe.py', 'pinned_buffer_namespace.py',
    'inherited_readset.py', 'generated_worker_flow.py', 'generated_operation_flow.py',
    'trusted_asr_resolver.py', 'asr_loading_adapter.py', 'generated_adapter_flow.py',
    'generated_journal_setup.py', 'dummy_bootstrap.py'}
SOURCE_EXTRA = {'API-AND-BOUNDS.md', 'BRIEF.md', 'NATIVE-PROTOCOL.md', 'SOURCE-INPUTS.json',
    'ROOT-ADMISSION-drain.json', 'ROOT-ADMISSION-TEMPLATE.json', 'run_normal_drain01.ps1',
    'test_creation_transfer.py', 'dummy_bootstrap.py.diff', 'run_normal_drain01.ps1.diff',
    'windows_reservation_port.py.diff'}
ORIGINS = {'dummy_bootstrap.py', 'PROTOCOL.md', 'run_actual_adapter01.ps1', 'SOURCE-INPUTS.json', 'windows_reservation_port.py'}
CONTROLS = {'ROOT-ADMISSION.json', 'SOURCE-INPUTS.json', 'run_normal_drain01.ps1'}
RECEIPTS = {'before.json', 'after.json', 'native-exit.json', 'exit.json', 'controller-result.json',
    'child-result.json', 'controller-stdout.log', 'controller-stderr.log', 'closed-journal-observation.json'}
PEER_NAMES = {'.gitattributes', 'VERDICT.md', 'TEXT-BINDING-CHECK.json', 'ACTUAL-TEXT-CHECK.json'}
ROOT_NAMES = {'WINDOWS-JOURNAL-NATIVE01-ACTUAL.json', 'WINDOWS-JOURNAL-NATIVE01-ADMISSION-ACTUAL.json',
              'WINDOWS-JOURNAL-NATIVE01-ROOT-REVIEW.md'}
PRIOR_FILES = {PRIOR / name for name in ('SHA256.json', 'FIXED-COPY-LIST.json', 'ASTRA-VERDICT.md', 'author/PINS.json')}
PRIOR_FILES.add(ROOT / 'docs/library/ASTRA-CREATION-TRANSFER-VERDICT-2026-09-13.md')
ALLOWED = {SOURCE / name for name in SOURCE_NAMES | SOURCE_EXTRA}
ALLOWED |= {SOURCE / 'origins' / name for name in ORIGINS}
ALLOWED |= {RUN / name for name in SOURCE_NAMES | CONTROLS | RECEIPTS | set(GENERATED)}
ALLOWED |= {PEER / name for name in PEER_NAMES} | {SCRATCH / name for name in ROOT_NAMES} | PRIOR_FILES | {JOURNAL}
ALLOWED |= {OUT / name for name in ('.gitattributes', 'VERDICT.md', 'write_fixed_list.py', 'RECEIPT-COMPARISON.json', 'FIXED-COPY-LIST.json')}

def raw(path):
    assert path in ALLOWED, 'No recorded support/artifact path may become a read target'
    assert not path.is_symlink() and path.is_file(), str(path)
    limit = 2118 if path == JOURNAL else 1048576
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    assert len(value) <= limit
    if path != JOURNAL:
        value.decode('utf-8-sig')
    return value

def fp(path):
    value = raw(path)
    return {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}

def sha(path):
    return fp(path)['sha256']

def read(path):
    return json.loads(raw(path))

def write(name, value):
    with (OUT / name).open('xb') as stream:
        stream.write((json.dumps(value, indent=2) + '\n').encode())

assert {p.name for p in SOURCE.iterdir() if p.is_file()} == SOURCE_NAMES | SOURCE_EXTRA
assert {p.name for p in SOURCE.iterdir() if p.is_dir()} == {'origins'}
assert {p.name for p in (SOURCE / 'origins').iterdir()} == ORIGINS
assert {p.name for p in RUN.iterdir() if p.is_file()} == SOURCE_NAMES | CONTROLS | RECEIPTS | set(GENERATED)
assert {p.name for p in RUN.iterdir() if p.is_dir()} == {'registry'}
assert {p.name for p in (RUN / 'registry').iterdir()} == {JOURNAL_NAME}
assert {p.name for p in PEER.iterdir()} == PEER_NAMES
assert sha(SOURCE / 'SOURCE-INPUTS.json') == 'e4c15e6b414c36e9fe69346cc214bc7d5c7b4f5bf3808e3b165696066de11dcc'
assert sha(SOURCE / 'run_normal_drain01.ps1') == 'b9c532a561e31afea34c47d4f060242d23f28fb5ece0eae102ae094a3eb4cb8e'
assert sha(PEER / 'VERDICT.md') == '8bcad49ea9ff62134e2edb8a25f8f6855b284101e8f027374e8f1920543de8b1'
mapping = read(SOURCE / 'SOURCE-INPUTS.json')
assert set(mapping['source_sha256']) == set(mapping['source_paths']) == SOURCE_NAMES
for name in SOURCE_NAMES:
    assert mapping['source_paths'][name] == str(SOURCE / name)
    assert sha(SOURCE / name) == sha(RUN / name) == mapping['source_sha256'][name]
assert len(mapping['native_bindings']) == 9
assert mapping['native_bindings'] == read(SOURCE / 'origins/SOURCE-INPUTS.json')['native_bindings']
prior_pins = read(PRIOR / 'author/PINS.json')
prior_hashes = {row['path']: row['sha256'] for row in prior_pins['files']}
shared = SOURCE_NAMES - {'dummy_bootstrap.py', 'generated_journal_setup.py'}
assert len(shared) == 15
for name in shared:
    assert prior_hashes[name] == mapping['source_sha256'][name]
admission = read(SOURCE / 'ROOT-ADMISSION-drain.json')
assert sha(SOURCE / 'ROOT-ADMISSION-drain.json') == '6cea34f867d1aa6263331b86cb65d4d605210dd677fde237c43908250256190a'
assert raw(SOURCE / 'ROOT-ADMISSION-drain.json') == raw(RUN / 'ROOT-ADMISSION.json')
assert admission['root_reviewed'] is True and admission['scope'] == 'generated-windows-journal-normal-drain-only'
assert admission['case'] == 'positive' and admission['operation_mode'] == 'drain' and admission['run_path'] == str(RUN)
assert admission['source_inputs_sha256'] == sha(SOURCE / 'SOURCE-INPUTS.json')
assert admission['launcher_sha256'] == sha(SOURCE / 'run_normal_drain01.ps1')
before, after = read(RUN / 'before.json'), read(RUN / 'after.json')
assert len(before['sources']) == 17 and len(before['controls']) == 3
assert len(after['source_and_controls']) == 20 and len(after['support_and_fixtures']) == 14 and after['inputs_unchanged'] is True
before_hashes = {row['name']: row['sha256'] for row in before['sources'] + before['controls']}
assert set(before_hashes) == SOURCE_NAMES | CONTROLS
for row in after['source_and_controls']:
    name = row['name']
    assert name in before_hashes
    source_name = 'ROOT-ADMISSION-drain.json' if name == 'ROOT-ADMISSION.json' else name
    assert row['before_sha256'] == row['source_after_sha256'] == row['copy_after_sha256'] == before_hashes[name] == sha(SOURCE / source_name) == sha(RUN / name)
assert len(before['native_inputs']) == 9 and len(before['fixtures']) == 5
recorded = {}
for row in before['native_inputs']:
    assert mapping['native_bindings'][row['path']] == {k: row[k] for k in ('bytes', 'sha256')}
    recorded[row['path']] = {k: row[k] for k in ('bytes', 'sha256')}
for row in before['fixtures']:
    assert row['name'] in GENERATED and row['path'] == str(RUN / row['name'])
    assert row['writer_closed'] is True and raw(RUN / row['name']) == GENERATED_BYTES[row['name']]
    assert fp(RUN / row['name']) == {k: row[k] for k in ('bytes', 'sha256')}
    recorded[row['path']] = {k: row[k] for k in ('bytes', 'sha256')}
assert len(recorded) == 14
for row in after['support_and_fixtures']:
    assert row['path'] in recorded
    assert row['before_sha256'] == row['after_sha256'] == recorded[row['path']]['sha256']
    assert row['bytes'] == recorded[row['path']]['bytes']
# No path from these nine support records is stat'ed, opened, resolved or copied.
actual = read(SCRATCH / 'WINDOWS-JOURNAL-NATIVE01-ACTUAL.json')
assert actual['chunk_id'] == 'd3d56f' and type(actual['exit_code']) is int and actual['exit_code'] == 0
native, exit_result = read(RUN / 'native-exit.json'), read(RUN / 'exit.json')
assert native == {'schema': 'uoink.native-exit.v1', 'child_returned': True, 'native_exit': 0}
assert all(exit_result[key] == 0 for key in ('controller_native_exit', 'expected_child_native_exit', 'outer_exit', 'stdout_bytes', 'stderr_bytes'))
assert exit_result['inputs_unchanged'] is True and exit_result['receipt_valid'] is True and exit_result['receipt_error_type'] is None
assert raw(RUN / 'controller-stdout.log') == raw(RUN / 'controller-stderr.log') == b''
controller, child = read(RUN / 'controller-result.json'), read(RUN / 'child-result.json')
for result, role, apis, dispatches, casts, receipt_size in (
    (controller, 'controller', 8203, 8238, 1, 307062), (child, 'child', 252, 286, 0, 14458)):
    assert result['schema'] == 'uoink.generated-windows-journal-normal-drain.v1'
    assert result['role'] == role and result['case'] == 'positive' and result['operation_mode'] == 'drain'
    assert result['error_type'] is None and result['native_exit_planned'] == 0 and result['guard_valid'] is True
    assert result['guard_denials'] == result['reserved_cleanup_calls'] == result['reserved_cleanup_wait_caps'] == result['model_imports'] == []
    assert result['metadata_traps'] == 12 and result['registry_traps'] == 25 and result['model_calls'] == 0
    assert result['work_budget_closed'] is False and result['pending_pipe_operations'] == 0
    assert result['fixed_dispatch_valid'] is True and result['fixed_dispatch_function_count'] == 33
    assert result['fixed_dispatch_invalid_contexts'] == 0 and result['fixed_attribute_cast_calls'] == casts
    assert len(result['native_api_calls']) == apis
    assert result['fixed_dispatch_completed_calls'] == result['fixed_dispatch_audit_events'] == dispatches == 34 + apis + casts
    assert result['source_sha256'] == mapping['source_sha256']
    assert len(result['adapter_state']) == 5 and all(value is True for value in result['adapter_state'].values())
    assert fp(RUN / (role + '-result.json'))['bytes'] == receipt_size
outcome = controller['result']
assert outcome['exit_observation'] == {'child_native_exit': 0, 'process_wait_observed': True, 'job_active_processes': 0}
assert outcome['lifecycle_phase'] == 8 and outcome['actual_adapter_context'] == 'faster_whisper_session'
assert all(outcome[key] is True for key in ('read_set_released', 'pipe_retired', 'parent_guards_held_through_exit',
    'retained_facade_and_stream_refused', 'adapter_globals_restored', 'real_resolver_approval_unchanged_none',
    'actual_factory_and_permit', 'adapter_owned_cleanup'))
assert outcome['cursor_state'] == child['result']['cursor_state'] == 'eof'
assert len(outcome['segments']) == child['result']['produced_segments'] == 2
for index, name in enumerate(('config.json', 'tokenizer.json')):
    assert outcome['segments'][index] == {'start': index / 2, 'end': (index + 1) / 2,
        'text': GENERATED_BYTES[name].decode('ascii').rstrip('\n'), 'words': []}
assert child['result']['child_flow_return'] == 0 and child['result']['readback']['payload_bytes'] == 328
for name in GENERATED:
    assert controller['generated_asset_io'][name] == {'seeks': 0, 'reads': 0, 'bytes': 0}
    assert child['generated_asset_io'][name] == {'seeks': 1, 'reads': 2, 'bytes': len(GENERATED_BYTES[name])}
journal = outcome['durable_journal']
assert journal['physical'] == [5062249756973681925, '79692100000001000000000000000000']
assert f"{journal['physical'][0]:016x}-{journal['physical'][1]}.journal" == JOURNAL_NAME
assert journal['journal_path'] == str(JOURNAL) and journal['journal_bytes'] == 2118 and journal['journal_sha256'] == JOURNAL_SHA
assert all(journal[key] is True for key in ('creation_handle_transferred_without_close', 'journal_handle_closed', 'directory_guards_retired'))
assert journal['native_power_loss_or_restart_claim'] is False and journal['flush_successes'] == 4
assert journal['phases'] == ['INITIALIZED', 'RESERVED', 'WORKER_BOUND', 'CLEARED']
milestone_spec = [('CreateProcessW', 'RESERVED', 4360, 2), ('ResumeThread', 'WORKER_BOUND', 6202, 3), ('CloseHandle', 'CLEARED', 8175, 4)]
assert len(journal['milestones']) == 3
for row, (api, phase, index, flushes) in zip(journal['milestones'], milestone_spec):
    assert (row['api'], row['phase'], row['call_index'], row['flush_successes']) == (api, phase, index, flushes)
    assert controller['native_api_calls'][index] == api
events = journal['io_events']
assert len(events) == 37 and [row['call_index'] for row in events] == sorted({row['call_index'] for row in events})
for event in events:
    assert event['result'] is True and controller['native_api_calls'][event['call_index']] == event['api']
    assert event['api'] in ('SetFilePointerEx', 'ReadFile', 'WriteFile', 'FlushFileBuffers')
    if event['api'] == 'SetFilePointerEx':
        assert 0 <= event['actual_offset'] == event['requested_offset'] <= 2118
    elif event['api'] in ('ReadFile', 'WriteFile'):
        assert 0 <= event['actual_bytes'] <= event['requested_bytes'] <= 65536
flushes = [event['call_index'] for event in events if event['api'] == 'FlushFileBuffers']
assert flushes == [1778, 3587, 5477, 7451]
assert controller['native_api_calls'].count('FlushFileBuffers') == 4 and child['native_api_calls'].count('FlushFileBuffers') == 0
assert flushes[1] < 4360 and flushes[2] < 6202 and flushes[3] < 8175
assert child['native_api_calls'].count('CreateFileW') == child['native_api_calls'].count('CreateProcessW') == 0
assert controller['native_api_calls'].count('CreateProcessW') == 1
journal_bytes = raw(JOURNAL)
assert len(journal_bytes) == 2118 and hashlib.sha256(journal_bytes).hexdigest() == JOURNAL_SHA
assert journal_bytes.hex() == journal['journal_hex'] and journal_bytes.startswith(b'UORS1\n')
assert journal_bytes[-32:].hex() == journal['head'] == journal['milestones'][-1]['head']
closed = read(RUN / 'closed-journal-observation.json')
assert closed == {'path': str(JOURNAL), 'bytes': 2118, 'sha256': JOURNAL_SHA,
                  'matches_controller_confirmed_bytes': True, 'exclusive_postexit_read_closed': True,
                  'power_loss_or_restart_proven': False}
comparison = {'scope': 'Completed documentary receipts plus the six exact permitted generated files; no native rerun',
    'actual_chunk_id': actual['chunk_id'], 'outer_exit': 0, 'controller_exit': 0, 'child_exit': 0,
    'outer_elapsed_seconds': actual['wall_time_seconds'], 'controller_api_calls': 8203, 'child_api_calls': 252,
    'controller_dispatch_and_audit_events': 8238, 'child_dispatch_and_audit_events': 286,
    'journal': fp(JOURNAL), 'generated_ascii_bytes': sum(map(len, GENERATED_BYTES.values())),
    'journal_io_events': 37, 'four_phase_order_verified': True, 'milestone_indexes': [4360, 6202, 8175],
    'flush_indexes': flushes, 'source_control_checks': 20, 'support_fixture_record_checks': 14,
    'support_files_reopened_or_copied': 0, 'all_current_source_control_and_generated_bytes_match': True,
    'shared_prior_source_hashes_verified': 15, 'prior_fake_70_proof_commit': '2f4311f',
    'native_failure_or_runtime_acceptance': False}
write('RECEIPT-COMPARISON.json', comparison)
rows = []
def add(path, relative):
    rows.append({'source': str(path), 'relative_path': relative, **fp(path)})
for name in sorted(SOURCE_NAMES | SOURCE_EXTRA): add(SOURCE / name, 'proposal/' + name)
for name in sorted(ORIGINS): add(SOURCE / 'origins' / name, 'proposal/origins/' + name)
for name in sorted(SOURCE_NAMES | CONTROLS | RECEIPTS | set(GENERATED)): add(RUN / name, 'native-run/' + name)
add(JOURNAL, 'native-run/registry/' + JOURNAL_NAME)
for name in sorted(PEER_NAMES): add(PEER / name, 'peer-review/' + name)
for name in sorted(ROOT_NAMES): add(SCRATCH / name, 'root/' + name)
for path in sorted(PRIOR_FILES): add(path, 'prior-2f4311f/' + ('author-PINS.json' if path.name == 'PINS.json' else path.name))
for name in ('.gitattributes', 'VERDICT.md', 'write_fixed_list.py', 'RECEIPT-COMPARISON.json'):
    add(OUT / name, name if name == '.gitattributes' else 'review/' + name)
rows.sort(key=lambda row: row['relative_path'])
assert len({row['relative_path'] for row in rows}) == len(rows)
fixed = {'schema': 'uoink.fixed-documentary-copy-list.v1', 'file_count': len(rows),
    'total_bytes': sum(row['bytes'] for row in rows), 'support_files_excluded': True,
    'generated_binary_allowlist': ['native-run/model.bin', 'native-run/registry/' + JOURNAL_NAME],
    'prior_large_proof_referenced_only': '2f4311f', 'files': rows}
write('FIXED-COPY-LIST.json', fixed)
print(json.dumps({'file_count': fixed['file_count'], 'total_bytes': fixed['total_bytes'],
    'fixed_copy_list': fp(OUT / 'FIXED-COPY-LIST.json'), 'verdict': fp(OUT / 'VERDICT.md'),
    'comparison': fp(OUT / 'RECEIPT-COMPARISON.json'), 'candidate_executed': False,
    'support_or_model_files_read': False}, indent=2))
