"""Copy and seal only the known vpr01 text receipts; execute no proposal."""
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
scratch = out.parent
source = scratch / 'vad-plain-state-reader-proposal01'
rows = []
run_names = ('actual-exit.json', 'fixed-plan.json', 'INPUTS.json', 'launch-plan.json',
             'plain_state_reader.py', 'qualify_reader.py', 'root-admission.json',
             'stderr.log', 'stdout.json')
outer_names = ('actual-exit.json', 'command.json', 'stderr.log', 'stdout.log')
copies = [(source / 'runs/vpr01' / name, 'run-vpr01/' + name) for name in run_names]
copies += [(source / 'outer/20260913T1628531395712Z' / name, 'outer-vpr01/' + name)
           for name in outer_names]
copies += [(source / 'SHA256.json', 'preparation-SHA256.json'),
           (scratch / 'ASTRA-VAD-READER-ADMISSION01.json', 'root-admission.json'),
           (scratch / 'ASTRA-VAD-READER-ADMISSION-2026-09-13.md', 'root-admission.md')]
for path, relative in copies:
    raw = path.read_bytes()
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
    assert target.read_bytes() == raw
with (out / '.gitattributes').open('x', encoding='ascii', newline='\n') as stream:
    stream.write('* -text\n')
for path in sorted(out.rglob('*')):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({'path': path.relative_to(out).as_posix(), 'bytes': len(raw),
                     'sha256': hashlib.sha256(raw).hexdigest()})
manifest = {'schema': 'uoink.documentary-payload-manifest.v1',
            'payload_count': len(rows), 'payload_bytes': sum(row['bytes'] for row in rows),
            'case_functions_executed': 0, 'qualification_valid': False,
            'actual_child_exit': 1, 'actual_outer_exit': 1, 'files': rows}
raw = (json.dumps(manifest, indent=2) + '\n').encode('utf-8')
with (out / 'SHA256.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps({'payload_count': len(rows), 'payload_bytes': manifest['payload_bytes'],
                  'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                  'copied_receipts_match': True}))
