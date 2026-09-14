import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library', scratch=path.join(root,'_scratch');
const rel='docs/library/proof/interrupted-owner-native01-root-integration-2026-09-14',out=path.join(root,rel);
if(fs.existsSync(out))throw Error('Fresh root archive');
const names=['INTERRUPTED-NATIVE01-ARCHIVE-COPY-ACTUAL.json','INTERRUPTED-NATIVE01-INTEGRATION-ACTUAL.json','INTERRUPTED-NATIVE01-TRANSPORT-INDEX-ACTUAL.json','INTERRUPTED-NATIVE01-INDEX-POLL01-ACTUAL.json','INTERRUPTED-NATIVE01-TRANSPORT-RESULT.json','integrate-interrupted-native01-failure.ps1','restore-interrupted-native01-transport.mjs','interrupted-native01-apply.stdout.log','interrupted-native01-apply.stderr.log','archive-interrupted-native01-integration.mjs'];
const done=JSON.parse(fs.readFileSync(path.join(scratch,'INTERRUPTED-NATIVE01-INDEX-POLL01-ACTUAL.json')));
if(done.exit_code!==0||done.session_id||!done.output.includes('payloads_matching_disk_and_git'))throw Error('Completed main index result');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),rows=[];
fs.mkdirSync(out);
for(const name of names){const p=path.join(scratch,name),s=fs.lstatSync(p);if(!s.isFile()||s.isSymbolicLink())throw Error('Plain source');const b=fs.readFileSync(p);fs.writeFileSync(path.join(out,name),b,{flag:'wx'});rows.push({path:name,bytes:b.length,sha256:sha(b)});}
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});rows.sort((a,b)=>a.path.localeCompare(b.path));
const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'Raw Git diff/application, anticipated newline-only transport restoration and completed raw Git-index verification for FAILED native01 archive. No subject rerun.',files:rows},null,2)+'\n');fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal)}));
