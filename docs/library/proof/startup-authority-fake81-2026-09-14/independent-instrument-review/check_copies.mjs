// Passive comparison of the two fixed source copies. No subject imports/writes.
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/';
const source=root+'startup-authority-qualification-proposal01/';
const read=(dir,name)=>readFileSync(dir+name),sha=b=>createHash('sha256').update(b).digest('hex');
const need=(v,m)=>{if(!v)throw Error(m)};
const sourcePins=read(source,'PINS.json'),pins=JSON.parse(sourcePins);
need(sha(sourcePins)==='47af697a62dcead062f8c2771aad550ebd194392665f85a9a9f3face60551fb8','source pins');
const sourceLauncher=read(source,'run_preflight01.ps1');
const oldLabel='startup-authority-fake01',newLabel='startup-authority-confirmation01';
need(sourceLauncher.toString('utf8').split(oldLabel).length-1===5,'five original label strings');
const expectedConfirmation=Buffer.from(sourceLauncher.toString('utf8').replaceAll(oldLabel,newLabel),'utf8');
const rows=[];
for(const spec of [
 ['author','startup-authority-fake81-author01',oldLabel,'47af697a62dcead062f8c2771aad550ebd194392665f85a9a9f3face60551fb8'],
 ['confirmation','startup-authority-fake81-confirmation01',newLabel,'963d1a5fbdc2cb89e14df155575767e1b9eeb2a28003a701c25d1b5b60781f31']
]){
 const [role,folder,label,digest]=spec,dir=root+folder+'/',bytes=read(dir,'PINS.json'),copyPins=JSON.parse(bytes);
 need(sha(bytes)===digest&&copyPins.files.length===27,'copy pins');
 const expectedPins=JSON.parse(sourcePins);
 if(role==='confirmation'){
  const row=expectedPins.files.find(r=>r.path==='run_preflight01.ps1');
  row.bytes=expectedConfirmation.length;row.sha256=sha(expectedConfirmation);
 }else need(bytes.equals(sourcePins),'author exact pins bytes');
 need(JSON.stringify(copyPins)===JSON.stringify(expectedPins),'only corresponding launcher pin changes');
 for(const row of copyPins.files){
  need(/^[A-Za-z0-9_.-]+$/.test(row.path),'flat input');
  const actual=read(dir,row.path),expected=role==='confirmation'&&row.path==='run_preflight01.ps1'?expectedConfirmation:read(source,row.path);
  need(actual.equals(expected)&&actual.length===row.bytes&&sha(actual)===row.sha256,'copy input '+row.path);
 }
 const template=JSON.parse(read(dir,'ROOT-ADMISSION.template.json'));
 need(template.approved===false&&template.label===label&&template.pins_sha256===digest&&template.scope==='generated_bytes_and_fake_ports_only','copy false template');
 need(!existsSync(dir+'ROOT-ADMISSION.json')&&!existsSync(dir+label),'no actual admission/run at check');
 rows.push({role,pins_sha256:digest,inputs:27,child_texts_unchanged:23,launcher_sha256:sha(read(dir,'run_preflight01.ps1')),label_replacements:role==='confirmation'?5:0,template_false:true,admission_and_run_absent:true});
}
console.log(JSON.stringify({scope:'passive fixed source copies only',status:'PASS',copies:rows},null,2));
