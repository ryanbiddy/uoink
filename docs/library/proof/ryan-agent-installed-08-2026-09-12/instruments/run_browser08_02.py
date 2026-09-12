"""Record explicit bounded browser commands in the fresh installed receipt."""
import datetime as dt,json,os,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08\c22\artifacts')
exe=Path(r'C:\Users\hello\AppData\Local\npm-cache\_npx\6de2aa2fded2970c\node_modules\agent-browser\bin\agent-browser-win32-x64.exe')
args=sys.argv[1:];assert args and args[0] in ('network','set','open','snapshot','click','eval','screenshot','errors','close','get')
if args[0]=='open':assert args[1:] == ['http://127.0.0.1:18081/dashboard']
assert root.is_dir()
env=os.environ.copy()
for key in list(env):
    if key.startswith('AGENT_BROWSER_') or any(x in key.upper() for x in ('API_KEY','AUTH_TOKEN','ACCESS_TOKEN','BASE_URL')):env.pop(key,None)
command=[str(exe),'--config',str(r/'_scratch/agent-browser08.json'),'--session','uoink-install08b','--allowed-domains','127.0.0.1',*args]
record={'utc_start':dt.datetime.now(dt.timezone.utc).isoformat(),'command':command}
log=root/'browser-actions.jsonl'
number=len(log.read_text(encoding='utf8').splitlines())+1 if log.exists() else 1
stdout=root/f'browser-action-{number:02d}.stdout';stderr=root/f'browser-action-{number:02d}.stderr'
timed_out=False
with stdout.open('xb') as output,stderr.open('xb') as error:
    child=subprocess.Popen(command,cwd=r,env=env,stdout=output,stderr=error)
    record['cli_pid']=child.pid
    try:code=child.wait(timeout=45)
    except subprocess.TimeoutExpired:
        timed_out=True;child.kill();code=child.wait(timeout=5)
record.update(exit=code,wrapper_exit=124 if timed_out else code,timed_out=timed_out,cleanup_required=timed_out,utc_end=dt.datetime.now(dt.timezone.utc).isoformat(),stdout=stdout.name,stderr=stderr.name)
with log.open('a',encoding='utf8') as f:f.write(json.dumps(record)+'\n')
sys.stdout.buffer.write(stdout.read_bytes());sys.stderr.buffer.write(stderr.read_bytes())
if timed_out:print('Timed out: retain this attempt and close only its named session before any further browser command.')
raise SystemExit(record['wrapper_exit'])
