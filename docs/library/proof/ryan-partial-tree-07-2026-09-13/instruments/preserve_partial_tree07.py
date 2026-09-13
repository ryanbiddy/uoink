"""Preserve an interrupted full-tree observation without inventing an exit."""
import collections,datetime as dt,hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
raw=s/'ryan-final-partitioned-07'
out=r/'docs/library/proof/ryan-partial-tree-07-2026-09-13'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()=='e53fe0e52131d7b210484b7c89850d1bcb31b9ee'
assert not (raw/'summary.json').exists() and not (s/'ryan-final-partitioned-07-main/tests.xml').exists()
expected=set(json.loads((raw/'expected-membership.json').read_text()))
reports=[json.loads(line) for line in (raw/'main/reports.jsonl').read_text().splitlines()]
grouped=collections.defaultdict(list)
for row in reports:grouped[row['nodeid']].append(row)
observed=collections.Counter();incomplete={}
for node,events in grouped.items():
    phases={row['when'] for row in events}
    if 'teardown' not in phases:
        incomplete[node]=events;continue
    if any(row['outcome']=='failed' for row in events):status='failed_or_error'
    elif any(row['outcome']=='skipped' for row in events):status='skipped'
    elif any(row['when']=='call' and row['outcome']=='passed' for row in events):status='passed'
    else:status='incomplete'
    observed[status]+=1
record={'source':'e53fe0e52131d7b210484b7c89850d1bcb31b9ee','result':'PARTIAL / interrupted; no aggregate result',
        'collected_cases':len(expected),'completed_case_reports':dict(observed),'incomplete_cases':incomplete,
        'cases_without_any_report':sorted(expected-set(grouped)),
        'main_exit':None,'media_partition_executed':False,'complete_disjoint_union':False,
        'diagnosis':'Exec handle 23389 is missing; two read-only process inventories found no relevant Python process. The last event is setup for BC3e chapter_metadata at 07:38:02 UTC. No main XML, result, terminal session or aggregate summary was written. Host last boot precedes this run. Exact termination cause is unknown.',
        'repair':'Use a separate hidden observer process with a durable PID/heartbeat/child-exit record and fresh full-tree label. Preserve every case, existing xfail body and only the S21 exclusion.',
        'recorded_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'release_ready':False}
out.mkdir(exist_ok=False);(out/'.gitattributes').write_bytes(b'* -text\n')
def copy(path,relative):
    target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
for label in ('ryan-final-partitioned-07','ryan-final-partitioned-07-collection','ryan-final-partitioned-07-main'):
    for path in (s/label).rglob('*'):
        if path.is_file() and path.suffix in ('.json','.jsonl','.xml','.log','.py'):
            copy(path,Path('raw')/label/path.relative_to(s/label))
for name in ('run_combined_candidate13.py','run_partitioned_repaired_tree.py','partition_receipt_plugin.py','integrator_verify.py','preserve_partial_tree07.py'):
    copy(s/name,Path('instruments')/name)
(out/'summary.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in record.items() if k not in ('cases_without_any_report','incomplete_cases')},indent=2))
print(json.dumps({'payloads':len(files),'incomplete_cases':list(incomplete),'no_report_cases':len(record['cases_without_any_report'])}))
