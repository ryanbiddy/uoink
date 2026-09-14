import fs from 'node:fs';import path from 'node:path';
const dir='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary-custody-repair01';
const prior=fs.readFileSync(path.join(dir,'write_and_check_diffs02.mjs'),'utf8');
let next=prior.slice(0,prior.indexOf('const diffs=['))+`const diffs=[
 writeDiff('before/accepted-durable_lifecycle.py','durable_lifecycle.py','durable_lifecycle.from-accepted.final03.diff'),
 writeDiff('before/accepted-asr_loading_adapter.py','asr_loading_adapter.py','asr_loading_adapter.from-accepted.final03.diff'),
 writeDiff('before/rejected-durable_lifecycle.py','durable_lifecycle.py','durable_lifecycle.from-rejected.final03.diff'),
 writeDiff('before/rejected-asr_loading_adapter.py','asr_loading_adapter.py','asr_loading_adapter.from-rejected.final03.diff'),
 writeDiff('before/pre-review-cleanup03-durable_lifecycle.py','durable_lifecycle.py','CLEANUP-ERROR-REPAIR03.diff'),
];
const oldD=fs.readFileSync(path.join(dir,'before/accepted-durable_lifecycle.py')),newD=fs.readFileSync(path.join(dir,'durable_lifecycle.py'));
const oldS=oldD.toString('utf8'),newS=newD.toString('utf8');
const moved='    def _flush_quarantine(self, key, original=None):\n        try:\n            token = self._token(key)\n';
const original='    def _flush_quarantine(self, key, original=None):\n        token = self._token(key)\n        try:\n';
if(newS.split(moved).length!==2)throw Error('cleanup movement absent');
const normalized=newS.replace(moved,original);
if(normalized!==fs.readFileSync(path.join(dir,'before/pre-review-cleanup03-durable_lifecycle.py'),'utf8'))throw Error('cleanup delta not exact');
const oldStart=oldS.indexOf('class DurableOwnedRuntimeFactory:'),newStart=normalized.indexOf('@dataclass(frozen=True, eq=False)');
const oldTail=oldS.indexOf('    def quarantine(self, key, protection, permit, reason):',oldStart),newTail=normalized.indexOf('    def quarantine(self, key, protection, permit, reason):',newStart);
if(oldStart<0||newStart<0||oldTail<0||newTail<0)throw Error('bounded region absent');
if(oldS.slice(0,oldStart)!==normalized.slice(0,newStart)||oldS.slice(oldTail)!==normalized.slice(newTail))throw Error('unrelated durable bytes changed');
const oldA=fs.readFileSync(path.join(dir,'before/accepted-asr_loading_adapter.py')),newA=fs.readFileSync(path.join(dir,'asr_loading_adapter.py'));
if(!newA.subarray(0,oldA.length).equals(oldA))throw Error('accepted adapter prefix changed');
const result={scope:'mechanical source-text differences only',diffs,accepted_adapter_prefix_bytes:oldA.length,accepted_adapter_prefix_identical:true,durable_unrelated_prefix_suffix_identical_except_exact_cleanup_movement:true,cleanup_reverse_exact:true,three_argument_kernel_signature:newS.includes('    def start_owned_worker(self, protection, permit, profile):'),candidate_executed:false};
fs.writeFileSync(path.join(dir,'DIFF-CHECK03-RESULT.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(result,null,2));
`;
fs.writeFileSync(path.join(dir,'write_and_check_diffs03.mjs'),next,{flag:'wx'});
let binding=fs.readFileSync(path.join(dir,'bind_final_sources.mjs'),'utf8')
 .replaceAll('8de6757dd1c21399d8bae5cf0accdeac28368b150d27e4fa54622559ed4b047b','ce69903d93daf41ae3717008f8d0dbd0b3ead7b11662b674eddf43828567b222')
 .replaceAll('SOURCE-INPUTS.json','SOURCE-INPUTS03.json')
 .replaceAll('FINAL-BINDINGS-ACTUAL.json','FINAL-BINDINGS03-ACTUAL.json')
 .replaceAll("'REPORT.md'","'REPORT03.md'");
fs.writeFileSync(path.join(dir,'bind_final_sources03.mjs'),binding,{flag:'wx'});
console.log(JSON.stringify({prepared:['write_and_check_diffs03.mjs','bind_final_sources03.mjs'],candidate_executed:false}));

