"""Adapt documentary instruments before use; no observation or outcome is fabricated."""
from pathlib import Path
import ast,difflib,hashlib,json
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
changes=[]
def save(oldname,newname,new):
 old=(s/oldname).read_text()
 if newname.endswith('.py'):ast.parse(new)
 with (s/newname).open('x',encoding='utf8',newline='\n') as f:f.write(new)
 patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=oldname,tofile=newname))
 with (s/(newname+'.diff')).open('x',encoding='utf8',newline='\n') as f:f.write(patch)
 changes.append({'old':oldname,'new':newname,'sha256':hashlib.sha256(new.encode()).hexdigest()})
def base(name):return (s/name).read_text().replace('07','08')
new=base('seal_installed07.py')
new=new.replace("Agent Install 06\\uninstall-before-package08", "Agent Install 07\\uninstall-before-package08")
new=new.replace("assert summary['setup_observed'] and summary['actual_client_tool_calls']==44", "assert summary['setup_observed'] and summary['actual_client_tool_calls']==summary['successful_terminal_hooks'] and summary['failed_terminal_hooks']==0")
new=new.replace("'uninstall_retained_package06.ps1','uninstall_retained_package06.diff'", "'uninstall_retained_package07.ps1','uninstall_retained_package07.diff'")
new=new.replace("'complete_browser08.py','review_browser08.py','agent-browser08.json'", "'complete_browser08.py','review_browser08.py','agent-browser08.json','run_browser08.py'")
new=new.replace("'review_native08.py','published_chapter08.py','observe_published_chapter08.py','review_published08.py','review_published08_02.py',\n    'review_published08_02.py.diff','repair_published_review08.py','published08-review-failure01.json',", "'review_native08.py','published_chapter08.py','observe_published_chapter08.py','review_published08_02.py',")
new=new.replace("'prepare_collection08.py','review_installed08.py','seal_installed08.py'", "'prepare_collection08.py','review_installed08.py','seal_installed08.py',\n    'package08-instrument-adaptations.json','package08-final-source-rebinding.json',\n    'installed08-aggregate-preexecution-review.json','review_installed08.py.preexecution.diff',\n    'prepare_delivery08.py','seal_installed08.py.diff'")
new=new.replace("'client_calls':44", "'client_calls':summary['actual_client_tool_calls']")
save('seal_installed07.py','seal_installed08.py',new)
new=base('build_release_bundle07.py')
new=new.replace(" 'candidate-package-08-2026-09-12','installed08-instrument-review-2026-09-12',", " 'candidate-package-08-2026-09-12','installed08-instrument-review-2026-09-12',\n 'media-detail12-astra-review-2026-09-12','native-note12-astra-review-2026-09-12',\n 'native-gui-package07-2026-09-12','native-gui-package08-2026-09-12',\n 'native-client-isolation12-astra-review-2026-09-12',\n 'security-repair-gemini-2026-09-12','security12-astra-review-2026-09-12',\n 'security-backport12-astra-review-2026-09-12',\n 'candidate-package-07-2026-09-12','ryan-agent-installed-07-2026-09-12',")
new=new.replace('No label application, paid API, new source fetch or speaker-attribution claim.', 'Label application stays disabled; this kit authorizes no paid API, new source fetch or speaker attribution. The earlier Desktop isolation attempt is invalid; read the incident record before any Desktop-client work.')
save('build_release_bundle07.py','build_release_bundle08.py',new)
save('review_bundle07.py','review_bundle08.py',base('review_bundle07.py'))
save('check_runbook07.ps1','check_runbook08.ps1',base('check_runbook07.ps1'))
new=base('verify_committed_package07_proofs.py')
start=new.index('names = [');end=new.index('\ncounts =',start)
names=['ryan-final-partitioned-06-2026-09-12','candidate-package-08-2026-09-12',
 'repaired-lock-audit-2026-09-11','ryan-agent-installed-08-2026-09-12',
 'installed08-instrument-review-2026-09-12','sqlite-deadline-cleanup-2026-09-12',
 'ryan-installed-client-06-2026-09-12','media-detail12-astra-review-2026-09-12',
 'native-note12-astra-review-2026-09-12','native-gui-package07-2026-09-12',
 'native-gui-package08-2026-09-12','native-client-isolation12-astra-review-2026-09-12',
 'security-repair-gemini-2026-09-12','security12-astra-review-2026-09-12',
 'security-backport12-astra-review-2026-09-12']
new=new[:start]+'names = '+repr(names)+new[end:]
new=new.replace("files = json.loads((folder / 'SHA256.json').read_text(encoding='utf8'))['files']", "seal = json.loads((folder / 'SHA256.json').read_text(encoding='utf8'))\n    files = seal.get('files',seal)\n    assert files and all(isinstance(row,dict) and 'sha256' in row and 'bytes' in row for row in files.values()),name")
save('verify_committed_package07_proofs.py','verify_committed_package08_proofs.py',new)
new=base('run_bundle07_once.py')
new=new.replace("expected='81e4495fdcf5d6365587e408e7e61c68440b9e01'", "expected=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()")
assert '81e4495' not in new
new=new.replace('6a89189d601467eeff33d304c2c9b69cdd2e6d0b','b8e44fbc0a16950a22b29ead66951fcb80b2d6e8').replace('ryan-final-partitioned-04','ryan-final-partitioned-06')
save('run_bundle07_once.py','run_bundle08_once.py',new)
new=base('seal_review_bundle07.py')
start=new.index("             'prepare_delivery08.py'");end=new.index("):\n    shutil.copyfile",start)
new=new[:start]+"             'prepare_delivery08.py', 'delivery08-adaptation-review.json',\n             'installed08-staged-proof-check.json', 'run_bundle08_once.py',\n             'build_release_bundle08.py.diff', 'review_bundle08.py.diff',\n             'seal_review_bundle08.py.diff'"+new[end:]
save('seal_review_bundle07.py','seal_review_bundle08.py',new)
with (s/'delivery08-adaptation-review.json').open('x',encoding='utf8') as f:json.dump({'scope':'Pre-execution documentary adaptation. Current outcomes are derived from new receipts, not copied. Native Desktop launch removed and retained incident must be included.','files':changes},f,indent=2)
print(json.dumps({'prepared':len(changes),'observations_started':False}))
