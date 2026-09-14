"""Read fixed text sources/receipts only. Never follow checkpoint or staging fields."""
from pathlib import Path
import hashlib
import json

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch')
SOURCE = ROOT / 'vad-d1-activated-invocation01'
RUN = SOURCE / 'execution-d1-real-01'
OUTER = SOURCE / 'outer-d1-real-01'
OUT = ROOT / 'd1-real01-final-list01'
EXTERNAL_RECEIPT = ROOT / 'vad-buffer-version-approved-output/d1-buffer-version-01.json'
OWNER_SHA = '3b395b5ab39d711502c69ce9c5f87ecb1587f1a9e619f713ddc3ac808c8390d2'
NOTE_SHA = '9f136312e41a9a72be804499d79d4a0e00c429ef0bc18551e604edde12c5f422'
RECEIPT_SHA = '754ca6dea6aed81de072940b35ad4c283f270b5770a88236ef55fd0a09d46e75'
ADMISSION_SHA = '6ca80d379598eaf94955f6a28a3fe92a54ab38eef2de36d1bb62627ff358d4be'
SCOPE = 'D1_STATIC_VERSION_AND_BUFFERS_ONLY'
TOP = {
    '.gitattributes', 'ACTIVATION-REVIEW.md', 'BRIEF.md', 'buffer_basis.py', 'd1_child.py',
    'd1_child.py.activation.diff', 'fixed_converter.py', 'INPUTS.json', 'inspect_adapter.py',
    'known-inventory.json', 'launch_d1.py', 'launch_d1.py.activation.diff', 'PROTOCOL.md',
    'ROOT-ADMISSION.json', 'ROOT-ADMISSION.TEMPLATE.json', 'run-root.ps1',
    'run-root.ps1.activation.diff', 'RYAN-D1-DECISION.json', 'RYAN-SOURCE-NOTE.md',
    'SOURCE-BINDINGS.json', 'TEXT-CHECKS.json', 'zip_bounds.py',
}
BEFORE = {'d1_child.py', 'launch_d1.py', 'run-root.repaired.ps1', 'winreg-guard-reference.py'}
CHILD_SOURCES = {'d1_child.py', 'zip_bounds.py', 'fixed_converter.py', 'buffer_basis.py',
                 'inspect_adapter.py', 'known-inventory.json'}
RUN_NAMES = CHILD_SOURCES | {'INPUTS.json', 'ROOT-ADMISSION.json', 'RYAN-D1-DECISION.json',
    'actual-child-exit.json', 'adapter-receipt.json', 'ATTEMPT-CLAIM.json',
    'checked-result.json', 'launch-plan.json', 'stderr.log', 'stdout.json'}
OUTER_NAMES = {'actual-exit.json', 'command.json', 'raw-exit.txt', 'stderr.log', 'stdout.log'}
EXTERNALS = (
    'D1-REAL01-ACTUAL.json', 'D1-ACTIVATED-ROOT-REVIEW-2026-09-13.md',
    'D1-ADMISSION-PREPARATION01-FAILURE-ACTUAL.json',
    'D1-ADMISSION-PREPARATION02-SUCCESS-ACTUAL.json',
    'D1-ADMISSION-PREPARATION-REPAIR01.md', 'RYAN-D1-STATIC-APPROVAL-2026-09-13.md',
)

def raw(path):
    # Caller supplies only one of the explicit documentary paths above/below.
    assert not path.is_symlink() and path.is_file(), str(path)
    value = path.read_bytes()
    assert len(value) < 200_000, str(path)
    value.decode('utf-8-sig')
    return value

def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()

def fp(path):
    value = raw(path)
    return {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}

def read(path):
    return json.loads(raw(path))

def write(name, value):
    with (OUT / name).open('xb') as stream:
        stream.write((json.dumps(value, indent=2) + '\n').encode())

