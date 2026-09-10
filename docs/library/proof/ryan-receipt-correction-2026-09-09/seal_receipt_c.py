"""Retain every receipt correction observation, including failures and interruption."""
import ast, hashlib, json, shutil, subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\269acc98-ac8\gemini')
out=r/'docs/library/proof/ryan-receipt-correction-2026-09-09'
assert not out.exists()
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf8',newline='\n')
def assertions(source,name):
 tree=ast.parse(source)
 fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
 return [ast.dump(n,include_attributes=False) for n in ast.walk(fn) if isinstance(n,ast.Assert)]
relative='tests/test_install_receipt_c22_kit.py'
before=subprocess.check_output(['git','show','c7a8426:'+relative],cwd=r).decode('utf8')
after=(r/relative).read_text(encoding='utf8')
old=assertions(before,'test_synthetic_helper_scenarios_and_verdict')
new=assertions(after,'test_synthetic_helper_scenarios_and_verdict')
assert old==new and len(old)==17
out.mkdir()
for base,label in [(w,'receipt-c-w1'),(w,'receipt-c-w2'),(w,'receipt-c-w3'),(w,'receipt-contract-w1'),(r,'receipt-c-c2')]:
 dest=out/label;dest.mkdir()
 for name in ('tests.log','tests.xml','results.json'):
  q=base/'_scratch'/label/name
  if q.exists():shutil.copyfile(q,dest/name)
  else:assert label=='receipt-c-w2' and name=='tests.xml'
 for name in ('sitecustomize.py','ig_paths.py'):shutil.copyfile(base/'_scratch'/label/'guard'/name,dest/name)
for name in ('receipt-c-partial.patch','receipt-c-instrument-failed.patch','receipt-c-final.patch','credential-integrated.patch','finish_receipt_stub.py','integrator_verify.py','seal_receipt_c.py'):
 shutil.copyfile(r/'_scratch'/name,out/name)
abort=r/'_scratch/receipt-c-w2/integrator-abort.json'
if not abort.exists():abort=w/'_scratch/receipt-c-w2/integrator-abort.json'
shutil.copyfile(abort,out/'receipt-c-w2/integrator-abort.json')
failed=w/'_scratch/c22-kit/t-zre_ulgc/receipt'
for name in ('fixture_prepare.json','guards.json','inputs.json','journal.jsonl','manifest.used.json','runner.json'):
 dest=out/'failed-stub-scenarios'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(failed/name,dest)
for folder in ('evidence','commands'):
 for q in (failed/folder).glob('*'):
  if q.is_file() and q.suffix in ('.json','.log'):
   dest=out/'failed-stub-scenarios'/folder/q.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(q,dest)
save(out/'assertion-audit.json',{'baseline':'c7a8426','test':relative+'::test_synthetic_helper_scenarios_and_verdict','before':old,'after':new,'unchanged':True,'count':len(old),'scope':'Scenario assertions unchanged; plan unit expectations explicitly corrected to supported flags; apply-false unchanged.'})
save(out/'observation-disposition.json',{'worker_original':'Partial; no completed report, not accepted','receipt-c-w1':'171 passed, 1 failed; stand-alone stub lacks original child/provenance behavior','receipt-c-w2':'Aborted before final XML/count; stale worker credential baseline; exact process-stop record retained','receipt-c-w3':'172 passed in 818.26 seconds; integrated credential baseline applied first','receipt-c-c2':'See original tests.xml/results.json for independent checkout result','installed_credit':False,'credential_limit':'Earlier source fixtures did not prove ordinary-keyring non-access. No real credential was queried to investigate.'})
save(out/'SHA256.json',{'algorithm':'sha256','files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}})
print('Sealed',len(json.loads((out/'SHA256.json').read_text())['files']),'payloads; 17 assertions unchanged')
