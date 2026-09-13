"""Read-only documentary verification. Executes no archived code or model."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
assert os.environ['IG_FORBIDDEN_LIVE'] == r'C:\Users\hello\AppData\Local\Uoink\index.db'
S = ROOT / '_scratch'
N = S / 'asr-dummy-worker-native04'
G = S / 'runtime-candidate03-complete-graph01'
E = S / 'runtime-candidate02-metadata' / 'evidence'

def read_json(path):
    return json.loads(path.read_bytes())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def local(base, value):
    assert isinstance(value, str) and value and '\\' not in value and ':' not in value
    assert not value.startswith('/') and all(x not in ('', '.', '..') for x in value.split('/'))
    return base.joinpath(*value.split('/'))

def check_rows(base, rows):
    assert len({r['path'] for r in rows}) == len(rows)
    for row in rows:
        p = local(base, row['path'])
        raw = p.read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], str(p)

b, a = read_json(N / 'before.json'), read_json(N / 'after.json')
expected_source_names = {'snapshot_lifecycle.py', 'owned_generation_protocol.py', 'win32_worker_connection.py', 'win32_private_pipe.py', 'generated_worker_flow.py', 'dummy_bootstrap.py'}
assert {r['name'] for r in b['sources']} == expected_source_names and len(b['sources']) == 6
assert {r['name'] for r in b['controls']} == {'ROOT-ADMISSION.json', 'SOURCE-INPUTS.json', 'run_native04.ps1'} and len(b['controls']) == 3
for kind in ('sources', 'controls'):
    after = {r['name']: r for r in a[kind]}
    assert set(after) == {r['name'] for r in b[kind]}
    for row in b[kind]:
        p = Path(row['path'])
        assert p.parent in (S / 'asr-worker-namespace-proposal01', S / 'asr-dummy-worker-flow-proposal04')
        assert p.name == row['name'] and digest(p) == row['sha256'] == digest(N / row['name'])
        assert all(after[row['name']][k] == row['sha256'] for k in ('before_sha256', 'copy_after_sha256', 'source_after_sha256'))
support = [r'C:\Python314\python.exe', r'C:\Python314\python314.dll', r'C:\Python314\python3.dll', r'C:\Python314\DLLs\_ctypes.pyd', r'C:\Python314\DLLs\libffi-8.dll', r'C:\Windows\System32\kernel32.dll', r'C:\Python314\Lib\ctypes\__init__.py', r'C:\Python314\Lib\ctypes\_endian.py', r'C:\Python314\Lib\ctypes\_layout.py']
assert [r['path'] for r in b['native_inputs']] == support == [r['path'] for r in a['native_inputs']]
for before, after in zip(b['native_inputs'], a['native_inputs']):
    raw = Path(before['path']).read_bytes()
    assert len(raw) == before['bytes'] == after['bytes']
    assert hashlib.sha256(raw).hexdigest() == before['sha256'] == after['before_sha256'] == after['after_sha256']
fixture = (N / 'generated-guard.txt').read_bytes()
assert fixture == b'Uoink generated worker guard fixture. No model or library data.\n'
assert len(fixture) == b['fixture_bytes'] == 64
assert hashlib.sha256(fixture).hexdigest() == b['fixture_sha256'] == a['fixture_before_sha256'] == a['fixture_after_sha256']
x = read_json(N / 'exit.json')
assert x['controller_native_exit'] == x['outer_exit'] == x['stdout_bytes'] == x['stderr_bytes'] == x['model_calls'] == 0
assert x['inputs_unchanged'] is True and x['receipt_valid'] is True
reports = [read_json(N / (role + '-result.json')) for role in ('controller', 'child')]
for r, calls in zip(reports, (148, 109)):
    assert r['guard_valid'] is True and r['guard_denials'] == [] and r['error_type'] is None
    assert r['metadata_traps'] == 12 and r['registry_traps'] == 25 and r['model_imports'] == [] and r['model_calls'] == 0
    assert r['fixed_dispatch_valid'] is True and r['fixed_dispatch_function_count'] == 31
    assert r['fixed_dispatch_completed_calls'] == r['fixed_dispatch_audit_events'] == calls
    assert r['fixed_dispatch_invalid_contexts'] == 0 and r['kernel32_path_verified'] is True
    assert r['source_sha256'] == {row['name']: row['sha256'] for row in b['sources']}
out = reports[0]['result']
assert out['generated_result'] == {'characters': 40000, 'generated_sha256': '49b5147f78225eabab7fb57a6e7d2b40eb5f78495ec830db98b81ab452885769'}
assert out['lifecycle_phase'] == 8 and out['read_set_released'] is True and out['pipe_retired'] is True and out['controller_handshake_begun'] is True
assert out['exit_observation'] == {'child_native_exit': 0, 'process_wait_observed': True, 'job_active_processes': 0}
assert out['write_access_observations'] == [{'write_open_refused': True, 'winerror': 32}, {'write_open_succeeded': True, 'bytes_written': 0}]
assert all(out['parent_guard_retirement'][k] is True for k in ('parent_originals_closed', 'parent_inheritable_copies_closed', 'exact_child_alive_after_parent_close'))

i = read_json(G / 'results/graph01/invocation.json')
g = read_json(G / 'results/graph01/raw-graph.json')
l = read_json(G / 'launch-graph01/result.json')
rows = read_json(G / 'INPUT-HASHES.json')
assert len(rows) == 36 and digest(G / 'INPUT-HASHES.json') == 'e3f9b6bdcdc9dc3cf99c8d239f5aa2e79f1fc3da98b3a7c6d746afd2a03f97f7'
check_rows(G, rows)
assert rows == i['source_after'] == l['input_hashes_before'] == l['input_hashes_after']
assert i['captures_before'] == i['captures_after'] and len(i['captures_before']) == 313
check_rows(E, i['captures_before'])
assert digest(E / 'SHA256.json') == i['capture_manifest_sha256'] == '216571a9f97de87ed96ad61dc64262a3703e2395c913a871e9df7eb692ed431d'
assert i['identities_before'] == i['identities_after']
assert i['invocation_status'] == l['instrumentation_verdict'] == 'VALID'
assert i['exit'] == i['graph_exit'] == l['actual_native_exit'] == l['intended_outer_exit'] == 1
assert i['graph_status'] == g['status'] == 'FAIL' and i['graph_passed'] is False and g['passed'] is False
assert i['guard'] == {'valid': True, 'violations': [], 'wrappers_intact': True, 'finder_installed': True, 'startup_binding': True}
assert i['local_claims_valid'] is True and i['artifact_verified_in_this_invocation'] is False
assert g['selection_count'] == 144 and g['active_edges_count'] == 287
for key in ('missing_packages', 'conflicting_constraints', 'incomplete_evidence', 'manifest_errors', 'marker_errors', 'direct_url_errors', 'selection_errors'):
    assert g[key] == [], key
assert [(r['package'], r['version'], r['status']) for r in g['wheel_failures']] == [('antlr4-python3-runtime', '4.9.3', 'NO_WHEELS'), ('proxy-tools', '0.1.0', 'NO_WHEELS')]
assert g['owned_built_wheel_metadata'] == ['faster-whisper', 'nltk', 'whisperx']
check_rows(G / 'launch-graph01', l['process_log_checks'])
print(json.dumps({'documentary_verification': 'PASS', 'native04': {'sources': 6, 'controls': 3, 'installed_support': 9, 'fixture_bytes': 64, 'actual_native_result': 'PASS'}, 'graph01': {'inputs': 36, 'captures': 313, 'selection_count': 144, 'active_edges': 287, 'actual_graph_result': 'FAIL', 'missing_wheels': 2, 'conflicts': 0}, 'executed_archived_code': False}))
