"""AW-5 review of the isolated writer's remaining exclusion boundaries."""
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import library_mirror as mirror
import library_resources as resources
from tests.library_work_astra.test_phase4_aw_acceptance import env, export


def test_aw5_another_writer_lock_does_not_certify_our_deferred_transaction(env):
    conn = env.idx._conn
    conn.execute("PRAGMA journal_mode=WAL")
    other = sqlite3.connect(str(env.idx._path), timeout=0)
    try:
        conn.execute("BEGIN DEFERRED")
        conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(resources.ResourceError) as caught:
            with env.store._sqlite_writer_exclusion():
                pass
        assert caught.value.code == "stale_brief"
        assert conn.in_transaction
        assert other.in_transaction
    finally:
        other.rollback()
        other.close()
        conn.rollback()


def test_aw5_destination_lease_io_is_inside_a_cancellable_boundary(env, monkeypatch):
    export(env)
    env.mirror._clock = time.monotonic
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    original_write = mirror._write_dest_lease
    results = []

    def stalled_destination_write(*args, **kwargs):
        entered.set()
        release.wait(12)
        return original_write(*args, **kwargs)

    def resync():
        try:
            results.append(env.mirror.resync(budget_s=0.1))
        finally:
            done.set()

    monkeypatch.setattr(mirror, "_write_dest_lease", stalled_destination_write)
    thread = threading.Thread(target=resync, daemon=True)
    thread.start()
    try:
        assert entered.wait(3), "The destination lease write was not reached"
        # More than both advertised 2 s startup and termination bounds plus
        # the 0.1 s publication budget. A blocked destination must not trap
        # the caller before its cancellable operation starts.
        assert done.wait(5), "Destination lease I/O trapped resync outside cancellation"
        assert results and not results[0]["ok"]
    finally:
        release.set()
        thread.join(8)
        assert not thread.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows parent-loss job lifetime")
def test_aw5_real_parent_loss_terminates_the_assigned_vault_writer(tmp_path):
    dest = tmp_path / "vault"
    dest.mkdir()
    ready = tmp_path / "ready.json"
    script = (
        "import json,sys,time\nfrom pathlib import Path\nimport library_mirror as m\n"
        "s=m._VaultIoSession.start(sys.argv[1])\n"
        "Path(sys.argv[2]).write_text(json.dumps({'pid':s.pid,'created':s.created_ms}))\n"
        "time.sleep(30)\n"
    )
    proc = subprocess.Popen([sys.executable, "-B", "-c", script, str(dest), str(ready)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    child = None
    try:
        until = time.monotonic() + 5
        while not ready.exists() and proc.poll() is None and time.monotonic() < until:
            time.sleep(0.02)
        assert ready.exists(), "Isolated parent did not report its writer"
        child = json.loads(ready.read_text())
        assert mirror._pid_is_alive(child["pid"], child["created"])
        proc.kill()
        proc.wait(timeout=3)
        until = time.monotonic() + 3
        while mirror._pid_is_alive(child["pid"], child["created"]) and time.monotonic() < until:
            time.sleep(0.02)
        assert not mirror._pid_is_alive(child["pid"], child["created"])
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=3)
        if child and mirror._pid_is_alive(child["pid"], child["created"]):
            os.kill(child["pid"], 15)
        if proc.stderr:
            proc.stderr.close()
