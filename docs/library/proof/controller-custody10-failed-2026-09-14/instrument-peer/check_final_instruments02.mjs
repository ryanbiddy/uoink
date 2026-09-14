import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',dir=path.join(root,'_scratch/controller-custody-qualification-proposal01'),out=path.join(root,'_scratch/controller-custody-instrument-peer01');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'), seen=new Map();
function read(p){const st=fs.lstatSync(p);if(!st.isFile()||st.isSymbolicLink())throw Error('plain fixed input required');const b=fs.readFileSync(p);if(!b.equals(Buffer.from(b.toString('utf8'))))throw Error('UTF8 required');seen.set(p,{bytes:b.length,sha256:sha(b)});return b;}
const txt=p=>read(p).toString('utf8').replace(/\r\n/g,'\n');
const pin=(p,h)=>{const b=read(p);if(sha(b)!==h)throw Error('fixed hash '+p);return b;};
const q=pin(path.join(dir,'qualify_windows_reservations.py'),'c0a51539cbb3aa7f89e48fb9711827fc7965c8326aed55d63875a69b1d75cac0');
const l=pin(path.join(dir,'run_preflight01.ps1'),'668cf992f7336d451ef892cc68afd63ce1b3a929dfb57565e48170e914bb44a1');
const map=JSON.parse(pin(path.join(dir,'SOURCE-INPUTS.json'),'403d9c9f6aa36d8bffd94220424c37beb486c9da49aef813e1c1d8edf7153039'));
const plan=JSON.parse(read(path.join(root,'_scratch/controller-custody-instrument-plan01/SOURCE-INPUTS.json')));
const fixture=JSON.parse(read(path.join(root,'_scratch/controller-boundary-fixture-repair01/SOURCE-INPUTS.json')));
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const qText=q.toString('utf8').replace(/\r\n/g,'\n'), lText=l.toString('utf8').replace(/\r\n/g,'\n');
for(const[name,b]of [['snapshot-qualify_windows_reservations.py',q],['snapshot-run_preflight01.ps1',l]]){const p=path.join(out,name);if(!fs.readFileSync(p).equals(b))throw Error('original snapshot changed');}
if(!equal(map.modules.map(x=>x.module),fixture.modules.map(x=>x.module)))throw Error('module order');
const modules=JSON.parse('['+/^MODULES = \((.+)\)$/m.exec(qText)[1]+']');
if(!equal(modules,map.modules.map(x=>x.module))||modules.length!==9)throw Error('qualifier closure');
if(!equal(map.child_names,[...modules.map(x=>x+'.py'),'qualify_windows_reservations.py','EXPECTED-CASES.json'])||map.child_names.length!==11)throw Error('child names');
if(!equal(map.parent_names,plan.future_parent_names)||!equal(map.successful_output_names,plan.future_success_output_names)||map.successful_output_names.length!==23)throw Error('membership plan');
if(!equal(map.capture_plan,plan.capture_plan)||!equal(map.guard_names,plan.guard_names))throw Error('capture/guard plan');
for(const row of [...map.modules,...map.donor]){const p=path.isAbsolute(row.path)?row.path:path.join(root,row.path),b=read(p);if(b.length!==row.bytes||sha(b)!==row.sha256)throw Error('origin binding');if(row.module&&!b.equals(read(path.join(dir,row.module+'.py'))))throw Error('source copy');}
const ids=JSON.parse(read(path.join(dir,'EXPECTED-CASES.json')));
if(!equal(ids,map.expected.cases.map(x=>x.id))||!equal(ids,JSON.parse(read(path.join(root,map.expected.path))))||ids.length!==10)throw Error('case identity');
function apply(text,diff,reverse){
 const lines=text?text.slice(0,-1).split('\n'):[],d=diff.trimEnd().split('\n');
 let i=d.findIndex(x=>x.startsWith('--- '));if(i<0||!d[i+1].startsWith('+++ '))throw Error('headers');i+=2;
 const result=[];let at=0;
 while(i<d.length){const m=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(d[i++]);if(!m)throw Error('hunk');
 let start=+(reverse?m[3]:m[1]),n=+(reverse?(m[4]??1):(m[2]??1)),nn=+(reverse?(m[2]??1):(m[4]??1));start-=n?1:0;
 if(start<at||start>lines.length)throw Error('order');while(at<start)result.push(lines[at++]);
 let got=0,added=0;
 while(i<d.length&&!d[i].startsWith('@@ ')){let tag=d[i][0],body=d[i++].slice(1);if(reverse)tag=tag==='+'?'-':tag==='-'?'+':tag;
 if(![' ','+','-'].includes(tag))throw Error('prefix');if(tag!=='+'){if(lines[at++]!==body)throw Error('context');got++;}if(tag!=='-'){result.push(body);added++;}}
 if(got!==n||added!==nn)throw Error('counts');}
 result.push(...lines.slice(at));return result.length?result.join('\n')+'\n':'';
}
const differences=[];
for(const [name,diff,edits]of [['qualify_windows_reservations.py','qualify_windows_reservations.diff','qualifier-declared-edits.json'],['run_preflight01.ps1','run_preflight01.diff','launcher-declared-edits.json']]){
 const before=txt(path.join(dir,'before',name)),after=txt(path.join(dir,name)),delta=txt(path.join(dir,diff));
 const donor=txt(path.join(root,'_scratch/controller-stage-qualification-proposal01',name));if(before!==donor)throw Error('before donor differs');
 if(apply(before,delta,false)!==after||apply(after,delta,true)!==before)throw Error('diff reconstruction');
 const declarations=JSON.parse(read(path.join(dir,edits)));let forward=before,reverse=after;const applied=[];
 for(const e of declarations){const count=e.count??1;if(forward.split(e.from).length-1!==count)throw Error('declared count');let cursor=0;for(let k=0;k<count;k++){const at=forward.indexOf(e.from,cursor);if(at<0)throw Error('exact original occurrence');forward=forward.slice(0,at)+e.to+forward.slice(at+e.from.length);applied.push({at,old:e.from,next:e.to});cursor=at+e.to.length;}}
 for(const e of applied.reverse()){if(reverse.slice(e.at,e.at+e.next.length)!==e.next)throw Error('recorded replacement span');reverse=reverse.slice(0,e.at)+e.old+reverse.slice(e.at+e.next.length);}
 if(forward!==after||reverse!==before)throw Error('declared reconstruction');
 differences.push({name,delta_sha256:seen.get(path.join(dir,diff)).sha256,forward:true,reverse:true,declared_edits:declarations.length});
}
const relation=JSON.parse(read(path.join(dir,'COPY-RELATION.json'))),copies=[];
for(const [copyIndex,entry] of relation.copies.entries()){
 const base=path.join(root,entry.directory),pinsBytes=read(path.join(base,'PINS.json')),pins=JSON.parse(pinsBytes);
 if(sha(pinsBytes)!==entry.pins.sha256||pins.count!==15||pins.files.length!==15||!equal(pins.files.map(r=>r.path),map.parent_names))throw Error('copy pins');
 const listing=fs.readdirSync(base).sort(),expected=[...map.parent_names,'PINS.json','ROOT-ADMISSION.template.json'].sort();if(!equal(listing,expected))throw Error('copy output/admission unexpected');
 for(const row of pins.files){const b=read(path.join(base,row.path));if(b.length!==row.bytes||sha(b)!==row.sha256)throw Error('copy row');
  const proposal=read(path.join(dir,row.path));if(row.path==='run_preflight01.ps1'&&copyIndex===1){if(lText.split('controller-custody-fake01').length-1!==5||b.toString('utf8').replace(/\r\n/g,'\n')!==lText.replaceAll('controller-custody-fake01','controller-custody-confirmation01'))throw Error('confirmation labels');}else if(!b.equals(proposal))throw Error('unexpected copy delta');}
 const templateBytes=read(path.join(base,'ROOT-ADMISSION.template.json')),template=JSON.parse(templateBytes);
 if(sha(templateBytes)!==entry.false_template.sha256||template.approved!==false||template.label!==entry.label||template.pins_sha256!==sha(pinsBytes)||template.scope!=='generated_bytes_and_fake_ports_only')throw Error('false admission');
 copies.push({directory:entry.directory,pins_sha256:sha(pinsBytes),false_template_sha256:sha(templateBytes),flat_inputs:15,files:listing.length,child_inputs_identical:11,non_launcher_parent_identical:14,no_admission_or_run:true});
}
const confirmation=txt(path.join(root,relation.copies[1].directory,'run_preflight01.ps1')),delta=txt(path.join(dir,'confirmation-launcher.diff'));
if(apply(lText,delta,false)!==confirmation||apply(confirmation,delta,true)!==lText)throw Error('confirmation full diff');
const proposalPins=read(path.join(dir,'PINS.json'));if(sha(proposalPins)!==relation.proposal_pins.sha256||!proposalPins.equals(read(path.join(root,relation.copies[0].directory,'PINS.json'))))throw Error('proposal pins');
for(const[p,b]of seen){const current=fs.readFileSync(p);if(current.length!==b.bytes||sha(current)!==b.sha256)throw Error('input changed');}
const result={scope:'passive instrument source/diff/copy review only',bindings:[...seen].map(([path,b])=>({path,...b})),differences,confirmation_diff_forward_reverse:true,canonical_modules:9,child_inputs:11,parent_inputs:15,success_membership:23,ordered_cases:ids,copy_checks:copies,candidate_executed:false};
fs.writeFileSync(path.join(out,'FINAL-BINDINGS.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({bindings:seen.size,source_diffs:2,confirmation_diff:1,declared_edits:differences.map(d=>d.declared_edits),canonical_modules:9,child_inputs:11,parent_inputs:15,cases:ids.length,copies,unchanged:true,bindings_sha256:sha(fs.readFileSync(path.join(out,'FINAL-BINDINGS.json'))),candidate_executed:false},null,2));

