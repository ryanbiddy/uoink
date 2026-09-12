"""Read UTF-8 explicitly; syntax only, with the failed reader attempt preserved."""
import ast,datetime as dt,hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1];p=r/'_scratch/update_release08_documents.py'
prior=json.loads((r/'_scratch/delivery08-preflight01.json').read_text(encoding='utf8'))
assert prior['exit']==1
ast.parse(p.read_text(encoding='utf8'))
report={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'exit':0,'scope':'UTF-8 reader and AST syntax only; script not executed, no document or product change','prior_failure':'delivery08-preflight01.json','repair_brief':'DELIVERY08-PREFLIGHT-REPAIR.md'}
with (r/'_scratch/delivery08-preflight02.json').open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
print(json.dumps(report))
