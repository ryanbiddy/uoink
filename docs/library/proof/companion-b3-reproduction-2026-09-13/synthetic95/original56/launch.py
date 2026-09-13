"""Retain commands and actual exits for reviewed B3 synthetic qualification."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
out = Path(__file__).absolute().parent
label = 'b3w01'
destination = out / ('launch-' + label)
destination.mkdir(exist_ok=False)
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
command = [r'C:\Python314\python.exe', '-I', '-S', '-B', str(out / 'run-synthetic.py'), label]
paths = [out / name for name in ('build_faster_whisper_localassets_wheel.py', 'tests-synthetic.py', 'run-synthetic.py', 'launch.py', 'BRIEF.md')]
paths.extend(path for folder in ('recipe', 'fixtures') for path in sorted((out / folder).rglob('*')) if path.is_file())
hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
(destination / 'plan.json').write_text(json.dumps({'command': command, 'cwd': str(out), 'input_hashes': hashes,
    'scrubbed_variable_names': sorted(removed), 'started_utc': datetime.now(timezone.utc).isoformat()}, indent=2)+'\n', encoding='utf-8', newline='\n')
with (destination / 'console.log').open('x', encoding='utf-8', newline='\n') as log:
    code = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
unchanged = all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in hashes.items())
(destination / 'result.json').write_text(json.dumps({'actual_child_exit': code, 'actual_outer_exit': code if unchanged else 99,
    'inputs_unchanged': unchanged, 'finished_utc': datetime.now(timezone.utc).isoformat()}, indent=2)+'\n', encoding='utf-8', newline='\n')
print((destination / 'console.log').read_text(encoding='utf-8'))
raise SystemExit(code if unchanged else 99)
