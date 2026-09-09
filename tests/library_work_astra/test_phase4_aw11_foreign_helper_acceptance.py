"""Foreign helper calls cannot adopt a Mirror object's admitted mutator."""
import json
import threading

import pytest
import library_mirror as m
from tests.library_work_astra.test_phase4_aw_acceptance import env


@pytest.mark.parametrize("operation", ["put", "unlink"])
def test_foreign_thread_cannot_adopt_current_mirror_session(env, operation):
    path = env.mirror._intent_path("owned-intent")
    path.parent.mkdir(parents=True, exist_ok=True)
    original = b'{"owner":"original"}'
    path.write_bytes(original)
    observations = {"operation": operation}
    env.mirror._start_vault_io(str(env.vault))
    session = env.mirror._vault_io

    def foreign_caller():
        observations["foreign_thread"] = threading.get_ident()
        observations["context_session"] = getattr(m._IO_CTX, "session", None) is not None
        observations["context_owner"] = getattr(m._EXCL_CTX, "owner", None) is not None
        try:
            if operation == "put":
                env.mirror._atomic_local(path, b'{"owner":"foreign"}')
            else:
                env.mirror._unlink_intent_file(path)
            observations["returned"] = "success"
        except (OSError, m._LockTimeout) as exc:
            observations["returned"] = type(exc).__name__
            observations["error"] = str(exc)

    thread = threading.Thread(target=foreign_caller)
    try:
        observations["origin_thread"] = threading.get_ident()
        observations["writer_pid"] = session.writer_pid
        thread.start()
        thread.join(12)
        assert not thread.is_alive(), "foreign helper did not return within its admission bound"
        after = path.read_bytes() if path.exists() else None
        observations["after"] = after.decode() if after is not None else None
        observations["original_writer_alive"] = session.alive
        print(json.dumps(observations, sort_keys=True))
        assert after == original, observations
    finally:
        assert session.terminate(), "task-owned writer death was not confirmed"
        thread.join(3)
        env.mirror._vault_io = None
