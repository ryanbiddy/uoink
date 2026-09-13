"""Supervise a complete guarded tree independently of an interactive terminal."""
import argparse,datetime as dt,hashlib,json,os,subprocess,sys,time,traceback
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--label',required=True);p.add_argument('--self-test',action='store_true');a=p.parse_args()
r=Path(__file__).resolve().parents[1]
assert sys.flags.isolated and sys.flags.no_site
assert a.label==('durable-tree09-preflight01' if a.self_test else 'ryan-final-partitioned-09')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()==a.source
if not a.self_test:
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=r)
    assert not (r/'_scratch'/a.label).exists()
out=r/'_scratch'/(a.label+'-supervisor');out.mkdir(exist_ok=False)
fixture=r/'_scratch/nltk-upstream-before-local13/nltk'
fixture_record=json.loads((fixture.parent/'receipt.json').read_text(encoding='utf8'))
for name,digest in fixture_record['files'].items():assert hashlib.sha256((fixture/name).read_bytes()).hexdigest()==digest
wheel=r/'_scratch/nltk-wheel-astra-artifact01/nltk-3.10.3-py3-none-any.whl'
assert hashlib.sha256(wheel.read_bytes()).hexdigest()=='ff9598a8e20518ee0d557745890cc4435b9578489e2dcbc69c4f81fa060caf7c'
env=os.environ.copy()
for key in list(env):
    upper=key.upper()
    if any(s in upper for s in ('API_KEY','AUTH_TOKEN','ACCESS_TOKEN','BASE_URL','OAUTH_TOKEN')) or upper.startswith(('ANTHROPIC_','OPENAI_','GOOGLE_API_','GEMINI_API_','XAI_','GROK_','CLAUDE_CODE_USE_')):env.pop(key,None)
env.update(UOINK_NLTK_BASE_SOURCE=str(fixture),UOINK_UPSTREAM_NLTK_WHEEL=str(wheel),
           PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
           IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db')
command=([sys.executable,'-I','-S','-B','-c','print("durable supervisor child exited")'] if a.self_test else
         [sys.executable,'-I','-S','-B',str(r/'_scratch/run_partitioned_mirror_tree09.py'),'--source',a.source,'--label',a.label])
record={'source':a.source,'label':a.label,'self_test':a.self_test,'observer_pid':os.getpid(),
        'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'child_pid':None,'child_exit':None,'status':'starting',
        'command':command,'fixture_files':len(fixture_record['files']),'release_ready':False,
        'instrument_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
def save():
    record['heartbeat_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    temporary=out/'state.tmp'
    with temporary.open('w',encoding='utf8',newline='\n') as stream:
        json.dump(record,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,out/'state.json')
save();child=None
try:
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        child=subprocess.Popen(command,cwd=r,env=env,stdout=stdout,stderr=stderr)
        record.update(child_pid=child.pid,status='running');save()
        while child.poll() is None:
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:save()
        record.update(child_exit=child.returncode,status='child_exited',finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        if not a.self_test:
            summary=r/'_scratch'/a.label/'summary.json'
            record['aggregate_summary_present']=summary.is_file()
            if summary.is_file():record['aggregate_summary_sha256']=hashlib.sha256(summary.read_bytes()).hexdigest()
        save()
except BaseException as exc:
    record.update(status='observer_failed',error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc(),
                  child_exit=child.poll() if child else None,child_may_still_run=bool(child and child.poll() is None))
    save();raise
print(json.dumps({'label':a.label,'child_exit':record['child_exit'],'state':str(out/'state.json')}),flush=True)
raise SystemExit(record['child_exit'])
