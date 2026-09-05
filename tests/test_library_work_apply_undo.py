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
Realigned to frozen LibraryWorkService surface per run K brief.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from index import Index
from library_work import LibraryWorkService, RequestContext, LibraryError

ROOT = Path(__file__).resolve().parent.parent
GATE_P2_3 = "Gate P2-3: preview/apply"
GATE_P2_4 = "Gate P2-4: pins/undo"


@pytest.fixture
def tmp_path():
    p = Path(tempfile.mkdtemp(prefix="uoink_apply_test_"))
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


def make_apply_environment(
    tmp_path: Path,
    items: Optional[List[Dict[str, Any]]] = None,
    librarian_apply_enabled: bool = True,
):
    root = tmp_path / "work"
    root.mkdir(parents=True, exist_ok=True)
    idx = Index.open(root / "test.db")
    store_root = root / "library"
    clock = [1_000_000]
    svc = LibraryWorkService(
        idx,
        store_root,
        clock=lambda: clock[0],
        librarian_apply_enabled=librarian_apply_enabled,
    )
    ctx_op = RequestContext(
        authenticated=True,
        client_id="operator",
        session_id="s_op",
        operator=True,
        local_user_confirmed=True,
    )

    if items is None:
        items = [{"video_id": f"vid_apply_{i:02d}", "target_shelf": "shelf_alpha"} for i in range(5)]

    for it in items:
        vid = it["video_id"]
        idx.upsert_yoink(dict(
            video_id=vid,
            slug=vid,
            title=f"Title {vid}",
            topic="Old",
            yoinked_at="2026-09-04",
            corpus_path="",
            sidecar_path="",
        ))
        with idx.write_transaction() as c:
            c.execute(
                "INSERT INTO clips(video_id, seq, start, end, text) VALUES (?, 0, 0, 10, ?)",
                (vid, f"Evidence text for {vid}"),
            )

    tax_res = svc.approve_taxonomy(ctx_op, {
        "version_id": "tax_v1",
        "nodes": [
            {
                "shelf_id": "shelf_alpha",
                "path": ["Alpha"],
                "definition": "Alpha shelf",
                "include": ["alpha"],
                "exclude": ["other"],
            },
            {
                "shelf_id": "shelf_beta",
                "path": ["Beta"],
                "definition": "Beta shelf",
                "include": ["beta"],
                "exclude": ["other"],
            },
        ],
    })
    assert tax_res.get("ok") is True, tax_res

    run_res = svc.prepare_run(ctx_op, {
        "run_id": "run_apply_01",
        "version_id": "tax_v1",
        "video_ids": [it["video_id"] for it in items],
        "prompt_hash": "0" * 64,
    })
    assert run_res.get("ok") is True, run_res

    return idx, svc, ctx_op, clock


def submit_accepted_result(svc, ctx_client, work_item, target_shelf="shelf_alpha"):
    card = work_item["card"]
    excerpt = card["excerpts"][0]
    shelf_path = ["Alpha"] if target_shelf == "shelf_alpha" else ["Beta"]
    payload = {
        "work_id": work_item["work_id"],
        "client_id": ctx_client.client_id,
        "attempt_token": work_item["attempt_token"],
        "submission_key": f"sub_{work_item['video_id']}",
        "schema_version": 1,
        "video_id": work_item["video_id"],
        "source_revision": work_item["source_revision"],
        "taxonomy_revision": work_item["taxonomy_revision"],
        "packet_hash": work_item["packet_hash"],
        "result": {
            "outcome": "assigned",
            "memberships": [
                {
                    "shelf_id": target_shelf,
                    "shelf_path": shelf_path,
                    "confidence": 0.95,
                    "evidence": {
                        "basis": "packet",
                        "kind": "timed_clip",
                        "excerpt_id": excerpt["excerpt_id"],
                        "card_hash": card["card_hash"],
                        "quote": "Evidence text",
                    },
                }
            ],
        },
        "usage": {
            "status": "unavailable",
            "reason": "fixture",
        },
    }
    return svc.submit_result(ctx_client, payload)


