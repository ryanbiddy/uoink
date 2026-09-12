"""Include actual later instrument corrections before the evidence seals run."""
from pathlib import Path
import ast,datetime as dt,difflib,hashlib,json
s=Path(__file__).resolve().parent
changes=[]
updates={
 'seal_installed08.py':("for name in instruments:add(scratch/name,'instruments/'+name)","""instruments += ['run_browser08_02.py','complete_browser08_02.py','run_browser08_02.py.diff','complete_browser08_02.py.diff',
    'BROWSER08-PREFLIGHT-REPAIR.md','repair_browser08_preflight.py','browser08-preflight-repair.json',
    'extend_delivery08_instruments.py','delivery08-instrument-extension.json','seal_installed08.py.extension.diff']
for name in instruments:add(scratch/name,'instruments/'+name)"""),
 'seal_review_bundle08.py':("             'seal_review_bundle08.py.diff'):","""             'seal_review_bundle08.py.diff', 'seal_review_bundle08.py.extension.diff',
             'extend_delivery08_instruments.py','delivery08-instrument-extension.json',
             'DELIVERY08-PREFLIGHT-REPAIR.md','delivery08-preflight01.json',
             'delivery08_preflight02.py','delivery08-preflight02.json',
             'update_release08_documents.py','stage_installed08_proofs.py'):
""".rstrip())
}
for name,(needle,replacement) in updates.items():
    p=s/name;old=p.read_text(encoding='utf8');assert old.count(needle)==1
    new=old.replace(needle,replacement,1);ast.parse(new)
    before=s/(name+'.before-extension');before.write_bytes(p.read_bytes())
    diff=s/(name+'.extension.diff');diff.write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=before.name,tofile=name)),encoding='utf8')
    p.write_text(new,encoding='utf8',newline='\n')
    changes.append({'file':name,'before':hashlib.sha256(before.read_bytes()).hexdigest(),'after':hashlib.sha256(p.read_bytes()).hexdigest(),'diff_sha256':hashlib.sha256(diff.read_bytes()).hexdigest()})
with (s/'delivery08-instrument-extension.json').open('x',encoding='utf8') as f:
    json.dump({'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'reason':'Archive later diagnosed browser/preflight corrections and exact readers. No product scenario, test or result changes. Sealers have not yet executed.','changes':changes},f,indent=2);f.write('\n')
print(json.dumps(changes))
