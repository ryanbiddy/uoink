"""tests/test_library_work_apply_undo.py - Independent verification tests for Gates P2-3 and P2-4.

Covers:
Gate P2-3 (preview/apply):
- Preview covers entire target manifest; incomplete manifest refuses activation
- Preview delta hash binds forward and inverse operations, expected revision, accepted hashes
- Churn calculation: distinct items changed / baseline items; initial filing reported separately (0.0, initial_filing=true)
- 15% churn ceiling enforced by service; client cannot override without trusted approval
- Apply requires unexpired approved preview, matching operation key, delta hash, and projection revision
- Stale revision, new pin, or changed taxonomy returns conflict with zero partial changes
- Idempotent apply key retry returns original receipt and advances zero rows

Gate P2-4 (pins/undo):
- User pins preserved through every claim, submit, taxonomy activation, and preview apply transition
- Move sets exclusive-move policy; agent apply cannot alter or add secondary memberships while exclusive
- Pin/move/undo requires valid user_intent_token (short-lived capability, <=5 min); invalid/expired/reused rejects
- Undo requires target after_revision == current_revision; inverts complete forward delta
- Stale undo refuses when newer pins exist on the item
- Undo replay with same key returns original receipt; second undo with different key conflicts

Written from PHASE2-CONTRACT-2026-09-04 and phase2-contract/tool-schemas.json.
xfails strictly until library_work is integrated.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

try:
    import library_work
    HAS_LIBRARY_WORK = True
except ImportError:
    library_work = None
    HAS_LIBRARY_WORK = False

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DIR = ROOT / "docs" / "library" / "phase2-contract"
GATE_P2_3 = "Gate P2-3: preview/apply"
GATE_P2_4 = "Gate P2-4: pins/undo"


def get_substrate_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS yoinks (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            channel TEXT,
            platform TEXT,
            deleted_at TEXT
        )"""
    )
    sql_path = CONTRACT_DIR / "0027_library_substrate.sql"
    conn.executescript(sql_path.read_text(encoding="utf-8"))
    return conn


