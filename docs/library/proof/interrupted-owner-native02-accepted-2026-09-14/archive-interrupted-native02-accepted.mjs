import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/31e8890c-ab8/gemini';
const rel='docs/library/proof/interrupted-owner-native02-accepted-2026-09-14';
const out=path.join(work,rel), scratch=path.join(root,'_scratch');
if(fs.existsSync(out))throw Error('Fresh archive required');
const rows=[],seen=new Set(),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const prep=path.join(scratch,'windows-interrupted-owner-native-proposal02');
const prepSeal=fs.readFileSync(path.join(prep,'PINS.json'));
if(sha(prepSeal)!=='c5808c7af66630b77d399409564733893a074de36169817ff4cd5234981c250d')throw Error('Frozen preparation seal');
const prepRows=JSON.parse(prepSeal).files;if(prepRows.length!==56)throw Error('Preparation membership');
for(const r of prepRows){if(path.isAbsolute(r.path)||r.path.split('/').includes('..'))throw Error('Relative preparation path');const b=fs.readFileSync(path.join(prep,r.path));if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error('Frozen preparation '+r.path);}
function copy(source,target){
 if(path.isAbsolute(target)||target.split('/').includes('..')||seen.has(target))throw Error('Archive target');
 const st=fs.lstatSync(source);if(!st.isFile()||st.isSymbolicLink())throw Error('Plain input only');
 const b=fs.readFileSync(source);fs.mkdirSync(path.dirname(path.join(out,target)),{recursive:true});
 fs.writeFileSync(path.join(out,target),b,{flag:'wx'});seen.add(target);rows.push({path:target,bytes:b.length,sha256:sha(b)});
}
function tree(source,target){for(const name of fs.readdirSync(source).sort()){
 const p=path.join(source,name),s=fs.lstatSync(p);if(s.isSymbolicLink())throw Error('No links');
 if(s.isDirectory())tree(p,target+'/'+name);else if(s.isFile())copy(p,target+'/'+name);else throw Error('Plain tree only');
}}
for(const [dir,label] of [
 ['windows-interrupted-owner-native-proposal02','preparation'],
 ['interrupted-owner-native02-peer-review','source-peer-review'],
 ['interrupted-owner-native02-receipt-peer','receipt-peer-review']
])tree(path.join(scratch,dir),label);
const run=path.join(scratch,'windows-interrupted-owner-retirement02');
const sourceMap=JSON.parse(fs.readFileSync(path.join(run,'SOURCE-INPUTS.json')));
const sourceNames=Object.keys(sourceMap.source_sha256);
if(sourceNames.length!==29||sourceNames.some(n=>path.basename(n)!==n||!n.endsWith('.py')))throw Error('29 exact source texts');
for(const name of sourceNames){const p=path.join(run,name);if(sha(fs.readFileSync(p))!==sourceMap.source_sha256[name])throw Error('Copied source mismatch '+name);copy(p,'run-saved/'+name);}
for(const name of ['before.json','after.json','exit.json','native-exit.json','controller-result.json','contender-result.json','child-receipt-observation.json','closed-journal-observation.json','interrupted-journal-observation.json','controller-stdout.log','controller-stderr.log','ROOT-ADMISSION.json','SOURCE-INPUTS.json','run_interrupted_owner02.ps1'])copy(path.join(run,name),'run-saved/'+name);
for(const name of ["INTERRUPTED-NATIVE-RUN02-ACTUAL.json","INTERRUPTED-NATIVE-RUN02-INITIAL-RECEIPTS-ACTUAL.json","INTERRUPTED-NATIVE02-SOURCE-BRIEF-COMMIT-ACTUAL.json","INTERRUPTED-NATIVE02-ROOT-INPUT-CHECK-ACTUAL.json","INTERRUPTED-NATIVE02-ROOT-DELTA-READ-ACTUAL.json","INTERRUPTED-NATIVE02-ADMISSION-COMMIT-ACTUAL.json","INTERRUPTED-NATIVE02-ROOT-RECEIPT-READ-ACTUAL.json","INTERRUPTED-NATIVE02-ROOT-PEER-READ-ACTUAL.json","INTERRUPTED-NATIVE02-ROOT-RECEIPT-CHECK-ACTUAL.json","INTERRUPTED-NATIVE02-ROOT-CHECKER-DIAGNOSIS-ACTUAL.json","INTERRUPTED-NATIVE02-ROOT-CHECKER-REPAIR02.md","INTERRUPTED-NATIVE02-ROOT-RECEIPT-CHECK02-ACTUAL.json","INTERRUPTED-NATIVE02-ROOT-RECEIPT-RESULT.json","check-native02-inputs-root.mjs","prepare-native02-root-check.mjs","check-native02-root-receipts.ps1","check-native02-root-receipts02.ps1","prepare-native02-archive-tools.mjs"])copy(path.join(scratch,name),'root-records/'+name);
for(const name of ['ASTRA-NATIVE-INTERRUPTED-OWNER02-ADMISSION-2026-09-14.md','INTERRUPTED-OWNER-NATIVE02-SOURCE-BRIEF-2026-09-14.md','ASTRA-INTERRUPTED-NATIVE02-VERDICT-2026-09-14.md'])copy(path.join(root,'docs/library',name),'contracts/'+name);
copy(path.join(scratch,'archive-interrupted-native02-accepted.mjs'),'archive-interrupted-native02-accepted.mjs');
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});
rows.sort((a,b)=>a.path.localeCompare(b.path));
const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'Accepted generated native observation 9753fb, frozen preparation and saved text receipts, passive root and peer reviews. No physical journal, support, generated fixture, checkpoint or D2 output access for archive; no rerun.',files:rows},null,2)+'\n');
fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal)}));
