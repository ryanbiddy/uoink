import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const core=path.join(root,'_scratch/controller-boundary-custody-repair01');
const fixture=path.join(root,'_scratch/controller-boundary-fixture-repair01');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function read(p){ const resolved=path.resolve(p); if(!resolved.toLowerCase().startsWith(path.resolve(root).toLowerCase()+path.sep)||! /\.(py|json|md|mjs|ps1|diff|txt|log)$/.test(resolved)) throw Error('Text outside task scope '+p); const s=fs.lstatSync(resolved);if(!s.isFile()||s.isSymbolicLink())throw Error('Plain file required');const b=fs.readFileSync(resolved);if(!Buffer.from(b.toString('utf8')).equals(b))throw Error('UTF8 required');return b; }
function check(p,row){const b=read(p);if(sha(b)!==row.sha256||(row.bytes!==undefined&&b.length!==row.bytes))throw Error('Binding mismatch '+p);return b;}
const cm=JSON.parse(check(path.join(core,'SOURCE-INPUTS03.json'),{sha256:'0d8e9d7b8f3fd112d477ecb9ef9c165058d6bb1c3ef938458c308eebc0ac18ec'}));
if(cm.selected_inputs.length!==15||cm.original_and_copy_bindings.length!==6||cm.derivatives.length!==76||cm.core_canonical_modules.length!==7)throw Error('Core membership');
for(const r of cm.selected_inputs)check(path.join(root,r.path),r);
for(const r of cm.original_and_copy_bindings){check(r.source,r);check(path.join(core,r.copy),r);}
for(const r of cm.derivatives)check(path.join(core,r.name),r);
for(const r of cm.core_canonical_modules)check(path.join(root,r.path),r);
const adapter=check(path.join(core,'asr_loading_adapter.py'),{bytes:47660,sha256:'227395c4e1f25f75f13dc950e3b2e222af4a4d8b307a36091908229b58ed0c0f'});
const prior=read(path.join(core,'before/accepted-asr_loading_adapter.py'));
if(prior.length!==34968||!adapter.subarray(0,prior.length).equals(prior))throw Error('Accepted prefix');
const fm=JSON.parse(check(path.join(fixture,'SOURCE-INPUTS.json'),{sha256:'82108776580dd7e0927f50d1dd26ce9ebd8af827b664c090db2c8d50e74465ad'}));
const names=['trusted_asr_resolver','snapshot_lifecycle','snapshot_reservations','reservation_file_port','durable_lifecycle','asr_loading_adapter','test_reservations','controller_boundary_fixture','test_controller_resume_publication'];
if(fm.modules.length!==9||fm.context.length!==6||fm.cases.length!==10||fm.proposed_subtest_total!==104||fm.maximum_subtests_per_case!==48)throw Error('Fixture membership');
for(const [i,r] of fm.modules.entries()){if(r.module!==names[i]||r.order!==i+1)throw Error('Module order');check(r.path,r);}
for(const r of fm.context)check(r.path,r);
const expected=JSON.parse(check(fm.expected.path,fm.expected));
const ids=[...read(path.join(fixture,'test_controller_resume_publication.py')).toString('utf8').matchAll(/^    def (test_[a-z0-9_]+)\(self\):/gm)].map(m=>'test_controller_resume_publication.ControllerBoundaryContracts.'+m[1]);
if(JSON.stringify(ids)!==JSON.stringify(expected)||JSON.stringify(ids)!==JSON.stringify(fm.cases.map(r=>r.id)))throw Error('Case order');
if(fm.cases.reduce((n,r)=>n+r.proposed_subtest_iterations,0)!==104)throw Error('Subtest arithmetic');
const donor=path.join(root,'_scratch/controller-stage-qualification-proposal01');
const old=JSON.parse(check(path.join(donor,'PINS.json'),{sha256:'b831bf6c864d8a7bef24355e5868dfa7480e6bba6ff1381cbc3ac9db07388606'}));
if(old.count!==29||old.files.length!==29)throw Error('Old95 membership');for(const r of old.files)check(path.join(donor,r.path),r);
check(path.join(root,'_scratch/controller-custody-source-peer01/VERDICT.md'),{bytes:4076,sha256:'e24c201ba7f23d026c1a4fdad64f5d0eaa84c24984d2a4a6ec9866a1b3f77fe3'});
check(path.join(root,'_scratch/controller-custody-fixture-peer01/VERDICT.md'),{bytes:3075,sha256:'c0fbb1e371dce5f7fc4af4d6fe786a27d16b3b8089c17a64c980e43798aff82d'});
console.log(JSON.stringify({status:'PASS_PASSIVE_BINDING_ONLY',core_inputs:15,original_copy_pairs:6,derivatives:76,core_modules:7,fixture_modules:9,context_sources:6,source_ordered_cases:10,proposed_subtests:104,old95_parent_inputs_unchanged:29,accepted_adapter_prefix_bytes:34968,candidate_executions:0}));
