"""Make fresh instruments for the diagnosed safe-path bootstrap failure."""
from pathlib import Path
import ast,difflib,hashlib,json
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08\native-gui01')
failed=json.loads((root/'dashboard/result.json').read_text(encoding='utf8'))
assert failed['status']=='failed' and failed['guard_restore']['ok']
assert all(c['cleaned'] and c['job_empty_affirmed'] for c in failed['cleanup'])
assert [x['label'] for x in failed['processes']]==['seed']
assert "ModuleNotFoundError: No module named 'index'" in (root/'dashboard/seed.stderr').read_text(encoding='utf8')
rows=[]
for oldname,newname in [('prepare_native_gui08.py','prepare_native_gui08_02.py'),('native_media08_seed.py','native_media08_seed02.py'),('native_gui08_driver.py','native_gui08_driver02.py'),('build_native_gui08_launchers.py','build_native_gui08_launchers02.py')]:
 old=(s/oldname).read_text(encoding='utf8');new=old.replace('native-gui01','native-gui02')
 if oldname=='native_media08_seed.py':
  assert new.count('import index as index_mod')==1
  new=new.replace('import index as index_mod',"sys.path.insert(0, str(app))  # Explicit verified installation, never caller cwd.\nimport index as index_mod",1)
 new=new.replace("_scratch/native_media08_seed.py","_scratch/native_media08_seed02.py").replace("_scratch/native_gui08_driver.py","_scratch/native_gui08_driver02.py")
 ast.parse(new)
 with (s/newname).open('x',encoding='utf8',newline='\n') as f:f.write(new)
 patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=oldname,tofile=newname))
 with (s/(newname+'.diff')).open('x',encoding='utf8',newline='\n') as f:f.write(patch)
 rows.append({'before':oldname,'after':newname,'before_sha256':hashlib.sha256((s/oldname).read_bytes()).hexdigest(),'after_sha256':hashlib.sha256((s/newname).read_bytes()).hexdigest()})
review={'scope':'Pre-execution bootstrap-path repair and fresh profile labels only; original failure and sealed scripts unchanged','original_gui_started':False,'original_seed_exit':1,'owned_cleanup_affirmed':True,'guard_restored':True,'seed_import_is_installed_path_only':True,'behavior_assertions_changed':False,'product_changed':False,'new_native_observation_claimed':False,'files':rows}
with (s/'native08-seed-preexecution-review.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
print(json.dumps(review))
