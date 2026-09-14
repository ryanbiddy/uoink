import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/asr-completion-info-fake59-author01';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const raw=fs.readFileSync(path.join(root,'PINS.json'));if(sha(raw)!=='3ab4293cfd48e9652029bd7c2de42269b57499c7c46d95cfd9f659db4a6099f1')throw Error('Final nine-input map');
const pins=JSON.parse(raw);if(pins.finalized!==true||pins.files.length!==9||new Set(pins.files.map(r=>r.path)).size!==9)throw Error('Finalized nine');
for(const r of pins.files){if(!/^[A-Za-z0-9_.-]+$/.test(r.path))throw Error('Flat source');const p=path.join(root,r.path),st=fs.lstatSync(p);if(!st.isFile()||st.isSymbolicLink())throw Error('Plain source');const b=fs.readFileSync(p);if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error('Pin '+r.path);}
const template=JSON.parse(fs.readFileSync(path.join(root,'ROOT-ADMISSION.template.json')));
if(template.approved!==false||template.pins_sha256!==sha(raw)||fs.existsSync(path.join(root,'ROOT-ADMISSION.json'))||fs.existsSync(path.join(root,'asr-completion-info-fake59-01')))throw Error('Fresh false author');
console.log(JSON.stringify({scope:'Final root binding only',pins_sha256:sha(raw),inputs:9,bytes:pins.files.reduce((n,r)=>n+r.bytes,0),finalized:true,template_false:true,fresh:true}));
