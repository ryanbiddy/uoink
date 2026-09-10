import json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
src=r/'_scratch/run_installed_decoders05.py'
dest=r/'_scratch/run_installed_decoders05_v2.py'
assert not dest.exists()
text=src.read_text()
text=text.replace("profile=root/'decoder-environment'", "profile=root/'decoder-environment-02'")
old="env['PATH']=str(app/'bin')+os.pathsep+env['SystemRoot']+'\\\\System32'+os.pathsep+env['SystemRoot']"
new="system_root=os.environ['SystemRoot']\nassert Path(system_root).is_absolute() and (Path(system_root)/'System32').is_dir()\nenv['PATH']=str(app/'bin')+os.pathsep+str(Path(system_root)/'System32')+os.pathsep+system_root"
assert text.count(old)==1
text=text.replace(old,new)
compile(text,str(dest),'exec')
dest.write_text(text,encoding='utf8')
report={'first_exit':1,'failure':"KeyError: 'SystemRoot'",'stage':'launcher preparation before either decoder subprocess','repair':'Read SystemRoot from the Windows case-insensitive os.environ before using the copied dict, whose keys are uppercase. Validate the system directory and retain the application-only native PATH plus Windows system paths. Use a fresh decoder environment directory.','product_changed':False,'rerun_brief':'Review this exact launcher-only change and repeat the two original decoder instruments with unchanged assertions and guards.'}
(r/'_scratch/decoder-launcher05-repair.json').write_text(json.dumps(report,indent=2)+'\n')
print('Second launcher compiles; only SystemRoot lookup and fresh environment path changed.')
