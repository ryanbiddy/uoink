"""Doctor reports stdio probe failures without losing its other diagnostics."""
import io
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import server


@pytest.fixture
def doctor(monkeypatch):
    for name in ("_helper_health_status", "_diagnose_payload", "_podcast_corpus_reconciliation_status"):
        monkeypatch.setattr(server, name, lambda: {"ok": True})
    monkeypatch.setattr(server, "_doctor_heartbeat", lambda *_: {"stale": False})
    monkeypatch.setattr(server.index, "schema_migration_status", lambda *_: {"pending": False})
    monkeypatch.setattr(server.migrate_install, "migration_status", lambda: {})
    monkeypatch.setattr(server, "_path_integrity_status", lambda **_: {"ok": True})
    probe = Mock(return_value={"ok": True})
    monkeypatch.setattr(server, "_mcp_stdio_selfcheck", probe)
    return probe


@pytest.mark.parametrize("failure", ["tempdir", "mkdir", "socket", "bind", "getsockname", "socket_close", "cleanup", "probe"])
def test_modern_setup_and_cleanup_fail_soft_in_doctor(tmp_path, monkeypatch, doctor, failure):
    error = OSError(f"injected {failure} failure")
    original_tempdir = tempfile.TemporaryDirectory

    def tempdir(**kwargs):
        if failure == "tempdir":
            raise error
        directory = original_tempdir(dir=tmp_path, **kwargs)
        if failure == "cleanup":
            cleanup = directory.cleanup

            def locked_cleanup():
                cleanup()
                raise error

            directory.cleanup = locked_cleanup
        return directory

    monkeypatch.setattr(tempfile, "TemporaryDirectory", tempdir)
    if failure == "mkdir":
        monkeypatch.setattr(server.Path, "mkdir", Mock(side_effect=error))

    class Socket:
        def __enter__(self):
            return self

        def bind(self, address):
            assert address == ("127.0.0.1", 0)
            if failure == "bind":
                raise error

        def getsockname(self):
            if failure == "getsockname":
                raise error
            return "127.0.0.1", 18785

        def __exit__(self, *_):
            if failure == "socket_close":
                raise error

    monkeypatch.setattr(server.socket, "socket", Mock(
        side_effect=error if failure == "socket" else Socket))
    if failure == "probe":
        doctor.side_effect = [{"ok": True}, error]
    payload = server.doctor_payload()
    check = payload["mcp_stdio_modern"]
    assert check["ok"] is False and str(error) in check["error"]
    assert payload["mcp_stdio"] == payload["diagnose"] == {"ok": True}


def test_doctor_probes_share_one_deadline(monkeypatch, doctor):
    now = [100.0]
    monkeypatch.setattr(server, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def legacy(*, timeout):
        assert timeout == 30.0
        now[0] += 25.0
        return {"ok": True}

    doctor.side_effect = legacy
    modern = Mock(return_value={"ok": True})
    monkeypatch.setattr(server, "_mcp_modern_stdio_selfcheck", modern)
    assert server.doctor_payload()["mcp_stdio_modern"]["ok"]
    modern.assert_called_once_with(timeout=5.0)


@pytest.mark.parametrize("modern", [False, True])
def test_exhausted_deadline_does_not_launch_or_allocate(monkeypatch, modern):
    launch = Mock(side_effect=AssertionError("must not launch"))
    allocate = Mock(side_effect=AssertionError("must not allocate"))
    monkeypatch.setattr(server.subprocess, "Popen", launch)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", allocate)
    check = (server._mcp_modern_stdio_selfcheck if modern else server._mcp_stdio_selfcheck)(timeout=0)
    assert not check["ok"] and "deadline exhausted" in check["error"]
    launch.assert_not_called()
    allocate.assert_not_called()


@pytest.mark.parametrize("failure", ["launch", "thread", "stdin", "wait", "kill", "join", "stdout", "stderr"])
def test_probe_process_setup_and_cleanup_fail_soft(monkeypatch, failure):
    error = OSError(f"injected {failure} failure")

    class Pipe(io.StringIO):
        def __init__(self, name, text=""):
            super().__init__(text)
            self.name = name

        def close(self):
            super().close()
            if failure == self.name:
                raise error

    frames = [{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}},
              {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{}] * 91}}]
    proc = SimpleNamespace(stdin=Pipe("stdin"),
                           stdout=Pipe("stdout", "".join(json.dumps(frame) + "\n" for frame in frames)),
                           stderr=Pipe("stderr"), wait=Mock(return_value=0), kill=Mock())
    if failure == "wait":
        proc.wait.side_effect = error
    elif failure == "kill":
        proc.wait.side_effect = server.subprocess.TimeoutExpired("fixture", 1)
        proc.kill.side_effect = error
    monkeypatch.setattr(server.subprocess, "Popen", Mock(
        side_effect=error if failure == "launch" else None, return_value=proc))

    class Thread:
        def __init__(self, target, **_):
            self.target = target

        def start(self):
            if failure == "thread":
                raise error
            self.target()

        def join(self, timeout):
            assert 0 <= timeout <= 0.5
            if failure == "join":
                raise error

        def is_alive(self):
            return False

    monkeypatch.setattr(server.threading, "Thread", Thread)
    check = server._mcp_stdio_selfcheck(timeout=5)
    assert check["ok"] is False and str(error) in check["error"]
    if failure != "launch":
        assert proc.stdin.closed and proc.stdout.closed and proc.stderr.closed
