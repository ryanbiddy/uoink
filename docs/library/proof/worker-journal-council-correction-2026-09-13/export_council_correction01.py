"""Read one completed Control Room run and fixed text inputs; execute no payload."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORKER = Path('C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/371ebc24-906/gemini')
OUT = ROOT / '_scratch/council-correction-observation01'
RUN = '371ebc24-906b-4335-b799-de9ebc38a7e8'
BASE = 'e3ff5b0255fba661ed2de465878a29b7b7c76875'
BRIEF = 'docs/library/proof/worker-journal-council-correction-brief-2026-09-13/'
REPORT = 'docs/library/GEMINI-WORKER-JOURNAL-ADAPTER-CORRECTION-2026-09-13.md'
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd)
def read(root, relative):
    p = root / relative
    assert p.resolve().is_relative_to(root.resolve())
    for part in (p, *p.parents):
        assert not part.is_symlink() and not part.is_junction(), str(part)
        if part == root:
            break
    return p.read_bytes()
def write(name, value):
    p = OUT / name
    assert not p.exists(), name
    p.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

assert git('rev-parse', 'HEAD', cwd=WORKER).decode().strip() == BASE
status = git('status', '--porcelain', cwd=WORKER).decode()
assert status == '?? ' + REPORT + '\n', status
mapping = json.loads(read(ROOT, BRIEF+'CORRECTION-INPUTS.json'))
rows = []
for row in mapping['inputs']:
    rel = row['path']
    assert rel.startswith('docs/library/proof/') and '..' not in Path(rel).parts
    raw = read(ROOT, rel)
    worker_raw = read(WORKER, rel)
    assert raw == worker_raw == git('show', BASE+':'+rel)
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256'], row['id']
    rows.append({'id': row['id'], 'path': rel, 'bytes': len(raw), 'sha256': sha(raw), 'raw_matches_git_and_both_roots': True})
assert len(rows) == 33
controls = []
for name in ('BRIEF.md', 'ROOT-REVIEW.md', 'DISCREPANCIES.md', 'CORRECTION-INPUTS.json'):
    rel = BRIEF+name
    raw = read(ROOT, rel)
    assert raw == read(WORKER, rel) == git('show', BASE+':'+rel)
    controls.append({'path': rel, 'bytes': len(raw), 'sha256': sha(raw)})
original = 'docs/library/proof/worker-journal-council-failed-2026-09-13/ORIGINAL-GEMINI-REPORT.md'
raw = read(ROOT, original)
assert raw == read(WORKER, original) == git('show', BASE+':'+original)
assert sha(raw) == '50a65888706d2a329318c73702b6f468c713d07f7e2bd4c48e423228f6fdda58'
report = read(WORKER, REPORT)
conn = sqlite3.connect('file:C:/Users/hello/AppData/Local/AgentControlRoom/control-room.sqlite?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
run = dict(conn.execute('select * from runs where id=?', (RUN,)).fetchone())
agents = [dict(r) for r in conn.execute('select * from agent_runs where run_id=?', (RUN,))]
events = [dict(r) for r in conn.execute('select * from events where run_id=? and type<>? order by id', (RUN, 'message'))]
conn.close()
assert run['status'] == 'completed' and len(agents) == 1 and agents[0]['status'] == 'completed'
views = []
tools = []
for event in events:
    if event['type'] == 'tool':
        payload = json.loads(event['payload_json']) if event['payload_json'] else None
        tools.append({'id': event['id'], 'message': event['message'], 'payload': payload})
        if event['message'] == 'view_file':
            views.append(tools[-1])
write('run.json', run)
write('agent.json', agents[0])
write('events.json', events)
write('view-metadata.json', views)
write('tool-metadata.json', tools)
check = {'status': 'FIXED_INPUTS_MATCH', 'frozen_base': BASE, 'worker_status': status,
         'source_count': len(rows), 'source_bytes': sum(row['bytes'] for row in rows),
         'source_rows': rows, 'controls': controls, 'original_unchanged': True,
         'report': {'path': REPORT, 'bytes': len(report), 'sha256': sha(report), 'lines': len(report.decode('utf-8-sig').splitlines())},
         'displayed_coverage': 'Worker assertion; tool metadata alone does not establish rendered line coverage.',
         'retained_nonmessage_events': len(events), 'view_events': len(views)}
write('ROOT-INPUT-CHECK.json', check)
out_report = OUT / 'WORKER-REPORT.md'
assert not out_report.exists()
out_report.write_bytes(report)
print(json.dumps({key: check[key] for key in ('status','source_count','source_bytes','original_unchanged','report','retained_nonmessage_events','view_events')}))
