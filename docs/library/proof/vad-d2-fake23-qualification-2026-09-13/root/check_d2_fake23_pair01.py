"""Read retained generated qualification receipts only; do not rerun cases."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
roots=(ROOT/'_scratch/vad-d2-dormant-invocation-proposal02',ROOT/'_scratch/astra-d2-fake23-confirmation01')
records=[]
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
expected_counts=dict(passed=23,failed=0,errors=0,skipped=0,subtests=0,tests_run=23)
for folder in roots:
    run=folder/'fake23-01'
    output=read(run/'stdout.json')
    checked=read(run/'checked-result.json')
    after=read(run/'after-inputs.json')
    actual=read(run/'actual-exit.json')
    names=read(folder/'EXPECTED-CASES.json')
    assert output['counts']==expected_counts
    assert [row['name'] for row in output['cases']]==names and len(names)==23
    assert all(row['status']=='passed' for row in output['cases'])
    assert len(output['guards'])==9 and all(value is True for value in output['guards'].values())
    assert output['guard_valid'] is True and output['registry_trap_count']==25
    assert output['qualification_exit']==actual['actual_native_exit']==0
    assert (run/'raw-native-exit.txt').read_bytes()==b'0\n'
    assert not (run/'stderr.log').read_bytes()
    assert output['instrumentation_failure'] is None and not output['failures'] and not output['errors']
    assert checked['fake23_passed'] is True and checked['exact_ordered_membership'] is True
    assert all(checked[k] is True and after[k] is True for k in ('manifest_unchanged','admission_unchanged'))
    assert checked['inputs_unchanged'] is True and after['unchanged'] is True
    assert output['actual_converter_or_model_executed'] is False and output['real_d2_authority'] is False
    inputs=read(folder/'QUALIFICATION-INPUTS.json')['files']
    assert len(inputs)==9
    assert all(sha(folder/name)==digest==after['input_hashes'][name] for name,digest in inputs.items())
    assert sha(folder/'ROOT-FAKE23-ADMISSION.json')==after['admission_before_sha256']==after['admission_after_sha256']
    records.append({'root':folder.relative_to(ROOT).as_posix(),'counts':output['counts'],
        'elapsed_case_seconds':output['elapsed_seconds'],'stdout_bytes':(run/'stdout.json').stat().st_size,
        'stdout_sha256':sha(run/'stdout.json'),'guards':9,'registry_traps':25,
        'actual_exit':0,'sources_and_controls_unchanged':True,'cases':output['cases']})
assert records[0]['cases']==records[1]['cases']
result={'scope':'D2 generated adapter contracts only','records':records,'same_ordered_case_objects':True,
        'distinct_cases':23,'real_converter_executed':False,'real_D2_approved':False}
dest=ROOT/'_scratch/D2-FAKE23-PAIR-CHECK.json'
assert not dest.exists()
dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'distinct_cases':23,'passes_per_copy':23,'failures_errors_skips':0,
                  'same_ordered_case_objects':True,'real_D2_approved':False,'records':[{k:v for k,v in row.items() if k!='cases'} for row in records]}))