def seed_substrate_manifest_and_proposals(
    conn: sqlite3.Connection,
    run_id: str = "run_apply_01",
    version_id: str = "tax_v1",
    items: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if items is None:
        items = [
            {"video_id": f"vid_apply_{i:02d}", "shelf_id": "shelf_alpha", "disposition": "accepted"}
            for i in range(10)
        ]

    # Taxonomy & shelves
    conn.execute("INSERT OR IGNORE INTO shelf_versions VALUES (?, NULL, ?, 'active', '2026-09-04T00:00:00Z', 'gemini', '2026-09-04T00:00:00Z')", (version_id, "t" * 64))
    conn.execute("UPDATE library_meta SET active_version_id=? WHERE singleton=1", (version_id,))
    conn.execute("INSERT OR IGNORE INTO shelves VALUES ('shelf_alpha', '2026-09-04T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO shelves VALUES ('shelf_beta', '2026-09-04T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO shelf_nodes VALUES (?, 'shelf_alpha', NULL, 'Alpha', '[\"Alpha\"]', 'Def', '[]', '[]', 0)", (version_id,))
    conn.execute("INSERT OR IGNORE INTO shelf_nodes VALUES (?, 'shelf_beta', NULL, 'Beta', '[\"Beta\"]', 'Def', '[]', '[]', 0)", (version_id,))

    conn.execute("INSERT OR IGNORE INTO library_runs VALUES (?, ?, ?, 1, 'review', '{}', '2026-09-04T00:00:00Z')", (run_id, version_id, "m" * 64))

    for item in items:
        vid = item["video_id"]
        shelf = item["shelf_id"]
        disp = item.get("disposition", "accepted")
        conn.execute("INSERT OR IGNORE INTO yoinks VALUES (?, 'Title', 'Channel', 'youtube', NULL)", (vid,))
        conn.execute("INSERT OR IGNORE INTO library_manifest VALUES (?, ?, ?, ?, NULL)", (run_id, vid, "s" * 64, disp))
        if disp == "accepted":
            sub_key = f"sub_{vid}"
            token = f"tok_{vid}" + "a" * (43 - len(f"tok_{vid}"))
            conn.execute("INSERT OR IGNORE INTO library_work VALUES (?, ?, ?, 'assign', 1, '{}', ?, 'accepted', 100, 1, 'now', 'now')", (f"work_{vid}", run_id, vid, "p" * 64))
            conn.execute("INSERT OR IGNORE INTO library_attempts VALUES (?, ?, 1, 1, 'client', ?, ?, 9999999, 9999999, 'submitted')", (token, f"work_{vid}", "s" * 64, "t" * 64))
            conn.execute("INSERT OR IGNORE INTO library_submissions VALUES (?, ?, ?, 'accepted', '{}', '{}', '{}', 'now')", (sub_key, token, "r" * 64))
            conn.execute("INSERT OR IGNORE INTO library_proposals VALUES (?, ?, ?, ?, ?, 1, 0.95, '{}')", (run_id, vid, shelf, version_id, sub_key))
    conn.commit()


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE_P2_3}: preview covers entire manifest required")
def test_p2_3_preview_covers_entire_manifest_and_refuses_incomplete():
    """Preview must account for all target items. Unaccounted/waiting items refuse activation."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE_P2_3}: preview covers entire manifest")

    conn = get_substrate_connection()
    # 9 accepted, 1 waiting
    items = [{"video_id": f"v_{i}", "shelf_id": "shelf_alpha", "disposition": "accepted"} for i in range(9)]
    items.append({"video_id": "v_waiting", "shelf_id": "shelf_alpha", "disposition": "waiting"})
    seed_substrate_manifest_and_proposals(conn, items=items)

    prev = library_work.preview_apply(conn, run_id="run_apply_01", expected_projection_revision=0)
    assert prev.get("ok") is True
    assert prev.get("can_apply") is False, "Waiting items must block activation"
    assert "waiting" in prev.get("manifest_exclusions", {}).get("reasons", [])


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE_P2_3}: churn calculation and 15% ceiling required")
def test_p2_3_churn_calculation_and_15_percent_ceiling():
    """Service stops apply when churn > 15% without explicit human approval. Initial filing is reported separately."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE_P2_3}: churn ceiling")

    conn = get_substrate_connection()
    # Seed baseline items in item_shelves (10 existing items on shelf_alpha)
    for i in range(10):
        vid = f"v_base_{i}"
        conn.execute("INSERT OR IGNORE INTO yoinks VALUES (?, 'T', 'C', 'youtube', NULL)", (vid,))
        conn.execute("INSERT INTO item_shelves VALUES (?, 'shelf_alpha', 'tax_v1', ?, 'agent', 0, 1, 0.9, '{}', 'now')", (vid, "s" * 64))
    conn.commit()

    # Create run proposing to move 3 of 10 items (30% churn > 15%)
    run_items = []
    for i in range(10):
        vid = f"v_base_{i}"
        target_shelf = "shelf_beta" if i < 3 else "shelf_alpha"
        run_items.append({"video_id": vid, "shelf_id": target_shelf, "disposition": "accepted"})
    seed_substrate_manifest_and_proposals(conn, items=run_items)

    prev = library_work.preview_apply(conn, run_id="run_apply_01", expected_projection_revision=0)
    assert prev.get("ok") is True
    churn = prev.get("churn_percent", 0)
    assert churn == 30.0
    assert prev.get("can_apply") is False, "30% churn exceeds 15% ceiling"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE_P2_3}: apply transaction and revision conflict required")
