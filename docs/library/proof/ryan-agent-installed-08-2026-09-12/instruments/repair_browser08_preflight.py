"""Prepare an explicit fresh browser tool attempt, retaining the failed startup."""
from pathlib import Path
import ast,datetime as dt,difflib,hashlib,json
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08\c22\artifacts')
old=(s/'run_browser08.py').read_text(encoding='utf8')
new=old.replace("'uoink-install08'","'uoink-install08b'")
start=new.index("record={'utc_start'")
new=new[:start]+'''record={'utc_start':dt.datetime.now(dt.timezone.utc).isoformat(),'command':command}
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
with log.open('a',encoding='utf8') as f:f.write(json.dumps(record)+'\\n')
sys.stdout.buffer.write(stdout.read_bytes());sys.stderr.buffer.write(stderr.read_bytes())
if timed_out:print('Timed out: retain this attempt and close only its named session before any further browser command.')
raise SystemExit(record['wrapper_exit'])
'''
ast.parse(new)
with (s/'run_browser08_02.py').open('x',encoding='utf8',newline='\n') as f:f.write(new)
(s/'run_browser08_02.py.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='run_browser08.py',tofile='run_browser08_02.py')),encoding='utf8')
old=(s/'complete_browser08.py').read_text(encoding='utf8')
new=old.replace('run_browser08.py','run_browser08_02.py').replace('dedicated uoink-install08 session','dedicated uoink-install08b session')
ast.parse(new)
with (s/'complete_browser08_02.py').open('x',encoding='utf8',newline='\n') as f:f.write(new)
(s/'complete_browser08_02.py.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='complete_browser08.py',tofile='complete_browser08_02.py')),encoding='utf8')
failure={'utc_recorded':dt.datetime.now(dt.timezone.utc).isoformat(),'attempt':'network-rule-before-navigation01','session':'uoink-install08','wrapper_pid':33680,'wrapper_created_utc':'2026-09-12T18:54:39.091185Z','daemon_pid_from_session_file':12268,'daemon_control_port':49765,'command':['network','route','http://127.0.0.1:5179/**','--abort'],'wrapper_exit':1,'error':'subprocess.TimeoutExpired after 45 seconds; captured pipe completion waited until daemon close','dashboard_open_requested':False,'cleanup_command':['--session','uoink-install08','close'],'cleanup_exit':0,'cleanup_message':'Browser closed','owned_wrapper_and_daemon_absent_after':True,'repair_brief':'BROWSER08-PREFLIGHT-REPAIR.md','observation_claimed':False}
with (root/'browser-preflight01-failure.json').open('x',encoding='utf8') as f:json.dump(failure,f,indent=2)
with (root/'browser-actions.jsonl').open('x',encoding='utf8') as f:f.write(json.dumps(failure)+'\n')
record={'scope':'Pre-execution repair, no browser action yet','source_before_sha256':hashlib.sha256((s/'run_browser08.py').read_bytes()).hexdigest(),'source_after_sha256':hashlib.sha256((s/'run_browser08_02.py').read_bytes()).hexdigest(),'original_attempt_preserved':True,'fresh_session':'uoink-install08b'}
with (s/'browser08-preflight-repair.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
print(json.dumps(record))
