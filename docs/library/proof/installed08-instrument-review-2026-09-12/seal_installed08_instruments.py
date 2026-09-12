"""Retain reviewed new observer copies and their pre-execution histories."""
from pathlib import Path
import ast,hashlib,json,shutil
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
out=r/'docs/library/proof/installed08-instrument-review-2026-09-12'
names=['published_chapter08.py','observe_published_chapter08.py','p4_operator_client08.py','run_installed_client08.py',
 'freeze_client08_inputs.py','prepare_native08.py','prepare_collection08.py','review_native08.py','review_client08.py','review_published08_02.py',
 'inventory_installed_extras08.py','run_installed_decoders08.py','run_installed_decoders08_portable.py',
 'uninstall_retained_package07.ps1','uninstall_retained_package07.diff',
 'agent_receipt_observe06.py','agent_install_observer05.ps1','seal_installed08_instruments.py',
 'prepare_package08_instruments.py','package08-instrument-adaptations.json','rebind_package08_final_source.py',
 'package08-final-source-rebinding.json','package08-instrument-adaptations-before-final-source.json',
 'run_installed_client08.py.a25-draft.txt','run_installed_client08.py.final-source.diff',
 'observe_published_chapter08.py.a25-draft.txt','observe_published_chapter08.py.final-source.diff',
 'prepare_native08_safety_correction.py','native_gui08_driver.py','build_native_gui08_launchers.py','native_media08_seed.py','prepare_native_gui08.py',
 'run_browser08.py','review_browser08.py','complete_browser08.py','agent-browser08.json',
 'correct_installed08_aggregate.py','review_installed08.py','review_installed08.py.initial-draft.txt',
 'review_installed08.py.preexecution.diff','installed08-aggregate-preexecution-review.json',
 'prepare_delivery08.py','delivery08-adaptation-review.json','seal_installed08.py','seal_installed08.py.diff']
sources={name:s/name for name in names}
for q in (s/'native08-preexecution-corrections').rglob('*'):
 if q.is_file():sources['native08-preexecution-corrections/'+q.relative_to(s/'native08-preexecution-corrections').as_posix()]=q
for name,q in sources.items():
 assert q.is_file(),name
 if q.suffix=='.py':ast.parse(q.read_text(encoding='utf8'))
driver=(s/'native_gui08_driver.py').read_text()
assert "mode == 'dashboard'" in driver and 'CLAUDE_USER_DATA_DIR' not in driver and 'WindowsApps' not in driver
assert "for mode in ('dashboard',)" in (s/'build_native_gui08_launchers.py').read_text()
out.mkdir(exist_ok=False);(out/'.gitattributes').write_bytes(b'* -text\n')
for name,q in sorted(sources.items()):
 target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(q,target)
files={q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(out.rglob('*')) if q.is_file()}
(out/'SHA256.json').write_text(json.dumps({'scope':'Pre-execution observer copies; retained earlier drafts and corrections are historical. No installed or model outcome claimed. Native launch accepts only the isolated Uoink dashboard.','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(files),'syntax_checked':True,'desktop_launch_removed':True,'installed_measurement':False}))
