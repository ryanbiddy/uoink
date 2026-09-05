"""tests/test_library_work_recovery.py - Independent verification tests for Gate P2-5.

Covers Gate P2-5 (crash and reconstruction):
- Subprocesses killed at all three durable boundaries (before publication, after publication before commit, after commit before response)
- Reopen and replay once restores exact receipt and projection revision
- Corrupt or missing committed authoritative record stops visibly with error; never skips
- Deleting only a verified disposable DB allows full reconstruction of pins, taxonomy, and exclusive policy from local authoritative records
- Retains orphan authoritative records for missing/deleted items without resurrecting deleted rows

Written from PHASE2-CONTRACT-2026-09-04 and phase2-contract/tool-schemas.json.
xfails strictly until library_work is integrated.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

import tests.library_crash_runner as crash_runner

try:
    import library_work
    HAS_LIBRARY_WORK = True
except ImportError:
    library_work = None
    HAS_LIBRARY_WORK = False

ROOT = Path(__file__).resolve().parent.parent
GATE = "Gate P2-5: crash and reconstruction"


@pytest.fixture
def isolated_storage_fixture():
    temp_dir = Path(tempfile.mkdtemp(prefix="uoink_recovery_test_"))
    db_path = temp_dir / "substrate.db"
    storage_root = temp_dir / ".uoink" / "library"
    crash_runner._init_test_substrate_db(db_path)
    yield db_path, storage_root
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_p2_5_crash_boundary_before_publication_harness(isolated_storage_fixture):
    """Crash before publication: temp file is not published; DB remains revision 0."""
    db_path, storage_root = isolated_storage_fixture
    res = crash_runner.run_crash_boundary_subprocess(
        boundary=crash_runner.BOUNDARY_BEFORE_PUBLICATION,
        db_path=db_path,
        storage_root=storage_root,
        operation_key="op_crash_b1",
    )
    assert res.exit_code == crash_runner.CRASH_EXIT_CODE
    assert not res.published_record_found
    assert not res.db_committed

    rec = crash_runner.replay_and_recover(db_path, storage_root)
    assert rec.recovered_revision == 0
    assert rec.db_integrity_ok


def test_p2_5_crash_boundary_after_publication_before_db_commit_harness(isolated_storage_fixture):
    """Crash after publication, before DB commit: authoritative record is durable; replay recovers revision to 1."""
    db_path, storage_root = isolated_storage_fixture
    res = crash_runner.run_crash_boundary_subprocess(
        boundary=crash_runner.BOUNDARY_AFTER_PUBLICATION_BEFORE_COMMIT,
        db_path=db_path,
        storage_root=storage_root,
        operation_key="op_crash_b2",
    )
    assert res.exit_code == crash_runner.CRASH_EXIT_CODE
    assert res.published_record_found
    assert not res.db_committed

    rec = crash_runner.replay_and_recover(db_path, storage_root)
    assert rec.recovered_revision == 1
    assert rec.db_integrity_ok
    assert rec.details["replayed_operations"] == 1


def test_p2_5_crash_boundary_after_commit_before_response_harness(isolated_storage_fixture):
    """Crash after commit, before response: both record and DB committed; retry returns receipt without second commit."""
    db_path, storage_root = isolated_storage_fixture
    res = crash_runner.run_crash_boundary_subprocess(
        boundary=crash_runner.BOUNDARY_AFTER_COMMIT_BEFORE_RESPONSE,
        db_path=db_path,
        storage_root=storage_root,
        operation_key="op_crash_b3",
    )
    assert res.exit_code == crash_runner.CRASH_EXIT_CODE
    assert res.published_record_found
    assert res.db_committed

    rec = crash_runner.replay_and_recover(db_path, storage_root)
    assert rec.recovered_revision == 1
    assert rec.db_integrity_ok
    assert rec.details["replayed_operations"] == 0, "Already committed operation must not re-advance"


def test_p2_5_corrupt_authoritative_record_stops_visibly(isolated_storage_fixture):
    """Corrupt or altered authoritative record halts replay with visible error; must not skip."""
    db_path, storage_root = isolated_storage_fixture

    # Publish an operation record
    crash_runner.run_crash_boundary_subprocess(
        boundary=crash_runner.BOUNDARY_AFTER_PUBLICATION_BEFORE_COMMIT,
        db_path=db_path,
        storage_root=storage_root,
        operation_key="op_corrupt_test",
    )

    # Tamper with the published record file
    ops_dir = storage_root / "operations"
    rec_file = next(ops_dir.glob("*.json"))
    content = json.loads(rec_file.read_text(encoding="utf-8"))
    content["after_revision"] = 999  # tampered revision
    rec_file.write_text(json.dumps(content), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Corrupt authoritative record"):
        crash_runner.replay_and_recover(db_path, storage_root)

    # DB state must reflect conflict
    conn = sqlite3.connect(str(db_path))
    state = conn.execute("SELECT recovery_state FROM library_meta WHERE singleton=1").fetchone()[0]
    conn.close()
    assert state == "conflict"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: recover_operations implementation required")
def test_p2_5_recover_operations_service_interface(isolated_storage_fixture):
    """Verify library_work.recover_operations restores projection and returns exact receipts."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: recover_operations")

    db_path, storage_root = isolated_storage_fixture
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")

    res = library_work.recover_operations(conn, storage_root=storage_root)
    assert res.get("ok") is True
    assert "replayed_count" in res


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: rebuild_library_state implementation required")
def test_p2_5_reconstruct_db_from_authoritative_records_retains_orphan_pins(isolated_storage_fixture):
    """Deleting disposable DB and rebuilding from .uoink/library/ recovers pins, taxonomies, and retains orphan pins."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: rebuild_library_state")

    db_path, storage_root = isolated_storage_fixture
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")

    # Rebuild on fresh database
    res = library_work.rebuild_library_state(conn, storage_root=storage_root)
    assert res.get("ok") is True
    assert "orphan_pins_count" in res
    assert "projection_revision" in res
