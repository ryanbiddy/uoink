from types import SimpleNamespace
import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env

def test_unconfirmed_child_death_is_not_forgotten(env,monkeypatch):
    session=mirror._VaultIoSession()
    session.proc=SimpleNamespace(poll=lambda:None)
    session.dest=str(env.vault)
    env.mirror._vault_io=session
    def unable_to_confirm():
        session._dead=True
        return False
    monkeypatch.setattr(session,"terminate",unable_to_confirm)
    env.mirror._kill_vault_io(session)
    assert session.proc.poll() is None
    assert env.mirror._vault_io is session, "Mirror forgot a child whose death was not confirmed"
