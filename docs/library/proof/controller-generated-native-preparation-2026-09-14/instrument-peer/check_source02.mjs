import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

// Passive fixed text comparison only. No subject import or support-path access.
const root = 'E:/AI/projects/uoink/checkouts/Yoink-library';
const donor = path.join(root, '_scratch/windows-interrupted-owner-native-proposal02');
const proposed = path.join(root, '_scratch/controller-generated-native-compatibility-proposal01');
const peer = path.join(root, '_scratch/controller-generated-native-compatibility-peer01');
const core = path.join(root, '_scratch/controller-boundary-custody-repair01');
const pins = [];
const raw = p => { const b = fs.readFileSync(p); pins.push({path:p,bytes:b.length,sha256:hash(b)}); return b; };
const hash = b => crypto.createHash('sha256').update(b).digest('hex');
const text = p => raw(p).toString('utf8');
const json = p => JSON.parse(text(p));
const equal = (a,b,label) => assert.deepEqual(a,b,label);
const norm = s => s.replace(/\r\n/g,'\n');
const lines = s => { assert.ok(norm(s).endsWith('\n'),'terminal newline required by fixed deltas'); return norm(s).slice(0,-1).split('\n'); };
function parseDiff(s) {
  const rows = lines(s); assert.ok(rows[0].startsWith('--- ') && rows[1].startsWith('+++ '));
  const hunks=[]; let h;
  for (const row of rows.slice(2)) {
    const m=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)$/.exec(row);
    if(m){ h={oldStart:+m[1],oldCount:m[2]===undefined?1:+m[2],newStart:+m[3],newCount:m[4]===undefined?1:+m[4],body:[]}; hunks.push(h); }
    else { assert.ok(h && /^[ +\-]/.test(row),'only fixed unified body'); h.body.push(row); }
  }
  assert.ok(hunks.length>0); return hunks;
}
function apply(old,hunks,reverse=false){
  let at=0; const out=[];
  for(const h of hunks){
    const start=(reverse?h.newStart:h.oldStart); const pos=start===0?0:start-1;
    assert.ok(pos>=at); out.push(...old.slice(at,pos)); at=pos;
    let consumed=0,produced=0;
    for(const row of h.body){
      let kind=row[0]; if(reverse)kind=kind==='+'?'-':kind==='-'?'+':kind;
      const value=row.slice(1);
      if(kind!=='+' ){equal(old[at++],value,'full context/deletion'); consumed++;}
      if(kind!=='-' ){out.push(value);produced++;}
    }
    equal(consumed,reverse?h.newCount:h.oldCount,'consumed count');
    equal(produced,reverse?h.oldCount:h.newCount,'produced count');
  }
  out.push(...old.slice(at)); return out;
}
const dm=json(path.join(donor,'SOURCE-INPUTS.json'));
const pm=json(path.join(proposed,'SOURCE-INPUTS.json'));
const names=Object.keys(dm.source_sha256);
equal(names.length,29); equal(Object.keys(dm.source_paths),names);
equal(Object.keys(pm.source_sha256),names);equal(Object.keys(pm.source_paths),names);
equal(pm.native_bindings,dm.native_bindings,'nine metadata records only'); equal(Object.keys(pm.native_bindings).length,9);
const replacements={
  'durable_lifecycle.py':'ce69903d93daf41ae3717008f8d0dbd0b3ead7b11662b674eddf43828567b222',
  'asr_loading_adapter.py':'227395c4e1f25f75f13dc950e3b2e222af4a4d8b307a36091908229b58ed0c0f'
};
let unchanged=0; const subjects=[];
for(const name of names){
  const d=raw(path.join(donor,name)), b=raw(path.join(proposed,'before',name)), p=raw(path.join(proposed,name));
  equal(hash(d),dm.source_sha256[name]);equal(b,d,'original before bytes');equal(hash(p),pm.source_sha256[name]);
  equal(pm.source_paths[name],path.win32.join(proposed.replaceAll('/','\\'),name));
  if(replacements[name]){equal(hash(p),replacements[name]);equal(p,raw(path.join(core,name)),'exact reviewed core copy');}
  else if(name!=='dummy_bootstrap.py'){equal(p,d,'unchanged subject');unchanged++;}
  subjects.push({name,donor_sha256:hash(d),proposed_sha256:hash(p),changed:!d.equals(p)});
}
equal(unchanged,26);
const bootstrap=text(path.join(proposed,'dummy_bootstrap.py'));
const launcher=text(path.join(proposed,'run_controller_generated_compatibility01.ps1'));
equal(hash(Buffer.from(bootstrap)), '84881e927563bf68f78ebcd1d26c1a0eae83d9d2f42902426938dd432efae57b');
equal(hash(Buffer.from(launcher)), 'b8318a2129ab129035ff90b3b4d02849a7049aad2e7ae9d7fcceb83698448fe3');
const edits=json(path.join(proposed,'DECLARED-EDITS.json'));
const originals={'dummy_bootstrap.py':'dummy_bootstrap.py','run_controller_generated_compatibility01.ps1':'run_interrupted_owner02.ps1','SOURCE-INPUTS.json':'SOURCE-INPUTS.json'};
const transformations=[];
for(const [name,rules] of Object.entries(edits)){
  const old=text(path.join(donor,originals[name])), current=text(path.join(proposed,name));let forward=old;
  for(const rule of rules){equal(forward.split(rule.from).length-1,rule.count,'literal count');forward=forward.split(rule.from).join(rule.to);}
  equal(forward,current,'exact raw literal reconstruction');
  let reverse=current;
  for(const rule of [...rules].reverse()){equal(reverse.split(rule.to).length-1,rule.count,'inverse literal count');reverse=reverse.split(rule.to).join(rule.from);}
  equal(reverse,old,'exact raw inverse reconstruction');transformations.push({name,rules:rules.length,occurrences:rules.reduce((n,r)=>n+r.count,0),exact_both_directions:true});
}
const diffPairs=[
 ['dummy_bootstrap.py','dummy_bootstrap.py','dummy_bootstrap.diff'],
 ['run_interrupted_owner02.ps1','run_controller_generated_compatibility01.ps1','run_controller_generated_compatibility01.diff'],
 ['SOURCE-INPUTS.json','SOURCE-INPUTS.json','SOURCE-INPUTS.diff'],
 ['durable_lifecycle.py','durable_lifecycle.py','durable_lifecycle.diff'],
 ['asr_loading_adapter.py','asr_loading_adapter.py','asr_loading_adapter.diff']
];
const diffs=[];
for(const [before,after,file] of diffPairs){
  const o=text(path.join(proposed,'before',before)),n=text(path.join(proposed,after)),h=parseDiff(text(path.join(proposed,file)));
  equal(apply(lines(o),h),lines(n),'whole forward diff');equal(apply(lines(n),h,true),lines(o),'whole reverse diff');
  diffs.push({file,hunks:h.length,full_lf_text_forward_reverse:true});
}
const beforeNames=fs.readdirSync(path.join(proposed,'before')).sort();
equal(beforeNames,[...names,'BRIEF.md','NATIVE-PROTOCOL.md','PINS.json','ROOT-ADMISSION-TEMPLATE.json','run_interrupted_owner02.ps1','SOURCE-INPUTS.json'].sort());
for(const name of beforeNames.filter(n=>!names.includes(n)))equal(raw(path.join(proposed,'before',name)),raw(path.join(donor,name)),'retained before control');
const template=json(path.join(proposed,'ROOT-ADMISSION-TEMPLATE.json'));
equal(template.root_reviewed,false);equal(template.scope,'generated-controller-core-start-compatibility-only');
equal(template.operation_mode,'drain');equal(template.case,'positive');
equal(template.run_path,path.win32.join(root.replaceAll('/','\\'),'_scratch','controller-generated-native-compatibility01'));
equal(template.source_inputs_sha256,hash(fs.readFileSync(path.join(proposed,'SOURCE-INPUTS.json'))));
equal(template.launcher_sha256,hash(Buffer.from(launcher)));
assert.ok(!fs.existsSync(path.join(proposed,'ROOT-ADMISSION-drain.json')),'no admission');
assert.ok(!fs.existsSync(template.run_path),'fresh run absent');
const listed=bootstrap.match(/MODULES = \(([\s\S]*?)\n\)/)[1].match(/"[a-z0-9_]+"/g).map(s=>s.slice(1,-1)+'.py');
equal([...listed,'dummy_bootstrap.py'],names,'exact module order and closure');
const launcherNames=launcher.match(/\$taskSourceNames=@\(([^\r\n]+)\)/)[1].match(/'[^']+'/g).map(s=>s.slice(1,-1));
equal(launcherNames,names,'launcher closure');
const beforeAfter=pins.map(row=>({...row,after_sha256:hash(fs.readFileSync(row.path))}));
assert.ok(beforeAfter.every(row=>row.sha256===row.after_sha256));
const result={scope:'PASSIVE SOURCE COMPARISON ONLY',subject_executed:false,support_paths_accessed:false,
  source_count:29,unchanged_subject_count:unchanged,exact_core_replacements:replacements,native_metadata_rows:9,
  transformations,diffs,retained_before_files:beforeNames.length,false_template:true,actual_admission_absent:true,new_run_absent:true,
  source_module_order:names,subjects,bindings:beforeAfter};
fs.writeFileSync(path.join(peer,'CHECK-RESULT.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({status:'PASS',source_count:29,unchanged_subjects:unchanged,diff_pairs:diffs.length,before_files:beforeNames.length,bindings:beforeAfter.length,subject_executed:false,support_access:false}));
