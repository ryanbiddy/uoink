// Fixed passive source/data comparisons; never imports subject modules.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,sep} from 'node:path';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const base=resolve(root,'_scratch/startup-authority-qualification-proposal01');
const old=resolve(root,'_scratch/windows-reservation-implementation-proposal02');
const startup=resolve(root,'_scratch/real-startup-authority-repair01');
const need=(v,m)=>{if(!v)throw Error(m)};
const sha=b=>createHash('sha256').update(b).digest('hex');
function read(name,parent=base){const p=resolve(parent,name);need(p.startsWith(resolve(parent)+sep)&&/\.(py|ps1|json|md|diff|txt)$/.test(p),'fixed text path');return readFileSync(p)}
const json=(name,parent)=>JSON.parse(read(name,parent));
const pinsBytes=read('PINS.json'), mapBytes=read('SOURCE-INPUTS.json');
need(sha(pinsBytes)==='47af697a62dcead062f8c2771aad550ebd194392665f85a9a9f3face60551fb8','frozen pins');
need(sha(mapBytes)==='fde7f1797a2873860e1547257cd94a0676821c271004f4c5a7b82d7dc9ebbcd8','frozen map');
const pins=JSON.parse(pinsBytes), map=JSON.parse(mapBytes);
need(pins.files.length===27&&new Set(pins.files.map(r=>r.path)).size===27,'27 flat inputs');
let total=0;
for(const row of pins.files){need(/^[A-Za-z0-9_.-]+$/.test(row.path),'flat input');const b=read(row.path);need(b.length===row.bytes&&sha(b)===row.sha256,'pin '+row.path);total+=b.length}
need(total===455776,'total input bytes');
need(map.child_inputs.length===23&&map.modules.length===21,'child closure');
const q=read('qualify_windows_reservations.py').toString('utf8'), bq=read('qualify_windows_reservations.py',old).toString('utf8');
const modules=s=>[...s.match(/^MODULES = \((.*)\)$/m)[1].matchAll(/"([a-z0-9_]+)"/g)].map(m=>m[1]);
const names=modules(q), originalNames=modules(bq), added=['startup_fixture_resolver','startup_fixture_adapter','startup_authority_fixture','test_startup_authority'];
need(JSON.stringify(names)===JSON.stringify(map.modules)&&new Set(names).size===21,'exact module order');
need(JSON.stringify(names.filter(n=>!added.includes(n)))===JSON.stringify(originalNames),'old17 module order');
need(JSON.stringify(names.filter(n=>added.includes(n)))===JSON.stringify(added),'four ordered added names');
const childNames=[...names.map(n=>n+'.py'),'qualify_windows_reservations.py','EXPECTED-CASES.json'];
need(childNames.every(n=>map.child_inputs.some(r=>r.name===n))&&new Set(map.child_inputs.map(r=>r.name)).size===23,'exact child membership');
let unchanged=0;
for(const row of map.child_inputs){
 const b=read(row.name);need(sha(b)===row.sha256&&b.length===row.bytes,'child '+row.name);
 if(row.kind==='unchanged_corrected65'){need(b.equals(read(row.name,old)),'old module '+row.name);unchanged++}
 else if(row.kind==='current_qualified_replacement')need(row.name==='durable_lifecycle.py'&&b.equals(read('inputs/durable_lifecycle.py',startup)),'current durable');
 else if(row.kind==='fixed_startup_copy'){
  const source={startup_fixture_resolver:'inputs/trusted_asr_resolver.py',startup_fixture_adapter:'asr_loading_adapter.py',startup_authority_fixture:'startup_authority_fixture.py',test_startup_authority:'test_startup_authority.py'}[row.name.slice(0,-3)];
  need(source&&b.equals(read(source,startup)),'startup copy');
 }else need(row.kind==='prepared_instrument'&&['qualify_windows_reservations.py','EXPECTED-CASES.json'].includes(row.name),'declared instrument');
}
need(unchanged===16,'16 unchanged originals');
const expected=json('EXPECTED-CASES.json'), oldIds=json('EXPECTED-CASES.json',old), newIds=json('EXPECTED-CASES.json',startup);
need(oldIds.length===65&&newIds.length===16&&expected.length===81&&new Set(expected).size===81,'case counts');
need(JSON.stringify(expected)===JSON.stringify([...oldIds,...newIds]),'ordered65+16');
const author=json('ROOT-ADMISSION.template.json'), confirmation=json('CONFIRMATION-ADMISSION.template.json');
need(author.approved===false&&author.label==='startup-authority-fake01'&&author.pins_sha256===sha(pinsBytes),'false author template');
need(confirmation.approved===false&&confirmation.label==='startup-authority-confirmation01'&&confirmation.pins_sha256===null,'false distinct confirmation template');
const norm=b=>b.toString('utf8').replaceAll('\r\n','\n').split('\n');
function patch(name,diff){
 const beforeBytes=read('before/'+name);need(beforeBytes.equals(read(name,old)),'exact instrument origin');
 const before=norm(beforeBytes),after=norm(read(name)),p=norm(read(diff));
 need(p[0].startsWith('--- ')&&p[1].startsWith('+++ '),'patch headers');
 let i=2,o=0,n=0,hunks=0;const forward=[],reverse=[];
 while(i<p.length&&p[i]!==''){
  const m=/^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$/.exec(p[i++]);need(m,'hunk header');
  forward.push(...before.slice(o,+m[1]-1));reverse.push(...after.slice(n,+m[3]-1));o=+m[1]-1;n=+m[3]-1;let oc=0,nc=0;
  while(i<p.length&&!p[i].startsWith('@@ ')&&p[i]!==''){
   const line=p[i++],tag=line[0],s=line.slice(1);need([' ','+','-'].includes(tag),'body tag');
   if(tag!=='+'){need(before[o++]===s,'old hunk line');oc++;reverse.push(s)}
   if(tag!=='-'){need(after[n++]===s,'new hunk line');nc++;forward.push(s)}
  }
  need(oc===+m[2]&&nc===+m[4],'hunk count');hunks++;
 }
 need(p.slice(i).every(s=>s===''),'patch trailer');forward.push(...before.slice(o));reverse.push(...after.slice(n));
 need(forward.join('\n')===after.join('\n')&&reverse.join('\n')===before.join('\n'),'complete reconstruction');
 return{file:diff,hunks,forward:true,reverse:true,comparison:'complete LF-normalized text'};
}
const patches=[patch('qualify_windows_reservations.py','qualify_windows_reservations.diff'),patch('run_preflight01.ps1','run_preflight01.diff')];
console.log(JSON.stringify({scope:'passive source/data only',status:'PASS',pins_sha256:sha(pinsBytes),map_sha256:sha(mapBytes),parent_inputs:27,parent_bytes:total,module_count:21,child_count:23,unchanged_original_modules:unchanged,old_cases:65,new_cases:16,ordered_total:81,false_templates:true,patches},null,2));
