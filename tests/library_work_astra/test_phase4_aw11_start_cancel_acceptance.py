"""Controlled cancellation after Mirror retains a session, before Popen."""
import json
import threading

import library_mirror as m
from tests.library_work_astra.test_phase4_aw_acceptance import env


def test_cancelled_start_does_not_leave_a_live_unretained_child(env, monkeypatch):
    entered = threading.Event()
    resume = threading.Event()
    sessions = []
    errors = []
    original_launch = m._VaultIoSession.launch

    def delayed_launch(session):
        sessions.append(session)
        entered.set()
        assert resume.wait(5), "test launcher was not released"
        return original_launch(session)

    monkeypatch.setattr(m._VaultIoSession, "launch", delayed_launch)

    def caller():
        try:
            with env.mirror._exclusive(timeout=0.5):
                env.mirror._start_vault_io(str(env.vault))
        except (OSError, m._LockTimeout) as exc:
            errors.append({"type": type(exc).__name__, "message": str(exc)})

    thread = threading.Thread(target=caller)
    thread.start()
    try:
        assert entered.wait(5)
        session = sessions[0]
        assert env.mirror._vault_io is session and session.proc is None
        env.mirror._kill_vault_io(session)
        resume.set()
        thread.join(8)
        assert not thread.is_alive()
        owner = session._exclusion_owner
        observed = {
            "caller_errors": errors,
            "launcher_pid": session.pid,
            "writer_pid": session.writer_pid,
            "physical_liveness": session.physical_liveness(),
            "admitted_alive": session.alive,
            "cancelled_admission": session._dead,
            "mirror_retained": env.mirror._vault_io is session,
            "global_retained": session in m._retained_sessions,
            "owner_held": bool(owner and owner.held),
            "lease_written": session._lease_written,
            "content_mutation_commands": 0,
        }
        print(json.dumps(observed, sort_keys=True))
        retained = observed["mirror_retained"] and observed["global_retained"] and observed["owner_held"]
        assert not session.physically_alive() or retained, observed
    finally:
        resume.set()
        thread.join(8)
        for session in sessions:
            assert session.terminate(), "owned child cleanup was not confirmed"
        env.mirror._vault_io = None
