"""Confirmed child death does not authorize a cancelled plan's later lease write."""
import threading
import pytest
import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env


def test_cancelled_origin_plan_cannot_start_a_later_lease_writer(env, monkeypatch):
    env.mirror._start_vault_io(str(env.vault))
    session = env.mirror._vault_io
    cancelled = threading.Event()
    plan = {'io': session, 'cancelled': cancelled, 'op_id': 19}
    try:
        with monkeypatch.context() as bound:
            bound.setattr(mirror._IO_CTX, 'plan', plan, raising=False)
            cancelled.set()
            assert session.terminate()
            assert session.physical_liveness() == 'dead'
            with pytest.raises(OSError):
                mirror._write_dest_lease(str(env.vault), {'owner': 'cancelled-origin'})
    finally:
        env.mirror._stop_vault_io(session)
        assert session.terminate()
