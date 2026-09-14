import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const current=path.join(root,'_scratch/windows-interrupted-owner-native-proposal02');
const prior=path.join(root,'_scratch/windows-interrupted-owner-native-proposal01');
const read=p=>{const s=fs.lstatSync(p);if(!s.isFile()||s.isSymbolicLink())throw Error('Plain source');return fs.readFileSync(p);};
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const check=(v,m)=>{if(!v)throw Error(m);};
const pinsRaw=read(path.join(current,'PINS.json')),pins=JSON.parse(pinsRaw);
check(sha(pinsRaw)==='c5808c7af66630b77d399409564733893a074de36169817ff4cd5234981c250d','Frozen preparation');
check(pins.files.length===56&&new Set(pins.files.map(r=>r.path)).size===56,'56 unique payloads');
let payloadBytes=0;
for(const r of pins.files){check(!path.isAbsolute(r.path)&&!r.path.split('/').includes('..'),'Relative payload');const b=read(path.join(current,r.path));check(b.length===r.bytes&&sha(b)===r.sha256,'Pinned payload '+r.path);payloadBytes+=b.length;}
check(payloadBytes===835488,'Exact preparation bytes');
const mapRaw=read(path.join(current,'SOURCE-INPUTS.json')),oldMapRaw=read(path.join(prior,'SOURCE-INPUTS.json'));
check(sha(mapRaw)==='b23d95a782fe39cff9d533f46fdf6b4a3f105dc85b09a9183c2258a4e6091f26'&&sha(oldMapRaw)==='5aba36e453cbd692b4e997e44d071f4f4e6c98a1b8ab941e29f6090544ff594d','Exact source maps');
const map=JSON.parse(mapRaw),oldMap=JSON.parse(oldMapRaw),names=Object.keys(map.source_sha256).sort();
check(names.length===29&&JSON.stringify(names)===JSON.stringify(Object.keys(oldMap.source_sha256).sort())&&JSON.stringify(names)===JSON.stringify(Object.keys(map.source_paths).sort()),'29 exact source names');
const special={'generated_adapter_flow.py':'24844bf419e4d34adaf0d5c5a2678de33a4796de86dad0f83b7e386f1785f961','dummy_bootstrap.py':'7969a4405470588c6bbc501b929d5e5f3eec85b116e50384ba64aa9036a5d198'};
let sourceBytes=0;
for(const name of names){check(/^[a-z0-9_]+\.py$/.test(name),'Flat Python name');const p=path.join(current,name);check(path.resolve(map.source_paths[name])===path.resolve(p),'Fixed source path '+name);const b=read(p);check(sha(b)===map.source_sha256[name]&&sha(b)===(special[name]||oldMap.source_sha256[name]),'Source hash '+name);sourceBytes+=b.length;if(!special[name])check(b.equals(read(path.join(prior,name))),'Unchanged old source '+name);}
check(read(path.join(current,'generated_adapter_flow.py')).equals(read(path.join(root,'_scratch/interrupted-owner-prelock-fake30-author03/generated_adapter_flow.py'))),'Qualified driver bytes');
const oldBootstrap=read(path.join(prior,'dummy_bootstrap.py')).toString('utf8'),bootstrap=read(path.join(current,'dummy_bootstrap.py')).toString('utf8');
check(oldBootstrap.split('windows-interrupted-owner-retirement01').length-1===1,'One bootstrap substitution');
check(oldBootstrap.replaceAll('windows-interrupted-owner-retirement01','windows-interrupted-owner-retirement02')===bootstrap,'Bootstrap body preserved');
const oldLauncher=read(path.join(prior,'run_interrupted_owner01.ps1')).toString('utf8'),launcherRaw=read(path.join(current,'run_interrupted_owner02.ps1')),launcher=launcherRaw.toString('utf8');
check(sha(launcherRaw)==='0ca7fa0fa81596c14659117f4e92688eea83b06d0d57a3e68073fa5922e8cc4f','Reviewed launcher');
let transformed=oldLauncher;const substitutions=[];
for(const [a,b,n] of [['windows-interrupted-owner-native-proposal01','windows-interrupted-owner-native-proposal02',1],['windows-interrupted-owner-retirement01','windows-interrupted-owner-retirement02',1],['run_interrupted_owner01.ps1','run_interrupted_owner02.ps1',2]]){const count=transformed.split(a).length-1;check(count===n,'Exact launcher substitution '+a);substitutions.push({before:a,after:b,count});transformed=transformed.replaceAll(a,b);}
check(transformed===launcher,'Every launcher predicate/body unchanged');
const stable=o=>JSON.stringify(Object.keys(o).sort().map(k=>[k,o[k].bytes,o[k].sha256]));
check(Object.keys(map.native_bindings).length===9&&stable(map.native_bindings)===stable(oldMap.native_bindings),'Nine unchanged support metadata rows');
const template=JSON.parse(read(path.join(current,'ROOT-ADMISSION-TEMPLATE.json')));
check(template.root_reviewed===false&&template.scope==='generated-windows-interrupted-owner-retirement-only'&&template.case==='positive'&&template.operation_mode==='drain'&&path.resolve(template.run_path)===path.resolve(root,'_scratch/windows-interrupted-owner-retirement02')&&template.source_inputs_sha256===sha(mapRaw)&&template.launcher_sha256===sha(launcherRaw),'Exact false template');
check(!fs.existsSync(path.join(current,'ROOT-ADMISSION-drain.json'))&&!fs.existsSync(path.join(root,'_scratch/windows-interrupted-owner-retirement02')),'Absent admission and output');
console.log(JSON.stringify({scope:'Passive fixed source/metadata comparison only',payloads:56,payload_bytes:payloadBytes,pins_sha256:sha(pinsRaw),source_files:29,source_bytes:sourceBytes,unchanged_sources:27,bootstrap_label_substitutions:1,launcher_substitutions:substitutions,all_launcher_predicates_unchanged:true,qualified_driver_exact:true,support_metadata_rows:9,support_access:false,template_false:true,admission_absent:true,run_absent:true,candidate_execution:false}));
