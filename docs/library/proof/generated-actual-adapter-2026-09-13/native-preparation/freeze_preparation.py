"""Seal exact preparation text; never execute candidates or read support binaries."""
from pathlib import Path
import ast
import hashlib
import json
HERE=Path(__file__).parent
bindings=json.loads((HERE/'PREPARATION-BINDINGS.json').read_bytes())
mapping=json.loads((HERE/'SOURCE-INPUTS.json').read_bytes())
assert len(mapping['source_paths'])==len(mapping['source_sha256'])==12 and len(mapping['native_bindings'])==9
for name,path in mapping['source_paths'].items():
    raw=Path(path).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==mapping['source_sha256'][name]
    ast.parse(raw)
for name,key in [('dummy_bootstrap.py','bootstrap_sha256'),('run_actual_adapter01.ps1','launcher_sha256'),('SOURCE-INPUTS.json','source_map_sha256')]:
    assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==bindings[key]
assert not Path(bindings['run_path']).exists()
assert not (HERE/'ROOT-ADMISSION-drain.json').exists()
admission=json.loads((HERE/'ROOT-ADMISSION-drain.template.json').read_bytes())
assert admission['root_reviewed'] is False and admission['run_path']==bindings['run_path']
assert admission['source_inputs_sha256']==bindings['source_map_sha256'] and admission['launcher_sha256']==bindings['launcher_sha256']
rows=[]
for path in sorted(HERE.rglob('*')):
    if path.is_file():
        raw=path.read_bytes()
        rows.append({'path':path.relative_to(HERE).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
value={'schema':'uoink.scratch-native-preparation.v1','payload_count':len(rows),'payload_bytes':sum(r['bytes'] for r in rows),
       'candidate_executions':0,'files':rows}
raw=(json.dumps(value,indent=2)+'\n').encode()
with (HERE/'PREPARATION-MANIFEST.json').open('xb') as stream:stream.write(raw)
print(json.dumps({'payload_count':len(rows),'payload_bytes':value['payload_bytes'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),'candidate_executions':0}))
