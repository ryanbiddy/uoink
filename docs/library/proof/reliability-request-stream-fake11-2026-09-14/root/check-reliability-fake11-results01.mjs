import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const specs=[['reliability-request-stream-fake11-author01','reliability-request-stream-fake01','RELIABILITY-FAKE11-AUTHOR-ACTUAL.json'],['reliability-request-stream-fake11-independent01','reliability-request-stream-confirmation01','RELIABILITY-FAKE11-INDEPENDENT-ACTUAL.json']];
const rows=[];
function assert(v,m){if(!v)throw Error(m);}
function json(p){return JSON.parse(fs.readFileSync(p,'utf8'));}
function binding(p){const s=fs.lstatSync(p);assert(s.isFile()&&!s.isSymbolicLink(),'plain file');const b=fs.readFileSync(p);return{bytes:b.length,sha256:sha(b)};}
for(const [dir,label,actualName] of specs){
 const source=path.join(root,dir),run=path.join(source,label),pins=json(path.join(source,'PINS.json')),outer=json(path.join(root,actualName)),plan=json(path.join(run,'plan.json')),result=json(path.join(run,'stdout.json')),native=json(path.join(run,'native-exit.json')),exit=json(path.join(run,'exit.json')),checks=json(path.join(run,'input-check.json')),expected=json(path.join(run,'EXPECTED-CASES.json'));
 assert(outer.exit_code===0&&!outer.session_id&&native.native_exit===0&&exit.native_exit===0&&result.qualification_exit===0&&exit.qualification_exit===0,'actual exits');
 assert(result.passed===11&&result.failed===0&&result.skipped===0&&result.count===11&&result.membership_valid===true&&result.guard_valid===true&&exit.valid===true,'result');
 assert(JSON.stringify(result.cases.map(c=>c.id))===JSON.stringify(expected)&&JSON.stringify(expected)===JSON.stringify(result.expected_cases),'exact membership');
 assert(result.cases.every(c=>c.passed===true&&c.skipped===false&&c.errors.length===0&&c.subtests.every(s=>s.passed===true)),'complete cases');
 assert(Object.keys(result.guards).length===10&&Object.values(result.guards).every(v=>v===true)&&result.metadata_trap_count===12&&result.registry_trap_count===25,'guards/traps');
 assert(result.guard_denials.length===0&&result.registry_denials.length===0&&result.heavy_roots_loaded.length===0&&fs.readFileSync(path.join(run,'stderr.log')).length===0,'denials');
 assert(pins.files.length===13&&plan.before.length===13&&plan.controls.length===3&&checks.inputs.length===13&&checks.controls.length===3&&checks.inputs_unchanged===true,'fixed sources controls');
 for(const p of pins.files){const before=plan.before.find(r=>r.name===p.path),check=checks.inputs.find(r=>r.name===p.path),orig=binding(path.join(source,p.path)),copy=binding(path.join(run,p.path));for(const r of [before,check.original,check.copy,orig,copy])assert(r.bytes===p.bytes&&r.sha256===p.sha256,'source '+p.path);assert(check.unchanged===true,'unchanged');}
 for(const c of plan.controls){const check=checks.controls.find(r=>r.name===c.name);for(const r of [check.original,check.copy,binding(path.join(source,c.name)),binding(path.join(run,c.name))])assert(r.bytes===c.binding.bytes&&r.sha256===c.binding.sha256,'control '+c.name);assert(check.unchanged===true,'control unchanged');}
 const child=pins.files.filter(r=>r.path.endsWith('.py')||r.path==='EXPECTED-CASES.json');
 assert(child.length===9&&Object.keys(result.input_sha256).length===9,'child membership');
 for(const c of child)assert(result.input_sha256[c.path]===c.sha256,'child hash');
 const outputNames=[...pins.files.map(p=>p.path),'PINS.json','ROOT-ADMISSION.json','plan.json','native-exit.json','input-check.json','stdout.json','stderr.log','exit.json'].sort();
 assert(outputNames.length===21&&JSON.stringify(fs.readdirSync(run).sort())===JSON.stringify(outputNames),'exact21 outputs');
 rows.push({source:dir,label,outer:outer.chunk_id,passed:result.passed,failed:0,skipped:0,subtests:result.cases.reduce((n,c)=>n+c.subtests.length,0),guards:result.guards,source_inputs:13,controls:3,child_hashes:result.input_sha256,outputs:outputNames,cases:result.cases});
}
assert(JSON.stringify(rows[0].cases)===JSON.stringify(rows[1].cases),'identical case objects');
assert(JSON.stringify(rows[0].child_hashes)===JSON.stringify(rows[1].child_hashes),'identical child hashes');
const out={scope:'Passive root comparison; no rerun, native or model qualification',identical_case_objects:true,identical_child_hashes:true,rows};
fs.writeFileSync(path.join(root,'RELIABILITY-FAKE11-ROOT-RESULT-CHECK.json'),JSON.stringify(out,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({runs:rows.map(({cases,child_hashes,outputs,guards,...r})=>r),identical_case_objects:true,identical9_child_hashes:true,ten_guards_each:true,outputs_each:21}));
