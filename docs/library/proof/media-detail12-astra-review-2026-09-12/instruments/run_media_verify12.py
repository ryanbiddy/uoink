import os,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
env=os.environ.copy()
for key in list(env):
    upper=key.upper()
    if any(x in upper for x in ('API_KEY','AUTH_TOKEN','ACCESS_TOKEN','BASE_URL')) or upper.startswith(('ANTHROPIC_','OPENAI_','GOOGLE_API_','GEMINI_API_','XAI_')):
        env.pop(key,None)
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db')
cmd=[str(r/'_scratch/ig-native/Scripts/python.exe'),'-B',str(r/'_scratch/integrator_verify.py'),*sys.argv[1:]]
raise SystemExit(subprocess.run(cmd,cwd=r,env=env).returncode)
