import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const src=path.join(root,'_scratch/controller-boundary-fixture-repair01');
const out=path.join(root,'_scratch/controller-custody-fixture-peer01');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const frozen={'controller_boundary_fixture.py':'63642115cf53a21911ea8fd1e31af91ff20c2807639e39dab5ec23fce94c06f7','test_controller_resume_publication.py':'061b7eb77db2ee834b54d790012fe280b1e1ac82e82dfb289681e926adbbec8d'};
const snapshots=new Map(), rows=[];
function read(p){const b=fs.readFileSync(p);if(!b.equals(Buffer.from(b.toString('utf8'))))throw Error('UTF8 required');snapshots.set(p,sha(b));return b;}
const mapBytes=read(path.join(src,'SOURCE-INPUTS.json'));
if(sha(mapBytes)!=='82108776580dd7e0927f50d1dd26ce9ebd8af827b664c090db2c8d50e74465ad')throw Error('map freeze differs');
const map=JSON.parse(mapBytes);
for(const row of [...map.modules,map.expected]){const b=read(row.path);if(b.length!==row.bytes||sha(b)!==row.sha256)throw Error('binding differs '+row.path);rows.push({path:row.path,bytes:b.length,sha256:sha(b)});}
for(const[name,h]of Object.entries(frozen)){const b=read(path.join(src,name));if(sha(b)!==h)throw Error('subject freeze differs');fs.writeFileSync(path.join(out,'snapshot-'+name),b,{flag:'wx'});}
function apply(text,diff,reverse){
 if(text.includes('\r')||text&& !text.endsWith('\n'))throw Error('LF source required');
 const lines=text?text.slice(0,-1).split('\n'):[],d=diff.replace(/\r\n/g,'\n').trimEnd().split('\n');
 let i=d.findIndex(x=>x.startsWith('--- '));if(i<0||!d[i+1].startsWith('+++ '))throw Error('headers');i+=2;
 const result=[];let at=0;
 while(i<d.length){const m=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(d[i++]);if(!m)throw Error('hunk');
  let start=+(reverse?m[3]:m[1]),n=+(reverse?(m[4]??1):(m[2]??1)),nn=+(reverse?(m[2]??1):(m[4]??1));start-=n?1:0;
  if(start<at||start>lines.length)throw Error('order');while(at<start)result.push(lines[at++]);
  let got=0,added=0;
  while(i<d.length&&!d[i].startsWith('@@ ')){let tag=d[i][0],body=d[i++].slice(1);if(reverse)tag=tag==='+'?'-':tag==='-'?'+':tag;
   if(![' ','+','-'].includes(tag))throw Error('prefix');
   if(tag!=='+'){if(lines[at++]!==body)throw Error('context');got++;}
   if(tag!=='-'){result.push(body);added++;}
  }
  if(got!==n||added!==nn)throw Error('counts');
 }
 result.push(...lines.slice(at));return result.length?result.join('\n')+'\n':'';
}
const differences=[];
for(const name of Object.keys(frozen)){
 const before=read(path.join(src,'before',name)).toString('utf8'),after=read(path.join(src,name)).toString('utf8');
 for(const added of [false,true]){const p=path.join(src,added?name+'.new.diff':name.replace('.py','.diff')),d=read(p).toString('utf8'),old=added?'':before;
  if(apply(old,d,false)!==after||apply(after,d,true)!==old)throw Error('whole reconstruction');
  differences.push({path:p,sha256:snapshots.get(p),forward:true,reverse:true});
 }
}
const tests=read(path.join(src,'test_controller_resume_publication.py')).toString('utf8');
const ids=[...tests.matchAll(/^    def (test_[a-z0-9_]+)\(self\):/gm)].map(m=>'test_controller_resume_publication.ControllerBoundaryContracts.'+m[1]);
const expected=JSON.parse(read(path.join(src,'EXPECTED-CASES.json')));
if(ids.length!==10||JSON.stringify(ids)!==JSON.stringify(expected)||JSON.stringify(ids)!==JSON.stringify(map.cases.map(c=>c.id)))throw Error('membership');
if(map.cases.reduce((n,c)=>n+c.proposed_subtest_iterations,0)!==104||Math.max(...map.cases.map(c=>c.proposed_subtest_iterations))!==48)throw Error('declared subtest arithmetic');
for(const[p,h]of snapshots)if(sha(fs.readFileSync(p))!==h)throw Error('input changed during check');
const result={scope:'independent text/hash/diff review only',source_map_sha256:sha(mapBytes),bindings:rows,differences,ordered_cases:ids,proposed_subtest_arithmetic:{total:104,max_per_case:48,not_measured:true},source_hashes_unchanged:true,candidate_executed:false};
fs.writeFileSync(path.join(out,'SOURCE-BINDINGS.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({scope:result.scope,bindings:rows.length,full_diff_pairs:differences.length,ordered_cases:ids.length,proposed_subtests:104,source_hashes_unchanged:true,source_bindings_sha256:sha(fs.readFileSync(path.join(out,'SOURCE-BINDINGS.json'))),candidate_executed:false},null,2));

