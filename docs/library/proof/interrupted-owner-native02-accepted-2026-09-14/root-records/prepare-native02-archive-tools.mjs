import fs from 'node:fs';
function create(file,text){fs.writeFileSync('_scratch/'+file,text,{flag:'wx'});}
let a=fs.readFileSync('_scratch/archive-interrupted-native-run01-failure.mjs','utf8');
a=a.replaceAll('interrupted-owner-native01-failure','interrupted-owner-native02-accepted').replaceAll('windows-interrupted-owner-native-proposal01','windows-interrupted-owner-native-proposal02').replaceAll('windows-interrupted-owner-retirement01','windows-interrupted-owner-retirement02').replaceAll('run_interrupted_owner01.ps1','run_interrupted_owner02.ps1').replaceAll('2ce447ecc0145d5a14a0fc8ea57cf5cd2b9134ff0293aab33b5b2e9bc2a2f223','c5808c7af66630b77d399409564733893a074de36169817ff4cd5234981c250d').replaceAll('prepRows.length!==86','prepRows.length!==56');
const start=a.indexOf('for(const [dir,label] of [');const end=a.indexOf("const run=",start);
a=a.slice(0,start)+`for(const [dir,label] of [
 ['windows-interrupted-owner-native-proposal02','preparation'],
 ['interrupted-owner-native02-peer-review','source-peer-review'],
 ['interrupted-owner-native02-receipt-peer','receipt-peer-review']
])tree(path.join(scratch,dir),label);
`+a.slice(end);
const s=a.indexOf('for(const suffix of [');const e=a.indexOf('const attrs=',s);
const actuals=['INTERRUPTED-NATIVE-RUN02-ACTUAL.json','INTERRUPTED-NATIVE-RUN02-INITIAL-RECEIPTS-ACTUAL.json','INTERRUPTED-NATIVE02-SOURCE-BRIEF-COMMIT-ACTUAL.json','INTERRUPTED-NATIVE02-ROOT-INPUT-CHECK-ACTUAL.json','INTERRUPTED-NATIVE02-ROOT-DELTA-READ-ACTUAL.json','INTERRUPTED-NATIVE02-ADMISSION-COMMIT-ACTUAL.json','INTERRUPTED-NATIVE02-ROOT-RECEIPT-READ-ACTUAL.json','INTERRUPTED-NATIVE02-ROOT-PEER-READ-ACTUAL.json','INTERRUPTED-NATIVE02-ROOT-RECEIPT-CHECK-ACTUAL.json','INTERRUPTED-NATIVE02-ROOT-CHECKER-DIAGNOSIS-ACTUAL.json','INTERRUPTED-NATIVE02-ROOT-CHECKER-REPAIR02.md','INTERRUPTED-NATIVE02-ROOT-RECEIPT-CHECK02-ACTUAL.json','INTERRUPTED-NATIVE02-ROOT-RECEIPT-RESULT.json','check-native02-inputs-root.mjs','prepare-native02-root-check.mjs','check-native02-root-receipts.ps1','check-native02-root-receipts02.ps1','prepare-native02-archive-tools.mjs'];
a=a.slice(0,s)+`for(const name of ${JSON.stringify(actuals)})copy(path.join(scratch,name),'root-records/'+name);
for(const name of ['ASTRA-NATIVE-INTERRUPTED-OWNER02-ADMISSION-2026-09-14.md','INTERRUPTED-OWNER-NATIVE02-SOURCE-BRIEF-2026-09-14.md','ASTRA-INTERRUPTED-NATIVE02-VERDICT-2026-09-14.md'])copy(path.join(root,'docs/library',name),'contracts/'+name);
copy(path.join(scratch,'archive-interrupted-native02-accepted.mjs'),'archive-interrupted-native02-accepted.mjs');
`+a.slice(e);
a=a.replace('FAILED native observation 3c41aa','Accepted generated native observation 9753fb').replace('passive diagnoses','passive root and peer reviews');
create('archive-interrupted-native02-accepted.mjs',a);
let p=fs.readFileSync('_scratch/integrate-interrupted-native01-failure.ps1','utf8').replaceAll('interrupted-owner-native01-failure','interrupted-owner-native02-accepted').replaceAll('interrupted-native01-failure','interrupted-native02-accepted').replaceAll('interrupted-native01-apply','interrupted-native02-apply');
create('integrate-interrupted-native02-accepted.ps1',p);
let r=fs.readFileSync('_scratch/restore-interrupted-native01-transport.mjs','utf8').replaceAll('interrupted-owner-native01-failure','interrupted-owner-native02-accepted').replaceAll('INTERRUPTED-NATIVE01','INTERRUPTED-NATIVE02');
create('restore-interrupted-native02-transport.mjs',r);
console.log('Created three documentary transport tools; no subject operation.');
