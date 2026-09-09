"""AW-10: session admission through a verified same-directory junction."""
import json
import os
from pathlib import Path
import subprocess
import sys

import library_mirror as m
from tests.library_work_astra.test_phase4_aw_acceptance import env


def test_junction_alias_refuses_competing_session_before_first_lease(env):
    original = str(env.vault)
    alias = str(env.vault.parent / "aw10-alias")
    child_env = os.environ.copy()
    child_env.update(AW_ALIAS_LINK=alias, AW_ALIAS_TARGET=original)
    made = subprocess.run(
        ["pwsh", "-NoProfile", "-Command",
         "New-Item -ItemType Junction -Path $env:AW_ALIAS_LINK -Target $env:AW_ALIAS_TARGET | Out-Null"],
        env=child_env, capture_output=True, text=True, timeout=8,
    )
    assert made.returncode == 0, made.stderr
    assert Path(original).samefile(alias)
    first = m._VaultIoSession.start(original)
    try:
        assert first.alive and not first._lease_written
        source = '''import json, os, sys
import library_mirror as m
session = None
result = {"competitor_pid": os.getpid(), "started": False}
try:
    session = m._VaultIoSession.start(sys.argv[1])
    result.update(started=True, writer_pid=session.writer_pid, launcher_pid=session.pid,
                  alive=session.alive, lease_written=session._lease_written)
except (OSError, m._LockTimeout) as exc:
    result.update(refusal_type=type(exc).__name__, refusal=str(exc))
finally:
    if session is not None:
        result["termination_confirmed"] = session.terminate()
print(json.dumps(result))
'''
        child = subprocess.run(
            [sys.executable, "-B", "-c", source, alias],
            capture_output=True, text=True, timeout=12,
        )
        assert child.returncode == 0, child.stderr
        observed = json.loads(child.stdout)
        observed.update(original=original, alias=alias, same_file=True,
                        first_writer_pid=first.writer_pid,
                        first_writer_alive=first.alive,
                        first_lease_written=first._lease_written)
        print(json.dumps(observed, sort_keys=True))
        assert not observed["started"], observed
    finally:
        assert first.terminate()