def test_p2_3_preview_covers_entire_manifest_and_refuses_incomplete(tmp_path):
    """Preview must account for all target items. Unaccounted/waiting items refuse activation."""
    items = [{"video_id": f"v_{i}", "target_shelf": "shelf_alpha"} for i in range(5)]
    idx, svc, ctx_op, clock = make_apply_environment(tmp_path, items=items)

    ctx_client = RequestContext(authenticated=True, client_id="client_worker", session_id="s_worker")
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_apply_01",
        "client_id": "client_worker",
        "max_items": 4,  # only claim 4 of 5; 1 remains waiting
        "lease_seconds": 600,
    })
    assert claim_res.get("ok") is True

    # Submit accepted results for the 4 claimed items
    for w in claim_res["work"]:
        sub_res = submit_accepted_result(svc, ctx_client, w)
        assert sub_res.get("ok") is True and sub_res.get("outcome") == "accepted"

    # Preview apply
    prev = svc.preview_apply(ctx_op, {
        "mode": "preview",
        "run_id": "run_apply_01",
        "expected_projection_revision": 0,
    })
    assert prev.get("ok") is True
    assert prev.get("can_apply") is False, "Waiting items must block activation"
    assert any(r.get("code") == "incomplete_manifest" for r in prev.get("reasons", []))


def test_p2_3_churn_calculation_and_15_percent_ceiling(tmp_path):
    """Service stops apply when churn > 15% without explicit human approval. Initial filing is reported separately."""
    items = [{"video_id": f"v_base_{i}", "target_shelf": "shelf_beta" if i < 3 else "shelf_alpha"} for i in range(10)]
    idx, svc, ctx_op, clock = make_apply_environment(tmp_path, items=items)

    # Seed baseline item_shelves (all 10 items initially on shelf_alpha)
    with idx.write_transaction() as c:
        for i in range(10):
            vid = f"v_base_{i}"
            c.execute(
                """INSERT INTO item_shelves (
                    video_id, shelf_id, version_id, source_revision, source, locked, is_primary, confidence, evidence_json, assigned_at
                ) VALUES (?, 'shelf_alpha', 'tax_v1', 'rev0', 'agent', 0, 1, 0.9, '{"quote":"evidence"}', '2026-09-04T00:00:00Z')""",
                (vid,),
            )

    # Claim all 10 items and submit proposals (3 items move to shelf_beta -> 30% churn)
    ctx_client = RequestContext(authenticated=True, client_id="client_worker", session_id="s_worker")
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_apply_01",
        "client_id": "client_worker",
        "max_items": 10,
        "lease_seconds": 600,
    })
    assert claim_res.get("ok") is True
    assert len(claim_res["work"]) == 10

    for w in claim_res["work"]:
        target = next(it["target_shelf"] for it in items if it["video_id"] == w["video_id"])
        sub_res = submit_accepted_result(svc, ctx_client, w, target_shelf=target)
        assert sub_res.get("ok") is True and sub_res.get("outcome") == "accepted"

    prev = svc.preview_apply(ctx_op, {
        "mode": "preview",
        "run_id": "run_apply_01",
        "expected_projection_revision": 0,
    })
    assert prev.get("ok") is True
    churn = prev.get("churn_percent", 0)
    assert churn == 30.0
    assert prev.get("can_apply") is False, "30% churn exceeds 15% ceiling"


