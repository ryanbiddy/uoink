"""One reviewed static trace; no object or tensor construction."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
source = root / '_scratch/vad-symbolic-adapter-proposal01/read_symbolic_inventory.py'
expected = '0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc'
raw = source.read_bytes()
assert hashlib.sha256(raw).hexdigest() == expected
review = (root / '_scratch/vad-symbolic-review01/ADAPTER-FINAL-REVIEW.md').read_bytes()
assert hashlib.sha256(review).hexdigest() == '361e5b5f2f4ec6c873cff70ba06970e6b32be44ef42878d527ea3278a40aa60d'
assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
out = root / '_scratch/vad-symbolic-run01-launch'
out.mkdir(exist_ok=False)
(out / 'independent-review.md').write_bytes(review)
(out / 'root-brief.md').write_bytes((root / '_scratch/VAD-SYMBOLIC-RUN01-BRIEF-2026-09-13.md').read_bytes())
reader = out / 'read_symbolic_inventory.py'
reader.write_bytes(raw)
assert hashlib.sha256(reader.read_bytes()).hexdigest() == expected
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
command = [r'C:\Python314\python.exe', '-I', '-S', '-B', str(reader), '--inspect', '--run-id', 'symbolic-run01']
(out / 'plan.json').write_text(json.dumps({'command': command, 'cwd': str(root), 'source_sha256': expected,
    'started_utc': datetime.now(timezone.utc).isoformat(), 'removed_variable_names': sorted(removed),
    'scope': 'One fixed-hash static symbolic trace; no object, tensor, model or converter execution',
    'IG_FORBIDDEN_LIVE_set_before_startup': True}, indent=2) + '\n', encoding='utf8')
with (out / 'stdout.log').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
    result = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr)
after = hashlib.sha256(reader.read_bytes()).hexdigest()
(out / 'exit.json').write_text(json.dumps({'actual_process_exit': result.returncode,
    'reader_sha256_after': after, 'reader_unchanged': after == expected,
    'finished_utc': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n', encoding='utf8')
print((out / 'stdout.log').read_text())
print((out / 'exit.json').read_text())
raise SystemExit(result.returncode if after == expected else 99)
