import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const a=path.join(root,'_scratch/interrupted-retirement-fake28-author01');
const b=path.join(root,'_scratch/astra-interrupted-retirement-confirmation01');
const sha=v=>crypto.createHash('sha256').update(v).digest('hex');
const raw=p=>fs.readFileSync(p), json=p=>JSON.parse(raw(p));
const req=(v,m)=>{if(!v)throw Error(m);};
function checkPreparation(d,pin){const pr=raw(path.join(d,'PINS.json'));req(sha(pr)===pin,'map');const p=JSON.parse(pr);req(p.finalized&&p.files.length===38&&new Set(p.files.map(r=>r.path)).size===38,'38');for(const r of p.files){req(/^[A-Za-z0-9_.-]+$/.test(r.path),'flat');const v=raw(path.join(d,r.path));req(v.length===r.bytes&&sha(v)===r.sha256,'payload '+r.path);}return p;}
const ap=checkPreparation(a,'eb108b71b9f2a7d10db57efb2aa92b7b8df20a25bf44923ca273f456ab753bc1');
const bp=checkPreparation(b,'bf5917433c3e0220a79625b9a0708a3fbfa359dac8023a2b4b6ae1951048e4de');
req(JSON.stringify(ap.files.map(r=>r.path))===JSON.stringify(bp.files.map(r=>r.path)),'ordered pins');
for(const r of ap.files){const v=raw(path.join(a,r.path)),w=raw(path.join(b,r.path));if(r.path==='run_preflight01.ps1'){const t=v.toString();req(t.split('interrupted-retirement-fake01').length-1===5,'5 labels');req(Buffer.from(t.replaceAll('interrupted-retirement-fake01','interrupted-retirement-confirmation01')).equals(w),'launcher delta');}else req(v.equals(w),'copy relation '+r.path);}
function checkRun(d,label,actualFile){const run=path.join(d,label), p=json(path.join(d,'PINS.json')), result=json(path.join(run,'stdout.json')), ex=json(path.join(run,'exit.json')), nx=json(path.join(run,'native-exit.json')), controls=json(path.join(run,'input-check.json')), plan=json(path.join(run,'plan.json')), admission=json(path.join(d,'ROOT-ADMISSION.json'));
 req(admission.approved===true&&admission.label===label&&admission.pins_sha256===sha(raw(path.join(d,'PINS.json'))),'admission');
 req(ex.valid&&ex.inputs_unchanged&&ex.membership_valid&&ex.guards_valid&&ex.native_exit===0&&ex.qualification_exit===0&&ex.passed===28&&ex.failed===0&&ex.skipped===0&&nx.native_exit===0,'parent exits');
 const actual=json(path.join(root,actualFile));req(actual.exit_code===0&&!actual.session_id,'outer exit');
 req(result.count===28&&result.passed===28&&result.failed===0&&result.skipped===0&&result.qualification_exit===0&&result.membership_valid&&result.guard_valid,'child result');
 const expected=json(path.join(d,'EXPECTED-CASES.json'));req(JSON.stringify(result.cases.map(r=>r.id))===JSON.stringify(expected)&&JSON.stringify(result.expected_cases)===JSON.stringify(expected),'cases');
 req(result.cases.every(r=>r.passed===true&&r.skipped===false&&r.errors.length===0&&r.subtests.length<=64&&r.subtests.every(s=>s.passed===true)),'case outcomes');
 req(Object.keys(result.guards).length===10&&Object.values(result.guards).every(v=>v===true)&&result.guard_denials.length===0&&result.registry_denials.length===0&&result.heavy_roots_loaded.length===0&&result.metadata_trap_count===12,'guards');
 req(raw(path.join(run,'stderr.log')).length===0&&raw(path.join(run,'stdout.json')).length<=262144,'raw capture');
 req(controls.inputs_unchanged&&controls.inputs.length===38&&controls.controls.length===3&&controls.inputs.every(r=>r.unchanged)&&controls.controls.every(r=>r.unchanged),'postcheck');
 for(const r of p.files){req(raw(path.join(d,r.path)).equals(raw(path.join(run,r.path))),'run input '+r.path);}
 for(const name of ['PINS.json','ROOT-ADMISSION.json','run_preflight01.ps1'])req(raw(path.join(d,name)).equals(raw(path.join(run,name))),'run control '+name);
 req(Object.keys(result.input_sha256).length===35,'35 child hashes');for(const [name,h]of Object.entries(result.input_sha256)){req(sha(raw(path.join(d,name)))===h,'child hash '+name);}
 req(plan.scope==='generated_bytes_and_fake_ports_only'&&plan.label===label&&plan.startup_binding_set===true&&plan.python==='C:\\Python314\\python.exe'&&JSON.stringify(plan.arguments.slice(0,3))==='["-I","-S","-B"]','launch plan');
 const wanted=[...p.files.map(r=>r.path),'PINS.json','ROOT-ADMISSION.json','plan.json','stdout.json','stderr.log','native-exit.json','input-check.json','exit.json'].sort();req(JSON.stringify(fs.readdirSync(run).sort())===JSON.stringify(wanted),'exact run files');
 return {label,outer_chunk:actual.chunk_id,passed:28,failed:0,skipped:0,subtests:result.cases.reduce((n,r)=>n+r.subtests.length,0),guard_count:10,child_inputs:35,run_files:wanted.length,cases:result.cases,hashes:result.input_sha256};}
const ar=checkRun(a,'interrupted-retirement-fake01','_scratch/INTERRUPTED-FAKE28-AUTHOR-RUN-ACTUAL.json');
if(process.argv.includes('--both')){const br=checkRun(b,'interrupted-retirement-confirmation01','_scratch/INTERRUPTED-FAKE28-INDEPENDENT-RUN-ACTUAL.json');req(JSON.stringify(ar.cases)===JSON.stringify(br.cases),'exact case objects');req(JSON.stringify(ar.hashes)===JSON.stringify(br.hashes),'same child hashes');delete br.cases;delete br.hashes;delete ar.cases;delete ar.hashes;console.log(JSON.stringify({author:ar,independent:br,exact_case_objects:true,exact35_child_hashes:true,source_relations:{identical:37,label_only:1}}));}
else{req(!fs.existsSync(path.join(b,'ROOT-ADMISSION.json'))&&!fs.existsSync(path.join(b,'interrupted-retirement-confirmation01')),'independent not started');delete ar.cases;delete ar.hashes;console.log(JSON.stringify({author:ar,independent_inputs_verified:true,independent_map_sha256:sha(raw(path.join(b,'PINS.json'))),source_relations:{identical:37,label_only:1},independent_admission:false}));}
