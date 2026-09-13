"""Collect one completed text council. Never import or execute reviewed inputs."""
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
WORKER = Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\98b5e1a3-c10\gemini')
PREP = ROOT / '_scratch/owned-runtime-council-collector-proposal01'
OUT = ROOT / '_scratch/gemini-owned-runtime-components-council-receipts01'
BASE = '59f3aeb84fdf2c545fcd90ffbc569f784a9818db'
RUN = '98b5e1a3-c100-4cf6-b147-1b73555538ce'
REPORT = 'docs/library/GEMINI-OWNED-RUNTIME-COMPONENTS-COUNCIL-REVIEW-2026-09-13.md'
BRIEF = 'docs/library/GEMINI-OWNED-RUNTIME-COMPONENTS-COUNCIL-BRIEF-2026-09-13.md'
PROOF = 'docs/library/proof/'
FACTORY = PROOF + 'vad-owned-factory-port-2026-09-13/'
WXS = PROOF + 'whisperx-owned-contracts-2026-09-13/derivative/after/whisperx/'
SOURCES = [
    ('code', PROOF+'vad-owned-cpu-tensor-port-2026-09-13/objects/ac9eb28194723ffaf2d98bb2cd691a7b27b0a1638694fdfd8cb198c3084e8964.txt', 'ac9eb28194723ffaf2d98bb2cd691a7b27b0a1638694fdfd8cb198c3084e8964'),
    ('code', FACTORY+'objects/2569853c7634b795e3d2cf717129ec3dbc4e11d96ddb347098dcc4fbc532f0d4.txt', '2569853c7634b795e3d2cf717129ec3dbc4e11d96ddb347098dcc4fbc532f0d4'),
    ('code', FACTORY+'objects/48567add0f0ac2ac9140e9aa86b06f077454c98e2f0773100da5ba070f7b3deb.txt', '48567add0f0ac2ac9140e9aa86b06f077454c98e2f0773100da5ba070f7b3deb'),
    ('code', PROOF+'asr-lifecycle-contracts-2026-09-13/author02/snapshot_lifecycle.py', 'a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd'),
    ('code', WXS+'_uoink_owned.py', '7672f614d81cf0be5e7bd408f8f856af328fe34e6ca7ee707c9d0db838e56d1f'),
    ('code', WXS+'asr.py', '723bfba5775cb4a610368e1ad706fc55131bc9a2e8ea2f1e1a2b55cd6e8b5d42'),
    ('code', WXS+'vads/pyannote.py', 'aeec3ec09d1ed7e11f827353c4f9087de665b1cd3dabf3ff47bb5917c679c6f2'),
    ('code', WXS+'audio.py', 'c7b696df836e415e7c732c03edae496c4317cb741eaac7357e8c9c7bdcf38152'),
    ('contract', FACTORY+'objects/4b0e29011821dd610a653d6c3692768c6451e61ca986f28b8d8e9bd54d974932.txt', '4b0e29011821dd610a653d6c3692768c6451e61ca986f28b8d8e9bd54d974932'),
    ('contract', FACTORY+'objects/50783d05baf8027334fc28b1972fc4d35ec205941c115b79bdf4f8edb8b4babb.txt', '50783d05baf8027334fc28b1972fc4d35ec205941c115b79bdf4f8edb8b4babb'),
    ('source_tree', FACTORY+'SOURCE-TREE.json', None),
    *[('verdict', 'docs/library/'+name, None) for name in (
        'ASTRA-VAD-CPU-PORT-VERDICT-2026-09-13.md',
        'ASTRA-VAD-FACTORY-PORT-VERDICT-2026-09-13.md',
        'ASTRA-ASR-LIFECYCLE-CONTRACT-VERDICT-2026-09-13.md',
        'ASTRA-OWNED-WHISPERX-CONTRACT-VERDICT-2026-09-13.md',
        'ASTRA-OWNED-WHISPERX-BUILD-VERDICT-2026-09-13.md')],
    ('brief', BRIEF, None),
]
ACTUALS = [
    ('OWNED-RUNTIME-COUNCIL-DISPATCH01-ACTUAL.json', '0295d209d438db264bdaf360c3d11c75cb40d3703e7fbae652cbf0fcebe18a91'),
    ('OWNED-RUNTIME-COUNCIL-FINAL01-ACTUAL.json', '1db8ae2936dfc2206aaad153e3aa8b06f757759731b084a98c64888e11526ae2'),
]

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def read(path, cap=4_000_000):
    with path.open('rb') as stream:
        raw = stream.read(cap+1)
    if len(raw) > cap:
        raise ValueError('Bounded text read exceeded: '+str(path))
    return raw

