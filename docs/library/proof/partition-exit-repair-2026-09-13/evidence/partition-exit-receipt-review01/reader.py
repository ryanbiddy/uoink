from pathlib import Path
import importlib.util
import json
import sys
r=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
out=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('partition_exit_contract',r/'_scratch/partition_exit_contract.py')
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
archive=read(r/'_scratch/ryan-final-partitioned-08/runs.json')
def archived_exit(name):return next(row['exit'] for row in archive if row['name']==name)
cases=[
 ('pipeline01','mirror-observer-pipeline01','mirror-observer-pipeline01-receipt/partition',1,{'passed':1,'failed':1},None),
 ('double01','partition-contract-double01','partition-contract-double01-receipt/partition',read(r/'_scratch/partition-contract-double01-receipt/launcher-result.json')['outer_exit'],{'passed':1,'error':1},None),
 ('shutdown01','partition-contract-shutdown01','partition-contract-shutdown01-receipt/partition',read(r/'_scratch/partition-contract-shutdown01-receipt/launcher-result.json')['outer_exit'],None,'actual pytest exit disagrees with session exit'),
 ('tree08-main','ryan-final-partitioned-08-main','ryan-final-partitioned-08/main',archived_exit('main'),{'passed':2673,'failed':51,'skipped':3},None),
 ('tree08-media','ryan-final-partitioned-08-media','ryan-final-partitioned-08/media',archived_exit('media'),{'passed':2},None),
]
rows=[]
for name,run,receipt,outer,counts,refusal in cases:
    folder=r/'_scratch'/receipt;runroot=r/'_scratch'/run
    inputs={'selected':read(folder/'membership.json'),'reports':[json.loads(line) for line in (folder/'reports.jsonl').read_text(encoding='utf8').splitlines()],
            'session':read(folder/'session.json'),'verifier_results':read(runroot/'results.json'),'outer_exit':outer,'junit_xml':(runroot/'tests.xml').read_bytes()}
    try:
        result=contract.validate_partition(**inputs)
    except Exception as error:
        matched=bool(refusal and isinstance(error,contract.PartitionContractError) and refusal in str(error))
        row={'name':name,'contract_refused':True,'error_type':type(error).__name__,'message':str(error),'expected_refusal':refusal,'validation_matched_expectation':matched}
    else:
        matched=refusal is None and result['counts']==counts
        row={'name':name,'contract_refused':False,'recorded_product_or_smoke_result':result['result'],'counts':result['counts'],
             'case_count':result['case_count'],'failed_phase_count':result['failed_phase_count'],'report_count':result['report_count'],
             'pytest_exit':result['pytest_exit'],'outer_exit':result['outer_exit'],'junit':result['junit'],'validation_matched_expectation':matched}
    rows.append(row)
    print(json.dumps(row),flush=True)
summary={'scope':'read-only validation of existing raw receipts; no tests or product rerun','expectations_met':all(row['validation_matched_expectation'] for row in rows),'rows':rows}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
raise SystemExit(int(not summary['expectations_met']))
