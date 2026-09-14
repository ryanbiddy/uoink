import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const dir=path.join(root,'_scratch/interrupted-owner-retirement-repair02');
const base=path.join(root,'docs/library/proof/runtime-owner-native-cancel-2026-09-13/native-preparation');
const out=path.join(root,'_scratch/interrupted-repair02-root-preservation.json');
if(fs.existsSync(out))throw new Error('preserve prior result; fresh check label required');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const method=(s,name)=>{
 const lines=s.replaceAll('\r\n','\n').split('\n');
 const needle='    def '+name+'(';
 const matches=lines.flatMap((l,i)=>l.startsWith(needle)?[i]:[]);
 if(matches.length!==1)throw new Error('unique method '+name);
 const start=matches[0];let end=start+1;
 for(;end<lines.length;end++){const l=lines[end];if(l.trim()&&l.search(/\S/)<=4)break;}
 return lines.slice(start,end).join('\n').trimEnd();
};
const files=['durable_lifecycle.py','generated_adapter_flow.py','generated_journal_setup.py','test_interrupted_owner_retirement.py'];
const bytes=files.map(name=>{const b=fs.readFileSync(path.join(dir,name));return {path:name,bytes:b.length,sha256:hash(b)};});
const checks=[];
for(const [file,names] of [['generated_adapter_flow.py',['_retired','_never_started','completion_evidence','confirm_teardown']],['generated_journal_setup.py',['before_close','before_recovery_close','complete_recovery','complete']]]){
 const a=fs.readFileSync(path.join(base,file),'utf8'),b=fs.readFileSync(path.join(dir,file),'utf8');
 for(const name of names){const same=method(a,name)===method(b,name);checks.push({file,method:name,same_normalized_text:same});}
}
const tests=fs.readFileSync(path.join(dir,'test_interrupted_owner_retirement.py'),'utf8');
const ids=[...tests.matchAll(/^    def (test_[a-z0-9_]+)\(self\):/gm)].map(x=>x[1]);
const required=['test_actual_adapter_interruption_preserves_error_and_quarantine','test_confirmed_idle_owner_retires_and_reconciles_once','test_foreign_stale_active_or_pending_attempt_refuses','test_retained_io_or_uncertain_handle_refuses_without_retirement','test_unobserved_exit_nonempty_job_or_close_failure_retains_custody','test_reentrant_or_clear_failure_preserves_first_error_and_gate'];
const sameIds=JSON.stringify(ids)===JSON.stringify(required);
const result={scope:'Passive text comparison only; no parser, candidate import or execution. This does not validate behavior or syntax.',files:bytes,ordinary_method_checks:checks,test_ids:ids,exact_six_ids:sameIds};
fs.writeFileSync(out,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(result));
if(!sameIds||checks.some(x=>!x.same_normalized_text))process.exitCode=1;
