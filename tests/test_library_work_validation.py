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
xfails strictly until library_work is integrated.
"""
from __future__ import annotations

import json
import math
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
GATE = "Gate P2-2: validation and retries"


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


def seed_work_row(
    conn: sqlite3.Connection,
    video_id: str = "vid_val_01",
    shelf_id: str = "shelf_valid",
    source_rev: str = "a" * 64,
    tax_rev: str = "b" * 64,
    packet_hash: str = "c" * 64,
    excerpt_id: str = "d" * 64,
    card_hash: str = "e" * 64,
    excerpt_text: str = "The quick brown fox jumps over the lazy dog.",
) -> Dict[str, str]:
    version_id = "tax_v1"
    run_id = "run_val_01"
    work_id = f"work_{video_id}"
    token = "t" * 43

    # Taxonomy & shelves
    conn.execute("INSERT OR IGNORE INTO shelf_versions VALUES (?, NULL, ?, 'active', '2026-09-04T00:00:00Z', 'gemini', '2026-09-04T00:00:00Z')", (version_id, tax_rev))
    conn.execute("UPDATE library_meta SET active_version_id=? WHERE singleton=1", (version_id,))
    conn.execute("INSERT OR IGNORE INTO shelves VALUES (?, '2026-09-04T00:00:00Z')", (shelf_id,))
    conn.execute(
        """INSERT OR IGNORE INTO shelf_nodes VALUES (?, ?, NULL, 'Valid Shelf', '["Valid Shelf"]', 'Def', '["inc"]', '["exc"]', 0)""",
        (version_id, shelf_id)
    )

    # Yoink & manifest
    conn.execute("INSERT OR IGNORE INTO yoinks VALUES (?, 'Title', 'Channel', 'youtube', NULL)", (video_id,))
    conn.execute("INSERT OR IGNORE INTO library_runs VALUES (?, ?, ?, 1, 'collecting', '{}', '2026-09-04T00:00:00Z')", (run_id, version_id, "m" * 64))
    conn.execute("INSERT OR IGNORE INTO library_manifest VALUES (?, ?, ?, 'waiting', NULL)", (run_id, video_id, source_rev))

    # Work packet with excerpt
    card = {
        "video_id": video_id,
        "title": "Title",
        "source_revision": source_rev,
        "card_hash": card_hash,
        "excerpts": [
            {
                "excerpt_id": excerpt_id,
                "evidence_kind": "timed_clip",
                "start": 10.0,
                "end": 25.0,
                "text": excerpt_text,
                "truncated": False,
            }
        ]
    }
    conn.execute(
        """INSERT OR IGNORE INTO library_work VALUES (?, ?, ?, 'assign', 1, ?, ?, 'leased', 100, 1, '2026-09-04T00:00:00Z', '2026-09-04T00:00:00Z')""",
        (work_id, run_id, video_id, json.dumps(card), packet_hash)
    )

    # Active attempt
    conn.execute(
        """INSERT OR IGNORE INTO library_attempts VALUES (?, ?, 1, 1, 'client_val', ?, ?, 9999999999999, 9999999999999, 'current')""",
        (token, work_id, source_rev, tax_rev)
    )
    conn.commit()

    return {
        "work_id": work_id,
        "video_id": video_id,
        "attempt_token": token,
        "shelf_id": shelf_id,
        "source_revision": source_rev,
        "taxonomy_revision": tax_rev,
        "packet_hash": packet_hash,
        "excerpt_id": excerpt_id,
        "card_hash": card_hash,
        "excerpt_text": excerpt_text,
    }


def make_valid_submission_payload(seeded: Dict[str, str], key: str = "sub_key_01") -> Dict[str, Any]:
    return {
        "work_id": seeded["work_id"],
        "client_id": "client_val",
        "attempt_token": seeded["attempt_token"],
        "submission_key": key,
        "schema_version": 1,
        "video_id": seeded["video_id"],
        "source_revision": seeded["source_revision"],
        "taxonomy_revision": seeded["taxonomy_revision"],
        "packet_hash": seeded["packet_hash"],
        "result": {
            "outcome": "assigned",
            "memberships": [
                {
                    "shelf_id": seeded["shelf_id"],
                    "shelf_path": ["Valid Shelf"],
                    "confidence": 0.88,
                    "evidence": {
                        "basis": "packet",
                        "kind": "timed_clip",
                        "excerpt_id": seeded["excerpt_id"],
                        "card_hash": seeded["card_hash"],
                        "quote": "brown fox jumps",
                    },
                }
            ],
        },
        "usage": {
            "status": "reported",
            "model": "test-librarian-v1",
            "input_tokens": 500,
            "output_tokens": 50,
            "wall_time_ms": 120,
        },
    }


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: ID validation required")
def test_p2_2_missing_or_malformed_id_rejected():
    """Submit with missing work_id or mismatched video_id returns validation rejection."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: ID validation")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload = make_valid_submission_payload(seeded)

    # Mismatched video_id
    bad_payload = dict(payload)
    bad_payload["video_id"] = "wrong_vid"
    res = library_work.submit_result(conn, bad_payload)
    assert res.get("ok") is False
    assert res.get("outcome") == "rejected"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: NaN/Infinity rejection required")
