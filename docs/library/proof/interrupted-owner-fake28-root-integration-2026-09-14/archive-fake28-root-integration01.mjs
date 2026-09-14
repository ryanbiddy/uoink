import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library', scratch=path.join(root,'_scratch');
const rel='docs/library/proof/interrupted-owner-fake28-root-integration-2026-09-14',out=path.join(root,rel);
if(fs.existsSync(out))throw Error('fresh root record');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const names=['INTERRUPTED-FAKE28-ARCHIVE-COPY-ACTUAL.json','INTERRUPTED-FAKE28-PROOF-INTEGRATION-ACTUAL.json','INTERRUPTED-FAKE28-TRANSPORT-CHECK-ACTUAL.json','INTERRUPTED-FAKE28-TRANSPORT-REPAIR02.md','INTERRUPTED-FAKE28-TRANSPORT-REPAIR-ACTUAL.json','INTERRUPTED-FAKE28-TRANSPORT-RECHECK-ACTUAL.json','FAKE28-TRANSPORT-REPAIR02-RESULT.json','interrupted-fake28-apply01.stdout.log','interrupted-fake28-apply01.stderr.log','integrate-fake28-proof01.ps1','check-fake28-transport01.mjs','restore-fake28-transport02.mjs','archive-fake28-root-integration01.mjs'];
const indexes=fs.readdirSync(scratch).filter(n=>/^INTERRUPTED-FAKE28-PROOF-INDEX(?:-POLL\d+)?-ACTUAL\.json$/.test(n)).sort();
if(indexes.length===0)throw Error('missing actual index verification');
const terminal=indexes.map(n=>JSON.parse(fs.readFileSync(path.join(scratch,n)))).find(r=>r.exit_code===0&&!r.session_id&&r.output.includes('payloads_matching_disk_and_git'));
if(!terminal)throw Error('no completed index result');
names.push(...indexes);
fs.mkdirSync(out);const rows=[];
for(const name of names){const p=path.join(scratch,name),s=fs.lstatSync(p);if(!s.isFile()||s.isSymbolicLink())throw Error('plain file');const b=fs.readFileSync(p);fs.writeFileSync(path.join(out,name),b,{flag:'wx'});rows.push({path:name,bytes:b.length,sha256:sha(b)});}
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});rows.sort((a,b)=>a.path.localeCompare(b.path));
const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'Root documentary integration, original failed newline transport check, exact donor-byte restoration and completed Git-index verification; no subject rerun.',files:rows},null,2)+'\n');fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal)}));
