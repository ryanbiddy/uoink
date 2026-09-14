import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/31e8890c-ab8/gemini';
const rel='docs/library/proof/interrupted-owner-prelock30-qualification-2026-09-14';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const seal=fs.readFileSync(path.join(work,rel,'SHA256.json')), rows=JSON.parse(seal).files;
const all=[...rows,{path:'SHA256.json',bytes:seal.length,sha256:sha(seal)}],changes=[];
for(const r of all){
 if(path.isAbsolute(r.path)||r.path.split('/').includes('..'))throw Error('Relative path');
 const a=fs.readFileSync(path.join(work,rel,r.path)),b=fs.readFileSync(path.join(root,rel,r.path));
 if(a.length!==r.bytes||sha(a)!==r.sha256)throw Error('Donor seal mismatch '+r.path);
 if(!a.equals(b)){if(!Buffer.from(a.toString('utf8'),'utf8').equals(a)||!Buffer.from(b.toString('utf8'),'utf8').equals(b)||a.toString('utf8').replaceAll('\r\n','\n')!==b.toString('utf8').replaceAll('\r\n','\n'))throw Error('Non-newline transport difference '+r.path);changes.push({path:r.path,before_bytes:b.length,before_sha256:sha(b),raw:a});}
}
for(const c of changes)fs.writeFileSync(path.join(root,rel,c.path),c.raw);
for(const r of all){const b=fs.readFileSync(path.join(root,rel,r.path));if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error('Final raw equality '+r.path);}
const result={scope:'Documented Git newline transport restoration; no subject rerun',proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal),restored:changes.map(({raw,...r})=>({...r,after_bytes:raw.length,after_sha256:sha(raw)})),all_raw_payloads_and_seal_equal_donor:true};
fs.writeFileSync(path.join(root,'_scratch/PRELOCK30-TRANSPORT-RESULT.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({payloads:rows.length,bytes:result.bytes,manifest_sha256:result.manifest_sha256,newline_only_restored:changes.length,all_raw_payloads_and_seal_equal_donor:true}));
