"""AV-5m4b5 focused tests: unknown liveness, mutex owner thread, failed start.

Does not edit frozen AW/AW-2..AW-9 cases. Original AW-9 failed logs remain
failed observations of B4. These tests add competitor-process observations
before and after lease creation, helper-created startup, recycled PID
identity, and proven-death release without a leaked gate.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env


def _competitor_mutex(dest, timeout=0.25):
    source = (
        "import json, os, sys\n"
        "import library_mirror as m\n"
        "try:\n"
        " h, k = m._win_acquire_dest_mutex(sys.argv[1], float(sys.argv[2]))\n"
        "except m._LockTimeout:\n"
        " print(json.dumps({'acquired': False, 'pid': os.getpid()}))\n"
        "else:\n"
        " print(json.dumps({'acquired': True, 'pid': os.getpid()}))\n"
        " m._win_release_dest_mutex(h, k)\n"
    )
    child = subprocess.run(
        [sys.executable, "-B", "-c", source, str(dest), str(timeout)],
        capture_output=True, text=True, timeout=8,
    )
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout.strip())


@pytest.mark.skipif(os.name != "nt", reason="AW-9 dest mutex is Windows")
def test_unknown_writer_after_launcher_exit_is_retained(env, monkeypatch):
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(poll=lambda: 0, pid=424240)
    session.writer_pid = 424241
    session.dest = str(env.vault)
    env.mirror._vault_io = session
    monkeypatch.setattr(mirror, "_process_liveness", lambda *a, **k: "unknown")

    def uncertain():
        session._dead = True
        return False

    monkeypatch.setattr(session, "terminate", uncertain)
    env.mirror._kill_vault_io(session)
    assert session.physical_liveness() == "unknown"
    assert session.physically_alive()
    assert env.mirror._vault_io is session, "Unknown writer was forgotten after its launcher exited"


@pytest.mark.skipif(os.name != "nt", reason="AW-9 dest mutex is Windows")
def test_destination_exclusion_survives_owning_thread_exit_before_lease(env):
    sessions = []
    errors = []
    t = {}

    def own():
        try:
            t["enter"] = time.monotonic()
            with env.mirror._exclusive(timeout=0.5):
                t["acquired"] = time.monotonic()
                session = mirror._VaultIoSession.start(str(env.vault))
                t["started"] = time.monotonic()
                sessions.append(session)
                env.mirror._vault_io = session
                assert not session._lease_written
            t["caller_returned"] = time.monotonic()
        except BaseException as exc:
            errors.append(repr(exc))

    thread = threading.Thread(target=own)
    thread.start()
    thread.join(8)
    try:
        assert not thread.is_alive() and not errors, errors
        session = sessions[0]
        assert session.physically_alive() and not session._lease_written
        assert t["started"] >= t["acquired"] >= t["enter"]
        assert t["caller_returned"] >= t["started"]
        observed = _competitor_mutex(env.vault)
        observed.update(
            original_writer=session.writer_pid,
            original_writer_alive=session.physically_alive(),
            lease_written=session._lease_written,
            caller_returned=True,
        )
        assert not observed["acquired"], observed
    finally:
        for session in sessions:
            session.terminate()
        env.mirror._vault_io = None


@pytest.mark.skipif(os.name != "nt", reason="AW-9 dest mutex is Windows")
def test_destination_exclusion_survives_owning_thread_exit_after_lease(env):
    sessions = []
    errors = []

    def own():
        try:
            with env.mirror._exclusive(timeout=0.5):
                session = mirror._VaultIoSession.start(str(env.vault))
                sessions.append(session)
                env.mirror._vault_io = session
                session.claim_lease()
                assert session._lease_written
        except BaseException as exc:
            errors.append(repr(exc))

    thread = threading.Thread(target=own)
    thread.start()
    thread.join(8)
    try:
        assert not thread.is_alive() and not errors, errors
        session = sessions[0]
        assert session.physically_alive() and session._lease_written
        observed = _competitor_mutex(env.vault)
        observed.update(
            original_writer=session.writer_pid,
            original_writer_alive=session.physically_alive(),
            lease_written=session._lease_written,
        )
        assert not observed["acquired"], observed
    finally:
        for session in sessions:
            session.terminate()
        env.mirror._vault_io = None


@pytest.mark.skipif(os.name != "nt", reason="AW-9 dest mutex is Windows")
def test_startup_failure_keeps_exclusion_until_child_death(env, monkeypatch):
    sessions = []
    errors = []
    original_terminate = mirror._VaultIoSession.terminate

    def no_ready(session, timeout=None):
        sessions.append(session)
        return None

    def uncertain(session):
        session._dead = True
        return False

    monkeypatch.setattr(mirror._VaultIoSession, "_readline", no_ready)
    monkeypatch.setattr(mirror._VaultIoSession, "terminate", uncertain)

    def own():
        try:
            with env.mirror._exclusive(timeout=0.5):
                env.mirror._start_vault_io(str(env.vault))
        except OSError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=own)
    thread.start()
    thread.join(8)
    try:
        assert not thread.is_alive() and sessions and errors
        session = sessions[0]
        assert session.proc.poll() is None and not session._lease_written
        assert env.mirror._vault_io is session
        observed = _competitor_mutex(env.vault)
        observed.update(
            original_session_pid=session.pid,
            parent_retained=env.mirror._vault_io is session,
            launcher_alive=session.proc.poll() is None,
            lease_written=session._lease_written,
        )
        assert not observed["acquired"], observed
    finally:
        monkeypatch.setattr(mirror._VaultIoSession, "terminate", original_terminate)
        for session in sessions:
            original_terminate(session)
        env.mirror._vault_io = None


@pytest.mark.skipif(os.name != "nt", reason="AW-9 dest mutex is Windows")
def test_helper_startup_failure_keeps_exclusion(env, monkeypatch):
    sessions = []
    errors = []
    original_terminate = mirror._VaultIoSession.terminate

    def no_ready(session, timeout=None):
        sessions.append(session)
        return None

    def uncertain(session):
        session._dead = True
        return False

    monkeypatch.setattr(mirror._VaultIoSession, "_readline", no_ready)
    monkeypatch.setattr(mirror._VaultIoSession, "terminate", uncertain)
    try:
        mirror._VaultIoSession.start(str(env.vault))
    except OSError as exc:
        errors.append(str(exc))
    try:
        assert sessions and errors
        session = sessions[0]
        assert session.proc.poll() is None
        assert session in mirror._retained_sessions
        observed = _competitor_mutex(env.vault)
        observed.update(
            helper=True,
            original_session_pid=session.pid,
            launcher_alive=session.proc.poll() is None,
        )
        assert not observed["acquired"], observed
    finally:
        monkeypatch.setattr(mirror._VaultIoSession, "terminate", original_terminate)
        for session in sessions:
            original_terminate(session)


@pytest.mark.skipif(os.name != "nt", reason="AW-9 dest mutex is Windows")
def test_competitor_blocked_before_and_after_lease_then_released_on_death(env):
    t = {}
    t["enter"] = time.monotonic()
    session = mirror._VaultIoSession.start(str(env.vault))
    t["started"] = time.monotonic()
    try:
        assert session.startup_s >= 0
        assert not session._lease_written
        before = _competitor_mutex(env.vault)
        before.update(phase="before_lease", writer=session.writer_pid)
        assert not before["acquired"], before
        session.claim_lease()
        t["leased"] = time.monotonic()
        after = _competitor_mutex(env.vault)
        after.update(phase="after_lease", writer=session.writer_pid)
        assert not after["acquired"], after
        t0 = time.monotonic()
        confirmed = session.terminate()
        t["terminated"] = time.monotonic()
        assert confirmed
        assert not session.physically_alive()
        assert session.termination_s >= 0
        assert (t["terminated"] - t0) + 0.05 >= session.termination_s
        freed = _competitor_mutex(env.vault, timeout=0.5)
        freed.update(phase="after_death")
        assert freed["acquired"], freed
        mirror._win_release_dest_mutex  # competitor already released
        assert t["started"] >= t["enter"]
        assert t["leased"] >= t["started"]
        assert t["terminated"] >= t["leased"]
    finally:
        session.terminate()


@pytest.mark.skipif(os.name != "nt", reason="Windows pid identity")
def test_recycled_pid_is_not_terminated(monkeypatch):
    killed = []
    k32 = mirror._kernel32()

    def term(handle, code):
        killed.append(int(code))
        return True

    monkeypatch.setattr(k32, "TerminateProcess", term)
    monkeypatch.setattr(mirror, "_windows_process_created_ms", lambda handle: 99_000)
    assert mirror._win_terminate_pid(os.getpid(), created_ms=1) is False
    assert killed == []


@pytest.mark.skipif(os.name != "nt", reason="AW-9 dest mutex is Windows")
def test_abandoned_flag_is_not_writer_death(env):
    session = mirror._VaultIoSession.start(str(env.vault))
    try:
        owner = session._exclusion_owner
        assert owner is not None and owner.held
        owner.abandoned = True
        assert session.physically_alive()
        assert owner.needed()
        observed = _competitor_mutex(env.vault)
        assert not observed["acquired"], observed
    finally:
        session.terminate()
        assert not session.physically_alive()


@pytest.mark.skipif(os.name != "nt", reason="AW-9 dest mutex is Windows")
def test_dest_aliases_share_exclusion_not_temp(tmp_path_factory, monkeypatch):
    dest = tmp_path_factory.mktemp("d")
    alias = str(dest) + os.sep
    assert mirror._canonical_dest(str(dest)) == mirror._canonical_dest(alias)
    assert mirror._dest_mutex_name(str(dest)) == mirror._dest_mutex_name(alias)
    assert mirror._dest_mutex_name(str(dest)) == mirror._WRITER_ADMISSION_MUTEX
    t1 = tmp_path_factory.mktemp("t1")
    t2 = tmp_path_factory.mktemp("t2")
    monkeypatch.setenv("TEMP", str(t1))
    name1 = mirror._dest_mutex_name(str(dest))
    monkeypatch.setenv("TEMP", str(t2))
    name2 = mirror._dest_mutex_name(alias)
    assert name1 == name2
    session = mirror._VaultIoSession.start(str(dest))
    try:
        observed = _competitor_mutex(alias)
        observed.update(alias=alias, dest=str(dest))
        assert not observed["acquired"], observed
    finally:
        confirmed = session.terminate()
        assert confirmed
        freed = _competitor_mutex(alias, timeout=0.5)
        assert freed["acquired"], freed
