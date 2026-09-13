"""Copy, compare and seal only author vpr03 text receipts; no reader execution."""
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
scratch = out.parent
source = scratch / 'vad-plain-state-reader-proposal03'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
manifest_raw = (source / 'SHA256.json').read_bytes()
assert sha(manifest_raw) == '236a86c300a180281dabcad46f8ba371daa28e42cbf3032735013eeedca2a397'
manifest = json.loads(manifest_raw)
for row in manifest['files']:
    raw = (source / row['path']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
assert len(manifest['files']) == 25
run_names = ('actual-exit.json', 'checked-result.json', 'fixed-plan.json', 'INPUTS.json',
             'launch-plan.json', 'plain_state_reader.py', 'qualify_reader.py',
             'root-admission.json', 'stderr.log', 'stdout.json')
outer_names = ('actual-exit.json', 'command.json', 'stderr.log', 'stdout.log')
copies = [(source / 'runs/vpr03' / name, 'run-vpr03/' + name) for name in run_names]
copies += [(source / 'outer/20260913T1646598007096Z' / name, 'outer-vpr03/' + name)
           for name in outer_names]
copies += [(source / 'SHA256.json', 'preparation03-SHA256.json'),
           (scratch / 'ASTRA-VAD-READER-ADMISSION03.json', 'root-admission.json'),
           (scratch / 'ASTRA-VAD-READER-ADMISSION03-2026-09-13.md', 'root-admission.md')]
for path, relative in copies:
    raw = path.read_bytes()
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    assert target.read_bytes() == raw
with (out / '.gitattributes').open('x', encoding='ascii', newline='\n') as stream:
    stream.write('* -text\n')
report = json.loads((out / 'run-vpr03/stdout.json').read_bytes())
expected = json.loads((source / 'EXPECTED-CASES.json').read_bytes())
assert [row['case'] for row in report['cases']] == expected and len(expected) == 82
assert all(row['passed'] is True for row in report['cases'])
assert report['guard']['valid'] and not report['guard']['unexpected_events']
assert json.loads((out / 'run-vpr03/actual-exit.json').read_bytes())['actual_child_exit'] == 0
assert json.loads((out / 'outer-vpr03/actual-exit.json').read_text(encoding='utf-8-sig'))['actual_outer_exit'] == 0
rows = []
for path in sorted(out.rglob('*')):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({'path': path.relative_to(out).as_posix(), 'bytes': len(raw),
                     'sha256': sha(raw)})
result = {'schema': 'uoink.documentary-payload-manifest.v1',
          'payload_count': len(rows), 'payload_bytes': sum(row['bytes'] for row in rows),
          'cases': 82, 'passed': 82, 'failed': 0, 'skipped': 0, 'guard_valid': True,
          'actual_child_exit': 0, 'actual_outer_exit': 0,
          'preparation_payloads_unchanged': 25, 'files': rows}
raw = (json.dumps(result, indent=2) + '\n').encode('utf-8')
with (out / 'SHA256.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(rows), 'payload_bytes': result['payload_bytes'],
                  'manifest_sha256': sha(raw), 'copied_receipts_match': True,
                  'complete_case_membership': True, 'prepared_inputs_unchanged': 25}))
