"""Copy and seal only known vpr02 text receipts; execute no reader/harness."""
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
scratch = out.parent
source = scratch / 'vad-plain-state-reader-proposal02'
run_names = ('actual-exit.json', 'checked-result.json', 'fixed-plan.json', 'INPUTS.json',
             'launch-plan.json', 'plain_state_reader.py', 'qualify_reader.py',
             'root-admission.json', 'stderr.log', 'stdout.json')
outer_names = ('actual-exit.json', 'command.json', 'stderr.log', 'stdout.log')
copies = [(source / 'runs/vpr02' / name, 'run-vpr02/' + name) for name in run_names]
copies += [(source / 'outer/20260913T1639230580686Z' / name, 'outer-vpr02/' + name)
           for name in outer_names]
copies += [(source / 'SHA256.json', 'preparation02-SHA256.json'),
           (scratch / 'ASTRA-VAD-READER-ADMISSION02.json', 'root-admission.json'),
           (scratch / 'ASTRA-VAD-READER-ADMISSION02-2026-09-13.md', 'root-admission.md')]
for path, relative in copies:
    raw = path.read_bytes()
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    assert target.read_bytes() == raw
with (out / '.gitattributes').open('x', encoding='ascii', newline='\n') as stream:
    stream.write('* -text\n')
rows = []
for path in sorted(out.rglob('*')):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({'path': path.relative_to(out).as_posix(), 'bytes': len(raw),
                     'sha256': hashlib.sha256(raw).hexdigest()})
manifest = {'schema': 'uoink.documentary-payload-manifest.v1',
            'payload_count': len(rows), 'payload_bytes': sum(row['bytes'] for row in rows),
            'cases': 76, 'passed': 75, 'failed': 1, 'skipped': 0, 'guard_valid': True,
            'actual_child_exit': 1, 'actual_outer_exit': 1, 'files': rows}
raw = (json.dumps(manifest, indent=2) + '\n').encode('utf-8')
with (out / 'SHA256.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(rows), 'payload_bytes': manifest['payload_bytes'],
                  'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                  'copied_receipts_match': True}))
