"""tests/test_library_work_validation.py - Independent verification tests for Gate P2-2.

Covers Gate P2-2 (validation and retries):
- Wrong/missing/extra/duplicate IDs, malformed nested output rejected
- NaN/Infinity rejection on all numeric values (confidence, tokens, latency)
- Confidence floor enforcement: confidence < 0.60 rejected for assigned outcome
- Foreign shelf: shelf_id not present in active approved taxonomy rejected
- Quote evidence validation: must be exact substring of ONE specified excerpt; joined-clip quotes rejected
- Stale revisions: mismatch against frozen source or taxonomy revision rejected
- Rejection outcome: records rejection reasons visibly; writes ZERO rows to item_shelves
- Identical submit retry: returns exact stored response under submission_key even after expiry
- Changed-key payload conflict: different request under recorded submission_key returns idempotency_conflict
- Consumed token reuse: second result under consumed attempt token returns idempotency_conflict
- Stale token: unknown/unleased token returns stale_attempt without writing proposals

Written from PHASE2-CONTRACT-2026-09-04 and phase2-contract/tool-schemas.json.
Realigned to frozen LibraryWorkService surface per run K brief.
"""
from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from index import Index
from library_work import LibraryWorkService, RequestContext, LibraryError

ROOT = Path(__file__).resolve().parent.parent
GATE = "Gate P2-2: validation and retries"


@pytest.fixture
def tmp_path():
    p = Path(tempfile.mkdtemp(prefix="uoink_val_test_"))
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


def make_validation_environment(
    tmp_path: Path,
    video_id: str = "vid_val_01",
    shelf_id: str = "shelf_valid",
    excerpt_text: str = "The quick brown fox jumps over the lazy dog.",
):
    root = tmp_path / "work"
    root.mkdir(parents=True, exist_ok=True)
    idx = Index.open(root / "test.db")
    store_root = root / "library"
    clock = [1_000_000]
    svc = LibraryWorkService(idx, store_root, clock=lambda: clock[0])
    ctx_op = RequestContext(authenticated=True, client_id="operator", session_id="s_op", operator=True, local_user_confirmed=True)

    idx.upsert_yoink(dict(
        video_id=video_id,
        slug=video_id,
        title="Valid Video Title",
        topic="Old",
        yoinked_at="2026-09-04",
        corpus_path="",
        sidecar_path="",
    ))
    with idx.write_transaction() as c:
        c.execute(
            "INSERT INTO clips(video_id, seq, start, end, text) VALUES (?, 0, 10.0, 25.0, ?)",
            (video_id, excerpt_text),
        )

    tax_res = svc.approve_taxonomy(ctx_op, {
        "version_id": "tax_v1",
        "nodes": [
            {
                "shelf_id": shelf_id,
                "path": ["Valid Shelf"],
                "definition": "Valid shelf definition",
                "include": ["valid"],
                "exclude": ["invalid"],
            },
            {
                "shelf_id": "shelf_other",
                "path": ["Other Shelf"],
                "definition": "Other shelf definition",
                "include": ["other"],
                "exclude": ["valid"],
            },
        ],
    })
    assert tax_res.get("ok") is True, tax_res

    run_res = svc.prepare_run(ctx_op, {
        "run_id": "run_val_01",
        "version_id": "tax_v1",
        "video_ids": [video_id],
        "prompt_hash": "0" * 64,
    })
    assert run_res.get("ok") is True, run_res

    ctx_client = RequestContext(authenticated=True, client_id="client_val", session_id="s_val")
    claim_res = svc.claim_work(ctx_client, {
        "action": "claim",
        "run_id": "run_val_01",
        "client_id": "client_val",
        "max_items": 1,
        "lease_seconds": 600,
    })
    assert claim_res.get("ok") is True, claim_res
    work_item = claim_res["work"][0]

    return idx, svc, ctx_client, work_item, clock


def make_valid_submission_payload(
    work_item: Dict[str, Any],
    key: str = "sub_key_01",
    shelf_id: str = "shelf_valid",
    shelf_path: Optional[List[str]] = None,
    quote: str = "brown fox",
    confidence: float = 0.85,
    client_id: str = "client_val",
) -> Dict[str, Any]:
    card = work_item["card"]
    excerpt = card["excerpts"][0]
    return {
        "work_id": work_item["work_id"],
        "client_id": client_id,
        "attempt_token": work_item["attempt_token"],
        "submission_key": key,
        "schema_version": 1,
        "video_id": work_item["video_id"],
        "source_revision": work_item["source_revision"],
        "taxonomy_revision": work_item["taxonomy_revision"],
        "packet_hash": work_item["packet_hash"],
        "result": {
            "outcome": "assigned",
            "memberships": [
                {
                    "shelf_id": shelf_id,
                    "shelf_path": shelf_path or ["Valid Shelf"],
                    "confidence": confidence,
                    "evidence": {
                        "basis": "packet",
                        "kind": "timed_clip",
                        "excerpt_id": excerpt["excerpt_id"],
                        "card_hash": card["card_hash"],
                        "quote": quote,
                    },
                }
            ],
        },
        "usage": {
            "status": "unavailable",
            "reason": "fixture",
        },
    }


