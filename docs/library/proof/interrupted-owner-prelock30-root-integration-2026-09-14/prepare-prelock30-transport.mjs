import fs from 'node:fs';
import path from 'node:path';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const pairs=[['integrate-interrupted-native01-failure.ps1','integrate-prelock30-qualification.ps1'],['restore-interrupted-native01-transport.mjs','restore-prelock30-transport.mjs']];
for(const [oldName,newName] of pairs){const old=path.join(root,'_scratch',oldName),target=path.join(root,'_scratch',newName);if(fs.existsSync(target))throw Error('Fresh derivative');let text=fs.readFileSync(old,'utf8');text=text.replaceAll('interrupted-owner-native01-failure-2026-09-14','interrupted-owner-prelock30-qualification-2026-09-14').replaceAll('interrupted-native01-failure.patch','prelock30-qualification.patch').replaceAll('interrupted-native01-apply','prelock30-apply').replaceAll('INTERRUPTED-NATIVE01-TRANSPORT-RESULT.json','PRELOCK30-TRANSPORT-RESULT.json');fs.writeFileSync(target,text,{flag:'wx'});}
console.log('Prepared fixed documentary transport derivatives; no application or subject execution.');
