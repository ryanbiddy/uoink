"""Data-only seal of the bounded actual-adapter source proposal."""
from pathlib import Path
import hashlib
import json
HERE=Path(__file__).parent
bindings=json.loads((HERE/'SOURCE-BINDINGS.json').read_bytes())
assert hashlib.sha256((HERE/'generated_adapter_flow.py').read_bytes()).hexdigest()==bindings['candidate_sha256']
for row in bindings['inherited_source_bindings']:
    raw=Path(row['path']).read_bytes()
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
rows=[]
for path in sorted(HERE.rglob('*')):
    if path.is_file():
        raw=path.read_bytes()
        rows.append({'path':path.relative_to(HERE).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
value={'schema':'uoink.scratch-source-preparation.v1','payload_count':len(rows),'payload_bytes':sum(r['bytes'] for r in rows),
       'candidate_executions':0,'files':rows}
raw=(json.dumps(value,indent=2)+'\n').encode()
with (HERE/'PREPARATION-MANIFEST.json').open('xb') as stream: stream.write(raw)
print(json.dumps({'payload_count':len(rows),'payload_bytes':value['payload_bytes'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),'candidate_executions':0}))
