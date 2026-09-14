import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/31e8890c-ab8/gemini';
const rel='docs/library/proof/interrupted-owner-native01-failure-2026-09-14';
const out=path.join(work,rel), scratch=path.join(root,'_scratch');
if(fs.existsSync(out))throw Error('Fresh archive required');
const rows=[],seen=new Set(),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const prep=path.join(scratch,'windows-interrupted-owner-native-proposal01');
const prepSeal=fs.readFileSync(path.join(prep,'PINS.json'));
if(sha(prepSeal)!=='2ce447ecc0145d5a14a0fc8ea57cf5cd2b9134ff0293aab33b5b2e9bc2a2f223')throw Error('Frozen preparation seal');
const prepRows=JSON.parse(prepSeal).files;if(prepRows.length!==86)throw Error('Preparation membership');
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
 ['windows-interrupted-owner-native-proposal01','preparation'],
 ['interrupted-owner-native-instrument-peer-review01','prior-source-review'],
 ['interrupted-native-run01-launcher-diagnosis01','launcher-diagnosis'],
 ['interrupted-native-run01-peer-diagnosis01','peer-diagnosis'],
 ['interrupted-native-run01-source-diagnosis01','source-diagnosis']
])tree(path.join(scratch,dir),label);
const run=path.join(scratch,'windows-interrupted-owner-retirement01');
const sourceMap=JSON.parse(fs.readFileSync(path.join(run,'SOURCE-INPUTS.json')));
const sourceNames=Object.keys(sourceMap.source_sha256);
if(sourceNames.length!==29||sourceNames.some(n=>path.basename(n)!==n||!n.endsWith('.py')))throw Error('29 exact source texts');
for(const name of sourceNames){const p=path.join(run,name);if(sha(fs.readFileSync(p))!==sourceMap.source_sha256[name])throw Error('Copied source mismatch '+name);copy(p,'run-saved/'+name);}
for(const name of ['before.json','after.json','exit.json','native-exit.json','controller-result.json','contender-result.json','child-receipt-observation.json','closed-journal-observation.json','interrupted-journal-observation.json','controller-stdout.log','controller-stderr.log','ROOT-ADMISSION.json','SOURCE-INPUTS.json','run_interrupted_owner01.ps1'])copy(path.join(run,name),'run-saved/'+name);
for(const suffix of ['ACTUAL','INVENTORY-ACTUAL','RECEIPTS-ACTUAL','CURRENT-CONTRACT-ACTUAL','WRITE-PREDICATE-ACTUAL','RETAINED-OBSERVATION-ACTUAL','DIAGNOSTIC-REVIEW-ACTUAL','PEER-VERDICT-READ-ACTUAL']){const name='INTERRUPTED-NATIVE-RUN01-'+suffix+'.json';copy(path.join(scratch,name),'root-actuals/'+name);}
for(const name of ['ASTRA-NATIVE-INTERRUPTED-OWNER01-ADMISSION-2026-09-14.md','INTERRUPTED-OWNER-NATIVE-SOURCE-BRIEF-2026-09-14.md','INTERRUPTED-OWNER-PRELOCK-REPAIR-BRIEF-2026-09-14.md','ASTRA-INTERRUPTED-NATIVE01-FAILURE-2026-09-14.md'])copy(path.join(root,'docs/library',name),'contracts/'+name);
copy(path.join(scratch,'archive-interrupted-native-run01-failure.mjs'),'archive-interrupted-native-run01-failure.mjs');
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});
rows.sort((a,b)=>a.path.localeCompare(b.path));
const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'FAILED native observation 3c41aa, frozen preparation and saved text receipts, passive diagnoses. No physical journal, support, generated fixture, checkpoint or D2 output access for archive; no rerun.',files:rows},null,2)+'\n');
fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal)}));
