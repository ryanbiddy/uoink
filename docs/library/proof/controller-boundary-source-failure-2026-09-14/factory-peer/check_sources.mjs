import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const repo='E:/AI/projects/uoink/checkouts/Yoink-library';
const root=path.join(repo,'_scratch/controller-boundary01-root-review');
const out=path.join(repo,'_scratch/controller-boundary01-factory-peer');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const pinsBytes=fs.readFileSync(path.join(root,'FROZEN-SOURCE-PINS.json'));
if(sha(pinsBytes)!=='1679fc8f78e08f6585232f9400cc12e3d2b2c15bcadb0d22bda31d50d149a438')throw Error('frozen pin manifest mismatch');
const pins=JSON.parse(pinsBytes), snapshots=new Map(), rows=[];
for(const row of pins.files){const file=path.join(root,row.path),bytes=fs.readFileSync(file);if(bytes.length!==row.bytes||sha(bytes)!==row.sha256)throw Error('pin mismatch '+row.path);snapshots.set(file,sha(bytes));rows.push(row);}
const map=JSON.parse(fs.readFileSync(path.join(root,'frozen/SOURCE-INPUTS.json')));
const origins=[];
for(const row of map.source_inputs){const file=path.join(repo,row.path),bytes=fs.readFileSync(file);if(bytes.length!==row.bytes||sha(bytes)!==row.sha256)throw Error('origin mismatch '+row.path);snapshots.set(file,sha(bytes));origins.push(row);}
for(const row of map.derivatives){const bytes=fs.readFileSync(path.join(root,'frozen',row.name));if(bytes.length!==row.bytes||sha(bytes)!==row.sha256)throw Error('derivative map mismatch '+row.name);}
function lines(t){const a=t.replace(/\r\n/g,'\n').split('\n');if(a.at(-1)==='')a.pop();return a;}
function parse(t){
 const ls=lines(t);if(!ls[0]?.startsWith('--- ')||!ls[1]?.startsWith('+++ '))throw Error('two unified headers required');
 const hunks=[];let i=2;
 while(i<ls.length){
  const h=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)$/.exec(ls[i]);
  if(!h)throw Error('invalid hunk header at patch line '+(i+1)+': '+JSON.stringify(ls[i]));
  const v={oldStart:+h[1],oldCount:h[2]===undefined?1:+h[2],newStart:+h[3],newCount:h[4]===undefined?1:+h[4],body:[]};i++;
  while(i<ls.length&&!ls[i].startsWith('@@ ')){
   if(!/^[ +\-]/.test(ls[i]))throw Error('invalid unified body marker at patch line '+(i+1)+': '+JSON.stringify(ls[i]));
   v.body.push(ls[i]);i++;
  }
  const oc=v.body.filter(x=>x[0]!=='+' ).length,nc=v.body.filter(x=>x[0]!=='-' ).length;
  if(oc!==v.oldCount||nc!==v.newCount)throw Error('hunk counts differ: expected '+v.oldCount+'/'+v.newCount+' actual '+oc+'/'+nc);
  hunks.push(v);
 }
 return hunks;
}
function apply(input,hunks,reverse){
 let cursor=0,result=[];
 for(const h of hunks){
  const start=reverse?h.newStart:h.oldStart;
  const index=start===0?0:start-1;
  if(index<cursor)throw Error('overlapping hunk');
  result.push(...input.slice(cursor,index));cursor=index;
  for(const b of h.body){
   const prefix=reverse?(b[0]==='+'?'-':b[0]==='-'?'+':b[0]):b[0],value=b.slice(1);
   if(prefix!=='+'&&input[cursor++]!==value)throw Error('context/removal mismatch at input line '+cursor);
   if(prefix!=='-')result.push(value);
  }
 }
 result.push(...input.slice(cursor));return result;
}
const diffs=[];
for(const name of ['durable_lifecycle','asr_loading_adapter']){
 const before=fs.readFileSync(path.join(root,'frozen/before',name+'.py'));
 const after=fs.readFileSync(path.join(root,'frozen',name+'.py'));
 const patch=fs.readFileSync(path.join(root,'frozen',name+'.diff'),'utf8');
 const row={name,before_sha256:sha(before),after_sha256:sha(after),patch_sha256:sha(Buffer.from(patch)),normalization:'CRLF to LF only'};
 try{
  const h=parse(patch),old=lines(before.toString('utf8')),next=lines(after.toString('utf8'));
  row.hunks=h.length;row.forward=JSON.stringify(apply(old,h,false))===JSON.stringify(next);row.reverse=JSON.stringify(apply(next,h,true))===JSON.stringify(old);
  if(!row.forward||!row.reverse)throw Error('reconstructed full text differs');
 }catch(e){row.forward=false;row.reverse=false;row.failure=e.message;}
 diffs.push(row);
}
const adapterOld=fs.readFileSync(path.join(root,'frozen/before/asr_loading_adapter.py')),adapterNew=fs.readFileSync(path.join(root,'frozen/asr_loading_adapter.py'));
const result={scope:'passive source/hash/unified-diff review only',frozen_count:rows.length,frozen_bytes:rows.reduce((a,b)=>a+b.bytes,0),frozen_pins:rows,origin_count:origins.length,origin_bytes:origins.reduce((a,b)=>a+b.bytes,0),origins,source_input_map_consistent:true,adapter_prefix_byte_identical:adapterNew.subarray(0,adapterOld.length).equals(adapterOld),diffs,all_sources_unchanged:[...snapshots].every(([file,hash])=>sha(fs.readFileSync(file))===hash),candidate_executed:false};
fs.writeFileSync(path.join(out,'CHECK-RESULT.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({frozen_count:result.frozen_count,frozen_bytes:result.frozen_bytes,origin_count:result.origin_count,origin_bytes:result.origin_bytes,adapter_prefix_byte_identical:result.adapter_prefix_byte_identical,diffs,all_sources_unchanged:result.all_sources_unchanged,candidate_executed:false},null,2));
if(diffs.some(x=>x.failure))process.exitCode=1;

