import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const old=path.join(root,'_scratch/interrupted-retirement-fake28-author01');
const author=path.join(root,'_scratch/interrupted-owner-prelock-fake30-author03');
const confirmation=path.join(root,'_scratch/interrupted-owner-prelock-fake30-confirmation03');
const selected=process.argv[2];if(!['author','both'].includes(selected))throw Error('Fixed mode');
const read=(p)=>{const s=fs.lstatSync(p);if(!s.isFile()||s.isSymbolicLink())throw Error('Plain input');return fs.readFileSync(p);};
const oldCases=JSON.parse(read(path.join(old,'EXPECTED-CASES.json')));
const added=['test_interrupted_owner_prelock.InterruptedOwnerPrelockContracts.test_actual_controller_probes_before_media_and_after_retirement','test_interrupted_owner_prelock.InterruptedOwnerPrelockContracts.test_refusal_error_stops_media_and_reaches_context_cleanup'];
if(oldCases.length!==28)throw Error('Original28');
const expected=[...oldCases,...added];
function modules(p){const text=read(p).toString('utf8'),line=text.split(/\r?\n/).find(l=>l.startsWith('MODULES = '));if(!line)throw Error('Module literal');const rest=line.slice('MODULES = '.length);if(rest.replace(/"[a-z0-9_]+"/g,'').replace(/[(),\s]/g,''))throw Error('Closed literal grammar');return [...rest.matchAll(/"([a-z0-9_]+)"/g)].map(m=>m[1]);}
const oldModules=modules(path.join(old,'qualify_windows_reservations.py'));if(oldModules.length!==33)throw Error('Original33 modules');
function inspect(dir,label){
 const raw=read(path.join(dir,'PINS.json')),pins=JSON.parse(raw),rows=pins.files;
 if(pins.finalized!==true||rows.length!==39||new Set(rows.map(r=>r.path)).size!==39)throw Error('Final39 map');
 for(const r of rows){if(!/^[A-Za-z0-9_.-]+$/.test(r.path)||r.status==='pending_author_freeze')throw Error('Fixed flat payload');const b=read(path.join(dir,r.path));if(b.length!==r.bytes||sha(b)!==r.sha256)throw Error('Pinned payload '+r.path);}
 const cases=JSON.parse(read(path.join(dir,'EXPECTED-CASES.json')));if(JSON.stringify(cases)!==JSON.stringify(expected))throw Error('Exact30 cases');
 const mods=modules(path.join(dir,'qualify_windows_reservations.py'));if(JSON.stringify(mods)!==JSON.stringify([...oldModules,'test_interrupted_owner_prelock']))throw Error('One appended module');
 for(const name of oldModules){if(name==='generated_adapter_flow')continue;if(!read(path.join(dir,name+'.py')).equals(read(path.join(old,name+'.py'))))throw Error('Old module changed '+name);}
 if(sha(read(path.join(dir,'generated_adapter_flow.py')))!=='24844bf419e4d34adaf0d5c5a2678de33a4796de86dad0f83b7e386f1785f961')throw Error('Reviewed repair');
 if(sha(read(path.join(dir,'test_interrupted_owner_prelock.py')))!=='6370a4846e3f5f43688ede53c6665988771db53ddf309065fbc92e5965288bb4')throw Error('Reviewed controls');
 const template=JSON.parse(read(path.join(dir,'ROOT-ADMISSION.template.json')));
 if(template.approved!==false||template.label!==label||template.pins_sha256!==sha(raw)||template.scope!=='generated_bytes_and_fake_ports_only')throw Error('False template binding');
 if(fs.existsSync(path.join(dir,'ROOT-ADMISSION.json'))||fs.existsSync(path.join(dir,label)))throw Error('No previous admission/run');
 return {directory:path.relative(root,dir).replaceAll('\\','/'),label,payloads:rows.length,bytes:rows.reduce((n,r)=>n+r.bytes,0),pins_sha256:sha(raw),launcher_sha256:sha(read(path.join(dir,'run_preflight01.ps1'))),qualifier_sha256:sha(read(path.join(dir,'qualify_windows_reservations.py'))),expected_sha256:sha(read(path.join(dir,'EXPECTED-CASES.json'))),old28_and_32_unchanged_modules:true,modules:mods.length,child_inputs:mods.length+2,admission_false:true,run_absent:true};
}
const results=[inspect(author,'interrupted-owner-prelock-fake03')];
if(selected==='both'){
 results.push(inspect(confirmation,'prelock-retirement-confirmation03'));
 const a=JSON.parse(read(path.join(author,'PINS.json'))).files,b=JSON.parse(read(path.join(confirmation,'PINS.json'))).files;
 if(JSON.stringify(a.map(r=>r.path))!==JSON.stringify(b.map(r=>r.path)))throw Error('Identical copy map order');
 for(const r of a){if(r.path==='run_preflight01.ps1')continue;if(!read(path.join(author,r.path)).equals(read(path.join(confirmation,r.path))))throw Error('Independent copied payload '+r.path);}
 const before=read(path.join(author,'run_preflight01.ps1')).toString('utf8'),after=read(path.join(confirmation,'run_preflight01.ps1')).toString('utf8');
 const count=before.split('interrupted-owner-prelock-fake03').length-1;
 if(count!==5||before.replaceAll('interrupted-owner-prelock-fake03','prelock-retirement-confirmation03')!==after)throw Error('Only five independent label substitutions');
}
console.log(JSON.stringify({scope:'Passive source/control binding only; no candidate execution',copies:results}));
