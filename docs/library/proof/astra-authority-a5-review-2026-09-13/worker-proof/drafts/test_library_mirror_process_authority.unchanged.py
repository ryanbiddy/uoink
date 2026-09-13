"""Focused synthetic regressions for mirror process authority.

Tests assert bounded, safe process authority and lifecycle behavior.
All probes use inert PIDs and mocked kernel/process observations.
No real processes are opened, assigned, suspended, or terminated.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import library_mirror as mirror


class EffectRecorder:
    def __init__(self):
        self.terminated_handles: list[int] = []
        self.assigned_handles: list[tuple[int, int]] = []
        self.released_exclusion: list[bool] = []
        self.dropped_session: list[object] = []
        self.closed_handles: list[int] = []


def _mock_k32(recorder: EffectRecorder, handle: int = 11111):
    mock = MagicMock()
    mock.OpenProcess.return_value = handle
    mock.CloseHandle.side_effect = lambda h: recorder.closed_handles.append(h) or 1
    mock.TerminateProcess.side_effect = lambda h, c: recorder.terminated_handles.append(h) or 1
    mock.AssignProcessToJobObject.side_effect = lambda j, h: recorder.assigned_handles.append((j, h)) or 1
    
    # GetExitCodeProcess sets code to STILL_ACTIVE (0x103)
    def mock_exit_code(h, code_ptr):
        try:
            code_ptr.contents.value = mirror._STILL_ACTIVE
        except AttributeError:
            if hasattr(code_ptr, "value"):
                code_ptr.value = mirror._STILL_ACTIVE
        return 1

    mock.GetExitCodeProcess.side_effect = mock_exit_code
    return mock


def test_refuse_preexisting_orphan_child(monkeypatch):
    """Orphan created before parent must be refused adoption in owned_pids and _adopt_owned_tree."""
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(pid=70001, poll=lambda: None)
    session.created_ms = 1_000_000

    # Orphan created at T=500,000 (500s before launcher born)
    orphan = {"pid": 80002, "exe": "orphan.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda p: [orphan] if p == 70001 else [])
    
    def mock_created_ms(pid):
        if pid == 70001:
            return 1_000_000
        if pid == 80002:
            return 500_000
        return None

    monkeypatch.setattr(mirror, "_process_created_ms", mock_created_ms)
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, c=None: "alive")
    monkeypatch.setattr(os, "name", "nt")

    pids = session.owned_pids()
    assert 80002 not in pids, "Older orphan must not be adopted into owned_pids"
    assert not session.owns_pid(80002), "Older orphan must not be claimed by owns_pid"
    assert 80002 not in session._owned_created, "Older orphan must not enter _owned_created"

    # Writer fallback in _adopt_owned_tree must also refuse older orphan
    session2 = mirror._VaultIoSession()
    session2.proc = SimpleNamespace(pid=70001, poll=lambda: None)
    session2.created_ms = 1_000_000
    session2.writer_pid = None
    orphan_writer = {"pid": 80002, "exe": "python.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda p: [orphan_writer] if p == 70001 else [])
    session2._adopt_owned_tree()
    assert session2.writer_pid != 80002, "_adopt_owned_tree must not adopt older orphan as writer"


def test_refuse_children_of_exited_parent(monkeypatch):
    """Toolhelp children of an exited parent must not be enumerated or adopted."""
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(pid=70001, poll=lambda: 0)  # Launcher already exited
    session.created_ms = 1_000_000

    child = {"pid": 80002, "exe": "child.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda p: [child] if p == 70001 else [])
    monkeypatch.setattr(mirror, "_process_created_ms", lambda pid: 1_500_000 if pid == 80002 else 1_000_000)
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, c=None: "dead" if pid == 70001 else "alive")
    monkeypatch.setattr(os, "name", "nt")

    pids = session.owned_pids()
    assert 80002 not in pids, "Children of exited parent must not be adopted"
    assert not session.owns_pid(80002)
    assert 80002 not in session._owned_created

    # Writer fallback in _adopt_owned_tree must also refuse adoption when parent exited
    session2 = mirror._VaultIoSession()
    session2.proc = SimpleNamespace(pid=70001, poll=lambda: 0)
    session2.created_ms = 1_000_000
    session2.writer_pid = None
    child_writer = {"pid": 80002, "exe": "python.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda p: [child_writer] if p == 70001 else [])
    session2._adopt_owned_tree()
    assert session2.writer_pid != 80002, "_adopt_owned_tree must not adopt child when parent exited"


def test_refuse_children_of_recycled_parent(monkeypatch):
    """Toolhelp children of a recycled parent PID must be refused adoption."""
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(pid=70001, poll=lambda: None)
    session.created_ms = 1_000_000  # Original launcher born at 1,000,000 ms

    # OS has recycled PID 70001 to a new process born at 2,000,000 ms
    def mock_created(pid):
        if pid == 70001:
            return 2_000_000
        if pid == 80002:
            return 2_050_000
        return None

    monkeypatch.setattr(mirror, "_process_created_ms", mock_created)
    # Liveness query with expected 1_000_000 detects mismatch and returns 'dead'
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, c=None: "dead" if (pid == 70001 and c == 1_000_000) else "alive")
    child = {"pid": 80002, "exe": "child.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda p: [child] if p == 70001 else [])
    monkeypatch.setattr(os, "name", "nt")

    pids = session.owned_pids()
    assert 80002 not in pids, "Children of recycled parent PID must not be adopted"
    assert not session.owns_pid(80002)
    assert 80002 not in session._owned_created


def test_refuse_unknown_creation_time_adoption(monkeypatch):
    """Children or parents with unverified creation times must be refused adoption."""
    # Subcase A: Child creation time cannot be queried
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(pid=70001, poll=lambda: None)
    session.created_ms = 1_000_000

    child = {"pid": 80002, "exe": "child.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda p: [child] if p == 70001 else [])
    monkeypatch.setattr(mirror, "_process_created_ms", lambda pid: 1_000_000 if pid == 70001 else None)
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, c=None: "alive")
    monkeypatch.setattr(os, "name", "nt")

    pids = session.owned_pids()
    assert 80002 not in pids, "Child with unknown creation time must not be adopted"
    assert not session.owns_pid(80002)
    assert 80002 not in session._owned_created

    # Subcase B: Parent creation time cannot be queried
    session_b = mirror._VaultIoSession()
    session_b.proc = SimpleNamespace(pid=70001, poll=lambda: None)
    session_b.created_ms = None
    monkeypatch.setattr(mirror, "_process_created_ms", lambda pid: None if pid == 70001 else 1_050_000)
    pids_b = session_b.owned_pids()
    assert 80002 not in pids_b, "Children must not be adopted when parent creation time is unknown"
    assert not session_b.owns_pid(80002)


def test_valid_child_adoption_positive_control(monkeypatch):
    """Legitimate child born after parent is adopted into owned_pids and _owned_created."""
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(pid=70001, poll=lambda: None)
    session.created_ms = 1_000_000

    child = {"pid": 80002, "exe": "legit_child.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda p: [child] if p == 70001 else [])
    monkeypatch.setattr(mirror, "_process_created_ms", lambda pid: 1_050_000 if pid == 80002 else 1_000_000)
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, c=None: "alive")
    monkeypatch.setattr(os, "name", "nt")

    pids = session.owned_pids()
    assert 80002 in pids, "Legitimate child must be included in owned_pids"
    assert session.owns_pid(80002), "Legitimate child must be owned"
    assert session._owned_created[80002] == 1_050_000, "Legitimate child timestamp must be recorded"


def test_previously_owned_child_survives_parent_exit(monkeypatch):
    """Proven owned child identity survives parent exit and keeps session alive until child exits."""
    session = mirror._VaultIoSession()
    session.dest = "C:\\inert\\dest"
    session.proc = SimpleNamespace(pid=70001, poll=lambda: 0)  # Parent has exited
    session.created_ms = 1_000_000
    # Child 80002 was previously verified and owned
    session._owned_created[80002] = 1_050_000
    session._owned_exe[80002] = "legit_child.exe"

    liveness_status = {70001: "dead", 80002: "alive"}
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, c=None: liveness_status.get(pid, "dead"))
    monkeypatch.setattr(os, "name", "nt")

    recorder = EffectRecorder()
    monkeypatch.setattr(session, "_release_held_exclusion", lambda: recorder.released_exclusion.append(True))
    monkeypatch.setattr(mirror, "_drop_retained_session", lambda s: recorder.dropped_session.append(s))

    # Child identity is preserved in owned_pids
    assert 80002 in session.owned_pids(), "Previously owned child must survive in owned_pids after parent exit"
    assert session.owns_pid(80002)

    # Session remains physically alive while child lives
    assert session.physical_liveness() == "alive"
    assert session.physically_alive() is True

    # Abandonment is blocked; exclusion is held
    session._abandon_unstarted()
    assert len(recorder.released_exclusion) == 0, "Exclusion must not be released while owned child lives"
    assert len(recorder.dropped_session) == 0

    # Now child exits
    liveness_status[80002] = "dead"
    assert session.physical_liveness() == "dead"
    assert session.physically_alive() is False

    # Now abandonment releases exclusion and drops session
    session._abandon_unstarted()
    assert len(recorder.released_exclusion) == 1, "Exclusion must be released once child is confirmed dead"
    assert len(recorder.dropped_session) == 1


def test_death_followed_by_unknown_retains_definitive_death(monkeypatch):
    """Confirmed process exit must not revert to unknown on subsequent failed query."""
    session = mirror._VaultIoSession()
    session.writer_pid = 70002
    session.writer_created_ms = 1_000_000
    session._owned_created[70002] = 1_000_000

    query_status = "dead"
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, c=None: query_status)

    assert session.physical_liveness() == "dead"
    assert session.physically_alive() is False

    # Later, OS recycles PID 70002 to a privileged process, yielding Access Denied (status 'unknown')
    query_status = "unknown"

    # Confirmed death must be latched and retained
    assert session.physical_liveness() == "dead", "Definitive death must not revert to unknown"
    assert session.physically_alive() is False


def test_exited_popen_plus_unknown_other_child_retains_exclusion(monkeypatch):
    """Popen poll exit is preserved, but unresolved other child retains exclusion."""
    session = mirror._VaultIoSession()
    session.dest = "C:\\inert\\dest"
    session.proc = SimpleNamespace(pid=70001, poll=lambda: 0)  # Popen definitive exit
    session.created_ms = 1_000_000
    session._owned_created[80003] = 1_020_000  # Other owned child

    # If raw PID 70001 were queried, it might return unknown; child 80003 is unknown
    liveness_status = {70001: "unknown", 80003: "unknown"}
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, c=None: liveness_status.get(pid, "unknown"))

    recorder = EffectRecorder()
    monkeypatch.setattr(session, "_release_held_exclusion", lambda: recorder.released_exclusion.append(True))
    monkeypatch.setattr(mirror, "_drop_retained_session", lambda s: recorder.dropped_session.append(s))

    # Popen's exit code is respected, but 80003 is genuinely unknown
    assert session.physical_liveness() == "unknown", "Unresolved child must yield unknown liveness"
    assert session.physically_alive() is True, "Unknown child keeps physically_alive True"

    # Exclusion is retained
    session._abandon_unstarted()
    assert len(recorder.released_exclusion) == 0, "Exclusion must remain held for unresolved child"
    assert len(recorder.dropped_session) == 0


def test_missing_or_mismatched_creation_time_refuses_kill_and_assignment(monkeypatch):
    """Missing or mismatched creation time refuses PID-based termination and job assignment."""
    recorder = EffectRecorder()
    mock_k32 = _mock_k32(recorder, handle=11111)
    monkeypatch.setattr(mirror, "_kernel32", lambda: mock_k32)
    monkeypatch.setattr(os, "name", "nt")

    # 1. Termination: missing creation time
    assert mirror._win_terminate_pid(70004, created_ms=None) is False
    assert len(recorder.terminated_handles) == 0, "Kill must refuse mutation without created_ms"

    # 2. Termination: mismatched creation time
    monkeypatch.setattr(mirror, "_windows_process_created_ms", lambda h: 2_000_000)
    assert mirror._win_terminate_pid(70004, created_ms=1_000_000) is False
    assert len(recorder.terminated_handles) == 0, "Kill must refuse mutation on mismatched created_ms"

    # 3. Termination: creation time query failed
    monkeypatch.setattr(mirror, "_windows_process_created_ms", lambda h: None)
    assert mirror._win_terminate_pid(70004, created_ms=1_000_000) is False
    assert len(recorder.terminated_handles) == 0, "Kill must refuse mutation when creation time query fails"

    # 4. Job assignment: missing creation time
    assert mirror._win_assign_pid(99999, 70004, created_ms=None) is False
    assert len(recorder.assigned_handles) == 0, "Job assignment must refuse mutation without created_ms"

    # 5. Job assignment: mismatched creation time
    monkeypatch.setattr(mirror, "_windows_process_created_ms", lambda h: 2_000_000)
    assert mirror._win_assign_pid(99999, 70004, created_ms=1_000_000) is False
    assert len(recorder.assigned_handles) == 0, "Job assignment must refuse mutation on mismatched created_ms"

    # 6. Job assignment: creation time query failed
    monkeypatch.setattr(mirror, "_windows_process_created_ms", lambda h: None)
    assert mirror._win_assign_pid(99999, 70004, created_ms=1_000_000) is False
    assert len(recorder.assigned_handles) == 0, "Job assignment must refuse mutation when creation time query fails"


def test_matching_creation_time_positive_control_for_kill_and_assignment(monkeypatch):
    """Verified creation time allows PID-based termination and job assignment."""
    import ctypes
    from ctypes import wintypes

    class FakeDWORD:
        def __init__(self, *args, **kwargs):
            self.value = mirror._STILL_ACTIVE

    recorder = EffectRecorder()
    mock_k32 = _mock_k32(recorder, handle=22222)
    monkeypatch.setattr(mirror, "_kernel32", lambda: mock_k32)
    monkeypatch.setattr(ctypes, "byref", lambda obj: obj)
    monkeypatch.setattr(wintypes, "DWORD", FakeDWORD)
    monkeypatch.setattr(mirror, "_windows_process_created_ms", lambda h: 1_000_000)
    monkeypatch.setattr(os, "name", "nt")

    # Positive control: kill with matching created_ms
    assert mirror._win_terminate_pid(70005, created_ms=1_000_000) is True
    assert recorder.terminated_handles == [22222], "Kill must invoke TerminateProcess on matching handle"

    # Positive control: assignment with matching created_ms
    assert mirror._win_assign_pid(99999, 70005, created_ms=1_000_000) is True
    assert recorder.assigned_handles == [(99999, 22222)], "Assignment must invoke AssignProcessToJobObject on matching handle"


def test_process_liveness_creation_query_failure_returns_unknown(monkeypatch):
    """When GetProcessTimes fails on a live handle, _process_liveness returns 'unknown', not 'alive'."""
    import ctypes
    from ctypes import wintypes

    class FakeDWORD:
        def __init__(self, *args, **kwargs):
            self.value = mirror._STILL_ACTIVE

    recorder = EffectRecorder()
    mock_k32 = _mock_k32(recorder, handle=33333)
    monkeypatch.setattr(mirror, "_kernel32", lambda: mock_k32)
    monkeypatch.setattr(ctypes, "byref", lambda obj: obj)
    monkeypatch.setattr(wintypes, "DWORD", FakeDWORD)
    monkeypatch.setattr(mirror, "_windows_process_created_ms", lambda handle: None)  # GetProcessTimes failed!
    monkeypatch.setattr(os, "name", "nt")

    result = mirror._process_liveness(70006, created_ms=1_000_000)
    assert result == "unknown", f"Expected 'unknown' when created_ms query fails, got '{result}'"
