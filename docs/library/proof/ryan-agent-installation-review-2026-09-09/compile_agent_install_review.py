import hashlib,json,shutil,subprocess,time
from pathlib import Path
r=Path(__file__).resolve().parents[1]
old=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\d0577a56-f15\grok\_scratch\inno-boundary-iscc-2')
out=r/'_scratch/agent-install-compile-01';out.mkdir(exist_ok=False)
for p in old.iterdir():
 if p.name in ('out','uoink.iss','compile.json','iscc.log'):continue
 if p.is_dir():shutil.copytree(p,out/p.name)
 else:shutil.copyfile(p,out/p.name)
shutil.copyfile(r/'installer/uoink.iss',out/'uoink.iss')
cmd=[r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe','/Q','/O'+str(out/'out'),'/FUoink-compile-only-agent-review',str(out/'uoink.iss')]
t=time.time();result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(out/'iscc.log').write_bytes(result.stdout)
record={'command':cmd,'exit':result.returncode,'elapsed_s':time.time()-t,'source_sha256':hashlib.sha256((r/'installer/uoink.iss').read_bytes()).hexdigest(),'copy_sha256':hashlib.sha256((out/'uoink.iss').read_bytes()).hexdigest(),'artifact_executed':False,'scope':'Exact Inno source compiled with dummy payloads; not a release build or installation'}
(out/'compile.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record,indent=2));print(result.stdout.decode('utf8','replace'));raise SystemExit(result.returncode)
