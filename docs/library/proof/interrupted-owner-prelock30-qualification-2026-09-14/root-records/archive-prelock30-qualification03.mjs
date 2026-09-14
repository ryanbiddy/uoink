import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',scratch=path.join(root,'_scratch');
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/31e8890c-ab8/gemini';
const rel='docs/library/proof/interrupted-owner-prelock30-qualification-2026-09-14',out=path.join(work,rel);
if(fs.existsSync(out))throw Error('Fresh proof required');
const done=JSON.parse(fs.readFileSync(path.join(scratch,'INTERRUPTED-PRELOCK30-BOTH-RECEIPT-CHECK-ACTUAL.json')));
if(done.exit_code!==0||done.session_id||!done.output.includes('identical_cases_and_child_hashes'))throw Error('Completed receipt review');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),rows=[],seen=new Set();
function copy(source,target){if(path.isAbsolute(target)||target.split('/').includes('..')||seen.has(target))throw Error('Relative unique target');const s=fs.lstatSync(source);if(!s.isFile()||s.isSymbolicLink())throw Error('Plain source');const b=fs.readFileSync(source);fs.mkdirSync(path.dirname(path.join(out,target)),{recursive:true});fs.writeFileSync(path.join(out,target),b,{flag:'wx'});seen.add(target);rows.push({path:target,bytes:b.length,sha256:sha(b)});}
function tree(source,target){for(const name of fs.readdirSync(source).sort()){const p=path.join(source,name),s=fs.lstatSync(p);if(s.isSymbolicLink())throw Error('No links');if(s.isDirectory())tree(p,target+'/'+name);else if(s.isFile())copy(p,target+'/'+name);else throw Error('Plain tree');}}
for(const [source,label] of [
 ['interrupted-owner-prelock-repair03','driver-repair'],
 ['interrupted-owner-prelock-controls03','new-controls'],
 ['interrupted-owner-prelock-peer-review03','source-review'],
 ['interrupted-owner-prelock-fake30-author03','author'],
 ['interrupted-owner-prelock-fake30-confirmation03','confirmation'],
 ['interrupted-owner-prelock-confirmation-copy03','independent-copy'],
 ['interrupted-owner-prelock-fake30-receipt-peer03','receipt-review']
])tree(path.join(scratch,source),label);
for(const name of fs.readdirSync(scratch).filter(n=>/^INTERRUPTED-PRELOCK(?:03|30)-.*-ACTUAL\.json$/.test(n)).sort())copy(path.join(scratch,name),'root-actuals/'+name);
for(const name of ['check-prelock30-inputs-root.mjs','check-prelock30-inputs-root02.mjs','verify-prelock30-receipts-root.mjs','PRELOCK30-ROOT-CHECKER-REPAIR02.md','archive-prelock30-qualification03.mjs','BACKUP-PUSH-7F142E8-ACTUAL.json','BACKUP-PUSH-7F142E8-REMOTE-ACTUAL.json'])copy(path.join(scratch,name),'root-records/'+name);
for(const name of ['INTERRUPTED-OWNER-PRELOCK-REPAIR-BRIEF-2026-09-14.md','ASTRA-PRELOCK30-QUALIFICATION-ADMISSION-2026-09-14.md','ASTRA-PRELOCK30-QUALIFICATION-VERDICT-2026-09-14.md','INTERRUPTED-OWNER-NATIVE02-SOURCE-BRIEF-2026-09-14.md'])copy(path.join(root,'docs/library',name),'contracts/'+name);
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});rows.sort((a,b)=>a.path.localeCompare(b.path));
const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'Qualified two-line prelock driver repair, two new actual-controller inert tests, unchanged original28/57, author and independent30/0/0 plus62 passing subtests, source/receipt reviews and retained preparation failures. No native/model or production acceptance.',files:rows},null,2)+'\n');fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal)}));
