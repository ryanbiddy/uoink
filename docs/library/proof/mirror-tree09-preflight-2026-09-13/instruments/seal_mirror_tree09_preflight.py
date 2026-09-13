import ast,collections,hashlib,json,shutil
from pathlib import Path
from xml.etree import ElementTree as ET
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
for row in json.loads((s/'mirror-state-plugin02/instrument-sha256.json').read_text()):
    p=Path(row['path']);assert p.resolve().is_relative_to(s.resolve())
    assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],str(p)
for label,total,failed in [('mirror-state-plugin01',14,0),('mirror-state-plugin02',15,0),('astra-mirror-state-plugin01',15,0),('mirror-observer-pipeline01',2,1)]:
    suites=list(ET.parse(s/label/'tests.xml').getroot().iter('testsuite'))
    assert sum(int(v.get('tests',0)) for v in suites)==total
    assert sum(int(v.get('failures',0)) for v in suites)==failed
    assert not sum(int(v.get(k,0)) for v in suites for k in ['errors','skipped'])
    assert json.loads((s/label/'results.json').read_text())[0]['exit']==int(failed>0)
receipt=s/'mirror-observer-pipeline01-receipt'
session=json.loads((receipt/'partition/session.json').read_text())
assert session=={'exit':1,'tests_collected':2,'tests_failed':1,'reports':6}
reports=[json.loads(line) for line in (receipt/'partition/reports.jsonl').read_text().splitlines()]
assert len(reports)==6 and len(set(json.loads((receipt/'partition/membership.json').read_text())))==2
rows=[json.loads(line) for line in (receipt/'mirror-state.jsonl').read_text().splitlines()]
assert rows[0]['event']=='observer_started' and rows[-1]['event']=='observer_finished'
assert len(rows)==5 and rows[-1]['diagnostic_complete'] and rows[-1]['observer_errors']==0
assert rows[-1]['pytest_exitstatus']==1 and rows[-1]['observation_attempts']==3
failed=[v for v in rows if v['event']=='mirror_state' and v['report']['outcome']=='failed']
assert len(failed)==1
assert failed[0]['state']['owners'][0]['sessions'][0]['_owned_created']==[{'key':70002,'value':1001000}]
assert failed[0]['state']['owners'][0]['thread_frame_present']
durable=json.loads((s/'durable-tree09-preflight01-supervisor/state.json').read_text())
assert durable['self_test'] and durable['child_exit']==0 and durable['status']=='child_exited'
assert hashlib.sha256((s/'run_complete_mirror_tree09_durable.py').read_bytes()).hexdigest()==durable['instrument_sha256']
for name in ['run_partitioned_mirror_tree09.py','run_complete_mirror_tree09_durable.py','seal_partitioned_mirror_tree09.py']:
    ast.parse((s/name).read_text())
out=r/'docs/library/proof/mirror-tree09-preflight-2026-09-13';out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
def copy(src,rel):
    target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
for folder in ['mirror-state-plugin01','mirror-state-plugin02','astra-mirror-state-plugin01','mirror-observer-pipeline01','mirror-observer-pipeline01-receipt','durable-tree09-preflight01-supervisor']:
    for p in (s/folder).rglob('*'):
        if p.is_file():copy(p,Path('observations')/folder/p.relative_to(s/folder))
for name in ['mirror_state_receipt_plugin.py','test_mirror_state_receipt_plugin.py','MIRROR-STATE-RECEIPT-REVIEW-2026-09-13.md','MIRROR-OBSERVER-PIPELINE-PREFLIGHT-BRIEF.md','test_phase4_mirror_observer_pipeline.py','run_mirror_observer_preflight.ps1','run_partitioned_repaired_tree.py','run_complete_candidate_durable.py','run_partitioned_mirror_tree09.py','run_complete_mirror_tree09_durable.py','run_partitioned_mirror_tree09.py.diff','run_complete_mirror_tree09_durable.py.diff','partition_receipt_plugin.py','integrator_verify.py','prepare_mirror_tree09_observer.py','mirror-tree09-instrument-preparation.json','MIRROR-COMBINED-TREE09-BRIEF-2026-09-13.md','seal_partitioned_mirror_tree09.py','seal_mirror_tree09_preflight.py']:
    copy(s/name,Path('instruments')/name)
copy(r/'docs/library/MIRROR-TREE09-OBSERVER-REVIEW-2026-09-13.md','MIRROR-TREE09-OBSERVER-REVIEW-2026-09-13.md')
(out/'summary.json').write_text(json.dumps({'agent_initial_unit_passed':14,'agent_corrected_unit_passed':15,'astra_unit_passed':15,'pipeline':{'passed':1,'deliberately_failed':1,'pytest_exit':1,'verifier_exit':1,'observations':3,'observer_errors':0},'supervisor_inert_child_exit':0,'full_product_tree_executed':False,'source_or_frozen_test_changed':False,'release_ready':False},indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'product_tree_executed':False,'pipeline_failed_cases':1}))
