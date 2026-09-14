"""Inspect fixed source and recorded generated receipts, without native/model access."""
import hashlib
import json
import os
from pathlib import Path

assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
repo = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
run = repo / '_scratch/windows-retired-owner-recovery01'
proposal = repo / '_scratch/windows-retired-owner-recovery-proposal01'

def text_bytes(path):
    with path.open('rb') as stream:
        data = stream.read(1048577)
    assert len(data) <= 1048576
    data.decode('utf-8-sig')
    return data

def read(name):
    return json.loads(text_bytes(run / name))

before, after, outcome = read('before.json'), read('after.json'), read('exit.json')
assert outcome['outer_exit'] == outcome['controller_native_exit'] == outcome['expected_child_native_exit'] == 0
assert outcome['inputs_unchanged'] is outcome['receipt_valid'] is True
assert outcome['receipt_error_type'] is None and outcome['operation_mode'] == 'cancel'
assert outcome['stdout_bytes'] == outcome['stderr_bytes'] == 0
assert read('native-exit.json') == {'schema':'uoink.native-exit.v1','child_returned':True,'native_exit':0}
assert after['inputs_unchanged'] is True
assert len(before['sources']) == 18 and len(before['controls']) == 3
bound = before['sources'] + before['controls']
assert len(after['source_and_controls']) == len(bound)
for original, recorded in zip(bound, after['source_and_controls']):
    assert original['name'] == recorded['name']
    sha = original['sha256']
    assert sha == recorded['before_sha256'] == recorded['source_after_sha256'] == recorded['copy_after_sha256']
    source = Path(original['path'])
    assert source.parent == proposal and source.suffix in ('.py','.json','.ps1')
    for path in (source, run / original['name']):
        assert hashlib.sha256(text_bytes(path)).hexdigest() == sha
assert len(before['native_inputs']) == 9 and len(before['fixtures']) == 5
assert len(after['support_and_fixtures']) == 14
for expected, actual in zip(before['native_inputs'] + before['fixtures'], after['support_and_fixtures']):
    assert actual['path'] == expected['path'] and actual['bytes'] == expected['bytes']
    assert expected['sha256'] == actual['before_sha256'] == actual['after_sha256']
# The support and fixture paths above are receipt metadata only.
roles = {role:read(role + '-result.json') for role in ('controller','child','contender')}
expected_sources = {row['name']:row['sha256'] for row in before['sources']}
for role, receipt in roles.items():
    assert receipt['role'] == role and receipt['schema'] == 'uoink.generated-windows-retired-owner-recovery.v1'
    assert receipt['case'] == 'positive' and receipt['operation_mode'] == 'cancel'
    assert receipt['guard_valid'] is receipt['fixed_dispatch_valid'] is receipt['kernel32_path_verified'] is True
    assert receipt['error_type'] is None and receipt['directory_refusal'] is None
    assert receipt['guard_denials'] == receipt['model_imports'] == receipt['reserved_cleanup_calls'] == []
    assert receipt['work_budget_closed'] is False
    assert receipt['model_calls'] == receipt['pending_pipe_operations'] == receipt['fixed_dispatch_invalid_contexts'] == 0
    assert receipt['native_exit_planned'] == 0
    assert receipt['metadata_traps'] == 12 and receipt['registry_traps'] == 25
    assert receipt['fixed_dispatch_function_count'] == 33
    assert receipt['fixed_dispatch_completed_calls'] == receipt['fixed_dispatch_audit_events']
    assert receipt['source_sha256'] == expected_sources
    assert all(value is True for value in receipt['adapter_state'].values())
c, child, contender = (roles[x]['result'] for x in ('controller','child','contender'))
events = ['admit_generated_media','begin_generated_transcription','next_generated_segment','cancel_generated_cursor']
assert c['operation_events'] == child['operation_events'] == events
assert len(c['segments']) == child['produced_segments'] == 1
assert c['cursor_state'] == child['cursor_state'] == 'cancelled'
cancel = c['cancellation_journal']
assert cancel['phase_before'] == cancel['phase_after'] == 'WORKER_BOUND'
assert cancel['confirmed_before_sha256'] == cancel['confirmed_after_sha256']
for name in ('same_token_and_handle','gate_held_before_stop','journal_open_before_stop','clear_deferred_until_adapter_finally'):
    assert cancel[name] is True
for name in ('adapter_globals_restored','real_resolver_approval_unchanged_none','actual_factory_and_permit','adapter_owned_cleanup','retained_facade_and_stream_refused','read_set_released','pipe_retired','parent_guards_held_through_exit'):
    assert c[name] is True
