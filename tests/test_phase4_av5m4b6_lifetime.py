"""AV-5m4b6 focused tests: destination-alias admission and shared gate.

Does not edit frozen AW/AW-2..AW-10 cases. Original AW-10 failed alias
output remains a failed observation of B5. These tests observe competitor
processes through an owned junction, same-process foreign-thread admission,
unknown/dead lifecycle, proven-death release, and unrelated-destination
serialization on the shared Windows gate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env
from tests.test_phase4_av5m4b5_lifetime import _competitor_mutex


def _make_junction(target: str, alias: str) -> None:
    child_env = os.environ.copy()
    child_env.update(B6_ALIAS_LINK=alias, B6_ALIAS_TARGET=target)
    made = subprocess.run(
        ["pwsh", "-NoProfile", "-Command",
         "New-Item -ItemType Junction -Path $env:B6_ALIAS_LINK -Target $env:B6_ALIAS_TARGET | Out-Null"],
        env=child_env, capture_output=True, text=True, timeout=8,
    )
    assert made.returncode == 0, made.stderr
    assert Path(target).samefile(alias)


def _competitor_session(dest: str, timeout: float = 12.0) -> dict:
    source = """import json, os, sys
import library_mirror as m
session = None
result = {"competitor_pid": os.getpid(), "started": False}
try:
    session = m._VaultIoSession.start(sys.argv[1])
    result.update(started=True, writer_pid=session.writer_pid, launcher_pid=session.pid,
                  alive=session.alive, lease_written=session._lease_written)
except (OSError, m._LockTimeout) as exc:
    result.update(refusal_type=type(exc).__name__, refusal=str(exc))
finally:
    if session is not None:
        result["termination_confirmed"] = session.terminate()
print(json.dumps(result))
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", source, str(dest)],
        capture_output=True, text=True, timeout=timeout,
    )
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout.strip())


def _foreign_thread_start(dest: str) -> dict:
    box: dict = {"started": False}
    session_holder: list = []

    def competitor() -> None:
        session = None
        try:
            session = mirror._VaultIoSession.start(str(dest))
            session_holder.append(session)
            box.update(
                started=True,
                writer_pid=session.writer_pid,
                alive=session.alive,
                lease_written=session._lease_written,
            )
        except (OSError, mirror._LockTimeout) as exc:
            box.update(started=False, refusal_type=type(exc).__name__, refusal=str(exc))
        finally:
            if session is not None:
                box["termination_confirmed"] = session.terminate()

    thread = threading.Thread(target=competitor)
    thread.start()
    thread.join(8)
    box["thread_alive"] = thread.is_alive()
    for session in session_holder:
        session.terminate()
    return box


@pytest.mark.skipif(os.name != "nt", reason="AW-10 junction admission is Windows")
def test_junction_competitor_process_refuses_before_first_lease(env):
    original = str(env.vault)
    alias = str(env.vault.parent / "j")
    _make_junction(original, alias)
    t = {"enter": time.monotonic()}
    first = mirror._VaultIoSession.start(original)
    t["started"] = time.monotonic()
    try:
        assert first.alive and not first._lease_written
        assert first.startup_s >= 0
        observed = _competitor_session(alias)
        t["competitor_returned"] = time.monotonic()
        observed.update(
            original=original, alias=alias, same_file=True,
            first_writer_pid=first.writer_pid,
            first_writer_alive=first.alive,
            first_lease_written=first._lease_written,
            startup_s=first.startup_s,
        )
        print(json.dumps(observed, sort_keys=True))
        assert not observed["started"], observed
        assert first.alive
        assert t["started"] >= t["enter"]
        assert t["competitor_returned"] >= t["started"]
    finally:
        t0 = time.monotonic()
        confirmed = first.terminate()
        t["terminated"] = time.monotonic()
        assert confirmed
        assert not first.physically_alive()
        assert first.termination_s >= 0
        assert (t["terminated"] - t0) + 0.05 >= first.termination_s
        t["caller_returned"] = time.monotonic()
        assert t["caller_returned"] >= t["terminated"]
        freed = _competitor_mutex(alias, timeout=0.5)
        assert freed["acquired"], freed


@pytest.mark.skipif(os.name != "nt", reason="AW-10 junction admission is Windows")
def test_same_process_foreign_thread_refuses_target_and_junction(env):
    original = str(env.vault)
    alias = str(env.vault.parent / "j")
    _make_junction(original, alias)
    first = mirror._VaultIoSession.start(original)
    try:
        assert first.alive and not first._lease_written
        through_target = _foreign_thread_start(original)
        through_alias = _foreign_thread_start(alias)
        through_target.update(path="target")
        through_alias.update(path="junction")
        print(json.dumps({"target": through_target, "alias": through_alias}, sort_keys=True))
        assert through_target["started"] is False, through_target
        assert through_alias["started"] is False, through_alias
        assert first.alive
    finally:
        assert first.terminate()
        assert not first.physically_alive()


