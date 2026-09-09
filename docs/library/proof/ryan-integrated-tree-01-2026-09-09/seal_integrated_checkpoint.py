"""Seal the committed integrated product checkpoint; preserve case identities."""
import collections,hashlib,importlib.metadata,json,re,shutil,subprocess,sys
from pathlib import Path
from xml.etree import ElementTree as ET
root=Path(__file__).resolve().parents[1]
sha='263b7e422a4cb5b0c3357a86e4ac957eec28a4cf'
run=root/'_scratch/integrated-tree-01'
out=root/'docs/library/proof/ryan-integrated-tree-01-2026-09-09'
def git(*args):
    return subprocess.check_output(['git',*args],cwd=root,text=True,encoding='utf-8').strip()
def cases(path):
    result={}
    for case in ET.parse(path).getroot().iter('testcase'):
        key=case.get('classname')+'::'+case.get('name')
        assert key not in result,key
        status,detail='passed',None
        for child in case:
            if child.tag in ('failure','error','skipped'):
                status={'failure':'failed','error':'error','skipped':'skipped'}[child.tag]
                if child.tag=='skipped' and child.get('type')=='pytest.xfail':status='xfailed'
                detail={'message':child.get('message'),'text':child.text}
                break
        result[key]={'status':status,'seconds':float(case.get('time','0')),'detail':detail}
    return result
assert git('rev-parse','HEAD')==sha
assert not git('diff','--name-only')
assert not git('diff','--cached','--name-only')
assert not git('diff','--name-only','--diff-filter=M','4a3531642692736d4aaa4098077ab8fde464aeb4',sha,'--','tests'), 'Existing corrected tests changed'
results=json.loads((run/'results.json').read_text(encoding='utf-8'))
current=cases(run/'tests.xml')
previous=cases(root/'docs/library/proof/ryan-corrected-01-2026-09-09/tests.xml')
counts=dict(collections.Counter(c['status'] for c in current.values()))
failures={k:v for k,v in current.items() if v['status'] in ('failed','error')}
summaryline=(run/'tests.log').read_text(encoding='utf-8').splitlines()[-1]
elapsed=re.search(r'in ([\d.]+)s',summaryline)
assert elapsed,summaryline
assert results[0]['exit']==(1 if failures else 0),results
out.mkdir(parents=True,exist_ok=False)
for name in ('tests.log','tests.xml','results.json'):
    shutil.copyfile(run/name,out/name)
for name in ('sitecustomize.py','ig_paths.py'):
    shutil.copyfile(run/'guard'/name,out/name)
shutil.copyfile(root/'_scratch/integrator_verify.py',out/'integrator_verify.py')
shutil.copyfile(Path(__file__),out/Path(__file__).name)
def save(name,value):
    (out/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
comparison={
    'baseline':'4a3531642692736d4aaa4098077ab8fde464aeb4','candidate':sha,
    'previous_failed_now_passed':[k for k,v in previous.items() if v['status']=='failed' and current.get(k,{}).get('status')=='passed'],
    'current_failed_previously_not_failed':[k for k in failures if previous.get(k,{}).get('status')!='failed'],
    'missing_current_cases':sorted(set(previous)-set(current)),
    'new_current_cases':sorted(set(current)-set(previous)),
    'note':'Separate observations; prior failures remain failed. No existing test edits since the five authorized corrections.'}
save('cases.json',current)
save('failures.json',failures)
save('comparison.json',comparison)
save('environment.json',{'python':sys.version,'executable':sys.executable,'versions':{n:importlib.metadata.version(n) for n in ('pytest','mcp','anyio','pydantic')},'native_runtime_receipt':'../ryan-verification-runtime-2026-09-09/SHA256.json','guard':'Python audit, no independent OS-wide access audit claimed'})
summary={'candidate':sha,'result':'FAIL' if failures else 'PASS','counts':counts,'seconds':float(elapsed.group(1)),'pytest_summary':summaryline,'excluded':['tests/library_work_astra/test_phase3_s21.py'],'scope':'Committed integrated product checkpoint; pending installation workers absent. Final source/package/installed verification remains separate.','existing_fixture_proposal':'pending, not applied','source_paths_changed_since_corrected_tree':git('diff','--name-only','4a3531642692736d4aaa4098077ab8fde464aeb4',sha).splitlines()}
save('summary.json',summary)
save('SHA256.json',{'algorithm':'sha256','files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256.json'}})
print(json.dumps({'summary':summaryline,'counts':counts,'failures':list(failures),'comparison':comparison},indent=2))
