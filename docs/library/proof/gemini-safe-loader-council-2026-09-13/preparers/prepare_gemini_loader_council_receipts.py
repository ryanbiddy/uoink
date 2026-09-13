"""Collect bounded text review receipts; do not execute reviewed sources."""
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

root = Path(__file__).absolute().parents[1]
worker = Path('C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/c5c89d60-00c/gemini')
out = root / '_scratch/gemini-safe-loader-council-c5c89d60'
out.mkdir(exist_ok=False)
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def save(name, raw):
    with (out / name).open('xb') as stream:
        stream.write(raw)
def data(name, value):
    save(name, (json.dumps(value, indent=2, ensure_ascii=True)+'\n').encode('ascii'))

report = 'docs/library/GEMINI-SAFE-LOADER-COUNCIL-REVIEW-2026-09-13.md'
brief = 'docs/library/GEMINI-SAFE-LOADER-COUNCIL-BRIEF-2026-09-13.md'
save('worker-report.md', (worker / report).read_bytes())
assert (worker / brief).read_bytes() == (root / brief).read_bytes()
save('brief.md', (root / brief).read_bytes())
sources = [
 ('asr-trusted-manifest-resolver-2026-09-13','proposal/trusted_asr_resolver.py'),
 ('vad-plain-state-reader-2026-09-13','preparation03/plain_state_reader.py'),
 ('vad-d1-adapter-2026-09-13','proposal/inspect_adapter.py'),
 ('vad-d1-adapter-2026-09-13','proposal/fixed_converter.py'),
 ('vad-d1-adapter-2026-09-13','proposal/zip_bounds.py'),
 ('vad-d1-adapter-2026-09-13','proposal/buffer_basis.py')]
bindings = []
for folder, name in sources:
    base = Path('docs/library/proof') / folder
    seal = json.loads((root / base / 'SHA256.json').read_bytes())
    row = next(x for x in seal['files'] if x['path'] == name)
    raw = (root / base / name).read_bytes()
    assert raw == (worker / base / name).read_bytes()
    assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
    archived = 'source-' + Path(name).name + '.txt'
    save(archived, raw)
    bindings.append({'path':(base/name).as_posix(),'archive':archived,
                     'sha256':sha(raw),'bytes':len(raw),'worker_root_seal_equal':True})
data('source-bindings.json', bindings)

run_id = 'c5c89d60-00cb-4c2a-bb0d-d9ebd5d86f9d'
c = sqlite3.connect('file:C:/Users/hello/AppData/Local/AgentControlRoom/control-room.sqlite?mode=ro',uri=True)
c.row_factory = sqlite3.Row
run = dict(c.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone())
agents = [dict(r) for r in c.execute('SELECT * FROM agent_runs WHERE run_id=?',(run_id,))]
events = [dict(r) for r in c.execute('SELECT * FROM events WHERE run_id=? ORDER BY rowid',(run_id,))]
c.close()
assert run['status'] == 'completed' and len(agents) == 1 and agents[0]['status'] == 'completed'
data('run.json', run)
data('agent-runs.json', agents)
data('events.json', events)
data('controller-result.json', {'actual_controller_exit':0,'session_id':48753,
    'completion_chunk':'17f07a','not_worker_test_or_runtime_acceptance':True})

subprocess.run(['git','add','-N','--',report],cwd=worker,check=True)
with (out/'worker.patch').open('xb') as patch:
    result = subprocess.run(['git','diff','--binary','--no-ext-diff','--no-color','--',report],
                            cwd=worker,stdout=patch,check=True)
data('patch-exit.json', {'actual_git_diff_exit':result.returncode,
    'sha256':sha((out/'worker.patch').read_bytes()),'scope':'one new review document'})
print(json.dumps({'out':str(out),'sources_verified':len(bindings),'events':len(events),
    'event_types':dict(collections.Counter(r['type'] for r in events)),
    'tool_messages':dict(collections.Counter(r['message'] for r in events if r['type']=='tool')),
    'report_sha256':sha((out/'worker-report.md').read_bytes()),
    'patch_sha256':sha((out/'worker.patch').read_bytes())}))
