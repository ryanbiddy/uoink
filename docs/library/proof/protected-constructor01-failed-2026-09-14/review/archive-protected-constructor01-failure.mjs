import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e6133b1f-fc8/gemini';
const rel='docs/library/proof/protected-constructor01-failed-2026-09-14', out=path.join(work,rel);
const src=path.join(root,'_scratch/protected-asr-constructor01-root-review');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
if(fs.existsSync(out))throw Error('Fresh archive required');
const rows=[];
function copy(from,name){
 if(path.isAbsolute(name)||name.split('/').includes('..'))throw Error('Relative path');
 const st=fs.lstatSync(from);if(!st.isFile()||st.isSymbolicLink())throw Error('Plain source only');
 const b=fs.readFileSync(from);fs.mkdirSync(path.dirname(path.join(out,name)),{recursive:true});
 fs.writeFileSync(path.join(out,name),b,{flag:'wx'});rows.push({path:name,bytes:b.length,sha256:sha(b)});
}
const pins=JSON.parse(fs.readFileSync(path.join(src,'FROZEN-SOURCE-PINS.json'),'utf8')).files;
if(pins.length!==22)throw Error('Exact delivered source count');
for(const r of pins){const b=fs.readFileSync(path.join(src,r.path));if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error('Frozen source '+r.path);copy(path.join(src,r.path),r.path);}
for(const n of ['FROZEN-SOURCE-PINS.json','INPUT-MAP-CHECK.json','DIFF-HEADER-CHECK.json','CONTROL-ROOM-RECORD.json','COMMAND-EVENTS.json'])copy(path.join(src,n),'review/'+n);
for(const n of ['DIFF-CHECK','DISPATCH','FREEZE-AUDIT','POLL01','POLL02','POLL03','POLL04','STATUS01'])copy(path.join(root,'_scratch/PROTECTED-ASR-CONSTRUCTOR01-'+n+'-ACTUAL.json'),'actuals/'+n+'-ACTUAL.json');
for(const n of ['freeze-constructor01-review.mjs','check-constructor01-diff-headers.mjs','archive-protected-constructor01-failure.mjs'])copy(path.join(root,'_scratch',n),'review/'+n);
for(const n of ['ASTRA-PROTECTED-CONSTRUCTOR01-FAILURE-2026-09-14.md','PROTECTED-ENGINE-OWNERSHIP-REPAIR-BRIEF-2026-09-14.md','PROTECTED-ASR-CONSTRUCTOR-BRIEF-2026-09-14.md'])copy(path.join(root,'docs/library',n),'contracts/'+n);
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});
rows.sort((a,b)=>a.path.localeCompare(b.path));
const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'FAILED source review, unexecuted 13 proposed tests. Exact delivered source, passive audits and original Control Room records. No production or runtime acceptance.',files:rows},null,2)+'\n');
fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal)}));
