"""Verify and copy completed handshake evidence; no archived code executes."""
from pathlib import Path
import hashlib
import json
import os

S = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch')
OUT = S.parent / 'docs/library/proof/controller-handshake-2026-09-13'
roots = [S / n for n in ('controller-handshake-contracts01', 'controller-handshake-contracts02', 'astra-controller-handshake-contracts02')]
assert os.environ['IG_FORBIDDEN_LIVE'] == r'C:\Users\hello\AppData\Local\Uoink\index.db'
def sha(raw): return hashlib.sha256(raw).hexdigest()
def raw(p):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size <= 1048576
    value = p.read_bytes()
    assert len(value) <= 1048576
    return value
def record(p): return json.loads(raw(p))
def add(name, value):
    assert name not in payloads and not name.startswith('/') and '..' not in name.split('/')
    payloads[name] = value

reports = []
for base in roots[1:]:
    run = base / 'runs/hs01'
    r, ex, ne = record(run / 'stdout.json'), record(run / 'exit.json'), record(run / 'native-exit.json')
    expected = record(base / 'EXPECTED-CASES.json')['ordered_cases']
    assert r['expected_cases'] == expected == [x['name'] for x in r['cases']] and len(expected) == 8
    assert all(x['passed'] is True for x in r['cases']) and r['passed'] == r['count'] == 8 and r['failed'] == r['skipped'] == 0
    assert all(r[k] is True for k in ('guard_valid', 'metadata_traps_installed', 'content_reads_closed', 'baseline_winreg_identity_unchanged', 'registry_namespace_unchanged', 'registry_traps_installed', 'captures_installed', 'capture_valid'))
    assert r['metadata_trap_count'] == 12 and r['registry_trap_count'] == 25
    assert r['guard_denials'] == r['registry_denials'] == r['heavy_roots_loaded'] == []
    assert r['stdout_capture'] == r['stderr_capture'] == ''
    assert r['native_exit'] == ex['native_exit'] == ex['outer_exit'] == ne['native_exit'] == 0
    assert ex['inputs_unchanged'] is True and ex['receipt_valid'] is True and ex['stderr_bytes'] == 0 and raw(run / 'stderr.log') == b''
    assert len(raw(run / 'stdout.json')) == ex['stdout_bytes'] and ne['child_returned'] is True
    plan, after = record(run / 'plan.json'), record(run / 'after.json')
    assert len(plan['inputs']) == len(after) == 7
    later = {row['name']: row for row in after}
    for row in plan['inputs']:
        name = row['name']; assert '/' not in name and '\\' not in name and ':' not in name
        assert Path(row['source']) == base / name
        digest = sha(raw(base / name))
        assert digest == row['sha256'] == sha(raw(run / name))
        assert all(later[name][k] == digest for k in ('before_sha256', 'copy_after_sha256', 'source_after_sha256'))
    assert {row['name'] for row in after} == set(record(base / 'ROOT-ADMISSION.json')['input_sha256']) | {'ROOT-ADMISSION.json'}
    for name, digest in r['input_sha256'].items(): assert sha(raw(base / name)) == digest
    reports.append(r)
assert reports[0]['cases'] == reports[1]['cases']
launcher_a = raw(roots[1] / 'run_handshake01.ps1').decode()
launcher_b = raw(roots[2] / 'run_handshake01.ps1').decode()
assert launcher_a.count(str(roots[1])) == 1
assert launcher_a.replace(str(roots[1]), str(roots[2])) == launcher_b
assert not OUT.exists()
payloads = {}
for base in roots:
    count = 0
    for p in sorted(base.rglob('*')):
        assert not p.is_symlink() and not (getattr(p.lstat(), 'st_file_attributes', 0) & 0x400)
        if p.is_file():
            count += 1; assert count <= 128
            add(base.name + '/' + p.relative_to(base).as_posix(), raw(p))
for name in ('HANDSHAKE02-AUTHOR-PREP-ACTUAL.json', 'HANDSHAKE02-AUTHOR-ACTUAL.json', 'HANDSHAKE02-ROOT-PREP-ACTUAL.json', 'HANDSHAKE02-ROOT-ACTUAL.json'):
    value = raw(S / name); assert json.loads(value)['exit_code'] == 0; add('actual/' + name, value)
add('seal_handshake02.py', raw(Path(__file__)))
add('.gitattributes', b'* -text\n')
summary = {'scope': 'Completed in-memory handshake evidence only', 'author': {'passed': 8, 'failed': 0, 'skipped': 0, 'elapsed_seconds': reports[0]['elapsed_seconds']}, 'root': {'passed': 8, 'failed': 0, 'skipped': 0, 'elapsed_seconds': reports[1]['elapsed_seconds']}, 'ordered_case_rows_equal': True, 'seven_source_control_inputs_checked_each': True, 'archived_code_executed_by_sealer': False}
add('VERIFICATION.json', (json.dumps(summary, indent=2) + '\n').encode())
OUT.mkdir()
rows = []
for name, value in sorted(payloads.items()):
    p = OUT / name; p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f: f.write(value)
    assert raw(p) == value
    rows.append({'path': name, 'bytes': len(value), 'sha256': sha(value)})
manifest = (json.dumps({'files': rows}, indent=2) + '\n').encode()
with (OUT / 'SHA256.json').open('xb') as f: f.write(manifest)
print(json.dumps({'proof': str(OUT), 'payloads': len(rows), 'bytes': sum(x['bytes'] for x in rows), 'seal': sha(manifest), **summary}))
