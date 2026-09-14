import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const base='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/protected-engine-ownership-fake39-author01';
const read=n=>fs.readFileSync(path.join(base,n)),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const require=(v,m)=>{if(!v)throw Error(m);};
const pins=JSON.parse(read('PINS.json')),map=JSON.parse(read('SOURCE-INPUTS.json')),l=read('run_fake39_01.ps1').toString('utf8');
require(sha(read('PINS.json'))==='7309394f50729101e23899ef1a947639e4abcb27d59910f3dd2446d98f3524ba','frozen PINS');
function table(name){const re=new RegExp('^\\$'+name+'=@\\{\\r?\\n([\\s\\S]*?)^\\}','gm'),matches=[...l.matchAll(re)];require(matches.length===1,'unique table '+name);const out={};for(const line of matches[0][1].trim().split(/\r?\n/)){const m=/^\s*'([^']+)'='([^']+)'\s*$/.exec(line);require(m&&!Object.hasOwn(out,m[1]),'literal table row');out[m[1]]=m[2];}return out;}
const expected=table('taskExpected'),sources=table('taskSourcePaths'),keys=Object.keys(map.source_paths).sort();
require(JSON.stringify(Object.keys(expected).sort())===JSON.stringify(keys)&&JSON.stringify(Object.keys(sources).sort())===JSON.stringify(keys)&&keys.length===38,'38 launcher child bindings');
for(const r of pins.files){const b=read(r.path);require(b.length===r.bytes&&sha(b)===r.sha256,'pin '+r.path);if(Object.hasOwn(expected,r.path)){require(expected[r.path]===r.sha256&&map.source_sha256[r.path]===r.sha256,'hash '+r.path);require(path.resolve(sources[r.path])===path.resolve(base,r.path)&&sources[r.path]===map.source_paths[r.path],'path '+r.path);}}
require(!fs.existsSync(path.join(base,'ROOT-ADMISSION.json'))&&!fs.existsSync(path.join(base,'runs')),'fresh unadmitted preparation');
console.log(JSON.stringify({scope:'Root passive launcher and frozen bindings; no subject execution',parent_pins:pins.files.length,parent_bytes:pins.files.reduce((n,r)=>n+r.bytes,0),launcher_child_hashes:38,launcher_child_paths:38,all_exact:true,pins:sha(read('PINS.json')),launcher:sha(read('run_fake39_01.ps1')),qualifier:sha(read('qualify_owner.py'))}));
