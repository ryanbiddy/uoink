import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const author=path.join(root,'_scratch/controller-custody-fake10-author01'),run=path.join(author,'controller-custody-fake01'),proposal=path.join(root,'_scratch/controller-custody-qualification-proposal01'),out=path.join(root,'_scratch/controller-custody10-failure-peer01'),confirmation=path.join(root,'_scratch/controller-custody-fake10-confirmation01');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),seen=new Map(),eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b),need=(v,m)=>{if(!v)throw Error(m);};
function bytes(p){const b=fs.readFileSync(p);need(b.equals(Buffer.from(b.toString('utf8'))),'text only');seen.set(p,{bytes:b.length,sha256:sha(b)});return b;}
const json=p=>JSON.parse(bytes(p)),binding=p=>{bytes(p);return seen.get(p);};
const pins=json(path.join(run,'PINS.json'));need(sha(bytes(path.join(run,'PINS.json')))==='25f302701d5ae62e481c0217338a84ff6eaef3febff54ca1458ea9ee28283d2a','frozen pins');
const map=json(path.join(run,'SOURCE-INPUTS.json')),plan=json(path.join(run,'plan.json')),after=json(path.join(run,'input-check.json')),result=json(path.join(run,'stdout.json')),exit=json(path.join(run,'exit.json')),native=json(path.join(run,'native-exit.json'));
const actual=json(path.join(root,'_scratch/CONTROLLER-CUSTODY10-AUTHOR-RUN-ACTUAL.json')),admissionActual=json(path.join(root,'_scratch/CONTROLLER-CUSTODY10-AUTHOR-ADMISSION-ACTUAL.json'));
need(actual.chunk_id==='6ba3f1'&&actual.exit_code===1&&actual.output===''&&native.native_exit===1&&exit.native_exit===1&&exit.qualification_exit===1&&exit.valid===false&&result.qualification_exit===1,'actual failed exits');
need(admissionActual.chunk_id==='405207'&&admissionActual.exit_code===0,'admission actual');
need(pins.files.length===15&&eq(pins.files.map(r=>r.path),map.parent_names)&&eq(plan.before.map(r=>r.name),map.parent_names)&&eq(after.inputs.map(r=>r.name),map.parent_names),'15 membership');
for(const row of pins.files){const b=binding(path.join(run,row.path));need(eq(b,{bytes:row.bytes,sha256:row.sha256}),'run pin');need(eq(binding(path.join(author,row.path)),b)&&eq(binding(path.join(proposal,row.path)),b),'author/proposal pair');
 const before=plan.before.find(r=>r.name===row.path),post=after.inputs.find(r=>r.name===row.path);need(before.bytes===b.bytes&&before.sha256===b.sha256&&post.unchanged===true&&eq(post.original,b)&&eq(post.copy,b),'recorded before/after');}
