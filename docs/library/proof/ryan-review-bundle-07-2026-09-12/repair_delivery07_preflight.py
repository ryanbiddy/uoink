from pathlib import Path
import ast,difflib,json
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
old=(s/'stage_installed07.py').read_text()
new=old.replace("['git','check-ignore','--stdin']","['git','check-ignore','-z','--stdin']",1)
new=new.replace("input='\\n'.join(paths)+'\\n'","input='\\0'.join(paths)+'\\0'",1)
new=new.replace('ignored_paths=ignored.stdout.splitlines()',"ignored_paths=[p for p in ignored.stdout.split('\\0') if p]",1)
assert old!=new;ast.parse(new)
with (s/'stage_installed07_02.py').open('x',encoding='utf8',newline='\n') as f:f.write(new)
with (s/'stage_installed07_02.py.diff').open('x',encoding='utf8',newline='\n') as f:f.write(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))))
old=(s/'seal_review_bundle06.py').read_text();new=old
mapping={'Review-Kit-06-2026-09-11':'Review-Kit-07-2026-09-12','ryan-review-bundle-06-2026-09-11':'ryan-review-bundle-07-2026-09-12',
 'build_release_bundle06.py':'build_release_bundle07.py','seal_review_bundle06.py':'seal_review_bundle07.py','review_bundle06.py':'review_bundle07.py',
 'review-bundle06-build.log':'review-bundle07-build.log','review-bundle06-inspection.json':'review-bundle07-inspection.json',
 'package06-git-proof-check02.json':'package07-git-proof-check01.json','verify_committed_package06_proofs.py':'verify_committed_package07_proofs.py',
 'runbook06-syntax.json':'runbook07-syntax.json','check_runbook06.ps1':'check_runbook07.ps1'}
for before in sorted(mapping,key=len,reverse=True):
    assert before in new,before
    new=new.replace(before,mapping[before])
new=new.replace("'runbook07-syntax.json', 'check_runbook07.ps1'):","'runbook07-syntax.json', 'check_runbook07.ps1',\n             'prepare_delivery07.py', 'repair_delivery07_preflight.py', 'delivery07-preflight-failures.json',\n             'stage_installed07.py', 'stage_installed07_02.py', 'stage_installed07_02.py.diff',\n             'installed07-staged-proof-check.json'):",1)
ast.parse(new)
with (s/'seal_review_bundle07.py').open('x',encoding='utf8',newline='\n') as f:f.write(new)
with (s/'seal_review_bundle07.py.diff').open('x',encoding='utf8',newline='\n') as f:f.write(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))))
with (s/'delivery07-preflight-failures.json').open('x',encoding='utf8',newline='\n') as f:
    f.write(json.dumps({'source':'Tool-returned diagnostics, retained as structured transcriptions',
      'failures':[{'instrument':'prepare_delivery07.py','exit':1,'error':"AssertionError: ('seal_review_bundle06.py', 'seal_review_bundle06.py')",'effect':'Four completed instrument adaptations preserved; missing final sealer never written'},
                  {'instrument':'stage_installed07.py','exit':1,'error':'line 18: assert all(p in paths for p in ignored_paths); AssertionError','effect':'Reviewed files staged; stopped before exact ignored-file additions or blob checks'}],
      'product_reruns':0,'zip_build_attempts':0},indent=2)+'\n')
print('Prepared only missing sealer and corrected NUL-safe staging reader.')
