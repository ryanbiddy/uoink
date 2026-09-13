"""Seal unchanged metadata evidence, actual independent review and withdrawn preflight."""
from pathlib import Path
import hashlib,json,shutil,subprocess
r=Path(__file__).resolve().parents[1]
capture=r/'_scratch/runtime-candidate02-metadata'
review=r/'_scratch/runtime-candidate02-astra-review01'
out=r/'docs/library/proof/runtime-candidate02-astra-2026-09-13'
manifest=json.loads((capture/'SHA256.json').read_text())
for name,digest in manifest.items():assert hashlib.sha256((capture/name).read_bytes()).hexdigest()==digest,name
old=json.loads((capture/'graph01/result.json').read_text());new=json.loads((review/'result.json').read_text())
assert old==new
for folder in [capture/'graph01',review]:
    execution=json.loads((folder/'execution.json').read_text())
    assert execution['actual_exit']==1
    assert execution['validator_sha256']==hashlib.sha256((r/'scripts/check_runtime_graph.py').read_bytes()).hexdigest()
assert new['selection_count']==144 and new['active_edges_count']==282
assert len(new['conflicting_constraints'])==5 and len(new['wheel_failures'])==2 and len(new['incomplete_evidence'])==1
assert not new['missing_packages'] and not new['manifest_errors'] and not new['passed']
assert new['active_extras']=={'fsspec':['http'],'pyjwt':['crypto']}
retrievals=json.loads((capture/'retrievals.json').read_text());assert len(retrievals)==9
for row in retrievals:
    data=(capture/row['saved_file']).read_bytes()
    assert row['status']==200 and row['url']==row['final_url'] and len(data)==row['bytes']
    assert hashlib.sha256(data).hexdigest()==row['sha256']
metadata=0
for row in json.loads((capture/'metadata-bindings.json').read_text()):
    if row.get('metadata_path'):
        digest=hashlib.sha256((capture/'evidence'/row['metadata_path']).read_bytes()).hexdigest()
        assert digest==row['metadata_sha256']==row['wheel']['core_metadata']['sha256']
        metadata+=1
out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
def copy(src,rel):
    dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    assert hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(dest.read_bytes()).digest()
for name in list(manifest)+['SHA256.json']:copy(capture/name,Path('original-capture')/name)
for folder,rel in [(review,'astra-review01'),(r/'_scratch/runtime-candidate02-astra-graph02','withdrawn-preflight')]:
    for src in sorted(folder.iterdir()):
        assert src.is_file();copy(src,Path(rel)/src.name)
for name in ['run_runtime_candidate02_astra_review01.py','prepare_runtime_independent_review01.py','RUNTIME-CANDIDATE02-ASTRA-REVIEW-BRIEF-2026-09-13.md','RUNTIME-MIGRATION-SCOPE-2026-09-13.md','seal_runtime_candidate02_astra01.py']:
    copy(r/'_scratch'/name,Path('instruments')/name)
copy(r/'docs/library/ASTRA-RUNTIME-CANDIDATE02-REVIEW-2026-09-13.md',Path('ASTRA-RUNTIME-CANDIDATE02-REVIEW-2026-09-13.md'))
summary={'source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),
         'original_payloads_unchanged':len(manifest),'retrievals_verified':len(retrievals),'exact_metadata_bindings_verified':metadata,
         'agent_exit':1,'astra_exit':1,'results_equal':True,'selected_versions':144,'active_edges':282,
         'missing_targets':0,'conflicts':5,'wheel_failures':2,'incomplete_evidence':1,'result':'FAIL',
         'withdrawn_preflight_checker_invoked':False,'release_ready':False,'product_or_model_execution':False}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'summary':summary}))
