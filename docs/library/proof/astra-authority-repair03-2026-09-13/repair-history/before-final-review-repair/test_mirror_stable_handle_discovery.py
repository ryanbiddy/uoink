"""Actual handle-discovery paths against an inert Windows lifetime model."""
import ctypes
import gc
import weakref

import pytest

import library_mirror as m


class Process:
    def __init__(self, pid, born, parent=None):
        self.pid, self.born, self.parent = pid, born, parent
        self.exit = None
        self.stdin = self.stdout = self.stderr = None

    def poll(self):
        return self.exit

    def kill(self):
        self.exit = 0

    def wait(self, timeout=None):
        return self.exit


class Kernel:
    def __init__(self):
        self.processes = {}
        self.handles = {}
        self.next = 100
        self.effects = []
        self.before_open = None
        self.snapshot_hook = None
        self.state_lock = None

    def __getattr__(self, name):
        raise AssertionError("Unmocked Windows API: " + name)

    def pin(self, proc):
        self.next += 1
        self.handles[self.next] = proc
        return self.next

    def check_unlocked(self):
        if self.state_lock is not None:
            assert not self.state_lock.locked(), "Native call holds cancellation lock"

    def OpenProcess(self, access, inherit, pid):
        self.check_unlocked()
        if self.before_open is not None:
            self.before_open(pid)
        assert pid in self.processes
        handle = self.pin(self.processes[pid])
        self.effects.append(("open", pid, handle))
        return handle

    def GetProcessTimes(self, handle, creation, exit_, kernel, user):
        self.check_unlocked()
        value = self.handles[handle].born
        creation._obj.dwLowDateTime = value & 0xFFFFFFFF
        creation._obj.dwHighDateTime = value >> 32
        return 1

    def GetExitCodeProcess(self, handle, ptr):
        self.check_unlocked()
        proc = self.handles[handle]
        ptr._obj.value = m._STILL_ACTIVE if proc.exit is None else proc.exit
        return 1

    def CloseHandle(self, handle):
        self.check_unlocked()
        assert handle in self.handles, "Double close or foreign handle"
        self.effects.append(("close", handle))
        del self.handles[handle]
        return 1

    def AssignProcessToJobObject(self, job, handle):
        self.check_unlocked()
        self.effects.append(("assign", job, self.handles[handle]))
        return 1

    def TerminateProcess(self, handle, code):
        self.check_unlocked()
        proc = self.handles[handle]
        self.effects.append(("terminate", proc))
        proc.exit = code
        return 1

    def replace(self, old, replacement):
        # Windows keeps the old PID reserved until its last process handle
        # closes. A test must not invent replacement while it is pinned.
        if any(proc is old for proc in self.handles.values()):
            self.effects.append(("replacement_refused", old.pid))
            return False
        self.processes[old.pid] = replacement
        return True

    def snapshot(self, parent):
        self.check_unlocked()
        if self.snapshot_hook is not None:
            self.snapshot_hook(parent)
        return [
            {"pid": p.pid, "ppid": parent, "exe": "python.exe"}
            for p in self.processes.values() if p.parent == parent and p.exit is None
        ]


@pytest.fixture
def native(monkeypatch):
    assert m.os.name == "nt"
    k = Kernel()
    base = m._FILETIME_EPOCH_OFFSET_100NS + 1_000_000 * 10000
    parent = Process(70001, base + 8000)
    child = Process(80002, base + 9000, parent.pid)
    k.processes = {parent.pid: parent, child.pid: child}
    parent._handle = k.pin(parent)
    s = m._VaultIoSession()
    s.proc = parent
    s.created_ms = 1_000_000
    k.state_lock = s._state_lock
    monkeypatch.setattr(m, "_kernel32", lambda: k)
    monkeypatch.setattr(m, "_windows_process_children", k.snapshot)
    monkeypatch.setattr(m, "_drop_retained_session", lambda owned: None)
    monkeypatch.setattr(m, "_unbind_dead_session_from_this_thread", lambda *a, **kw: None)
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **kw: pytest.fail("Real Popen forbidden"))
    return s, k, parent, child


def test_child_older_within_same_millisecond_is_refused(native):
    s, k, parent, child = native
    child.born = parent.born - 1
    assert (child.born // 10000) == (parent.born // 10000)
    assert child.pid not in s.owned_pids()
    assert child.pid not in s._owned_handles
    assert not any(p is child for p in k.handles.values())


def test_foreign_replacement_before_child_open_fails_final_relationship(native):
    s, k, parent, child = native
    foreign = Process(child.pid, child.born, 99001)

    def replace_before_open(pid):
        if pid == child.pid:
            k.before_open = None
            child.exit = 0
            assert k.replace(child, foreign)

    k.before_open = replace_before_open
    assert child.pid not in s.owned_pids()
    assert child.pid not in s._owned_handles
    assert not any(p is foreign for p in k.handles.values())


def test_pinned_child_cannot_be_replaced_before_relationship_or_mutation(native):
    s, k, parent, child = native
    snapshots = []

    def after_open(parent_pid):
        snapshots.append(parent_pid)
        if len(snapshots) == 2:
            replacement = Process(child.pid, child.born, 99001)
            assert not k.replace(child, replacement)

    k.snapshot_hook = after_open
    assert child.pid in s.owned_pids()
    before_opens = len([effect for effect in k.effects if effect[0] == "open"])
    assert s._assign_owned_handle(444, child.pid, 1_000_000)
    assert s._terminate_owned_handle(child.pid)
    assert ("assign", 444, child) in k.effects
    assert ("terminate", child) in k.effects
    assert len([effect for effect in k.effects if effect[0] == "open"]) == before_opens


def test_borrowed_handle_keeps_owner_until_last_user_finishes(monkeypatch):
    class Owner:
        pass
    owner = Owner()
    reference = weakref.ref(owner)
    closed = []
    monkeypatch.setattr(m, "_win_close_handle", lambda h: closed.append(h))
    retained = m._CountedNativeHandle(owns_close=False)
    retained.set_handle(123, owner=owner)
    assert retained.acquire() == 123
    retained.request_close()
    del owner
    gc.collect()
    assert reference() is not None
    retained.release()
    gc.collect()
    assert reference() is None
    assert closed == []


def test_cancellation_during_discovery_defers_cleanup_without_losing_child(native):
    s, k, parent, child = native
    results = []

    def cancel(parent_pid):
        k.snapshot_hook = None
        results.append(s.terminate())
        assert s._discovery_users == 1
        assert not s._termination_lock.locked()

    k.snapshot_hook = cancel
    s.owned_pids()
    assert results == [False]
    assert s._discovery_users == 0
    assert child.exit is not None
    assert ("terminate", child) in k.effects
    assert s.proc is None
    assert s._owned_handles == {}
