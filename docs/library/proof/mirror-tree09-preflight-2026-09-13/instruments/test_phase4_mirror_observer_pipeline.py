"""Inert plugin pipeline checks; one deliberate failure must remain a failure."""
import sys
import threading
from types import SimpleNamespace

import pytest


def test_partition_and_observer_keep_a_passing_case():
    assert 2+2==4


def test_partition_and_observer_keep_a_deliberate_failure(monkeypatch):
    session=SimpleNamespace(proc=SimpleNamespace(pid=70001,returncode=0),
                            writer_pid=70002,created_ms=1_000_000,
                            writer_created_ms=1_001_000,_dead=True,
                            _launching=False,_popen_in_progress=False,
                            _owned_created={70002:1_001_000},
                            _owned_exe={70002:'inert-writer'},
                            _origin_thread=threading.current_thread())
    owner=SimpleNamespace(dest='inert-destination',key='inert-gate',held=True,
                          _exclusive_holds=0,_stop=threading.Event(),
                          _done=threading.Event(),_acquired=threading.Event(),
                          _thread=threading.current_thread(),sessions=[session])
    session._exclusion_owner=owner
    fake=SimpleNamespace(_live_owners=[owner],_retained_sessions=[session],_dest_holds={'inert':1})
    monkeypatch.setitem(sys.modules,'library_mirror',fake)
    pytest.fail('Deliberate inert failure: observer must preserve this outcome')