need(eq(plan.controls.map(r=>r.name),['PINS.json','ROOT-ADMISSION.json','run_preflight01.ps1'])&&eq(after.controls.map(r=>r.name),plan.controls.map(r=>r.name)),'3 controls');
for(const c of plan.controls){const b=binding(path.join(run,c.name)),p=after.controls.find(r=>r.name===c.name);need(eq(b,c.binding)&&eq(binding(path.join(author,c.name)),b)&&p.unchanged===true&&eq(p.original,b)&&eq(p.copy,b),'control hash');}
need(after.inputs_unchanged===true&&exit.inputs_unchanged===true,'unchanged records');
const names=fs.readdirSync(run).sort();need(names.length===23&&eq(names,[...map.successful_output_names].sort()),'exact 23 output membership');
const expected=json(path.join(run,'EXPECTED-CASES.json'));need(eq(result.cases.map(r=>r.id),expected)&&eq(result.expected_cases,expected)&&expected.length===10&&result.count===10&&result.membership_valid===true&&exit.membership_valid===true,'ordered cases');
need(eq(Object.keys(result.guards),map.guard_names)&&Object.values(result.guards).every(x=>x===true)&&result.guard_valid===true&&exit.guards_valid===true,'ten guards');
need(result.metadata_trap_count===12&&result.registry_trap_count===25&&result.guard_denials.length===0&&result.registry_denials.length===0&&result.heavy_roots_loaded.length===0,'traps denials');
need(eq(Object.keys(result.input_sha256),map.child_names)&&map.child_names.length===11,'11 child names');
for(const name of map.child_names)need(result.input_sha256[name]===binding(path.join(run,name)).sha256,'child hash');
need(result.passed===8&&result.failed===2&&result.skipped===0&&exit.passed===8&&exit.failed===2&&exit.skipped===0,'8/2/0');
const bad=new Map([[expected[1],["Native permit is stale or already consumed"," (fault='wrong_permit')"]],[expected[5],["Factory start owner is not live and unpublished"," (fault='active')"]]]);
let subtests=0,subpass=0;
for(const row of result.cases){need(eq(Object.keys(row),['id','passed','skipped','errors','subtests'])&&row.skipped===false,'case schema');need(row.subtests.length===map.expected.cases.find(c=>c.id===row.id).proposed_subtest_iterations,'subtest membership count');
 for(const sub of row.subtests){need(eq(Object.keys(sub),['id','passed'])&&typeof sub.id==='string'&&typeof sub.passed==='boolean','subtest schema');subtests++;subpass+=Number(sub.passed);}
 if(bad.has(row.id)){const [message,suffix]=bad.get(row.id);need(row.passed===false&&eq(row.errors,[{type:'SessionClosed',message}])&&eq(row.subtests.filter(s=>!s.passed),[{id:row.id+suffix,passed:false}]),'exact failure');}
 else need(row.passed===true&&row.errors.length===0&&row.subtests.every(s=>s.passed),'passing full row');}
need(subtests===104&&subpass===102,'subtest totals');
need(bytes(path.join(run,'stdout.json')).length===exit.stdout_bytes&&exit.stdout_bytes===32216&&bytes(path.join(run,'stderr.log')).length===0&&exit.stderr_bytes===0,'captures');
const admission=json(path.join(run,'ROOT-ADMISSION.json'));need(admission.approved===true&&admission.label===plan.label&&admission.pins_sha256===binding(path.join(run,'PINS.json')).sha256&&admission.invocations===1&&admission.no_retry===true,'admission scope');
const ctemplate=json(path.join(confirmation,'ROOT-ADMISSION.template.json'));need(ctemplate.approved===false&&ctemplate.pins_sha256==='df339faa9011e91671c5c56541a7a015e0ed5c787278d422e11d7ebee799d087','confirmation false');
need(eq(fs.readdirSync(confirmation).sort(),[...map.parent_names,'PINS.json','ROOT-ADMISSION.template.json'].sort()),'confirmation uninvoked membership');
for(const[p,h]of seen){const b=fs.readFileSync(p);need(b.length===h.bytes&&sha(b)===h.sha256,'read inputs changed');}
for(const[name,p]of [['RAW-STDOUT.json',path.join(run,'stdout.json')],['AUTHOR-RUN-ACTUAL.json',path.join(root,'_scratch/CONTROLLER-CUSTODY10-AUTHOR-RUN-ACTUAL.json')],['AUTHOR-ADMISSION-ACTUAL.json',path.join(root,'_scratch/CONTROLLER-CUSTODY10-AUTHOR-ADMISSION-ACTUAL.json')]])fs.writeFileSync(path.join(out,name),bytes(p),{flag:'wx'});
const report={review:'passive complete receipt verification',observed_overall:'FAILED',outer_exit:actual.exit_code,native_exit:native.native_exit,qualification_exit:result.qualification_exit,cases:result.cases,passed:8,failed:2,skipped:0,subtests:104,passing_subtests:102,failing_subtests:2,guards:result.guards,inputs:15,controls:3,child_hashes:result.input_sha256,output_names:names,confirmation_uninvoked:true,bindings:[...seen].map(([path,h])=>({path,...h})),candidate_rerun:false};
fs.writeFileSync(path.join(out,'CHECK-RESULT.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({review_checks:'PASS',observed_subject:'FAILED',actual:'6ba3f1',outer_exit:1,native_exit:1,qualification_exit:1,case_counts:[8,2,0],subtest_counts:[102,2],input_count:15,controls:3,child_hashes:11,guards:10,output_files:23,confirmation_uninvoked:true,inputs_unchanged:true,result_sha256:sha(fs.readFileSync(path.join(out,'CHECK-RESULT.json'))),candidate_rerun:false},null,2));