assert {p.name for p in SOURCE.iterdir() if p.is_file()} == TOP
assert {p.name for p in SOURCE.iterdir() if p.is_dir()} == {'before', RUN.name, OUTER.name}
for directory, names in ((SOURCE / 'before', BEFORE), (RUN, RUN_NAMES), (OUTER, OUTER_NAMES)):
    assert not directory.is_symlink()
    assert {p.name for p in directory.iterdir()} == names
bindings = read(SOURCE / 'SOURCE-BINDINGS.json')
assert bindings['operative_count'] == len(bindings['files']) == 9 and len(bindings['before']) == 4
admission = read(SOURCE / 'ROOT-ADMISSION.json')
assert sha(SOURCE / 'ROOT-ADMISSION.json') == ADMISSION_SHA
assert admission['root_reviewed'] is True and admission['scope'] == SCOPE and admission['run_id'] == 'd1-real-01'
assert admission['owner_decision_sha256'] == OWNER_SHA
assert set(admission['source_hashes']) == CHILD_SOURCES | {'INPUTS.json', 'launch_d1.py', 'run-root.ps1'}
for row in bindings['files'] + bindings['before']:
    name = row['path']
    assert name in TOP or name.startswith('before/') and name[7:] in BEFORE
    assert fp(SOURCE / name) == {k: row[k] for k in ('bytes', 'sha256')}
for row in bindings['files']:
    assert admission['source_hashes'][row['path']] == row['sha256']
for row in bindings['unchanged_fixed_inputs']:
    assert row['unchanged'] is True and sha(SOURCE / row['name']) == row['sha256']
assert len(bindings['unchanged_fixed_inputs']) == 5
assert sha(SOURCE / 'inspect_adapter.py') == '533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649'
assert sha(SOURCE / 'RYAN-D1-DECISION.json') == bindings['owner_decision_sha256'] == OWNER_SHA
assert sha(SOURCE / 'RYAN-SOURCE-NOTE.md') == bindings['source_note_sha256'] == NOTE_SHA
assert raw(SOURCE / 'RYAN-SOURCE-NOTE.md') == raw(ROOT / EXTERNALS[5])
owner = read(SOURCE / 'RYAN-D1-DECISION.json')
assert owner['approved'] is True and owner['owner'] == 'Ryan'
assert owner['decision_text'] == 'Approve D1 static inspection only'
assert owner['source_message_id'] is None and owner['approved_utc'] is None
assert owner['scope'] == SCOPE and owner['source_note_sha256'] == NOTE_SHA
assert (owner['artifact_bytes'], owner['interpreted_payload_bytes']) == (17719103, 1002)
assert all(owner[key] is False for key in ('conversion_authorized', 'model_execution_authorized', 'network_authorized'))
child_hashes = read(SOURCE / 'INPUTS.json')['child_files']
assert set(child_hashes) == CHILD_SOURCES
for name in CHILD_SOURCES | {'INPUTS.json', 'ROOT-ADMISSION.json', 'RYAN-D1-DECISION.json'}:
    assert raw(SOURCE / name) == raw(RUN / name)
    if name in child_hashes:
        assert sha(RUN / name) == child_hashes[name]

result = read(RUN / 'stdout.json')
checked = read(RUN / 'checked-result.json')
native = read(RUN / 'actual-child-exit.json')
outer = read(OUTER / 'actual-exit.json')
actual = read(ROOT / EXTERNALS[0])
assert actual['chunk_id'] == 'b29f6c' and type(actual['exit_code']) is int and actual['exit_code'] == 0
assert type(native['actual_child_exit']) is int and native['actual_child_exit'] == 0 and native['timed_out'] is False
assert type(outer['actual_outer_exit']) is int and outer['actual_outer_exit'] == 0
assert raw(OUTER / 'raw-exit.txt') == b'0\n'
assert result['actual_child_exit'] == checked['actual_child_exit'] == 0
assert result['scope'] == SCOPE and result['failure'] is None
assert raw(RUN / 'stderr.log') == raw(OUTER / 'stderr.log') == b''
guard = result['guard']
truths = ('valid', 'inputs_unchanged', 'metadata_wrappers_installed',
          'baseline_winreg_identity_unchanged', 'registry_namespace_unchanged', 'registry_traps_installed')
