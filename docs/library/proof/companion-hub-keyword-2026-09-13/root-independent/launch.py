"""Retain relative-script/root-cwd runs with exact raw exits and scrubbed keys."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
out = Path(__file__).absolute().parent
parser = argparse.ArgumentParser()
parser.add_argument('label', choices=('baseline03', 'patched03'))
label = parser.parse_args().label
launch = out / ('launch-' + label)
launch.mkdir(exist_ok=False)
env = os.environ.copy()
removed = []
for key in list(env):
    upper = key.upper()
    if (re.search('API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL', upper)
        or upper.startswith(('ANTHROPIC_', 'OPENAI_', 'GOOGLE_API_', 'GEMINI_API_', 'XAI_', 'GROK_', 'CLAUDE_CODE_USE_'))
        or upper in {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'PYTHONPATH', 'PYTHONHOME'}):
        removed.append(key)
        env.pop(key)
env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1',
    IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db')
command = [r'C:\Python314\python.exe', '-I', '-S', '-B', r'_scratch\companion-hub-keyword-qualified01\qualify.py', label]
cwd = out.parents[1]
(launch / 'plan.json').write_text(json.dumps({'command': command, 'cwd': str(cwd), 'scrubbed_variable_names': sorted(removed), 'started_utc': datetime.now(timezone.utc).isoformat()}, indent=2)+'\n', encoding='utf-8', newline='\n')
with (launch / 'console.log').open('x', encoding='utf-8', newline='\n') as log:
    code = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
(launch / 'result.json').write_text(json.dumps({'actual_child_exit': code, 'actual_outer_exit': code, 'finished_utc': datetime.now(timezone.utc).isoformat()}, indent=2)+'\n', encoding='utf-8', newline='\n')
print((launch / 'console.log').read_text(encoding='utf-8'))
raise SystemExit(code)
