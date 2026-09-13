import hashlib,json,os,subprocess,sys
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root)
fixture=root / '_scratch/nltk-upstream-before-local13/nltk'
receipt=json.loads((fixture.parent/'receipt.json').read_text(encoding='utf8'))
for rel,digest in receipt['files'].items():assert hashlib.sha256((fixture/rel).read_bytes()).hexdigest()==digest
wheel=root / '_scratch/nltk-wheel-astra-artifact01/nltk-3.10.3-py3-none-any.whl'
assert hashlib.sha256(wheel.read_bytes()).hexdigest()=='ff9598a8e20518ee0d557745890cc4435b9578489e2dcbc69c4f81fa060caf7c'
env=os.environ.copy()
for key in list(env):
    upper=key.upper()
    if any(s in upper for s in ('API_KEY','AUTH_TOKEN','ACCESS_TOKEN','BASE_URL','OAUTH_TOKEN')) or upper.startswith(('ANTHROPIC_','OPENAI_','GOOGLE_API_','GEMINI_API_','XAI_','CLAUDE_CODE_USE_')):env.pop(key,None)
env.update(UOINK_NLTK_BASE_SOURCE=str(fixture),UOINK_UPSTREAM_NLTK_WHEEL=str(wheel),
           PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
           IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db')
command=[sys.executable,'-I','-S','-B',str(root/'_scratch/run_partitioned_repaired_tree.py'),
         '--source',source,'--label','ryan-final-partitioned-07']
print(json.dumps({'source':source,'command':command,'pristine_fixture_files':len(receipt['files'])}),flush=True)
raise SystemExit(subprocess.run(command,cwd=root,env=env).returncode)
