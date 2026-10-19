"""Native ABI fixtures plus live child identity on the host platform."""
import ctypes
import errno
import json
import os
import subprocess
import sys
import time
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
    assert observed.created_ms == 1700000000123.456
    assert native.darwin_creation_us(json.loads(json.dumps(observed.created_ms))) == observed.started_us


def test_persisted_birth_distinguishes_every_microsecond_in_a_millisecond():
    starts = range(1792368000123000, 1792368000124000)
    decoded = [native.darwin_creation_us(json.loads(json.dumps(
        native.DarwinProcessObservation("alive", start).created_ms))) for start in starts]
    assert decoded == list(starts)


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
    assert native.darwin_liveness(123, 123456.789, str(image)) == "alive"
    assert native.darwin_liveness(123, 123456.788, str(image)) == "dead"
    assert native.darwin_liveness(123, 123456, str(image)) == "dead"
    assert native.darwin_liveness(123, 123457, str(image)) == "dead"
    assert native.darwin_liveness(123, None, str(image)) == "unknown"
    assert native.darwin_liveness(123, 123456.789, str(other)) == "dead"
    assert native.darwin_liveness(123, 123456.789, str(tmp_path / "absent")) == "unknown"
    assert native.darwin_liveness(123, None, str(image), require_identity=False) == "alive"
    for invalid in ("", True, 123, [str(image)]):
        assert native.darwin_liveness(123, 123456.789, invalid) == "unknown"


def test_invalid_pid_and_library_unavailable_are_unknown(monkeypatch):
    for pid in (0, -1, True, None, "123", 2**32):
        assert native.darwin_observe(pid).status == "unknown"
    def unavailable():
        raise OSError("library unavailable")
    monkeypatch.setattr(native, "_darwin_libproc", unavailable)
    assert native.darwin_observe(123).status == "unknown"


def test_darwin_death_precedes_executable_query(monkeypatch):
    for fixture in (LibprocFixture(status=5), LibprocFixture(error=errno.ESRCH)):
        def forbidden(*args):
            raise AssertionError("exited process must not need an executable")
        fixture.proc_pidpath = forbidden
        monkeypatch.setattr(native, "_darwin_libproc", lambda: fixture)
        monkeypatch.setattr(isolation, "sys", SimpleNamespace(platform="darwin"))
        assert isolation._pid_identity_liveness(123, 456, "/missing/python") == "dead"


def test_consumers_compare_executable_and_mirror_lease_tolerance(monkeypatch, tmp_path):
    import library_mirror as mirror
    import source_subscriptions as subscriptions
    for module in (mirror, subscriptions):
        monkeypatch.setattr(module, "sys", SimpleNamespace(platform="darwin", executable=sys.executable))
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"fixture")
    calls = []
    def observe(pid, *, with_executable=False):
        calls.append(with_executable)
        return native.DarwinProcessObservation("alive", 1700000000123456, sys.executable)
    monkeypatch.setattr(native, "darwin_observe", observe)
    assert mirror._process_liveness(123, 1700000000122.456, tolerance_ms=1) == "alive"
    assert mirror._process_liveness(123, 1700000000122.455, tolerance_ms=1) == "dead"
    assert mirror._process_liveness(123, 1700000000123.455) == "dead"
    assert mirror._lease_holder_status({"pid": 123, "created_ms": 1700000000123.456}) == "alive"
    assert subscriptions._process_alive(123, 1700000000123.456, str(foreign)) == "dead"
    assert all(calls)
    assert not mirror._creation_identity_equal(1700000000123.455, 1700000000123.456)
    assert not mirror._child_born_on_or_after_parent(1700000000123.455, 1700000000123.456)
    monkeypatch.setattr(mirror, "sys", SimpleNamespace(platform="darwin", executable=str(foreign)))
    assert mirror._process_liveness(123, 1700000000123.456) == "dead"


def test_darwin_identity_file_keeps_microseconds(monkeypatch, tmp_path):
    monkeypatch.setattr(isolation, "sys", SimpleNamespace(platform="darwin"))
    binding = isolation.validate_binding(profile=tmp_path, port=5180)
    stamp = 1700000000123.456
    path = isolation.write_runtime_identity(binding, pid=123, executable=sys.executable,
                                            script=__file__, created_ms=stamp, nonce="fixture")
    payload = json.loads(path.read_text())
    assert payload["created_ms"] == stamp
    assert isolation._parse_owned_identity(payload)["created_ms"] == stamp
    monkeypatch.setattr(native, "darwin_observe", lambda *a, **k:
                        native.DarwinProcessObservation("alive", 1700000000123457, sys.executable))
    assert isolation._identity_liveness(payload) == "dead"


