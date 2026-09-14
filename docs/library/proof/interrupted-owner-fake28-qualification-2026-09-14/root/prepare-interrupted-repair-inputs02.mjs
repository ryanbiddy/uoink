import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/31e8890c-ab8/gemini';
const out=path.join(root,'_scratch/interrupted-owner-retirement-repair02');
if(fs.existsSync(out)) throw new Error('fresh source repair output required');
fs.mkdirSync(out);
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const baseline=JSON.parse(fs.readFileSync(path.join(root,'docs/library/proof/interrupted-owner-retirement-direction-2026-09-13/corrected/INPUTS.json'),'utf8'));
const inputs=[];
for(const row of baseline.inputs){const file=path.join(root,row.path);const b=fs.readFileSync(file);if(b.length!==row.bytes||hash(b)!==row.sha256)throw new Error(row.id);inputs.push({...row,path:file});}
const failed=JSON.parse(fs.readFileSync(path.join(root,'_scratch/interrupted-retirement-root-provenance01/SOURCE-BINDINGS.json'),'utf8'));
for(const row of failed.outputs){const file=path.join(work,'_scratch/interrupted-owned-session-retirement-implementation01',row.path);const b=fs.readFileSync(file);if(b.length!==row.bytes||hash(b)!==row.sha256)throw new Error(row.path);inputs.push({...row,id:'F'+String(inputs.length-15).padStart(2,'0'),path:file,role:'rejected source proposal; never execute'});}
for(const name of ['generated_native_owner_fixture.py','generated_unit_cases.py','connection_cases.py','native_owner_cases.py','generated_bootstrap_fixture.py','generated_factory_fixture.py']){
 const file=path.join(root,'docs/library/proof/runtime-owner-native-fake33-2026-09-13/author-preparation',name);const b=fs.readFileSync(file);
 inputs.push({id:'C'+String(inputs.length-24).padStart(2,'0'),path:file,bytes:b.length,sha256:hash(b),role:'qualified fake connection source context only; preserve originals'});
}
const doc={schema:'interrupted-owner-source-repair-inputs-v2',brief:'docs/library/INTERRUPTED-OWNER-SOURCE-REPAIR-BRIEF-2026-09-14.md',execution_admitted:false,inputs};
const raw=JSON.stringify(doc,null,2)+'\n';fs.writeFileSync(path.join(out,'INPUTS.json'),raw,{flag:'wx'});fs.writeFileSync(path.join(out,'.gitattributes'),'* -text\n',{flag:'wx'});
console.log(JSON.stringify({inputs:inputs.length,bytes:inputs.reduce((s,x)=>s+x.bytes,0),map_sha256:hash(Buffer.from(raw)),output:out,candidate_execution:false}));
