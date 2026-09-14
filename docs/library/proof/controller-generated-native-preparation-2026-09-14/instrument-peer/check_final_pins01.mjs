import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const root='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-generated-native-compatibility-proposal01';
const peer='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-generated-native-compatibility-peer01';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const pinRaw=fs.readFileSync(path.join(root,'PINS.json'));
assert.equal(hash(pinRaw),'f8ee47b3977da4d562850ccf616855e02d5a74df8e3bebf6dd7f4714172c0824');
const pins=JSON.parse(pinRaw);
assert.equal(pins.files.length,91);assert.equal(pins.payload_count,91);
assert.equal(pins.payload_bytes,1569239);
const allowedParents=new Set(['.','before','author-records']);
for(const name of allowedParents)assert.equal(fs.lstatSync(path.join(root,name)).isSymbolicLink(),false);
const rows=[];
for(const row of pins.files){
  assert.ok(allowedParents.has(path.posix.dirname(row.path)) && /^[a-zA-Z0-9_.\/-]+$/.test(row.path));
  assert.ok(!row.path.split('/').includes('..') && /\.(json|md|mjs|py|ps1|diff)$/.test(row.path));
  const full=path.join(root,row.path);assert.equal(fs.lstatSync(full).isSymbolicLink(),false);
  const b=fs.readFileSync(full);assert.equal(b.length,row.bytes);assert.equal(hash(b),row.sha256);
  rows.push({...row,after_sha256:hash(fs.readFileSync(full))});assert.equal(rows.at(-1).after_sha256,row.sha256);
}
assert.equal(new Set(rows.map(r=>r.path)).size,91);assert.equal(rows.reduce((n,r)=>n+r.bytes,0),1569239);
const disk=[];
for(const parent of allowedParents){
  for(const item of fs.readdirSync(path.join(root,parent),{withFileTypes:true})){
    if(item.isDirectory()){assert.equal(parent,'.');assert.ok(allowedParents.has(item.name));continue;}
    assert.ok(item.isFile());disk.push(parent==='.'?item.name:parent+'/'+item.name);
  }
}
assert.deepEqual(disk.sort(),[...rows.map(r=>r.path),'PINS.json','author-records/FINAL-PINS-ACTUAL.json'].sort());
const prior=JSON.parse(fs.readFileSync(path.join(peer,'CHECK-RESULT.json')));
const priorMap=new Map(prior.bindings.map(r=>[path.resolve(r.path),r]));let reconciled=0;
for(const row of rows){const old=priorMap.get(path.resolve(root,row.path));if(old){assert.equal(row.sha256,old.sha256);assert.equal(row.bytes,old.bytes);reconciled++;}}
const template=JSON.parse(fs.readFileSync(path.join(root,'ROOT-ADMISSION-TEMPLATE.json')));
assert.equal(template.root_reviewed,false);assert.ok(!disk.includes('ROOT-ADMISSION-drain.json'));
assert.ok(!fs.existsSync(template.run_path));
assert.equal(hash(fs.readFileSync(path.join(root,'PINS.json'))),hash(pinRaw));
const result={scope:'PASSIVE FINAL TEXT PIN RECONCILIATION',subject_executed:false,support_access:false,
  pins_sha256:hash(pinRaw),payload_count:91,payload_bytes:1569239,exact_folder_files:93,
  prior_bound_payloads_unchanged:reconciled,false_template:true,actual_admission_absent:true,new_run_absent:true,rows};
fs.writeFileSync(path.join(peer,'FINAL-FREEZE-BINDINGS.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({...result,rows:undefined}));
