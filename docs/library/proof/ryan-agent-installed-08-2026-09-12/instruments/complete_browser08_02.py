"""Seal the views actually captured and inspected for this new observation."""
from pathlib import Path
import datetime as dt,hashlib,json,subprocess,sys
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08\c22\artifacts')
def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
errors=subprocess.run([sys.executable,str(repo/'_scratch/run_browser08_02.py'),'errors'],capture_output=True,timeout=50)
(root/'browser-errors.txt').write_bytes(errors.stdout);(root/'browser-errors.stderr').write_bytes(errors.stderr)
assert errors.returncode==0 and not errors.stdout.decode('utf8').strip(),errors.stdout
files=[]
for name in ('browser-library.png','browser-sources-top.png','browser-checkpoint.png','browser-activity.png'):
    p=root/name;data=p.read_bytes();assert data.startswith(b'\x89PNG\r\n\x1a\n')
    files.append({'file':name,'bytes':len(data),'sha256':sha(p),'captured_file_mtime_utc':dt.datetime.fromtimestamp(p.stat().st_mtime,dt.timezone.utc).isoformat()})
closed=subprocess.run([sys.executable,str(repo/'_scratch/run_browser08_02.py'),'close'],capture_output=True,timeout=50)
(root/'browser-close.stdout').write_bytes(closed.stdout);(root/'browser-close.stderr').write_bytes(closed.stderr)
assert closed.returncode==0,closed.stderr
record={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'observer':'Astra','tool':'agent-browser; dedicated uoink-install08b session','browser_config_sha256':sha(repo/'_scratch/agent-browser08.json'),'url':'http://127.0.0.1:18081/dashboard','viewport':[1440,1100],'images':files,'browser_page_errors':'','browser_close_exit':closed.returncode,'actions_sha256':sha(root/'browser-actions.jsonl'),
    'reviewed_visible_fields':{'source':'http://c22-fixture.invalid/child-life/feed.xml','consent':'On (Standing capture), rev 1','detection':'healthy','capture':'settled failed (worker_lost)','enrollment':'1 / 25','starts':'1 / 10 used; 9 remaining','recovery':'eligible for retry; C22 child-lifetime episode; worker_lost; attempt 1/3; start failed; retry scheduled','activity':'0 running, 0 queued, 0 completed loaded'},
    'scope':'Actual installed dashboard; four original PNGs inspected by Astra. Read-only tabs and scrolling; no source fetch, consent change, capture or model run. The complete command ledger retains actual actions and failures.',
    'visual_verdict':'Visible consent, charge, outcome and recovery fields match the fixture; persisted-state and cleanup review follows.'}
save(root/'browser-observation-complete.json',record)
print(json.dumps({'images':len(files),'page_errors':'','browser_close_exit':closed.returncode,'utc':record['utc']}))