assert all(guard[name] is True for name in truths)
assert guard['registry_trap_count'] == 25 and guard['active'] is False
assert guard['artifact_opens'] == guard['receipt_opens'] == guard['invocations'] == 1
assert all(guard[name] == [] for name in ('unexpected_events', 'forbidden_conversion_calls',
                                       'heavy_preloaded', 'heavy_after', 'registry_denials'))
assert result['adapter_owner_gate_reset'] is True and result['conversion_profile_activated'] is False
assert result['runtime_or_release_approved'] is False and result['owner_decision_sha256'] == OWNER_SHA
assert set(result['input_sha256']) == CHILD_SOURCES | {'INPUTS.json', 'ROOT-ADMISSION.json', 'RYAN-D1-DECISION.json'}
for name, digest in result['input_sha256'].items():
    assert sha(SOURCE / name) == sha(RUN / name) == digest
assert checked['guard_valid'] is True and checked['input_bytes_unchanged'] is True
assert checked['conversion_runtime_or_release_accepted'] is False
inspection = result['inspection_result']
assert checked['inspection_result'] == inspection and inspection['inspection_exit'] == 0
assert inspection['conversion_profile_activated'] is inspection['release_approved'] is False
assert inspection['receipt_sha256'] == RECEIPT_SHA and inspection['receipt_bytes'] == 1984
assert fp(EXTERNAL_RECEIPT) == fp(RUN / 'adapter-receipt.json') == {'bytes': 1984, 'sha256': RECEIPT_SHA}
receipt = read(EXTERNAL_RECEIPT)
assert receipt['status'] == 'static_inspection_complete_unqualified'
assert receipt['interpreted_payload_bytes'] == 1002
assert receipt['version_actual_hex'] == receipt['version_expected_hex'] == '330a'
assert receipt['zip'] == {'all_member_crc_verified': True, 'exact_inventory_verified': True, 'members': 131}
assert receipt['input']['bytes'] == 17719103 and receipt['input']['sha256'] == owner['artifact_sha256']
assert receipt['input']['synthetic'] is False
assert [(row['name'], row['bytes']) for row in receipt['selected_members']] == [
    ('archive/data/4', 500), ('archive/data/5', 500), ('archive/version', 2)]
assert all(receipt[key] is False for key in ('conversion_performed', 'conversion_profile_activated',
    'historical_writer_authenticated', 'model_or_tensor_constructed', 'other_storage_values_interpreted',
    'pickle_interpreted', 'release_approved'))
basis = receipt['buffer_basis']
assert basis['status'] == 'consistent_with_unapproved_analytic_basis' and basis['orientation'] == 'little'
assert basis['ulp_limit'] == 8 and basis['word_count'] == 250
assert all(basis[key] is False for key in ('other_storages_validated', 'real_profile_approved', 'writer_authenticated'))
assert basis['orientations']['little'] == {'matches_both': True, 'maximum_same_sign_finite_ulp_distance': 2,
                                         'time_vector_failures': 0, 'window_failures': 0}
assert basis['orientations']['big'] == {'matches_both': False, 'maximum_same_sign_finite_ulp_distance': 1118589630,
                                      'time_vector_failures': 125, 'window_failures': 125}
