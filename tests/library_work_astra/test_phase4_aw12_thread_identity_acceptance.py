"""Model recycled integer IDs without changing actual thread or writer objects."""
import json
import threading

import library_mirror as m
from tests.library_work_astra.test_phase4_aw_acceptance import env


def test_exited_origin_cannot_authorize_another_thread_by_recycled_integer_id(env, monkeypatch):
    ready = threading.Event()
    original_ids = []
    failures = []

    def origin():
        try:
            env.mirror._start_vault_io(str(env.vault))
            original_ids.append(threading.get_ident())
        except Exception as exc:
            failures.append(str(exc))
        finally:
            ready.set()

    caller = threading.Thread(target=origin)
    caller.start()
    assert ready.wait(5)
    caller.join(5)
    assert not caller.is_alive() and not failures
    session = env.mirror._vault_io
    assert session is not None and session.alive
    path = env.mirror._intent_path("original-owner")
    path.parent.mkdir(parents=True, exist_ok=True)
    original = b'{"owner":"original"}'
    path.write_bytes(original)

    class RecycledIdentity:
        def get_ident(self):
            return original_ids[0]

        def __getattr__(self, name):
            return getattr(threading, name)

    observed = {
        "allocator_reuse": "simulated at mirror.get_ident only",
        "origin_exited": not caller.is_alive(),
        "same_thread_object": caller is threading.current_thread(),
        "origin_integer_id": original_ids[0],
        "actual_current_integer_id": threading.get_ident(),
        "simulated_current_integer_id": original_ids[0],
        "writer_pid": session.writer_pid,
    }
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(m, "threading", RecycledIdentity())
            try:
                env.mirror._atomic_local(path, b'{"owner":"foreign"}')
                observed["returned"] = "success"
            except (OSError, m._LockTimeout) as exc:
                observed["returned"] = type(exc).__name__
                observed["error"] = str(exc)
        after = path.read_bytes() if path.exists() else None
        observed["after"] = after.decode() if after is not None else None
        print(json.dumps(observed, sort_keys=True))
        assert after == original, observed
    finally:
        assert session.terminate(), "task-owned writer cleanup was not confirmed"
        env.mirror._vault_io = None
