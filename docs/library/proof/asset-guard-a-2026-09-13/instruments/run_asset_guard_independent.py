import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('target',choices=['worker','checkout']);a=p.parse_args()
root=Path('E:/AI/projects/uoink/worktrees/asset-guard-a') if a.target=='worker' else r
label='agv01' if a.target=='worker' else 'agc01'
out=r/'_scratch'/(label+'-launch');out.mkdir(exist_ok=False)
selectors=['tests/test_whisper_cache_consent.py','tests/test_phase6_evaluation.py','tests/test_podcast_background_jobs.py','tests/test_podcast_watch.py','tests/test_podcast_workflow_truth.py','tests/test_library_adapters.py','tests/test_packaged_decoder_loader.py','tests/test_installer_dependency_lock.py']
guard=root/'_scratch/agw_heavy_import_guard.py'
assert hashlib.sha256(guard.read_bytes()).hexdigest()=='4a97b84d24edea4bca28958183ffc9dd442be0522f1b0a7b230e441630a879d9'
env=os.environ.copy()
for k in list(env):
    u=k.upper()
    if re.search('API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL',u) or u.startswith(('ANTHROPIC_','OPENAI_','GOOGLE_API_','GEMINI_API_','XAI_','GROK_','CLAUDE_CODE_USE_')) or u in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'):env.pop(k,None)
env.update(LOCALAPPDATA=r'C:\Users\hello\AppData\Local',IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',AGW_HEAVY_GUARD_RECEIPT=str(out/'heavy-import-guard.json'))
cmd=[str(r/'_scratch/ig-native/Scripts/python.exe'),'-B',str(r/'_scratch/integrator_verify.py'),'--root',str(root),'--label',label,*selectors,'--runxfail','-p','_scratch.agw_heavy_import_guard']
files=[root/'whisper_runner.py',guard,Path(__file__),*[root/n for n in selectors]]
hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
(out/'plan.json').write_text(json.dumps({'command':cmd,'root':str(root),'inputs':hashes},indent=2)+'\n',encoding='utf8')
with (out/'launcher.log').open('x',encoding='utf8') as log:result=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
same=hashes=={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
receipt=json.loads((out/'heavy-import-guard.json').read_bytes())
valid=same and not receipt['already_loaded_at_startup'] and receipt['guard_installed_at_finish']
(out/'result.json').write_text(json.dumps({'verifier_exit':result.returncode,'inputs_unchanged':same,'guard_valid':valid,'guard':receipt},indent=2)+'\n',encoding='utf8')
print('\n'.join((out/'launcher.log').read_text(encoding='utf8').splitlines()[-22:]))
raise SystemExit(result.returncode if valid else 99)
