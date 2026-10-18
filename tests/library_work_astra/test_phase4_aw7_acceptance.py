"""AW-7 draft review: timeout must stop the destination lease mutation too."""
import threading
import time

import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env, export


def test_aw7_timed_out_lease_writer_cannot_mutate_destination_after_return(env, monkeypatch):
    export(env)
    env.mirror._clock = time.monotonic
    entered, release, completed = threading.Event(), threading.Event(), threading.Event()
    original_write = mirror._write_dest_lease
    lease_path = mirror._dest_lease_path(str(env.vault))

    def paused_write(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(8)
            return original_write(*args, **kwargs)
        finally:
            completed.set()

    monkeypatch.setattr(mirror, "_write_dest_lease", paused_write)
    try:
        result = env.mirror.resync(budget_s=0.1)
        assert entered.is_set(), "The real lease mutation boundary was not entered"
        assert not result["ok"]
        before = lease_path.read_bytes() if lease_path.is_file() else None
    finally:
        release.set()
        assert completed.wait(5), "The held lease operation did not finish"
    after = lease_path.read_bytes() if lease_path.is_file() else None
    assert after == before, "The timed-out parent wrote the destination lease after returning"
