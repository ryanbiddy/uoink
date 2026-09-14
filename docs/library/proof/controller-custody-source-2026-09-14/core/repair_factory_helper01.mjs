import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const dir='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary-custody-repair01';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
for(const [name,expected]of[['durable_lifecycle.py','410e958c8dce2762a3f7d7e5cfefe91ebd8dde7172da8cc3fde327535d64aa41'],['asr_loading_adapter.py','227395c4e1f25f75f13dc950e3b2e222af4a4d8b307a36091908229b58ed0c0f']]){
 const b=fs.readFileSync(path.join(dir,name));if(sha(b)!==expected)throw Error('initial pair changed');
 fs.writeFileSync(path.join(dir,'before/pre-review-helper01-'+name),b,{flag:'wx'});
}
const source=fs.readFileSync(path.join(dir,'durable_lifecycle.py'),'utf8');const eol=source.includes('\r\n')?'\r\n':'\n';
let next=source;
const changes=[
 ['    functions: tuple\n','    functions: tuple\n    factory_check: object\n'],
 ['        functions = adapter._CONTROLLER_BOUNDARY_FUNCTIONS\n','        functions = adapter._CONTROLLER_BOUNDARY_FUNCTIONS\n        factory_check = _require_factory_start\n'],
 ['                        token, controller, adapter, capture, entry_check, boundary_check, functions)\n','                        token, controller, adapter, capture, entry_check, boundary_check, functions, factory_check)\n'],
 ['                    _require_factory_start(kernel, attempt, True, worker)\n','                    if _require_factory_start is not attempt.factory_check:\n                        raise LifecycleUnavailable("Fixed factory start function changed")\n                    attempt.factory_check(kernel, attempt, True, worker)\n'],
 ['                _require_factory_start(self, attempt, False)\n','                if _require_factory_start is not attempt.factory_check:\n                    raise LifecycleUnavailable("Fixed factory start function changed")\n                attempt.factory_check(self, attempt, False)\n'],
 ['                    _require_factory_start(self, attempt, True, worker)\n','                    if _require_factory_start is not attempt.factory_check:\n                        raise LifecycleUnavailable("Fixed factory start function changed")\n                    attempt.factory_check(self, attempt, True, worker)\n'],
];
for(const [from,to]of changes){const a=from.replace(/\n/g,eol),b=to.replace(/\n/g,eol);if(next.split(a).length!==2)throw Error('exact correction target absent');next=next.replace(a,b);}
fs.writeFileSync(path.join(dir,'durable_lifecycle.py'),next);
console.log(JSON.stringify({scope:'source-text correction only',before:sha(Buffer.from(source)),after:sha(Buffer.from(next)),bytes:Buffer.byteLength(next),changes:changes.length,adapter_unchanged:sha(fs.readFileSync(path.join(dir,'asr_loading_adapter.py')))==='227395c4e1f25f75f13dc950e3b2e222af4a4d8b307a36091908229b58ed0c0f',candidate_executed:false},null,2));

