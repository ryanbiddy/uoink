import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const out=path.join(root,'_scratch/controller-boundary-custody-repair01');
const frozen=path.join(root,'docs/library/proof/controller-boundary-source-failure-2026-09-14/delivery/frozen');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const specs=[
 ['before/accepted-durable_lifecycle.py','before/durable_lifecycle.py','3c8963eaa02bbc1d810ee2632d0363303bfe05ec6ceeef73771ca8005a00ece3'],
 ['before/accepted-asr_loading_adapter.py','before/asr_loading_adapter.py','2f12cbf5a5f1142f892aa34df7d23af77107148b448fb4294329532e36be63ee'],
 ['before/rejected-durable_lifecycle.py','durable_lifecycle.py','4eeeade5384ca8172c3724a3ee2a6574ca6801e3af3408f177e586c9cd9a4dc3'],
 ['before/rejected-asr_loading_adapter.py','asr_loading_adapter.py','94e522e622b8de3304ef48c97258a91692e70f22c3112dd6afabd6b493438611'],
 ['before/rejected-durable_lifecycle.diff','durable_lifecycle.diff','bf1e477feb591e448f54266a7699d9d3d033fed665e7d7465d62f9c4a05713a9'],
 ['before/rejected-asr_loading_adapter.diff','asr_loading_adapter.diff','360be788a6673b4f50cb21c490b0f4e62d8a7b262fa8b5486eda8250b2ef6e91'],
];
const inputs=specs.map(([copy,src,sha256])=>{const bytes=fs.readFileSync(path.join(frozen,src));if(hash(bytes)!==sha256)throw Error('source mismatch '+src);return{copy,src,bytes,sha256};});
fs.mkdirSync(path.join(out,'before'),{recursive:false});
for(const row of inputs)fs.writeFileSync(path.join(out,row.copy),row.bytes,{flag:'wx'});
let durable=fs.readFileSync(path.join(out,'durable_boundary.fragment.txt'),'utf8');
const changes=[
 ['    boundary_check: object\n','    boundary_check: object\n    functions: tuple\n'],
 ['            or attempt.factory.manager is not manager or manager._delegate is not attempt.delegate\n','            or attempt.factory.manager is not manager\n            or attempt.factory._start_attempts.get(attempt.permit_identity) is not attempt\n            or manager._delegate is not attempt.delegate\n'],
 ['            or attempt.adapter._check_controller_boundary is not attempt.boundary_check):\n','            or attempt.adapter._check_controller_boundary is not attempt.boundary_check\n            or attempt.adapter._CONTROLLER_BOUNDARY_FUNCTIONS is not attempt.functions):\n'],
 ['        self.manager = lifecycle\n','        self.manager = lifecycle\n        self._start_attempts = {}\n'],
 ['        boundary_check = adapter._check_controller_boundary\n','        boundary_check = adapter._check_controller_boundary\n        functions = adapter._CONTROLLER_BOUNDARY_FUNCTIONS\n'],
 ['                            or permit.identity in kernel._factory_starts):\n','                            or permit.identity in kernel._factory_starts\n                            or permit.identity in self._start_attempts):\n'],
 ['                    controller = capture(profile, permit)\n','                    controller = capture(profile, permit)\n                    if controller is not None and (controller.factory is not self\n                            or controller.manager is not manager or controller.record is not record\n                            or controller.token is not token):\n                        raise LifecycleUnavailable("Controller custody belongs to another factory")\n'],
 ['                        token, controller, adapter, capture, entry_check, boundary_check)\n','                        token, controller, adapter, capture, entry_check, boundary_check, functions)\n                    self._start_attempts[permit.identity] = attempt\n'],
];
for(const [a,b]of changes){if(durable.split(a).length!==2)throw Error('exact initial fragment replacement required');durable=durable.replace(a,b);}
const accepted=inputs[0].bytes.toString('utf8');
const start=accepted.indexOf('class DurableOwnedRuntimeFactory:');
const end=accepted.indexOf('    def quarantine(self, key, protection, permit, reason):',start);
if(start<0||end<0)throw Error('bounded original region absent');
const eol=accepted.includes('\r\n')?'\r\n':'\n';
const durableBytes=Buffer.from(accepted.slice(0,start)+durable.replace(/\r?\n/g,eol)+accepted.slice(end));
const rejectedAdapter=inputs[3].bytes.toString('utf8').replace(/\r\n/g,'\n');
const preStart=rejectedAdapter.indexOf('def _validate_controller_pre_resume_locked(');
const preEnd=rejectedAdapter.indexOf('def _classify_controller_attempt(',preStart);
if(preStart<0||preEnd<0)throw Error('retained reviewed pre-resume predicate absent');
const appendix='\n'+rejectedAdapter.slice(preStart,preEnd)+fs.readFileSync(path.join(out,'adapter_binding.fragment.txt'),'utf8');
const adapterBytes=Buffer.concat([inputs[1].bytes,Buffer.from(appendix)]);
for(const [name,bytes]of[['durable_lifecycle.py',durableBytes],['asr_loading_adapter.py',adapterBytes]])fs.writeFileSync(path.join(out,name),bytes,{flag:'wx'});
const result={scope:'data-only source composition; no subject parse/import/compile',inputs:inputs.map(x=>({copy:x.copy,source:path.join(frozen,x.src),bytes:x.bytes.length,sha256:x.sha256})),outputs:[['durable_lifecycle.py',durableBytes],['asr_loading_adapter.py',adapterBytes]].map(([name,b])=>({name,bytes:b.length,sha256:hash(b)})),adapter_prefix_byte_identical:adapterBytes.subarray(0,inputs[1].bytes.length).equals(inputs[1].bytes),candidate_executed:false};
fs.writeFileSync(path.join(out,'INITIAL-SOURCE-PINS.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(result,null,2));