printed = json.loads(actual['output'])
assert printed == read(OUTER / 'stdout.log')
assert printed['actual_child_exit'] == 0 and printed['inspection_result'] == inspection
assert printed['guard_valid'] is True and printed['conversion_runtime_or_release_accepted'] is False
plan = read(RUN / 'launch-plan.json')
assert plan['command'] == [r'C:\Python314\python.exe', '-I', '-S', '-B', str(RUN / 'd1_child.py')]
assert plan['cwd'] == str(RUN) and plan['source_hashes'] == admission['source_hashes']
assert plan['owner_decision_sha256'] == OWNER_SHA and plan['external_timeout_seconds'] == 60
command = read(OUTER / 'command.json')
assert command['executable'] == r'C:\Python314\python.exe'
assert command['arguments'] == ['-I', '-S', '-B', str(SOURCE / 'launch_d1.py')]
assert command['forbidden_live_binding_set'] is True and command['provider_environment_scrubbed'] is True
assert command['removed_variable_names'] == []
failure, preparation = read(ROOT / EXTERNALS[2]), read(ROOT / EXTERNALS[3])
assert failure['chunk_id'] == 'c27355' and failure['exit_code'] == 1
assert preparation['chunk_id'] == 'ddbdf1' and preparation['exit_code'] == 0
prepared = json.loads(preparation['output'])
assert prepared['verified_sources'] == 9 and prepared['verified_preserved_references'] == 4
assert prepared['owner_record_verified'] is True and prepared['transcript_note_verified'] is True
assert prepared['checkpoint_touched'] is False and prepared['admission_sha256'] == ADMISSION_SHA
assert sha(ROOT / EXTERNALS[1]) == prepared['review_sha256']

comparison = {
    'review_scope': 'Completed text sources and receipts only; no checkpoint/staging operations or payload execution',
    'actual_tool': {'chunk_id': actual['chunk_id'], 'exit_code': actual['exit_code'],
                    'wall_time_seconds': actual['wall_time_seconds']},
    'status': receipt['status'], 'outer_exit': 0, 'child_exit': 0, 'inspection_exit': 0,
    'receipt': fp(EXTERNAL_RECEIPT), 'receipt_copies_equal': True,
    'operative_bindings_verified': 9, 'preserved_source_references_verified': 4,
    'child_content_hashes_verified': 9, 'interpreted_payload_bytes': 1002,
    'zip_members_recorded': 131, 'version_actual_hex': '330a',
    'little_maximum_ulp_distance': 2, 'little_failures': [0, 0], 'big_failures': [125, 125],
    'artifact_open_count_recorded': 1, 'receipt_open_count_recorded': 1, 'invocation_count_recorded': 1,
    'all_reported_guard_checks_true': True, 'registry_traps': 25, 'gate_reset_recorded': True,
    'conversion_profile_closed': True, 'failed_preparation_preserved': 'c27355',
    'repaired_preparation_preserved': 'ddbdf1', 'writer_storage_runtime_acceptance': False,
    'approval_message_id_and_timestamp_not_invented': True,
}
write('RECEIPT-COMPARISON.json', comparison)
rows = []
def add(source, relative):
    rows.append({'source': str(source), 'relative_path': relative, **fp(source)})
for name in sorted(TOP):
    add(SOURCE / name, 'activated/' + name)
for prefix, names in (('before', BEFORE), ('execution-d1-real-01', RUN_NAMES), ('outer-d1-real-01', OUTER_NAMES)):
    for name in sorted(names):
        add(SOURCE / prefix / name, 'activated/' + prefix + '/' + name)
add(EXTERNAL_RECEIPT, 'approved-output/d1-buffer-version-01.json')
for name in EXTERNALS:
    add(ROOT / name, 'root/' + name)
for name in ('.gitattributes', 'VERDICT.md', 'write_fixed_list.py', 'RECEIPT-COMPARISON.json'):
    add(OUT / name, name if name == '.gitattributes' else 'review/' + name)
assert len({row['relative_path'] for row in rows}) == len(rows)
rows.sort(key=lambda row: row['relative_path'])
fixed = {'schema': 'uoink.fixed-documentary-copy-list.v1',
         'purpose': 'One completed D1 static inspection; exact text-only sources and receipts',
         'file_count': len(rows), 'total_bytes': sum(row['bytes'] for row in rows), 'files': rows}
write('FIXED-COPY-LIST.json', fixed)
print(json.dumps({'file_count': fixed['file_count'], 'total_bytes': fixed['total_bytes'],
                  'fixed_copy_list': fp(OUT / 'FIXED-COPY-LIST.json'),
                  'comparison': fp(OUT / 'RECEIPT-COMPARISON.json'), 'verdict': fp(OUT / 'VERDICT.md'),
                  'payload_executed': False, 'checkpoint_or_staging_accessed': False}, indent=2))
