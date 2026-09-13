"""Preserve a withdrawn reader proposal and prepare unchanged-graph verification."""
from pathlib import Path
import hashlib,json,shutil
r=Path(__file__).resolve().parents[1]
capture=r/'_scratch/runtime-candidate02-metadata'
withdrawn=r/'_scratch/runtime-candidate02-astra-graph02'
assert list(withdrawn.iterdir())==[]
for name in ['review_runtime_candidate02_graph02.py','RUNTIME-CANDIDATE02-EXTRAS-REPAIR-BRIEF-2026-09-13.md']:
    shutil.copyfile(r/'_scratch'/name,withdrawn/name)
(withdrawn/'preflight-result.json').write_text(json.dumps({
    'actual_exit':1,'observed_tool_chunk':'34d4e2','failure':'AssertionError at original-lock composite-key assertion',
    'native_log_file':None,'new_selection_written':False,'checker_invoked':False,
    'reason':'Proposed correction incorrectly treated transitive extras as root requirements.',
    'disposition':'Withdrawn. Graph01 already propagates both extras. No graph02 measurement exists.'},indent=2)+'\n',encoding='utf8')
shutil.copyfile(r/'_scratch/RUNTIME-CANDIDATE02-ASTRA-REVIEW-BRIEF-2026-09-13.md',withdrawn/'withdrawal-and-next-review.md')
manifest=json.loads((capture/'SHA256.json').read_text())
for name,digest in manifest.items():assert hashlib.sha256((capture/name).read_bytes()).hexdigest()==digest
graph=json.loads((capture/'graph01/result.json').read_text())
assert graph['active_extras']=={'fsspec':['http'],'pyjwt':['crypto']}
assert graph['active_edges_count']==282 and graph['selection_count']==144 and not graph['passed']
driver=(capture/'instruments/run_runtime_candidate02_graph.py').read_text()
old="output = capture / 'graph01'"
assert driver.count(old)==1
driver=driver.replace(old,"output = root / '_scratch/runtime-candidate02-astra-review01'")
path=r/'_scratch/run_runtime_candidate02_astra_review01.py'
assert not path.exists();path.write_text(driver,encoding='utf8')
print(json.dumps({'old_payloads_verified':len(manifest),'graph01_extras':graph['active_extras'],'prepared':str(path),'graph02_invoked':False}))
