"""Seal actual complete-tree counts and independently validate passive receipts."""
import collections,hashlib,json,shutil,subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
r=Path(__file__).resolve().parents[1];label='ryan-final-partitioned-09';raw=r/'_scratch'/label
def git(*args):return subprocess.check_output(['git',*args],cwd=r,text=True).strip()
summary=json.loads((raw/'summary.json').read_text(encoding='utf8'))
assert summary['source']==git('rev-parse','HEAD') and not git('status','--porcelain')
assert summary['complete_disjoint_union']
assert not git('diff','--diff-filter=CDMRTUXB','ff67b84',summary['source'],'--','tests','scripts/install_receipt/p4_prepare_fixture.py')
supervisor=r/'_scratch'/(label+'-supervisor');state=json.loads((supervisor/'state.json').read_text())
assert state['source']==summary['source'] and state['status']=='child_exited'
assert state['child_exit']==int(summary['result']=='FAIL') and state['aggregate_summary_present']
assert state['aggregate_summary_sha256']==hashlib.sha256((raw/'summary.json').read_bytes()).hexdigest()
runs=json.loads((raw/'runs.json').read_text());assert [v['name'] for v in runs]==['collection','main','media']
before=set(json.loads((r/'_scratch/ryan-final-partitioned-08/expected-membership.json').read_text()))
expected=set(json.loads((raw/'expected-membership.json').read_text()))
assert not before-expected
new_files=set(git('diff','--diff-filter=A','--name-only','9dd0cfb',summary['source'],'--','tests').splitlines())
assert all(n.split('::')[0] in new_files for n in expected-before)
actual=json.loads((raw/'cases.json').read_text());assert set(actual)==expected
assert dict(collections.Counter(v['status'] for v in actual.values()))==summary['counts']
counts=collections.Counter();seconds={}
for run in runs[1:]:
    suites=list(ET.parse(r/'_scratch'/run['label']/'tests.xml').getroot().iter('testsuite'))
    seconds[run['name']]=sum(float(s.get('time',0)) for s in suites)
    for suite in suites:
        total=int(suite.get('tests',0));failed=int(suite.get('failures',0));errors=int(suite.get('errors',0));skips=int(suite.get('skipped',0))
        counts.update({'passed':total-failed-errors-skips,'failed':failed,'error':errors,'skipped':skips})
assert +counts==collections.Counter(summary['counts'])
reports=[json.loads(line) for line in (raw/'main/reports.jsonl').read_text().splitlines()]
def capture_needed(row):
    file=row['nodeid'].split('::',1)[0].replace('\\','/').rsplit('/',1)[-1]
    return row['outcome']=='failed' or (row['when']=='teardown' and file.startswith('test_phase4'))
def key(row):return row['nodeid'],row['when'],row['outcome']
needed=collections.Counter(key(row) for row in reports if capture_needed(row))
observer=[json.loads(line) for line in (raw/'mirror-state.jsonl').read_text().splitlines()]
assert observer[0]['event']=='observer_started' and observer[-1]['event']=='observer_finished'
assert sum(row['event']=='observer_started' for row in observer)==1
assert sum(row['event']=='observer_finished' for row in observer)==1
assert all(row['event'] in ['observer_started','mirror_state','observer_finished'] for row in observer)
assert collections.Counter(key(row['report']) for row in observer if row['event']=='mirror_state')==needed
end=observer[-1]
assert end['diagnostic_complete'] and end['observer_errors']==0 and end['observation_attempts']==sum(needed.values())
assert end['pytest_exitstatus']==runs[1]['exit']
assert 'MIRROR STATE OBSERVER ERROR' not in (r/'_scratch'/runs[1]['label']/'tests.log').read_text()
out=r/'docs/library/proof/ryan-final-partitioned-09-2026-09-13';out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
def copy(src,rel):
    dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
for src in raw.rglob('*'):
    if src.is_file():copy(src,Path('partition-observation')/src.relative_to(raw))
for run in runs:
    folder=r/'_scratch'/run['label']
    for src in folder.rglob('*'):
        if src.is_file() and src.suffix in ('.py','.json','.jsonl','.xml','.log'):copy(src,Path('raw')/run['name']/src.relative_to(folder))
for name in [label+'-supervisor',label+'-launch']:
    for src in (r/'_scratch'/name).rglob('*'):
        if src.is_file():copy(src,Path('durable-observer')/name/src.relative_to(r/'_scratch'/name))
for name in ['run_partitioned_mirror_tree09.py','run_complete_mirror_tree09_durable.py','partition_receipt_plugin.py','mirror_state_receipt_plugin.py','integrator_verify.py','seal_partitioned_mirror_tree09.py','mirror-tree09-instrument-preparation.json','MIRROR-COMBINED-TREE09-BRIEF-2026-09-13.md']:
    copy(r/'_scratch'/name,Path('instruments')/name)
summary.update(new_cases_since_tree08=sorted(expected-before),test_process_seconds=seconds,observer_capture_count=sum(needed.values()),observer_diagnostic_complete=True,release_ready=False)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'summary':summary},indent=2))
