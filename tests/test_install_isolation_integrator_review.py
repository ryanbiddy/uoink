"""Read-only identity/configuration probes; no helper, socket or kill."""
import os
import sys
from pathlib import Path

import pytest
import uoink_install_isolation as iso


@pytest.mark.parametrize("flag", [iso.CLI_PROFILE, iso.CLI_PORT, iso.CLI_FROM_INSTALL])
def test_incomplete_isolation_flag_never_becomes_ordinary_mode(flag):
    with pytest.raises(iso.IsolationError):
        iso.resolve_from_process([flag], environ={})


def test_live_pid_without_creation_identity_is_not_owned():
    assert iso._pid_liveness(os.getpid(), None) != "alive"


def test_different_creation_identity_is_not_owned():
    created = iso.current_process_created_ms()
    assert created is not None
    assert iso._pid_liveness(os.getpid(), created + 1) != "alive"


def test_unavailable_creation_lookup_is_not_owned(monkeypatch):
    created = iso.current_process_created_ms()
    assert created is not None
    name = "_windows_process_created_ms" if os.name == "nt" else "_posix_process_created_ms"
    monkeypatch.setattr(iso, name, lambda *args: None)
    assert iso._pid_liveness(os.getpid(), created) != "alive"


def test_missing_expected_executable_is_not_owned():
    created = iso.current_process_created_ms()
    assert created is not None
    identity = {"pid": os.getpid(), "created_ms": created, "executable": ""}
    assert iso._identity_liveness(identity) != "alive"
