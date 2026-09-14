import fs from 'node:fs';import path from 'node:path';
const dir='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/controller-boundary-custody-repair01';
let s=fs.readFileSync(path.join(dir,'write_and_check_diffs03.mjs'),'utf8');
const moved='    def _flush_quarantine(self, key, original=None):\n        try:\n            token = self._token(key)\n';
const original='    def _flush_quarantine(self, key, original=None):\n        token = self._token(key)\n        try:\n';
for(const[name,value]of[['moved',moved],['original',original]]){const bad="const "+name+"='"+value+"';";if(s.split(bad).length!==2)throw Error('fixed escaped literal absent');s=s.replace(bad,'const '+name+'='+JSON.stringify(value)+';');}
const bad="JSON.stringify(result,null,2)+'\n'";
if(s.split(bad).length!==2)throw Error('fixed result literal absent');
s=s.replace(bad,"JSON.stringify(result,null,2)+'\\n'");
fs.writeFileSync(path.join(dir,'write_and_check_diffs04.mjs'),s,{flag:'wx'});
console.log(JSON.stringify({source_only_checker_repair:'escape three newlines expanded by preparer template',prior_unchanged:true,candidate_executed:false}));