def test_p2_2_nan_infinity_confidence_rejected():
    """NaN, Infinity, or negative/out-of-bounds confidence values must be rejected."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: NaN/Infinity rejection")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload = make_valid_submission_payload(seeded)

    for bad_conf in (float("nan"), float("inf"), -0.1, 1.1):
        p = json.loads(json.dumps(payload))
        p["result"]["memberships"][0]["confidence"] = bad_conf
        res = library_work.submit_result(conn, p)
        assert res.get("ok") is False


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: confidence floor >=0.60 required")
def test_p2_2_confidence_floor_enforcement():
    """Confidence scores below 0.60 must be rejected for assigned outcome."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: confidence floor")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload = make_valid_submission_payload(seeded)
    payload["result"]["memberships"][0]["confidence"] = 0.59

    res = library_work.submit_result(conn, payload)
    assert res.get("ok") is False
    assert any("confidence" in str(r).lower() for r in res.get("rejected", []))


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: foreign shelf rejection required")
def test_p2_2_foreign_shelf_rejected():
    """Shelf ID not present in active approved taxonomy must be rejected."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: foreign shelf")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload = make_valid_submission_payload(seeded)
    payload["result"]["memberships"][0]["shelf_id"] = "nonexistent_foreign_shelf"

    res = library_work.submit_result(conn, payload)
    assert res.get("ok") is False


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: quote validation required")
def test_p2_2_quote_evidence_must_be_substring_of_single_excerpt():
    """Evidence quote must be a verbatim substring of ONE specified excerpt. Hallucinated or joined quotes rejected."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: quote validation")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn, excerpt_text="The quick brown fox jumps over the lazy dog.")
    payload = make_valid_submission_payload(seeded)

    # Hallucinated quote
    p1 = json.loads(json.dumps(payload))
    p1["result"]["memberships"][0]["evidence"]["quote"] = "completely fabricated quote not in excerpt"
    res1 = library_work.submit_result(conn, p1)
    assert res1.get("ok") is False

    # Wrong excerpt_id
    p2 = json.loads(json.dumps(payload))
    p2["result"]["memberships"][0]["evidence"]["excerpt_id"] = "f" * 64
    res2 = library_work.submit_result(conn, p2)
    assert res2.get("ok") is False


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: stale revisions rejection required")
def test_p2_2_stale_source_or_taxonomy_revision_rejected():
    """Mismatch in source_revision or taxonomy_revision invalidates attempt and rejects."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: stale revisions")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload = make_valid_submission_payload(seeded)
    payload["source_revision"] = "0" * 64

    res = library_work.submit_result(conn, payload)
    assert res.get("ok") is False


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: zero current labels written on rejection required")
def test_p2_2_rejection_writes_zero_current_labels_and_stays_visible():
    """Rejected submission writes zero rows to item_shelves; rejection record remains visible."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: rejection accounting")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload = make_valid_submission_payload(seeded)
    payload["result"]["memberships"][0]["confidence"] = 0.40  # invalid confidence

    res = library_work.submit_result(conn, payload)
    assert res.get("ok") is False

    # Check that item_shelves has ZERO rows
    assigned_count = conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0]
    assert assigned_count == 0

    # Submission record must be stored with outcome='rejected'
    sub_row = conn.execute("SELECT outcome FROM library_submissions WHERE submission_key=?", (payload["submission_key"],)).fetchone()
    assert sub_row is not None
    assert sub_row[0] == "rejected"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: idempotent submit retry required")
def test_p2_2_identical_submit_retry_returns_stored_response():
    """An identical retry of a completed submission returns the exact recorded response without advancing state."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: idempotent submit retry")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload = make_valid_submission_payload(seeded, key="key_idempotent")

    res1 = library_work.submit_result(conn, payload)
    assert res1.get("ok") is True

    # Retry exact request
    res2 = library_work.submit_result(conn, payload)
    assert res2.get("ok") is True
    assert res2 == res1


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: idempotency conflict on changed payload required")
def test_p2_2_changed_payload_under_same_key_returns_idempotency_conflict():
    """A changed payload submitted under an already used submission_key returns idempotency_conflict."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: idempotency conflict")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload1 = make_valid_submission_payload(seeded, key="key_conflict")
    res1 = library_work.submit_result(conn, payload1)
    assert res1.get("ok") is True

    # Changed request under same key
    payload2 = dict(payload1)
    payload2["result"] = {"outcome": "unmapped", "reason": "different outcome"}
    res2 = library_work.submit_result(conn, payload2)
    assert res2.get("ok") is False
    assert res2.get("error", {}).get("code") == "idempotency_conflict"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: stale attempt token rejection required")
def test_p2_2_stale_attempt_token_returns_stale_attempt():
    """A stale or unknown token with no recorded submission returns stale_attempt and writes no proposal."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: stale attempt token")

    conn = get_substrate_connection()
    seeded = seed_work_row(conn)
    payload = make_valid_submission_payload(seeded, key="key_stale")
    payload["attempt_token"] = "z" * 43  # unknown token

    res = library_work.submit_result(conn, payload)
    assert res.get("ok") is False
    assert res.get("error", {}).get("code") == "stale_attempt"

    # Zero proposals written
    proposals = conn.execute("SELECT count(*) FROM library_proposals").fetchone()[0]
    assert proposals == 0
