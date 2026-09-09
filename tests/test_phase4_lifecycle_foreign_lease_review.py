"""An old dead operation cannot certify absence of a new live lease owner."""
import threading
import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env


def test_dead_bound_context_still_blocks_an_actual_foreign_lease(env):
    env.mirror._start_vault_io(str(env.vault))
    original = env.mirror._vault_io
    terminated = []
    terminator = threading.Thread(target=lambda: terminated.append(original.terminate()))
    terminator.start()
    terminator.join(8)
    assert not terminator.is_alive() and terminated == [True]
    assert getattr(mirror._IO_CTX, 'session', None) is original
    ready, release = threading.Event(), threading.Event()
    state = {}

    def later_owner():
        session = None
        try:
            session = mirror._VaultIoSession.start(str(env.vault))
            session.claim_lease()
            state['session'] = session
            ready.set()
            release.wait(10)
        except BaseException as exc:
            state['error'] = repr(exc)
            ready.set()
        finally:
            if session is not None:
                state['terminated'] = session.terminate()

    thread = threading.Thread(target=later_owner)
    thread.start()
    try:
        assert ready.wait(8), state
        assert 'error' not in state, state
        assert state['session'].alive
        assert mirror._read_dest_lease(str(env.vault)) == 'unavailable'
        assert mirror._foreign_vault_worker_alive(str(env.vault)), state
    finally:
        release.set()
        thread.join(8)
        assert not thread.is_alive() and state.get('terminated') is True, state
        env.mirror._stop_vault_io(original)
