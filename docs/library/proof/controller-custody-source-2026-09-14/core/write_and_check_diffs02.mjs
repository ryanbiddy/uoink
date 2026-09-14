import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const dir='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary-custody-repair01';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function lines(b){const s=b.toString('utf8').replace(/\r\n/g,'\n');if(!s.endsWith('\n'))throw Error('final newline required by this fixed diff writer');return s.slice(0,-1).split('\n');}
function writeDiff(oldName,newName,diffName){
 const a=fs.readFileSync(path.join(dir,oldName)),b=fs.readFileSync(path.join(dir,newName)),x=lines(a),y=lines(b);
 let p=0,s=0;while(p<x.length&&p<y.length&&x[p]===y[p])p++;while(s<x.length-p&&s<y.length-p&&x[x.length-1-s]===y[y.length-1-s])s++;
 if(p===x.length&&p===y.length)throw Error('expected changed fixed pair');
 const start=Math.max(0,p-3),tailOld=x.length-s,tailNew=y.length-s,endOld=Math.min(x.length,tailOld+3),endNew=Math.min(y.length,tailNew+3);
 const body=[...x.slice(start,p).map(v=>' '+v),...x.slice(p,tailOld).map(v=>'-'+v),...y.slice(p,tailNew).map(v=>'+'+v),...x.slice(tailOld,endOld).map(v=>' '+v)];
 const diff=['--- '+oldName,'+++ '+newName,'@@ -'+(start+1)+','+(endOld-start)+' +'+(start+1)+','+(endNew-start)+' @@',...body].join('\n')+'\n';
 const rows=diff.slice(0,-1).split('\n');const m=/^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$/.exec(rows[2]);if(!m)throw Error('generated header malformed');
 const oldPart=[],newPart=[];for(const row of rows.slice(3)){if(!' +-'.includes(row[0]))throw Error('invalid body prefix');if(row[0]!=='+')oldPart.push(row.slice(1));if(row[0]!=='-')newPart.push(row.slice(1));}
 if(oldPart.length!==+m[2]||newPart.length!==+m[4])throw Error('hunk counts');
 if(JSON.stringify(oldPart)!==JSON.stringify(x.slice(start,endOld))||JSON.stringify(newPart)!==JSON.stringify(y.slice(start,endNew)))throw Error('body differs');
 const forward=[...x.slice(0,start),...newPart,...x.slice(endOld)],reverse=[...y.slice(0,start),...oldPart,...y.slice(endNew)];
 if(JSON.stringify(forward)!==JSON.stringify(y)||JSON.stringify(reverse)!==JSON.stringify(x))throw Error('whole reconstruction differs');
 fs.writeFileSync(path.join(dir,diffName),diff,{flag:'wx'});
 return{before:oldName,after:newName,diff:diffName,before_sha256:sha(a),after_sha256:sha(b),diff_sha256:sha(Buffer.from(diff)),bytes:Buffer.byteLength(diff),forward:true,reverse:true,normalization:'CRLF to LF only'};
}
const diffs=[
 writeDiff('before/accepted-durable_lifecycle.py','durable_lifecycle.py','durable_lifecycle.from-accepted.final.diff'),
 writeDiff('before/accepted-asr_loading_adapter.py','asr_loading_adapter.py','asr_loading_adapter.from-accepted.final.diff'),
 writeDiff('before/rejected-durable_lifecycle.py','durable_lifecycle.py','durable_lifecycle.from-rejected.final.diff'),
 writeDiff('before/rejected-asr_loading_adapter.py','asr_loading_adapter.py','asr_loading_adapter.from-rejected.final.diff'),
 writeDiff('before/pre-review-helper01-durable_lifecycle.py','before/pre-review-entry02-durable_lifecycle.py','FACTORY-HELPER-REPAIR01.valid.diff'),
 writeDiff('before/pre-review-entry02-durable_lifecycle.py','durable_lifecycle.py','ENTRY-SELECTION-REPAIR02.diff'),
];
const oldD=fs.readFileSync(path.join(dir,'before/accepted-durable_lifecycle.py')),newD=fs.readFileSync(path.join(dir,'durable_lifecycle.py'));
const oldS=oldD.toString('utf8'),newS=newD.toString('utf8'),oldStart=oldS.indexOf('class DurableOwnedRuntimeFactory:'),newStart=newS.indexOf('@dataclass(frozen=True, eq=False)');
const oldTail=oldS.indexOf('    def quarantine(self, key, protection, permit, reason):',oldStart),newTail=newS.indexOf('    def quarantine(self, key, protection, permit, reason):',newStart);
if(oldStart<0||newStart<0||oldTail<0||newTail<0)throw Error('bounded region absent');
if(oldS.slice(0,oldStart)!==newS.slice(0,newStart)||oldS.slice(oldTail)!==newS.slice(newTail))throw Error('unrelated durable bytes changed');
const oldA=fs.readFileSync(path.join(dir,'before/accepted-asr_loading_adapter.py')),newA=fs.readFileSync(path.join(dir,'asr_loading_adapter.py'));
if(!newA.subarray(0,oldA.length).equals(oldA))throw Error('accepted adapter prefix changed');
const result={scope:'mechanical source-text differences only',diffs,accepted_adapter_prefix_bytes:oldA.length,accepted_adapter_prefix_identical:true,durable_unrelated_prefix_suffix_identical:true,three_argument_kernel_signature:newS.includes('    def start_owned_worker(self, protection, permit, profile):'),candidate_executed:false};
fs.writeFileSync(path.join(dir,'DIFF-CHECK02-RESULT.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(result,null,2));

