"""Correct unused package-08 instruments before any app launch."""
import ast,difflib,hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch';out=s/'native08-preexecution-corrections';out.mkdir(exist_ok=False)
changes=[]
def write(name,old,new,reason):
    ast.parse(new);p=s/name
    (out/(name+'.original.txt')).write_bytes(p.read_bytes())
    (out/(name+'.diff')).write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='unused-draft/'+name,tofile='corrected/'+name)),encoding='utf8')
    p.write_text(new,encoding='utf8',newline='\n')
    changes.append({'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'reason':reason,'executed':False})
p=s/'native_gui08_driver.py';old=p.read_text(encoding='utf8');new=old
needle="mode=sys.argv[1];assert mode in ('dashboard','desktop')";assert needle in new
new=new.replace(needle,"mode=sys.argv[1];assert mode == 'dashboard', 'Desktop override is not a verified isolation boundary'")
start=new.index("  else:\n   data=run/'user-data'");end=new.index("  save('ready.json',record)",start)
new=new[:start]+new[end:]
needle="  if mode=='dashboard':\n   helper=start("
assert needle in new
new=new.replace(needle,"""  if mode=='dashboard':
   seed=start([str(app/'python/python.exe'),'-P','-B','-s',str(repo/'_scratch/native_media08_seed.py')],'seed',env)
   assert seed.popen.wait(timeout=60)==0, 'Native media fixture preparation failed; preserve attempt'
   assert seed.terminate_tree(timeout=5)['cleaned']
   record['synthetic_media_seed']=json.loads((root/'media-seed.json').read_text(encoding='utf8'))
   helper=start(""")
write(p.name,old,new,'Remove unverified Desktop launch entirely; only guarded Uoink dashboard. Add a separate synthetic in-root media seed through installed interpreter before UI observation.')
p=s/'build_native_gui08_launchers.py';old=p.read_text(encoding='utf8');assert "for mode in ('dashboard','desktop'):" in old
new=old.replace("for mode in ('dashboard','desktop'):","for mode in ('dashboard',):")
write(p.name,old,new,'Compile only the Uoink dashboard launcher; no Desktop launcher is produced.')
(out/'review.json').write_text(json.dumps({'changes':changes,'original_scenarios_changed':False,'no_gui_started':True,'incident':'NATIVE-CLIENT-ISOLATION-INCIDENT-2026-09-12.md'},indent=2)+'\n',encoding='utf8')
print(json.dumps({'unused_instruments_corrected':len(changes),'desktop_launch_available':False}))
