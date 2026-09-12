"""Seal reviewed observer copies before the package-07 installed stages."""
from pathlib import Path
import hashlib,json,shutil
r=Path(__file__).resolve().parents[1];out=r/'docs/library/proof/installed07-instrument-review-2026-09-12'
out.mkdir(exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf8',newline='\n')
names=['published_chapter07.py','observe_published_chapter07.py','p4_operator_client07.py','run_installed_client07.py',
       'freeze_client07_inputs.py','prepare_client07_instruments.py','client07-instrument-adaptations.json',
       'p4_operator_client07.py.diff','run_installed_client07.py.diff',
       'prepare_installed07_instruments.py','installed07-instrument-adaptations.json',
       'inventory_installed_extras07.py','inventory_installed_extras07.py.diff',
       'run_installed_decoders07.py','run_installed_decoders07.py.diff',
       'run_installed_decoders07_portable.py','run_installed_decoders07_portable.py.diff',
       'uninstall_retained_package06.ps1','uninstall_retained_package06.diff','uninstall06-adaptation-review.json',
       'agent_receipt_observe06.py','agent_install_observer05.ps1','seal_installed07_instruments.py']
for name in names:shutil.copyfile(r/'_scratch'/name,out/name)
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file()}
(out/'SHA256.json').write_text(json.dumps({'scope':'Pre-execution observer source and review only; no installed pass claimed','files':files},indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'payloads':len(files),'no_installed_measurement':True}))
