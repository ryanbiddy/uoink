import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const old=path.join(root,'_scratch/controller-custody-fake10-author01');
const dest=path.join(root,'_scratch/controller-custody-final02');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const read=p=>fs.readFileSync(p);
const json=p=>JSON.parse(read(p));
const check=(b,m)=>{if(!b)throw Error(m)};
const write=(n,b)=>fs.writeFileSync(path.join(dest,n),b,{flag:'wx'});
const pins=json(path.join(old,'PINS.json'));
check(sha(read(path.join(old,'PINS.json')))==='25f302701d5ae62e481c0217338a84ff6eaef3febff54ca1458ea9ee28283d2a','Original pins');
const patch=read(path.join(root,'docs/library/proof/controller-custody10-failed-2026-09-14/test-contract-diagnosis/PROPOSED-EXPECTATIONS.UNAPPLIED.patch.txt'));
check(sha(patch)==='f1c8950dfbe84ddbeb5838cdc518a25a2c5eaed2011802ea8dab7e1c25aa4e8a','Approved patch');
fs.mkdirSync(dest);
const changes=[];
for(const row of pins.files){
  let b=read(path.join(old,row.path));
  check(b.length===row.bytes&&sha(b)===row.sha256,'Original '+row.path);
  if(row.path==='test_controller_resume_publication.py'){
    let s=b.toString('utf8');const lines=s.split('\n');
    check(lines[127].trim()==='with self.assertRaises(REFUSALS) as caught:','Line128');
    check(lines[299].trim()==='self.fail_start(f)','Line300');
    lines[127]=lines[127].replace('self.assertRaises(REFUSALS)','self.assertRaises(SessionClosed if fault == "wrong_permit" else REFUSALS)');
    lines[299]=lines[299].replace('self.fail_start(f)','self.fail_start(f, SessionClosed if fault == "active" else REFUSALS)');
    b=Buffer.from(lines.join('\n'));
  } else if(row.path==='run_preflight01.ps1'){
    const s=b.toString('utf8');check(s.split('controller-custody-fake01').length===6,'Five label literals');
    b=Buffer.from(s.replaceAll('controller-custody-fake01','controller-custody-final02'));
  } else if(row.path==='BRIEF.md'){
    b=Buffer.from('Controller10 final closure, 2026-09-15. Ryan approves only patch f1c8950dfbe84ddbeb5838cdc518a25a2c5eaed2011802ea8dab7e1c25aa4e8a. Original run6ba3f1 remains 8 passed, 2 failed, 0 skipped, with102/104 passing subtests. The two selected faults correctly raise SessionClosed; all fault inputs and subsequent assertions remain unchanged.\n\nApply the exact two-line exception correction, then invoke this fresh copy once using its unchanged qualifier and ten ordered cases. Expected104 subtests are source expectations until observed. All eight other modules and EXPECTED-CASES remain byte-identical. Launcher changes only its five output/admission labels. The source map updates the changed test binding and records this derivative.\n\nRoot must verify these deltas and PINS before admitting. Use C:\\Python314\\python.exe -I -S -B with IG_FORBIDDEN_LIVE set before outer startup. Preserve immediate child/outer exits, input checks, complete cases and guards. No retry or confirmation run. Freeze after the result, including failure. No native, runtime-owner, journal, model, D3/D4 or fake-stack continuation. No production migration or release qualification follows.\n');
  } else if(row.path==='QUALIFICATION-PROTOCOL.md'){
    b=Buffer.from('Ryan\'s 2026-09-15 instruction supersedes the old two-copy protocol: one invocation only, then freeze regardless of result. The unchanged qualifier and fixed launcher receipt checks govern execution. No confirmation or compatibility follow-up is authorized.\n\n'+b.toString('utf8').split('After separate root review and admission, each fresh copy')[0]+'After root review and admission, invoke this one fresh copy with C:\\Python314\\python.exe -I -S -B. Set IG_FORBIDDEN_LIVE before the outer host. Preserve all15 input bindings and3 controls, immediate child exit, full ordered cases/subtests, ten guards and23 output files. An observed pass requires10/0/0, all104 subtests passing, empty denials/stderr, no heavy roots, unchanged bytes and actual outer/child exits0. A failure remains a failure; do not rerun. The original protocol and result remain archived in controller-custody10-failed-2026-09-14.\n');
  } else if(row.path==='SOURCE-INPUTS.json'){
    const map=JSON.parse(b);const test=read(path.join(dest,'test_controller_resume_publication.py'));
    map.checkpoint='Ryan-approved final Controller10 closure, 2026-09-15';
    map.modules[8]={...map.modules[8],path:path.join(dest,'test_controller_resume_publication.py'),bytes:test.length,sha256:sha(test)};
    map.final_closure={approved_patch_sha256:sha(patch),original_pins_sha256:sha(read(path.join(old,'PINS.json'))),run_label:'controller-custody-final02',invocations:1,freeze_after:true};
    b=Buffer.from(JSON.stringify(map,null,2)+'\n');
  }
  write(row.path,b);if(sha(b)!==row.sha256)changes.push({path:row.path,before:row.sha256,after:sha(b)});
}
const next={...pins,files:pins.files.map(r=>{const b=read(path.join(dest,r.path));return{path:r.path,bytes:b.length,sha256:sha(b)}})};
write('PINS.json',JSON.stringify(next,null,2)+'\n');
write('PREPARATION.json',JSON.stringify({approved_patch_sha256:sha(patch),source:old,destination:dest,changes,pins_sha256:sha(read(path.join(dest,'PINS.json'))),subject_invoked:false},null,2)+'\n');
console.log(JSON.stringify({destination:dest,changes,pins_sha256:sha(read(path.join(dest,'PINS.json')))},null,2));
