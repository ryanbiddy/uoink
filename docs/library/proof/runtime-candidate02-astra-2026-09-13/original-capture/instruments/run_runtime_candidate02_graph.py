"""Record one offline metadata validator invocation and its actual exit."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

root = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
capture = root / '_scratch/runtime-candidate02-metadata'
output = capture / 'graph01'
if output.exists():
    raise FileExistsError('Fresh graph01 required')
output.mkdir()
validator = root / 'scripts/check_runtime_graph.py'
bootstrap = r"""import runpy,sys
sys.path.append(r'C:\Users\hello\AppData\Roaming\Python\Python314\site-packages')
def guard(event,args):
    if event.startswith('socket.') or event=='subprocess.Popen':
        raise PermissionError('Offline metadata validation')
    if event=='open' and args and str(args[0]).replace(chr(47),chr(92)).casefold()==r'C:\Users\hello\AppData\Local\Uoink\index.db'.casefold():
        raise PermissionError('Forbidden live index')
sys.addaudithook(guard)
path=sys.argv.pop(1)
runpy.run_path(path,run_name='__main__')
"""
command = [sys.executable, '-I', '-S', '-B', '-c', bootstrap, str(validator),
           '--selection', str(capture / 'selection.json'),
           '--evidence-dir', str(capture / 'evidence'),
           '--output-json', str(output / 'result.json')]
environment = {key: value for key, value in os.environ.items()
               if not re.search(r'(?i)(API.?KEY|ACCESS.?TOKEN|AUTH.?TOKEN|BEARER|ANTHROPIC|OPENAI|GEMINI|GROK|XAI|HF_TOKEN|HUGGING_FACE_HUB_TOKEN|BASE_URL)', key)}
environment['PYTHONDONTWRITEBYTECODE'] = '1'
record = {'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
          'command': command, 'actual_exit': None,
          'validator_sha256': hashlib.sha256(validator.read_bytes()).hexdigest(),
          'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(output / 'execution.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
with (output / 'stdout.txt').open('wb') as stdout, (output / 'stderr.txt').open('wb') as stderr:
    child = subprocess.run(command, env=environment, cwd=root, stdout=stdout, stderr=stderr, check=False)
record.update(actual_exit=child.returncode, finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
if (output / 'result.json').exists():
    result = json.loads((output / 'result.json').read_text(encoding='utf8'))
    record['result'] = {key: result.get(key) for key in ('status', 'passed', 'selection_count', 'active_edges_count', 'missing_packages', 'conflicting_constraints', 'wheel_failures', 'incomplete_evidence', 'manifest_errors')}
(output / 'execution.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
print(json.dumps(record, indent=2))
raise SystemExit(child.returncode)
