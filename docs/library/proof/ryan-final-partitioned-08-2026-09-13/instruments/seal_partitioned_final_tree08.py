"""Seal original partition observations and compare membership with the prior tree."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
p=argparse.ArgumentParser();p.add_argument('--label',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1];raw=r/'_scratch'/a.label
summary=json.loads((raw/'summary.json').read_text(encoding='utf8'))
out=r/'docs/library/proof/ryan-final-partitioned-08-2026-09-13';out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
assert summary['complete_disjoint_union'] and summary['source']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=r,text=True).strip()
def copy(src,rel):
 dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
for src in raw.rglob('*'):
 if src.is_file():copy(src,Path('partition-observation')/src.relative_to(raw))
seconds={}
for run in json.loads((raw/'runs.json').read_text(encoding='utf8')):
 folder=r/'_scratch'/run['label']
 for src in folder.rglob('*'):
  if src.is_file() and src.suffix in ('.json','.xml','.log','.py'):copy(src,Path('raw')/run['name']/src.relative_to(folder))
 if run['name']!='collection':
  seconds[run['name']]=sum(float(suite.get('time','0')) for suite in ET.parse(folder/'tests.xml').getroot().iter('testsuite'))
for name in ('run_partitioned_repaired_tree.py','partition_receipt_plugin.py','integrator_verify.py','seal_partitioned_final_tree08.py','run_complete_candidate_durable.py','rebind_package09_instruments13.py','fix_tree08_sealer_preflight.py','tree08-sealer-preflight.json','run_combined_candidate13.py','prepare_package09_instruments.py','prepare_package09_instruments02.py','package09-preparation-refusal01.json','seal_partitioned_final_tree07.py.diff'):
 copy(r/'_scratch'/name,Path('instruments')/name)
supervisor=r/'_scratch/ryan-final-partitioned-08-supervisor'
state=json.loads((supervisor/'state.json').read_text(encoding='utf8'))
assert state['source']==summary['source'] and state['status']=='child_exited' and state['child_exit'] in (0,1), state
assert state['aggregate_summary_present'] is True and state['aggregate_summary_sha256']==hashlib.sha256((raw/'summary.json').read_bytes()).hexdigest()
for folder in ('ryan-final-partitioned-08-supervisor','ryan-final-partitioned-08-launch','durable-tree-preflight01-supervisor','package09-unused-drafts-before-tree08'):
 for src in (r/'_scratch'/folder).rglob('*'):
  if src.is_file():copy(src,Path('durable-observer')/folder/src.relative_to(r/'_scratch'/folder))
for filename in ('membership.json','session.json'):
 copy(r/'_scratch/partition-preflight-01/collection'/filename,Path('instrument-preflight')/filename)
for filename in ('results.json','tests.log','tests.xml'):
 copy(r/'_scratch/partition-collect-preflight-01'/filename,Path('instrument-preflight')/filename)
expected=set(json.loads((raw/'expected-membership.json').read_text(encoding='utf8')))
before=set(json.loads((r/'_scratch/ryan-final-partitioned-06/expected-membership.json').read_text(encoding='utf8')))
added=expected-before;missing=before-expected
expected_added_by_file = {'tests/test_installer_signing.py': 26, 'tests/test_nltk_local_wheel.py': 29, 'tests/test_nltk_pathsec_backport.py': 28, 'tests/test_nltk_preparation_boundaries.py': 10, 'tests/test_nltk_wheel_boundaries.py': 9, 'tests/test_runtime_graph.py': 13, 'tests/test_runtime_graph_boundaries.py': 18, 'tests/test_signing_host_selection.py': 4, 'tests/test_signing_receipts.py': 10}
actual_added_by_file = {name:sum(n.split('::')[0]==name for n in added) for name in expected_added_by_file}
assert not missing and len(added)==147 and actual_added_by_file==expected_added_by_file and all(n.split('::')[0] in expected_added_by_file for n in added)
summary.update(previous_collected_cases=len(before),new_cases=sorted(added),missing_prior_cases=sorted(missing),test_process_seconds=seconds,total_test_process_seconds=sum(seconds.values()),source_scope_check='No modifications/deletions to prior tests or P4 fixture guard; only added regression files; exact new case membership checked')
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
changes=subprocess.check_output(['git','diff','--name-status','7109182',summary['source'],'--','tests','scripts/install_receipt/p4_prepare_fixture.py'],cwd=r)
(out/'existing-test-change-check.txt').write_bytes(changes)
files={q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(out.rglob('*')) if q.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'summary':summary},indent=2))
