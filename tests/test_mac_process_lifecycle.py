"""Native POSIX tree cleanup, including owner death and surviving foreign work."""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

import pytest

import _platform as native
import uoink_install_isolation as isolation
from uoink_processes import PosixChild


GRANDCHILD = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
CHILD = f"""
import subprocess,sys,time
p = subprocess.Popen([sys.executable, '-c', {GRANDCHILD!r}])
print(p.pid, flush=True)
time.sleep(60)
"""
TREE = f"""
import json,os,subprocess,sys
p = subprocess.Popen([sys.executable, '-c', {CHILD!r}], stdout=subprocess.PIPE)
grandchild = int(p.stdout.readline())
print(json.dumps([os.getpid(), p.pid, grandchild]), flush=True)
sys.stdin.readline()
sys.exit(7)
"""


def line(stream):
    assert select.select([stream], [], [], 15)[0], "child did not acknowledge readiness"
    return stream.readline()


def dead(pid):
    if sys.platform == "darwin":
        return native.darwin_observe(pid).status == "dead"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return isolation._posix_process_state(pid) in {"Z", "X"}


def assert_dead(pids):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if all(dead(pid) for pid in pids):
            return
        time.sleep(0.01)
    assert all(dead(pid) for pid in pids), pids


@pytest.mark.skipif(os.name == "nt", reason="native POSIX process groups")
@pytest.mark.parametrize("ending", ["cancel", "exit", "crash", "stopped"])
def test_tree_cleanup_and_foreign_process_survival(ending):
    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    child = PosixChild([sys.executable, "-c", TREE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        pids = json.loads(line(child.stdout))
        assert child.pid == pids[0]
        assert all(os.getpgid(pid) == child.pgid for pid in pids)
        assert os.getpgid(foreign.pid) != child.pgid
        if ending == "exit":
            child.stdin.write(b"exit\n")
            child.stdin.flush()
        elif ending == "crash":
            os.kill(child.pid, signal.SIGKILL)
        else:
            if ending == "stopped":
                for pid in pids:
                    os.kill(pid, signal.SIGSTOP)
            child.terminate()
        assert child.wait(timeout=10) == (7 if ending == "exit" else -signal.SIGKILL)
        assert child.cleaned
        assert_dead(pids)
        # Repeated cleanup cannot signal a recycled numeric group.
        child.kill()
        assert child.wait(timeout=1) is not None
        assert foreign.poll() is None
    finally:
        child.kill()
        child.wait(timeout=10)
        child.stdin.close()
        child.stdout.close()
        foreign.kill()
        foreign.wait(timeout=10)


@pytest.mark.skipif(os.name == "nt", reason="native POSIX parent-death lifeline")
def test_owner_sigkill_cleans_tree_without_parent_finally():
    owner_code = f"""
import subprocess,sys,time
from uoink_processes import PosixChild
p = PosixChild([sys.executable, '-c', {TREE!r}], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
print(p.stdout.readline().decode().strip(), flush=True)
time.sleep(60)
"""
    owner = subprocess.Popen([sys.executable, "-c", owner_code], stdout=subprocess.PIPE)
    try:
        pids = json.loads(line(owner.stdout))
        owner.kill()
        owner.wait(timeout=10)
        assert_dead(pids)
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=10)
        owner.stdout.close()


@pytest.mark.skipif(os.name == "nt", reason="native POSIX mirror owner death")
def test_mirror_owner_death_releases_writer_and_admission(tmp_path):
    owner_code = """
import sys,time
import library_mirror as mirror
session = mirror._VaultIoSession.start(sys.argv[1])
print(session.pid, flush=True)
time.sleep(60)
"""
    owner = subprocess.Popen([sys.executable, "-c", owner_code, str(tmp_path)], stdout=subprocess.PIPE)
    try:
        writer = int(line(owner.stdout))
        owner.kill()
        owner.wait(timeout=10)
        assert_dead([writer])
        import library_mirror as mirror
        restarted = mirror._VaultIoSession.start(str(tmp_path))
        try:
            assert restarted.call({"cmd": "whoami"})["pid"] == restarted.pid
        finally:
            assert restarted.terminate()
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=10)
        owner.stdout.close()


@pytest.mark.skipif(os.name == "nt", reason="native POSIX server cancellation")
@pytest.mark.parametrize("ending", ["cancel", "timeout"])
def test_server_job_owns_descendants(tmp_path, ending):
    import server
    import threading
    marker = tmp_path / "pids.json"
    command = TREE.replace("print(json.dumps([os.getpid(), p.pid, grandchild]), flush=True)",
                           f"open({str(marker)!r}, 'w').write(json.dumps([os.getpid(), p.pid, grandchild]))")
    # Keep the root alive even with DEVNULL stdin.
    command = command.replace("sys.stdin.readline()", "__import__('time').sleep(60)")
    cancel = threading.Event()
    errors = []
    def run():
        try:
            server._run_subprocess([sys.executable, "-c", command], cancel_event=cancel,
                                   timeout=2 if ending == "timeout" else 30)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        if ending == "cancel":
            cancel.set()
        thread.join(15)
        assert not thread.is_alive()
        expected = server.PlaylistJobCancelled if ending == "cancel" else subprocess.TimeoutExpired
        assert len(errors) == 1 and isinstance(errors[0], expected)
        assert_dead(json.loads(marker.read_text()))
    finally:
        cancel.set()
        thread.join(15)


