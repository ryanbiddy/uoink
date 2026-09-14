import fs from 'node:fs';import path from 'node:path';
const dir='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-custody-instrument-peer01';
let s=fs.readFileSync(path.join(dir,'check_final_instruments.mjs'),'utf8');
s=s.replace("fs.writeFileSync(path.join(out,name),b,{flag:'wx'});","{const p=path.join(out,name);if(!fs.readFileSync(p).equals(b))throw Error('original snapshot changed');}");
const old="const declarations=JSON.parse(read(path.join(dir,edits)));let forward=before,reverse=after;\n for(const e of declarations){if(forward.split(e.from).length-1!==(e.count??1))throw Error('declared count');forward=forward.split(e.from).join(e.to);}\n for(const e of [...declarations].reverse())reverse=reverse.split(e.to).join(e.from);";
const fresh="const declarations=JSON.parse(read(path.join(dir,edits)));let forward=before,reverse=after;const applied=[];\n for(const e of declarations){const count=e.count??1;if(forward.split(e.from).length-1!==count)throw Error('declared count');let cursor=0;for(let k=0;k<count;k++){const at=forward.indexOf(e.from,cursor);if(at<0)throw Error('exact original occurrence');forward=forward.slice(0,at)+e.to+forward.slice(at+e.from.length);applied.push({at,old:e.from,next:e.to});cursor=at+e.to.length;}}\n for(const e of applied.reverse()){if(reverse.slice(e.at,e.at+e.next.length)!==e.next)throw Error('recorded replacement span');reverse=reverse.slice(0,e.at)+e.old+reverse.slice(e.at+e.next.length);}";
if(s.split(old).length!==2)throw Error('fixed checker span absent');s=s.replace(old,fresh);
fs.writeFileSync(path.join(dir,'check_final_instruments02.mjs'),s,{flag:'wx'});
console.log(JSON.stringify({correction:'Reverse only the exact spans recorded during forward declared replacements; preserve unrelated existing -eq 10 guard. Existing snapshots compared unchanged.',candidate_executed:false}));

