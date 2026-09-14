import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',scratch=path.join(root,'_scratch');
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e6133b1f-fc8/gemini';
const rel='docs/library/proof/reliability-request-stream-fake11-2026-09-14',out=path.join(work,rel);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
if(fs.existsSync(out))throw Error('Fresh archive');
const dirs=[['reliability-request-stream-proposal01','proposal'],['reliability-request-stream-fake11-author01','author'],['reliability-request-stream-fake11-independent01','independent'],['reliability-request-stream-peer01','source-peer'],['reliability-request-stream-receipt-peer01','receipt-peer']];
const rows=[];
function put(from,target){const st=fs.lstatSync(from);if(!st.isFile()||st.isSymbolicLink())throw Error('Plain documentary file');if(!(/\.(py|ps1|mjs|json|md|txt|diff|log)$/.test(from)||path.basename(from)==='.gitattributes'))throw Error('Documentary extension '+from);const b=fs.readFileSync(from);fs.mkdirSync(path.dirname(path.join(out,target)),{recursive:true});fs.writeFileSync(path.join(out,target),b,{flag:'wx'});rows.push({path:target,bytes:b.length,sha256:sha(b)});}
function walk(source,target){for(const e of fs.readdirSync(source,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){if(e.isSymbolicLink())throw Error('Symlink');if(e.isDirectory())walk(path.join(source,e.name),target+'/'+e.name);else put(path.join(source,e.name),target+'/'+e.name);}}
function checkMap(dir,name,expected){const raw=fs.readFileSync(path.join(scratch,dir,name));if(sha(raw)!==expected)throw Error('Exact map '+dir);for(const r of JSON.parse(raw).files){if(path.isAbsolute(r.path)||r.path.split('/').includes('..'))throw Error('Relative source');const b=fs.readFileSync(path.join(scratch,dir,r.path));if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error('Source changed '+r.path);}}
checkMap('reliability-request-stream-proposal01','PROPOSAL-PINS.json','cdfb1c7927c2fa65a89cdec726b8535b3a17798e0158e1619e731f72a38bb1a0');
checkMap('reliability-request-stream-fake11-author01','PINS.json','f8685dc37bfc8be1b2021e243d08546e45c2270c619dd6aca4cea8ffeb2f440a');
checkMap('reliability-request-stream-fake11-independent01','PINS.json','c784392df7dc910d47656ff32bb13ecbee179431070eade5adf0951679b87a66');
for(const [dir,label] of dirs)walk(path.join(scratch,dir),label);
for(const name of fs.readdirSync(scratch).filter(n=>/^RELIABILITY-FAKE11-[A-Z0-9-]+\.json$/.test(n)).sort())put(path.join(scratch,name),'root/'+name);
for(const name of ['check-reliability-fake11-root01.mjs','check-reliability-fake11-independent01.mjs','check-reliability-fake11-results01.mjs','archive-reliability-fake11.mjs','CONSTRUCTOR01-FAILURE-ARCHIVE-ACTUAL.json','CONSTRUCTOR01-FAILURE-INTEGRATION-ACTUAL.json','CONSTRUCTOR01-FAILURE-INDEX-ACTUAL.json','CONSTRUCTOR01-FAILURE-COMMIT-ACTUAL.json','CONSTRUCTOR01-FAILURE-TRANSPORT-RESULT.json'])put(path.join(scratch,name),'root/'+name);
for(const name of ['ASTRA-RELIABILITY-FAKE11-ADMISSION-2026-09-14.md','ASTRA-RELIABILITY-FAKE11-CONFIRMATION-ADMISSION-2026-09-14.md','ASTRA-RELIABILITY-FAKE11-VERDICT-2026-09-14.md'])put(path.join(root,'docs/library',name),'contracts/'+name);
const attrs=Buffer.from('* -text\n');fs.writeFileSync(path.join(out,'.gitattributes'),attrs,{flag:'wx'});rows.push({path:'.gitattributes',bytes:attrs.length,sha256:sha(attrs)});rows.sort((a,b)=>a.path.localeCompare(b.path));
const seal=Buffer.from(JSON.stringify({schema:'documentary-proof-v1',scope:'Both eleven-case inert caller qualifications, preserved source/preparation reviews, exact original outcomes and prior constructor failure transport records. No production/model/release acceptance.',files:rows},null,2)+'\n');fs.writeFileSync(path.join(out,'SHA256.json'),seal,{flag:'wx'});
console.log(JSON.stringify({proof:rel,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),manifest_sha256:sha(seal)}));