@pytest.mark.skipif(os.name == "nt", reason="native POSIX launch protocol")
def test_missing_command_and_communicate_timeout():
    with pytest.raises(FileNotFoundError):
        PosixChild(["/uoink-test-missing-executable"])
    child = PosixChild([sys.executable, "-c", "import time; print('hello', flush=True); time.sleep(60)"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            child.communicate(timeout=0.1)
        child.kill()
        out, err = child.communicate(timeout=10)
        assert out == "hello\n" and err == ""
        assert child.cleaned and child.returncode == -signal.SIGKILL
    finally:
        child.kill()
        child.wait(timeout=10)


def test_supervisor_missing_cleanup_evidence_fails_closed(monkeypatch):
    import threading
    from types import SimpleNamespace
    child = PosixChild.__new__(PosixChild)
    child._lock = threading.RLock()
    child._failure = None
    child.returncode = None
    child.cleaned = False
    child._lifeline = None
    child._status, write_fd = os.pipe()
    os.close(write_fd)
    child._supervisor = SimpleNamespace(poll=lambda: -9)
    # Avoid select on anonymous Windows pipe; inject the exact protocol failure.
    def lost(*args):
        raise OSError("missing cleanup proof")
    monkeypatch.setattr("uoink_processes._receive", lost)
    with pytest.raises(OSError, match="cleanup proof"):
        child.poll()
    assert not child.cleaned and child.returncode is None
    with pytest.raises(OSError, match="cleanup proof"):
        child.poll()


@pytest.mark.skipif(os.name == "nt", reason="native POSIX supervisor crash")
def test_anchor_cleans_tree_if_supervisor_crashes():
    child = PosixChild([sys.executable, "-c", TREE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        pids = json.loads(line(child.stdout))
        child._supervisor.kill()
        child._supervisor.wait(timeout=10)
        with pytest.raises(OSError, match="proof of cleanup"):
            child.poll()
        assert_dead(pids)
        assert not child.cleaned
    finally:
        child.kill()
        child.stdin.close()
        child.stdout.close()


@pytest.mark.skipif(os.name == "nt", reason="native POSIX receipt cleanup")
def test_receipt_session_certifies_group_cleanup(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/install_receipt"))
    from p4_session import spawn_owned
    owned = spawn_owned([sys.executable, "-c", TREE], cwd=tmp_path, env=dict(os.environ))
    try:
        pids = json.loads(line(owned.popen.stdout))
        result = owned.terminate_tree(timeout=10)
        assert result["cleaned"] and result["descendants_exited"]
        assert not result["identity_uncertain"]
        assert_dead(pids)
        assert owned.terminate_tree() == result
    finally:
        owned.close()
        for stream in (owned.popen.stdin, owned.popen.stdout, owned.popen.stderr):
            stream.close()


@pytest.mark.parametrize("state, count, expected", [
    ("dead", 4, True), ("alive", 4, False), ("unknown", 4, False),
    ("dead", -1, False), ("dead", 3, False), ("dead", 0, True),
    ("alive", 0, False), ("unknown", 0, False),
])
def test_native_group_drain_needs_complete_death_evidence(monkeypatch, state, count, expected):
    from types import SimpleNamespace
    import uoink_processes as processes
    class ListPids:
        def __call__(self, kind, group, buffer, size):
            assert kind == 2 and group == 123
            if buffer is None:
                return 4
            buffer[0] = 123
            return count
    monkeypatch.setattr(processes, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(native, "_darwin_libproc", lambda: SimpleNamespace(proc_listpids=ListPids()))
    monkeypatch.setattr(native, "darwin_observe", lambda pid: native.DarwinProcessObservation(state))
    assert processes._group_drained(123) is expected


@pytest.mark.parametrize("ending", ["success", "error", "timeout"])
def test_run_owned_preserves_result_and_always_cleans(monkeypatch, ending):
    import io
    import uoink_processes as processes
    from types import SimpleNamespace
    effects = []
    def communicate(**kwargs):
        if ending == "timeout":
            raise subprocess.TimeoutExpired(["fixture"], 1)
        return "output", "error"
    proc = SimpleNamespace(
        returncode=7 if ending == "error" else 0, communicate=communicate,
        terminate=lambda: effects.append("terminate"), wait=lambda **kw: effects.append("wait"),
        stdin=None, stdout=io.BytesIO(), stderr=io.BytesIO())
    monkeypatch.setattr(processes, "PosixChild", lambda *a, **k: proc)
    if ending == "success":
        result = processes.run_owned(["fixture"], capture_output=True, check=True)
        assert result.stdout == "output" and result.returncode == 0
    else:
        with pytest.raises(subprocess.TimeoutExpired if ending == "timeout"
                           else subprocess.CalledProcessError):
            processes.run_owned(["fixture"], capture_output=True, check=True, timeout=1)
    assert effects == ["terminate", "wait"]
    assert proc.stdout.closed and proc.stderr.closed


@pytest.mark.skipif(os.name == "nt", reason="native POSIX inherited flock lifetime")
def test_supervisor_retains_admission_until_group_cleanup(tmp_path):
    import fcntl
    path = tmp_path / "admission.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    child = None
    contender = None
    try:
        child = PosixChild([sys.executable, "-c", "import time; time.sleep(60)"], hold_fds=(fd,))
        os.close(fd)  # Same kernel operation as parent death; no explicit unlock.
        fd = None
        contender = os.open(path, os.O_RDWR)
        with pytest.raises(BlockingIOError):
            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        child.terminate()
        child.wait(timeout=10)
        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        if child is not None:
            child.terminate()
            child.wait(timeout=10)
        if fd is not None:
            os.close(fd)
        if contender is not None:
            os.close(contender)
