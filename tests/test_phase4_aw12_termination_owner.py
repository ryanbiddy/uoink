"""Concurrent cancellation has one native-job cleanup owner."""
import json
import threading
import time

import library_mirror as m
from tests.library_work_astra.test_phase4_aw_acceptance import env


def test_concurrent_termination_does_not_close_a_job_twice(env, monkeypatch):
    session = m._VaultIoSession.start(str(env.vault))
    job = session.job
    entered = threading.Event()
    resume = threading.Event()
    results = []
    closes = []
    original_terminate = m._win_terminate_job
    original_close = m._win_close_handle

    def paused_terminate(handle):
        if handle == job:
            entered.set()
            assert resume.wait(5)
        return original_terminate(handle)

    def counted_close(handle):
        if handle == job:
            closes.append(handle)
        return original_close(handle)

    monkeypatch.setattr(m, "_win_terminate_job", paused_terminate)
    monkeypatch.setattr(m, "_win_close_handle", counted_close)
    first = threading.Thread(target=lambda: results.append(session.terminate()))
    first.start()
    try:
        assert entered.wait(3)
        started = time.monotonic()
        second = session.terminate()
        elapsed = time.monotonic() - started
        retained = session in m._retained_sessions
        held = session._exclusion_owner.held
        resume.set()
        first.join(5)
        observed = {
            "second_confirmed": second, "second_return_s": elapsed,
            "retained_during_first_termination": retained,
            "owner_held_during_first_termination": held,
            "first_results": results, "job_close_count": len(closes),
            "final_liveness": session.physical_liveness(),
        }
        print(json.dumps(observed, sort_keys=True))
        assert second is False and elapsed < 0.25, observed
        assert retained and held and results == [True], observed
        assert closes == [job] and not session.physically_alive(), observed
    finally:
        resume.set()
        first.join(5)
        assert session.terminate()
