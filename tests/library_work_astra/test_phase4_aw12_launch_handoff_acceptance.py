"""Prepared cancellation and job ownership during the launch handoff."""
import json
import threading
import time

import pytest
import library_mirror as m
from tests.library_work_astra.test_phase4_aw_acceptance import env
from tests.test_phase4_av5m4b5_lifetime import _competitor_mutex


def test_cancelled_prepare_releases_without_requiring_a_future_launch(env):
    session = m._VaultIoSession.prepare(str(env.vault))
    try:
        started = time.monotonic()
        confirmed = session.terminate()
        observed = {
            "termination_confirmed": confirmed,
            "cancel_return_s": time.monotonic() - started,
            "physical_liveness": session.physical_liveness(),
            "launch_open": m._session_launch_open(session),
            "global_retained": session in m._retained_sessions,
            "owner_held": bool(session._exclusion_owner and session._exclusion_owner.held),
        }
        observed["competitor"] = _competitor_mutex(str(env.vault), timeout=0.3)
        print(json.dumps(observed, sort_keys=True))
        assert confirmed and observed["competitor"]["acquired"], observed
        with pytest.raises(OSError):
            session.launch()
        assert session.proc is None
    finally:
        # Old bytes retain a prepared cancelled session until launch refuses.
        try:
            session.launch()
        except OSError:
            pass
        assert session.terminate()


def test_cancel_cannot_close_job_during_launch_assignment(env, monkeypatch):
    entered = threading.Event()
    resume = threading.Event()
    original_assign = m._win_assign_job
    original_close = m._win_close_handle
    handles = []
    closed_early = []
    errors = []

    def paused_assignment(job, proc):
        handles.append(job)
        entered.set()
        assert resume.wait(6)
        if closed_early:
            return False  # Do not issue a kernel call with a known stale handle.
        return original_assign(job, proc)

    def observe_close(handle):
        if handles and handle == handles[0] and not resume.is_set():
            closed_early.append(handle)
        return original_close(handle)

    monkeypatch.setattr(m, "_win_assign_job", paused_assignment)
    monkeypatch.setattr(m, "_win_close_handle", observe_close)

    def caller():
        try:
            env.mirror._start_vault_io(str(env.vault))
        except OSError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=caller)
    thread.start()
    session = None
    try:
        assert entered.wait(5)
        session = env.mirror._vault_io
        assert session is not None and session.proc is not None
        launcher_pid = session.pid
        started = time.monotonic()
        confirmed = session.terminate()
        observed = {
            "launcher_pid": launcher_pid,
            "cancel_return_s": time.monotonic() - started,
            "termination_confirmed_before_handoff": confirmed,
            "job_closed_before_launcher_resumed": bool(closed_early),
            "retained_before_handoff": session in m._retained_sessions,
            "owner_held_before_handoff": bool(session._exclusion_owner and session._exclusion_owner.held),
            "actual_stale_handle_kernel_call": False,
        }
        resume.set()
        thread.join(8)
        observed["caller_errors"] = errors
        observed["caller_returned"] = not thread.is_alive()
        observed["final_physical_liveness"] = session.physical_liveness()
        print(json.dumps(observed, sort_keys=True))
        assert not closed_early, observed
        assert not thread.is_alive() and not session.physically_alive(), observed
    finally:
        resume.set()
        thread.join(8)
        if session is not None:
            assert session.terminate(), "task-owned child cleanup was not confirmed"
        env.mirror._vault_io = None
