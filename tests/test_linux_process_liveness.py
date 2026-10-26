"""Linux liveness: an exited but unreaped pid (zombie) is not running."""
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

import _platform
import library_mirror
import source_subscriptions
import writer_peer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from install_receipt import process_identity  # noqa: E402

PID = 4242
LINUX = SimpleNamespace(platform="linux", executable=sys.executable)


def _fake_proc(monkeypatch, module, state):
    """Serve /proc/<PID>/stat for ``module``; any other path is missing."""
    def fake_open(path, *args, **kwargs):
        if str(path) == f"/proc/{PID}/stat" and state is not None:
            # A ")" inside comm must not shift the state field.
            return io.StringIO(f"{PID} (py (x)) {state} 1 {PID} {PID} 0 -1 4194560 0 0")
        raise FileNotFoundError(path)
    monkeypatch.setattr(module, "open", fake_open, raising=False)


@pytest.mark.parametrize("state, exited", [("Z", True), ("X", True), ("R", False),
                                           ("S", False), ("D", False), (None, False)])
def test_procfs_exited_reads_the_state_field(monkeypatch, state, exited):
    monkeypatch.setattr(_platform, "sys", LINUX)
    _fake_proc(monkeypatch, _platform, state)
    assert _platform.procfs_exited(PID) is exited


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_procfs_exited_never_reads_proc_off_linux(monkeypatch, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))

    def no_read(*args, **kwargs):
        raise AssertionError("procfs read off Linux")
    monkeypatch.setattr(_platform, "open", no_read, raising=False)
    assert _platform.procfs_exited(PID) is False


@pytest.mark.parametrize("state, running", [("Z", False), ("X", False), ("S", True)])
def test_signal_probes_treat_a_zombie_as_exited(monkeypatch, state, running):
    # kill(pid, 0) succeeds for a zombie; only the procfs state tells them apart.
    posix = SimpleNamespace(**{**vars(os), "name": "posix", "kill": lambda pid, sig: None})
    for module in (library_mirror, source_subscriptions, writer_peer, process_identity):
        monkeypatch.setattr(module, "os", posix)
        monkeypatch.setattr(module, "sys", LINUX)
    monkeypatch.setattr(_platform, "sys", LINUX)
    _fake_proc(monkeypatch, _platform, state)
    _fake_proc(monkeypatch, process_identity, state)
    expected = "alive" if running else "dead"
    assert library_mirror._process_liveness(PID) == expected
    assert source_subscriptions._process_alive(PID, None) == expected
    assert process_identity.liveness(PID, None) == expected
    assert writer_peer.process_is_live(PID) is running


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux procfs zombie")
def test_real_unreaped_child_is_not_running():
    child = subprocess.Popen([sys.executable, "-B", "-c",
                              "import time; print('ready', flush=True); time.sleep(30)"],
                             stdout=subprocess.PIPE)
    try:
        assert child.stdout.readline().strip() == b"ready"
        created = process_identity._posix_created_ms(child.pid)
        assert created is not None
        assert library_mirror._process_liveness(child.pid) == "alive"
        assert source_subscriptions._process_alive(child.pid, created) == "alive"
        assert process_identity.liveness(child.pid, created) == "alive"
        assert writer_peer.process_is_live(child.pid) is True
        os.kill(child.pid, signal.SIGKILL)
        stat = Path(f"/proc/{child.pid}/stat")
        deadline = time.monotonic() + 10
        while stat.read_text().rsplit(")", 1)[1].split()[0] != "Z":
            assert time.monotonic() < deadline, "child never became a zombie"
            time.sleep(0.01)
        os.kill(child.pid, 0)  # Still signalable: this is the case the probes must catch.
        assert library_mirror._process_liveness(child.pid) == "dead"
        assert library_mirror._process_liveness(child.pid, created) == "dead"
        assert source_subscriptions._process_alive(child.pid, created) == "dead"
        assert process_identity.liveness(child.pid, created) == "dead"
        assert writer_peer.process_is_live(child.pid) is False
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        child.stdout.close()