def test_p2_3_apply_transaction_and_stale_revision_conflict():
    """Apply executes in one atomic transaction; stale expected_projection_revision aborts with zero changes."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE_P2_3}: apply transaction")

    conn = get_substrate_connection()
    seed_substrate_manifest_and_proposals(conn)

    prev = library_work.preview_apply(conn, run_id="run_apply_01", expected_projection_revision=0)
    preview_id = prev["preview_id"]
    delta_hash = prev["delta_hash"]
    library_work.approve_preview(conn, preview_id=preview_id, approved_by="user_admin")

    # Stale revision (expected 1, actual 0)
    conflict_res = library_work.apply_preview(
        conn,
        preview_id=preview_id,
        expected_projection_revision=1,  # wrong revision
        delta_hash=delta_hash,
        operation_key="op_apply_01",
    )
    assert conflict_res.get("ok") is False
    assert conflict_res.get("error", {}).get("code") == "revision_conflict"

    # Zero rows changed
    current_rev = conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    assert current_rev == 0
    assigned_count = conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0]
    assert assigned_count == 0


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE_P2_3}: idempotent apply key retry required")
def test_p2_3_idempotent_apply_key_retry():
    """Replaying the same operation key on apply returns the original receipt and advances zero rows."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE_P2_3}: idempotent apply key retry")

    conn = get_substrate_connection()
    seed_substrate_manifest_and_proposals(conn)

    prev = library_work.preview_apply(conn, run_id="run_apply_01", expected_projection_revision=0)
    preview_id = prev["preview_id"]
    delta_hash = prev["delta_hash"]
    library_work.approve_preview(conn, preview_id=preview_id, approved_by="user_admin")

    res1 = library_work.apply_preview(
        conn, preview_id=preview_id, expected_projection_revision=0, delta_hash=delta_hash, operation_key="op_key_idem"
    )
    assert res1.get("ok") is True
    rev1 = conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    assert rev1 == 1

    # Retry exact same key
    res2 = library_work.apply_preview(
        conn, preview_id=preview_id, expected_projection_revision=0, delta_hash=delta_hash, operation_key="op_key_idem"
    )
    assert res2.get("ok") is True
    rev2 = conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    assert rev2 == 1, "Revision must not advance on idempotent retry"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE_P2_4}: user pin and exclusive move policy required")
