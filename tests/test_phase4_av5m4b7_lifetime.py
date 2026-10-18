"""AV-5m4b7 focused tests: cancelled launch retention and helper ownership.

Does not edit frozen AW/AW-2..AW-11 cases. Original AW-11 failed logs remain
failed observations of B6. These tests observe cancellation during an actual
Popen handoff, launch failure after cancellation, eventual cleanup and gate
release, originating-helper success with foreign-helper refusal, and exact
destination reuse/refusal without parent realpath.

An idle cancelled child is not post-timeout publication.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time

import pytest

import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env
from tests.test_phase4_av5m4b5_lifetime import _competitor_mutex
from tests.test_phase4_av5m4b6_lifetime import _make_junction


def _is_vault_worker(cmd) -> bool:
    if not isinstance(cmd, (list, tuple)):
        return False
    return any("library_mirror_vault_io" in str(part) for part in cmd)


def _pid_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    return bool(mirror._pid_is_alive(pid))


def test_cancel_during_popen_handoff_retains_then_cleans_original_session(env, monkeypatch):
    entered = threading.Event()
    resume = threading.Event()
    original_popen = mirror.subprocess.Popen
    created = []
    errors = []
    t = {}

    def delayed_popen(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        if not _is_vault_worker(cmd):
            return original_popen(*args, **kwargs)
        entered.set()
        assert resume.wait(5), "popen handoff was not released"
        proc = original_popen(*args, **kwargs)
        created.append({"pid": proc.pid, "proc": proc})
        return proc

    monkeypatch.setattr(mirror.subprocess, "Popen", delayed_popen)

    def caller() -> None:
        try:
            with env.mirror._exclusive(timeout=2.0):
                env.mirror._start_vault_io(str(env.vault))
        except (OSError, mirror._LockTimeout) as exc:
            errors.append({"type": type(exc).__name__, "message": str(exc)})

    thread = threading.Thread(target=caller)
    t["enter"] = time.monotonic()
    thread.start()
    try:
        assert entered.wait(5)
        t["popen_entered"] = time.monotonic()
        session = env.mirror._vault_io
        assert session is not None and session.proc is None
        assert session._popen_in_progress
        t["cancel_start"] = time.monotonic()
        env.mirror._kill_vault_io(session)
        t["cancel_returned"] = time.monotonic()
        owner = session._exclusion_owner
        mid = {
            "cancel_return_s": session.cancel_return_s,
            "termination_s_mid": session.termination_s,
            "startup_s_mid": session.startup_s,
            "launcher_pid_mid": session.pid,
            "writer_pid_mid": session.writer_pid,
            "physical_liveness_mid": session.physical_liveness(),
            "admitted_alive_mid": session.alive,
            "cancelled_admission": session._dead,
            "popen_in_progress": session._popen_in_progress,
            "mirror_retained": env.mirror._vault_io is session,
            "global_retained": session in mirror._retained_sessions,
            "owner_held": bool(owner and owner.held),
            "lease_written": session._lease_written,
            "content_mutation_commands": 0,
            "idle_child_is_not_post_timeout_publication": True,
        }
        print(json.dumps({"mid": mid}, sort_keys=True))
        assert mid["cancelled_admission"]
        assert mid["mirror_retained"] and mid["global_retained"] and mid["owner_held"]
        assert mid["lease_written"] is False
        assert t["cancel_returned"] - t["cancel_start"] < 0.5
        assert session.cancel_return_s >= 0
        assert session.cancel_return_s < 0.5
        resume.set()
        thread.join(8)
        t["caller_returned"] = time.monotonic()
        assert not thread.is_alive()
        child_pid = created[0]["pid"] if created else None
        t0 = time.monotonic()
        confirmed = session.terminate()
        t["terminated"] = time.monotonic()
        after = {
            "caller_errors": errors,
            "child_registered": child_pid is not None,
            "child_pid": child_pid,
            "child_alive_after": _pid_alive(child_pid),
            "termination_confirmed": confirmed,
            "physical_liveness": session.physical_liveness(),
            "startup_s": session.startup_s,
            "cancel_return_s": session.cancel_return_s,
            "termination_s": session.termination_s,
            "lease_written": session._lease_written,
        }
        print(json.dumps({"after": after}, sort_keys=True))
        assert after["child_registered"], after
        assert not after["child_alive_after"], after
        assert confirmed
        assert after["physical_liveness"] == "dead"
        assert t["popen_entered"] >= t["enter"]
        assert t["cancel_returned"] >= t["cancel_start"]
        assert t["caller_returned"] >= t["cancel_returned"]
        assert t["terminated"] >= t0
        assert session.termination_s >= 0
        assert session.cancel_return_s <= (t["caller_returned"] - t["enter"]) + 0.05
        if os.name == "nt":
            freed = _competitor_mutex(str(env.vault), timeout=0.5)
            assert freed["acquired"], freed
    finally:
        resume.set()
        thread.join(8)
        session = env.mirror._vault_io
        if session is not None:
            session.terminate()
        for item in created:
            proc = item.get("proc")
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(2)
                except OSError:
                    pass
        env.mirror._vault_io = None


def test_launch_failure_after_cancel_releases_without_untracked_child(env, monkeypatch):
    entered = threading.Event()
    resume = threading.Event()
    original_popen = mirror.subprocess.Popen
    created = []
    errors = []
    t = {}

    def failing_popen(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        if not _is_vault_worker(cmd):
            return original_popen(*args, **kwargs)
        entered.set()
        assert resume.wait(5), "failing popen was not released"
        raise OSError("injected popen failure")

    monkeypatch.setattr(mirror.subprocess, "Popen", failing_popen)

    def caller() -> None:
        try:
            with env.mirror._exclusive(timeout=2.0):
                env.mirror._start_vault_io(str(env.vault))
        except (OSError, mirror._LockTimeout) as exc:
            errors.append({"type": type(exc).__name__, "message": str(exc)})

    thread = threading.Thread(target=caller)
    t["enter"] = time.monotonic()
    thread.start()
    try:
        assert entered.wait(5)
        session = env.mirror._vault_io
        assert session is not None and session.proc is None
        t["cancel_start"] = time.monotonic()
        env.mirror._kill_vault_io(session)
        t["cancel_returned"] = time.monotonic()
        assert session._dead
        assert session in mirror._retained_sessions
        resume.set()
        thread.join(8)
        t["caller_returned"] = time.monotonic()
        assert not thread.is_alive()
        observed = {
            "caller_errors": errors,
            "children_created": len(created),
            "launcher_pid": session.pid,
            "writer_pid": session.writer_pid,
            "physical_liveness": session.physical_liveness(),
            "mirror_retained": env.mirror._vault_io is session,
            "global_retained": session in mirror._retained_sessions,
            "owner_held": bool(session._exclusion_owner and session._exclusion_owner.held),
            "cancel_return_s": session.cancel_return_s,
            "termination_s": session.termination_s,
            "lease_written": session._lease_written,
        }
        print(json.dumps(observed, sort_keys=True))
        assert observed["children_created"] == 0, observed
        assert observed["launcher_pid"] is None
        assert observed["physical_liveness"] == "dead"
        assert not observed["global_retained"]
        assert not observed["owner_held"]
        assert errors
        assert t["cancel_returned"] - t["cancel_start"] < 0.5
        assert t["caller_returned"] >= t["cancel_returned"]
        if os.name == "nt":
            freed = _competitor_mutex(str(env.vault), timeout=0.5)
            assert freed["acquired"], freed
    finally:
        resume.set()
        thread.join(8)
        if env.mirror._vault_io is not None:
            env.mirror._vault_io.terminate()
        env.mirror._vault_io = None


def test_originating_helper_succeeds_foreign_helper_refuses(env):
    path = env.mirror._intent_path("owned-intent")
    path.parent.mkdir(parents=True, exist_ok=True)
    original = b'{"owner":"original"}'
    path.write_bytes(original)
    env.mirror._start_vault_io(str(env.vault))
    session = env.mirror._vault_io
    try:
        env.mirror._atomic_local(path, original)
        assert path.read_bytes() == original
        origin_again = b'{"owner":"origin-again"}'
        env.mirror._atomic_local(path, origin_again)
        assert path.read_bytes() == origin_again
        foreign = {"returned": None}

        def foreign_caller() -> None:
            foreign["thread"] = threading.get_ident()
            foreign["context_session"] = getattr(mirror._IO_CTX, "session", None) is not None
            foreign["context_owner"] = getattr(mirror._EXCL_CTX, "owner", None) is not None
            try:
                env.mirror._atomic_local(path, b'{"owner":"foreign"}')
                foreign["returned"] = "success"
            except (OSError, mirror._LockTimeout) as exc:
                foreign["returned"] = type(exc).__name__
                foreign["error"] = str(exc)

        thread = threading.Thread(target=foreign_caller)
        thread.start()
        thread.join(12)
        assert not thread.is_alive()
        after = path.read_bytes() if path.exists() else None
        observed = {
            "origin_thread": threading.get_ident(),
            "foreign": foreign,
            "after": after.decode() if after is not None else None,
            "original_writer_alive": session.alive,
            "writer_pid": session.writer_pid,
        }
        print(json.dumps(observed, sort_keys=True))
        assert after == origin_again, observed
        assert foreign["returned"] != "success", observed
        assert session.alive
        env.mirror._unlink_intent_file(path)
        assert not path.exists()
        path.write_bytes(original)
        unlink_foreign = {"returned": None}

        def unlink_caller() -> None:
            try:
                env.mirror._unlink_intent_file(path)
                unlink_foreign["returned"] = "success"
            except (OSError, mirror._LockTimeout) as exc:
                unlink_foreign["returned"] = type(exc).__name__

        thread = threading.Thread(target=unlink_caller)
        thread.start()
        thread.join(12)
        assert not thread.is_alive()
        assert path.exists() and path.read_bytes() == original
        assert unlink_foreign["returned"] != "success"
        assert session.alive
    finally:
        assert session.terminate()
        env.mirror._vault_io = None


@pytest.mark.skipif(os.name != "nt", reason="shared Windows admission gate")
def test_lease_helper_validates_dest_without_parent_realpath(env, tmp_path_factory):
    original = str(env.vault)
    other = str(tmp_path_factory.mktemp("o"))
    alias = str(env.vault.parent / "j")
    _make_junction(original, alias)
    session = mirror._VaultIoSession.start(original)
    prev_session = getattr(mirror._IO_CTX, "session", None)
    prev_token = getattr(mirror._IO_CTX, "token", None)
    reused = []
    try:
        mirror._IO_CTX.session = session
        mirror._IO_CTX.token = session.token
        assert Path(original).samefile(alias)
        assert mirror._canonical_dest(original) != mirror._canonical_dest(alias)
        assert mirror._canonical_dest(original) != mirror._canonical_dest(other)
        assert mirror._admission_gate_key(original) == mirror._admission_gate_key(alias)
        assert mirror._admission_gate_key(original) == mirror._admission_gate_key(other)

        def capture(sess):
            reused.append(sess)
            return sess.dest

        matched = mirror._with_isolated_lease_session(original, capture)
        assert matched == original
        assert reused == [session]
        with pytest.raises(OSError):
            mirror._with_isolated_lease_session(alias, capture)
        with pytest.raises(OSError):
            mirror._with_isolated_lease_session(other, capture)
        assert reused == [session]
        assert session.alive
        assert session.dest == original
        observed = {
            "original": original,
            "alias": alias,
            "other": other,
            "samefile_alias": True,
            "canonical_alias_differs": True,
            "gate_key_shared": True,
            "reused_count": len(reused),
            "session_alive": session.alive,
        }
        print(json.dumps(observed, sort_keys=True))
    finally:
        mirror._IO_CTX.session = prev_session
        mirror._IO_CTX.token = prev_token
        assert session.terminate()
        freed = _competitor_mutex(original, timeout=0.5)
        assert freed["acquired"], freed
