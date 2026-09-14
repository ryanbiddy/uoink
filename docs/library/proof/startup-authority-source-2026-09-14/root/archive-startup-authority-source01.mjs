import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',scratch=path.join(root,'_scratch'),work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/56af690a-060/gemini',rel='docs/library/proof/startup-authority-source-2026-09-14',out=path.join(work,rel),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
if(fs.existsSync(out))throw Error('Fresh archive required');
const source=path.join(scratch,'real-startup-authority-repair01'),raw=fs.readFileSync(path.join(source,'SOURCE-INPUTS.json'));
if(sha(raw)!=='23591b4c9fd6d18ee9856c5abb9329ce926ab49553c72bb20b1eaaf8a549d775')throw Error('Source map changed');
const map=JSON.parse(raw);for(const r of map.derivatives){const b=fs.readFileSync(path.join(source,r.path));if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error('Derivative changed');}
const rows=[],pending=[];
function plan(from,to){const st=fs.lstatSync(from);if(!st.isFile()||st.isSymbolicLink()||!/^.*\.(json|md|mjs|py|ps1|diff|txt|log|patch)$/.test(from))throw Error('Plain source/document only '+from);const b=fs.readFileSync(from);if(!Buffer.from(b.toString('utf8'),'utf8').equals(b))throw Error('Invalid UTF8');pending.push({to,b});}
function tree(from,to){for(const e of fs.readdirSync(from,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){if(e.isSymbolicLink())throw Error('Link');if(e.isDirectory())tree(path.join(from,e.name),to+'/'+e.name);else plan(path.join(from,e.name),to+'/'+e.name);}}
tree(source,'source');
tree(path.join(scratch,'real-startup-authority-peer01'),'independent-source-review');
tree(path.join(scratch,'startup-authority-qualification-plan01'),'qualification-plan');
tree(path.join(scratch,'real-engine-next-contract01'),'next-constructor-contract');
tree(path.join(scratch,'control-room-command-provenance02-root'),'control-room-integration');
const fixed=['check-startup-authority-source01.mjs','archive-startup-authority-source01.mjs','BACKUP-PUSH-3954258-ACTUAL.json','BACKUP-PUSH-3954258-REMOTE-ACTUAL.json','REAL-ENGINE-CONNECTION01-ARCHIVE-ACTUAL.json','REAL-ENGINE-CONNECTION01-FAILURE-COMMIT-ACTUAL.json','REAL-ENGINE-CONNECTION01-FAILURE-INDEX-ACTUAL.json','REAL-ENGINE-CONNECTION01-FAILURE-INTEGRATION-ACTUAL.json','REAL-ENGINE-CONNECTION01-FAILURE-TRANSPORT-RESULT.json'];
for(const n of fs.readdirSync(scratch).sort())if(/^(STARTUP-AUTHORITY-|REAL-VAD-PARENT-LINK-).*ACTUAL\.json$/.test(n))fixed.push(n);
for(const n of fixed)plan(path.join(scratch,n),'root/'+n);
for(const n of ['ASTRA-STARTUP-AUTHORITY-SOURCE-VERDICT-2026-09-14.md','REAL-STARTUP-AUTHORITY-REPAIR-BRIEF-2026-09-14.md','STARTUP-AUTHORITY-QUALIFICATION-BRIEF-2026-09-14.md','REAL-VAD-PARENT-LINK-2026-09-14.md'])plan(path.join(root,'docs/library',n),'contracts/'+n);
if(new Set(pending.map(r=>r.to)).size!==pending.length)throw Error('Duplicate path');
for(const {to,b} of pending){fs.mkdirSync(path.dirname(path.join(out,to)),{recursive:true});fs.writeFileSync(path.join(out,to),b,{flag:'wx'});rows.push({path:to,bytes:b.length,sha256:sha(b)});}
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});
rows.sort((a,b)=>a.path.localeCompare(b.path));const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'Controller source accepted for qualification; all16 new cases unexecuted. Includes earlier integration receipts and next-constructor source context. No native/model/runtime acceptance.',files:rows},null,2)+'\n');fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal),source_map_sha256:sha(raw),proposed_tests:16,qualification:'not executed',source_review:'accepted for qualification'}));
