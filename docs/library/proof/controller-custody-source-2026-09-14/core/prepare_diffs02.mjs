import fs from 'node:fs';import path from 'node:path';
const dir='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary-custody-repair01';
let source=fs.readFileSync(path.join(dir,'write_and_check_diffs.mjs'),'utf8');
const replacements=[
 ["'durable_lifecycle.from-accepted.diff'","'durable_lifecycle.from-accepted.final.diff'"],
 ["'asr_loading_adapter.from-accepted.diff'","'asr_loading_adapter.from-accepted.final.diff'"],
 ["'durable_lifecycle.from-rejected.diff'","'durable_lifecycle.from-rejected.final.diff'"],
 ["'asr_loading_adapter.from-rejected.diff'","'asr_loading_adapter.from-rejected.final.diff'"],
 ["writeDiff('before/pre-review-helper01-durable_lifecycle.py','durable_lifecycle.py','FACTORY-HELPER-REPAIR01.diff'),","writeDiff('before/pre-review-helper01-durable_lifecycle.py','before/pre-review-entry02-durable_lifecycle.py','FACTORY-HELPER-REPAIR01.valid.diff'),\n writeDiff('before/pre-review-entry02-durable_lifecycle.py','durable_lifecycle.py','ENTRY-SELECTION-REPAIR02.diff'),"],
 ["newS.indexOf('@dataclass(frozen=True, eq=False)\\r\\nclass _FactoryStartAttempt:')","newS.indexOf('@dataclass(frozen=True, eq=False)')"],
 ["'DIFF-CHECK-RESULT.json'","'DIFF-CHECK02-RESULT.json'"]
];
for(const[a,b]of replacements){if(source.split(a).length!==2)throw Error('exact passive correction target missing: '+a);source=source.replace(a,b);}
fs.writeFileSync(path.join(dir,'write_and_check_diffs02.mjs'),source,{flag:'wx'});
console.log('Prepared fresh passive checker02; original checker and five outputs preserved.');

