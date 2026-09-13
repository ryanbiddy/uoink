"""Unexecuted review proposals for the unfinished a5e7ba0d authority patch.

All native/process effects fail closed unless an individual probe replaces
them with an explicit inert implementation. No prepare() or writer gate runs.
"""
from __future__ import annotations

import io
import json
import threading
from types import SimpleNamespace

import pytest

import library_mirror as mirror


LAUNCHER = 71001
WRITER = 81002
LAUNCHER_HANDLE = 171001
WRITER_HANDLE = 181002
JOB_HANDLE = 199999
LAUNCHER_CREATED = 1_000_000
WRITER_CREATED = 1_100_000


def _unmocked(*args, **kwargs):
    raise AssertionError("Unmocked native/process operation in inert review probe")


class StrictKernel:
    def __init__(self):
        self.assignments = []
        self.closed = []
        self.opened = []
        self.handles = {LAUNCHER: LAUNCHER_HANDLE, WRITER: WRITER_HANDLE}

    def __getattr__(self, name):
        raise AssertionError(f"Unmocked kernel method: {name}")

    def OpenProcess(self, access, inherit, pid):
        if pid not in self.handles:
            raise AssertionError(f"Unconfigured inert process PID: {pid}")
        self.opened.append((access, inherit, pid))
        return self.handles[pid]

    def AssignProcessToJobObject(self, job, handle):
        assert job == JOB_HANDLE
        assert handle in (LAUNCHER_HANDLE, WRITER_HANDLE)
        self.assignments.append((job, handle))
        return 1

    def CloseHandle(self, handle):
        assert handle in (LAUNCHER_HANDLE, WRITER_HANDLE, JOB_HANDLE)
        self.closed.append(handle)
        return 1


@pytest.fixture(autouse=True)
def inert_native_boundary(monkeypatch):
    # These probes target the native Windows implementation. Changing os.name
    # globally would also change pytest/pathlib behavior and hide fixture bugs.
    assert mirror.os.name == "nt", "Run through the guarded native Windows verifier"
    kernel = StrictKernel()
    monkeypatch.setattr(mirror, "_kernel32", lambda: kernel)
    monkeypatch.setattr(mirror.subprocess, "Popen", _unmocked)
    for name in (
        "_windows_process_created_ms", "_process_created_ms",
        "_windows_process_children", "_process_liveness",
        "_win_create_kill_job", "_win_terminate_job", "_win_terminate_pid",
        "_win_terminate_retained_handle", "_win_acquire_dest_mutex_result",
        "_win_release_dest_mutex",
    ):
        if hasattr(mirror, name):
            monkeypatch.setattr(mirror, name, _unmocked)
    monkeypatch.setattr(mirror.os, "kill", _unmocked)
    if hasattr(mirror.os, "killpg"):
        monkeypatch.setattr(mirror.os, "killpg", _unmocked)
    return kernel


def test_original_popen_handle_creation_positive_control(monkeypatch):
    proc = SimpleNamespace(pid=LAUNCHER, _handle=LAUNCHER_HANDLE)
    monkeypatch.setattr(
        mirror, "_windows_process_created_ms",
        lambda handle: LAUNCHER_CREATED if handle == LAUNCHER_HANDLE else _unmocked(),
    )
    # The autouse raw-PID trap stays armed.
    assert mirror._creation_from_popen(proc) == LAUNCHER_CREATED


class InertPopen:
    def __init__(self):
        self.pid = LAUNCHER
        self._handle = LAUNCHER_HANDLE
        self.returncode = None
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()
        self.stderr = None
        self.kill_calls = 0

    def poll(self):
        return self.returncode

    def kill(self):
        self.kill_calls += 1
        self.returncode = 0

    def wait(self, timeout=None):
        if self.returncode is None:
            raise mirror.subprocess.TimeoutExpired("inert writer", timeout)
        return self.returncode


