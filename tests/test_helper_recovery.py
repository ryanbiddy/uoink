"""Disposable processes only. No installed helper, tasks, registry or launchd."""
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

import uoink_supervisor as recovery

ROOT = Path(__file__).resolve().parents[1]
FAKE = r'''
import json, os, socket, sys, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
mode, root = sys.argv[1], Path(sys.argv[2])
with (root / 'starts').open('a') as f: f.write('start\n')
if mode == 'exit0': sys.exit(0)
if mode == 'exit1': sys.exit(1)
if mode == 'crash': os._exit(7)
if mode == 'already_running':
    print('Uoink server already running on http://127.0.0.1:1 -- exiting', flush=True)
    sys.exit(0)
if mode == 'quit':
    (root / 'helper-stop.json').write_text('{"reason": "quit"}')
    sys.exit(1)
if mode == 'bind':
    try: socket.create_server(('127.0.0.1', int(sys.argv[3])))
    except OSError:
        print('Failed to bind local port', flush=True)
        sys.exit(1)
    sys.exit(9)
if mode == 'hang': time.sleep(30)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({'ok': True, 'pid': os.getpid(),
                          'supervisor_run_id': os.environ['UOINK_SUPERVISOR_RUN_ID']}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
http = HTTPServer(('127.0.0.1', 0), Handler)
assert http.server_port != 5179
(root / 'port').write_text(str(http.server_port))
threading.Thread(target=http.serve_forever, daemon=True).start()
time.sleep(6)  # Job lasts longer than startup deadline once ready.
(root / 'slow-job-finished').touch()
http.shutdown()
'''


def supervisor(tmp_path, mode, **kw):
    script = tmp_path / 'fake.py'
    script.write_text(FAKE)
    command = [sys.executable, str(script), mode, str(tmp_path)]
    def probe(_url, run_id, pid):
        try:
            port = int((tmp_path / 'port').read_text())
        except (OSError, ValueError):
            return False
        assert port != 5179
        return recovery.ready(f'http://127.0.0.1:{port}/health', run_id, pid)
    options = dict(session='test-login', backoff=(0.01, 0.02, 0.03), poll=0.01,
                   readiness_timeout=5, probe=probe, notify=lambda state: None)
    options.update(kw)
    return recovery.Supervisor(tmp_path, command, 'http://127.0.0.1:1/health', **options)


@pytest.mark.parametrize('mode,code', [('exit0', 0), ('exit1', 1), ('crash', 7), ('hang', None)])
def test_real_disposable_child_policy(tmp_path, mode, code):
    notifications = []
    runner = supervisor(tmp_path, mode, notify=lambda state: notifications.append(dict(state)))
    assert runner.run() == 0
    state = recovery.read_json(tmp_path / recovery.STATE_FILE)
    starts = (tmp_path / 'starts').read_text().splitlines()
    assert len(starts) == (1 if mode == 'exit0' else 4)
    assert state['restart_count'] == (0 if mode == 'exit0' else 3)
    assert state['status'] == ('stopped' if mode == 'exit0' else 'crash_loop')
    assert state['last_start_at'] and state['last_stop_at']
    assert state['schema_version'] == 1 and state['ready_at'] is None
    if code is not None:
        assert state['last_exit_code'] == code
    if mode == 'hang':
        assert 'startup deadline' in state['reason']
    assert len(notifications) == (0 if mode == 'exit0' else 1)
    if notifications:
        assert 'uoink doctor' in state['action']


def test_bind_failure_is_disclosed(tmp_path):
    notifications = []
    with socket.socket() as held:
        held.bind(('127.0.0.1', 0))
        held.listen()
        assert held.getsockname()[1] != 5179
        runner = supervisor(tmp_path, 'bind', notify=notifications.append)
        runner.command.append(str(held.getsockname()[1]))
        assert runner.run() == 0
    assert 'could not bind' in recovery.status(tmp_path)['reason']
    assert recovery.status(tmp_path)['last_exit_code'] == 1
    assert (tmp_path / 'starts').read_text().splitlines() == ['start']
    assert recovery.status(tmp_path)['restart_count'] == 0
    assert recovery.status(tmp_path)['status'] == 'stopped'
    assert runner.state['restart_times'] == []
    assert notifications == []


def test_healthy_other_helper_is_disclosed_without_retry(tmp_path):
    notifications = []
    runner = supervisor(tmp_path, 'already_running', notify=notifications.append)
    assert runner.run() == 0
    state = recovery.status(tmp_path)
    assert state['status'] == 'stopped' and state['last_exit_code'] == 0
    assert 'already running' in state['reason'] and state['action']
    assert (tmp_path / 'starts').read_text().splitlines() == ['start']
    assert state['restart_count'] == 0 and runner.state['restart_times'] == []
    assert notifications == []


def test_stop_intent_wins_over_nonzero_exit(tmp_path):
    supervisor(tmp_path, 'quit').run()
    assert recovery.status(tmp_path)['status'] == 'stopped'
    assert recovery.status(tmp_path)['last_exit_code'] == 1
    assert recovery.status(tmp_path)['restart_count'] == 0
    supervisor(tmp_path, 'exit1', startup=True).run()
    assert len((tmp_path / 'starts').read_text().splitlines()) == 1