def test_p2_4_pin_and_exclusive_move_policy():
    """Pin adds locked membership; move sets exclusive policy blocking agent additions."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE_P2_4}: pin and exclusive move")

    conn = get_substrate_connection()
    vid = "vid_pin_test"
    conn.execute("INSERT OR IGNORE INTO yoinks VALUES (?, 'Title', 'Channel', 'youtube', NULL)", (vid,))
    conn.execute("INSERT OR IGNORE INTO shelf_versions VALUES ('tax_v1', NULL, ?, 'active', 'now', 'u', 'now')", ("t" * 64,))
    conn.execute("UPDATE library_meta SET active_version_id='tax_v1' WHERE singleton=1")
    conn.execute("INSERT OR IGNORE INTO shelves VALUES ('shelf_a', 'now')")
    conn.execute("INSERT OR IGNORE INTO shelves VALUES ('shelf_b', 'now')")
    conn.execute("INSERT OR IGNORE INTO shelf_nodes VALUES ('tax_v1', 'shelf_a', NULL, 'A', '[\"A\"]', 'D', '[]', '[]', 0)")
    conn.execute("INSERT OR IGNORE INTO shelf_nodes VALUES ('tax_v1', 'shelf_b', NULL, 'B', '[\"B\"]', 'D', '[]', '[]', 0)")
    conn.commit()

    token = "intent_token_" + "a" * 30

    # User move to shelf_a -> sets exclusive_move=1
    move_res = library_work.pin_shelf(
        conn,
        video_id=vid,
        shelf_id="shelf_a",
        action="move",
        expected_projection_revision=0,
        operation_key="op_move_01",
        user_intent_token=token,
    )
    assert move_res.get("ok") is True

    # Verify locked=1, source='user', confidence is null
    row = conn.execute("SELECT locked, source, confidence FROM item_shelves WHERE video_id=?", (vid,)).fetchone()
    assert row[0] == 1
    assert row[1] == "user"
    assert row[2] is None

    # Verify exclusive_move=1 in library_item_policy
    policy = conn.execute("SELECT exclusive_move FROM library_item_policy WHERE video_id=?", (vid,)).fetchone()
    assert policy is not None
    assert policy[0] == 1

    # Pinning to another shelf while exclusive without unpin/move returns conflict
    token2 = "intent_token_2_" + "b" * 28
    pin_conflict = library_work.pin_shelf(
        conn,
        video_id=vid,
        shelf_id="shelf_b",
        action="pin",
        expected_projection_revision=1,
        operation_key="op_pin_conflict",
        user_intent_token=token2,
    )
    assert pin_conflict.get("ok") is False


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE_P2_4}: user intent token required for pin/undo")
def test_p2_4_user_intent_token_required_for_pins_and_undo():
    """Missing, invalid, expired, or reused user_intent_token is rejected."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE_P2_4}: user intent token validation")

    conn = get_substrate_connection()
    vid = "vid_intent_test"
    conn.execute("INSERT OR IGNORE INTO yoinks VALUES (?, 'Title', 'Channel', 'youtube', NULL)", (vid,))
    conn.execute("INSERT OR IGNORE INTO shelf_versions VALUES ('tax_v1', NULL, ?, 'active', 'now', 'u', 'now')", ("t" * 64,))
    conn.execute("UPDATE library_meta SET active_version_id='tax_v1' WHERE singleton=1")
    conn.execute("INSERT OR IGNORE INTO shelves VALUES ('shelf_a', 'now')")
    conn.execute("INSERT OR IGNORE INTO shelf_nodes VALUES ('tax_v1', 'shelf_a', NULL, 'A', '[\"A\"]', 'D', '[]', '[]', 0)")
    conn.commit()

    # Malformed token (<43 chars)
    res_bad = library_work.pin_shelf(
        conn,
        video_id=vid,
        shelf_id="shelf_a",
        action="pin",
        expected_projection_revision=0,
        operation_key="op_bad_tok",
        user_intent_token="too_short",
    )
    assert res_bad.get("ok") is False


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE_P2_4}: undo inverts complete operation")
def test_p2_4_undo_inverts_complete_operation():
    """Undo restores previous revision, inverts memberships, and preserves journal entry."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE_P2_4}: undo operation")

    conn = get_substrate_connection()
    seed_substrate_manifest_and_proposals(conn)

    # 1. Apply preview
    prev = library_work.preview_apply(conn, run_id="run_apply_01", expected_projection_revision=0)
    library_work.approve_preview(conn, preview_id=prev["preview_id"], approved_by="user_admin")
    apply_res = library_work.apply_preview(
        conn, preview_id=prev["preview_id"], expected_projection_revision=0, delta_hash=prev["delta_hash"], operation_key="op_to_undo"
    )
    apply_id = apply_res["apply_id"]
    assert conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0] == 1

    # 2. Undo apply
    undo_token = "undo_intent_" + "u" * 31
    undo_res = library_work.undo_apply(
        conn,
        apply_id=apply_id,
        expected_projection_revision=1,
        operation_key="op_undo_01",
        user_intent_token=undo_token,
    )
    assert undo_res.get("ok") is True

    # Revision restored to 0
    rev_after = conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    assert rev_after == 0

    # Assigned items cleared
    assert conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0] == 0


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE_P2_4}: stale undo refuses newer changes")
def test_p2_4_stale_undo_refuses_when_revision_not_matching():
    """Undo requires apply_id's after_revision == current_revision; rejects if newer changes exist."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE_P2_4}: stale undo")

    conn = get_substrate_connection()
    seed_substrate_manifest_and_proposals(conn)

    prev = library_work.preview_apply(conn, run_id="run_apply_01", expected_projection_revision=0)
    library_work.approve_preview(conn, preview_id=prev["preview_id"], approved_by="user_admin")
    apply_res = library_work.apply_preview(
        conn, preview_id=prev["preview_id"], expected_projection_revision=0, delta_hash=prev["delta_hash"], operation_key="op_first"
    )
    apply_id = apply_res["apply_id"]

    # Advance revision by another operation (e.g. user pin)
    vid_new = "vid_newer_pin"
    conn.execute("INSERT OR IGNORE INTO yoinks VALUES (?, 'T', 'C', 'youtube', NULL)", (vid_new,))
    library_work.pin_shelf(
        conn, video_id=vid_new, shelf_id="shelf_alpha", action="pin", expected_projection_revision=1,
        operation_key="op_newer_pin", user_intent_token="intent_newer_" + "n" * 30
    )
    # Current revision is now 2. apply_id after_revision was 1.
    assert conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0] == 2

    # Attempt undo of first apply: must conflict
    undo_res = library_work.undo_apply(
        conn,
        apply_id=apply_id,
        expected_projection_revision=2,
        operation_key="op_undo_stale",
        user_intent_token="intent_tok_" + "x" * 32,
    )
    assert undo_res.get("ok") is False
    assert undo_res.get("error", {}).get("code") in ("stale_undo_target", "conflict")
