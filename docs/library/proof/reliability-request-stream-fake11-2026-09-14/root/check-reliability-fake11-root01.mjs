import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const source=path.join(root,'_scratch/reliability-request-stream-fake11-author01');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const pb=fs.readFileSync(path.join(source,'PINS.json'));
if(sha(pb)!=='f8685dc37bfc8be1b2021e243d08546e45c2270c619dd6aca4cea8ffeb2f440a')throw Error('Exact reviewed map');
const pins=JSON.parse(pb);
if(!pins.finalized||pins.files.length!==13||new Set(pins.files.map(r=>r.path)).size!==13)throw Error('Exact finalized13');
for(const r of pins.files){if(!/^[A-Za-z0-9_.-]+$/.test(r.path))throw Error('Flat path');const p=path.join(source,r.path),s=fs.lstatSync(p);if(!s.isFile()||s.isSymbolicLink())throw Error('Plain input');const b=fs.readFileSync(p);if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error('Pin '+r.path);}
const ids=JSON.parse(fs.readFileSync(path.join(source,'EXPECTED-CASES.json'),'utf8'));
if(ids.length!==11||new Set(ids).size!==11)throw Error('Eleven IDs');
const peer=fs.readFileSync(path.join(root,'_scratch/reliability-request-stream-peer01/VERDICT.md'));
if(sha(peer)!=='ca17c27ac237b1cad73d69aea9a743f6b352c1b35b98ea925028892eced2c80d')throw Error('Peer');
const template=JSON.parse(fs.readFileSync(path.join(source,'ROOT-ADMISSION.template.json'),'utf8'));
if(template.approved!==false||fs.existsSync(path.join(source,'ROOT-ADMISSION.json'))||fs.existsSync(path.join(source,'reliability-request-stream-fake01')))throw Error('Fresh unadmitted invocation');
console.log(JSON.stringify({scope:'Root passive source/control check, no invocation',pins_sha256:sha(pb),pins:13,bytes:pins.files.reduce((n,r)=>n+r.bytes,0),expected_ids:ids,peer_sha256:sha(peer),template_false:true,fresh:true}));
