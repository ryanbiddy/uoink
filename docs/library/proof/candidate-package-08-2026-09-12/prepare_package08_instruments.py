"""Adapt already reviewed observers to fresh package/profile labels only."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch';changes=[]
source='a25e3be1c4b8ca1f0c064dd8383b49870f23465f'
names=['review_package07_notices.py','compare_package07_repair_wheels.py','verify_package07_graph.py','review_package07_pins.py','finalize_package07.py',
       'inventory_installed_extras07.py','run_installed_decoders07.py','run_installed_decoders07_portable.py',
       'p4_operator_client07.py','run_installed_client07.py','freeze_client07_inputs.py',
       'published_chapter07.py','observe_published_chapter07.py','review_published07_02.py',
       'prepare_native07.py','prepare_collection07.py','prepare_native_gui07.py','native_gui07_driver.py']
for name in names:
    old=(s/name).read_text(encoding='utf8')
    new=old.replace('package07','package08').replace('package-07','package-08').replace('Agent Install 07','Agent Install 08')
    for prefix in ('client','chapter','published','native','collection','gui','decoders'):
        new=new.replace(prefix+'07',prefix+'08')
    new=new.replace('6a89189d601467eeff33d304c2c9b69cdd2e6d0b',source)
    if name=='finalize_package07.py':
        oldblock="for name in ('package08-instrument-adaptations.json','package08-finalizer-review.json',\n             'package08-finalizer-review.diff','finalize_package08_initial_draft.py'):"
        assert oldblock in new
        new=new.replace(oldblock,"for name in ('package08-instrument-adaptations.json','prepare_package08_instruments.py','finalize_package08.py.diff'):")
    target=s/name.replace('07','08');assert not target.exists();ast.parse(new)
    target.write_text(new,encoding='utf8',newline='\n')
    delta=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=name,tofile=target.name))
    (s/(target.name+'.diff')).write_text(delta,encoding='utf8',newline='\n')
    changes.append({'before':name,'after':target.name,'scope':'New package/profile/source labels; finalizer archives this current adaptation instead of obsolete draft review. Existing checks unchanged.',
      'before_sha256':hashlib.sha256((s/name).read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'executed':False})
old=(s/'seal_partitioned_final_tree04.py').read_text(encoding='utf8')
new=old.replace('ryan-final-partitioned-04-2026-09-12','ryan-final-partitioned-05-2026-09-12').replace('seal_partitioned_final_tree04.py','seal_partitioned_final_tree05.py')
new=new.replace('_scratch/ryan-final-partitioned-03/expected-membership.json','_scratch/ryan-final-partitioned-04/expected-membership.json').replace("allowed = ('tests/test_sqlite_deadline_cleanup.py::',)","allowed = ('tests/test_note_readiness_truth.py::',)").replace('len(added)==5','len(added)==16')
ast.parse(new);(s/'seal_partitioned_final_tree05.py').write_text(new,encoding='utf8',newline='\n')
(s/'seal_partitioned_final_tree05.py.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='seal_partitioned_final_tree04.py',tofile='seal_partitioned_final_tree05.py')),encoding='utf8',newline='\n')
(s/'package08-instrument-adaptations.json').write_text(json.dumps(changes,indent=2)+'\n',encoding='utf8',newline='\n')
exe=r/'build/Uoink-Setup-3.8.0.exe';expected='308205ec6273dafe3fb0b2f5273e713803e6e78ea989d883217ecd813a17d32b'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert sha(exe)==expected
archive=s/'Uoink-Setup-3.8.0-package07-308205ec.exe';assert not archive.exists()
shutil.copyfile(exe,archive);assert sha(archive)==expected
(s/'package07-preserved-before08.json').write_text(json.dumps({'source':str(exe),'archive':str(archive),'sha256':expected,'bytes':archive.stat().st_size,'verified':True},indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'adapted':len(changes)+1,'old_exe_preserved':True,'qualification_source':source}))
