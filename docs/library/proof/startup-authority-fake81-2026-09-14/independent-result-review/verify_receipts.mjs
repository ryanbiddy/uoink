// Passive verification of fixed saved text receipts only. No subject imports.
import {readFileSync,readdirSync,lstatSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,sep} from 'node:path';
const root='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/';
const own=root+'startup81-results-peer01/',origin=root+'startup-authority-qualification-proposal01/';
const need=(v,m)=>{if(!v)throw Error(m)};
const hash=b=>createHash('sha256').update(b).digest('hex');
const exact=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const sorted=a=>[...a].sort();
const keys=(o,k)=>exact(sorted(Object.keys(o)),sorted(k));
function read(dir,name){need(/^[A-Za-z0-9_.-]+$/.test(name),'flat text name');const p=resolve(dir,name);need(p.startsWith(resolve(dir)+sep),'bounded path');const s=lstatSync(p);need(s.isFile()&&!s.isSymbolicLink()&&s.size<=1048576,'bounded plain text');return readFileSync(p)}
const json=(dir,name)=>JSON.parse(read(dir,name));
const binding=b=>({bytes:b.length,sha256:hash(b)});
const expected=json(origin,'EXPECTED-CASES.json');
need(expected.length===81&&new Set(expected).size===81,'frozen81 membership');
need(hash(read(origin,'EXPECTED-CASES.json'))==='2dc0ec32738188ece925603d823ae04767f8255ae67b68038014cb65b244c0f2','expected pin');
const oldIds=json(root+'windows-reservation-implementation-proposal02/','EXPECTED-CASES.json');
const newIds=json(root+'real-startup-authority-repair01/','EXPECTED-CASES.json').cases;
need(oldIds.length===65&&newIds.length===16&&exact(expected,[...oldIds,...newIds]),'original65+16');
const relation=json(root,'STARTUP81-COPY-RELATION.json');
const guardNames=['startup_bound','content_reads_closed','audit_identity_unchanged','metadata_traps_installed','baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed','captures_installed','capture_valid','real_entrypoints_unchanged'];
const controls=['PINS.json','ROOT-ADMISSION.json','run_preflight01.ps1'];
const summaries=[],results=[];
for(const [role,folder,label,actualName,chunk,pin] of [
 ['author','startup-authority-fake81-author01','startup-authority-fake01','STARTUP81-AUTHOR-RUN-ACTUAL.json','28a03e','47af697a62dcead062f8c2771aad550ebd194392665f85a9a9f3face60551fb8'],
 ['confirmation','startup-authority-fake81-confirmation01','startup-authority-confirmation01','STARTUP81-CONFIRMATION-RUN-ACTUAL.json','9a8704','963d1a5fbdc2cb89e14df155575767e1b9eeb2a28003a701c25d1b5b60781f31']
]){
 const source=root+folder+'/',run=source+label+'/',actualBytes=read(root,actualName),actual=JSON.parse(actualBytes);
 need(actual.chunk_id===chunk&&actual.exit_code===0&&actual.output===label+': 81 passed, 0 failed, 0 skipped; generated scope only.\r\n','actual outer exit');
 const pinsBytes=read(run,'PINS.json'),pins=JSON.parse(pinsBytes),sourcePins=read(source,'PINS.json');
 need(hash(pinsBytes)===pin&&pinsBytes.equals(sourcePins)&&pins.files.length===27&&pins.count===27,'pins binding');
 const selectedRelation=relation.copies.find(r=>r.role===role);need(selectedRelation.pins_sha256===pin&&selectedRelation.label===label,'copy relation');
 const expectedFiles=[...pins.files.map(r=>r.path),'PINS.json','ROOT-ADMISSION.json','plan.json','stdout.json','stderr.log','native-exit.json','input-check.json','exit.json'];
 const entries=readdirSync(run,{withFileTypes:true});need(entries.length===35&&entries.every(e=>e.isFile())&&new Set(expectedFiles).size===35&&exact(sorted(entries.map(e=>e.name)),sorted(expectedFiles)),'exact35 output membership');
 const plan=json(run,'plan.json'),check=json(run,'input-check.json'),exit=json(run,'exit.json'),native=json(run,'native-exit.json'),admission=json(run,'ROOT-ADMISSION.json');
 const stdout=read(run,'stdout.json'),stderr=read(run,'stderr.log'),r=JSON.parse(stdout);
 need(plan.label===label&&plan.schema==='uoink.windows-reservation-fake-launch.v1'&&plan.scope==='generated_bytes_and_fake_ports_only'&&plan.startup_binding_set===true,'plan scope');
 need(plan.python==='C:\\Python314\\python.exe'&&exact(plan.arguments.slice(0,3),['-I','-S','-B'])&&plan.arguments.length===4&&resolve(plan.arguments[3])===resolve(run,'qualify_windows_reservations.py'),'fixed isolated invocation');
 need(admission.approved===true&&admission.label===label&&admission.pins_sha256===pin&&admission.scope===plan.scope&&admission.attempts===1&&admission.expected_cases===81&&admission.new_cases===16&&admission.model_or_native_service_authority===false,'exact bounded admission');
 need(admission.source_commit==='d7c86f902cd120553a9ddda5300fb4867d9d279f'&&admission.peer_verdict_sha256==='06f077ce460117870b7544cb3d434c47752313f66bede84615e939c1ff032cb2','source acceptance binding');
 need(Date.parse(admission.timestamp_utc)<=Date.parse(plan.started_utc)&&Date.parse(plan.started_utc)<=Date.parse(native.finished_utc)&&Date.parse(native.finished_utc)<=Date.parse(exit.finished_utc),'recorded timing order');
 need(plan.before.length===27&&check.inputs.length===27&&check.inputs_unchanged===true,'27 before/after records');
 for(let i=0;i<27;i++){
  const row=pins.files[i],before=plan.before[i],after=check.inputs[i],originalBytes=read(source,row.path),copyBytes=read(run,row.path),b=binding(originalBytes);
  need(originalBytes.equals(copyBytes)&&b.bytes===row.bytes&&b.sha256===row.sha256,'actual source/copy pin '+row.path);
  need(exact(before,{name:row.path,bytes:row.bytes,sha256:row.sha256})&&after.name===row.path&&after.unchanged===true&&exact(after.original,b)&&exact(after.copy,b),'recorded source/copy binding '+row.path);
 }
 need(plan.controls.length===3&&check.controls.length===3,'three controls');
 for(let i=0;i<3;i++){
  const name=controls[i],b=binding(read(source,name)),copy=read(run,name),before=plan.controls[i],after=check.controls[i];
  need(read(source,name).equals(copy)&&before.name===name&&exact(before.binding,b)&&after.name===name&&after.unchanged===true&&exact(after.original,b)&&exact(after.copy,b),'actual/recorded control '+name);
 }
 need(selectedRelation.launcher_sha256===hash(read(run,'run_preflight01.ps1')),'launcher relation');
 need(r.schema==='uoink.windows-reservation-fake-preflight.v1'&&r.scope==='Original65 plus16 controller startup cases; isolated synthetic authority and fake services only; real worker remains closed','receipt schema/scope');
 need(r.count===81&&r.passed===81&&r.failed===0&&r.skipped===0&&r.qualification_exit===0&&r.membership_valid===true&&r.guard_valid===true,'receipt totals');
 need(exact(r.expected_cases,expected)&&r.cases.length===81&&exact(r.cases.map(c=>c.id),expected),'complete ordered cases');
 let subtests=0,oldSubtests=0;
 for(let i=0;i<r.cases.length;i++){
  const c=r.cases[i];need(keys(c,['id','passed','skipped','errors','subtests'])&&c.passed===true&&c.skipped===false&&Array.isArray(c.errors)&&c.errors.length===0&&Array.isArray(c.subtests)&&c.subtests.length<=64,'case state '+c.id);
  for(const s of c.subtests)need(keys(s,['id','passed'])&&typeof s.id==='string'&&s.id.length<=512&&s.passed===true,'subtest state '+c.id);
  subtests+=c.subtests.length;if(i<65)oldSubtests+=c.subtests.length;
 }
 need(subtests===48,'48 complete passing subtests');
 need(keys(r.guards,guardNames)&&guardNames.every(n=>r.guards[n]===true),'exact ten guards');
 need(r.metadata_trap_count===12&&r.registry_trap_count===25&&exact(r.guard_denials,[])&&exact(r.registry_denials,[])&&exact(r.heavy_roots_loaded,[]),'traps and empty denials/heavy roots');
 const map=json(run,'SOURCE-INPUTS.json');need(hash(read(run,'SOURCE-INPUTS.json'))==='fde7f1797a2873860e1547257cd94a0676821c271004f4c5a7b82d7dc9ebbcd8'&&map.child_inputs.length===23&&keys(r.input_sha256,map.child_inputs.map(x=>x.name)),'23 hash membership');
 for(const row of map.child_inputs)need(r.input_sha256[row.name]===row.sha256&&hash(read(run,row.name))===row.sha256,'child hash '+row.name);
 need(native.native_exit===0&&exit.native_exit===0&&exit.qualification_exit===0&&exit.valid===true&&exit.inputs_unchanged===true&&exit.membership_valid===true&&exit.guards_valid===true&&exit.passed===81&&exit.failed===0&&exit.skipped===0,'actual native/outer receipt states');
 need(stdout.length===exit.stdout_bytes&&stdout.length<=262144&&stderr.length===0&&exit.stderr_bytes===0,'raw stdout/stderr bounds');
 need([r.elapsed_seconds,native.elapsed_seconds,exit.elapsed_seconds,actual.wall_time_seconds].every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=0),'finite elapsed times');
 results.push(r);
 summaries.push({role,actual_chunk:chunk,actual_exit:actual.exit_code,actual_sha256:hash(actualBytes),pins_sha256:pin,admission_sha256:hash(read(run,'ROOT-ADMISSION.json')),passed:81,failed:0,skipped:0,subtests,old65_subtests:oldSubtests,new16_subtests:subtests-oldSubtests,child_hashes:23,guards:10,metadata_traps:12,registry_traps:25,inputs:27,controls:3,outputs:35,stdout_bytes:stdout.length,stderr_bytes:stderr.length,stdout_sha256:hash(stdout),cases_sha256:hash(Buffer.from(JSON.stringify(r.cases))),case_elapsed_seconds:r.elapsed_seconds,launcher_elapsed_seconds:exit.elapsed_seconds,outer_elapsed_seconds:actual.wall_time_seconds});
 writeFileSync(own+role.toUpperCase()+'-RUN-ACTUAL.json',actualBytes,{flag:'wx'});
}
need(exact(results[0].cases,results[1].cases),'all complete case/subtest objects equal');
need(exact(results[0].input_sha256,results[1].input_sha256),'all23 child hash objects equal');
const result={scope:'passive saved text receipt verification; no subject rerun',status:'PASS',runs:summaries,complete_case_objects_equal:true,all_child_hash_objects_equal:true};
writeFileSync(own+'RESULT.json',JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(result,null,2));
