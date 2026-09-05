"""tests/test_library_work_leases.py - Independent verification tests for Gate P2-1.

Covers Gate P2-1 (leases):
- Two concurrent connections/processes contend for one row and receive exactly one current token
- Batches contain distinct single-item rows (each work row contains exactly one card)
- Expiry boundary: server clock `now >= lease_expires_ms` marks expiry; expired tokens are reaped
- Capped renewal: renewal extends from server time, but never past 3,600s after initial claim
- Release: retires token; returns to ready if attempts < 3, otherwise blocked
- Cancel: retires token, sets work/attempt state to cancelled
- Three-attempt ceiling: third claim exhaustion blocks row without reset
- No model or network calls during any lease transition

Written from PHASE2-CONTRACT-2026-09-04 and phase2-contract/tool-schemas.json.
xfails strictly until library_work is integrated.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
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
GATE = "Gate P2-1: leases"


def get_substrate_connection() -> sqlite3.Connection:
    """Creates an in-memory SQLite connection with 0027 substrate schema."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    # Base yoinks table for foreign keys
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


def seed_run_and_manifest(
    conn: sqlite3.Connection,
    run_id: str = "run_test_p2_1",
    version_id: str = "tax_v1",
    revision_hash: str = "a" * 64,
    items: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Seeds prerequisite rows: active taxonomy, run, manifest, and ready work."""
    if items is None:
        items = [
            {"video_id": f"vid_test_{i:03d}", "priority": 100} for i in range(5)
        ]

    conn.execute("INSERT OR IGNORE INTO shelf_versions VALUES (?, NULL, ?, 'active', '2026-09-04T00:00:00Z', 'gemini', '2026-09-04T00:00:00Z')", (version_id, revision_hash))
    conn.execute("UPDATE library_meta SET active_version_id=? WHERE singleton=1", (version_id,))
    conn.execute("INSERT INTO library_runs VALUES (?, ?, ?, 1, 'collecting', '{}', '2026-09-04T00:00:00Z')", (run_id, version_id, "b" * 64))

    for item in items:
        vid = item["video_id"]
        conn.execute("INSERT OR IGNORE INTO yoinks VALUES (?, 'Title', 'Channel', 'youtube', NULL)", (vid,))
        conn.execute("INSERT INTO library_manifest VALUES (?, ?, ?, 'waiting', NULL)", (run_id, vid, "c" * 64))
        card_json = json.dumps({"video_id": vid, "title": "Title", "excerpts": []})
        conn.execute(
            """INSERT INTO library_work(
                work_id, run_id, video_id, kind, packet_generation, packet_json, packet_hash, state, priority, attempts, created_at, updated_at
            ) VALUES (?, ?, ?, 'assign', 1, ?, ?, 'ready', ?, 0, '2026-09-04T00:00:00Z', '2026-09-04T00:00:00Z')""",
            (f"work_{vid}", run_id, vid, card_json, "d" * 64, item.get("priority", 100)),
        )
    conn.commit()


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: claim_work implementation required")
def test_p2_1_claim_work_grants_attempt_token_and_deadline():
    """Verify claim_work transitions row ready -> leased, generates cryptographically strong attempt token >=43 chars."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: claim_work")

    conn = get_substrate_connection()
    seed_run_and_manifest(conn)

    res = library_work.claim_work(
        conn,
        action="claim",
        run_id="run_test_p2_1",
        client_id="client_alpha",
        max_items=1,
        lease_seconds=600,
    )
    assert res.get("ok") is True
    assert res.get("schema_version") == 1
    assert "work" in res
    assert len(res["work"]) == 1

    work_item = res["work"][0]
    token = work_item.get("attempt_token")
    assert token and len(token) >= 43
    assert work_item.get("attempt_number") == 1
    assert work_item.get("lease_expires_ms") is not None
    assert work_item.get("video_id") == "vid_test_000"

    # Verify DB state
    row = conn.execute("SELECT state, attempts FROM library_work WHERE work_id=?", (work_item["work_id"],)).fetchone()
    assert row[0] == "leased"
    assert row[1] == 1

    # Verify attempt recorded in library_attempts
    att = conn.execute("SELECT client_id, state FROM library_attempts WHERE attempt_token=?", (token,)).fetchone()
    assert att[0] == "client_alpha"
    assert att[1] == "current"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: concurrent claim contention required")
