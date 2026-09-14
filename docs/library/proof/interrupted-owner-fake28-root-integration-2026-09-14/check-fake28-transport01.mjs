import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const rel='docs/library/proof/interrupted-owner-fake28-qualification-2026-09-14';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/31e8890c-ab8/gemini';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const m=fs.readFileSync(path.join(work,rel,'SHA256.json'));
const rows=JSON.parse(m).files;
for(const r of [...rows,{path:'SHA256.json',bytes:m.length,sha256:sha(m)}]){if(r.path.includes('..')||path.isAbsolute(r.path))throw Error('relative');const a=fs.readFileSync(path.join(work,rel,r.path)),b=fs.readFileSync(path.join(root,rel,r.path));if(a.length!==r.bytes||sha(a)!==r.sha256||!a.equals(b))throw Error('raw transport '+r.path);}
console.log(JSON.stringify({payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(m),donor_and_checkout_raw_identical:true,mutation:false}));
