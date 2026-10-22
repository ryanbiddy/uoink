"""Cross-process privacy regressions. All POSTs are mocks and files are temporary."""
import json
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import pytest

import server
import uoink_mcp_tools as tools
import uoink_usage as usage
from tests.test_usage_sharing import age, enabled, store  # noqa: F401


def settings_handler(store, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_PATH", store / "settings.json")
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: "")
    monkeypatch.setattr(server, "_get_saved_scrapecreators_key", lambda: "")
    monkeypatch.setattr(server, "_load_topics", lambda: {})
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_reliability_model_status", lambda *args: {})
    monkeypatch.setattr(server.whisper_runner, "is_whisperx_available", lambda: False)
    server._write_settings({}, usage_choice=True)
    handler = object.__new__(server.Handler)
    replies = []
    handler._send_json = lambda status, body: replies.append((status, body))
    return handler, replies


def test_reviewer_eight_second_send_keeps_database_available(store, monkeypatch):
    handler, replies = settings_handler(store, monkeypatch)
    enabled()
    usage.count("searches")
    usage._queue.join()
    now = age()
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "https://usage-test.invalid/v1/ping")
    entered, finished = threading.Event(), threading.Event()

    def slow_post(endpoint, payload):
        entered.set()
        time.sleep(8)
        finished.set()
        return 204

    monkeypatch.setattr(usage, "_post", slow_post)
    results = []
    sender = threading.Thread(target=lambda: results.append(usage.send_due(now)))
    started = time.monotonic()
    sender.start()
    try:
        assert entered.wait(2)
        script = (
            "import sys,time; from pathlib import Path; import uoink_usage as u; "
            "u.configure(lambda: Path(sys.argv[1]), '3.10.0'); "
            "t=time.monotonic(); u._record(u._path(),'searches','count','ok',time.time()); "
            "print(time.monotonic()-t)"
        )
        result = subprocess.run([sys.executable, "-c", script, str(store)],
                                capture_output=True, text=True, timeout=3)
        assert result.returncode == 0, result.stderr
        assert float(result.stdout.strip()) < 1
        before = time.monotonic()
        handler._handle_settings_get()
        assert replies[-1][0] == 200 and replies[-1][1]["settings"]["usage_sharing"]
        assert usage.disclosure()["next_payload"]["searches"] == 1  # immutable snapshot
        assert usage._read_state()["counts"]["searches"]["count"] == 2
        assert time.monotonic() - before < 1
        sender.join(5)
        assert not sender.is_alive() and results == [False]
        assert time.monotonic() - started < 6
        assert usage._read_state()["counts"]["searches"]["count"] == 2
    finally:
        assert finished.wait(10)
        sender.join(5)
    # A late successful POST has no authority to clear local counts. The same
    # report must be acknowledged on a later daily attempt.
    assert usage._read_state()["counts"]["searches"]["count"] == 2
    monkeypatch.setattr(usage, "_post", Mock(return_value=204))
    assert usage.send_due(now + usage.DAY)
    assert usage.disclosure()["next_payload"]["searches"] == 1


@pytest.mark.parametrize("turn_off", [False, True])
def test_counts_and_opt_out_do_not_wait_for_post(store, monkeypatch, turn_off):
    handler, replies = settings_handler(store, monkeypatch)
    first_id = enabled()["install_id"]
    with usage._transaction() as state:
        state["counts"] = {"searches": {"count": usage.MAX_COUNT}}
    now = age()
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "https://usage-test.invalid/v1/ping")

    def post(*args):
        entered.set()
        release.wait(5)
        return 204

    monkeypatch.setattr(usage, "_post", post)
    results = []
    sender = threading.Thread(target=lambda: results.append(usage.send_due(now)))
    sender.start()
    try:
        assert entered.wait(2)
        start = time.monotonic()
        if turn_off:
            handler._handle_settings_post({"usage_sharing": False})
            assert replies[-1][1]["ok"] and not replies[-1][1]["settings"]["usage_sharing"]
            assert usage.disclosure()["sample"]
            handler._handle_settings_post({"usage_sharing": True})
            assert replies[-1][1]["ok"] and replies[-1][1]["settings"]["usage_sharing"]
            assert enabled()["install_id"] != first_id
        usage._record(usage._path(), "searches", "count", "ok", time.time())
        assert time.monotonic() - start < 1
    finally:
        release.set()
        sender.join(5)
    assert results == [not turn_off]
    assert usage.disclosure()["next_payload"]["searches"] == 1
    if turn_off:
        assert usage.disclosure()["sent"] == []


@pytest.mark.parametrize("current", [False, True])
def test_stdio_role_writer_preserves_consent_changed_in_another_process(store, monkeypatch, current):
    monkeypatch.setattr(server, "SETTINGS_PATH", store / "settings.json")
    server._write_settings({}, usage_choice=not current)
    script = r'''
import json,sys
from pathlib import Path
import server, uoink_mcp_tools as tools, uoink_usage as usage
tools.bind_backend(server)
root = Path(sys.argv[1])
server.SETTINGS_PATH = root / "settings.json"
usage.configure(lambda: root, "3.10.0")
read = server._read_settings
stale = read()
print("ready", flush=True)
sys.stdin.readline()
snapshots = [stale]
server._read_settings = lambda: snapshots.pop() if snapshots else read()
print(json.dumps(tools.set_user_role({"role": "researcher"})), flush=True)
'''
    child = subprocess.Popen([sys.executable, "-c", script, str(store)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        server._write_settings({}, usage_choice=current)
        out, err = child.communicate("continue\n", timeout=10)
        assert child.returncode == 0, err
        assert json.loads(out)["ok"], out
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    assert server._read_settings()["usage_sharing"] is current
    assert server._read_settings()["role"] == "researcher"
    assert usage.disclosure()["sample"] is (not current)


def test_exit_flushes_queued_stdio_counts(store):
    enabled()
    script = r'''
import sys,time
from pathlib import Path
import uoink_usage as u
u.configure(lambda: Path(sys.argv[1]), "3.10.0")
record = u._record
def slow(*args):
    time.sleep(0.03)
    record(*args)
u._record = slow
# Three counts keep the backlog well inside the 1 s exit flush bound even on
# slow CI runners, where each locked write can take about 100 ms.
for _ in range(3):
    u.count("searches")
# Deliberately no queue.join: the daemon's exit hook must flush these.
'''
    result = subprocess.run([sys.executable, "-c", script, str(store)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert usage.disclosure()["next_payload"]["searches"] == 3


def test_exit_flush_is_bounded(store, monkeypatch):
    enabled()
    release, entered = threading.Event(), threading.Event()

    def record(*args):
        entered.set()
        release.wait(5)

    monkeypatch.setattr(usage, "_record", record)
    usage.count("searches")
    try:
        assert entered.wait(2)
        start = time.monotonic()
        assert usage.flush(0.05) is False
        assert time.monotonic() - start < 1
    finally:
        release.set()
        assert usage.flush()
