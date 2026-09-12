"""Retain four actually inspected views and finish the owned browser/helper hold."""
from pathlib import Path
import datetime as dt,hashlib,json,subprocess
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07\c22\artifacts')
exe=Path(r'C:\Users\hello\AppData\Local\npm-cache\_npx\6de2aa2fded2970c\node_modules\agent-browser\bin\agent-browser-win32-x64.exe')
base=[str(exe),'--config',str(repo/'_scratch/agent-browser07.json'),'--session','uoink-install07']
def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(value,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
errors=subprocess.run([*base,'errors'],capture_output=True,timeout=30)
(root/'browser-errors.txt').write_bytes(errors.stdout)
(root/'browser-errors.stderr').write_bytes(errors.stderr)
assert errors.returncode==0 and not errors.stdout.decode('utf8').strip(),errors.stdout
files=[]
for name in ('browser-library.png','browser-sources-top.png','browser-checkpoint.png','browser-activity.png'):
    path=root/name;data=path.read_bytes();assert data.startswith(b'\x89PNG\r\n\x1a\n')
    files.append({'file':name,'bytes':len(data),'sha256':sha(path),
        'captured_file_mtime_utc':dt.datetime.fromtimestamp(path.stat().st_mtime,dt.timezone.utc).isoformat()})
closed=subprocess.run([*base,'close'],capture_output=True,timeout=30)
(root/'browser-close.stdout').write_bytes(closed.stdout)
(root/'browser-close.stderr').write_bytes(closed.stderr)
assert closed.returncode==0,closed.stderr
record={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'observer':'Astra',
    'tool':'agent-browser 0.37.1; dedicated uoink-install07 session',
    'binary_sha256':sha(exe),'browser_config_sha256':sha(repo/'_scratch/agent-browser07.json'),
    'url':'http://127.0.0.1:18081/dashboard','viewport':[1440,1100],
    'images':files,'browser_page_errors':'','browser_close_exit':closed.returncode,
    'reviewed_visible_fields':{'source':'http://c22-fixture.invalid/child-life/feed.xml',
       'consent':'On (Standing capture), rev 1','detection':'healthy',
       'capture':'settled failed (worker_lost)','enrollment':'1 / 25',
       'starts':'1 / 10 used; 9 remaining',
       'recovery':'eligible for retry; C22 child-lifetime episode; worker_lost; attempt 1/3; start failed; retry scheduled',
       'activity':'0 running, 0 queued, 0 completed loaded'},
    'scope':'Actual installed UI. Four original PNGs inspected by Astra; no source fetch, capture, consent change or model run. UTC is paired here and visible in the Library snapshot.',
    'navigation_observation':[
       'Initial about:blank preflight exited 1: No hostname in URL. No product page was loaded by that command.',
       'Kept the 127.0.0.1 domain restriction, registered an abort route for http://127.0.0.1:5179/**, then opened the declared dashboard once.',
       'Observed div.content as the scrolling container and used its native scrollTo(0,640). No CSS, text or image bytes were edited.',
       'Four views cover Library, Sources top, full recovery card and Activity. Earlier package-06 intermediate images remain separate.'],
    'visual_verdict':'Visible consent, charge, outcome and recovery fields match the fixture; persisted-state and helper cleanup review follows.'}
save(root/'browser-observation-complete.json',record)
print(json.dumps({'images':len(files),'page_errors':'','browser_close_exit':closed.returncode,'utc':record['utc']}))
