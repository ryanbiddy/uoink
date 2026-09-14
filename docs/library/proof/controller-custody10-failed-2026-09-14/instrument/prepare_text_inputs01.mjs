// Data-only text derivation. Never imports or invokes candidate Python.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const proposal=path.join(root,'_scratch/controller-custody-qualification-proposal01');
const donor=path.join(root,'_scratch/controller-stage-qualification-proposal01');
const planPath=path.join(root,'_scratch/controller-custody-instrument-plan01/SOURCE-INPUTS.json');
function insist(v,m){if(!v)throw Error(m);}
function sha(b){return crypto.createHash('sha256').update(b).digest('hex');}
function read(p){const s=fs.lstatSync(p);insist(s.isFile()&&!s.isSymbolicLink()&&s.size<=1048576,'fixed plain text '+p);return fs.readFileSync(p);}
function write(p,b){fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,b,{flag:'wx'});}
function json(p,v){write(p,JSON.stringify(v,null,2)+'\n');}
function binding(p){const b=read(p);return {bytes:b.length,sha256:sha(b)};}
const plan=JSON.parse(read(planPath));
insist(sha(read(planPath))==='79c4db91184884b00aaccdc881b68e888714082460d77d4036a51f079c60ef07','frozen plan map');
const briefPath=path.join(root,'docs/library/CONTROLLER-CUSTODY-QUALIFICATION-BRIEF-2026-09-14.md');
insist(sha(read(briefPath))==='f15dff6182f0f9a9a248f3744dc57ff886329f984bd7ba1bad728abbe2134970','canonical brief');
for(const r of plan.donor){const b=read(path.join(root,r.path));insist(b.length===r.bytes&&sha(b)===r.sha256,'donor '+r.path);}
for(const r of plan.canonical_load_order){const b=read(r.path);insist(b.length===r.bytes&&sha(b)===r.sha256,'subject '+r.module);}
const expectedBytes=read(path.join(root,plan.expected.path));
insist(sha(expectedBytes)===plan.expected.sha256,'expected bytes');
const expected=JSON.parse(expectedBytes);
insist(expected.length===10&&JSON.stringify(expected)===JSON.stringify(plan.expected.cases.map(x=>x.id)),'ten case IDs');
const before=['qualify_windows_reservations.py','run_preflight01.ps1','QUALIFICATION-PROTOCOL.md','PINS.json','EXPECTED-CASES.json','SOURCE-INPUTS.json','BRIEF.md'];
for(const name of before)write(path.join(proposal,'before',name),read(path.join(donor,name)));
write(path.join(proposal,'before','accepted-PLAN.md'),read(path.join(root,'_scratch/controller-custody-instrument-plan01/PLAN.md')));
write(path.join(proposal,'before','accepted-plan-SOURCE-INPUTS.json'),read(planPath));
write(path.join(proposal,'before','canonical-qualification-BRIEF.md'),read(briefPath));
for(const r of plan.canonical_load_order)write(path.join(proposal,r.module+'.py'),read(r.path));
write(path.join(proposal,'EXPECTED-CASES.json'),expectedBytes);
const cp=plan.capture_plan;
function pyTuple(a){return '('+a.map(x=>JSON.stringify(x)).join(', ')+(a.length===1?',':'')+')';}
const block = [
'def startup_pair_valid():',
'    resolver = LOADED["trusted_asr_resolver"]',
'    adapter = LOADED["asr_loading_adapter"]',
'    durable = LOADED["durable_lifecycle"]',
'    lifecycle = LOADED["snapshot_lifecycle"]',
'    reservations = LOADED["snapshot_reservations"]',
'    return (all(sys.modules.get(name) is module for name, module in LOADED.items())',
'        and adapter.resolver is resolver and adapter._STARTUP_RESOLVER is resolver',
'        and resolver.REAL_APPROVAL is None',
'        and all(getattr(adapter, name) is None for name in AUTHORITY_NAMES)',
'        and adapter._STARTUP_LOAD is resolver.load_manifest',
'        and adapter._STARTUP_ADMIT is resolver.admit_snapshot',
'        and adapter._STARTUP_BIND is resolver.bind_for_constructor',
'        and adapter._STARTUP_RELEASE is adapter._release',
'        and adapter._STARTUP_PROFILE is adapter._runtime_profile',
'        and durable._FIXED_FACTORY_START_CHECK is durable._require_factory_start',
'        and adapter.DurableOwnedRuntimeFactory is durable.DurableOwnedRuntimeFactory',
'        and adapter.DurableSnapshotLifecycle is durable.DurableSnapshotLifecycle',
'        and adapter._DurableKernel is durable._DurableKernel',
'        and adapter._DurableLease is durable._DurableLease',
'        and adapter.OwnedSession is lifecycle.OwnedSession',
'        and adapter._NativePermit is lifecycle._NativePermit',
'        and adapter.Phase is lifecycle.Phase',
'        and adapter.Reservation is reservations.Reservation)',
'',
'STARTUP_VALIDATOR = startup_pair_valid',
'STARTUP_ENTRY_VALID = False',
'STARTUP_FUNCTIONS = ()',
'STARTUP_TYPES = ()',
'STARTUP_METHODS = ()',
'STARTUP_KERNEL_TYPE = None',
'BOUNDARY_FUNCTIONS = None',
'FACTORY_CHECK = None',
'REAL_ENTRIES = ()',
'BOUNDARY_NAMES = '+pyTuple(cp.controller_tuple.names),
'for name in MODULES:',
'    module = types.ModuleType(name)',
'    module.__file__ = os.path.join(HERE, name + ".py")',
'    sys.modules[name] = module',
'    if name == "test_reservations":',
'        # Capture original canonical subjects before any fixture/test definitions.',
'        STARTUP_ENTRY_VALID = startup_pair_valid()',
'        assert STARTUP_ENTRY_VALID',
'        adapter = LOADED["asr_loading_adapter"]',
'        durable = LOADED["durable_lifecycle"]',
'        STARTUP_KERNEL_TYPE = durable._DurableKernel',
'        BOUNDARY_FUNCTIONS = adapter._CONTROLLER_BOUNDARY_FUNCTIONS',
'        FACTORY_CHECK = durable._FIXED_FACTORY_START_CHECK',
'        assert type(BOUNDARY_FUNCTIONS) is tuple and len(BOUNDARY_FUNCTIONS) == 19',
'        assert all(function is getattr(adapter, name) for name, function in zip(BOUNDARY_NAMES, BOUNDARY_FUNCTIONS))',
'        STARTUP_FUNCTIONS = tuple(',
'            (LOADED[module_name], method, getattr(LOADED[module_name], method))',
'            for module_name, methods in (',
'                ("trusted_asr_resolver", '+pyTuple(cp.resolver_functions)+'),',
'                ("asr_loading_adapter", '+pyTuple(cp.adapter_functions)+'),',
'                ("durable_lifecycle", ("_require_factory_start",)),',
'            ) for method in methods)',
'        assert len(STARTUP_FUNCTIONS) == 38',
'        STARTUP_TYPES = tuple(',
'            (LOADED[module_name], name, getattr(LOADED[module_name], name))',
'            for module_name, names in (',
...Object.entries(cp.class_identities).map(([m,n])=>'                ('+JSON.stringify(m)+', '+pyTuple(n)+'),'),
'            ) for name in names)',
'        assert len(STARTUP_TYPES) == 12',
'        STARTUP_METHODS = tuple(',
'            (owner, name, getattr(owner, name))',
'            for owner, names in (',
'                (durable.DurableOwnedRuntimeFactory, ("__init__", "open_owned_session")),',
'                (durable._DurableKernel, ("__init__", "start_owned_worker", "stop_unpublished")),',
'                (durable.DurableSnapshotLifecycle, ("_flush_quarantine",)),',
'            ) for name in names)',
'        assert len(STARTUP_METHODS) == 6',
'        REAL_ENTRIES = ((LOADED["reservation_file_port"], "real_journal_port", LOADED["reservation_file_port"].real_journal_port),',
'                        (LOADED["snapshot_reservations"], "real_reservation_service", LOADED["snapshot_reservations"].real_reservation_service))',
'    exec(compile(RAW[name + ".py"], module.__file__, "exec"), module.__dict__)',
'    LOADED[name] = module',
'',
].join('\n');
const guard=[
'    "real_entrypoints_unchanged": len(REAL_ENTRIES) == 2',
'        and all(getattr(module, name) is function for module, name, function in REAL_ENTRIES)',
'        and STARTUP_ENTRY_VALID and startup_pair_valid is STARTUP_VALIDATOR and startup_pair_valid()',
'        and len(STARTUP_FUNCTIONS) == 38',
'        and all(getattr(module, name) is function for module, name, function in STARTUP_FUNCTIONS)',
'        and len(STARTUP_TYPES) == 12',
'        and all(getattr(module, name) is original for module, name, original in STARTUP_TYPES)',
'        and len(STARTUP_METHODS) == 6',
'        and all(getattr(owner, name) is original for owner, name, original in STARTUP_METHODS)',
'        and LOADED["durable_lifecycle"]._DurableKernel is STARTUP_KERNEL_TYPE',
'        and LOADED["asr_loading_adapter"]._DurableKernel is STARTUP_KERNEL_TYPE',
'        and LOADED["asr_loading_adapter"]._CONTROLLER_BOUNDARY_FUNCTIONS is BOUNDARY_FUNCTIONS',
'        and type(BOUNDARY_FUNCTIONS) is tuple and len(BOUNDARY_FUNCTIONS) == 19',
'        and all(function is getattr(LOADED["asr_loading_adapter"], name)',
'                for name, function in zip(BOUNDARY_NAMES, BOUNDARY_FUNCTIONS))',
'        and LOADED["durable_lifecycle"]._FIXED_FACTORY_START_CHECK is FACTORY_CHECK',
'        and LOADED["durable_lifecycle"]._require_factory_start is FACTORY_CHECK,',
].join('\n');
let q=read(path.join(donor,'qualify_windows_reservations.py')).toString('utf8');
const qBefore=q;
const edits=[];
function replaceExact(text,from,to,reason){insist(text.split(from).length===2,'one occurrence: '+reason);edits.push({from,to,reason});return text.replace(from,to);}
const oldModule=q.match(/^MODULES = .+$/m)[0];
q=replaceExact(q,oldModule,'MODULES = '+pyTuple(plan.canonical_load_order.map(x=>x.module)),'Nine canonical modules; fixed fixture-map order.');
q=replaceExact(q,'len(EXPECTED) == 95 and len(set(EXPECTED)) == 95','len(EXPECTED) == 10 and len(set(EXPECTED)) == 10','Exact ten cases.');
const start=q.indexOf('def startup_pair_valid():'),end=q.indexOf('\nclass Results',start);
q=replaceExact(q,q.slice(start,end),block,'Canonical before-test fixed captures and exact tuple/type/method anchors; remove isolated alias and omitted native modules.');
const gs=q.indexOf('    "real_entrypoints_unchanged":'),ge=q.indexOf('\n}',gs);
q=replaceExact(q,q.slice(gs,ge),guard,'Final original captures and authority restoration; same tenth guard key.');
q=replaceExact(q,'passed == 95 and skipped == 0','passed == 10 and skipped == 0','Ten-case result count.');
q=replaceExact(q,'Original81 plus14 controller worker-stage cases; isolated synthetic authority and fake services only; real worker remains closed','Ten canonical controller custody cases; generated metadata and fake lower services only; generated-start and real worker qualification remain closed','Precise bounded result scope.');
write(path.join(proposal,'qualify_windows_reservations.py'),q);
json(path.join(proposal,'qualifier-declared-edits.json'),edits);
let launch=read(path.join(donor,'run_preflight01.ps1')).toString('utf8');
const launchBefore=launch; const launchEdits=[];
function many(text,from,to,count,reason,ledger=launchEdits){insist(text.split(from).length-1===count,'fixed occurrence count '+from);ledger.push({from,to,count,reason});return text.split(from).join(to);}
launch=many(launch,'controller-stage-fake01','controller-custody-fake01',5,'Fresh exact author label.');
launch=many(launch,'-ne 29','-ne 15',2,'Fifteen parent rows.');
launch=many(launch,'Exact 29-entry','Exact 15-entry',1,'Map count diagnostic.');
launch=many(launch,'-eq 95','-eq 10',3,'Ten-case outer predicates.');
launch=many(launch,': 95 passed',': 10 passed',1,'Bounded successful-result label.');
write(path.join(proposal,'run_preflight01.ps1'),launch);
json(path.join(proposal,'launcher-declared-edits.json'),launchEdits);
const brief='This is source-only preparation under the canonical controller custody qualification brief at checkpoint71df9d34327357be32510758ffe0cbada11ede95. The nine subject modules and ten ordered cases remain byte-identical to their accepted source bindings. The104 proposed subtest iterations are not results.\n\nThe stage95 instrument contributes fixed guards and receipt mechanics. It is not a compatibility test donor: no old case is selected or modified here. SOURCE-INPUTS.json binds the exact module order, capture plan, source origins and output membership. Parent PINS has15 inputs; child reads11 texts. Both concrete input copies require separate root review and admission. Templates remain false.\n\nThe author copy label is controller-custody-fake01. The confirmation label is controller-custody-confirmation01. Only five launcher label literals and their dependent pins/templates differ. This proposal is preparation and must not itself be invoked.\n\nFull latest generated-start compatibility remains required separately. Child transport, namespace, engine, PCM, native/model and release qualification are not claimed. No Python or subject execution occurs in preparation.\n';
const protocol='This prepared instrument loads nine canonical modules in the exact SOURCE-INPUTS order. Qualifier and EXPECTED make11 child texts; launcher, BRIEF, protocol and SOURCE-INPUTS make15 parent inputs. Only the ten source-ordered EXPECTED methods are selected through loadTestsFromName(relative_name, LOADED[module_name]). Proposed subtest counts are0,26,4,4,48,4,4,4,8,2; total104 and maximum48, not observations.\n\nThe early registry and twelve metadata traps, audit/import/content closure, heavy-root refusals, bounded captures and ten guard keys are retained. No stdlib preload is added. Before the first fixture definitions, retain38 canonical function attributes,12 class identities,6 method identities, the exact19-entry controller tuple, the fixed durable factory guard and imported type relationships. Check those original references and absent configured authority after the suite. Failed inert custody is retained; do not demand an empty registry. No resolver alias or fixture-provided positive validator is loaded.\n\nAfter separate root review and admission, each fresh copy uses C:\\Python314\\python.exe -I -S -B. Root must set lexical IG_FORBIDDEN_LIVE before the outer PowerShell host starts; the wrapper also sets it before child startup. Keep the existing environment-name removal, value privacy,1MiB child text,8192-character capture,64-subtest-per-case and262144-byte receipt limits.\n\nThe wrapper checks all15 originals/copies plus PINS/admission/launcher controls before and after. It records global:LASTEXITCODE immediately and writes native-exit.json before postchecks. Successful fixed membership is23 files:15 copied parent inputs, copied PINS and admission, then plan.json,stdout.json,stderr.log,native-exit.json,input-check.json,exit.json. Preserve any actual launch-failure.json and partial receipts on failure; pre-try failures need their raw outer object. Never infer a child exit.\n\nAcceptance requires ten ordered passing cases with zero failures/skips, all ten guards true, empty captures/stderr/denials, no heavy roots, unchanged input/control bytes and actual child/outer exits0. Retain and compare full ordered case/subtest objects, all11 child hashes and complete source/control receipts across the two copies.104 subtests remain expected source counts until observed. Save each initial/poll/final raw tool object immediately outside pinned inputs.\n\nAuthor label controller-custody-fake01 and confirmation label controller-custody-confirmation01 have separate exact false templates. Both copies preserve all11 child inputs and fourteen non-launcher parent bytes. Confirmation changes only five launcher labels and its dependent control pins. One admission authorizes neither a second run nor a retry. A failure stops the attempt; no automatic rerun or assertion change.\n\nThere is no hard execution deadline in the inherited wrapper. This controller-only unit does not qualify the separate latest generated-start family or native, model, namespace, PCM or release routes.\n';
write(path.join(proposal,'BRIEF.md'),brief.replace(/checkpoint71/g,'checkpoint 71').replace(/The104/g,'The 104').replace(/has15/g,'has 15').replace(/reads11/g,'reads 11'));
write(path.join(proposal,'QUALIFICATION-PROTOCOL.md'),protocol.replace(/\bmake11/g,'make 11').replace(/\bmake15/g,'make 15').replace(/are0/g,'are 0').replace(/total104/g,'total 104').replace(/maximum48/g,'maximum 48').replace(/retain38/g,'retain 38').replace(/,12 class/g,', 12 class').replace(/,6 method/g,', 6 method').replace(/exact19/g,'exact 19').replace(/privacy,1MiB/g,'privacy, 1 MiB').replace(/,8192/g,', 8192').replace(/,64-subtest/g,', 64-subtest').replace(/and262144/g,'and 262144').replace(/all15/g,'all 15').replace(/is23/g,'is 23').replace(/files:15/g,'files: 15').replace(/exits0/g,'exits 0').replace(/all11/g,'all 11').replace(/\.104/g,'. 104'));
const sourceMap={schema:'controller-custody-qualification-source-inputs.v1',checkpoint:'71df9d34327357be32510758ffe0cbada11ede95',scope:'generated_bytes_and_fake_ports_only',modules:plan.canonical_load_order,expected:plan.expected,donor:plan.donor,capture_plan:plan.capture_plan,guard_names:plan.guard_names,child_names:plan.future_child_names,parent_names:plan.future_parent_names,successful_output_names:plan.future_success_output_names,labels:{author:plan.future_author.label,confirmation:plan.future_confirmation.label}};
json(path.join(proposal,'SOURCE-INPUTS.json'),sourceMap);
function lines(text){insist(text.endsWith('\n'),'final newline');return text.slice(0,-1).split('\n');}
function patch(a,b,name){const A=lines(a),B=lines(b),n=A.length,m=B.length,dp=Array.from({length:n+1},()=>new Uint16Array(m+1));for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i][j]=A[i]===B[j]?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);const ops=[];let i=0,j=0;while(i<n||j<m){if(i<n&&j<m&&A[i]===B[j]){ops.push([' ',A[i++]]);j++;}else if(j<m&&(i===n||dp[i][j+1]>dp[i+1][j]))ops.push(['+',B[j++]]);else ops.push(['-',A[i++]]);}const changes=ops.map((x,k)=>x[0]!==' '?k:-1).filter(k=>k>=0),ranges=[];for(const k of changes){const st=Math.max(0,k-3),en=Math.min(ops.length,k+4);if(ranges.length&&st<=ranges.at(-1)[1])ranges.at(-1)[1]=en;else ranges.push([st,en]);}let out='--- before/'+name+'\n+++ '+name+'\n';for(const [s,e]of ranges){const pre=ops.slice(0,s),part=ops.slice(s,e);const oldStart=pre.filter(x=>x[0]!=='+').length+1,newStart=pre.filter(x=>x[0]!=='-').length+1;out+='@@ -'+oldStart+','+part.filter(x=>x[0]!=='+').length+' +'+newStart+','+part.filter(x=>x[0]!=='-').length+' @@\n'+part.map(x=>x[0]+x[1]).join('\n')+'\n';}return out;}
function applyPatch(text,p,reverse=false){const a=lines(text),pl=lines(p),out=[];let pos=0,k=2;while(k<pl.length){const h=/^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$/.exec(pl[k++]);insist(h,'hunk header');const at=Number(h[reverse?3:1])-1;out.push(...a.slice(pos,at));pos=at;let old=0,neu=0;while(k<pl.length&&!pl[k].startsWith('@@ ')){const line=pl[k++],tag=reverse?(line[0]==='+'?'-':line[0]==='-'?'+':' '):line[0],v=line.slice(1);if(tag!=='+' ){insist(a[pos++]===v,'hunk old context');old++;}if(tag!=='-'){out.push(v);neu++;}}insist(old===Number(h[reverse?4:2])&&neu===Number(h[reverse?2:4]),'hunk counts');}out.push(...a.slice(pos));return out.join('\n')+'\n';}
for(const [name,a,b]of [['qualify_windows_reservations.py',qBefore,q],['run_preflight01.ps1',launchBefore,launch]]){const p=patch(a,b,name);insist(applyPatch(a,p)===b&&applyPatch(b,p,true)===a,'full diff relation '+name);write(path.join(proposal,name.replace(/\.(py|ps1)$/,'')+'.diff'),p);}
function pinsAt(dir){const files=plan.future_parent_names.map(p=>({path:p,...binding(path.join(dir,p))}));return {schema:'uoink.controller-custody-qualification-parent-inputs.v1',count:15,files};}
const pins=pinsAt(proposal);json(path.join(proposal,'PINS.json'),pins);
function template(dir,label){json(path.join(dir,'ROOT-ADMISSION.template.json'),{approved:false,label,pins_sha256:binding(path.join(dir,'PINS.json')).sha256,scope:'generated_bytes_and_fake_ports_only'});}
template(proposal,plan.future_author.label);
const copies=[];
for(const spec of [plan.future_author,plan.future_confirmation]){
 const dir=path.join(root,spec.directory);insist(!fs.existsSync(dir),'fresh copy '+dir);fs.mkdirSync(dir);
 for(const row of pins.files){let b=read(path.join(proposal,row.path));if(spec===plan.future_confirmation&&row.path==='run_preflight01.ps1'){const s=b.toString('utf8');insist(s.split(plan.future_author.label).length-1===5,'five confirmation labels');b=Buffer.from(s.split(plan.future_author.label).join(spec.label));}write(path.join(dir,row.path),b);}
 json(path.join(dir,'PINS.json'),pinsAt(dir));template(dir,spec.label);
 const relations=pins.files.map(row=>{const a=read(path.join(proposal,row.path)),b=read(path.join(dir,row.path));const identical=a.equals(b);insist(identical||spec===plan.future_confirmation&&row.path==='run_preflight01.ps1','only confirmation launcher differs');return {path:row.path,identical,...binding(path.join(dir,row.path))};});
 copies.push({directory:spec.directory,label:spec.label,pins:binding(path.join(dir,'PINS.json')),false_template:binding(path.join(dir,'ROOT-ADMISSION.template.json')),files:relations});
}
const conf=path.join(root,plan.future_confirmation.directory,'run_preflight01.ps1'),confText=read(conf).toString('utf8'),confPatch=patch(launch,confText,'run_preflight01.ps1');
insist(applyPatch(launch,confPatch)===confText&&applyPatch(confText,confPatch,true)===launch,'confirmation full delta');
write(path.join(proposal,'confirmation-launcher.diff'),confPatch);
json(path.join(proposal,'COPY-RELATION.json'),{scope:'data_only_unexecuted_input_copy',proposal_pins:binding(path.join(proposal,'PINS.json')),copies,only_confirmation_change:'Five fixed launcher label literals; derived launcher/PINS/template bindings.'});
write(path.join(proposal,'SOURCE-REASONS.md'),'This derivative implements the accepted plan with six qualifier replacement blocks and five launcher replacement rules. The early startup/registry/preload block, audit and metadata closure, capture implementation, Results, explicit selector and nine unchanged guard predicates remain donor bytes. The tenth guard adapts the finite canonical captures. Only counts, fixed labels and reported scope change elsewhere.\n\nThe exact19-entry tuple, fixed factory anchor,38 function attributes,12 classes,6 methods and two remaining refusal entries are captured before fixture definitions. Type aliases and resolver hooks are checked after all cases. The fixture may retain failed custody; no registry clearing is introduced. Generated-adapter imports remain closed.\n\nBoth unified source patches and the confirmation label patch reconstruct the complete old and new texts in both directions. Original donor inputs and the accepted plan/brief are retained under before. No subject source or assertion was changed. All preparation is Node text/data work; no Python or candidate command runs.\n'.replace(/exact19/g,'exact 19').replace(/anchor,38/g,'anchor, 38').replace(/attributes,12/g,'attributes, 12').replace(/classes,6/g,'classes, 6'));
const result={scope:'data_only_qualification_preparation',candidate_execution:false,modules:9,child_inputs:11,parent_inputs:15,cases:10,proposed_subtests:104,qualifier:binding(path.join(proposal,'qualify_windows_reservations.py')),launcher:binding(path.join(proposal,'run_preflight01.ps1')),pins:binding(path.join(proposal,'PINS.json')),source_map:binding(path.join(proposal,'SOURCE-INPUTS.json')),copies:copies.map(x=>({directory:x.directory,label:x.label,pins:x.pins,false_template:x.false_template})),full_forward_reverse_diffs:true,actual_admissions_created:false};
json(path.join(proposal,'PREPARATION-RESULT.json'),result);console.log(JSON.stringify(result,null,2));