@pytest.mark.skipif(os.name != "nt", reason="shared Windows admission gate")
def test_unrelated_destination_serializes_on_shared_gate(tmp_path_factory):
    dest_a = tmp_path_factory.mktemp("a")
    dest_b = tmp_path_factory.mktemp("b")
    assert Path(dest_a).resolve() != Path(dest_b).resolve()
    assert mirror._dest_mutex_name(str(dest_a)) == mirror._dest_mutex_name(str(dest_b))
    assert mirror._dest_mutex_name(str(dest_a)) == mirror._WRITER_ADMISSION_MUTEX
    first = mirror._VaultIoSession.start(str(dest_a))
    try:
        assert first.alive
        mutex_b = _competitor_mutex(str(dest_b))
        session_b = _competitor_session(str(dest_b))
        mutex_b.update(phase="held", dest="b")
        session_b.update(phase="held", dest="b")
        print(json.dumps({"mutex": mutex_b, "session": session_b}, sort_keys=True))
        assert not mutex_b["acquired"], mutex_b
        assert not session_b["started"], session_b
    finally:
        confirmed = first.terminate()
        assert confirmed
        assert not first.physically_alive()
        freed = _competitor_mutex(str(dest_b), timeout=0.5)
        assert freed["acquired"], freed
        later = mirror._VaultIoSession.start(str(dest_b))
        try:
            assert later.alive
            assert later.dest == str(dest_b)
        finally:
            assert later.terminate()


@pytest.mark.skipif(os.name != "nt", reason="shared Windows admission gate")
def test_helper_refuses_replacement_while_launching_or_live(env):
    with env.mirror._exclusive(timeout=2.0):
        prepared = mirror._VaultIoSession.prepare(str(env.vault))
        try:
            assert prepared._launching and prepared.proc is None
            with pytest.raises(OSError, match="still live"):
                mirror._VaultIoSession.start(str(env.vault))
            prepared.launch()
            assert prepared.alive and not prepared._launching
            with pytest.raises(OSError, match="still live"):
                mirror._VaultIoSession.start(str(env.vault))
            assert prepared.alive
        finally:
            assert prepared.terminate()
            assert not prepared.physically_alive()


@pytest.mark.skipif(os.name != "nt", reason="shared Windows admission gate")
def test_same_thread_nonrecursion_uses_gate_identity(tmp_path_factory):
    dest_a = tmp_path_factory.mktemp("a")
    dest_b = tmp_path_factory.mktemp("b")
    handle, key = mirror._win_acquire_dest_mutex(str(dest_a), 0.5)
    try:
        assert key == mirror._WRITER_ADMISSION_MUTEX
        with pytest.raises(mirror._LockTimeout):
            mirror._win_acquire_dest_mutex(str(dest_b), 0.2)
        with pytest.raises(mirror._LockTimeout):
            mirror._win_acquire_dest_mutex(str(dest_a) + os.sep, 0.2)
    finally:
        mirror._win_release_dest_mutex(handle, key)
    handle2, key2 = mirror._win_acquire_dest_mutex(str(dest_b), 0.5)
    try:
        assert key2 == key
    finally:
        mirror._win_release_dest_mutex(handle2, key2)


@pytest.mark.skipif(os.name != "nt", reason="shared Windows admission gate")
def test_session_dest_token_independent_of_gate_key(env):
    dest = str(env.vault)
    session = mirror._VaultIoSession.start(dest)
    try:
        owner = session._exclusion_owner
        assert owner is not None
        assert owner.key == mirror._WRITER_ADMISSION_MUTEX
        assert owner.key != dest
        assert session.dest == dest
        assert session.token
        plan = {"op_id": 7, "lock_generation": 3, "io": session}
        session.bind_operation(plan)
        assert session.dest == dest
        assert session.token
        assert owner.key == mirror._WRITER_ADMISSION_MUTEX
    finally:
        assert session.terminate()


@pytest.mark.skipif(os.name != "nt", reason="shared Windows admission gate")
def test_unknown_liveness_keeps_gate_proven_death_releases(env, monkeypatch):
    session = mirror._VaultIoSession.start(str(env.vault))
    try:
        assert session.alive
        owner = session._exclusion_owner
        assert owner is not None and owner.held
        owner.abandoned = True
        monkeypatch.setattr(session, "physical_liveness", lambda: "unknown")
        assert session.physically_alive()
        observed = _competitor_mutex(str(env.vault))
        helper = _foreign_thread_start(str(env.vault))
        assert not observed["acquired"], observed
        assert helper["started"] is False, helper
        assert owner.needed()
    finally:
        monkeypatch.undo()
        confirmed = session.terminate()
        assert confirmed
        assert not session.physically_alive()
        freed = _competitor_mutex(str(env.vault), timeout=0.5)
        assert freed["acquired"], freed