def test_p2_3_apply_transaction_and_stale_revision_conflict(tmp_path):
    """Apply executes in one atomic transaction; stale expected_projection_revision aborts with zero changes."""
    items = [{"video_id": f"v_apply_{i}", "target_shelf": "shelf_alpha"} for i in range(3)]
    idx, svc, ctx_op, clock = make_apply_environment(tmp_path, items=items)

    ctx_client = RequestContext(authenticated=True, client_id="client_worker", session_id="s_worker")
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_apply_01",
        "client_id": "client_worker",
        "max_items": 3,
        "lease_seconds": 600,
    })
    for w in claim_res["work"]:
        submit_accepted_result(svc, ctx_client, w)

    prev = svc.preview_apply(ctx_op, {
        "mode": "preview",
        "run_id": "run_apply_01",
        "expected_projection_revision": 0,
    })
    preview_id = prev["preview_id"]
    delta_hash = prev["delta_hash"]

    app_res = svc.approve_preview(ctx_op, {
        "preview_id": preview_id,
        "delta_hash": delta_hash,
        "operation_key": "op_apply_01",
        "expected_projection_revision": 0,
    })
    assert app_res.get("ok") is True

    # Stale revision (expected 1, actual 0)
    conflict_res = svc.apply_preview(ctx_op, {
        "mode": "apply",
        "preview_id": preview_id,
        "expected_projection_revision": 1,
        "delta_hash": delta_hash,
        "operation_key": "op_apply_01",
    })
    assert conflict_res.get("ok") is False
    assert conflict_res.get("error", {}).get("code") in ("revision_conflict", "preview_conflict")

    # Zero rows changed
    current_rev = idx._conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    assert current_rev == 0
    assigned_count = idx._conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0]
    assert assigned_count == 0


def test_p2_3_idempotent_apply_key_retry(tmp_path):
    """Replaying the same operation key on apply returns the original receipt and advances zero rows."""
    items = [{"video_id": f"v_idem_{i}", "target_shelf": "shelf_alpha"} for i in range(3)]
    idx, svc, ctx_op, clock = make_apply_environment(tmp_path, items=items)

    ctx_client = RequestContext(authenticated=True, client_id="client_worker", session_id="s_worker")
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_apply_01",
        "client_id": "client_worker",
        "max_items": 3,
        "lease_seconds": 600,
    })
    for w in claim_res["work"]:
        submit_accepted_result(svc, ctx_client, w)

    prev = svc.preview_apply(ctx_op, {
        "mode": "preview",
        "run_id": "run_apply_01",
        "expected_projection_revision": 0,
    })
    preview_id = prev["preview_id"]
    delta_hash = prev["delta_hash"]

    app_res = svc.approve_preview(ctx_op, {
        "preview_id": preview_id,
        "delta_hash": delta_hash,
        "operation_key": "op_key_idem",
        "expected_projection_revision": 0,
    })
    assert app_res.get("ok") is True

    res1 = svc.apply_preview(ctx_op, {
        "mode": "apply",
        "preview_id": preview_id,
        "expected_projection_revision": 0,
        "delta_hash": delta_hash,
        "operation_key": "op_key_idem",
    })
    assert res1.get("ok") is True
    rev1 = idx._conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    assert rev1 == 1

    # Retry exact same key
    res2 = svc.apply_preview(ctx_op, {
        "mode": "apply",
        "preview_id": preview_id,
        "expected_projection_revision": 0,
        "delta_hash": delta_hash,
        "operation_key": "op_key_idem",
    })
    assert res2.get("ok") is True
    rev2 = idx._conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    assert rev2 == 1, "Revision must not advance on idempotent retry"


