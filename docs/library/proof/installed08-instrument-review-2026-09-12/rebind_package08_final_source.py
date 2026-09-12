import ast,difflib,hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
assert source=='b8e44fbc0a16950a22b29ead66951fcb80b2d6e8'
record=s/'package08-instrument-adaptations.json';original=record.read_bytes()
(s/'package08-instrument-adaptations-before-final-source.json').write_bytes(original)
rows=json.loads(original);changes=[]
for name in ('run_installed_client08.py','observe_published_chapter08.py'):
    p=s/name;old=p.read_text(encoding='utf8');needle='a25e3be1c4b8ca1f0c064dd8383b49870f23465f'
    assert old.count(needle)==1
    new=old.replace(needle,source);ast.parse(new)
    (s/(name+'.a25-draft.txt')).write_bytes(p.read_bytes())
    p.write_text(new,encoding='utf8',newline='\n')
    delta=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a25-draft/'+name,tofile='final-source/'+name))
    (s/(name+'.final-source.diff')).write_text(delta,encoding='utf8')
    for row in rows:
        if row['after']==name:
            row['a25_draft_sha256']=row['after_sha256'];row['after_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
            row['final_source_rebinding']='Expected build_source only; before any observation, with every assertion preserved.'
    changes.append({'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source':source,'executed':False})
record.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8',newline='\n')
old=(s/'seal_partitioned_final_tree05.py').read_text(encoding='utf8')
new=old.replace('ryan-final-partitioned-05-2026-09-12','ryan-final-partitioned-06-2026-09-12').replace('seal_partitioned_final_tree05.py','seal_partitioned_final_tree06.py').replace('_scratch/ryan-final-partitioned-04/expected-membership.json','_scratch/ryan-final-partitioned-05/expected-membership.json')
new=new.replace("allowed = ('tests/test_note_readiness_truth.py::',)","allowed = ('tests/test_dashboard_media_detail_truth.py::','tests/test_media_detail_boundaries.py::')").replace('len(added)==16','len(added)==23')
ast.parse(new);(s/'seal_partitioned_final_tree06.py').write_text(new,encoding='utf8',newline='\n')
(s/'seal_partitioned_final_tree06.py.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='seal_partitioned_final_tree05.py',tofile='seal_partitioned_final_tree06.py')),encoding='utf8')
(s/'package08-final-source-rebinding.json').write_text(json.dumps({'source':source,'changes':changes,'tree_sealer':'Same complete-union checks; compare preceding 2559 cases with 23 specific additions.'},indent=2)+'\n',encoding='utf8')
print(json.dumps({'source':source,'client_observers_rebound':len(changes),'tree_sealer_prepared':True,'observations_executed':False}))
