import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const rel='docs/library/proof/interrupted-owner-fake28-qualification-2026-09-14';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/31e8890c-ab8/gemini';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const m=fs.readFileSync(path.join(work,rel,'SHA256.json'));
const rows=JSON.parse(m).files, changes=[];
for(const r of [...rows,{path:'SHA256.json',bytes:m.length,sha256:sha(m)}]){
 if(r.path.includes('..')||path.isAbsolute(r.path))throw Error('relative');
 const a=fs.readFileSync(path.join(work,rel,r.path)),b=fs.readFileSync(path.join(root,rel,r.path));
 if(a.length!==r.bytes||sha(a)!==r.sha256)throw Error('donor seal '+r.path);
 if(!a.equals(b)){if(a.toString('utf8').replaceAll('\r\n','\n')!==b.toString('utf8').replaceAll('\r\n','\n'))throw Error('non-newline '+r.path);changes.push({path:r.path,before_bytes:b.length,after_bytes:a.length,raw:a});}
}
for(const c of changes)fs.writeFileSync(path.join(root,rel,c.path),c.raw);
const report={archive:rel,payloads:rows.length,manifest_sha256:sha(m),restored:changes.map(({raw,...r})=>r)};
fs.writeFileSync(path.join(root,'_scratch/FAKE28-TRANSPORT-REPAIR02-RESULT.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({payloads:rows.length,restored:changes.length,manifest_sha256:sha(m),report:'_scratch/FAKE28-TRANSPORT-REPAIR02-RESULT.json'}));
