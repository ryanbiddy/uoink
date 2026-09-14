import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),read=p=>fs.readFileSync(p),json=p=>JSON.parse(read(p));
function require(v,m){if(!v)throw Error(m);}
const guards=['metadata_traps_installed','content_reads_closed','baseline_winreg_identity_unchanged','registry_namespace_unchanged','registry_traps_installed','captures_installed','capture_valid','methods_unchanged','closed_entries_unchanged','owner_binding_valid'];
const specs=[['protected-engine-ownership-fake39-author01','protected-engine-fake01','ENGINE-FAKE39-AUTHOR-POLL02-ACTUAL.json']];
if(process.argv[2]==='pair')specs.push(['protected-engine-ownership-fake39-independent01','protected-engine-confirmation01','ENGINE-FAKE39-INDEPENDENT-FINAL-ACTUAL.json']);
else require(process.argv.length===2,'known mode only');
const rows=[];
for(const [dir,label,actual] of specs){const source=path.join(root,dir),run=path.join(source,'runs',label),pins=json(path.join(source,'PINS.json')),plan=json(path.join(run,'plan.json')),after=json(path.join(run,'after.json')),result=json(path.join(run,'stdout.json')),native=json(path.join(run,'native-exit.json')),exit=json(path.join(run,'exit.json')),outer=json(path.join(root,actual)),admission=json(path.join(source,'ROOT-ADMISSION.json')),expected=json(path.join(run,'EXPECTED-CASES.json'));
 require(outer.exit_code===0&&!outer.session_id&&native.child_returned===true&&native.native_exit===0&&exit.native_exit===0&&exit.outer_exit===0&&result.native_exit===0,'actual exit chain');
 require(result.schema==='uoink.runtime-owner-native-fake.v1'&&result.count===39&&result.passed===39&&result.failed===0&&result.skipped===0&&result.guard_valid===true&&exit.receipt_valid===true&&exit.inputs_unchanged===true&&exit.startup_binding_set===true,'result and receipt');
 require(expected.schema==='uoink.runtime-owner-native-expected-cases.v1'&&expected.count===39&&expected.ordered_cases.length===39&&new Set(expected.ordered_cases).size===39,'expected schema/count');
 for(const sequence of [result.expected_cases,plan.planned_cases,admission.expected_cases,result.cases.map(c=>c.name)])require(JSON.stringify(sequence)===JSON.stringify(expected.ordered_cases),'ordered39');
 require(result.cases.every(c=>c.passed===true&&Object.keys(c).sort().join(',')==='name,passed'),'exact passing case objects');
 require(guards.every(g=>result[g]===true)&&result.metadata_trap_count===12&&result.registry_trap_count===25&&result.registry_trap_names.length===25,'ten guards/traps');
 require(['guard_denials','registry_denials','heavy_roots_loaded'].every(k=>Array.isArray(result[k])&&result[k].length===0)&&result.stdout_capture===''&&result.stderr_capture===''&&read(path.join(run,'stderr.log')).length===0,'no denied/heavy/incidental activity');
 require(exit.stderr_bytes===0&&exit.stdout_bytes===read(path.join(run,'stdout.json')).length,'receipt output bounds');
 require(pins.count===40&&pins.files.length===40&&plan.inputs.length===40&&after.length===41&&plan.label===label&&admission.label===label&&admission.root_reviewed===true&&admission.scope==='protected-engine-ownership-fake-39-only','parents and scope');
 require(plan.interpreter==='C:\\Python314\\python.exe'&&JSON.stringify(plan.arguments)===JSON.stringify(['-I','-S','-B','qualify_owner.py'])&&plan.startup_binding_set===true&&plan.no_native_or_model_activity===true,'fixed startup');
 require(JSON.stringify(after.map(r=>r.name).sort())===JSON.stringify([...pins.files.map(r=>r.path),'ROOT-ADMISSION.json'].sort()),'after membership');
 for(const p of pins.files){const prior=plan.inputs.find(r=>r.name===p.path),check=after.find(r=>r.name===p.path);require(prior&&check&&path.resolve(prior.source)===path.resolve(source,p.path)&&prior.sha256===p.sha256&&admission.input_sha256[p.path]===p.sha256,'plan binding '+p.path);for(const field of ['before_sha256','copy_after_sha256','source_after_sha256'])require(check[field]===p.sha256,'after '+p.path);for(const dir of [source,run]){const b=read(path.join(dir,p.path));require(b.length===p.bytes&&sha(b)===p.sha256,'current '+p.path);}}
 const a=after.find(r=>r.name==='ROOT-ADMISSION.json'),aHash=sha(read(path.join(source,a.name)));require(a.before_sha256===aHash&&a.copy_after_sha256===aHash&&a.source_after_sha256===aHash&&sha(read(path.join(run,a.name)))===aHash,'admission unchanged');
 const child=pins.files.filter(p=>p.path.endsWith('.py')||p.path==='EXPECTED-CASES.json');require(child.length===38&&JSON.stringify(Object.keys(result.input_sha256).sort())===JSON.stringify(child.map(r=>r.path).sort()),'child membership');for(const p of child)require(result.input_sha256[p.path]===p.sha256,'child hash');
 const names=[...pins.files.map(p=>p.path),'ROOT-ADMISSION.json','plan.json','native-exit.json','after.json','stdout.json','stderr.log','exit.json'].sort();require(names.length===47&&JSON.stringify(fs.readdirSync(run).sort())===JSON.stringify(names),'exact47 output membership');
 rows.push({source:dir,label,outer:outer.chunk_id,passed:39,failed:0,skipped:0,elapsed_seconds:result.elapsed_seconds,guards:10,parent_inputs:40,admission_controls:1,child_hashes:result.input_sha256,output_files:47,cases:result.cases});
}
if(rows.length===2){require(JSON.stringify(rows[0].cases)===JSON.stringify(rows[1].cases),'identical case objects');require(JSON.stringify(rows[0].child_hashes)===JSON.stringify(rows[1].child_hashes),'identical38 child hashes');}
const out={scope:'Passive root receipt verification; no subject rerun',pair:rows.length===2,rows};
fs.writeFileSync(path.join(root,'ENGINE-FAKE39-ROOT-'+(rows.length===2?'PAIR':'AUTHOR')+'-RESULT.json'),JSON.stringify(out,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({pair:rows.length===2,rows:rows.map(({cases,child_hashes,...r})=>r),separate_subtest_count_claimed:false}));