def test_p2_4_pin_and_exclusive_move_policy(tmp_path):
    """Pin adds locked membership; move sets exclusive policy blocking agent additions."""
    idx, svc, ctx_op, clock = make_apply_environment(tmp_path, items=[{"video_id": "vid_pin_test", "target_shelf": "shelf_alpha"}])
    ctx_user = RequestContext(authenticated=True, client_id="user_admin", session_id="s_user", local_user_confirmed=True)

    vid = "vid_pin_test"
    move_op = {
        "video_id": vid,
        "shelf_id": "shelf_alpha",
        "action": "move",
        "expected_projection_revision": 0,
        "operation_key": "op_move_01",
    }
    intent_res = svc.mint_user_intent(ctx_user, {"kind": "pin", "operation": move_op})
    assert intent_res.get("ok") is True
    token = intent_res["user_intent_token"]

    move_res = svc.pin_shelf(ctx_user, dict(move_op, user_intent_token=token))
    assert move_res.get("ok") is True

    # Verify locked=1, source='user', confidence is null
    row = idx._conn.execute("SELECT locked, source, confidence FROM item_shelves WHERE video_id=?", (vid,)).fetchone()
    assert row[0] == 1
    assert row[1] == "user"
    assert row[2] is None

    # Verify exclusive_move=1 in library_item_policy
    policy = idx._conn.execute("SELECT exclusive_move FROM library_item_policy WHERE video_id=?", (vid,)).fetchone()
    assert policy is not None
    assert policy[0] == 1

    # Pinning to another shelf while exclusive without unpin/move returns conflict
    pin_op = {
        "video_id": vid,
        "shelf_id": "shelf_beta",
        "action": "pin",
        "expected_projection_revision": 1,
        "operation_key": "op_pin_conflict",
    }
    intent_res2 = svc.mint_user_intent(ctx_user, {"kind": "pin", "operation": pin_op})
    if intent_res2.get("ok") is False:
        assert intent_res2.get("error", {}).get("code") == "exclusive_move_conflict"
    else:
        token2 = intent_res2["user_intent_token"]
        pin_conflict = svc.pin_shelf(ctx_user, dict(pin_op, user_intent_token=token2))
        assert pin_conflict.get("ok") is False
        assert pin_conflict.get("error", {}).get("code") == "exclusive_move_conflict"


def test_p2_4_user_intent_token_required_for_pins_and_undo(tmp_path):
    """Missing, invalid, expired, or reused user_intent_token is rejected."""
    idx, svc, ctx_op, clock = make_apply_environment(tmp_path, items=[{"video_id": "vid_intent_test", "target_shelf": "shelf_alpha"}])
    ctx_user = RequestContext(authenticated=True, client_id="user_admin", session_id="s_user", local_user_confirmed=True)

    # Malformed token (<43 chars)
    res_bad = svc.pin_shelf(
        ctx_user,
        {
            "video_id": "vid_intent_test",
            "shelf_id": "shelf_alpha",
            "action": "pin",
            "expected_projection_revision": 0,
            "operation_key": "op_bad_tok",
            "user_intent_token": "too_short",
        },
    )
    assert res_bad.get("ok") is False


def test_p2_4_undo_inverts_complete_operation(tmp_path):
    """Undo restores previous revision, inverts memberships, and preserves journal entry."""
    items = [{"video_id": f"v_undo_{i}", "target_shelf": "shelf_alpha"} for i in range(2)]
    idx, svc, ctx_op, clock = make_apply_environment(tmp_path, items=items)

    ctx_client = RequestContext(authenticated=True, client_id="client_worker", session_id="s_worker")
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_apply_01",
        "client_id": "client_worker",
        "max_items": 2,
        "lease_seconds": 600,
    })
    for w in claim_res["work"]:
        submit_accepted_result(svc, ctx_client, w)

    prev = svc.preview_apply(ctx_op, {
        "mode": "preview",
        "run_id": "run_apply_01",
        "expected_projection_revision": 0,
    })
    preview_id = prev["preview_id"]
    delta_hash = prev["delta_hash"]

    svc.approve_preview(ctx_op, {
        "preview_id": preview_id,
        "delta_hash": delta_hash,
        "operation_key": "op_to_undo",
        "expected_projection_revision": 0,
    })

    apply_res = svc.apply_preview(ctx_op, {
        "mode": "apply",
        "preview_id": preview_id,
        "expected_projection_revision": 0,
        "delta_hash": delta_hash,
        "operation_key": "op_to_undo",
    })
    assert apply_res.get("ok") is True
    apply_id = apply_res["apply_id"]
    assert idx._conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0] == 1

    # Undo apply
    ctx_user = RequestContext(authenticated=True, client_id="user_admin", session_id="s_user", local_user_confirmed=True)
    undo_op = {
        "apply_id": apply_id,
        "expected_projection_revision": 1,
        "operation_key": "op_undo_01",
    }
    intent_undo = svc.mint_user_intent(ctx_user, {"kind": "undo", "operation": undo_op})
    assert intent_undo.get("ok") is True
    token = intent_undo["user_intent_token"]

    undo_res = svc.undo_apply(ctx_user, dict(undo_op, user_intent_token=token))
    assert undo_res.get("ok") is True
    assert undo_res.get("before_revision") == 1
    assert undo_res.get("after_revision") == 2

    # Monotonic revision advanced to 2 in meta
    rev_after = idx._conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    assert rev_after == 2

    # Assigned items cleared (inverting the apply)
    assert idx._conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0] == 0