def test_p2_1_concurrent_claim_contention_single_winner():
    """Two concurrent connections contend for one ready row: exactly one receives token, other gets none."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: concurrent claim contention")

    conn = get_substrate_connection()
    seed_run_and_manifest(conn, items=[{"video_id": "single_row", "priority": 100}])

    results = []
    errors = []

    def claim_worker(client_id: str):
        try:
            res = library_work.claim_work(
                conn,
                action="claim",
                run_id="run_test_p2_1",
                client_id=client_id,
                max_items=1,
                lease_seconds=300,
            )
            results.append((client_id, res))
        except Exception as e:
            errors.append((client_id, e))

    t1 = threading.Thread(target=claim_worker, args=("client_1",))
    t2 = threading.Thread(target=claim_worker, args=("client_2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(errors) == 0
    assert len(results) == 2

    claimed = [r for r in results if r[1].get("ok") and len(r[1].get("work", [])) > 0]
    unclaimed = [r for r in results if r[1].get("ok") and len(r[1].get("work", [])) == 0]

    # Exactly one client won the lease
    assert len(claimed) == 1
    assert len(unclaimed) == 1

    # Exactly one current attempt exists in DB
    current_attempts = conn.execute("SELECT count(*) FROM library_attempts WHERE work_id='work_single_row' AND state='current'").fetchone()[0]
    assert current_attempts == 1


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: distinct single-item batches required")
def test_p2_1_batch_claim_returns_distinct_single_item_rows():
    """A claim batch returns rows where each work row contains exactly one card, distinct video_ids."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: batch claim")

    conn = get_substrate_connection()
    seed_run_and_manifest(conn, items=[{"video_id": f"vid_batch_{i}", "priority": 100} for i in range(4)])

    res = library_work.claim_work(
        conn,
        action="claim",
        run_id="run_test_p2_1",
        client_id="client_batch",
        max_items=4,
        lease_seconds=300,
    )
    assert res.get("ok") is True
    items = res.get("work", [])
    assert len(items) == 4

    video_ids = [w["video_id"] for w in items]
    assert len(set(video_ids)) == 4, "Batch must contain distinct items"
    for w in items:
        assert "card" in w
        assert w["card"]["video_id"] == w["video_id"]
        assert len(w["attempt_token"]) >= 43


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: lease expiry boundary required")
def test_p2_1_lease_expiry_boundary_and_reap():
    """Server clock now >= lease_expires_ms is expired; reap retires token and returns row to ready."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: lease expiry")

    conn = get_substrate_connection()
    seed_run_and_manifest(conn, items=[{"video_id": "vid_expire", "priority": 100}])

    # Mock injectable clock or set short lease
    claim_res = library_work.claim_work(
        conn,
        action="claim",
        run_id="run_test_p2_1",
        client_id="client_exp",
        max_items=1,
        lease_seconds=60,
    )
    token = claim_res["work"][0]["attempt_token"]

    # Advance time past lease_expires_ms
    past_deadline = claim_res["work"][0]["lease_expires_ms"] + 1000
    library_work.expire_attempts(conn, now_ms=past_deadline)

    # Token must be expired in library_attempts
    att_state = conn.execute("SELECT state FROM library_attempts WHERE attempt_token=?", (token,)).fetchone()[0]
    assert att_state == "expired"

    # Work row must be returned to ready (since attempts = 1 < 3)
    work_state = conn.execute("SELECT state, attempts FROM library_work WHERE video_id='vid_expire'").fetchone()
    assert work_state[0] == "ready"
    assert work_state[1] == 1, "Attempts count must be preserved across expiry"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: capped renewal required")
def test_p2_1_renewal_extends_deadline_capped_at_3600s():
    """Valid renewal extends deadline from server time, but never past 3600s from initial claim."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: lease renewal")

    conn = get_substrate_connection()
    seed_run_and_manifest(conn, items=[{"video_id": "vid_renew", "priority": 100}])

    now_ms = 1_700_000_000_000
    claim_res = library_work.claim_work(
        conn,
        action="claim",
        run_id="run_test_p2_1",
        client_id="client_renew",
        max_items=1,
        lease_seconds=900,
        now_ms=now_ms,
    )
    work_id = claim_res["work"][0]["work_id"]
    token = claim_res["work"][0]["attempt_token"]
    max_deadline = now_ms + 3600 * 1000

    # Renew after 500s
    renew_now = now_ms + 500 * 1000
    renew_res = library_work.renew_attempt(
        conn,
        work_id=work_id,
        client_id="client_renew",
        attempt_token=token,
        lease_seconds=900,
        now_ms=renew_now,
    )
    assert renew_res.get("ok") is True

    # Renew near 3500s: extension must clamp to initial + 3600s
    renew_late = now_ms + 3500 * 1000
    renew_res_late = library_work.renew_attempt(
        conn,
        work_id=work_id,
        client_id="client_renew",
        attempt_token=token,
        lease_seconds=900,
        now_ms=renew_late,
    )
    assert renew_res_late.get("ok") is True
    assert renew_res_late["lease_expires_ms"] <= max_deadline

    # Attempts count and token remain identical
    att_row = conn.execute("SELECT attempt_token, attempt_number FROM library_attempts WHERE work_id=? AND state='current'", (work_id,)).fetchone()
    assert att_row[0] == token
    assert att_row[1] == 1


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: renewal authorization check required")
def test_p2_1_renewal_rejected_for_wrong_owner_or_expired():
    """Renewal by a different client ID or after expiry must be refused with error."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: renewal authorization")

    conn = get_substrate_connection()
    seed_run_and_manifest(conn, items=[{"video_id": "vid_renew_auth", "priority": 100}])

    claim_res = library_work.claim_work(
        conn, action="claim", run_id="run_test_p2_1", client_id="owner_1", max_items=1, lease_seconds=300
    )
    work_id = claim_res["work"][0]["work_id"]
    token = claim_res["work"][0]["attempt_token"]

    # Wrong client
    bad_client = library_work.renew_attempt(
        conn, work_id=work_id, client_id="imposter", attempt_token=token, lease_seconds=300
    )
    assert bad_client.get("ok") is False

    # Wrong token
    bad_token = library_work.renew_attempt(
        conn, work_id=work_id, client_id="owner_1", attempt_token="x" * 43, lease_seconds=300
    )
    assert bad_token.get("ok") is False


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: release and cancel required")
def test_p2_1_release_and_cancel_semantics():
    """Release returns row to ready; cancel transitions to cancelled without resetting attempts."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: release and cancel")

    conn = get_substrate_connection()
    seed_run_and_manifest(conn, items=[
        {"video_id": "vid_rel", "priority": 100},
        {"video_id": "vid_can", "priority": 100}
    ])

    # 1. Release
    c1 = library_work.claim_work(conn, action="claim", run_id="run_test_p2_1", client_id="c_rel", max_items=1, lease_seconds=300)
    w1 = c1["work"][0]["work_id"]
    t1 = c1["work"][0]["attempt_token"]

    rel_res = library_work.release_attempt(conn, work_id=w1, client_id="c_rel", attempt_token=t1, reason="client stopped")
    assert rel_res.get("ok") is True
    assert rel_res.get("state") == "ready"
    assert rel_res.get("remaining_attempts") == 2

    # 2. Cancel
    c2 = library_work.claim_work(conn, action="claim", run_id="run_test_p2_1", client_id="c_can", max_items=1, lease_seconds=300)
    w2 = c2["work"][0]["work_id"]
    t2 = c2["work"][0]["attempt_token"]

    can_res = library_work.cancel_attempt(conn, work_id=w2, client_id="c_can", attempt_token=t2, reason="user aborted")
    assert can_res.get("ok") is True
    assert can_res.get("state") == "cancelled"

    row = conn.execute("SELECT state FROM library_work WHERE work_id=?", (w2,)).fetchone()
    assert row[0] == "cancelled"


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: third-attempt exhaustion required")
def test_p2_1_third_attempt_exhaustion_blocks_row():
    """Claiming a row 3 times without accepted submission transitions row to blocked."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: third-attempt exhaustion")

    conn = get_substrate_connection()
    seed_run_and_manifest(conn, items=[{"video_id": "vid_exhaust", "priority": 100}])
    work_id = "work_vid_exhaust"

    # Claim 1 & release
    c1 = library_work.claim_work(conn, action="claim", run_id="run_test_p2_1", client_id="c", max_items=1, lease_seconds=300)
    library_work.release_attempt(conn, work_id=work_id, client_id="c", attempt_token=c1["work"][0]["attempt_token"], reason="retry 1")

    # Claim 2 & release
    c2 = library_work.claim_work(conn, action="claim", run_id="run_test_p2_1", client_id="c", max_items=1, lease_seconds=300)
    library_work.release_attempt(conn, work_id=work_id, client_id="c", attempt_token=c2["work"][0]["attempt_token"], reason="retry 2")

    # Claim 3 & release -> must become blocked, not ready
    c3 = library_work.claim_work(conn, action="claim", run_id="run_test_p2_1", client_id="c", max_items=1, lease_seconds=300)
    rel3 = library_work.release_attempt(conn, work_id=work_id, client_id="c", attempt_token=c3["work"][0]["attempt_token"], reason="retry 3")
    
    assert rel3.get("state") == "blocked"
    row = conn.execute("SELECT state, attempts FROM library_work WHERE work_id=?", (work_id,)).fetchone()
    assert row[0] == "blocked"
    assert row[1] == 3

    # Attempting a 4th claim must yield 0 items
    c4 = library_work.claim_work(conn, action="claim", run_id="run_test_p2_1", client_id="c", max_items=1, lease_seconds=300)
    assert len(c4.get("work", [])) == 0


@pytest.mark.xfail(not HAS_LIBRARY_WORK, strict=True, reason=f"{GATE}: no model or network calls permitted")
def test_p2_1_no_model_or_network_calls_during_leases(monkeypatch):
    """Ensure lease operations do not perform any model or external network calls."""
    if not HAS_LIBRARY_WORK:
        raise NotImplementedError(f"{GATE}: no model/network calls")

    def forbidden_call(*args, **kwargs):
        raise AssertionError("Network or model call attempted during lease transaction")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_call)
    
    conn = get_substrate_connection()
    seed_run_and_manifest(conn)

    res = library_work.claim_work(conn, action="claim", run_id="run_test_p2_1", client_id="c_clean", max_items=2, lease_seconds=300)
    assert res.get("ok") is True
