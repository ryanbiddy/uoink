import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const dir='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary-custody-repair01';const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
for(const [name,expected]of[['durable_lifecycle.py','bc95b798512a588af9a46e591fb7d1d69d19f7c5d8218d7c7e13ad5f071fd20e'],['asr_loading_adapter.py','227395c4e1f25f75f13dc950e3b2e222af4a4d8b307a36091908229b58ed0c0f']]){
 const bytes=fs.readFileSync(path.join(dir,name));if(sha(bytes)!==expected)throw Error('reviewed pair changed');fs.writeFileSync(path.join(dir,'before/pre-review-entry02-'+name),bytes,{flag:'wx'});
}
const old=fs.readFileSync(path.join(dir,'durable_lifecycle.py'),'utf8');const eol=old.includes('\r\n')?'\r\n':'\n';let next=old;
const changes=[
 ['class DurableOwnedRuntimeFactory:\n','_FIXED_FACTORY_START_CHECK = _require_factory_start\n\n\nclass DurableOwnedRuntimeFactory:\n'],
 ['        capture = adapter._capture_controller_boundary\n        entry_check = adapter._check_controller_entry\n        boundary_check = adapter._check_controller_boundary\n        functions = adapter._CONTROLLER_BOUNDARY_FUNCTIONS\n        factory_check = _require_factory_start\n',
  '        functions = adapter._CONTROLLER_BOUNDARY_FUNCTIONS\n        factory_check = _FIXED_FACTORY_START_CHECK\n        if (type(functions) is not tuple or len(functions) != 19\n                or functions[0] is not adapter._capture_controller_boundary\n                or functions[1] is not adapter._check_controller_entry\n                or functions[2] is not adapter._check_controller_boundary\n                or functions[3] is not adapter._require_fixed_controller_functions\n                or _require_factory_start is not factory_check):\n            raise LifecycleUnavailable("Fixed startup helper selection changed")\n        functions[3](functions)\n        capture, entry_check, boundary_check = functions[:3]\n'],
];
for(const [a,b]of changes){const from=a.replace(/\n/g,eol),to=b.replace(/\n/g,eol);if(next.split(from).length!==2)throw Error('exact entry correction target missing');next=next.replace(from,to);}
const from='if _require_factory_start is not attempt.factory_check:';
if(next.split(from).length!==4)throw Error('three direct checks required');
next=next.replaceAll(from,'if (_require_factory_start is not attempt.factory_check'+eol+'                            or _FIXED_FACTORY_START_CHECK is not attempt.factory_check):');
fs.writeFileSync(path.join(dir,'durable_lifecycle.py'),next);
console.log(JSON.stringify({scope:'source-text correction only',before:sha(Buffer.from(old)),after:sha(Buffer.from(next)),bytes:Buffer.byteLength(next),adapter_unchanged:true,candidate_executed:false},null,2));