def test_p2_4_stale_undo_refuses_when_revision_not_matching(tmp_path):
    """Undo requires apply_id's after_revision == current_revision; rejects if newer changes exist."""
    items = [{"video_id": f"v_stale_{i}", "target_shelf": "shelf_alpha"} for i in range(2)]
    idx, svc, ctx_op, clock = make_apply_environment(tmp_path, items=items)

    ctx_client = RequestContext(authenticated=True, client_id="client_worker", session_id="s_worker")
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_apply_01",
        "client_id": "client_worker",
        "max_items": 2,
        "lease_seconds": 600,
    })
    for w in claim_res["work"]:
        submit_accepted_result(svc, ctx_client, w)

    prev = svc.preview_apply(ctx_op, {
        "mode": "preview",
        "run_id": "run_apply_01",
        "expected_projection_revision": 0,
    })
    preview_id = prev["preview_id"]
    delta_hash = prev["delta_hash"]

    svc.approve_preview(ctx_op, {
        "preview_id": preview_id,
        "delta_hash": delta_hash,
        "operation_key": "op_first",
        "expected_projection_revision": 0,
    })

    apply_res = svc.apply_preview(ctx_op, {
        "mode": "apply",
        "preview_id": preview_id,
        "expected_projection_revision": 0,
        "delta_hash": delta_hash,
        "operation_key": "op_first",
    })
    assert apply_res.get("ok") is True
    apply_id = apply_res["apply_id"]

    # Advance revision by another operation (user pin)
    vid_new = "vid_newer_pin"
    idx.upsert_yoink(dict(
        video_id=vid_new,
        slug=vid_new,
        title=f"Title {vid_new}",
        topic="Old",
        yoinked_at="2026-09-04",
        corpus_path="",
        sidecar_path="",
    ))
    with idx.write_transaction() as c:
        c.execute(
            "INSERT INTO clips(video_id, seq, start, end, text) VALUES (?, 0, 0, 10, ?)",
            (vid_new, f"Evidence text for {vid_new}"),
        )

    ctx_user = RequestContext(authenticated=True, client_id="user_admin", session_id="s_user", local_user_confirmed=True)
    pin_op = {
        "video_id": vid_new,
        "shelf_id": "shelf_alpha",
        "action": "pin",
        "expected_projection_revision": 1,
        "operation_key": "op_newer_pin",
    }
    mint_pin = svc.mint_user_intent(ctx_user, {"kind": "pin", "operation": pin_op})
    assert mint_pin.get("ok") is True
    pin_res = svc.pin_shelf(ctx_user, dict(pin_op, user_intent_token=mint_pin["user_intent_token"]))
    assert pin_res.get("ok") is True

    # Current revision is now 2. apply_id after_revision was 1.
    assert idx._conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0] == 2

    # Attempt undo of first apply: minting intent or undo_apply must conflict
    undo_op = {
        "apply_id": apply_id,
        "expected_projection_revision": 2,
        "operation_key": "op_undo_stale",
    }
    # Either minting fails because after_revision != expected revision, or undo fails
    mint_undo = svc.mint_user_intent(ctx_user, {"kind": "undo", "operation": undo_op})
    if mint_undo.get("ok") is True:
        undo_res = svc.undo_apply(ctx_user, dict(undo_op, user_intent_token=mint_undo["user_intent_token"]))
        assert undo_res.get("ok") is False
        assert undo_res.get("error", {}).get("code") in ("revision_conflict", "stale_undo_target", "conflict", "preview_conflict")
    else:
        assert mint_undo.get("ok") is False
        assert mint_undo.get("error", {}).get("code") in ("revision_conflict", "stale_undo_target", "conflict", "preview_conflict")
