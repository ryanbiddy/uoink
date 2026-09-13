"""Repeat exact reviewed eight-case Hub contracts in a fresh root directory."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
source = root / '_scratch/companion-hub-keyword-qualified01'
out = root / '_scratch/astra-hub-keyword01'
raw_seal = (source / 'INPUT-QUALIFICATION.json').read_bytes()
assert hashlib.sha256(raw_seal).hexdigest() == '4bba9f3ac322a81827fe29c64d8231aedd7956d3bcc7fce368a5345cd5eaa587'
rows = json.loads(raw_seal)['payloads']
out.mkdir(exist_ok=False)
for row in rows:
    raw = (source / row['file']).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    with (out / row['file']).open('xb') as stream:
        stream.write(raw)
(out / 'INPUT-QUALIFICATION.json').write_bytes(raw_seal)
env = os.environ.copy()
for key in list(env):
    upper = key.upper()
    if (re.search('API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL', upper)
        or upper.startswith(('ANTHROPIC_', 'OPENAI_', 'GOOGLE_API_', 'GEMINI_API_', 'XAI_', 'GROK_', 'CLAUDE_CODE_USE_'))
        or upper in {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'PYTHONPATH', 'PYTHONHOME'}):
        env.pop(key)
env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1',
           IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db')
outcomes = []
for label in ['baseline03', 'patched03']:
    command = [r'C:\Python314\python.exe', '-I', '-S', '-B', r'_scratch\astra-hub-keyword01\qualify.py', label]
    with (out / (label + '-console.log')).open('xb') as stream:
        process = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
    receipt = json.loads((out / label / 'result.json').read_bytes())
    outcomes.append({'command': command, 'cwd': str(root), 'actual_child_exit': process.returncode, 'receipt': receipt})
unchanged = all(hashlib.sha256((out / row['file']).read_bytes()).hexdigest() == row['sha256'] for row in rows)
(out / 'ROOT-RESULT.json').write_text(json.dumps({'inputs_unchanged': unchanged, 'outcomes': outcomes}, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'inputs_unchanged': unchanged, 'outcomes': outcomes}))
assert unchanged and all(item['receipt']['guard_valid'] for item in outcomes)
assert outcomes[0]['actual_child_exit'] == 1 and outcomes[0]['receipt']['passed'] == 4 and outcomes[0]['receipt']['errors'] == 4
assert outcomes[1]['actual_child_exit'] == 0 and outcomes[1]['receipt']['passed'] == 8
