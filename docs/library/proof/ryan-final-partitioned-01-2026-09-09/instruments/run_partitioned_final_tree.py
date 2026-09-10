"""Execute every original case once in two guarded processes; preserve real failures."""
import argparse,collections,datetime as dt,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from xml.etree import ElementTree as ET
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--label',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1]
out=r/'_scratch'/a.label
assert out.parent==r/'_scratch' and a.label.startswith('ryan-final-partitioned-')
def git(*args):return subprocess.check_output(['git',*args],cwd=r,text=True).strip()
assert git('rev-parse','HEAD')==a.source and not git('status','--porcelain')
assert not git('diff','--diff-filter=CDMRTUXB','7109182',a.source,'--','tests','scripts/install_receipt/p4_prepare_fixture.py')
out.mkdir(exist_ok=False)
media=['tests/test_long_video_v324.py::test_screenshot_phase_end_to_end',
       'tests/test_screenshot_extraction_cm10.py::test_limited_range_15_second_fixture_produces_eight_jpegs']
def save(name,value):(out/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
env=os.environ.copy()
for key in list(env):
 if key.endswith('API_KEY') or key=='ANTHROPIC_AUTH_TOKEN' or key.startswith('CLAUDE_CODE_USE_'):env.pop(key,None)
env['IG_FORBIDDEN_LIVE']=r'C:\Users\hello\AppData\Local\Uoink\index.db'
env['PATH']=str(r/'_scratch/native-bin-gpl-01')+os.pathsep+env['PATH']
for name in ('ffmpeg.exe','ffprobe.exe'):
 receipt=json.loads((r/'_scratch/native-bin-gpl-01/receipt.json').read_text())
 row=next(x for x in receipt['files'] if Path(x['path']).name==name)
 with Path(row['path']).open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
native=r/'_scratch/ig-native/Scripts/python.exe'
base=[str(native),'-B',str(r/'_scratch/integrator_verify.py'),'--root',str(r)]
definitions=[('collection',['tests','--ignore=tests/library_work_astra/test_phase3_s21.py','--collect-only']),
 ('main',['tests','--ignore=tests/library_work_astra/test_phase3_s21.py',*['--deselect='+n for n in media]]),
 ('media',media)]
runs=[];start=time.monotonic()
save('plan.json',{'source':a.source,'scope':'Complete tree in two test processes, plus read-only collection. Only S21 absent; no existing test or guard edited.','media_partition':media,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
for name,selectors in definitions:
 label=a.label+'-'+name
 env['IG_PARTITION_RECEIPT_PATH']=str(out/name)
 command=base+['--label',label,*selectors,'-p','_scratch.partition_receipt_plugin']
 print('START',name,flush=True)
 with (out/(name+'.launcher.log')).open('w',encoding='utf8') as stream:
  result=subprocess.run(command,cwd=r,env=env,stdout=stream,stderr=subprocess.STDOUT)
 row={'name':name,'label':label,'command':command,'exit':result.returncode}
 runs.append(row);save('runs.json',runs)
 print('END',name,'exit',result.returncode,flush=True)
 assert git('rev-parse','HEAD')==a.source and not git('status','--porcelain'),'Source changed during observation'
 if name=='collection':
  assert result.returncode==0,'Collection failed; no test run follows'
  selected=json.loads((out/name/'membership.json').read_text())
  assert len(selected)==len(set(selected)) and set(media)<=set(selected)
  save('expected-membership.json',selected)
expected=set(json.loads((out/'expected-membership.json').read_text()))
seen=set();counts=collections.Counter();cases={}
for row in runs[1:]:
 name=row['name'];selected=json.loads((out/name/'membership.json').read_text())
 assert len(selected)==len(set(selected)) and not seen.intersection(selected),'Duplicate cases'
 seen.update(selected)
 reports=[json.loads(line) for line in (out/name/'reports.jsonl').read_text().splitlines()]
 grouped=collections.defaultdict(list)
 for report in reports:grouped[report['nodeid']].append(report)
 assert set(grouped)==set(selected),'Missing or unexpected execution report'
 for node,events in grouped.items():
  assert len({e['when'] for e in events})==len(events),'Repeated case phase'
  failures=[e for e in events if e['outcome']=='failed']
  skipped=[e for e in events if e['outcome']=='skipped']
  if failures:status='error' if any(e['when']!='call' for e in failures) else 'failed'
  elif skipped:status='xfailed' if any(e['wasxfail'] for e in skipped) else 'skipped'
  else:
   assert any(e['when']=='call' and e['outcome']=='passed' for e in events)
   status='passed'
  counts[status]+=1;cases[node]={'status':status,'partition':name}
 xmlcounts=collections.Counter()
 for case in ET.parse(r/'_scratch'/row['label']/'tests.xml').getroot().iter('testcase'):
  status='passed'
  for child in case:
   if child.tag in ('failure','error','skipped'):
    status={'failure':'failed','error':'error','skipped':'xfailed' if child.get('type')=='pytest.xfail' else 'skipped'}[child.tag];break
  xmlcounts[status]+=1
 assert xmlcounts==collections.Counter(v['status'] for v in cases.values() if v['partition']==name),'XML/report count mismatch'
assert seen==expected,{'missing':sorted(expected-seen),'extra':sorted(seen-expected)}
assert set(json.loads((out/'media/membership.json').read_text()))==set(media)
summary={'source':a.source,'result':'FAIL' if counts['failed'] or counts['error'] else 'PASS','counts':dict(counts),'cases':len(cases),'seconds_including_collection':time.monotonic()-start,'complete_disjoint_union':True,'only_absent_file':'tests/library_work_astra/test_phase3_s21.py','label':'Complete partitioned tree; not a monolithic pytest run','finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'failures':{k:v for k,v in cases.items() if v['status'] in ('failed','error')}}
save('cases.json',cases);save('summary.json',summary)
print(json.dumps(summary,indent=2),flush=True)
raise SystemExit(int(summary['result']=='FAIL'))