def _inert_launch(monkeypatch, kernel, *, ready_pid, legitimate_writer=False):
    proc = InertPopen()
    state = SimpleNamespace(proc=proc, alive=True, popen_calls=0, raw_queries=[], mutations=[])
    session = mirror._VaultIoSession()
    session.dest = r"C:\inert\mirror-authority-review02"
    session.token = "inert-review-token"
    session._launching = True

    def fake_popen(*args, **kwargs):
        state.popen_calls += 1
        return proc

    def raw_created(pid):
        state.raw_queries.append(pid)
        if pid == LAUNCHER:
            return LAUNCHER_CREATED
        if pid == WRITER:
            return WRITER_CREATED
        return _unmocked()

    def handle_created(handle):
        if handle == LAUNCHER_HANDLE:
            return LAUNCHER_CREATED
        if handle == WRITER_HANDLE:
            return WRITER_CREATED
        return _unmocked()

    def children(parent):
        assert parent in (LAUNCHER, WRITER)
        if legitimate_writer and parent == LAUNCHER:
            return [{"pid": WRITER, "ppid": LAUNCHER, "exe": "python.exe"}]
        return []

    monkeypatch.setattr(mirror.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(mirror, "_win_create_kill_job", lambda: JOB_HANDLE)
    monkeypatch.setattr(mirror, "_windows_process_created_ms", handle_created)
    monkeypatch.setattr(mirror, "_process_created_ms", raw_created)
    monkeypatch.setattr(mirror, "_windows_process_children", children)
    monkeypatch.setattr(
        mirror, "_process_liveness",
        lambda pid, created=None, **kwargs: "alive" if state.alive else "dead",
    )
    monkeypatch.setattr(
        session, "_readline",
        lambda timeout=None: json.dumps({"ready": True, "pid": ready_pid}).encode("ascii"),
    )
    # These cleanup callbacks must never reach a real exclusion owner/session.
    monkeypatch.setattr(mirror, "_drop_retained_session", lambda owned: None)
    monkeypatch.setattr(mirror, "_unbind_dead_session_from_this_thread", lambda *a, **kw: None)

    def finish_job(job):
        assert job == JOB_HANDLE
        state.mutations.append(("job", job))
        state.alive = False
        proc.returncode = 0

    def finish_pid(pid, created=None):
        assert pid in (LAUNCHER, WRITER)
        state.mutations.append(("pid", pid, created))
        return True

    def finish_handle(handle, created=None):
        assert handle in (LAUNCHER_HANDLE, WRITER_HANDLE)
        state.mutations.append(("handle", handle, created))
        return True

    monkeypatch.setattr(mirror, "_win_terminate_job", finish_job)
    monkeypatch.setattr(mirror, "_win_terminate_pid", finish_pid)
    if hasattr(mirror, "_win_terminate_retained_handle"):
        monkeypatch.setattr(mirror, "_win_terminate_retained_handle", finish_handle)
    return session, state


def test_ready_pid_foreign_epoch_is_neither_registered_nor_assigned(
    monkeypatch, inert_native_boundary,
):
    """The old ready writer is gone; its current PID is outside the owned tree."""
    kernel = inert_native_boundary
    session, state = _inert_launch(monkeypatch, kernel, ready_pid=WRITER)
    refusal = None
    try:
        session.launch()
    except OSError as exc:
        # Refusing this unverified writer is a valid result. Kernel AssertionError
        # and unexpected exceptions remain failures, never accepted refusals.
        refusal = str(exc)
    observed = {
        "foreign_registered": WRITER in session._owned_created,
        "foreign_writer": session.writer_pid == WRITER,
        "foreign_assigned": (JOB_HANDLE, WRITER_HANDLE) in kernel.assignments,
    }
    assert state.popen_calls == 1
    assert (JOB_HANDLE, LAUNCHER_HANDLE) in kernel.assignments
    assert observed == {
        "foreign_registered": False, "foreign_writer": False, "foreign_assigned": False,
    }, {"observed": observed, "refusal": refusal, "assignments": kernel.assignments}


def test_ready_launcher_identity_positive_control(monkeypatch, inert_native_boundary):
    kernel = inert_native_boundary
    session, state = _inert_launch(monkeypatch, kernel, ready_pid=LAUNCHER)
    session.launch()
    assert state.popen_calls == 1
    assert session.writer_pid == LAUNCHER
    assert session.writer_created_ms == LAUNCHER_CREATED
    assert kernel.assignments == [(JOB_HANDLE, LAUNCHER_HANDLE)]
    assert state.raw_queries == [], "The same-PID writer already has original-handle identity"


def test_cancelled_launch_does_not_release_active_terminator_job_lease(
    monkeypatch, inert_native_boundary,
):
    """Exercise the real failed-acquire caller while terminate() uses its lease."""
    kernel = inert_native_boundary
    session, state = _inert_launch(
        monkeypatch, kernel, ready_pid=WRITER, legitimate_writer=True,
    )
    entered = threading.Event()
    proceed = threading.Event()
    thread_errors = []
    termination_results = []
    thread = None
    triggered = False
    original_created = session._created_for_pid

    def paused_job_termination(job):
        assert job == JOB_HANDLE
        state.mutations.append(("job_enter", job))
        entered.set()
        assert proceed.wait(3), "Review interleaving did not release its fake kernel pause"
        state.alive = False
        state.proc.returncode = 0
        state.mutations.append(("job_exit", job))

    def terminate_on_other_thread():
        try:
            termination_results.append(session.terminate())
        except BaseException as exc:
            thread_errors.append(repr(exc))

    def creation_at_assignment_boundary(pid):
        nonlocal thread, triggered
        if pid == WRITER and not triggered:
            triggered = True
            thread = threading.Thread(
                target=terminate_on_other_thread,
                name="inert-authority-review02-terminator",
                daemon=True,
            )
            thread.start()
            assert entered.wait(3), {"errors": thread_errors, "mutations": state.mutations}
        return original_created(pid)

    monkeypatch.setattr(mirror, "_win_terminate_job", paused_job_termination)
    monkeypatch.setattr(session, "_created_for_pid", creation_at_assignment_boundary)
    observation = None
    try:
        with pytest.raises(OSError, match="cancelled"):
            session.launch()
        observation = {
            "terminator_entered": entered.is_set(),
            "lease_in_use": session._job_lifetime.in_use,
            "job_closed_while_terminator_paused": JOB_HANDLE in kernel.closed,
        }
    finally:
        proceed.set()
        if thread is not None:
            thread.join(3)
    assert thread is not None and not thread.is_alive(), "Inert test thread did not finish"
    assert thread_errors == []
    assert termination_results == [True]
    assert observation == {
        "terminator_entered": True,
        "lease_in_use": True,
        "job_closed_while_terminator_paused": False,
    }
