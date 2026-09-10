"""Seal one completed, committed observation without changing its outcome."""
import argparse,collections,hashlib,importlib.metadata,json,re,shutil,subprocess,sys
from pathlib import Path
from xml.etree import ElementTree as ET
p=argparse.ArgumentParser()
p.add_argument('--source',required=True)
p.add_argument('--label',required=True)
p.add_argument('--proof',required=True)
p.add_argument('--baseline-source',required=True)
p.add_argument('--baseline-proof',required=True)
p.add_argument('--scope',required=True)
a=p.parse_args()
r=Path(__file__).resolve().parents[1]
run=r/'_scratch'/a.label
out=r/'docs/library/proof'/a.proof
assert out.parent==r/'docs/library/proof' and run.parent==r/'_scratch'
def git(*args):return subprocess.check_output(['git',*args],cwd=r,text=True,encoding='utf8').strip()
assert git('rev-parse','HEAD')==a.source
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
# Only reviewed and explicitly authorized corrections may differ from the prior full tree.
allowed = {
 'tests/library_work_astra/test_phase4_aw_acceptance.py',
 'tests/library_work_astra/test_phase4_aw2_acceptance.py',
 'tests/library_work_astra/test_phase4_aw3_acceptance.py',
 'tests/test_existing_index_read_open.py',
 'tests/test_installer_dependency_lock.py',
 'tests/test_install_receipt_c22_kit.py',
 'tests/test_install_receipt_p4_kit.py',
}
changed=set(git('diff','--name-only','--diff-filter=M',a.baseline_source,a.source,'--','tests').splitlines())
assert changed==allowed, {'unexpected':sorted(changed-allowed),'missing_expected':sorted(allowed-changed)}
reviews={name:git('rev-parse',a.source+':docs/library/'+name) for name in (
 'RYAN-APPROVED-FIXTURE-INTEGRATION-REVIEW-2026-09-09.md',
 'ASTRA-DEPENDENCY-SECURITY-VERDICT-2026-09-09.md',
 'ASTRA-RECEIPT-CORRECTION-VERDICT-2026-09-09.md')}

def cases(path):
    result={}
    for case in ET.parse(path).getroot().iter('testcase'):
        key=case.get('classname')+'::'+case.get('name')
        assert key not in result,key
        status,detail='passed',None
        for c in case:
            if c.tag in ('failure','error','skipped'):
                status={'failure':'failed','error':'error','skipped':'skipped'}[c.tag]
                if c.tag=='skipped' and c.get('type')=='pytest.xfail':status='xfailed'
                detail={'message':c.get('message'),'text':c.text};break
        result[key]={'status':status,'seconds':float(case.get('time','0')),'detail':detail}
    return result
current=cases(run/'tests.xml')
previous=cases(r/'docs/library/proof'/a.baseline_proof/'tests.xml')
counts=dict(collections.Counter(c['status'] for c in current.values()))
failures={k:v for k,v in current.items() if v['status'] in ('failed','error')}
results=json.loads((run/'results.json').read_text(encoding='utf8'))
summaryline=(run/'tests.log').read_text(encoding='utf8').splitlines()[-1]
elapsed=re.search(r'in ([\d.]+)s',summaryline)
assert elapsed,summaryline
assert results[0]['exit']==(1 if failures else 0),results
out.mkdir(exist_ok=False)
def save(name,data):(out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf8',newline='\n')
for name in ('tests.log','tests.xml','results.json'):shutil.copyfile(run/name,out/name)
for name in ('sitecustomize.py','ig_paths.py'):shutil.copyfile(run/'guard'/name,out/name)
shutil.copyfile(r/'_scratch/integrator_verify.py',out/'integrator_verify.py')
shutil.copyfile(Path(__file__),out/Path(__file__).name)
comparison={'baseline':a.baseline_source,'candidate':a.source,
 'previous_failed_now_passed':[k for k,v in previous.items() if v['status']=='failed' and current.get(k,{}).get('status')=='passed'],
 'current_failed_previously_not_failed':[k for k in failures if previous.get(k,{}).get('status')!='failed'],
 'missing_current_cases':sorted(set(previous)-set(current)),
 'new_current_cases':sorted(set(current)-set(previous)),
 'note':'Separate observations. Prior failures remain failed. Seven existing files changed only through the three named reviewed corrections; added regression cases are listed separately.'}
save('cases.json',current);save('failures.json',failures);save('comparison.json',comparison)
save('environment.json',{'python':sys.version,'executable':sys.executable,'versions':{n:importlib.metadata.version(n) for n in ('pytest','mcp','anyio','pydantic')},'native_runtime_receipt':'../ryan-verification-runtime-2026-09-09/SHA256.json','guard':'Python audit; no OS-wide audit claim'})
summary={'candidate':a.source,'result':'FAIL' if failures else 'PASS','counts':counts,'seconds':float(elapsed.group(1)),'pytest_summary':summaryline,'excluded':['tests/library_work_astra/test_phase3_s21.py'],'scope':a.scope,'approved_corrections':{'changed_existing_tests':sorted(changed),'review_git_blobs':reviews},'source_paths_changed_since_baseline':git('diff','--name-only',a.baseline_source,a.source).splitlines()}
save('summary.json',summary)
subprocess.run(['git','diff',a.baseline_source,a.source,'--binary','--full-index','--output='+str(out/'authorized-test-changes.patch'),'--',*sorted(changed)],cwd=r,check=True)
save('test-source-bindings.json',{name:{'baseline_blob':git('rev-parse',a.baseline_source+':'+name),'candidate_blob':git('rev-parse',a.source+':'+name)} for name in sorted(changed)})
save('SHA256.json',{'algorithm':'sha256','files':{q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(out.rglob('*')) if q.is_file()}})
print(json.dumps({'summary':summaryline,'counts':counts,'failures':list(failures),'comparison':comparison},indent=2))
