import fs from 'node:fs';import crypto from 'node:crypto';import path from 'node:path';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',dir=path.join(root,'_scratch/controller-custody-final02'),old=path.join(root,'_scratch/controller-custody-fake10-author01');
const read=p=>fs.readFileSync(p),sha=b=>crypto.createHash('sha256').update(b).digest('hex'),assert=(v,m)=>{if(!v)throw Error(m)};
const raw=read(path.join(dir,'PINS.json')),pins=JSON.parse(raw),prior=JSON.parse(read(path.join(old,'PINS.json')));
assert(sha(raw)==='488a1a4223e7885fe108a3bb375512306291681fcb45018c0e0e8a658940e39b','PINS');
for(const row of pins.files){const b=read(path.join(dir,row.path));assert(sha(b)===row.sha256&&b.length===row.bytes,'Binding '+row.path)}
const changed=pins.files.filter(r=>r.sha256!==prior.files.find(p=>p.path===r.path).sha256).map(r=>r.path);
assert(JSON.stringify(changed)===JSON.stringify(['test_controller_resume_publication.py','run_preflight01.ps1','BRIEF.md','QUALIFICATION-PROTOCOL.md','SOURCE-INPUTS.json']),'Change membership');
const exact=JSON.parse(read(path.join(root,'_scratch/CONTROLLER-FINAL02-EXACT-DIFF-ACTUAL.json')));
const patch=read(path.join(root,'docs/library/proof/controller-custody10-failed-2026-09-14/test-contract-diagnosis/PROPOSED-EXPECTATIONS.UNAPPLIED.patch.txt')).toString('utf8');
const hunks=s=>s.slice(s.indexOf('@@')).replaceAll('\r\n','\n').trim();
assert(exact.exit_code===1&&hunks(exact.output)===hunks(patch),'Exact approved hunks');
assert(read(path.join(dir,'run_preflight01.ps1')).toString().replaceAll('controller-custody-final02','controller-custody-fake01')===read(path.join(old,'run_preflight01.ps1')).toString(),'Launcher label-only');
const map=JSON.parse(read(path.join(dir,'SOURCE-INPUTS.json')));assert(map.final_closure.invocations===1&&map.final_closure.freeze_after===true,'Single-run bound');
for(const m of map.modules){const row=pins.files.find(r=>r.path===m.module+'.py');assert(row.bytes===m.bytes&&row.sha256===m.sha256,'Module map')}
assert(!fs.existsSync(path.join(dir,'controller-custody-final02')),'Fresh output');
const admission={approved:true,label:'controller-custody-final02',pins_sha256:sha(raw),scope:'generated_bytes_and_fake_ports_only',authority:'Ryan 2026-09-15; decisions d7d8c1c; exact approved patch f1c8950d',invocations:1,freeze_after:true};
fs.writeFileSync(path.join(dir,'ROOT-ADMISSION.json'),JSON.stringify(admission,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({admitted:true,...admission,changed},null,2));
