"""Archive this completed text review; execute no reviewed source."""
import collections
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
root = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker = Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\028ec7d7-34f\gemini')
out = root / '_scratch/gemini-runtime-orchestration-council-receipts01'
assert not out.exists()
out.mkdir()
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def save(name, raw):
    with (out / name).open('xb') as stream:
        stream.write(raw)
def data(name, value):
    save(name, (json.dumps(value, indent=2, ensure_ascii=True)+'\n').encode('ascii'))
report = 'docs/library/GEMINI-RUNTIME-ORCHESTRATION-COUNCIL-REVIEW-2026-09-13.md'
brief = 'docs/library/GEMINI-RUNTIME-ORCHESTRATION-COUNCIL-BRIEF-2026-09-13.md'
save('worker-report.md', (worker / report).read_bytes())
a, b = (worker / brief).read_bytes(), (root / brief).read_bytes()
assert a.replace(b'\r\n', b'\n') == b.replace(b'\r\n', b'\n')
save('worker-brief.md', a)
save('checkout-brief.md', b)
data('brief-transport.json', {'worker_sha256':sha(a), 'checkout_sha256':sha(b),
    'only_crlf_lf_difference':True, 'applies_to_brief_only':True})
asr = 'author-history209/asr-author03/adapter-preflight03/'
sources = [
 ('asr-owned-adapter-2026-09-13', asr+'asr_loading_adapter.py'),
 ('asr-owned-adapter-2026-09-13', asr+'PORT-CONTRACTS.md'),
 ('asr-owned-adapter-2026-09-13', asr+'CALL-SITE-SPLICES.md'),
 ('vad-native-state-bridge-2026-09-13', 'objects/b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2.txt'),
 ('vad-native-state-bridge-2026-09-13', 'objects/38a51bb9708302d2a29bc8d63bb6082934ee6b07abf720d0052b8cb897f82070.txt'),
 ('vad-d1-wrapper-2026-09-13', 'preparation/before/launch_d1.py'),
 ('vad-d1-wrapper-2026-09-13', 'preparation/before/d1_child.py'),
 ('vad-d1-wrapper-2026-09-13', 'preparation/run-root.repaired.ps1')]
bindings = []
for number, (folder, name) in enumerate(sources, 1):
    base = Path('docs/library/proof') / folder
    seal = json.loads((root / base / 'SHA256.json').read_bytes())
    assert len(seal['files']) == seal['payload_count']
    rows = [row for row in seal['files'] if row['path'] == name]
    assert len(rows) == 1
    row = rows[0]
    raw = (root / base / name).read_bytes()
    assert raw == (worker / base / name).read_bytes()
    assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
    archived = f'source-{number:02d}.txt'
    save(archived, raw)
    bindings.append({'path':(base/name).as_posix(), 'archive':archived,
                     'sha256':sha(raw), 'bytes':len(raw), 'worker_checkout_seal_equal':True})
data('source-bindings.json', bindings)
run_id = '028ec7d7-34ff-44d6-af77-366c7294709c'
with sqlite3.connect('file:C:/Users/hello/AppData/Local/AgentControlRoom/control-room.sqlite?mode=ro', uri=True) as connection:
    connection.row_factory = sqlite3.Row
    run = dict(connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone())
    agents = [dict(row) for row in connection.execute('SELECT * FROM agent_runs WHERE run_id=?', (run_id,))]
    events = [dict(row) for row in connection.execute('SELECT * FROM events WHERE run_id=? ORDER BY rowid', (run_id,))]
assert run['status'] == 'completed' and len(agents) == 1 and agents[0]['status'] == 'completed'
data('run.json', run)
data('agent-runs.json', agents)
data('events.json', events)
controller = root / '_scratch/gemini-runtime-orchestration-council01'
for name in ('controller-stdout.log', 'controller-stderr.log', 'controller-exit.json'):
    save(name, (controller / name).read_bytes())
assert json.loads((out/'controller-exit.json').read_bytes())['actual_controller_exit'] == 0
assert (out/'controller-stderr.log').read_bytes() == b''
subprocess.run(['git', 'add', '-N', '--', report], cwd=worker, check=True)
with (out/'worker.patch').open('xb') as patch:
    result = subprocess.run(['git', 'diff', '--binary', '--no-ext-diff', '--no-color', '--', report], cwd=worker, stdout=patch, check=True)
data('patch-exit.json', {'actual_git_diff_exit':result.returncode,
    'patch_sha256':sha((out/'worker.patch').read_bytes()), 'scope':'one new review document'})
summary = {'sources_verified':len(bindings), 'events':len(events),
    'tool_messages':dict(collections.Counter(row['message'] for row in events if row['type']=='tool')),
    'report_sha256':sha((out/'worker-report.md').read_bytes()),
    'patch_sha256':sha((out/'worker.patch').read_bytes()), 'controller_exit':0,
    'new_tests_run':False, 'market_approval':False}
data('COLLECTION.json', summary)
print(json.dumps(summary))