assert c['lifecycle_phase'] == 8 and c['binding_calls'] == 1
expected_exit = {'child_native_exit':0,'process_wait_observed':True,'job_active_processes':0}
assert c['exit_observation'] == roles['controller']['writer_exclusion']['exit_observation'] == expected_exit
assert child['child_flow_return'] == 0
journal = c['durable_journal']
phases = ['INITIALIZED','RESERVED','WORKER_BOUND','CLEARED']
assert journal['phases'] == phases and journal['flush_successes'] == 4
assert journal['journal_handle_closed'] is journal['directory_guards_retired'] is True
assert journal['native_power_loss_or_restart_claim'] is False
recovery = c['retired_owner_recovery']
assert len(recovery) == 12
assert recovery['interruption_type'] == 'KeyboardInterrupt' and recovery['stage'] == 'after_teardown_before_clear'
assert recovery['phases_before_recovery'] == journal['before_clear_phases'] == phases[:3]
assert recovery['before_recovery_sha256'] == journal['before_clear_sha256'] == cancel['confirmed_before_sha256']
assert recovery['native_interrupt_crash_or_restart_claim'] is False
for name in ('interruption_identity_match','ordinary_completion_refused','manager_reconciliation_confirmed','owner_still_revoked','token_still_revoked','same_owner_and_record','journal_open_until_recovery_clear'):
    assert recovery[name] is True
for name in ('explicit_retired_owner_recovery','old_owner_still_revoked','old_token_still_revoked','injected_interrupt_identity_observed','same_manager_and_service_attempt'):
    assert journal[name] is True
assert journal['injected_interrupt_type'] == 'KeyboardInterrupt' and journal['injected_stage'] == 'after_teardown_before_clear'
assert journal['fresh_process_query_after_retirement'] is journal['os_interrupt_or_crash_claim'] is False
closed = read('closed-journal-observation.json')
assert closed['bytes'] == journal['journal_bytes']
assert closed['sha256'] == journal['journal_sha256']
assert closed['matches_controller_confirmed_bytes'] is closed['exclusive_postexit_read_closed'] is True
assert closed['power_loss_or_restart_proven'] is False
raw = bytes.fromhex(journal['journal_hex'])  # Decode recorded generated bytes only.
assert 0 < len(raw) <= 4*1024*1024 and len(raw) == closed['bytes']
assert hashlib.sha256(raw).hexdigest() == closed['sha256'] and raw.startswith(b'UORS1\n')
offset, previous = 6, '0'*64
frames = []
for index, phase in enumerate(phases):
    assert offset + 4 <= len(raw)
    length = int.from_bytes(raw[offset:offset+4], 'big')
    offset += 4
    assert 0 < length <= 4096 and offset + length + 32 <= len(raw)
    payload, checksum = raw[offset:offset+length], raw[offset+length:offset+length+32]
    offset += length + 32
    assert hashlib.sha256(payload).digest() == checksum
    frame = json.loads(payload)
    assert frame['sequence'] == index and frame['phase'] == phase and frame['previous'] == previous
    previous = checksum.hex()
    frames.append(frame)
    if index == 2:
        assert hashlib.sha256(raw[:offset]).hexdigest() == cancel['confirmed_before_sha256']
assert offset == len(raw)
assert all(row['physical'] == frames[0]['physical'] for row in frames)
assert all(row['generation'] == frames[1]['generation'] for row in frames[1:])
assert frames[2]['process'] == frames[3]['process'] and frames[2]['process'] is not None
assert contender['physical'] == journal['physical'] and contender['journal_path'] == journal['journal_path']
assert contender['status'] == 'sharing_refused' and contender['winerror'] == 32 and contender['attempt_count'] == 1
assert contender['journal_content_reads'] == contender['journal_writes'] == 0 and contender['valid_journal_handle_returned'] is False
print(json.dumps({'status':'PASS_GENERATED_NATIVE_RETIRED_OWNER_RECOVERY_ONLY', 'source_control_pairs':21, 'receipt_roles':3, 'guards_valid':True, 'process_and_jobs_closed':True, 'operation_events':events, 'segments':1, 'journal_bytes':len(raw), 'journal_sha256':closed['sha256'], 'before_recovery_sha256':cancel['confirmed_before_sha256'], 'native_calls':{r:len(v['native_api_calls']) for r,v in roles.items()}, 'dispatch_calls':{r:v['fixed_dispatch_completed_calls'] for r,v in roles.items()}, 'elapsed_seconds':{r:v['elapsed_seconds'] for r,v in roles.items()}, 'model_runtime_restart_release_accepted':False}, sort_keys=True))
