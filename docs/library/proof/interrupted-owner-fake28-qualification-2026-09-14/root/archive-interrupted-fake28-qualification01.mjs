import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/31e8890c-ab8/gemini';
const rel='docs/library/proof/interrupted-owner-fake28-qualification-2026-09-14';
const dest=path.join(work,rel);
if(fs.existsSync(dest))throw Error('fresh proof required');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const rows=[];
const copy=(src,name)=>{if(name.includes('..')||path.isAbsolute(name))throw Error('relative payload');const st=fs.lstatSync(src);if(!st.isFile()||st.isSymbolicLink())throw Error('plain file '+src);const b=fs.readFileSync(src);const d=path.join(dest,name);fs.mkdirSync(path.dirname(d),{recursive:true});fs.writeFileSync(d,b,{flag:'wx'});if(!fs.readFileSync(d).equals(b))throw Error('copy '+name);rows.push({path:name,bytes:b.length,sha256:sha(b)});};
const tree=(src,prefix)=>{for(const e of fs.readdirSync(src,{withFileTypes:true})){if(e.isSymbolicLink())throw Error('no link');if(e.isDirectory())tree(path.join(src,e.name),prefix+'/'+e.name);else copy(path.join(src,e.name),prefix+'/'+e.name);}};
for(const [dir,prefix]of [
 ['interrupted-owner-retirement-repair02','repaired-source'],
 ['interrupted-repair02-core-peer-review01','core-peer-review'],
 ['interrupted-retirement-fake28-preparation01','pending-instrument'],
 ['interrupted-retirement-fake28-author01','author'],
 ['astra-interrupted-retirement-confirmation01','independent'],
 ['interrupted-retirement-confirmation-copy-preparation01','independent-copy-record'],
 ['interrupted-fake28-peer-receipt-review01','receipt-peer-review'],
 ['interrupted-repair02-mechanical-diffs01','mechanical-source-diffs']
])tree(path.join(root,'_scratch',dir),prefix);
for(const n of [
 'INTERRUPTED-FAKE28-AUTHOR-MATERIALIZATION-ACTUAL.json',
 'INTERRUPTED-REPAIR02-INPUT-MAP-ACTUAL.json',
 'INTERRUPTED-REPAIR02-ROOT-PRESERVATION-ACTUAL.json',
 'INTERRUPTED-REPAIR02-ROOT-TEST-READ-ACTUAL.json',
 'INTERRUPTED-REPAIR02-ROOT-LOCK-READ-ACTUAL.json',
 'INTERRUPTED-REPAIR02-ROOT-FIXTURE-ACQUISITION-READ-ACTUAL.json',
 'INTERRUPTED-FAKE28-INSTRUMENT-ROOT-READ01-ACTUAL.json',
 'INTERRUPTED-FAKE28-INSTRUMENT-ROOT-READ02-ACTUAL.json',
 'INTERRUPTED-REPAIR02-FINAL-REVIEW-READ-ACTUAL.json',
 'INTERRUPTED-FAKE28-FINAL-AUTHOR-CONTROL-READ-ACTUAL.json',
 'INTERRUPTED-FAKE28-PREADMISSION-BOUNDARIES-READ-ACTUAL.json',
 'INTERRUPTED-FAKE28-AUTHOR-PREADMISSION-CHECK-ACTUAL.json',
 'INTERRUPTED-FAKE28-AUTHOR-RUN-ACTUAL.json',
 'INTERRUPTED-FAKE28-AUTHOR-RECEIPT-READ-ACTUAL.json',
 'INTERRUPTED-FAKE28-INDEPENDENT-CONTROL-READ-ACTUAL.json',
 'INTERRUPTED-FAKE28-AUTHOR-VERIFICATION-ACTUAL.json',
 'INTERRUPTED-FAKE28-INDEPENDENT-RUN-ACTUAL.json',
 'INTERRUPTED-FAKE28-BOTH-VERIFICATION-ACTUAL.json',
 'INTERRUPTED-FAKE28-PEER-VERDICT-READ-ACTUAL.json',
 'INTERRUPTED-REPAIR02-MECHANICAL-VERDICT-READ-ACTUAL.json',
 'prepare-interrupted-repair-inputs02.mjs','check-interrupted-repair-preservation02.mjs',
 'interrupted-repair02-root-preservation.json','materialize-interrupted-fake28-author01.mjs',
 'check-fake28-author-admission01.mjs','verify-fake28-receipts01.mjs',
 'archive-interrupted-fake28-qualification01.mjs'
])copy(path.join(root,'_scratch',n),'root/'+n);
for(const n of ['INTERRUPTED-OWNER-SOURCE-REPAIR-BRIEF-2026-09-14.md','INTERRUPTED-OWNER-FAKE28-QUALIFICATION-BRIEF-2026-09-14.md','ASTRA-INTERRUPTED-OWNER-FAKE28-ADMISSION-2026-09-14.md','ASTRA-INTERRUPTED-OWNER-FAKE28-VERDICT-2026-09-14.md'])copy(path.join(root,'docs/library',n),n);
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(dest,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});
rows.sort((a,b)=>a.path.localeCompare(b.path));
const manifest=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'Repaired generated interrupted-owner source and two fixed fake28 qualifications; no real kernel/model, production or release qualification.',files:rows},null,2)+'\n');
fs.writeFileSync(path.join(dest,'SHA256.json'),manifest,{flag:'wx'});
console.log(JSON.stringify({archive:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(manifest)}));
