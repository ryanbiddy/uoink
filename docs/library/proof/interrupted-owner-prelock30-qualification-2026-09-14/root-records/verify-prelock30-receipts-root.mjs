import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',scratch=path.join(root,'_scratch');
const mode=process.argv[2];if(!['author','both'].includes(mode))throw Error('Fixed mode');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const read=p=>{const s=fs.lstatSync(p);if(!s.isFile()||s.isSymbolicLink()||s.size>1048576)throw Error('Bounded plain file');return fs.readFileSync(p);};
const json=p=>JSON.parse(read(p));const require=(v,m)=>{if(!v)throw Error(m);};
const guardKeys=['startup_bound','content_reads_closed','audit_identity_unchanged','metadata_traps_installed','baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed','captures_installed','capture_valid','real_entrypoints_unchanged'].sort();
const legacy=json(path.join(scratch,'interrupted-retirement-fake28-author01/interrupted-retirement-fake01/stdout.json'));
require(legacy.count===28&&legacy.passed===28&&legacy.failed===0,'Original28 receipt');
function inspect(directory,label,actualName){
 const prep=path.join(scratch,directory),run=path.join(prep,label),actual=json(path.join(scratch,actualName));
 require(actual.exit_code===0&&!actual.session_id,'Completed actual outer exit');
 const pinsRaw=read(path.join(prep,'PINS.json')),pins=JSON.parse(pinsRaw),rows=pins.files;
 require(pins.finalized===true&&rows.length===39,'Final39 map');
 const manifestNames=rows.map(r=>r.path);require(manifestNames.every(n=>/^[A-Za-z0-9_.-]+$/.test(n))&&new Set(manifestNames).size===39,'Exact39 names');
 const expectedNames=[...manifestNames,'PINS.json','ROOT-ADMISSION.json','plan.json','native-exit.json','input-check.json','stdout.json','stderr.log','exit.json'].sort();
 require(expectedNames.length===47&&new Set(expectedNames).size===47,'Output47 plan');
 require(JSON.stringify(fs.readdirSync(run).sort())===JSON.stringify(expectedNames),'Exact47 output files');
 for(const row of rows){const a=read(path.join(prep,row.path)),b=read(path.join(run,row.path));require(a.equals(b)&&a.length===row.bytes&&sha(a)===row.sha256,'Unchanged original/copy '+row.path);}
 for(const name of ['PINS.json','ROOT-ADMISSION.json'])require(read(path.join(prep,name)).equals(read(path.join(run,name))),'Control copy '+name);
 const admission=json(path.join(run,'ROOT-ADMISSION.json'));require(admission.approved===true&&admission.label===label&&admission.pins_sha256===sha(pinsRaw)&&admission.scope==='generated_bytes_and_fake_ports_only','Actual admission binding');
 const result=json(path.join(run,'stdout.json')),exit=json(path.join(run,'exit.json')),native=json(path.join(run,'native-exit.json')),check=json(path.join(run,'input-check.json')),plan=json(path.join(run,'plan.json')),expected=json(path.join(run,'EXPECTED-CASES.json'));
 require(result.schema==='uoink.windows-reservation-fake-preflight.v1'&&result.qualification_exit===0&&native.native_exit===0&&exit.native_exit===0&&exit.qualification_exit===0,'All recorded exits');
 require(result.count===30&&result.passed===30&&result.failed===0&&result.skipped===0&&exit.passed===30&&exit.failed===0&&exit.skipped===0,'All30 cases pass');
 require(result.membership_valid===true&&result.guard_valid===true&&exit.valid===true&&exit.membership_valid===true&&exit.guards_valid===true&&exit.inputs_unchanged===true,'Valid outcome fields');
 require(JSON.stringify(Object.keys(result.guards).sort())===JSON.stringify(guardKeys)&&Object.values(result.guards).every(v=>v===true),'All ten exact guards');
 require(result.metadata_trap_count===12&&result.registry_trap_count===25&&result.guard_denials.length===0&&result.registry_denials.length===0&&result.heavy_roots_loaded.length===0,'Traps and denials');
 require(JSON.stringify(result.cases.map(r=>r.id))===JSON.stringify(expected)&&JSON.stringify(result.expected_cases)===JSON.stringify(expected),'Exact ordered cases');
 require(JSON.stringify(result.cases.slice(0,28))===JSON.stringify(legacy.cases),'Original28 complete case objects');
 let subtests=0;for(const c of result.cases){require(c.passed===true&&c.skipped===false&&c.errors.length===0&&c.subtests.every(s=>s.passed===true),'Successful case and subtests');subtests+=c.subtests.length;}
 require(subtests===62&&result.cases[29].subtests.length===5,'Observed62 nested rows including five new negatives');
 const childNames=manifestNames.filter(n=>n.endsWith('.py')||n==='EXPECTED-CASES.json').sort();
 require(childNames.length===36&&JSON.stringify(Object.keys(result.input_sha256).sort())===JSON.stringify(childNames),'Exact36 child hashes');
 for(const name of childNames)require(result.input_sha256[name]===rows.find(r=>r.path===name).sha256,'Child source hash '+name);
 require(check.inputs_unchanged===true&&check.inputs.length===39&&check.controls.length===3&&check.inputs.every(r=>r.unchanged===true)&&check.controls.every(r=>r.unchanged===true),'39 inputs/3 controls recorded');
 require(JSON.stringify(check.controls.map(c=>c.name))===JSON.stringify(['PINS.json','ROOT-ADMISSION.json','run_preflight01.ps1']),'Exact control names');
 require(JSON.stringify(check.inputs.map(r=>r.name))===JSON.stringify(manifestNames)&&JSON.stringify(plan.before.map(r=>r.name))===JSON.stringify(manifestNames),'Recorded source membership');
 for(const r of check.inputs){const pinned=rows.find(p=>p.path===r.name);for(const side of [r.original,r.copy])require(side.bytes===pinned.bytes&&side.sha256===pinned.sha256,'Recorded binding '+r.name);}
 for(const c of check.controls){const b=read(path.join(prep,c.name));require(c.original.bytes===b.length&&c.copy.bytes===b.length&&c.original.sha256===sha(b)&&c.copy.sha256===sha(b),'Recorded control '+c.name);}
 require(plan.label===label&&plan.python==='C:\\Python314\\python.exe'&&plan.startup_binding_set===true&&plan.scope==='generated_bytes_and_fake_ports_only','Plan scope');
 require(JSON.stringify(plan.arguments.slice(0,3))===JSON.stringify(['-I','-S','-B']),'Isolated interpreter flags');
 require(plan.arguments.length===4&&path.normalize(plan.arguments[3])===path.normalize(path.join(run,'qualify_windows_reservations.py')),'Exact child command');
 require(read(path.join(run,'stderr.log')).length===0&&exit.stderr_bytes===0&&read(path.join(run,'stdout.json')).length===exit.stdout_bytes,'Stream sizes');
 return {directory,label,actual:actual.chunk_id,outer_exit:actual.exit_code,passed:result.passed,failed:result.failed,skipped:result.skipped,passing_subtests:subtests,case_elapsed_seconds:result.elapsed_seconds,payloads_unchanged:39,controls_unchanged:3,child_hashes:36,output_files:47,pins_sha256:sha(pinsRaw),cases:result.cases,input_sha256:result.input_sha256};
}
const all=[inspect('interrupted-owner-prelock-fake30-author03','interrupted-owner-prelock-fake03','INTERRUPTED-PRELOCK30-AUTHOR-RUN-ACTUAL.json')];
if(mode==='both'){all.push(inspect('interrupted-owner-prelock-fake30-confirmation03','prelock-retirement-confirmation03','INTERRUPTED-PRELOCK30-CONFIRMATION-RUN-ACTUAL.json'));require(JSON.stringify(all[0].cases)===JSON.stringify(all[1].cases),'Same complete independent case objects');require(JSON.stringify(all[0].input_sha256)===JSON.stringify(all[1].input_sha256),'Same36 child hashes');}
console.log(JSON.stringify({scope:'Passive saved fake30 receipts and exact source/control comparison; no subject execution',copies:all.map(({cases,input_sha256,...r})=>r),identical_cases_and_child_hashes:mode==='both'}));
