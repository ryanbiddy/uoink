"""Astra's inert identity boundaries; no process or kernel API is invoked."""
import ctypes
from ctypes import wintypes
from types import SimpleNamespace

import pytest

import library_mirror as m
from _mirror_stable_native_fixture import stable_native_authority


def session():
    value=m._VaultIoSession()
    value.proc=SimpleNamespace(pid=70001,poll=lambda:None)
    value.created_ms=1_000_000
    return value


def fake_kernel(monkeypatch, actual):
    effects=[]
    def exit_code(handle, ptr):
        ctypes.cast(ptr,ctypes.POINTER(wintypes.DWORD)).contents.value=m._STILL_ACTIVE
        return 1
    k=SimpleNamespace(OpenProcess=lambda *args:123,
                      CloseHandle=lambda *args:1,
                      GetExitCodeProcess=exit_code,
                      TerminateProcess=lambda *args:effects.append('terminate') or 1,
                      AssignProcessToJobObject=lambda *args:effects.append('assign') or 1)
    monkeypatch.setattr(m,'_kernel32',lambda:k)
    monkeypatch.setattr(m,'_windows_process_created_ms',lambda handle:actual)
    return effects


@pytest.mark.parametrize('operation',['terminate','assign'])
@pytest.mark.parametrize('difference',[-1,1])
def test_pid_action_refuses_any_different_creation_time(monkeypatch,operation,difference):
    effects=fake_kernel(monkeypatch,1_000_000+difference)
    if operation=='terminate':
        result=m._win_terminate_pid(70001,1_000_000)
    else:
        result=m._win_assign_pid(999,70001,1_000_000)
    assert not effects, 'A different process identity received a mutation request'
    assert result is False


def test_liveness_rejects_one_millisecond_identity_mismatch(monkeypatch):
    fake_kernel(monkeypatch,1_000_001)
    assert m._process_liveness(70001,1_000_000)=='dead'


def test_orphan_one_millisecond_older_than_parent_is_not_owned(monkeypatch):
    s=session()
    monkeypatch.setattr(m,'_windows_process_children',lambda pid:[{'pid':80002,'ppid':70001,'exe':'python.exe'}])
    monkeypatch.setattr(m,'_process_created_ms',lambda pid:999_999 if pid==80002 else 1_000_000)
    monkeypatch.setattr(m,'_process_liveness',lambda *args:'alive')
    assert 80002 not in s.owned_pids()
    s._adopt_owned_tree()
    assert s.writer_pid != 80002


def test_missing_recorded_parent_identity_is_not_filled_from_raw_pid(monkeypatch):
    s=session();s.created_ms=None
    monkeypatch.setattr(m,'_windows_process_children',lambda pid:[{'pid':80002,'ppid':70001,'exe':'child.exe'}])
    monkeypatch.setattr(m,'_process_created_ms',lambda pid:1_050_000 if pid==80002 else 1_000_000)
    monkeypatch.setattr(m,'_process_liveness',lambda *args:'alive')
    assert 80002 not in s.owned_pids()


def test_parent_replacement_during_snapshot_does_not_adopt_foreign_child(monkeypatch):
    s=session();state={'replaced':False}
    def snapshot(pid):
        state['replaced']=True
        return [{'pid':80002,'ppid':70001,'exe':'foreign.exe'}]
    monkeypatch.setattr(m,'_windows_process_children',snapshot)
    monkeypatch.setattr(m,'_process_created_ms',lambda pid:2_050_000 if pid==80002 else (2_000_000 if state['replaced'] else 1_000_000))
    monkeypatch.setattr(m,'_process_liveness',lambda pid,created=None:'dead' if pid==70001 and state['replaced'] else 'alive')
    assert 80002 not in s.owned_pids()


def test_child_replacement_between_snapshot_and_identity_query_is_not_owned(monkeypatch):
    s=session();state={'replaced':False}
    def created(pid):
        if pid==80002:
            state['replaced']=True
            return 2_000_000
        return 1_000_000
    def snapshot(pid):
        if state['replaced']:
            return []  # The current child belongs to a different creator.
        return [{'pid':80002,'ppid':70001,'exe':'child.exe'}]
    monkeypatch.setattr(m,'_process_created_ms',created)
    monkeypatch.setattr(m,'_windows_process_children',snapshot)
    monkeypatch.setattr(m,'_process_liveness',lambda *args:'alive')
    assert 80002 not in s.owned_pids()


def test_exited_launcher_proves_same_pid_writer_dead_when_writer_time_is_unknown(monkeypatch):
    s=session();s.proc.poll=lambda:0
    s.writer_pid=70001;s.writer_created_ms=None
    monkeypatch.setattr(m,'_process_liveness',lambda *args:'unknown')
    assert s.physical_liveness()=='dead'