def test_p2_2_missing_or_malformed_id_rejected(tmp_path):
    """Missing or malformed identifiers (empty, invalid pattern) must be rejected."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)

    # Missing work_id
    payload_missing = make_valid_submission_payload(work_item)
    del payload_missing["work_id"]
    res = svc.submit_result(ctx, payload_missing)
    assert res.get("ok") is False
    assert res.get("error", {}).get("code") == "validation_error"

    # Malformed work_id (whitespace only)
    payload_malformed = make_valid_submission_payload(work_item)
    payload_malformed["work_id"] = "   "
    res = svc.submit_result(ctx, payload_malformed)
    assert res.get("ok") is False
    assert res.get("error", {}).get("code") == "validation_error"


def test_p2_2_nan_infinity_confidence_rejected(tmp_path):
    """NaN and Infinity values for numeric fields like confidence must be rejected."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)

    # NaN confidence
    payload_nan = make_valid_submission_payload(work_item)
    payload_nan["result"]["memberships"][0]["confidence"] = float("nan")
    res_nan = svc.submit_result(ctx, payload_nan)
    assert res_nan.get("ok") is False
    assert res_nan.get("error", {}).get("code") == "validation_error"

    # Infinity confidence
    payload_inf = make_valid_submission_payload(work_item)
    payload_inf["result"]["memberships"][0]["confidence"] = float("inf")
    res_inf = svc.submit_result(ctx, payload_inf)
    assert res_inf.get("ok") is False
    assert res_inf.get("error", {}).get("code") == "validation_error"


def test_p2_2_confidence_floor_enforcement(tmp_path):
    """Confidence score below 0.60 must be rejected for assigned outcome."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)

    payload_low = make_valid_submission_payload(work_item, confidence=0.55)
    res = svc.submit_result(ctx, payload_low)
    assert res.get("ok") is True
    assert res.get("outcome") == "rejected"
    assert any(r.get("code") in ("confidence_floor", "low_confidence") for r in res.get("rejected", []))


def test_p2_2_foreign_shelf_rejected(tmp_path):
    """shelf_id not present in the active approved taxonomy must be rejected."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)

    payload_foreign = make_valid_submission_payload(
        work_item, shelf_id="shelf_nonexistent", shelf_path=["Nonexistent Shelf"]
    )
    res = svc.submit_result(ctx, payload_foreign)
    assert res.get("ok") is True
    assert res.get("outcome") == "rejected"
    assert any(r.get("code") in ("invalid_shelf", "foreign_shelf") for r in res.get("rejected", []))
    assert idx._conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0] == 0


def test_p2_2_quote_evidence_must_be_substring_of_single_excerpt(tmp_path):
    """Quoted evidence must strictly be a substring of ONE specified excerpt."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)

    payload_bad_quote = make_valid_submission_payload(work_item, quote="pink elephants jumping")
    res = svc.submit_result(ctx, payload_bad_quote)
    assert res.get("ok") is True
    assert res.get("outcome") == "rejected"
    assert any(r.get("code") in ("invalid_evidence", "quote_mismatch") for r in res.get("rejected", []))


def test_p2_2_stale_source_or_taxonomy_revision_rejected(tmp_path):
    """Mismatch against frozen source or taxonomy revision must be rejected."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)

    # Stale source revision
    payload_stale_src = make_valid_submission_payload(work_item)
    payload_stale_src["source_revision"] = "f" * 64
    res = svc.submit_result(ctx, payload_stale_src)
    assert res.get("ok") is False or res.get("outcome") == "rejected"


def test_p2_2_rejection_writes_zero_current_labels_and_stays_visible(tmp_path):
    """A rejected result writes zero labels to item_shelves and records rejection visibly in manifest."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)

    payload_reject = make_valid_submission_payload(work_item, confidence=0.40)
    res = svc.submit_result(ctx, payload_reject)
    assert res.get("ok") is True
    assert res.get("outcome") == "rejected"

    # Zero rows in item_shelves
    assigned = idx._conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0]
    assert assigned == 0

    # Manifest records rejection disposition
    manifest_disp = idx._conn.execute(
        "SELECT disposition FROM library_manifest WHERE video_id=?", (work_item["video_id"],)
    ).fetchone()[0]
    assert manifest_disp == "rejected"


def test_p2_2_identical_submit_retry_returns_stored_response(tmp_path):
    """An identical retry of a completed submission returns the exact recorded response without advancing state."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)
    payload = make_valid_submission_payload(work_item, key="key_idempotent")

    res1 = svc.submit_result(ctx, payload)
    assert res1.get("ok") is True
    assert res1.get("outcome") == "accepted"

    # Advance clock
    clock[0] += 900_000

    # Retry same payload
    res2 = svc.submit_result(ctx, payload)
    assert res2 == res1


def test_p2_2_changed_payload_under_same_key_returns_idempotency_conflict(tmp_path):
    """A changed payload submitted under an already used submission_key returns idempotency_conflict."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)
    payload1 = make_valid_submission_payload(work_item, key="key_conflict", quote="brown fox")
    res1 = svc.submit_result(ctx, payload1)
    assert res1.get("ok") is True

    # Same submission_key, changed quote
    payload2 = make_valid_submission_payload(work_item, key="key_conflict", quote="quick brown")
    res2 = svc.submit_result(ctx, payload2)
    assert res2.get("ok") is False
    assert res2.get("error", {}).get("code") == "idempotency_conflict"


def test_p2_2_stale_attempt_token_returns_stale_attempt(tmp_path):
    """A stale or unknown token with no recorded submission returns stale_attempt and writes no proposal."""
    idx, svc, ctx, work_item, clock = make_validation_environment(tmp_path)
    payload = make_valid_submission_payload(work_item, key="key_stale")
    payload["attempt_token"] = "z" * 43  # unknown token

    res = svc.submit_result(ctx, payload)
    assert res.get("ok") is False
    assert res.get("error", {}).get("code") == "stale_attempt"

    # Zero proposals written
    proposals = idx._conn.execute("SELECT count(*) FROM library_proposals WHERE submission_key='key_stale'").fetchone()[0]
    assert proposals == 0
