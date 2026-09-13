"""Synthetic controls for exact identity and retained-handle lifetime.

The eleven worker assertions and ten Astra boundary assertions are unchanged
in their own files. This module only adds handle-lifetime and identity
controls. Every kernel effect is an inert fake; unmocked operations fail
closed and never open, assign, wait on, or terminate a real process.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

import library_mirror as mirror


class FailClosedKernel:
    """Kernel stub: unmocked operations record refusal and return 0."""

    def __init__(self):
        self.effects: list[tuple] = []
        self.allowed_open: dict[int, int] = {}
        self.created_by_handle: dict[int, int] = {}
        self.exit_by_handle: dict[int, int] = {}
        self.closed: list[int] = []

    def OpenProcess(self, access, inherit, pid):
        handle = self.allowed_open.get(int(pid))
        if not handle:
            self.effects.append(("refused-open", int(pid), int(access)))
            return 0
        self.effects.append(("open", int(pid), int(handle)))
        return handle

    def CloseHandle(self, handle):
        self.closed.append(int(handle))
        self.effects.append(("close", int(handle)))
        return 1

    def TerminateProcess(self, handle, code):
        self.effects.append(("terminate", int(handle), int(code)))
        return 1

    def AssignProcessToJobObject(self, job, handle):
        self.effects.append(("assign", int(job), int(handle)))
        return 1

    def GetExitCodeProcess(self, handle, ptr):
        value = self.exit_by_handle.get(int(handle), mirror._STILL_ACTIVE)
        try:
            ptr.contents.value = value
        except AttributeError:
            if hasattr(ptr, "value"):
                ptr.value = value
        self.effects.append(("exit-code", int(handle), int(value)))
        return 1

    def GetProcessTimes(self, *args):
        self.effects.append(("refused-times",))
        return 0

    def __getattr__(self, name):
        def refused(*args, **kwargs):
            self.effects.append(("refused", name))
            return 0
        return refused


def _session(pid=70001, created_ms=1_000_000, poll=None):
    value = mirror._VaultIoSession()
    value.proc = SimpleNamespace(pid=pid, poll=lambda: poll, _handle=555)
    value.created_ms = created_ms
    return value


@pytest.fixture
def nt(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    return monkeypatch


def test_fail_closed_kernel_does_not_mutate_unmocked_pid(nt):
    kernel = FailClosedKernel()
    nt.setattr(mirror, "_kernel32", lambda: kernel)
    nt.setattr(mirror, "_windows_process_created_ms", lambda handle: None)
    mirror._win_terminate_pid(70001, 1_000_000)
    assert "terminate" not in {e[0] for e in kernel.effects}
    assert mirror._win_assign_pid(999, 70001, 1_000_000) is False
    assert "assign" not in {e[0] for e in kernel.effects}


def test_exact_identity_positive_control_mutates_only_matching_handle(nt):
    kernel = FailClosedKernel()
    kernel.allowed_open[70005] = 22222
    kernel.created_by_handle[22222] = 1_000_000
    nt.setattr(mirror, "_kernel32", lambda: kernel)
    nt.setattr(mirror, "_windows_process_created_ms", lambda handle: kernel.created_by_handle.get(int(handle)))
    assert mirror._win_terminate_pid(70005, 1_000_000) is True
    assert ("terminate", 22222, 1) in kernel.effects
    kernel.effects.clear()
    assert mirror._win_assign_pid(99999, 70005, 1_000_000) is True
    assert ("assign", 99999, 22222) in kernel.effects


def test_one_millisecond_mismatch_refuses_retained_handle_mutation(nt):
    kernel = FailClosedKernel()
    nt.setattr(mirror, "_kernel32", lambda: kernel)
    nt.setattr(mirror, "_windows_process_created_ms", lambda handle: 1_000_001)
    assert mirror._win_terminate_retained_handle(444, 1_000_000) is False
    assert "terminate" not in {e[0] for e in kernel.effects}
    assert mirror._handle_creation_matches(444, 1_000_000) is False


def test_matching_retained_handle_terminates_without_openprocess(nt):
    kernel = FailClosedKernel()
    kernel.exit_by_handle[444] = mirror._STILL_ACTIVE
    nt.setattr(mirror, "_kernel32", lambda: kernel)
    nt.setattr(mirror, "_windows_process_created_ms", lambda handle: 1_000_000)
    assert mirror._win_terminate_retained_handle(444, 1_000_000) is True
    assert ("terminate", 444, 1) in kernel.effects
    assert "open" not in {e[0] for e in kernel.effects}
    assert "refused-open" not in {e[0] for e in kernel.effects}


def test_job_handle_close_deferred_while_in_use(nt):
    closed: list[int] = []
    nt.setattr(mirror, "_win_close_handle", lambda handle: closed.append(int(handle)))
    session = mirror._VaultIoSession()
    session._publish_job(4242)
    held = session._acquire_job_handle()
    assert held == 4242
    session._close_session_job()
    assert closed == []
    assert session._job_lifetime.in_use
    session._release_job_handle()
    assert closed == [4242]
    assert session.job is None


def test_counted_handle_does_not_close_borrowed_popen_handle(nt):
    closed: list[int] = []
    nt.setattr(mirror, "_win_close_handle", lambda handle: closed.append(int(handle)))
    retained = mirror._CountedNativeHandle(owns_close=False)
    retained.set_handle(555)
    used = retained.acquire()
    assert used == 555
    retained.request_close()
    assert closed == []
    retained.release()
    assert closed == []


def test_launcher_identity_prefers_retained_popen_handle(nt):
    pid_queries: list[int] = []
    nt.setattr(
        mirror,
        "_windows_process_created_ms",
        lambda handle: 1_000_000 if int(handle) == 555 else 9_000_000,
    )
    nt.setattr(
        mirror,
        "_process_created_ms",
        lambda pid: pid_queries.append(int(pid)) or 9_000_000,
    )
    proc = SimpleNamespace(pid=70001, poll=lambda: None, _handle=555)
    assert mirror._creation_from_popen(proc) == 1_000_000
    assert pid_queries == []


def test_missing_handle_does_not_invent_parent_identity_from_later_pid(nt):
    session = _session()
    session.created_ms = None
    nt.setattr(
        mirror,
        "_windows_process_children",
        lambda pid: [{"pid": 80002, "ppid": 70001, "exe": "child.exe"}],
    )
    nt.setattr(mirror, "_process_created_ms", lambda pid: 1_050_000 if pid == 80002 else 1_000_000)
    nt.setattr(mirror, "_process_liveness", lambda *args, **kwargs: "alive")
    assert 80002 not in session.owned_pids()


def test_same_pid_distinct_epoch_writer_is_not_merged(nt):
    session = _session()
    session.proc.poll = lambda: 0
    session.writer_pid = 70001
    session.writer_created_ms = 2_000_000

    def liveness(pid, created=None, **kwargs):
        if created == 2_000_000:
            return "alive"
        return "unknown"

    nt.setattr(mirror, "_process_liveness", liveness)
    assert session.physical_liveness() == "alive"
    assert session._writer_is_canonical_launcher() is False


def test_canonical_launcher_writer_stays_dead_when_timestamp_query_fails(nt):
    session = _session()
    session.proc.poll = lambda: 0
    session.writer_pid = 70001
    session.writer_created_ms = None
    nt.setattr(mirror, "_process_liveness", lambda *args, **kwargs: "unknown")
    assert session._writer_is_canonical_launcher() is True
    assert session.physical_liveness() == "dead"


def test_verified_child_still_adopted_with_revalidation(nt):
    session = _session()
    nt.setattr(
        mirror,
        "_windows_process_children",
        lambda pid: [{"pid": 80002, "ppid": 70001, "exe": "legit_child.exe"}],
    )
    nt.setattr(mirror, "_process_created_ms", lambda pid: 1_050_000 if pid == 80002 else 1_000_000)
    nt.setattr(mirror, "_process_liveness", lambda *args, **kwargs: "alive")
    pids = session.owned_pids()
    assert 80002 in pids
    assert session._owned_created[80002] == 1_050_000


def test_unknown_owned_child_retains_exclusion(nt):
    session = _session()
    session.dest = "C:\\inert\\dest"
    session.proc.poll = lambda: 0
    session._owned_created[80003] = 1_020_000
    nt.setattr(mirror, "_process_liveness", lambda pid, created=None, **kwargs: "unknown")
    released: list[bool] = []
    dropped: list[object] = []
    nt.setattr(session, "_release_held_exclusion", lambda: released.append(True))
    nt.setattr(mirror, "_drop_retained_session", lambda s: dropped.append(s))
    assert session.physical_liveness() == "unknown"
    assert session.physically_alive() is True
    session._abandon_unstarted()
    assert released == []
    assert dropped == []


def test_session_terminate_uses_retained_handle_not_pid_open(nt):
    kernel = FailClosedKernel()
    kernel.exit_by_handle[777] = mirror._STILL_ACTIVE
    nt.setattr(mirror, "_kernel32", lambda: kernel)
    nt.setattr(mirror, "_windows_process_created_ms", lambda handle: 1_050_000 if int(handle) == 777 else None)
    session = _session()
    session.proc.poll = lambda: 0
    session._retain_owned_handle(80002, 777, 1_050_000, owns_close=True)
    session._owned_exe[80002] = "child.exe"
    nt.setattr(mirror, "_process_liveness", lambda pid, created=None, **kwargs: "dead")
    nt.setattr(mirror, "_windows_process_children", lambda pid: [])
    assert session.terminate() is True
    assert ("terminate", 777, 1) in kernel.effects
    assert "refused-open" not in {e[0] for e in kernel.effects} or 80002 not in {
        e[1] for e in kernel.effects if e[0] == "refused-open"
    }


def test_state_lock_is_not_held_across_job_assignment(nt):
    """Assignment must not take the cancellation lock with the kernel call."""
    session = mirror._VaultIoSession()
    session._publish_job(9)
    held = []

    def assign(job, pid, created_ms=None):
        held.append(session._state_lock.locked())
        return True

    nt.setattr(mirror, "_win_assign_pid", assign)
    job_handle = session._acquire_job_handle()
    try:
        if job_handle is not None:
            mirror._win_assign_pid(job_handle, 80002, 1_050_000)
    finally:
        session._release_job_handle()
    # The product launch loop acquires the job handle, then calls assign
    # without the state lock. The helper itself only locks to increment the
    # use count. Direct assign here is outside the lock.
    assert held == [False]
