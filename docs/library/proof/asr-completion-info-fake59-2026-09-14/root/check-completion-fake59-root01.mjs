import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root='E:/AI/projects/uoink/checkouts/Yoink-library',base=path.join(root,'_scratch/asr-completion-info-fake59-author01');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),norm=t=>t.replaceAll('\r\n','\n');
function read(n){return fs.readFileSync(path.join(base,n));}
function require(v,m){if(!v)throw Error(m);}
const map=JSON.parse(read('SOURCE-INPUTS.json')),before=map.before_bindings;
for(const r of [...map.copied_sources,...before]){const b=read(r.path);require(b.length===r.bytes&&sha(b)===r.sha256,'binding '+r.path);}
require(sha(read('before/qualify_reliability.py'))==='045aaa73b69f5b93afda44785d84053c2835b5bd5094a9b6264752876fbb8f7f','accepted qualifier');
require(sha(read('before/run_fake11_01.ps1'))==='2ae106d2e6eddb33fb065840612becec0b6b600662cd1c1bb094a9a8db037126','accepted launcher');
require(sha(read('snapshot_lifecycle.py'))==='22b662938178d1898eb287348d0b4556c6579b5d0ce79f2782d49a4748ed1509','reviewed lifecycle');
require(sha(read('test_completion_info.py'))==='29d3a327d9b507f1a16b147a7be68887fb2233536823f76da3e65d1e45b57549','corrected13');
const legacy=norm(read('before/qualify_lifecycle46.py').toString('utf8'));
require(sha(read('before/qualify_lifecycle46.py'))==='563539d579a6584029f6596d6cba5de375976b6ada02535108cc195cb4fc3de7','legacy accepted source');
const start=legacy.indexOf('class TestInterrupt(BaseException):'),end=legacy.indexOf('results = []',start);
require(start>=0&&end>start,'historical extraction markers');
const expectedExtract='"""Unchanged historical lifecycle46 controls under the shared closed guard."""\nimport dataclasses\nimport snapshot_lifecycle as M\n\n\n'+legacy.slice(start,end);
require(norm(read('lifecycle46_cases.py').toString('utf8'))===expectedExtract,'exact historical helpers/cases/membership block');
function applyDiff(beforeText,diffText,reverse=false){const src=norm(beforeText).split('\n');if(src.at(-1)==='')src.pop();const diff=norm(diffText).split('\n');let i=2,cur=0,out=[],hunks=0;
 while(i<diff.length){if(diff[i]===''&&i===diff.length-1)break;const m=/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(diff[i++]);require(m,'hunk header');let oldStart=Number(m[reverse?3:1]),oldCount=Number(m[reverse?4:2]??1),newCount=Number(m[reverse?2:4]??1);const pos=oldStart===0?0:oldStart-1;require(pos>=cur,'ordered hunk');out.push(...src.slice(cur,pos));cur=pos;let a=0,b=0;
 while(i<diff.length&&!diff[i].startsWith('@@ ')){let line=diff[i++];if(line===''&&i===diff.length)break;if(line.startsWith('\\ No newline'))continue;let tag=line[0];if(reverse)tag=tag==='+'?'-':tag==='-'?'+':tag;const body=line.slice(1);require([' ','+','-'].includes(tag),'line tag');if(tag!=='+' ){require(src[cur]===body,'context at '+cur);cur++;a++;}if(tag!=='-'){out.push(body);b++;}}
 require(a===oldCount&&b===newCount,'hunk counts');hunks++;}
 out.push(...src.slice(cur));return{text:out.join('\n')+'\n',hunks};
}
const deltas=[['before/qualify_reliability.py','qualify_completion_info.py','qualify_completion_info.diff'],['before/run_fake11_01.ps1','run_fake59_01.ps1','run_fake59_01.diff'],['before/qualify_lifecycle46.py','lifecycle46_cases.py','lifecycle46_cases.diff']];
const checked=[];
for(const [a,b,d] of deltas){const x=read(a).toString('utf8'),y=read(b).toString('utf8'),patch=read(d).toString('utf8');const f=applyDiff(x,patch),r=applyDiff(y,patch,true);require(f.text===norm(y)&&r.text===norm(x),'complete forward reverse '+d);checked.push({diff:d,hunks:f.hunks,sha256:sha(read(d))});}
const old=JSON.parse(read('before/LIFECYCLE46-EXPECTED.json')),added=JSON.parse(read('before/COMPLETION13-EXPECTED.json')),all=JSON.parse(read('EXPECTED-CASES.json'));
const oldIds=Array.isArray(old)?old:old.expected_cases;
require(oldIds.length===46&&added.length===13&&all.length===59&&new Set(all).size===59&&JSON.stringify(all)===JSON.stringify([...oldIds,...added]),'exact original46 then new13');
require(!fs.existsSync(path.join(base,'ROOT-ADMISSION.json'))&&!fs.existsSync(path.join(base,'asr-completion-info-fake59-01')),'not admitted/unexecuted');
console.log(JSON.stringify({scope:'Root passive preparation relation, no subject execution',historical_source_sha256:sha(read('before/qualify_lifecycle46.py')),historical_body_exact:true,expected59_sha256:sha(read('EXPECTED-CASES.json')),source_inputs_checked:7,full_deltas:checked,source_sha256:sha(read('snapshot_lifecycle.py')),tests_sha256:sha(read('test_completion_info.py')),qualifier_sha256:sha(read('qualify_completion_info.py')),launcher_sha256:sha(read('run_fake59_01.ps1'))}));
