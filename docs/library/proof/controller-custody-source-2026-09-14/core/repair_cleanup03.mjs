import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const dir='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary-custody-repair01';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const map=JSON.parse(fs.readFileSync(path.join(dir,'SOURCE-INPUTS.json')));
for(const row of map.derivatives){const b=fs.readFileSync(path.join(dir,row.name));if(b.length!==row.bytes||sha(b)!==row.sha256)throw Error('intermediate differs '+row.name);}
const keep=['durable_lifecycle.py','asr_loading_adapter.py','SOURCE-INPUTS.json','REPORT.md','SOURCE-CORRECTIONS.md','FINAL-BINDINGS-ACTUAL.json'];
const preserved=keep.map(name=>{const b=fs.readFileSync(path.join(dir,name)),copy='before/pre-review-cleanup03-'+name;fs.writeFileSync(path.join(dir,copy),b,{flag:'wx'});return{name,copy,bytes:b.length,sha256:sha(b)};});
const p=path.join(dir,'durable_lifecycle.py'),b=fs.readFileSync(p),s=b.toString('utf8');
if(sha(b)!=='8de6757dd1c21399d8bae5cf0accdeac28368b150d27e4fa54622559ed4b047b')throw Error('wrong source');
const from='    def _flush_quarantine(self, key, original=None):\n        token = self._token(key)\n        try:\n';
const to='    def _flush_quarantine(self, key, original=None):\n        try:\n            token = self._token(key)\n';
if(s.split(from).length!==2)throw Error('unique fixed block absent');
const next=s.replace(from,to);
if(next.replace(to,from)!==s)throw Error('reverse mismatch');
fs.writeFileSync(p,next);
console.log(JSON.stringify({scope:'source-only one-line placement repair',intermediate_map_rows_verified:map.derivatives.length,preserved,durable:{bytes:Buffer.byteLength(next),sha256:sha(Buffer.from(next))},single_exact_replacement:true,candidate_executed:false},null,2));

