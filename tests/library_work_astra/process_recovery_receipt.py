"""Phase 3 AS-02 process-recovery receipt (Fable-only launcher, not collected by pytest).

A real parent process takes the persisted execution claim for a start, spawns a real
child and records it under DATA_ROOT/source_children, then is killed while the child
survives. A fresh process (the restarted helper) evaluates the production
_ServerCaptureBackend.probe compiled from this checkout's server.py: it must report the
start as still running while the recorded child lives, and stopped only once the child
is gone and the executing incarnation is verifiably dead. Disposable data root; no
helper, no port 5179, no live index, no model, no network.

    python -B tests/library_work_astra/process_recovery_receipt.py --execute
"""
import ast
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PARENT_CODE = r'''
import json, os, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
root = sys.argv[2]
import source_subscriptions as ss
start = {"start_id": "st_procrec", "owner_token": "o" * 43, "capture_key": "procrec", "source_id": "src_procrec", "item_id": "si_procrec"}
inc = ss.process_incarnation(root)
claim = ss.claim_execution_record(root, start, inc)
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
instance = (claim.get("claim") or {}).get("instance")
ss.record_child_start(root, start["start_id"], child.pid, instance)
print(json.dumps({"parent_pid": os.getpid(), "child_pid": child.pid, "claim": claim.get("outcome"),
                  "instance": instance, "claim_record": claim.get("claim")}), flush=True)
time.sleep(600)
'''


def backend_probe_namespace(root):
    """Compile the production backend from this checkout's server.py with explicit
    globals (the same technique as Astra's test_phase3_integration.server_parts)."""
    import source_subscriptions as ss
    names = {'_ServerCaptureBackend', '_find_job_for_start', '_source_instance_id'}
    path = ROOT / 'server.py'
    parsed = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    nodes = [n for n in parsed.body if getattr(n, 'name', None) in names]
    assert {n.name for n in nodes} == names
    ns = dict(source_subscriptions=ss, json=json, log=logging.getLogger('procrec'),
              threading=threading, socket=SimpleNamespace(gethostname=lambda: 'fixture-host'),
              DATA_ROOT=Path(root), _source_capture_threads={}, _source_capture_threads_lock=threading.RLock(),
              _jobs={}, _jobs_lock=threading.RLock(), _JOB_TERMINAL_STATES={'completed', 'failed', 'cancelled'},
              _extract_lock=threading.Lock(), _source_service=lambda: None, _get_index=lambda: None,
              maybe_toast=lambda *a, **k: None, os=os, time=time, subprocess=subprocess, sys=sys, Path=Path)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return ns


def run():
    import source_subscriptions as ss
    scratch = ROOT / '_scratch'
    scratch.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='procrec-', dir=scratch)).resolve()
    receipt = {'procedure': 'AS-02 process recovery', 'root': str(root), 'steps': []}
    env = {k: v for k, v in os.environ.items() if k.upper() != 'ANTHROPIC_API_KEY'}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    parent = subprocess.Popen([sys.executable, '-B', '-c', PARENT_CODE, str(ROOT), str(root)],
                              stdout=subprocess.PIPE, text=True, env=env)
    info = json.loads(parent.stdout.readline())
    receipt['parent'] = info
    start = {"start_id": "st_procrec", "owner_token": "o" * 43, "capture_key": "procrec",
             "source_id": "src_procrec", "item_id": "si_procrec", "owner_instance": info['instance']}
    ns = backend_probe_namespace(root)
    backend = ns['_ServerCaptureBackend']()

    def observe(label):
        obs = {'label': label,
               'claim': ss.read_execution_claim(root, 'st_procrec'),
               'children': ss.child_ownership_liveness(root, 'st_procrec'),
               'instance_liveness': ss.instance_liveness((ss.read_execution_claim(root, 'st_procrec') or {}).get('instance'), root),
               'probe': backend.probe(dict(start))}
        receipt['steps'].append(obs)
        print(label, {k: obs[k] for k in ('children', 'instance_liveness', 'probe')}, flush=True)
        return obs

    a = observe('1 parent alive, child alive')
    parent.kill()
    parent.wait(timeout=10)
    time.sleep(1.0)
    b = observe('2 parent killed, child surviving')
    # The child must still be alive at the OS level.
    child_alive = ss._process_alive(info['child_pid'], None) if hasattr(ss, '_process_alive') else 'unknown'
    receipt['child_alive_after_parent_kill'] = child_alive
    subprocess.run(['taskkill', '/PID', str(info['child_pid']), '/F'], capture_output=True)
    time.sleep(1.0)
    c = observe('3 parent killed, child killed')
    ok = (a['probe'] == 'running' and b['probe'] == 'running' and b['children'] == 'alive'
          and b['instance_liveness'] == 'dead' and c['probe'] == 'stopped')
    receipt['result'] = 'PASS' if ok else 'FAIL'
    receipt['assertions'] = {
        'parent alive -> probe running': a['probe'] == 'running',
        'parent dead + child alive -> children alive': b['children'] == 'alive',
        'parent dead + child alive -> instance dead': b['instance_liveness'] == 'dead',
        'parent dead + child alive -> probe running (not stopped)': b['probe'] == 'running',
        'parent dead + child dead -> probe stopped': c['probe'] == 'stopped',
    }
    (root / 'receipt.json').write_text(json.dumps(receipt, indent=1, default=str), encoding='utf-8')
    print('receipt:', root / 'receipt.json', receipt['result'])
    return 0 if ok else 1


if __name__ == '__main__':
    if '--execute' not in sys.argv:
        print(__doc__)
        sys.exit(2)
    sys.exit(run())
