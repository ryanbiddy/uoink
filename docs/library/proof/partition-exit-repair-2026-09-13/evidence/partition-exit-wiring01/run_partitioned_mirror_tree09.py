"""Execute every original case once in two guarded processes; preserve real failures."""
import argparse,collections,datetime as dt,hashlib,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
from xml.etree import ElementTree as ET
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--label',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('partition_exit_contract',r/'_scratch/partition_exit_contract.py')
contract=importlib.util.module_from_spec(spec);sys.modules[spec.name]=contract;spec.loader.exec_module(contract)
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
save('plan.json',{'source':a.source,'scope':'Complete tree in two test processes, plus read-only collection. Only S21 absent; --runxfail executes the repaired SEC-06 assertions normally. No existing test or guard edited.','media_partition':media,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
for name,selectors in definitions:
 label=a.label+'-'+name
 env['IG_PARTITION_RECEIPT_PATH']=str(out/name)
 command=base+['--label',label,*selectors,'--runxfail','-p','_scratch.partition_receipt_plugin']
 if name=='main':
  env['IG_MIRROR_STATE_RECEIPT_PATH']=str(out/'mirror-state.jsonl')
  command+=['-p','_scratch.mirror_state_receipt_plugin']
 else:
  env.pop('IG_MIRROR_STATE_RECEIPT_PATH',None)
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
  verifier=json.loads((r/'_scratch'/label/'results.json').read_text())
  session=json.loads((out/name/'session.json').read_text())
  assert len(verifier)==1 and verifier[0]['name']=='tests' and verifier[0]['exit']==0
  assert session=={'exit':0,'tests_collected':len(selected),'tests_failed':0,'reports':0}
  save('expected-membership.json',selected)
expected=set(json.loads((out/'expected-membership.json').read_text()))
seen=set();counts=collections.Counter();cases={};partition_validation={}
for row in runs[1:]:
 name=row['name'];selected=json.loads((out/name/'membership.json').read_text())
 assert len(selected)==len(set(selected)) and not seen.intersection(selected),'Duplicate cases'
 seen.update(selected)
 reports=[json.loads(line) for line in (out/name/'reports.jsonl').read_text().splitlines()]
 verified=contract.validate_partition(
  selected=selected,reports=reports,
  session=json.loads((out/name/'session.json').read_text()),
  verifier_results=json.loads((r/'_scratch'/row['label']/'results.json').read_text()),
  outer_exit=row['exit'],junit_xml=(r/'_scratch'/row['label']/'tests.xml').read_bytes())
 partition_validation[name]=verified
 save(name+'-validation.json',verified)
 counts.update(verified['counts'])
 for node,case in verified['cases'].items():cases[node]={**case,'partition':name}
assert seen==expected,{'missing':sorted(expected-seen),'extra':sorted(seen-expected)}
assert set(json.loads((out/'media/membership.json').read_text()))==set(media)
summary={'source':a.source,'result':'FAIL' if counts['failed'] or counts['error'] else 'PASS','counts':dict(counts),'cases':len(cases),'seconds_including_collection':time.monotonic()-start,'complete_disjoint_union':True,'only_absent_file':'tests/library_work_astra/test_phase3_s21.py','label':'Complete partitioned tree with --runxfail; not a monolithic pytest run','expected_failure_policy':'Original marks unchanged; --runxfail executes all assertion bodies normally','finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'failures':{k:v for k,v in cases.items() if v['status'] in ('failed','error')}}
summary['partition_exit_contract']='Every tested partition reconciles session, pytest, verifier, reports and JUnit; abnormal or incomplete execution cannot produce this complete aggregate.'
summary['failed_phases']={name:verified['failed_phases'] for name,verified in partition_validation.items()}
save('cases.json',cases);save('summary.json',summary)
print(json.dumps(summary,indent=2),flush=True)
raise SystemExit(int(summary['result']=='FAIL'))
