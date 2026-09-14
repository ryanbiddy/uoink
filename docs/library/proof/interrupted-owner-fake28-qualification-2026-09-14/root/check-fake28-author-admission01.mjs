import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const dir=path.join(root,'_scratch/interrupted-retirement-fake28-author01');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const read=p=>fs.readFileSync(p);
const raw=read(path.join(dir,'PINS.json'));
if(sha(raw)!=='eb108b71b9f2a7d10db57efb2aa92b7b8df20a25bf44923ca273f456ab753bc1')throw Error('map changed');
const pins=JSON.parse(raw);
if(pins.finalized!==true||pins.files.length!==38||new Set(pins.files.map(r=>r.path)).size!==38)throw Error('closure');
for(const r of pins.files){if(!/^[A-Za-z0-9_.-]+$/.test(r.path))throw Error('flat input');const b=read(path.join(dir,r.path));if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error(r.path);}
const src=JSON.parse(read(path.join(root,'_scratch/interrupted-retirement-fake28-preparation01/SOURCE-ROWS.pending.json')));
for(const r of [...src.frozen_rows,...src.pending_rows]){const b=read(r.source_path);if(!b.equals(read(path.join(dir,r.path))))throw Error('source copy '+r.path);}
const q=read(path.join(dir,'qualify_windows_reservations.py')).toString();
const m=q.match(/^MODULES = \(([^\n]+)\)$/m);
if(!m)throw Error('literal modules');
const names=JSON.parse('['+m[1]+']');
if(JSON.stringify(names)!==JSON.stringify(src.modules)||names.length!==33)throw Error('module closure');
const child=[...names.map(n=>n+'.py'),'qualify_windows_reservations.py','EXPECTED-CASES.json'];
const expected=JSON.parse(read(path.join(dir,'EXPECTED-CASES.json')));
if(expected.length!==28||new Set(expected).size!==28)throw Error('selection');
const old22=JSON.parse(read(path.join(root,'docs/library/proof/retired-owner-recovery-qualification-2026-09-13/proposal/EXPECTED-CASES.json')));
if(JSON.stringify(expected.slice(0,22))!==JSON.stringify(old22))throw Error('original selection');
const test=read(path.join(dir,'test_interrupted_owner_retirement.py')).toString();
const ids=[...test.matchAll(/^    def (test_[A-Za-z0-9_]+)\(self\):/gm)].map(m=>'test_interrupted_owner_retirement.InterruptedOwnerRetirementContracts.'+m[1]).sort();
if(ids.length!==6||JSON.stringify(ids)!==JSON.stringify(expected.slice(22)))throw Error('new selection');
if(fs.existsSync(path.join(dir,'ROOT-ADMISSION.json'))||fs.existsSync(path.join(dir,'interrupted-retirement-fake01')))throw Error('premature admission/output');
console.log(JSON.stringify({pins_sha256:sha(raw),payload_count:38,bytes:pins.files.reduce((n,r)=>n+r.bytes,0),source_copies:33,child_inputs:child.length,original22_unchanged:true,old_test_modules:src.frozen_rows.filter(r=>r.path.startsWith('test_')).map(r=>r.path),exact28_selection:true,actual_admission:false,execution:false}));
