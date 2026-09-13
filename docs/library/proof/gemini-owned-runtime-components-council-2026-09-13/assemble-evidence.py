"""Archive completed documentary evidence and exact report transport only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
SOURCE = ROOT / '_scratch/gemini-owned-runtime-components-council-receipts01'
OUT = ROOT / 'docs/library/proof/gemini-owned-runtime-components-council-2026-09-13'
REPORT = ROOT / 'docs/library/GEMINI-OWNED-RUNTIME-COMPONENTS-COUNCIL-REVIEW-2026-09-13.md'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
seal_raw = (SOURCE / 'SHA256.json').read_bytes()
assert sha(seal_raw) == 'b9070b4fc426f9bef5c0bdc5f559acba92bef14565f9d92ef416677b6464d3ce'
seal = json.loads(seal_raw)
assert seal['payload_count'] == len(seal['files']) == 86
expected = {r['path'] for r in seal['files']} | {'SHA256.json'}
assert {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob('*') if p.is_file()} == expected
for row in seal['files']:
    raw = (SOURCE / row['path']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
assert not OUT.exists()
OUT.mkdir()
shutil.copytree(SOURCE, OUT / 'collection')
(OUT / '.gitattributes').write_bytes(b'* -text\n')
launch = ROOT / '_scratch/gemini-owned-runtime-components-council-collect01-launch'
names = ('plan.json', 'stdout.json', 'stderr.log', 'native-exit.raw.txt', 'exit.json')
assert {p.name for p in launch.iterdir()} == set(names)
assert (launch / 'native-exit.raw.txt').read_text().strip() == '0'
assert (launch / 'stderr.log').read_bytes() == b''
receipt = json.loads((launch / 'exit.json').read_bytes())
assert receipt['actual_native_exit'] == 0 and receipt['inputs_unchanged'] is True
assert all(r['actual_sha256'] == r['expected_sha256'] for r in receipt['input_checks'])
(OUT / 'collector-launch').mkdir()
for name in names:
    shutil.copyfile(launch / name, OUT / 'collector-launch' / name)
for name in ('OWNED-RUNTIME-COUNCIL-COLLECTION01-ACTUAL.json', 'OWNED-RUNTIME-COUNCIL-APPLY01-ACTUAL.json'):
    raw = (ROOT / '_scratch' / name).read_bytes()
    assert json.loads(raw)['exit_code'] == 0
    (OUT / name).write_bytes(raw)
raw_worker = (SOURCE / 'worker-report.md').read_bytes()
raw_checkout = REPORT.read_bytes()
assert sha(raw_worker) == '9a8bc8e6103e86ebd13eba9cc1c9472c83b2a01f07f1c4192346ed5c7aeeadaf'
assert raw_worker.replace(b'\r\n', b'\n') == raw_checkout.replace(b'\r\n', b'\n')
REPORT.write_bytes(raw_worker)
assert REPORT.read_bytes() == raw_worker
transport = {'git_apply_actual_tool':'e2f730', 'actual_exit':0,
             'application':'three-way requested, direct fallback for new file',
             'worker_report_sha256':sha(raw_worker), 'applied_checkout_sha256':sha(raw_checkout),
             'only_crlf_lf_transport':True, 'checkout_restored_to_exact_worker_bytes':True}
(OUT / 'report-integration.json').write_text(json.dumps(transport, indent=2)+'\n', encoding='utf-8')
control_path = Path(r'E:\AI\projects\agent-control-room\src\core\worktrees.ts')
control_raw = control_path.read_bytes()
assert sha(control_raw) == '3750717b853f4444c879911380de4e9a4530660f39810bc0d3bc3b76e9a08a1b'
(OUT / 'current-control-room-worktrees.ts.txt').write_bytes(control_raw)
(OUT / 'current-control-room-source-scope.json').write_text(json.dumps({
    'path':str(control_path), 'sha256':sha(control_raw), 'read_only_current_source_observation':True,
    'frozen_dispatch_source_identity_claim':False,
    'finding':'assertGoalInputsCommitted adds visited references before outside-root/absent-path skips and returns that set; the event counter is not twelve file receipts.'
}, indent=2)+'\n', encoding='utf-8')
shutil.copyfile(Path(__file__), OUT / 'assemble-evidence.py')
rows = []
for p in sorted(OUT.rglob('*')):
    if p.is_file():
        raw = p.read_bytes()
        rows.append({'path':p.relative_to(OUT).as_posix(), 'bytes':len(raw), 'sha256':sha(raw)})
manifest = {'schema':1, 'payload_count':len(rows), 'excluded':['SHA256.json'], 'files':rows}
(OUT / 'SHA256.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
assert {p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()} == {r['path'] for r in rows} | {'SHA256.json'}
for row in rows:
    raw = (OUT / row['path']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
print(json.dumps({'payload_count':len(rows), 'bytes':sum(r['bytes'] for r in rows),
                  'manifest_sha256':sha((OUT/'SHA256.json').read_bytes()),
                  'collector_payloads':86, 'current_bindings':17, 'events':364,
                  'report_restored':True, 'no_tests_executed':True}))
