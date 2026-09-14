// Source-text preparation only. No candidate import, process, FFI, support or generated-file access.
import fs from 'node:fs'; import path from 'node:path'; import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const oldName='windows-interrupted-owner-native-proposal02',newName='controller-generated-native-compatibility-proposal01';
const donor=path.join(root,'_scratch',oldName),out=path.join(root,'_scratch',newName);
const oldRun='windows-interrupted-owner-retirement02',newRun='controller-generated-native-compatibility01';
const oldLauncher='run_interrupted_owner02.ps1',newLauncher='run_controller_generated_compatibility01.ps1';
const oldScope='generated-windows-interrupted-owner-retirement-only',newScope='generated-controller-core-start-compatibility-only';
const expected={map:'b23d95a782fe39cff9d533f46fdf6b4a3f105dc85b09a9183c2258a4e6091f26',boot:'7969a4405470588c6bbc501b929d5e5f3eec85b116e50384ba64aa9036a5d198',launcher:'0ca7fa0fa81596c14659117f4e92688eea83b06d0d57a3e68073fa5922e8cc4f'};
const core={ 'durable_lifecycle.py':'ce69903d93daf41ae3717008f8d0dbd0b3ead7b11662b674eddf43828567b222','asr_loading_adapter.py':'227395c4e1f25f75f13dc950e3b2e222af4a4d8b307a36091908229b58ed0c0f'};
function ok(v,m){if(!v)throw Error(m);}
function read(p){const st=fs.lstatSync(p);ok(st.isFile()&&!st.isSymbolicLink()&&st.size<=1048576,'fixed plain source '+p);return fs.readFileSync(p);}
function write(p,b){fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,b,{flag:'wx'});}
function sha(b){return crypto.createHash('sha256').update(b).digest('hex');}
function json(p,v){write(p,JSON.stringify(v,null,2)+'\n');}
function binding(p){const b=read(p);return {bytes:b.length,sha256:sha(b)};}
const mapRaw=read(path.join(donor,'SOURCE-INPUTS.json')),map=JSON.parse(mapRaw),names=Object.keys(map.source_sha256);
ok(sha(mapRaw)===expected.map&&names.length===29&&Object.keys(map.source_paths).length===29&&Object.keys(map.native_bindings).length===9,'fixed donor map');
ok(names.every(n=>/^[a-z0-9_]+\.py$/.test(n))&&names.at(-1)==='dummy_bootstrap.py','fixed source names');
ok(!fs.existsSync(path.join(root,'_scratch',newRun)),'new run remains absent');
const originals={};for(const n of names){const b=read(path.join(donor,n));ok(sha(b)===map.source_sha256[n],'source '+n);originals[n]=b;write(path.join(out,'before',n),b);}
for(const n of [oldLauncher,'SOURCE-INPUTS.json','NATIVE-PROTOCOL.md','BRIEF.md','ROOT-ADMISSION-TEMPLATE.json','PINS.json'])write(path.join(out,'before',n),read(path.join(donor,n)));
const edits={};
function replace(text,from,to,count,reason,ledger){ok(text.split(from).length-1===count,'literal count '+from);ledger.push({from,to,count,reason});return text.split(from).join(to);}
let boot=originals['dummy_bootstrap.py'].toString('utf8');ok(sha(originals['dummy_bootstrap.py'])===expected.boot,'bootstrap');
edits['dummy_bootstrap.py']=[];
boot=replace(boot,oldRun,newRun,1,'Fresh fixed run identity.',edits['dummy_bootstrap.py']);
boot=replace(boot,oldScope,newScope,1,'Exact compatibility admission scope.',edits['dummy_bootstrap.py']);
let launcher=read(path.join(donor,oldLauncher)).toString('utf8');ok(sha(Buffer.from(launcher))===expected.launcher,'launcher');
edits[newLauncher]=[];
launcher=replace(launcher,oldName,newName,1,'Fresh source proposal identity.',edits[newLauncher]);
launcher=replace(launcher,oldRun,newRun,1,'Fresh output identity.',edits[newLauncher]);
launcher=replace(launcher,oldLauncher,newLauncher,2,'Exact original/copied launcher control name.',edits[newLauncher]);
launcher=replace(launcher,oldScope,newScope,1,'Exact compatibility admission scope.',edits[newLauncher]);
const rows=[];
for(const n of names){let b=originals[n],origin=path.join(donor,n);if(core[n]){origin=path.join(root,'_scratch/controller-boundary-custody-repair01',n);b=read(origin);ok(sha(b)===core[n],'reviewed core '+n);}if(n==='dummy_bootstrap.py')b=Buffer.from(boot);write(path.join(out,n),b);rows.push({name:n,donor_path:path.join(donor,n),before:{bytes:originals[n].length,sha256:sha(originals[n])},origin_path:origin,after:{bytes:b.length,sha256:sha(b)},unchanged:b.equals(originals[n])});}
ok(rows.filter(x=>x.name!=='dummy_bootstrap.py'&&x.unchanged).length===26,'26 unchanged subjects');
write(path.join(out,newLauncher),launcher);
let newMapText=mapRaw.toString('utf8');edits['SOURCE-INPUTS.json']=[];
newMapText=replace(newMapText,oldName,newName,29,'Only the fixed source-path proposal component changes.',edits['SOURCE-INPUTS.json']);
for(const n of ['durable_lifecycle.py','asr_loading_adapter.py','dummy_bootstrap.py'])newMapText=replace(newMapText,map.source_sha256[n],sha(read(path.join(out,n))),1,'Pin '+n,edits['SOURCE-INPUTS.json']);
const newMap=JSON.parse(newMapText);
ok(JSON.stringify(newMap.native_bindings)===JSON.stringify(map.native_bindings),'support metadata exactly retained');
ok(newMapText.slice(newMapText.indexOf('  "native_bindings"'))===mapRaw.toString('utf8').slice(mapRaw.toString('utf8').indexOf('  "native_bindings"')),'support metadata text unchanged');
for(const n of names)ok(newMap.source_paths[n]===path.win32.join(root,'_scratch',newName,n),'literal source path '+n);
write(path.join(out,'SOURCE-INPUTS.json'),newMapText);
const templ=JSON.parse(read(path.join(donor,'ROOT-ADMISSION-TEMPLATE.json')));
ok(templ.root_reviewed===false,'false donor template');
templ.scope=newScope;templ.run_path=path.win32.join(root,'_scratch',newRun);
templ.source_inputs_sha256=sha(Buffer.from(newMapText));templ.launcher_sha256=sha(Buffer.from(launcher));
templ.reason='Source preparation only. Both corrected controller10 copies must qualify, then root and peer must review this exact source before a separate root admission. No native/model/D3/D4 authority is granted.';
json(path.join(out,'ROOT-ADMISSION-TEMPLATE.json'),templ);
const protocol=read(path.join(donor,'NATIVE-PROTOCOL.md')).toString('utf8');
const newerProtocol=protocol.split(oldName).join(newName).split(oldRun).join(newRun).split(oldLauncher).join(newLauncher);
write(path.join(out,'NATIVE-PROTOCOL.md'),'Generated controller core compatibility preparation; exact scope '+newScope+'. Both corrected controller10 copies must qualify before any native admission. The donor native02 result at99ce3c9 is historical; this derivative has no result. Only the two reviewed controller core modules and the fixed instrument identities change.\n\n'+newerProtocol+'\nThe unchanged native predicates establish at most positive generated startup/facade publication followed by the fixed interruption and explicit retirement. Ordinary close, real model loading/inference, negative generated-policy controls and D3/D4 remain separate. No simulated OS backend is implemented. The frozen alternative plan remains documentary only.\n');
write(path.join(out,'BRIEF.md'),'This is source-only preparation under CONTROLLER-GENERATED-NATIVE-COMPATIBILITY-BRIEF-2026-09-14.md, committed0a74367fce366f02a23f8938db4fc8728fbc6a88. It selects exact durablece69903d and adapter227395c4 from the accepted custody checkpoint. Twenty-six other subject modules remain donor bytes; source membership stays29, including bootstrap, with nine unchanged support metadata rows. No support path is read, statted or hashed in preparation.\n\nThe bootstrap changes only its fixed run identity and admission scope. The launcher changes only its proposal/run labels, own filename and admission scope. Every behavioral receipt predicate, journal decoder/bound, guard, native dispatch/finalizer and strict contender/worker route is preserved. Existing ordinary parent_guards_held_through_exit=False remains; no graceful killed-child claim is added.\n\nThe output directory and true ROOT-ADMISSION-drain.json remain absent. ROOT-ADMISSION-TEMPLATE.json is false. A native invocation must wait for both corrected controller10 qualifications and separate final root/peer review/admission. This preparation neither repeats native02 nor predicts a result. Full before sources, exact deltas, substitution counts and current maps are retained.\n'.replace('committed0a','committed 0a').replace('durablece','durable ce').replace('adapter227','adapter 227').replace('stays29','stays 29'));
function lines(s){ok(s.endsWith('\n'),'source ends newline');return s.slice(0,-1).split('\n');}
function diff(a,b,oldPath,newPath){const A=lines(a),B=lines(b),n=A.length,m=B.length,dp=Array.from({length:n+1},()=>new Uint16Array(m+1));for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i][j]=A[i]===B[j]?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);const ops=[];let i=0,j=0;while(i<n||j<m){if(i<n&&j<m&&A[i]===B[j]){ops.push([' ',A[i++]]);j++;}else if(j<m&&(i===n||dp[i][j+1]>dp[i+1][j]))ops.push(['+',B[j++]]);else ops.push(['-',A[i++]]);}let ranges=[];ops.forEach((o,k)=>{if(o[0]===' ')return;const s=Math.max(0,k-3),e=Math.min(ops.length,k+4);if(ranges.length&&s<=ranges.at(-1)[1])ranges.at(-1)[1]=e;else ranges.push([s,e]);});let p='--- '+oldPath+'\n+++ '+newPath+'\n';for(const[s,e]of ranges){const prev=ops.slice(0,s),part=ops.slice(s,e);p+='@@ -'+(prev.filter(x=>x[0]!=='+').length+1)+','+part.filter(x=>x[0]!=='+').length+' +'+(prev.filter(x=>x[0]!=='-').length+1)+','+part.filter(x=>x[0]!=='-').length+' @@\n'+part.map(x=>x[0]+x[1]).join('\n')+'\n';}return p;}
function apply(s,p,reverse=false){const a=lines(s),ls=lines(p),out=[];let k=2,pos=0;while(k<ls.length){const h=/^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$/.exec(ls[k++]);ok(h,'hunk header');const target=+h[reverse?3:1]-1;ok(target>=pos,'ordered hunk');out.push(...a.slice(pos,target));pos=target;let old=0,neu=0;while(k<ls.length&&!ls[k].startsWith('@@ ')){const l=ls[k++];let tag=l[0];if(reverse)tag=tag==='+'?'-':tag==='-'?'+':tag;if(tag!=='+'){ok(a[pos++]===l.slice(1),'old content');old++;}if(tag!=='-'){out.push(l.slice(1));neu++;}}ok(old===+h[reverse?4:2]&&neu===+h[reverse?2:4],'hunk counts');}out.push(...a.slice(pos));return out.join('\n')+'\n';}
const deltas=[];
for(const [a,b]of [['dummy_bootstrap.py','dummy_bootstrap.py'],[oldLauncher,newLauncher],['durable_lifecycle.py','durable_lifecycle.py'],['asr_loading_adapter.py','asr_loading_adapter.py'],['SOURCE-INPUTS.json','SOURCE-INPUTS.json']]){const before=read(path.join(out,'before',a)).toString('utf8'),after=read(path.join(out,b)).toString('utf8'),d=diff(before,after,'before/'+a,b);ok(apply(before,d)===after&&apply(after,d,true)===before,'complete diff '+b);const name=b.replace(/\.(py|ps1|json)$/,'')+'.diff';write(path.join(out,name),d);deltas.push({path:name,...binding(path.join(out,name))});}
for(const file of ['dummy_bootstrap.py',newLauncher,'SOURCE-INPUTS.json']){let s=read(path.join(out,file)).toString('utf8');for(const e of [...edits[file]].reverse()){ok(s.split(e.to).length-1===e.count,'inverse count '+file);s=s.split(e.to).join(e.from);}const old=file===newLauncher?oldLauncher:file;ok(s===read(path.join(donor,old)).toString('utf8'),'whole inverse '+file);}
json(path.join(out,'DECLARED-EDITS.json'),edits);
json(path.join(out,'SOURCE-PRESERVATION.json'),{scope:newScope,source_names:names,source_count:29,subject_count:28,unchanged_subject_count:26,source_rows:rows,native_metadata:{count:9,text_suffix_unchanged:true,parsed_rows_unchanged:true,paths_accessed:false},bootstrap:binding(path.join(out,'dummy_bootstrap.py')),launcher:{name:newLauncher,...binding(path.join(out,newLauncher))},source_map:binding(path.join(out,'SOURCE-INPUTS.json')),false_template:binding(path.join(out,'ROOT-ADMISSION-TEMPLATE.json')),deltas,whole_inverse_substitutions:true,all_behavioral_receipt_predicates_preserved:true});
console.log(JSON.stringify({kind:'source_only_native_compatibility_preparation',candidate_execution:false,source_count:29,unchanged_subject_count:26,support_metadata_count:9,support_access:false,bootstrap:binding(path.join(out,'dummy_bootstrap.py')),launcher:binding(path.join(out,newLauncher)),map:binding(path.join(out,'SOURCE-INPUTS.json')),template:binding(path.join(out,'ROOT-ADMISSION-TEMPLATE.json')),diffs:deltas,actual_run_or_admission_created:false},null,2));

