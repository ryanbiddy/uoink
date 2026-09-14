import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const repo='E:/AI/projects/uoink/checkouts/Yoink-library';
const parent=path.join(repo,'_scratch/real-child-namespace01-root-review');
const root=path.join(parent,'frozen');
const out=path.join(repo,'_scratch/child-namespace01-process-peer');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const read=p=>fs.readFileSync(p);
const pin=read(path.join(parent,'FROZEN-SOURCE-PINS.json'));
assert.equal(sha(pin),'75d20134558f5cebf61a8dc219d8652bf9d592a1ca29d835d757c8fd749fa124');
const rows=JSON.parse(pin).files;
assert.equal(rows.length,26);
const snapshots=new Map();
for(const row of rows){
 const p=path.resolve(parent,row.path); assert(p.startsWith(root+path.sep));
 const bytes=read(p); assert.equal(bytes.length,row.bytes,row.path); assert.equal(sha(bytes),row.sha256,row.path); snapshots.set(p,bytes);
}
assert.equal(rows.reduce((n,r)=>n+r.bytes,0),553800);
const normalized=b=>b.toString('utf8').replaceAll('\r\n','\n');
function lines(b){const s=normalized(b); assert(s.endsWith('\n'));return s.slice(0,-1).split('\n');}
function diffCheck(name){
 const b=lines(read(path.join(root,'before',name+'.py')));
 const a=lines(read(path.join(root,name+'.py')));
 const d=lines(read(path.join(root,name+'.diff')));
 assert(d[0].startsWith('--- ') && d[1].startsWith('+++ '));
 let cursor=0, result=[], reverse=[], acursor=0, hunks=0;
 for(let i=2;i<d.length;){
  const m=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(d[i++]);assert(m,'hunk '+name);
  const oldStart=+m[1],oldCount=m[2]===undefined?1:+m[2],newStart=+m[3],newCount=m[4]===undefined?1:+m[4];
  const oi=oldCount===0?oldStart:oldStart-1,ai=newCount===0?newStart:newStart-1;
  assert(oi>=cursor && ai>=acursor);result.push(...b.slice(cursor,oi)); reverse.push(...a.slice(acursor,ai));
  cursor=oi;acursor=ai;let oldSeen=0,newSeen=0;
  while(i<d.length&&!d[i].startsWith('@@ ')){
   const l=d[i++]; if(l.startsWith('\\ No newline'))continue;
   assert([' ','-','+'].includes(l[0]),'line '+name);
   const s=l.slice(1);
   if(l[0]!=='+' ){assert.equal(b[cursor++],s,'old '+name);oldSeen++;}
   if(l[0]!=='-'){assert.equal(a[acursor++],s,'new '+name);newSeen++;result.push(s);}
   if(l[0]!=='+')reverse.push(s);
  }
  assert.equal(oldSeen,oldCount);assert.equal(newSeen,newCount);hunks++;
 }
 result.push(...b.slice(cursor));reverse.push(...a.slice(acursor));
 assert.deepEqual(result,a,'forward '+name);assert.deepEqual(reverse,b,'reverse '+name);
 return {name,headers:d.slice(0,2),hunks,oldLines:b.length,newLines:a.length,forward:true,reverse:true,comparison:'complete LF-normalized texts; raw bytes independently pinned'};
}
const diffs=['inherited_readset','pinned_buffer_namespace','owned_generation_protocol'].map(diffCheck);
function methods(b){
 const ls=lines(b), entries={}; let cls='';
 for(let i=0;i<ls.length;i++){
  const cm=/^class (\w+)/.exec(ls[i]);if(cm)cls=cm[1];
  const m=/^( *)def (\w+)\(/.exec(ls[i]);if(!m)continue;
  const indent=m[1].length;let end=i+1;
  while(end<ls.length){
   const l=ls[end];if(l.trim()&&!l.trimStart().startsWith('#')&&l.match(/^ */)[0].length<=indent)break;
   end++;
  }
  let body=ls.slice(i,end);while(body.length&&!body.at(-1).trim())body.pop();
  entries[(indent?cls+'.':'')+m[2]]=body.join('\n');
 }
 return entries;
}
const preservation=[];
for(const name of ['inherited_readset','pinned_buffer_namespace','owned_generation_protocol']){
 const b=methods(read(path.join(root,'before',name+'.py'))),a=methods(read(path.join(root,name+'.py')));
 preservation.push({name,unchanged:Object.keys(b).filter(k=>a[k]===b[k]),changed:Object.keys(b).filter(k=>a[k]!==b[k]),new:Object.keys(a).filter(k=>!(k in b))});
}
const dependencies=[
 ['_scratch/protected-engine-ownership-repair02/worker_runtime_owner.py','25e57481197e07c8731d54a5313c822e482624f3bc106717870e15890c3362fe'],
 ['_scratch/windows-interrupted-owner-native-proposal02/model_binding_registry.py','48567add0f0ac2ac9140e9aa86b06f077454c98e2f0773100da5ba070f7b3deb']
].map(([relative,expected])=>{const b=read(path.join(repo,relative));assert.equal(sha(b),expected);return{path:relative,bytes:b.length,sha256:sha(b)};});
for(const[p,b]of snapshots)assert(read(p).equals(b),'changed '+p);
const result={status:'PASSIVE_BINDINGS_AND_DIFFS_MATCH',candidateExecuted:false,files:rows.length,bytes:553800,pins_sha256:sha(pin),diffs,preservation,additionalCalledSourceDependencies:dependencies,allFrozenInputsUnchanged:true};
fs.writeFileSync(path.join(out,'BINDINGS-RESULT.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
process.stdout.write(JSON.stringify(result,null,2)+'\n');

