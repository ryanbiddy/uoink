import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const repo='E:/AI/projects/uoink/checkouts/Yoink-library';
const root=path.join(repo,'_scratch/controller-worker-stage-repair01');
const out=path.join(repo,'_scratch/controller-worker-stage-peer01');
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const retained=new Map();
function read(p){p=path.resolve(p);assert(p.startsWith(path.resolve(repo)+path.sep));assert(/\.(?:py|txt|json|md|diff)$/i.test(p));const b=fs.readFileSync(p);if(retained.has(p))assert(retained.get(p).equals(b));else retained.set(p,b);return b;}
function pinned(p,n,h){const b=read(p);if(n!==undefined)assert.equal(b.length,n,p);assert.equal(hash(b),h,p);return b;}
const rawMap=pinned(path.join(root,'SOURCE-INPUTS.json'),undefined,'0fd7fe35f9936d1a102f5c1b70962b7df6ae022d34f7fb4c6ffb9959484e2835');
const map=JSON.parse(rawMap);
assert.equal(map.original_inputs.length,16);assert.equal(map.derivatives.length,11);
pinned(path.join(repo,map.brief.path),undefined,map.brief.sha256);
for(const r of map.original_inputs){
 const original=pinned(path.join(repo,r.source),r.bytes,r.sha256);
 const copy=pinned(path.join(root,r.copy),r.bytes,r.sha256);assert(copy.equals(original));
}
for(const r of map.derivatives)pinned(path.join(root,r.path),r.bytes,r.sha256);
const before=read(path.join(root,'before/asr_loading_adapter.py')),after=read(path.join(root,'asr_loading_adapter.py'));
assert.equal(before.length,28922);assert(after.subarray(0,before.length).equals(before));
assert(after.subarray(before.length).equals(read(path.join(root,'stage_addition.py.txt'))));
const normalize=b=>b.toString('utf8').replaceAll('\r\n','\n');
function lines(b){if(!b.length)return[];const s=normalize(b);assert(s.endsWith('\n'));return s.slice(0,-1).split('\n');}
function patchCheck(file,diffName,previous){
 const b=lines(previous),a=lines(read(path.join(root,file))),d=lines(read(path.join(root,diffName)));
 assert(d[0].startsWith('--- ')&&d[1].startsWith('+++ '));let i=2,bc=0,ac=0,forward=[],reverse=[],hunks=0;
 while(i<d.length){
  const m=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(d[i++]);assert(m,file);
  const bn=m[2]===undefined?1:+m[2],an=m[4]===undefined?1:+m[4],bi=bn?+m[1]-1:+m[1],ai=an?+m[3]-1:+m[3];
  assert(bi>=bc&&ai>=ac);forward.push(...b.slice(bc,bi));reverse.push(...a.slice(ac,ai));bc=bi;ac=ai;let bs=0,as=0;
  while(i<d.length&&!d[i].startsWith('@@ ')){
   const s=d[i++],kind=s[0],text=s.slice(1);assert([' ','-','+'].includes(kind));
   if(kind!=='+'){assert.equal(b[bc++],text);bs++;reverse.push(text);}
   if(kind!=='-'){assert.equal(a[ac++],text);as++;forward.push(text);}
  }
  assert.equal(bs,bn);assert.equal(as,an);hunks++;
 }
 forward.push(...b.slice(bc));reverse.push(...a.slice(ac));assert.deepEqual(forward,a);assert.deepEqual(reverse,b);
 return{file,hunks,before_lines:b.length,after_lines:a.length,complete_forward_reverse:true,comparison:'LF-normalized texts; bytes independently pinned'};
}
const diffs=[patchCheck('asr_loading_adapter.py','asr_loading_adapter.diff',before),
 patchCheck('worker_stage_fixture.py','worker_stage_fixture.py.diff',Buffer.alloc(0)),
 patchCheck('test_controller_worker_stage.py','test_controller_worker_stage.py.diff',Buffer.alloc(0))];
const expected=JSON.parse(read(path.join(root,'EXPECTED-CASES.json')));
const tests=normalize(read(path.join(root,'test_controller_worker_stage.py')));
assert(tests.includes('class ControllerWorkerStageContracts(unittest.TestCase):'));
const methods=[...tests.matchAll(/^    def (test_[A-Za-z0-9_]+)\(self\):$/gm)].map(m=>'test_controller_worker_stage.ControllerWorkerStageContracts.'+m[1]);
assert.equal(methods.length,14);assert.deepEqual(methods,expected);assert.equal(new Set(methods).size,14);
for(const[p,b]of retained)assert(fs.readFileSync(p).equals(b),'input changed '+p);
const result={status:'PASSIVE_SOURCE_BINDINGS_MATCH',candidateExecuted:false,map_sha256:hash(rawMap),original_copy_pairs:16,derivative_records:11,all_read_texts:retained.size,exact_accepted_prefix_bytes:before.length,exact_append_bytes:after.length-before.length,diffs,proposed_case_ids:expected,case_results:'unexecuted',all_read_inputs_unchanged:true};
fs.writeFileSync(path.join(out,'CHECK-RESULT.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
process.stdout.write(JSON.stringify(result,null,2)+'\n');

