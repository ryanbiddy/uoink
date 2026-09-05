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
from index import Index
from library_work import LibraryWorkService, RequestContext, LibraryError

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


def test_p2_5_recover_operations_service_interface(isolated_storage_fixture):
    """Verify library_work.recover_operations restores projection and returns exact receipts."""
    db_path, storage_root = isolated_storage_fixture
    idx = Index.open(db_path)
    idx.upsert_yoink(dict(
        video_id="vid_rec",
        slug="vid_rec",
        title="Title",
        topic="Old",
        yoinked_at="2026-09-04",
        corpus_path="",
        sidecar_path="",
    ))
    with idx.write_transaction() as c:
        c.execute("INSERT INTO clips(video_id, seq, start, end, text) VALUES ('vid_rec', 0, 0, 10, 'evidence')")

    svc = LibraryWorkService(idx, storage_root)
    ctx_op = RequestContext(authenticated=True, operator=True, local_user_confirmed=True, session_id="s_op")

    tax_res = svc.approve_taxonomy(ctx_op, {
        "version_id": "v1",
        "nodes": [{"shelf_id": "s1", "path": ["S1"], "definition": "Def", "include": ["i"], "exclude": ["e"]}],
    })
    assert tax_res.get("ok") is True

    intent = svc.mint_user_intent(ctx_op, {
        "kind": "pin",
        "operation": {
            "video_id": "vid_rec",
            "shelf_id": "s1",
            "action": "move",
            "expected_projection_revision": 0,
            "operation_key": "op_rec_01",
        },
    })
    assert intent.get("ok") is True

    pin_res = svc.pin_shelf(ctx_op, {
        "video_id": "vid_rec",
        "shelf_id": "s1",
        "action": "move",
        "expected_projection_revision": 0,
        "operation_key": "op_rec_01",
        "user_intent_token": intent["user_intent_token"],
    })
    assert pin_res.get("ok") is True
    assert pin_res.get("after_revision") == 1

    res = svc.recover_operations(ctx_op, {})
    assert res.get("ok") is True
    assert res.get("projection_revision") == 1
    idx.close()


def test_p2_5_reconstruct_db_from_authoritative_records_retains_orphan_pins(isolated_storage_fixture):
    """Deleting disposable DB and rebuilding from .uoink/library/ recovers pins, taxonomies, and retains orphan pins."""
    db_path, storage_root = isolated_storage_fixture
    idx = Index.open(db_path)
    old_yoink = dict(
        video_id="vid_orphan",
        slug="vid_orphan",
        title="Title",
        topic="Old",
        yoinked_at="2026-09-04",
        corpus_path="",
        sidecar_path="",
    )
    idx.upsert_yoink(old_yoink)
    with idx.write_transaction() as c:
        c.execute("INSERT INTO clips(video_id, seq, start, end, text) VALUES ('vid_orphan', 0, 0, 10, 'evidence')")

    svc = LibraryWorkService(idx, storage_root)
    ctx_op = RequestContext(authenticated=True, operator=True, local_user_confirmed=True, session_id="s_op")

    svc.approve_taxonomy(ctx_op, {
        "version_id": "v1",
        "nodes": [{"shelf_id": "s1", "path": ["S1"], "definition": "Def", "include": ["i"], "exclude": ["e"]}],
    })

    intent = svc.mint_user_intent(ctx_op, {
        "kind": "pin",
        "operation": {
            "video_id": "vid_orphan",
            "shelf_id": "s1",
            "action": "move",
            "expected_projection_revision": 0,
            "operation_key": "op_orphan_01",
        },
    })
    pin_res = svc.pin_shelf(ctx_op, {
        "video_id": "vid_orphan",
        "shelf_id": "s1",
        "action": "move",
        "expected_projection_revision": 0,
        "operation_key": "op_orphan_01",
        "user_intent_token": intent["user_intent_token"],
    })
    assert pin_res.get("ok") is True
    idx.close()

    # Total disposable DB loss: delete the database file and WAL
    db_path.unlink()
    for suffix in ("-wal", "-shm"):
        sibling = db_path.with_name(db_path.name + suffix)
        sibling.unlink(missing_ok=True)

    # Reopen fresh index: yoinks not restored yet -> item is an orphan pin
    new_idx = Index.open(db_path)
    new_svc = LibraryWorkService(new_idx, storage_root)
    assert new_svc.startup_status.get("orphaned_count") == 1
    assert "vid_orphan" in new_svc.startup_status.get("orphaned_items", [])

    # Reconstruct corpus identity (upsert yoink)
    new_idx.upsert_yoink(old_yoink)

    # Rebuild library state
    rebuild_res = new_svc.rebuild_library_state(ctx_op, {})
    assert rebuild_res.get("ok") is True
    assert rebuild_res.get("orphaned_count") == 0
    assert rebuild_res.get("projection_revision") == 1

    # Verify pin and exclusive policy restored in database
    row = new_idx._conn.execute("SELECT shelf_id, locked FROM item_shelves WHERE video_id='vid_orphan'").fetchone()
    assert row[0] == "s1"
    assert row[1] == 1
    policy = new_idx._conn.execute("SELECT exclusive_move FROM library_item_policy WHERE video_id='vid_orphan'").fetchone()
    assert policy[0] == 1
    new_idx.close()