def test_manual_start_recovers_corrupt_state(tmp_path):
    (tmp_path / recovery.STATE_FILE).write_text('invalid')
    supervisor(tmp_path, 'exit0').run()
    assert recovery.status(tmp_path)['status'] == 'stopped'


def test_ready_slow_job_is_not_restarted(tmp_path):
    runner = supervisor(tmp_path, 'slow')
    assert runner.run() == 0
    state = recovery.status(tmp_path)
    assert state['ready_at'] and state['restart_count'] == 0
    assert (tmp_path / 'slow-job-finished').exists()


def test_stop_intent_during_backoff_and_same_login(tmp_path):
    runner = supervisor(tmp_path, 'exit1')
    def stop(delay):
        recovery.request_stop(tmp_path)
        return False
    runner.wait = stop
    runner.run()
    assert recovery.status(tmp_path)['status'] == 'stopped'
    assert recovery.status(tmp_path)['last_exit_code'] == 1
    assert supervisor(tmp_path, 'exit1', startup=True).run() == 0
    assert len((tmp_path / 'starts').read_text().splitlines()) == 1
    # A manual start clears the marker and gets a fresh budget.
    supervisor(tmp_path, 'exit0').run()
    assert len((tmp_path / 'starts').read_text().splitlines()) == 2
    recovery.request_stop(tmp_path)
    supervisor(tmp_path, 'exit0', startup=True, session='next-login').run()
    assert len((tmp_path / 'starts').read_text().splitlines()) == 3


def test_crash_loop_survives_supervisor_reentry(tmp_path):
    supervisor(tmp_path, 'exit1').run()
    supervisor(tmp_path, 'exit1', startup=True).run()
    assert len((tmp_path / 'starts').read_text().splitlines()) == 4


def test_exact_default_backoff_and_sliding_window(tmp_path, monkeypatch):
    now = [1000.0]
    sleeps = []
    child = SimpleNamespace(pid=123, stdout=io.BytesIO(), poll=lambda: 1, wait=lambda **k: 1)
    monkeypatch.setattr(recovery.subprocess, 'Popen', lambda *a, **kw: child)
    monkeypatch.setattr(recovery, 'capture_output', lambda *a: None)
    runner = supervisor(tmp_path, 'exit1', backoff=recovery.BACKOFF, clock=lambda: now[0])
    def wait(delay):
        sleeps.append(delay)
        now[0] += delay
        return True
    runner.wait = wait
    runner.run()
    assert sleeps == [5, 15, 45]
    assert runner.state['restart_times'] == [1005, 1020, 1065]
    # An old retry expires, even when the helper is still in the same login.
    runner.state.update(status='running', restart_times=[now[0] - 601, now[0] - 10])
    recovery.write_json(tmp_path / recovery.STATE_FILE, runner.state)
    sleeps.clear()
    runner.startup = True
    runner.run()
    assert sleeps == [15, 45]


def test_admission_prevents_second_helper(tmp_path):
    with recovery.admission(tmp_path) as first:
        assert first
        assert supervisor(tmp_path, 'exit1').run() == 0
        assert not (tmp_path / 'starts').exists()


def test_two_launch_processes_start_one_helper(tmp_path):
    (tmp_path / 'fake.py').write_text(FAKE)
    entry = tmp_path / 'launch.py'
    entry.write_text("import sys\nfrom pathlib import Path\nimport uoink_supervisor as r\n"
                     "root = Path(sys.argv[1])\n"
                     "raise SystemExit(r.Supervisor(root, [sys.executable, str(root / 'fake.py'), 'slow', str(root)], "
                     "'http://127.0.0.1:1/health', session='fixture', probe=lambda *a: True, "
                     "poll=0.01, notify=lambda *a: None).run())\n")
    first = subprocess.Popen([sys.executable, str(entry), str(tmp_path)])
    try:
        deadline = time.monotonic() + 15
        while not (tmp_path / 'starts').exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (tmp_path / 'starts').exists()
        second = subprocess.run([sys.executable, str(entry), str(tmp_path)], timeout=15)
        assert second.returncode == 0
        assert first.wait(timeout=15) == 0
        assert (tmp_path / 'starts').read_text().splitlines() == ['start']
    finally:
        if first.poll() is None:
            recovery.request_stop(tmp_path)
            try:
                first.wait(timeout=20)
            except subprocess.TimeoutExpired:
                first.kill()
                first.wait(timeout=5)


