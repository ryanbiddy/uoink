"""Native ABI fixtures plus live child identity on the host platform."""
import ctypes
import errno
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import _platform as native
import uoink_install_isolation as isolation


class LibprocFixture:
    def __init__(self, *, status=2, error=0, short=False, reuse=False, path=b"/fixture/python"):
        self.status, self.error, self.short = status, error, short
        self.reuse, self.path, self.calls = reuse, path, 0

    def proc_pidinfo(self, pid, flavor, arg, pointer, size):
        assert flavor == 3 and size == 136 and arg == 0
        self.calls += 1
        if self.error:
            ctypes.set_errno(self.error)
            return 0
        info = pointer._obj
        info.pid, info.status = pid, self.status
        info.start_sec, info.start_usec = 1700000000, 123456 + (self.calls if self.reuse else 0)
        return size - 1 if self.short else size

    def proc_pidpath(self, pid, buffer, size):
        if self.path is None:
            ctypes.set_errno(errno.EPERM)
            return 0
        buffer.value = self.path
        return len(self.path)


def test_native_layout_and_microsecond_snapshot(monkeypatch):
    assert ctypes.sizeof(native._DarwinProcBSDInfo) == 136
    assert native._DarwinProcBSDInfo.start_sec.offset == 120
    monkeypatch.setattr(native, "_darwin_libproc", lambda: LibprocFixture())
    observed = native.darwin_observe(123, with_executable=True)
    assert observed == native.DarwinProcessObservation("alive", 1700000000123456, "/fixture/python")
    assert observed.created_ms == 1700000000123


@pytest.mark.parametrize("kwargs, expected", [
    ({"error": errno.ESRCH}, "dead"), ({"error": errno.EPERM}, "unknown"),
    ({"error": errno.EACCES}, "unknown"), ({"short": True}, "unknown"),
    ({"status": 5}, "dead"), ({"status": 99}, "unknown"),
    ({"path": None}, "unknown"), ({"path": b"relative"}, "unknown"),
    ({"reuse": True}, "unknown"),
])
def test_incomplete_native_observations_never_authorize_ownership(monkeypatch, kwargs, expected):
    monkeypatch.setattr(native, "_darwin_libproc", lambda: LibprocFixture(**kwargs))
    assert native.darwin_observe(123, with_executable=True).status == expected


def test_exact_start_missing_start_and_executable_identity(monkeypatch, tmp_path):
    image = tmp_path / "python"
    image.write_bytes(b"fixture")
    other = tmp_path / "foreign"
    other.write_bytes(b"fixture")
    monkeypatch.setattr(native, "darwin_observe", lambda *a, **k:
                        native.DarwinProcessObservation("alive", 123456789, str(image)))
    assert native.darwin_liveness(123, 123456, str(image)) == "alive"
    assert native.darwin_liveness(123, 123457, str(image)) == "dead"
    assert native.darwin_liveness(123, None, str(image)) == "unknown"
    assert native.darwin_liveness(123, 123456, str(other)) == "dead"
    assert native.darwin_liveness(123, 123456, str(tmp_path / "absent")) == "unknown"


def test_invalid_pid_and_library_unavailable_are_unknown(monkeypatch):
    for pid in (0, -1, True, None, "123", 2**32):
        assert native.darwin_observe(pid).status == "unknown"
    def unavailable():
        raise OSError("library unavailable")
    monkeypatch.setattr(native, "_darwin_libproc", unavailable)
    assert native.darwin_observe(123).status == "unknown"


def test_darwin_consumers_share_unknown_and_exact_creation(monkeypatch):
    import importlib.util
    from pathlib import Path
    import library_mirror
    import source_subscriptions
    source = Path(__file__).resolve().parents[1] / "scripts/install_receipt/process_identity.py"
    spec = importlib.util.spec_from_file_location("receipt_identity_fixture", source)
    receipt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receipt)
    for module in (library_mirror, source_subscriptions, receipt, isolation):
        monkeypatch.setattr(module, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(native, "darwin_observe", lambda *a, **k: native.DarwinProcessObservation("unknown"))
    probes = (library_mirror._process_liveness, source_subscriptions._process_alive, receipt.liveness)
    for probe in probes:
        assert probe(123, 456) == "unknown"
    for probe in (library_mirror._posix_process_created_ms, source_subscriptions._posix_process_created_ms,
                  receipt._posix_created_ms, isolation._posix_process_created_ms):
        assert probe(123) is None
    monkeypatch.setattr(native, "darwin_observe", lambda *a, **k: native.DarwinProcessObservation("alive", 456000))
    for probe in probes:
        assert probe(123, 456) == "alive"
        assert probe(123, 457) == "dead"
        assert probe(123, None) == "unknown"


def test_darwin_filesystem_identity_not_string_case(monkeypatch, tmp_path):
    monkeypatch.setattr(isolation, "sys", SimpleNamespace(platform="darwin"))
    upper = tmp_path / "MixedCase"
    upper.mkdir()
    lower = tmp_path / "mixedcase"
    if lower.exists():  # case-insensitive APFS/NTFS: actual filesystem identity
        assert isolation._same_path(upper, lower)
        assert isolation._is_nested(upper / "child", lower)
    else:  # case-sensitive APFS/ext4 must not collapse distinct names
        lower.mkdir()
        assert not isolation._same_path(upper, lower)
        assert not isolation._is_nested(upper / "child", lower)


def test_live_child_exact_identity_exit_and_foreign_executable(tmp_path):
    # On macOS this executes libproc; on Windows it retains the existing native
    # handle path. No test is skipped and no process is killed by a guessed PID.
    child = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(30)"])
    try:
        if os.name == "nt":
            handle, _ = isolation._windows_open_process(child.pid, isolation._PROCESS_QUERY_LIMITED_INFORMATION)
            try:
                created = isolation._windows_process_created_ms(handle)
            finally:
                isolation._windows_close_handle(handle)
        else:
            created = isolation._posix_process_created_ms(child.pid)
        image = isolation._process_executable(child.pid)
        assert created is not None and image
        assert isolation._pid_identity_liveness(child.pid, created, image) == "alive"
        assert isolation._pid_identity_liveness(child.pid, created + 1, image) == "dead"
        foreign = tmp_path / "foreign-python"
        foreign.write_bytes(b"not the child executable")
        assert isolation._pid_identity_liveness(child.pid, created, str(foreign)) == "dead"
        child.terminate()
        child.wait(timeout=10)
        assert isolation._pid_identity_liveness(child.pid, created, image) == "dead"
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
