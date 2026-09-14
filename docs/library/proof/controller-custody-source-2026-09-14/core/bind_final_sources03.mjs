import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',dir=path.join(root,'_scratch/controller-boundary-custody-repair01');const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const selected=[
 ['docs/library/CONTROLLER-BOUNDARY-CUSTODY-REPAIR-BRIEF-2026-09-14.md',null],
 ['docs/library/CONTROLLER-RESUME-PUBLICATION-IMPLEMENTATION-BRIEF-2026-09-14.md','691bc362c8aa2fd1b3e9623a2638dc68617d585a129a8dfee00e41dd0a822d36'],
 ['docs/library/ASTRA-CONTROLLER-BOUNDARY01-SOURCE-FAILURE-2026-09-14.md',null],
 ['docs/library/proof/controller-boundary-source-failure-2026-09-14/delivery/FROZEN-SOURCE-PINS.json','1679fc8f78e08f6585232f9400cc12e3d2b2c15bcadb0d22bda31d50d149a438'],
 ['docs/library/proof/controller-boundary-source-failure-2026-09-14/factory-peer/VERDICT.md','9f85fdc6d4be5b519b5b6059ca184b2197cc067a9947e5296a147ee449c5c66e'],
 ['docs/library/proof/controller-boundary-source-failure-2026-09-14/fixture-peer/VERDICT.md',null],
 ['_scratch/controller-boundary-custody-design01/DESIGN.md','f65ab5d9bff0a4fddfec6363ce6074198e3b989d271c3cb5d02d20f681e0f2b3'],
 ['_scratch/windows-reservation-implementation-proposal02/reservation_file_port.py',null],
 ['_scratch/windows-interrupted-owner-native-proposal02/snapshot_reservations.py','e80ae881fa4af9cc7d1a3e4a06624f5b19abe4de09aec3844e8a541449335b98'],
 ['_scratch/windows-interrupted-owner-native-proposal02/snapshot_lifecycle.py','a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd'],
 ['_scratch/windows-interrupted-owner-native-proposal02/trusted_asr_resolver.py','16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833'],
 ['_scratch/windows-reservation-implementation-proposal02/test_reservations.py',null],
 ['_scratch/windows-reservation-implementation-proposal02/test_windows_reservations.py','91b0de71eb55d088ee2fdbcd11ff3e6a074f18f713dfcd5b384814a1dc78300c'],
 ['_scratch/windows-interrupted-owner-native-proposal02/generated_worker_flow.py','1ab240d60ceaca130ac85f5d2e908ef5895da5297f35d78a1caba1c62e622238'],
 ['_scratch/windows-interrupted-owner-native-proposal02/generated_adapter_flow.py','24844bf419e4d34adaf0d5c5a2678de33a4796de86dad0f83b7e386f1785f961'],
];
const inputRows=[];const snapshots=new Map();
for(const [name,expected]of selected){const p=path.join(root,name),b=fs.readFileSync(p),h=sha(b);if(expected&&h!==expected)throw Error('selected source mismatch '+name);inputRows.push({path:name,bytes:b.length,sha256:h});snapshots.set(p,h);}
const origin=JSON.parse(fs.readFileSync(path.join(dir,'INITIAL-SOURCE-PINS.json'))).inputs;
for(const row of origin){const a=fs.readFileSync(row.source),b=fs.readFileSync(path.join(dir,row.copy));if(sha(a)!==row.sha256||!a.equals(b))throw Error('original/copy mismatch '+row.copy);snapshots.set(row.source,sha(a));}
const required=[['durable_lifecycle.py','ce69903d93daf41ae3717008f8d0dbd0b3ead7b11662b674eddf43828567b222'],['asr_loading_adapter.py','227395c4e1f25f75f13dc950e3b2e222af4a4d8b307a36091908229b58ed0c0f']];
for(const[n,h]of required)if(sha(fs.readFileSync(path.join(dir,n)))!==h)throw Error('final source changed');
const derivativeNames=fs.readdirSync(dir,{withFileTypes:true}).filter(x=>x.isFile()&&!['SOURCE-INPUTS03.json','FINAL-BINDINGS03-ACTUAL.json'].includes(x.name)).map(x=>x.name);
for(const row of fs.readdirSync(path.join(dir,'before'),{withFileTypes:true})){if(!row.isFile())throw Error('unexpected nested history');derivativeNames.push('before/'+row.name);}
derivativeNames.sort();
const derivatives=derivativeNames.map(name=>{const b=fs.readFileSync(path.join(dir,name));return{name,bytes:b.length,sha256:sha(b)};});
if(![...snapshots].every(([p,h])=>sha(fs.readFileSync(p))===h))throw Error('input changed during final binding');
const fixed=[['reservation_file_port','_scratch/windows-reservation-implementation-proposal02/reservation_file_port.py'],['snapshot_reservations','_scratch/windows-interrupted-owner-native-proposal02/snapshot_reservations.py'],['snapshot_lifecycle','_scratch/windows-interrupted-owner-native-proposal02/snapshot_lifecycle.py'],['durable_lifecycle','_scratch/controller-boundary-custody-repair01/durable_lifecycle.py'],['trusted_asr_resolver','_scratch/windows-interrupted-owner-native-proposal02/trusted_asr_resolver.py'],['asr_loading_adapter','_scratch/controller-boundary-custody-repair01/asr_loading_adapter.py'],['test_reservations','_scratch/windows-reservation-implementation-proposal02/test_reservations.py']];
const coreClosure=fixed.map(([name,p])=>({module:name,path:p,sha256:sha(fs.readFileSync(path.join(root,p)))}));
const result={scope:'frozen source repair only; no harness/test/native admission',root,selected_inputs:inputRows,original_and_copy_bindings:origin,derivatives,core_canonical_modules:coreClosure,test_closure_status:'Separate fixture/gate closure and new cases are not qualified here',source_hashes_unchanged:true,candidate_executed:false};
fs.writeFileSync(path.join(dir,'SOURCE-INPUTS03.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
const mapBytes=fs.readFileSync(path.join(dir,'SOURCE-INPUTS03.json'));
console.log(JSON.stringify({selected_inputs:inputRows.length,original_copy_pairs:origin.length,derivative_count:derivatives.length,derivative_bytes:derivatives.reduce((a,b)=>a+b.bytes,0),core_module_count:coreClosure.length,source_map:{bytes:mapBytes.length,sha256:sha(mapBytes)},sources:required.map(([name,h])=>({name,bytes:fs.statSync(path.join(dir,name)).size,sha256:h})),report:{sha256:sha(fs.readFileSync(path.join(dir,'REPORT03.md')))},source_hashes_unchanged:true,candidate_executed:false},null,2));