def test_profile_and_public_projection(tmp_path, monkeypatch):
    monkeypatch.setenv('UOINK_ISOLATED_PROFILE', str(tmp_path))
    recovery.request_stop()
    assert (tmp_path / recovery.STOP_FILE).exists()
    recovery.write_json(tmp_path / recovery.STATE_FILE, {'status': 'crash_loop', 'session': 'private',
                                                       'supervisor_pid': 98, 'command': 'private',
                                                       'data_root': str(tmp_path),
                                                       'token': 'secret-test-token',
                                                       'exception': 'private raw exception'})
    result = recovery.status()
    assert result['status'] == 'crash_loop'
    assert set(result) == {'available', 'schema_version', 'status', 'last_exit_code',
                          'restart_count', 'last_start_at', 'last_stop_at', 'ready_at',
                          'reason', 'action'}
    serialized = json.dumps(result)
    assert all(value not in serialized for value in
               ('private', 'secret-test-token', str(tmp_path), json.dumps(str(tmp_path))[1:-1]))
    (tmp_path / recovery.STATE_FILE).write_text('broken')
    assert recovery.status()['status'] == 'unreadable'


def test_output_is_size_capped_and_rotated(tmp_path):
    recovery.capture_output(io.BytesIO(b'x' * (5 * 1024 * 1024)), tmp_path, [b''])
    files = list(tmp_path.glob('helper-output.log*'))
    assert len(files) == 4
    assert all(path.stat().st_size <= 1024 * 1024 for path in files)


def test_readiness_rejects_foreign_or_unstable_health(tmp_path):
    runner = supervisor(tmp_path, 'slow')
    calls = []
    def unstable(*args):
        calls.append(True)
        return len(calls) % 2 == 0
    runner.probe = unstable
    runner.run()
    assert recovery.status(tmp_path)['ready_at'] is None
    assert recovery.status(tmp_path)['status'] == 'crash_loop'


@pytest.mark.parametrize('payload,expected', [
    ({'ok': True, 'pid': 123, 'supervisor_run_id': 'current'}, True),
    ({'ok': True, 'pid': 456, 'supervisor_run_id': 'current'}, False),
    ({'ok': True, 'pid': 123, 'supervisor_run_id': 'old'}, False),
    ({'ok': False, 'pid': 123, 'supervisor_run_id': 'current'}, False),
    ({'ok': True}, False),
])
def test_readiness_requires_this_child_and_launch(monkeypatch, payload, expected):
    from contextlib import nullcontext
    reply = SimpleNamespace(status=200, read=lambda limit: json.dumps(payload).encode())
    opener = SimpleNamespace(open=lambda *a, **kw: nullcontext(reply))
    monkeypatch.setattr(recovery.urllib.request, 'build_opener', lambda *a: opener)
    assert recovery.ready('http://127.0.0.1:1/health', 'current', 123) is expected


def test_quit_writes_intent_before_response_and_shutdown(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(server, 'DATA_ROOT', tmp_path)
    events = []
    handler = server.Handler.__new__(server.Handler)
    handler._require_token = lambda: True
    def send(*args):
        assert (tmp_path / recovery.STOP_FILE).exists()
        events.append('reply')
    handler._send_json = send
    handler.server = SimpleNamespace(shutdown=lambda: events.append('shutdown'))
    handler._handle_helper_quit()
    deadline = time.time() + 2
    while len(events) < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert events == ['reply', 'shutdown']


def test_mcp_status_and_native_dashboard_can_read_offline(tmp_path, monkeypatch):
    import uoink_dashboard
    import uoink_mcp_tools
    monkeypatch.setenv('UOINK_ISOLATED_PROFILE', str(tmp_path))
    recovery.write_json(tmp_path / recovery.STATE_FILE, {'status': 'crash_loop', 'last_exit_code': 7})
    monkeypatch.setattr(uoink_mcp_tools, '_b', lambda: SimpleNamespace(_is_valid_job_id=lambda _: False))
    assert uoink_mcp_tools.get_job_status({'job_id': 'bad'})['helper_recovery']['last_exit_code'] == 7
    assert uoink_dashboard.JsApi().helper_recovery()['status'] == 'crash_loop'


def test_legacy_installed_launch_enters_same_supervisor(monkeypatch):
    import server
    monkeypatch.delenv('UOINK_SUPERVISOR_RUN_ID', raising=False)
    monkeypatch.setattr(server._install_isolation, 'current_binding', lambda: None)
    monkeypatch.setattr(server, '_is_installed_layout', lambda: True)
    called = []
    monkeypatch.setattr(server.os, 'execv', lambda executable, argv: called.append((executable, argv)))
    assert server.run_cli(['--show-dashboard']) == 0
    assert called == [(sys.executable, [sys.executable, '-B', '-s', str(ROOT / 'uoink_supervisor.py'), '--show-dashboard'])]


def test_macos_login_session_arguments(monkeypatch):
    monkeypatch.setattr(recovery, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(recovery.os, 'getuid', lambda: 501, raising=False)
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(stdout='\tasid = 100123\n' if argv[0] == '/bin/launchctl' else '{ sec = 123 }')
    monkeypatch.setattr(recovery.subprocess, 'run', run)
    assert recovery.login_session() == 'macos:100123:{ sec = 123 }'
    assert calls == [
        (['/bin/launchctl', 'print', 'gui/501'], dict(capture_output=True, text=True, check=True, timeout=5)),
        (['/usr/sbin/sysctl', '-n', 'kern.boottime'], dict(capture_output=True, text=True, check=True, timeout=5))]
