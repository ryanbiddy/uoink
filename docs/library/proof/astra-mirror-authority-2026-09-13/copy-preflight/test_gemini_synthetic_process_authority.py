"""Synthetic process-authority and lifecycle regression probes for Gemini.

Diagnostic assignment: inspect authority in owned_pids, physical_liveness,
and termination. All probes use inert PIDs and mocked observations.
No real processes are launched, suspended, or terminated.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import library_mirror as mirror


def test_probe_toolhelp_orphan_child_adopted_without_temporal_check(monkeypatch):
    """Toolhelp parent PID outlives creator: orphan child adopted without created_ms check.
    
    If launcher PID 70001 is recycled from an earlier dead process that spawned 80002,
    80002 has th32ParentProcessID == 70001 but was created before 70001.
    Current owned_pids adopts 80002 into _owned_created and claims ownership.
    """
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(pid=70001, poll=lambda: None)
    session.created_ms = 1_000_000  # Launcher born at T=1,000,000 ms

    # Foreign orphan created at T=500,000 ms (500s BEFORE launcher was born)
    orphan_entry = {"pid": 80002, "exe": "foreign_orphan.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda ppid: [orphan_entry] if ppid == 70001 else [])
    
    def mock_created_ms(pid):
        if pid == 70001:
            return 1_000_000
        if pid == 80002:
            return 500_000  # Predates launcher!
        return None

    monkeypatch.setattr(mirror, "_process_created_ms", mock_created_ms)
    monkeypatch.setattr(os, "name", "nt")

    pids = session.owned_pids()

    # Confirmed defect: 80002 was adopted without verifying creation timestamp against session.created_ms
    assert 80002 in pids, "Foreign orphan was not ingested into owned_pids"
    assert session.owns_pid(80002), "Foreign orphan is claimed as owned"
    assert session._owned_created.get(80002) == 500_000, "Foreign orphan timestamp recorded as valid authority"


def test_probe_foreign_orphan_retains_session_and_blocks_abandonment(monkeypatch):
    """Foreign orphan retention: session remains 'alive' and refuses cleanup.
    
    Even when the launcher (70001) has exited (poll() == 0), the presence of the
    running orphan (80002) causes physical_liveness() to report 'alive'.
    _abandon_unstarted refuses to drop retain or release exclusion.
    """
    session = mirror._VaultIoSession()
    session.dest = "C:\\fake\\dest"
    session.proc = SimpleNamespace(pid=70001, poll=lambda: 0)  # Launcher exited!
    session.created_ms = 1_000_000

    orphan_entry = {"pid": 80002, "exe": "foreign_orphan.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda ppid: [orphan_entry] if ppid == 70001 else [])
    monkeypatch.setattr(mirror, "_process_created_ms", lambda pid: 500_000 if pid == 80002 else 1_000_000)
    monkeypatch.setattr(os, "name", "nt")

    # Ingest orphan
    session.owned_pids()

    # Launcher is dead, orphan is alive
    def mock_liveness(pid, created_ms=None):
        if pid == 70001:
            return "dead"
        if pid == 80002:
            return "alive"
        return "dead"

    monkeypatch.setattr(mirror, "_process_liveness", mock_liveness)

    # Confirmed defect: physical_liveness reports 'alive' due to the foreign orphan
    assert session.physical_liveness() == "alive"
    assert session.physically_alive() is True

    # _abandon_unstarted cannot release exclusion or drop retain because physically_alive() is True
    dropped = False
    released = False
    monkeypatch.setattr(mirror, "_drop_retained_session", lambda s: globals().update(dropped=True))
    monkeypatch.setattr(session, "_release_held_exclusion", lambda: globals().update(released=True))

    session._abandon_unstarted()
    assert not dropped, "_abandon_unstarted unexpectedly dropped session despite physically_alive()"
    assert not released, "_abandon_unstarted unexpectedly released exclusion despite physically_alive()"


def test_probe_foreign_orphan_targeted_by_terminate(monkeypatch):
    """Foreign orphan kill hazard: termination invokes _win_terminate_pid on foreign child.
    
    Because the foreign orphan's timestamp was recorded in _owned_created,
    _created_for_pid matches the orphan's actual timestamp, and terminate()
    attempts to kill the foreign process.
    """
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(pid=70001, poll=lambda: 0, wait=lambda **k: 0,
                                   stdin=None, stdout=None, stderr=None)
    session.created_ms = 1_000_000

    orphan_entry = {"pid": 80002, "exe": "foreign_orphan.exe", "ppid": 70001}
    monkeypatch.setattr(mirror, "_windows_process_children", lambda ppid: [orphan_entry] if ppid == 70001 else [])
    monkeypatch.setattr(mirror, "_process_created_ms", lambda pid: 500_000 if pid == 80002 else 1_000_000)
    monkeypatch.setattr(os, "name", "nt")

    session.owned_pids()

    terminated_calls = []
    monkeypatch.setattr(mirror, "_win_terminate_job", lambda job: None)
    monkeypatch.setattr(mirror, "_win_terminate_pid", lambda pid, created_ms: terminated_calls.append((pid, created_ms)) or True)
    monkeypatch.setattr(mirror, "_process_liveness", lambda *a, **k: "dead")

    session.terminate()

    # Confirmed defect: terminate targeted the foreign orphan PID with its recorded timestamp
    assert (80002, 500_000) in terminated_calls, f"Foreign orphan 80002 was not targeted for termination: {terminated_calls}"


def test_probe_confirmed_exit_forgotten_on_recycled_pid_access_denied(monkeypatch):
    """Confirmed process exit is forgotten when subsequent query encounters Access Denied.
    
    If writer 70002 was confirmed 'dead' at time T1, but the PID is later recycled
    into a protected system process causing OpenProcess to fail with error 5 (Access Denied),
    _process_liveness returns 'unknown'.
    physical_liveness forgets the confirmed death and transitions from 'dead' back to 'unknown'.
    """
    session = mirror._VaultIoSession()
    session.proc = None
    session.writer_pid = 70002
    session.writer_created_ms = 1_000_000
    session._owned_created[70002] = 1_000_000

    liveness_status = "dead"
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, created_ms=None: liveness_status)

    # Query 1: writer is confirmed dead
    assert session.physical_liveness() == "dead"
    assert session.physically_alive() is False

    # OS recycles PID 70002 to a protected process -> OpenProcess returns Access Denied -> 'unknown'
    liveness_status = "unknown"

    # Query 2: confirmed exit is forgotten!
    assert session.physical_liveness() == "unknown", "physical_liveness did not return unknown on failed query"
    assert session.physically_alive() is True, "Confirmed dead process was not forgotten on subsequent query"


def test_probe_proc_poll_death_overridden_by_recycled_pid_query(monkeypatch):
    """Definitive subprocess handle exit is overridden by raw PID lookup.
    
    proc.poll() returns 0 (definitive kernel proof that the subprocess exited).
    However, physical_liveness still queries _process_liveness(self.pid, self.created_ms).
    If that raw PID query returns 'unknown' (due to recycling/permission error),
    the session reports 'unknown' and physically_alive() returns True.
    """
    session = mirror._VaultIoSession()
    session.proc = SimpleNamespace(pid=70003, poll=lambda: 0)  # Exited with code 0!
    session.created_ms = 1_000_000

    # Raw PID query yields 'unknown' (e.g. Access Denied on recycled PID)
    monkeypatch.setattr(mirror, "_process_liveness", lambda pid, created_ms=None: "unknown")

    # Confirmed defect: proc.poll() == 0 is overridden by raw PID query
    assert session.physical_liveness() == "unknown"
    assert session.physically_alive() is True, "Subprocess exit code 0 was overridden by raw PID lookup"


def test_probe_process_times_failure_bypasses_start_time_check(monkeypatch):
    """When GetProcessTimes fails on a live handle, _process_liveness returns 'alive' instead of verifying created_ms.
    
    In _process_liveness (line 663-667), if actual is None (GetProcessTimes failed),
    the timestamp check is bypassed and the function falls through to return 'alive'.
    """
    import ctypes

    class FakeDWORD:
        def __init__(self, *args, **kwargs):
            self.value = mirror._STILL_ACTIVE

    mock_k32 = MagicMock()
    mock_k32.OpenProcess.return_value = 12345
    mock_k32.GetExitCodeProcess.return_value = 1
    mock_k32.CloseHandle.return_value = 1

    monkeypatch.setattr(mirror, "_kernel32", lambda: mock_k32)
    monkeypatch.setattr(ctypes, "byref", lambda obj: obj)
    from ctypes import wintypes
    monkeypatch.setattr(wintypes, "DWORD", FakeDWORD)
    monkeypatch.setattr(mirror, "_windows_process_created_ms", lambda handle: None)  # GetProcessTimes failed!
    monkeypatch.setattr(os, "name", "nt")

    # Call _process_liveness with a specific expected created_ms
    result = mirror._process_liveness(70004, created_ms=1_000_000)

    # Confirmed defect: Returns 'alive' even though created_ms could not be validated
    assert result == "alive", f"Expected fallthrough to 'alive', got {result}"
