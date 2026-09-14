import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',scratch=path.join(root,'_scratch');
const rel='docs/library/proof/interrupted-owner-native02-root-integration-2026-09-14',out=path.join(root,rel);
const actual=JSON.parse(fs.readFileSync(path.join(scratch,'INTERRUPTED-NATIVE02-INDEX-POLL01-ACTUAL.json')));
if(actual.exit_code!==0||actual.session_id||!actual.output.includes('payloads_matching_disk_and_git'))throw Error('Completed index proof');
if(fs.existsSync(out))throw Error('Fresh root archive');
const names=['INTERRUPTED-NATIVE02-ARCHIVE-COPY-ACTUAL.json','INTERRUPTED-NATIVE02-INTEGRATION-ACTUAL.json','INTERRUPTED-NATIVE02-TRANSPORT-INDEX-ACTUAL.json','INTERRUPTED-NATIVE02-INDEX-POLL01-ACTUAL.json','INTERRUPTED-NATIVE02-TRANSPORT-RESULT.json','integrate-interrupted-native02-accepted.ps1','restore-interrupted-native02-transport.mjs','interrupted-native02-apply.stdout.log','interrupted-native02-apply.stderr.log','archive-native02-root-integration.mjs'];
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),rows=[];
fs.mkdirSync(out);
for(const name of names){const source=path.join(scratch,name);const st=fs.lstatSync(source);if(!st.isFile()||st.isSymbolicLink())throw Error('Plain file required');const b=fs.readFileSync(source);fs.writeFileSync(path.join(out,name),b,{flag:'wx'});rows.push({path:name,bytes:b.length,sha256:sha(b)});}
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});
rows.sort((a,b)=>a.path.localeCompare(b.path));
const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'Native02 raw worktree diff/application, verified newline-only transport restoration and completed disk/index proof. No native rerun.',files:rows},null,2)+'\n');
fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal)}));
