from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 05')
failure=json.loads((root/'p4-collect-02-observation.json').read_text())
assert failure['exit']==2 and failure['guard_absent_after']
profile=root/'p4-02/profile'
assert not any((profile/('operator-collect'+suffix)).exists() for suffix in ('.json','.stdout','.stderr'))
with (profile/'operator.json').open('x',encoding='utf8') as f:f.write('{}\n')
src=r/'_scratch/agent_receipt_observe_p4_02.py';out=r/'_scratch/agent_receipt_observe_p4_collect03.py'
s=src.read_text(encoding='utf8')
for old,new in [("a.stage+'-02-observation.json'","a.stage+'-03-observation.json'"),("a.stage+'-02.stdout'","a.stage+'-03.stdout'"),("a.stage+'-02.stderr'","a.stage+'-03.stderr'")]:
 assert s.count(old)==1;s=s.replace(old,new)
with out.open('x',encoding='utf8',newline='\n') as f:f.write(s)
(r/'_scratch/p4-collection-input-repair.json').write_text(json.dumps({'brief':'P4-COLLECTION-INPUT-REPAIR-2026-09-10.md','operator_json':'explicit empty object; missing observations stay unobserved','original_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'corrected_wrapper_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'change':'outer evidence suffix only; same p4-02 profile and unmodified original collector'},indent=2)+'\n',encoding='utf8')