def save(name, raw):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)

def data(name, value):
    raw = (json.dumps(value, indent=2, ensure_ascii=True)+'\n').encode('ascii')
    if len(raw) > 32_000_000:
        raise ValueError('Documentary JSON bound exceeded')
    save(name, raw)

def obj(raw):
    name = 'objects/'+sha(raw)+'.txt'
    path = OUT/name
    if path.exists():
        assert read(path) == raw
    else:
        save(name, raw)
    return name

COMMANDS = []

def git(args, check=True):
    command = ['git', '-c', 'core.quotePath=false', *args]
    started = utc()
    result = subprocess.run(command, cwd=WORKER, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60, check=False)
    ended = utc()
    if len(result.stdout)+len(result.stderr) > 4_000_000:
        raise ValueError('Git documentary output bound exceeded')
    row = {'argv':command, 'cwd':str(WORKER), 'started_utc':started,
           'finished_utc':ended, 'actual_exit':result.returncode,
           'stdout':obj(result.stdout), 'stderr':obj(result.stderr)}
    COMMANDS.append(row)
    data('git/command-%02d.json'%len(COMMANDS), row)
    if check and result.returncode != 0:
        raise RuntimeError('Git failed; raw command receipt retained')
    return result

def main():
    assert sys.argv[1:] == ['--collect']
    assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
    assert Path(__file__).absolute() == PREP/'collect.py'
    assert len(SOURCES) == 17 and len({p for _,p,_ in SOURCES}) == 17
    assert not OUT.exists()
    OUT.mkdir()
    save('.gitattributes', b'* -text\n')
    started = utc()
    for name in ('collect.py', 'before-collector.py', 'BRIEF.md', 'run_collect01.ps1',
                 'PINS.json', 'PREEXECUTION-REPAIR02.md', 'PREEXECUTION-REPAIR02.diff.txt', 'before-review02/collect.py',
                 'before-review02/run_collect01.ps1', 'before-review02/PINS.json'):
        save('preparation/'+name, read(PREP/name))
    for name, expected in ACTUALS:
        raw = read(ROOT/'_scratch'/name)
        assert sha(raw) == expected
        save('actual/'+name, raw)
    final = json.loads(read(ROOT/'_scratch'/ACTUALS[1][0]))
    assert final['chunk_id'] == 'fa4418' and final['exit_code'] == 0
    assert final['original_token_count'] == 5689
    assert 'Warning: truncated output' not in final['output']

    assert git(['rev-parse', '--verify', 'HEAD^{commit}']).stdout.strip().decode('ascii') == BASE
    initial = git(['status', '--porcelain=v1', '-z', '--untracked-files=all']).stdout
    assert initial == ('?? '+REPORT+'\0').encode('utf-8'), 'Worker contains changes beyond the new report'
    assert git(['diff', '--cached', '--name-only', '-z']).stdout == b''
    assert git(['ls-tree', '--name-only', BASE, '--', REPORT]).stdout == b''
    raw_report = read(WORKER/REPORT)
    assert raw_report and len(raw_report) < 1_000_000
    save('worker-report.md', raw_report)

    with sqlite3.connect('file:C:/Users/hello/AppData/Local/AgentControlRoom/control-room.sqlite?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        row = connection.execute('SELECT * FROM runs WHERE id=?', (RUN,)).fetchone()
        assert row is not None
        run = dict(row)
        agents = [dict(r) for r in connection.execute('SELECT * FROM agent_runs WHERE run_id=? ORDER BY rowid LIMIT 3', (RUN,))]
        events = [dict(r) for r in connection.execute('SELECT * FROM events WHERE run_id=? ORDER BY rowid LIMIT 5001', (RUN,))]
    data('run.json', run)
    data('agent-runs.json', agents)
    data('events.json', events)
    assert run['status'] == 'completed' and run['mode'] == 'work'
    assert run['strategy'] == 'parallel' and run['lead_agent'] == 'gemini'
    assert json.loads(run['agents_json']) == ['gemini']
    assert len(agents) == 1 and agents[0]['status'] == 'completed'
    assert agents[0]['agent'] == 'gemini' and agents[0]['model'] == 'gemini-3.8-flash-high'
    assert Path(agents[0]['worktree_path']) == WORKER
    assert 0 < len(events) < 5001
    preflight = [e for e in events if e['type']=='preflight' and e['message']==f'frozen-base={BASE} · verified-inputs=12']
    assert len(preflight) == 1 and preflight[0]['payload_json'] is None
    memberships = [e['id'] for e in events if 'reviewedInputFiles' in json.dumps(e)]
    assert not memberships, 'New membership evidence requires documentary review'
    data('preflight-record-scope.json', {
        'recorded_verified_inputs_counter':12, 'recorded_frozen_base':BASE,
        'preflight_event_id':preflight[0]['id'], 'membership_payload':None,
        'reviewedInputFiles_event_ids':memberships,
        'separate_current_binding_count':17,
        'current_bindings_are_original_preflight_manifest':False,
        'limitation':'The retained event reports a reference counter, without original membership. Current bindings below are separately verified.'})

    bindings, seals = [], {}
    for kind, path, expected in SOURCES:
        worker_raw, root_raw = read(WORKER/path), read(ROOT/path)
        base_raw = git(['show', BASE+':'+path]).stdout
        normalize = kind in ('verdict', 'brief')
        comparable = lambda raw: raw.replace(b'\r\n', b'\n') if normalize else raw
        assert comparable(worker_raw) == comparable(root_raw) == comparable(base_raw)
        if expected is not None:
            assert sha(worker_raw) == expected
        seal_info = None
        if path.startswith(PROOF):
            folder, member = path[len(PROOF):].split('/', 1)
            manifest_name = 'SHA256-MANIFEST.json' if folder == 'asr-lifecycle-contracts-2026-09-13' else 'SHA256.json'
            sealpath = PROOF+folder+'/'+manifest_name
            if sealpath not in seals:
                sr, sw = read(ROOT/sealpath), read(WORKER/sealpath)
                sb = git(['show', BASE+':'+sealpath]).stdout
                assert sr == sw == sb
                seal = json.loads(sr)
                if folder == 'whisperx-owned-contracts-2026-09-13':
                    assert type(seal) is list
                    seal_rows = seal
                elif folder == 'asr-lifecycle-contracts-2026-09-13':
                    seal_rows = seal['files']
                    assert len(seal_rows) == seal['count']
                    assert sum(r['bytes'] for r in seal_rows) == seal['bytes']
                else:
                    assert folder in ('vad-owned-cpu-tensor-port-2026-09-13', 'vad-owned-factory-port-2026-09-13')
                    seal_rows = seal['files']
                    assert len(seal_rows) == seal['payload_count']
                assert len({r['path'] for r in seal_rows}) == len(seal_rows)
                seals[sealpath] = {'raw':sr, 'rows':seal_rows, 'object':obj(sr)}
            seal = seals[sealpath]
            matches = [r for r in seal['rows'] if r['path']==member]
            assert len(matches) == 1
            assert matches[0]['sha256'] == sha(worker_raw) and matches[0]['bytes'] == len(worker_raw)
            seal_info = {'seal_path':sealpath, 'seal_object':seal['object'], 'row':matches[0]}
        bindings.append({'path':path, 'kind':kind,
            'comparison':'CRLF-to-LF only' if normalize else 'exact raw bytes',
            'worker':{'sha256':sha(worker_raw), 'bytes':len(worker_raw), 'object':obj(worker_raw)},
            'checkout':{'sha256':sha(root_raw), 'bytes':len(root_raw), 'object':obj(root_raw)},
            'frozen_git':{'commit':BASE, 'sha256':sha(base_raw), 'bytes':len(base_raw), 'object':obj(base_raw)},
            'proof_row':seal_info})
    tree = json.loads(read(WORKER/(FACTORY+'SOURCE-TREE.json')))
    for logical, digest in (
        ('author/INTEGRATION-AND-LIMITS.md', SOURCES[8][2]),
        ('author/WORKER-CAPABILITY-CONTRACT.md', SOURCES[9][2])):
        rows = [r for r in tree['sources'] if r['logical_path'] == logical]
        assert len(rows) == 1 and rows[0]['sha256'] == digest
        assert rows[0]['object'] == 'objects/'+digest+'.txt'
    data('current-review-bindings.json', {'original_preflight_membership':False,
        'count':len(bindings), 'kinds':dict(collections.Counter(b['kind'] for b in bindings)),
        'bindings':bindings})

    git(['add', '-N', '--', REPORT])
    assert git(['diff', '--name-only', '-z', '--no-ext-diff']).stdout == (REPORT+'\0').encode('utf-8')
    assert git(['diff', '--cached', '--name-only', '-z']).stdout == b''
    patch = git(['diff', '--binary', '--no-ext-diff', '--no-textconv', '--no-color', '--', REPORT]).stdout
    assert patch.startswith(('diff --git a/'+REPORT+' b/'+REPORT+'\n').encode('utf-8'))
    assert b'new file mode 100644\n' in patch
    save('worker.patch', patch)
    assert read(WORKER/REPORT) == raw_report
    assert git(['rev-parse', '--verify', 'HEAD^{commit}']).stdout.strip().decode('ascii') == BASE
    assert git(['status', '--porcelain=v1', '-z', '--untracked-files=all']).stdout == (' A '+REPORT+'\0').encode('utf-8')
    data('COLLECTION.json', {'run_id':RUN, 'frozen_worker_base':BASE,
        'report_production_baseline_label':'e8d058f (unchanged report; distinct from worker base)',
        'current_review_bindings':17, 'original_preflight_counter':12,
        'original_preflight_membership_retained':False,
        'events':len(events), 'tool_messages':dict(collections.Counter(e['message'] for e in events if e['type']=='tool')),
        'report_sha256':sha(raw_report), 'patch_sha256':sha(patch),
        'actual_controller_completion_exit':final['exit_code'],
        'actual_completion_tool_tokens':final['original_token_count'],
        'completion_tool_internal_truncation':False,
        'git_command_count':len(COMMANDS), 'new_tests_run':False,
        'source_acceptance_groups':3, 'native_acceptance':False,
        'installed_acceptance':False, 'market_approval':False,
        'website_marketing_paused':True, 'started_utc':started, 'finished_utc':utc(),
        'collector_outer_result':'Will be retained separately after this seal; cannot be its own payload.'})
    files = [{'path':p.relative_to(OUT).as_posix(), 'bytes':len(raw), 'sha256':sha(raw)}
             for p in sorted(OUT.rglob('*')) if p.is_file() for raw in [read(p, 32_000_000)]]
    data('SHA256.json', {'schema':1, 'excluded':['SHA256.json'], 'payload_count':len(files), 'files':files})
    seal = json.loads(read(OUT/'SHA256.json'))
    assert {p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()} == {r['path'] for r in seal['files']} | {'SHA256.json'}
    for r in seal['files']:
        raw = read(OUT/r['path'], 32_000_000)
        assert len(raw) == r['bytes'] and sha(raw) == r['sha256']
    print(json.dumps({'status':'collected_and_full_file_set_verified', 'output':str(OUT),
        'payload_count':len(files), 'physical_file_count':len(files)+1,
        'seal_sha256':sha(read(OUT/'SHA256.json')), 'current_review_bindings':17,
        'original_preflight_counter':12, 'events':len(events),
        'report_sha256':sha(raw_report), 'patch_sha256':sha(patch)}))

if __name__ == '__main__':
    main()
