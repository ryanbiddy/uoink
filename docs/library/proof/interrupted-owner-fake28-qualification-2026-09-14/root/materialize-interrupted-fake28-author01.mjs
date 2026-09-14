import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const pending=path.join(root,'_scratch/interrupted-retirement-fake28-preparation01');
const repair=path.join(root,'_scratch/interrupted-owner-retirement-repair02');
const out=path.join(root,'_scratch/interrupted-retirement-fake28-author01');
if(fs.existsSync(out))throw new Error('fresh author preparation required');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const pins=JSON.parse(fs.readFileSync(path.join(pending,'PINS.json'),'utf8'));
if(pins.finalized!==false||pins.files.length!==38)throw new Error('expected pending map');
const frozen=JSON.parse(fs.readFileSync(path.join(root,'_scratch/interrupted-repair02-root-preservation.json'),'utf8')).files;
const rows=[];const data=[];
for(const row of pins.files){
 if(!/^[A-Za-z0-9_.-]+$/.test(row.path))throw new Error('flat input');
 const current=frozen.find(x=>x.path===row.path);
 let raw;
 if(current){if(row.status!=='pending_author_freeze'||row.bytes!==null||row.sha256!==null)throw new Error('exact pending row');raw=fs.readFileSync(path.join(repair,row.path));if(raw.length!==current.bytes||sha(raw)!==current.sha256)throw new Error('frozen repair '+row.path);}
 else {raw=fs.readFileSync(path.join(pending,row.path));if(raw.length!==row.bytes||sha(raw)!==row.sha256)throw new Error('inherited pin '+row.path);}
 if(row.path==='BRIEF.md')raw=fs.readFileSync(path.join(root,'docs/library/INTERRUPTED-OWNER-FAKE28-QUALIFICATION-BRIEF-2026-09-14.md'));
 if(row.path==='QUALIFICATION-PROTOCOL.md'){
  const text=raw.toString('utf8');const before='2026-09-14. Unexecuted preparation; admission is false and four source rows remain pending.';
  if(!text.includes(before))throw new Error('protocol pending line');
  raw=Buffer.from(text.replace(before,'2026-09-14. Final source preparation; all four reviewed repair inputs are bound. Actual admission remains separate and absent until root writes it.'));
 }
 data.push({path:row.path,raw});rows.push({...row,bytes:raw.length,sha256:sha(raw),status:current?'frozen_repaired':row.status});
}
if(frozen.length!==4||rows.some(x=>x.status==='pending_author_freeze'))throw new Error('complete final closure');
fs.mkdirSync(out);
for(const d of data)fs.writeFileSync(path.join(out,d.path),d.raw,{flag:'wx'});
const finalRaw=Buffer.from(JSON.stringify({...pins,finalized:true,files:rows},null,2)+'\n');
fs.writeFileSync(path.join(out,'PINS.json'),finalRaw,{flag:'wx'});
fs.writeFileSync(path.join(out,'.gitattributes'),'* -text\n',{flag:'wx'});
const note={approved:false,label:'interrupted-retirement-fake01',pins_sha256:sha(finalRaw),scope:'generated_bytes_and_fake_ports_only',note:'Finalized sources only; actual root admission is still absent.'};
fs.writeFileSync(path.join(out,'ROOT-ADMISSION.template.json'),JSON.stringify(note,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({output:out,payloads:rows.length,bytes:rows.reduce((s,r)=>s+r.bytes,0),pins_sha256:sha(finalRaw),repaired_inputs:frozen,launcher_sha256:rows.find(x=>x.path==='run_preflight01.ps1').sha256,qualifier_sha256:rows.find(x=>x.path==='qualify_windows_reservations.py').sha256,actual_admission:false,candidate_execution:false}));
