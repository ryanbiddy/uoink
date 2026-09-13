"""Read actual inert/archived receipts; no product execution or old result edits."""
import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

r=Path(__file__).resolve().parents[1]
out=r/'_scratch/partition-exit-wiring01'
out.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('partition_exit_contract',r/'_scratch/partition_exit_contract.py')
contract=importlib.util.module_from_spec(spec);sys.modules[spec.name]=contract;spec.loader.exec_module(contract)
inputs={}
def read(path,kind='json'):
    data=path.read_bytes()
    inputs[str(path.relative_to(r))]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return json.loads(data) if kind=='json' else data
def validate(run,receipt,outer):
    return contract.validate_partition(
        selected=read(receipt/'membership.json'),
        reports=[json.loads(line) for line in read(receipt/'reports.jsonl','bytes').splitlines()],
        session=read(receipt/'session.json'),
        verifier_results=read(run/'results.json'),outer_exit=outer,
        junit_xml=read(run/'tests.xml','bytes'))
facts={}
double=validate(r/'_scratch/partition-contract-double01',r/'_scratch/partition-contract-double01-receipt/partition',1)
assert double['result']=='FAIL' and double['counts']=={'passed':1,'error':1}
assert double['case_count']==2 and double['failed_phase_count']==2 and double['junit']['case_elements']==3
facts['deliberate_double_failure']={k:v for k,v in double.items() if k!='cases'}
try:
    validate(r/'_scratch/partition-contract-shutdown01',r/'_scratch/partition-contract-shutdown01-receipt/partition',1)
except contract.PartitionContractError as error:
    facts['deliberate_late_shutdown']={'qualification':'REFUSED','reason':str(error),'product_result':None}
else:
    raise AssertionError('Late shutdown failure was incorrectly accepted')
old_counts={}
for name,expected_exit in [('main',1),('media',0)]:
    old=validate(r/('_scratch/ryan-final-partitioned-08-'+name),r/('_scratch/ryan-final-partitioned-08/'+name),expected_exit)
    facts['archived_tree08_'+name]={k:v for k,v in old.items() if k not in ('cases','failed_phases')}
    for status,count in old['counts'].items():old_counts[status]=old_counts.get(status,0)+count
assert old_counts=={'passed':2675,'failed':51,'skipped':3},old_counts
facts['archived_tree08_result']={'result':'FAIL','counts':old_counts,'new_product_execution':False}
for name in ['run_partitioned_mirror_tree09.py','seal_partitioned_mirror_tree09.py','partition_exit_contract.py']:
    source=read(r/'_scratch'/name,'bytes')
    ast.parse(source,filename=name)
    shutil.copyfile(r/'_scratch'/name,out/name)
facts['prepared_syntax']=['run_partitioned_mirror_tree09.py','seal_partitioned_mirror_tree09.py','partition_exit_contract.py']
for label in ['mirror-tree09-preflight-2026-09-13','ryan-final-partitioned-08-2026-09-13']:
    folder=r/'docs/library/proof'/label
    manifest=read(folder/'SHA256.json')
    rows=manifest['files']
    for name,row in rows.items():
        data=(folder/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==row['sha256'],(label,name)
    facts[label]={'unchanged_payloads':len(rows)}
facts.update(source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),
             scope='Reader-only validation and syntax; no tree09 product run',release_ready=False,input_receipts=inputs)
shutil.copyfile(Path(__file__),out/Path(__file__).name)
(out/'result.json').write_text(json.dumps(facts,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in facts.items() if k!='input_receipts'},indent=2))