def test_darwin_child_record_uses_its_own_executable(monkeypatch, tmp_path):
    import source_subscriptions as subscriptions
    monkeypatch.setattr(subscriptions, "sys", SimpleNamespace(platform="darwin", executable=sys.executable))
    monkeypatch.setattr(subscriptions, "_process_created_ms", lambda pid: None)
    image = tmp_path / "ffmpeg"
    image.write_bytes(b"fixture")
    monkeypatch.setattr(native, "darwin_observe", lambda *a, **k:
                        native.DarwinProcessObservation("alive", 1700000000123456, str(image)))
    subscriptions.record_child_start(tmp_path, "fixture-start", 123, "fixture-instance")
    path = subscriptions._ownership_path(tmp_path, subscriptions.CHILD_OWNERSHIP_DIR, "fixture-start")
    record = subscriptions._read_ownership_record(path)
    child = record["children"][0]
    assert child["created_ms"] == 1700000000123.456
    assert child["executable"] == str(image)
    assert subscriptions.child_ownership_liveness(tmp_path, "fixture-start") == "alive"
    child["created_ms"] -= 0.001
    subscriptions._write_ownership_record(path, record)
    assert subscriptions.child_ownership_liveness(tmp_path, "fixture-start") == "dead"
    child.pop("executable")
    subscriptions._write_ownership_record(path, record)
    assert subscriptions.child_ownership_liveness(tmp_path, "fixture-start") == "unknown"


@pytest.mark.skipif(sys.platform != "darwin", reason="requires native libproc")
def test_native_unreaped_child_is_dead_before_executable_lookup():
    # Never poll/wait until after observation: Popen.poll() itself reaps children.
    child = subprocess.Popen([sys.executable, "-B", "-c", "pass"])
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            observed = native.darwin_observe(child.pid, with_executable=True)
            if observed.status == "dead":
                break
            time.sleep(0.01)
        assert observed.status == "dead"  # libproc can return ESRCH for zombies.
        assert isolation._pid_identity_liveness(child.pid, 1, sys.executable) == "dead"
    finally:
        child.wait(timeout=10)


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
        monkeypatch.setattr(module, "sys", SimpleNamespace(platform="darwin", executable=sys.executable))
    monkeypatch.setattr(native, "darwin_observe", lambda *a, **k: native.DarwinProcessObservation("unknown"))
    probes = (library_mirror._process_liveness, source_subscriptions._process_alive, receipt.liveness)
    for probe in probes:
        assert probe(123, 456) == "unknown"
    for probe in (library_mirror._posix_process_created_ms, source_subscriptions._posix_process_created_ms,
                  receipt._posix_created_ms, isolation._posix_process_created_ms):
        assert probe(123) is None
    monkeypatch.setattr(native, "darwin_observe", lambda *a, **k:
                        native.DarwinProcessObservation("alive", 456001, sys.executable))
    for probe in probes:
        assert probe(123, 456.001) == "alive"
        assert probe(123, 456.002) == "dead"
        assert probe(123, 457) == "dead"
    assert library_mirror._process_liveness(123, None) == "alive"
    assert source_subscriptions._process_alive(123, None) == "unknown"
    assert receipt.liveness(123, None) == "unknown"
    record = {"pid": 123, "created_ms": 456.001, "executable": sys.executable}
    assert receipt.exact_identity_on_handle(record, record)
    assert not receipt.exact_identity_on_handle(record, {**record, "created_ms": 456.002})


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
        if sys.platform == "darwin":
            import library_mirror as mirror
            import source_subscriptions as subscriptions
            assert mirror._pid_is_alive(child.pid)
            assert mirror._pid_is_alive(child.pid, created)
            assert subscriptions._process_alive(child.pid, created) == "alive"
            app = tmp_path / "app"
            app.mkdir()
            (app / "server.py").write_text("# fixture")
            (tmp_path / "runtime-identity.json").write_text(json.dumps({
                "pid": child.pid, "created_ms": created, "executable": image,
                "script": str(app / "server.py")}))
            assert native.darwin_helper_running(app, tmp_path)
            assert isolation._pid_identity_liveness(child.pid, created + 0.001, image) == "dead"
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
