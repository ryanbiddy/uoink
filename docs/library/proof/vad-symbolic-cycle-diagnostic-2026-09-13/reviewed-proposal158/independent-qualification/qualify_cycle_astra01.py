"""Independent run of the reviewed reporting-only cycle diagnostic protocol."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
source = root / '_scratch/vad-symbolic-cycle-diagnostic-proposal01'
out = root / '_scratch/astra-cycle-diagnostic01'
expected = {
    'before/read_symbolic_inventory.py': '0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc',
    'read_symbolic_inventory.py': '15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd',
    'qualify_cycle.py': 'f76fa88e58bba46130c2b8d44c7d17543ff46334c73976adb138efa0fa169f6a',
    'before/read_checkpoint_inventory.py': '67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5',
    'before/symbolic_trace.py': 'f41ce88a2eceee565fcc9116e19f064723bf3339ffe4ca8669ae20bff6033127',
}
assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
for name, sha in expected.items():
    assert hashlib.sha256((source / name).read_bytes()).hexdigest() == sha
out.mkdir(exist_ok=False)
for name in expected:
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / name, target)
env = os.environ.copy()
removed = []
for key in list(env):
    upper = key.upper()
    if (re.search('API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL', upper)
            or upper.startswith(('ANTHROPIC_', 'OPENAI_', 'GOOGLE_API_', 'GEMINI_API_', 'XAI_', 'GROK_', 'CLAUDE_CODE_USE_'))
            or upper in {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'PYTHONPATH', 'PYTHONHOME'}):
        removed.append(key)
        env.pop(key)
env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1')
command = [r'C:\Python314\python.exe', '-I', '-S', '-B', str(out / 'qualify_cycle.py'), 'astra-cycle01']
(out / 'plan.json').write_text(json.dumps({'command': command, 'cwd': str(out), 'input_sha256': expected,
    'started_utc': datetime.now(timezone.utc).isoformat(), 'removed_variable_names': sorted(removed),
    'scope': 'Same 36 synthetic cases; no actual checkpoint or real main paths',
    'IG_FORBIDDEN_LIVE_set_before_startup': True}, indent=2) + '\n', encoding='utf8')
with (out / 'stdout.json').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
    process = subprocess.run(command, cwd=out, env=env, stdout=stdout, stderr=stderr)
unchanged = all(hashlib.sha256((out / name).read_bytes()).hexdigest() == sha for name, sha in expected.items())
(out / 'exit.json').write_text(json.dumps({'actual_qualification_exit': process.returncode, 'inputs_unchanged': unchanged,
    'finished_utc': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n', encoding='utf8')
print(json.dumps({'actual_qualification_exit': process.returncode, 'inputs_unchanged': unchanged}))
print((out / 'stdout.json').read_text())
raise SystemExit(process.returncode if unchanged else 99)
