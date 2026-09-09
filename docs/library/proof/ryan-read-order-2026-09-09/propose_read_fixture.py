import ast,difflib,hashlib,json,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[1]
name='tests/test_existing_index_read_open.py'
old=(r/name).read_text(encoding='utf8')
new=old.replace('from index import Index\n','from index import Index\nfrom server import _get_index as _production_get_index\n',1)
needle='    monkeypatch.setattr(server, "INDEX_PATH", path)\n'
assert needle in new
new=new.replace(needle,'    monkeypatch.setattr(server, "_get_index", _production_get_index)\n'+needle,1)
def assertions(text):return [ast.dump(x,include_attributes=False) for x in ast.walk(ast.parse(text)) if isinstance(x,ast.Assert)]
assert assertions(old)==assertions(new)
patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
out=r/'docs/library/patches/ryan-proposed-read-fixture-2026-09-09.patch'
assert not out.exists()
out.write_text(patch,encoding='utf8',newline='\n')
proof=r/'docs/library/proof/ryan-read-order-2026-09-09';proof.mkdir(exist_ok=False)
for name in ('tests.log','tests.xml','results.json'):shutil.copyfile(r/'_scratch/pre-o1'/name,proof/name)
audit={'applied':False,'patch':out.relative_to(r).as_posix(),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'unchanged_assertions':len(assertions(old)),'reproduction':'3 passed, 1 failed, 1 warning, 1.25 s; unchanged discovery-route file then read-opening file','cause':'tests/test_discovery_route.py directly leaves server._get_index as a lambda returning its own fixture Index; production getter is not called','proposed_change':'Capture production getter during collection; monkeypatch that original callable only for the new test. No behavior assertion changes.'}
(proof/'proposal.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf8',newline='\n')
shutil.copyfile(Path(__file__),proof/Path(__file__).name)
files={p.relative_to(proof).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in proof.iterdir() if p.is_file()}
(proof/'SHA256.json').write_text(json.dumps({'files':files},indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(audit,indent=2))
