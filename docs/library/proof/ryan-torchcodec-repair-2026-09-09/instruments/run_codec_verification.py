import argparse,json,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--label',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1]
env=os.environ.copy()
for key in list(env):
 if key.endswith('API_KEY') or key=='ANTHROPIC_AUTH_TOKEN' or key.startswith('CLAUDE_CODE_USE_'):env.pop(key,None)
env['IG_FORBIDDEN_LIVE']=r'C:\Users\hello\AppData\Local\Uoink\index.db'
selectors=['tests/test_docs_live_contracts.py','tests/test_c02_reliability_faster_whisper.py','tests/test_installer_dependency_lock.py','tests/test_installer_download_accuracy.py','tests/test_installer_files_complete.py','tests/test_build_guide_accuracy.py','tests/test_current_doc_references.py','tests/test_packaged_decoder_loader.py','tests/test_podcast_workflow_truth.py']
cmd=[str(r/'_scratch/ig-native/Scripts/python.exe'),'-B',str(r/'_scratch/integrator_verify.py'),'--root',a.root,'--label',a.label,*selectors]
raise SystemExit(subprocess.call(cmd,cwd=a.root,env=env))
