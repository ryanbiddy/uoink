"""tests/test_library_work_rulings.py - Independent verification tests for Phase 2 rulings R1-R5.

Written strictly from docs/library/PHASE2-RULINGS-BRIEF-2026-09-04.md:
- R1 (OBS-2): Unpin and undo invalidate every work row for the item in every run that contains it
  (work blocked, manifest pinned/changed, proposals and previews deleted, run_revision bumped).
- R2 (OBS-4): _ready returns recovery_conflict when recovery_state='conflict' and recovery_pending
  when 'pending', for every endpoint, with the same message shape.
- R3 (deviation 1): expire_attempts and list_work must not call _expire unless _ready passes.
  A list during pending recovery reports the frozen lease state plus recovery_state; an expiry
  call returns recovery_pending and changes nothing.
- R4 (deviation 2): A preview refused because a pin arrived returns error.details.conflicts
  listing each (video_id, shelf_id, pin_kind) the way stale-revision conflicts already do.
- R5 (deviation 3): contract-version constant becomes phase2-v1.2-2026-09-04 and the list_work
  response carries it as contract_version.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from index import Index
import library_cards
import library_work
from library_work import LibraryWorkService, RequestContext, LibraryError


@pytest.fixture
def tmp_path():
    p = Path(tempfile.mkdtemp(prefix="uoink_rulings_test_"))
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


def make_test_environment(
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
        items = [{"video_id": f"vid_r_{i:02d}", "target_shelf": "shelf_alpha"} for i in range(3)]

    for it in items:
        vid = it["video_id"]
        idx.upsert_yoink(dict(
            video_id=vid,
            slug=vid,
            title=f"Title {vid}",
            topic="Topic",
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

    return idx, svc, ctx_op, clock


def submit_assigned_result(svc, ctx_client, work_item, target_shelf="shelf_alpha"):
    card = work_item["card"]
    excerpt = card["excerpts"][0]
    shelf_path = ["Alpha"] if target_shelf == "shelf_alpha" else ["Beta"]
    payload = {
        "work_id": work_item["work_id"],
        "client_id": ctx_client.client_id,
        "attempt_token": work_item["attempt_token"],
        "submission_key": f"sub_{work_item['work_id']}_{work_item['video_id']}",
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


# ---------------------------------------------------------------------------
# R1 (OBS-2): Conservative invalidation on unpin and undo
# ---------------------------------------------------------------------------


def test_r1_unpin_invalidates_work_in_every_run(tmp_path):
    """R1: Unpin invalidates every work row for the item in every run that contains it.

    Work is marked 'blocked', manifest disposition becomes 'changed', proposals and
    previews are deleted, and run_revision is bumped across all containing runs.
    """
    vid = "vid_r1_unpin"
    idx, svc, ctx_op, clock = make_test_environment(tmp_path, items=[{"video_id": vid, "target_shelf": "shelf_alpha"}])
    ctx_user = RequestContext(authenticated=True, client_id="user_admin", session_id="s_user", local_user_confirmed=True)
    ctx_client = RequestContext(authenticated=True, client_id="worker_c1", session_id="s_c1")

    # 1. Prepare two distinct runs containing this item while unpinned
    run_a = "run_r1_unpin_A"
    run_b = "run_r1_unpin_B"
    res_a = svc.prepare_run(ctx_op, {"run_id": run_a, "version_id": "tax_v1", "video_ids": [vid], "prompt_hash": "0" * 64})
    assert res_a.get("ok") is True
    res_b = svc.prepare_run(ctx_op, {"run_id": run_b, "version_id": "tax_v1", "video_ids": [vid], "prompt_hash": "0" * 64})
    assert res_b.get("ok") is True

    # 2. Claim and submit proposals, and generate previews in both runs
    claim_a = svc.claim_work(ctx_client, {"action": "claim", "run_id": run_a, "client_id": "worker_c1", "max_items": 1, "lease_seconds": 600})
    assert claim_a.get("ok") is True
    sub_a = submit_assigned_result(svc, ctx_client, claim_a["work"][0], target_shelf="shelf_alpha")
    assert sub_a.get("ok") is True
    prev_a = svc.preview_apply(ctx_op, {"mode": "preview", "run_id": run_a, "expected_projection_revision": 0})
    assert prev_a.get("ok") is True

    claim_b = svc.claim_work(ctx_client, {"action": "claim", "run_id": run_b, "client_id": "worker_c1", "max_items": 1, "lease_seconds": 600})
    assert claim_b.get("ok") is True
    sub_b = submit_assigned_result(svc, ctx_client, claim_b["work"][0], target_shelf="shelf_alpha")
    assert sub_b.get("ok") is True
    prev_b = svc.preview_apply(ctx_op, {"mode": "preview", "run_id": run_b, "expected_projection_revision": 0})
    assert prev_b.get("ok") is True

    # 3. Pin the item initially
    pin_op = {
        "video_id": vid,
        "shelf_id": "shelf_alpha",
        "action": "pin",
        "expected_projection_revision": 0,
        "operation_key": "op_pin_initial",
    }
    intent_pin = svc.mint_user_intent(ctx_user, {"kind": "pin", "operation": pin_op})
    assert intent_pin.get("ok") is True
    pin_res = svc.pin_shelf(ctx_user, dict(pin_op, user_intent_token=intent_pin["user_intent_token"]))
    assert pin_res.get("ok") is True

    key_a = f"sub_{claim_a['work'][0]['work_id']}_{vid}"
    key_b = f"sub_{claim_b['work'][0]['work_id']}_{vid}"

    # Re-seed proposals and previews in both runs using valid submission keys
    # to verify the subsequent unpin invalidation.
    with idx.write_transaction() as conn:
        conn.execute("UPDATE library_work SET state='ready' WHERE video_id=?", (vid,))
        conn.execute("UPDATE library_manifest SET disposition='waiting' WHERE video_id=?", (vid,))
        conn.execute(
            "INSERT INTO library_proposals(run_id, video_id, shelf_id, version_id, submission_key, is_primary, confidence, evidence_json) VALUES(?,?,?,?,?,?,?,?)",
            (run_a, vid, "shelf_alpha", "tax_v1", key_a, 1, 0.95, "{}"),
        )
        conn.execute(
            "INSERT INTO library_proposals(run_id, video_id, shelf_id, version_id, submission_key, is_primary, confidence, evidence_json) VALUES(?,?,?,?,?,?,?,?)",
            (run_b, vid, "shelf_alpha", "tax_v1", key_b, 1, 0.95, "{}"),
        )
        conn.execute(
            "INSERT INTO library_previews(preview_id, run_id, expected_projection_revision, delta_hash, binding_json, forward_json, inverse_json, summary_json, expires_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            ("prev_a_reseed", run_a, 1, "0" * 64, "{}", "{}", "{}", "{}", clock[0] + 100000),
        )
        conn.execute(
            "INSERT INTO library_previews(preview_id, run_id, expected_projection_revision, delta_hash, binding_json, forward_json, inverse_json, summary_json, expires_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            ("prev_b_reseed", run_b, 1, "0" * 64, "{}", "{}", "{}", "{}", clock[0] + 100000),
        )

    rev_a_before = idx._conn.execute("SELECT run_revision FROM library_runs WHERE run_id=?", (run_a,)).fetchone()[0]
    rev_b_before = idx._conn.execute("SELECT run_revision FROM library_runs WHERE run_id=?", (run_b,)).fetchone()[0]

    # 4. Unpin the item
    unpin_op = {
        "video_id": vid,
        "shelf_id": "shelf_alpha",
        "action": "unpin",
        "expected_projection_revision": 1,
        "operation_key": "op_unpin_action",
    }
    intent_unpin = svc.mint_user_intent(ctx_user, {"kind": "pin", "operation": unpin_op})
    assert intent_unpin.get("ok") is True
    unpin_res = svc.pin_shelf(ctx_user, dict(unpin_op, user_intent_token=intent_unpin["user_intent_token"]))
    assert unpin_res.get("ok") is True

    # 5. Verify invalidation across all runs containing the item
    for r_id, rev_before in ((run_a, rev_a_before), (run_b, rev_b_before)):
        # Work is blocked
        w_state = idx._conn.execute("SELECT state FROM library_work WHERE run_id=? AND video_id=?", (r_id, vid)).fetchone()[0]
        assert w_state == "blocked", f"Run {r_id} work state must be 'blocked', got {w_state}"

        # Manifest disposition is changed
        disp = idx._conn.execute("SELECT disposition FROM library_manifest WHERE run_id=? AND video_id=?", (r_id, vid)).fetchone()[0]
        assert disp == "changed", f"Run {r_id} manifest disposition must be 'changed', got {disp}"

        # Proposals deleted
        props_count = idx._conn.execute("SELECT count(*) FROM library_proposals WHERE run_id=? AND video_id=?", (r_id, vid)).fetchone()[0]
        assert props_count == 0, f"Run {r_id} proposals must be deleted, found {props_count}"

        # Previews deleted
        prev_count = idx._conn.execute("SELECT count(*) FROM library_previews WHERE run_id=?", (r_id,)).fetchone()[0]
        assert prev_count == 0, f"Run {r_id} previews must be deleted, found {prev_count}"

        # Run revision bumped
        r_rev = idx._conn.execute("SELECT run_revision FROM library_runs WHERE run_id=?", (r_id,)).fetchone()[0]
        assert r_rev == rev_before + 1, f"Run {r_id} revision must be bumped from {rev_before} to {rev_before + 1}, got {r_rev}"


def test_r1_undo_invalidates_work_in_every_run(tmp_path):
    """R1: Undo invalidates every work row for the item in every run that contains it.

    Work is marked 'blocked', manifest disposition becomes 'pinned' or 'changed', proposals
    and previews are deleted, and run_revision is bumped across all containing runs.
    """
    vid = "vid_r1_undo"
    idx, svc, ctx_op, clock = make_test_environment(tmp_path, items=[{"video_id": vid, "target_shelf": "shelf_alpha"}])
    ctx_user = RequestContext(authenticated=True, client_id="user_admin", session_id="s_user", local_user_confirmed=True)

    # 1. Perform an operation that can be undone: pin the item
    pin_op = {
        "video_id": vid,
        "shelf_id": "shelf_alpha",
        "action": "pin",
        "expected_projection_revision": 0,
        "operation_key": "op_pin_to_undo",
    }
    intent_pin = svc.mint_user_intent(ctx_user, {"kind": "pin", "operation": pin_op})
    assert intent_pin.get("ok") is True
    pin_res = svc.pin_shelf(ctx_user, dict(pin_op, user_intent_token=intent_pin["user_intent_token"]))
    assert pin_res.get("ok") is True
    apply_id = pin_res["apply_id"]

    # 2. Prepare two runs containing the item
    run_a = "run_r1_undo_A"
    run_b = "run_r1_undo_B"
    res_a = svc.prepare_run(ctx_op, {"run_id": run_a, "version_id": "tax_v1", "video_ids": [vid], "prompt_hash": "0" * 64})
    assert res_a.get("ok") is True
    res_b = svc.prepare_run(ctx_op, {"run_id": run_b, "version_id": "tax_v1", "video_ids": [vid], "prompt_hash": "0" * 64})
    assert res_b.get("ok") is True

    # Seed proposals and previews in both runs
    with idx.write_transaction() as conn:
        conn.execute("UPDATE library_work SET state='ready' WHERE video_id=?", (vid,))
        # Insert a valid attempt and submission to anchor the proposals
        for r_id, tok in ((run_a, "t_undo_a_" + "x" * 35), (run_b, "t_undo_b_" + "x" * 35)):
            w_id = conn.execute("SELECT work_id FROM library_work WHERE run_id=?", (r_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO library_attempts(attempt_token, work_id, attempt_number, packet_generation, client_id, source_revision, taxonomy_revision, lease_expires_ms, lease_max_ms, state) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (tok, w_id, 1, 1, "worker_c1", "0" * 64, "0" * 64, clock[0] + 600000, clock[0] + 1800000, "submitted"),
            )
            s_key = f"sub_undo_{r_id}"
            conn.execute(
                "INSERT INTO library_submissions(submission_key, attempt_token, request_hash, outcome, result_json, response_json, usage_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (s_key, tok, "0" * 64, "accepted", "{}", "{}", "{}", "2026-09-04"),
            )
            conn.execute(
                "INSERT INTO library_proposals(run_id, video_id, shelf_id, version_id, submission_key, is_primary, confidence, evidence_json) VALUES(?,?,?,?,?,?,?,?)",
                (r_id, vid, "shelf_alpha", "tax_v1", s_key, 1, 0.95, "{}"),
            )
            conn.execute(
                "INSERT INTO library_previews(preview_id, run_id, expected_projection_revision, delta_hash, binding_json, forward_json, inverse_json, summary_json, expires_ms) VALUES(?,?,?,?,?,?,?,?,?)",
                (f"prev_undo_{r_id}", r_id, 1, "0" * 64, "{}", "{}", "{}", "{}", clock[0] + 100000),
            )

    rev_a_before = idx._conn.execute("SELECT run_revision FROM library_runs WHERE run_id=?", (run_a,)).fetchone()[0]
    rev_b_before = idx._conn.execute("SELECT run_revision FROM library_runs WHERE run_id=?", (run_b,)).fetchone()[0]

    # 3. Undo the pin
    undo_op = {
        "apply_id": apply_id,
        "operation_key": "op_undo_pin",
        "expected_projection_revision": 1,
    }
    intent_undo = svc.mint_user_intent(ctx_user, {"kind": "undo", "operation": undo_op})
    assert intent_undo.get("ok") is True
    undo_res = svc.undo_apply(ctx_user, dict(undo_op, user_intent_token=intent_undo["user_intent_token"]))
    assert undo_res.get("ok") is True

    # 4. Verify invalidation in all runs containing the item
    for r_id, rev_before in ((run_a, rev_a_before), (run_b, rev_b_before)):
        w_state = idx._conn.execute("SELECT state FROM library_work WHERE run_id=? AND video_id=?", (r_id, vid)).fetchone()[0]
        assert w_state == "blocked", f"Run {r_id} work state must be 'blocked', got {w_state}"

        disp = idx._conn.execute("SELECT disposition FROM library_manifest WHERE run_id=? AND video_id=?", (r_id, vid)).fetchone()[0]
        assert disp in ("changed", "pinned"), f"Run {r_id} manifest disposition must be 'changed' or 'pinned', got {disp}"

        props_count = idx._conn.execute("SELECT count(*) FROM library_proposals WHERE run_id=? AND video_id=?", (r_id, vid)).fetchone()[0]
        assert props_count == 0, f"Run {r_id} proposals must be deleted, found {props_count}"

        prev_count = idx._conn.execute("SELECT count(*) FROM library_previews WHERE run_id=?", (r_id,)).fetchone()[0]
        assert prev_count == 0, f"Run {r_id} previews must be deleted, found {prev_count}"

        r_rev = idx._conn.execute("SELECT run_revision FROM library_runs WHERE run_id=?", (r_id,)).fetchone()[0]
        assert r_rev == rev_before + 1, f"Run {r_id} revision must be bumped from {rev_before} to {rev_before + 1}, got {r_rev}"


# ---------------------------------------------------------------------------
# R2 (OBS-4): Surface stored recovery state from _ready
# ---------------------------------------------------------------------------


def test_r2_ready_surfaces_recovery_conflict_when_state_is_conflict(tmp_path):
    """R2: _ready returns recovery_conflict when recovery_state='conflict' for every endpoint.

    Fails until Astra implements R2 (currently returns recovery_pending).
    """
    idx, svc, ctx_op, _ = make_test_environment(tmp_path)
    ctx_client = RequestContext(authenticated=True, client_id="worker_c1", session_id="s_c1")

    # Set recovery state to conflict
    with idx.write_transaction() as conn:
        conn.execute("UPDATE library_meta SET recovery_state='conflict' WHERE singleton=1")

    # 1. claim_work
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_r2",
        "client_id": "worker_c1",
        "max_items": 1,
        "lease_seconds": 600,
    })
    assert claim_res.get("ok") is False
    assert claim_res.get("error", {}).get("code") == "recovery_conflict", (
        f"claim_work must return 'recovery_conflict' when recovery_state='conflict', got {claim_res}"
    )

    # 2. approve_taxonomy
    tax_res = svc.approve_taxonomy(ctx_op, {
        "version_id": "tax_v2",
        "nodes": [{"shelf_id": "s_new", "path": ["New"], "definition": "def", "include": ["x"], "exclude": ["y"]}],
    })
    assert tax_res.get("ok") is False
    assert tax_res.get("error", {}).get("code") == "recovery_conflict", (
        f"approve_taxonomy must return 'recovery_conflict' when recovery_state='conflict', got {tax_res}"
    )

    # 3. prepare_run
    run_res = svc.prepare_run(ctx_op, {"run_id": "run_r2", "version_id": "tax_v1", "video_ids": ["vid_r_00"], "prompt_hash": "0" * 64})
    assert run_res.get("ok") is False
    assert run_res.get("error", {}).get("code") == "recovery_conflict", (
        f"prepare_run must return 'recovery_conflict' when recovery_state='conflict', got {run_res}"
    )


def test_r2_ready_surfaces_recovery_pending_when_state_is_pending(tmp_path):
    """R2: _ready returns recovery_pending when recovery_state='pending' for every endpoint."""
    idx, svc, ctx_op, _ = make_test_environment(tmp_path)
    ctx_client = RequestContext(authenticated=True, client_id="worker_c1", session_id="s_c1")

    # Set recovery state to pending
    with idx.write_transaction() as conn:
        conn.execute("UPDATE library_meta SET recovery_state='pending' WHERE singleton=1")

    # 1. claim_work
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_r2_pend",
        "client_id": "worker_c1",
        "max_items": 1,
        "lease_seconds": 600,
    })
    assert claim_res.get("ok") is False
    assert claim_res.get("error", {}).get("code") == "recovery_pending", (
        f"claim_work must return 'recovery_pending' when recovery_state='pending', got {claim_res}"
    )

    # 2. prepare_run
    run_res = svc.prepare_run(ctx_op, {"run_id": "run_r2_pend", "version_id": "tax_v1", "video_ids": ["vid_r_00"], "prompt_hash": "0" * 64})
    assert run_res.get("ok") is False
    assert run_res.get("error", {}).get("code") == "recovery_pending", (
        f"prepare_run must return 'recovery_pending' when recovery_state='pending', got {run_res}"
    )


# ---------------------------------------------------------------------------
# R3 (deviation 1): No mutation during pending recovery
# ---------------------------------------------------------------------------


def test_r3_list_work_reports_frozen_leases_without_mutation_during_pending_recovery(tmp_path):
    """R3: list_work must not call _expire unless _ready passes.

    A list during pending recovery reports the frozen lease state plus recovery_state.
    Fails until Astra implements R3 (currently _expire runs unconditionally in list_work).
    """
    vid = "vid_r3_list"
    idx, svc, ctx_op, clock = make_test_environment(tmp_path, items=[{"video_id": vid, "target_shelf": "shelf_alpha"}])
    ctx_client = RequestContext(authenticated=True, client_id="worker_c1", session_id="s_c1")

    run_id = "run_r3_list"
    prep = svc.prepare_run(ctx_op, {"run_id": run_id, "version_id": "tax_v1", "video_ids": [vid], "prompt_hash": "0" * 64})
    assert prep.get("ok") is True

    # Claim the work item
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": run_id,
        "client_id": "worker_c1",
        "max_items": 1,
        "lease_seconds": 600,
    })
    assert claim_res.get("ok") is True
    assert len(claim_res["work"]) == 1
    w_item = claim_res["work"][0]
    work_id = w_item["work_id"]

    # Verify initial state is leased
    w_row = idx._conn.execute("SELECT state FROM library_work WHERE work_id=?", (work_id,)).fetchone()
    assert w_row[0] == "leased"

    # Advance clock past the lease expiration deadline
    clock[0] += 600_000  # 10 minutes past deadline

    # Transition recovery state to pending
    with idx.write_transaction() as conn:
        conn.execute("UPDATE library_meta SET recovery_state='pending' WHERE singleton=1")

    # Call list_work
    list_res = svc.list_work(ctx_op, {"run_id": run_id})
    assert list_res.get("ok") is True
    assert list_res.get("recovery_state") == "pending"

    # Verify that the lease state was FROZEN, not expired to 'ready'
    item_in_list = next((it for it in list_res["items"] if it["work_id"] == work_id), None)
    assert item_in_list is not None
    assert item_in_list["state"] == "leased", (
        f"Work state reported by list_work must remain 'leased' during pending recovery, got '{item_in_list['state']}'"
    )

    # Database verification: work state must still be 'leased' and attempt still 'current'
    work_state_db = idx._conn.execute("SELECT state FROM library_work WHERE work_id=?", (work_id,)).fetchone()[0]
    attempt_state_db = idx._conn.execute("SELECT state FROM library_attempts WHERE work_id=?", (work_id,)).fetchone()[0]
    assert work_state_db == "leased", f"DB library_work.state must remain 'leased', got '{work_state_db}'"
    assert attempt_state_db == "current", f"DB library_attempts.state must remain 'current', got '{attempt_state_db}'"


def test_r3_expire_attempts_returns_recovery_pending_and_changes_nothing(tmp_path):
    """R3: expire_attempts must not call _expire unless _ready passes.

    An expiry call returns recovery_pending and changes nothing.
    Fails until Astra implements R3 (currently returns ok:true with expired count).
    """
    vid = "vid_r3_exp"
    idx, svc, ctx_op, clock = make_test_environment(tmp_path, items=[{"video_id": vid, "target_shelf": "shelf_alpha"}])
    ctx_client = RequestContext(authenticated=True, client_id="worker_c1", session_id="s_c1")

    run_id = "run_r3_exp"
    prep = svc.prepare_run(ctx_op, {"run_id": run_id, "version_id": "tax_v1", "video_ids": [vid], "prompt_hash": "0" * 64})
    assert prep.get("ok") is True

    # Claim work
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": run_id,
        "client_id": "worker_c1",
        "max_items": 1,
        "lease_seconds": 600,
    })
    assert claim_res.get("ok") is True
    w_item = claim_res["work"][0]
    work_id = w_item["work_id"]

    # Advance clock past lease deadline
    clock[0] += 600_000

    # Transition recovery state to pending
    with idx.write_transaction() as conn:
        conn.execute("UPDATE library_meta SET recovery_state='pending' WHERE singleton=1")

    # Call expire_attempts
    exp_res = svc.expire_attempts(ctx_op, {})
    assert exp_res.get("ok") is False, f"expire_attempts must fail during pending recovery, got {exp_res}"
    assert exp_res.get("error", {}).get("code") == "recovery_pending", (
        f"expire_attempts must return error code 'recovery_pending', got {exp_res}"
    )

    # Database verification: lease state must be completely untouched
    work_state_db = idx._conn.execute("SELECT state FROM library_work WHERE work_id=?", (work_id,)).fetchone()[0]
    attempt_state_db = idx._conn.execute("SELECT state FROM library_attempts WHERE work_id=?", (work_id,)).fetchone()[0]
    assert work_state_db == "leased", f"DB library_work.state must remain 'leased', got '{work_state_db}'"
    assert attempt_state_db == "current", f"DB library_attempts.state must remain 'current', got '{attempt_state_db}'"


# ---------------------------------------------------------------------------
# R4 (deviation 2): Pin-invalidated previews name their conflicts
# ---------------------------------------------------------------------------


def test_r4_pin_invalidated_previews_name_conflicts(tmp_path):
    """R4: A preview refused because a pin arrived returns error.details.conflicts

    listing each (video_id, shelf_id, pin_kind) the way stale-revision conflicts already do.
    Fails until Astra implements R4 (currently details is empty).
    """
    vid = "vid_r4_conflict"
    shelf = "shelf_alpha"
    idx, svc, ctx_op, clock = make_test_environment(tmp_path, items=[{"video_id": vid, "target_shelf": shelf}])
    ctx_client = RequestContext(authenticated=True, client_id="worker_c1", session_id="s_c1")
    ctx_user = RequestContext(authenticated=True, client_id="user_admin", session_id="s_user", local_user_confirmed=True)

    run_id = "run_r4"
    prep = svc.prepare_run(ctx_op, {"run_id": run_id, "version_id": "tax_v1", "video_ids": [vid], "prompt_hash": "0" * 64})
    assert prep.get("ok") is True

    # Claim and submit result
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": run_id,
        "client_id": "worker_c1",
        "max_items": 1,
        "lease_seconds": 600,
    })
    assert claim_res.get("ok") is True
    sub_res = submit_assigned_result(svc, ctx_client, claim_res["work"][0], target_shelf=shelf)
    assert sub_res.get("ok") is True

    # Create and approve preview at projection revision 0
    prev_res = svc.preview_apply(ctx_op, {"mode": "preview", "run_id": run_id, "expected_projection_revision": 0})
    assert prev_res.get("ok") is True
    preview_id = prev_res["preview_id"]
    delta_hash = prev_res["delta_hash"]

    app_res = svc.approve_preview(ctx_op, {
        "preview_id": preview_id,
        "delta_hash": delta_hash,
        "operation_key": "op_apply_r4",
        "expected_projection_revision": 0,
    })
    assert app_res.get("ok") is True

    # A pin arrives on that item, invalidating the preview
    pin_op = {
        "video_id": vid,
        "shelf_id": shelf,
        "action": "pin",
        "expected_projection_revision": 0,
        "operation_key": "op_pin_r4_arrival",
    }
    intent_pin = svc.mint_user_intent(ctx_user, {"kind": "pin", "operation": pin_op})
    assert intent_pin.get("ok") is True
    pin_arrival = svc.pin_shelf(ctx_user, dict(pin_op, user_intent_token=intent_pin["user_intent_token"]))
    assert pin_arrival.get("ok") is True

    # Submit the original apply request with the invalidated preview
    apply_res = svc.apply_preview(ctx_op, {
        "mode": "apply",
        "preview_id": preview_id,
        "delta_hash": delta_hash,
        "operation_key": "op_apply_r4",
        "expected_projection_revision": 0,
    })

    assert apply_res.get("ok") is False
    assert apply_res.get("error", {}).get("code") == "preview_conflict"

    # R4 requirement: details.conflicts listing each (video_id, shelf_id, pin_kind)
    details = apply_res.get("error", {}).get("details", {})
    conflicts = details.get("conflicts")
    assert conflicts is not None, f"error.details must contain 'conflicts', got details={details}"
    assert len(conflicts) > 0, f"'conflicts' list must not be empty, got {conflicts}"

    # Match (video_id, shelf_id, pin_kind) represented as tuple/list or dict
    matched = False
    for entry in conflicts:
        if isinstance(entry, (list, tuple)) and len(entry) >= 3:
            if entry[0] == vid and entry[1] == shelf and entry[2] in ("pin", "move", "unpin"):
                matched = True
                break
        elif isinstance(entry, dict):
            if (entry.get("video_id") == vid and entry.get("shelf_id") == shelf and
                    (entry.get("pin_kind") in ("pin", "move", "unpin") or entry.get("action") in ("pin", "move", "unpin"))):
                matched = True
                break
    assert matched, f"Expected conflict entry matching ({vid}, {shelf}, 'pin') in conflicts: {conflicts}"


# ---------------------------------------------------------------------------
# R5 (deviation 3): Contract version constant and list_work field
# ---------------------------------------------------------------------------


def test_r5_contract_version_constant_and_list_work(tmp_path):
    """R5: contract-version constant becomes phase2-v1.2-2026-09-04 and list_work carries it.

    Fails until Astra implements R5 (currently CONTRACT_VERSION is phase2-v1-2026-09-04
    and list_work does not return contract_version).
    """
    # 1. Constant check
    expected_version = "phase2-v1.2-2026-09-04"
    actual_version = getattr(library_work, "CONTRACT_VERSION", None)
    assert actual_version == expected_version, (
        f"library_work.CONTRACT_VERSION must be '{expected_version}', got '{actual_version}'"
    )

    # 2. list_work response field check
    _, svc, ctx_op, _ = make_test_environment(tmp_path)
    res = svc.list_work(ctx_op, {})
    assert res.get("ok") is True
    assert res.get("contract_version") == expected_version, (
        f"list_work response must carry contract_version='{expected_version}', got '{res.get('contract_version')}'"
    )
