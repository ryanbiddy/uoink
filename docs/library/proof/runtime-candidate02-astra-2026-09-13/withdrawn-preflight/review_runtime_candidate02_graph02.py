"""Correct only omitted selection extras, preserving the original failed graph."""
from pathlib import Path
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

r=Path(__file__).resolve().parents[1]
capture=r/'_scratch/runtime-candidate02-metadata'
out=r/'_scratch/runtime-candidate02-astra-graph02';out.mkdir(exist_ok=False)
manifest=json.loads((capture/'SHA256.json').read_text())
def verify():
    for name,digest in manifest.items():
        path=capture/name
        assert path.is_relative_to(capture) and '..' not in Path(name).parts
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
verify()
retrievals=json.loads((capture/'retrievals.json').read_text())
assert len(retrievals)==9
for item in retrievals:
    assert item['status']==200
    data=(capture/item['saved_file']).read_bytes()
    assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
    assert item['url']==item['final_url']
bindings=json.loads((capture/'metadata-bindings.json').read_text())
metadata_checked=0
for item in bindings:
    if item.get('metadata_path'):
        data=(capture/'evidence'/item['metadata_path']).read_bytes()
        digest=hashlib.sha256(data).hexdigest()
        assert digest==item['metadata_sha256']==item['wheel']['core_metadata']['sha256']
        metadata_checked+=1
before=(capture/'selection.json').read_text()
selection=json.loads(before)
assert len(selection['selected'])==144
lock=(capture/'input-production-lock.txt').read_text()
for name,extra in [('fsspec','http'),('pyjwt','crypto')]:
    version=selection['selected'].pop(name)
    composite=name+'['+extra+']'
    assert composite+'=='+version in lock
    selection['selected'][composite]=version
after=json.dumps(selection,indent=2)+'\n'
(out/'selection-before.json').write_text(before,encoding='utf8')
(out/'selection.json').write_text(after,encoding='utf8')
(out/'selection-extras.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='candidate02/selection.json',tofile='graph02/selection.json')),encoding='utf8')
original=json.loads((capture/'graph01/execution.json').read_text())
command=original['command'][:]
command[0]=sys.executable
command[command.index('--selection')+1]=str(out/'selection.json')
command[command.index('--output-json')+1]=str(out/'result.json')
validator=r/'scripts/check_runtime_graph.py'
assert hashlib.sha256(validator.read_bytes()).hexdigest()==original['validator_sha256']
environment={k:v for k,v in os.environ.items() if not re.search(r'(?i)(API.?KEY|ACCESS.?TOKEN|AUTH.?TOKEN|BEARER|ANTHROPIC|OPENAI|GEMINI|GROK|XAI|HF_TOKEN|HUGGING_FACE_HUB_TOKEN|BASE_URL)',k)}
environment.update(PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
record={'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),
        'command':command,'actual_exit':None,'validator_sha256':original['validator_sha256'],'before_verified_payloads':len(manifest),
        'retrievals_verified':len(retrievals),'metadata_hash_bindings_verified':metadata_checked,'product_or_model_execution':False}
(out/'execution.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
shutil.copyfile(Path(__file__),out/Path(__file__).name)
shutil.copyfile(r/'_scratch/RUNTIME-CANDIDATE02-EXTRAS-REPAIR-BRIEF-2026-09-13.md',out/'BRIEF.md')
with (out/'stdout.txt').open('wb') as stdout,(out/'stderr.txt').open('wb') as stderr:
    child=subprocess.run(command,cwd=r,env=environment,stdout=stdout,stderr=stderr)
record.update(actual_exit=child.returncode,finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
if (out/'result.json').is_file():
    result=json.loads((out/'result.json').read_text())
    record['result']={k:result.get(k) for k in ('status','passed','selection_count','active_edges_count','active_extras','missing_packages','conflicting_constraints','wheel_failures','incomplete_evidence','manifest_errors')}
verify();record['after_verified_payloads']=len(manifest)
(out/'execution.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in record.items() if k!='command'},indent=2))
raise SystemExit(child.returncode)
