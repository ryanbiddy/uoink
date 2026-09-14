import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const work='C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e6133b1f-fc8/gemini';
const source=path.join(work,'_scratch/protected-asr-constructor01');
const out=path.join(root,'_scratch/protected-asr-constructor01-root-review');
if(fs.existsSync(out))throw Error('Fresh frozen source review');
fs.mkdirSync(out);const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const rows=[];
function copyTree(dir,target){for(const name of fs.readdirSync(dir).sort()){const p=path.join(dir,name),st=fs.lstatSync(p),rel=target+'/'+name;if(st.isSymbolicLink())throw Error('No links');if(st.isDirectory())copyTree(p,rel);else{if(!st.isFile()||!/[.](py|md|json|diff)$/.test(name))throw Error('Only documentary source');const b=fs.readFileSync(p);fs.mkdirSync(path.dirname(path.join(out,rel)),{recursive:true});fs.writeFileSync(path.join(out,rel),b,{flag:'wx'});rows.push({path:rel,bytes:b.length,sha256:sha(b)});}}}
copyTree(source,'frozen');
const map=JSON.parse(fs.readFileSync(path.join(source,'SOURCE-INPUTS.json'))),checks=[];
for(const group of ['inputs','before_copies','delivered_source_files','unified_diffs'])for(const r of map[group]){
 if(path.isAbsolute(r.path)||r.path.includes('..')||!/[.](py|md|json|txt|diff)$/.test(r.path))throw Error('Fixed source-only path');
 const p=path.join(group==='inputs'?root:work,r.path);let actual=null;
 if(fs.existsSync(p)){const b=fs.readFileSync(p);actual={bytes:b.length,sha256:sha(b)};}
 checks.push({group,path:r.path,expected:{bytes:r.bytes,sha256:r.sha256},actual,match:actual!==null&&actual.bytes===r.bytes&&actual.sha256===r.sha256});
}
fs.writeFileSync(path.join(out,'INPUT-MAP-CHECK.json'),JSON.stringify({scope:'Passive comparison of delivered map; no subject execution',checks,mismatches:checks.filter(c=>!c.match)},null,2)+'\n',{flag:'wx'});
const db=new DatabaseSync('C:/Users/hello/AppData/Local/AgentControlRoom/control-room.sqlite',{readOnly:true});
try{
 const id='e6133b1f-fc8e-4f78-b252-1fae0659ef5e';
 const run=db.prepare('SELECT id,status,started_at,finished_at,summary FROM runs WHERE id=?').get(id);
 const workers=db.prepare('SELECT id,agent,model,status,worktree_path,output,error,started_at,finished_at FROM agent_runs WHERE run_id=?').all(id);
 const events=db.prepare('SELECT id,type,message,payload_json,created_at FROM events WHERE run_id=? ORDER BY id').all(id);
 if(run.status!=='completed'||workers.some(w=>w.status!=='completed'))throw Error('Completed transport required');
 fs.writeFileSync(path.join(out,'CONTROL-ROOM-RECORD.json'),JSON.stringify({run,workers,events},null,2)+'\n',{flag:'wx'});
 const commands=events.filter(e=>e.type==='tool'&&e.message==='run_command');
 fs.writeFileSync(path.join(out,'COMMAND-EVENTS.json'),JSON.stringify(commands,null,2)+'\n',{flag:'wx'});
 console.log(JSON.stringify({run_id:id,status:run.status,started_at:run.started_at,finished_at:run.finished_at,source_files:rows.length,map_rows:checks.length,map_mismatches:checks.filter(c=>!c.match).map(c=>({group:c.group,path:c.path,actual:c.actual})),events:events.length,command_events:commands.length}));
}finally{db.close();}
fs.writeFileSync(path.join(out,'FROZEN-SOURCE-PINS.json'),JSON.stringify({files:rows},null,2)+'\n',{flag:'wx'});
