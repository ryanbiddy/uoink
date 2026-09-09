import hashlib,json,os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
native=root/'_scratch/ig-native'
out=root/'_scratch/native-runtime-proof'
out.mkdir(exist_ok=False)
records={}
for name in ('python.exe','pythonw.exe','python3.dll','python314.dll','vcruntime140.dll','vcruntime140_1.dll'):
    src=Path('C:/Python314')/name
    dest=native/'Scripts'/name
    src_hash=hashlib.sha256(src.read_bytes()).hexdigest()
    assert src_hash==hashlib.sha256(dest.read_bytes()).hexdigest()
    records[name]={'bytes':dest.stat().st_size,'sha256':src_hash}
script=out/'probe.py'
script.write_text('''import json,os,sys,sitecustomize
from pathlib import Path
canary=Path(os.environ['IG_FORBIDDEN_LIVE'])
try:
    canary.write_text('must not write')
except PermissionError:
    refused=True
else:
    refused=False
assert refused and not canary.exists()
print(json.dumps({'pid':os.getpid(),'guard':sitecustomize.__file__,'canary_refused':refused,'executable':sys.executable,'version':sys.version}))
''',encoding='utf-8')
env=os.environ.copy()
env.pop('PYTHONPATH',None)
env.pop('ANTHROPIC_API_KEY',None)
env['IG_FORBIDDEN_LIVE']=str(out/'forbidden-canary.db')
proc=subprocess.Popen([str(native/'Scripts/python.exe'),'-B',str(script)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
stdout,stderr=proc.communicate(timeout=10)
(out/'stdout.txt').write_text(stdout,encoding='utf-8')
(out/'stderr.txt').write_text(stderr,encoding='utf-8')
assert proc.returncode==0,stderr
observed=json.loads(stdout)
assert observed['pid']==proc.pid
result={'vendor':'C:/Python314','files':records,'popen_pid':proc.pid,'observed':observed,'exit':proc.returncode,'pythonpath_removed':True,'real_live_index_probed':False,'port_probed':False}
(out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
