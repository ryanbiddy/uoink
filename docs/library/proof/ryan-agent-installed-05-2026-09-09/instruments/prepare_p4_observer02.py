from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parents[1]
src=r/'_scratch/agent_receipt_observe.py';out=r/'_scratch/agent_receipt_observe_p4_02.py'
s=src.read_text(encoding='utf8')
changes={
"record_path=root/(a.stage+'-observation.json')":"record_path=root/(a.stage+'-02-observation.json')",
"p4=root/'p4';p4.mkdir(exist_ok=True)":"p4=root/'p4-02';p4.mkdir(exist_ok=True)",
"root/(a.stage+'.stdout')":"root/(a.stage+'-02.stdout')",
"root/(a.stage+'.stderr')":"root/(a.stage+'-02.stderr')",
}
for old,new in changes.items():
 assert s.count(old)==1,old
 s=s.replace(old,new)
with out.open('x',encoding='utf8',newline='\n') as f:f.write(s)
(r/'_scratch/p4-observer02-receipt.json').write_text(json.dumps({'reason':'Fresh directory and output names after the documented failed embedded probe attempt. Same package and guard boundary; no behavior change.','brief':'P4-EMBEDDED-PROBE-REPAIR-BRIEF-2026-09-09.md','source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'changes':changes},indent=2)+'\n',encoding='utf8')
