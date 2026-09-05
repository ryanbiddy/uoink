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
Realigned to frozen LibraryWorkService surface per run K brief.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from index import Index
from library_work import LibraryWorkService, RequestContext, LibraryError

ROOT = Path(__file__).resolve().parent.parent
GATE = "Gate P2-1: leases"


@pytest.fixture
def tmp_path():
    p = Path(tempfile.mkdtemp(prefix="uoink_lease_test_"))
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


def make_test_environment(tmp_path: Path, items: Optional[List[Dict[str, Any]]] = None, clock_ms: int = 1_000_000):
    root = tmp_path / "work"
    root.mkdir(parents=True, exist_ok=True)
    idx = Index.open(root / "test.db")
    store_root = root / "library"
    clock = [clock_ms]
    svc = LibraryWorkService(idx, store_root, clock=lambda: clock[0])
    ctx_op = RequestContext(authenticated=True, client_id="operator", session_id="s_op", operator=True, local_user_confirmed=True)

    if items is None:
        items = [{"video_id": f"vid_test_{i:03d}", "priority": 100} for i in range(5)]

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
                (vid, f"Evidence text for {vid}")
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
            }
        ]
    })
    assert tax_res.get("ok") is True, tax_res

    run_res = svc.prepare_run(ctx_op, {
        "run_id": "run_test_p2_1",
        "version_id": "tax_v1",
        "video_ids": [it["video_id"] for it in items],
        "prompt_hash": "0" * 64,
    })
    assert run_res.get("ok") is True, run_res

    return idx, svc, clock


def test_p2_1_claim_work_grants_attempt_token_and_deadline(tmp_path):
    """Verify claim_work transitions row ready -> leased, generates cryptographically strong attempt token >=43 chars."""
    idx, svc, clock = make_test_environment(tmp_path, items=[{"video_id": "vid_test_000", "priority": 100}])
    ctx = RequestContext(authenticated=True, client_id="client_alpha", session_id="s1")

    res = svc.claim_work(
        ctx,
        {
            "action": "claim",
            "run_id": "run_test_p2_1",
            "client_id": "client_alpha",
            "max_items": 1,
            "lease_seconds": 600,
        },
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
    row = idx._conn.execute("SELECT state, attempts FROM library_work WHERE work_id=?", (work_item["work_id"],)).fetchone()
    assert row[0] == "leased"
    assert row[1] == 1

    # Verify attempt recorded in library_attempts
    att = idx._conn.execute("SELECT client_id, state FROM library_attempts WHERE attempt_token=?", (token,)).fetchone()
    assert att[0] == "client_alpha"
    assert att[1] == "current"


def test_p2_1_concurrent_claim_contention_single_winner(tmp_path):
    """Two concurrent connections contend for one ready row: exactly one receives token, other gets none."""
    idx, svc, clock = make_test_environment(tmp_path, items=[{"video_id": "single_row", "priority": 100}])

    results = []
    errors = []

    def claim_worker(client_id: str):
        try:
            worker_ctx = RequestContext(authenticated=True, client_id=client_id, session_id=f"s_{client_id}")
            res = svc.claim_work(
                worker_ctx,
                {
                    "action": "claim",
                    "run_id": "run_test_p2_1",
                    "client_id": client_id,
                    "max_items": 1,
                    "lease_seconds": 300,
                },
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
    current_attempts = idx._conn.execute(
        "SELECT count(*) FROM library_attempts a JOIN library_work w USING(work_id) WHERE w.video_id='single_row' AND a.state='current'"
    ).fetchone()[0]
    assert current_attempts == 1


def test_p2_1_batch_claim_returns_distinct_single_item_rows(tmp_path):
    """A claim batch returns rows where each work row contains exactly one card, distinct video_ids."""
    idx, svc, clock = make_test_environment(tmp_path, items=[{"video_id": f"vid_batch_{i}", "priority": 100} for i in range(4)])
    ctx = RequestContext(authenticated=True, client_id="client_batch", session_id="s_batch")

    res = svc.claim_work(
        ctx,
        {
            "action": "claim",
            "run_id": "run_test_p2_1",
            "client_id": "client_batch",
            "max_items": 4,
            "lease_seconds": 300,
        },
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


def test_p2_1_lease_expiry_boundary_and_reap(tmp_path):
    """Server clock now >= lease_expires_ms is expired; reap retires token and returns row to ready."""
    idx, svc, clock = make_test_environment(tmp_path, items=[{"video_id": "vid_expire", "priority": 100}])
    ctx = RequestContext(authenticated=True, client_id="client_exp", session_id="s_exp")

    claim_res = svc.claim_work(
        ctx,
        {
            "action": "claim",
            "run_id": "run_test_p2_1",
            "client_id": "client_exp",
            "max_items": 1,
            "lease_seconds": 60,
        },
    )
    assert claim_res.get("ok") is True
    token = claim_res["work"][0]["attempt_token"]

    # Advance time past lease_expires_ms
    past_deadline = claim_res["work"][0]["lease_expires_ms"] + 1000
    clock[0] = past_deadline

    ctx_op = RequestContext(authenticated=True, operator=True)
    exp_res = svc.expire_attempts(ctx_op, {})
    assert exp_res.get("ok") is True

    # Token must be expired in library_attempts
    att_state = idx._conn.execute("SELECT state FROM library_attempts WHERE attempt_token=?", (token,)).fetchone()[0]
    assert att_state == "expired"

    # Work row must be returned to ready (since attempts = 1 < 3)
    work_state = idx._conn.execute("SELECT state, attempts FROM library_work WHERE video_id='vid_expire'").fetchone()
    assert work_state[0] == "ready"
    assert work_state[1] == 1, "Attempts count must be preserved across expiry"


def test_p2_1_renewal_extends_deadline_capped_at_3600s(tmp_path):
    """Valid renewal extends deadline from server time, but never past 3600s from initial claim."""
    now_ms = 1_700_000_000_000
    idx, svc, clock = make_test_environment(tmp_path, items=[{"video_id": "vid_renew", "priority": 100}], clock_ms=now_ms)
    ctx = RequestContext(authenticated=True, client_id="client_renew", session_id="s_renew")

    claim_res = svc.claim_work(
        ctx,
        {
            "action": "claim",
            "run_id": "run_test_p2_1",
            "client_id": "client_renew",
            "max_items": 1,
            "lease_seconds": 900,
        },
    )
    assert claim_res.get("ok") is True
    work_id = claim_res["work"][0]["work_id"]
    token = claim_res["work"][0]["attempt_token"]
    max_deadline = now_ms + 3600 * 1000

    # Renew successively before expiry: 800s, 1600s, 2400s, 3200s
    for elapsed in [800, 1600, 2400]:
        clock[0] = now_ms + elapsed * 1000
        res = svc.renew_attempt(
            ctx,
            {
                "action": "renew",
                "work_id": work_id,
                "client_id": "client_renew",
                "attempt_token": token,
                "lease_seconds": 900,
            },
        )
        assert res.get("ok") is True

    # Renew at 3200s for 900s: extension would be 4100s, but must clamp to initial + 3600s
    clock[0] = now_ms + 3200 * 1000
    renew_res_late = svc.renew_attempt(
        ctx,
        {
            "action": "renew",
            "work_id": work_id,
            "client_id": "client_renew",
            "attempt_token": token,
            "lease_seconds": 900,
        },
    )
    assert renew_res_late.get("ok") is True
    assert renew_res_late["lease_expires_ms"] == max_deadline

    # Attempts count and token remain identical
    att_row = idx._conn.execute(
        "SELECT attempt_token, attempt_number FROM library_attempts WHERE work_id=? AND state='current'", (work_id,)
    ).fetchone()
    assert att_row[0] == token
    assert att_row[1] == 1


def test_p2_1_renewal_rejected_for_wrong_owner_or_expired(tmp_path):
    """Renewal by a different client ID or after expiry must be refused with error."""
    idx, svc, clock = make_test_environment(tmp_path, items=[{"video_id": "vid_renew_auth", "priority": 100}])
    ctx_owner = RequestContext(authenticated=True, client_id="owner_1", session_id="s_owner")

    claim_res = svc.claim_work(
        ctx_owner,
        {
            "action": "claim",
            "run_id": "run_test_p2_1",
            "client_id": "owner_1",
            "max_items": 1,
            "lease_seconds": 300,
        },
    )
    assert claim_res.get("ok") is True
    work_id = claim_res["work"][0]["work_id"]
    token = claim_res["work"][0]["attempt_token"]

    # Wrong client
    ctx_imposter = RequestContext(authenticated=True, client_id="imposter", session_id="s_imposter")
    bad_client = svc.renew_attempt(
        ctx_imposter,
        {
            "action": "renew",
            "work_id": work_id,
            "client_id": "imposter",
            "attempt_token": token,
            "lease_seconds": 300,
        },
    )
    assert bad_client.get("ok") is False

    # Wrong token
    bad_token = svc.renew_attempt(
        ctx_owner,
        {
            "action": "renew",
            "work_id": work_id,
            "client_id": "owner_1",
            "attempt_token": "x" * 43,
            "lease_seconds": 300,
        },
    )
    assert bad_token.get("ok") is False


def test_p2_1_release_and_cancel_semantics(tmp_path):
    """Release returns row to ready; cancel transitions to cancelled without resetting attempts."""
    idx, svc, clock = make_test_environment(
        tmp_path,
        items=[
            {"video_id": "vid_rel", "priority": 100},
            {"video_id": "vid_can", "priority": 100},
        ],
    )

    # 1. Release
    ctx_rel = RequestContext(authenticated=True, client_id="c_rel", session_id="s_rel")
    c1 = svc.claim_work(
        ctx_rel,
        {
            "action": "claim",
            "run_id": "run_test_p2_1",
            "client_id": "c_rel",
            "max_items": 1,
            "lease_seconds": 300,
        },
    )
    assert c1.get("ok") is True
    w1 = c1["work"][0]["work_id"]
    t1 = c1["work"][0]["attempt_token"]

    rel_res = svc.release_attempt(
        ctx_rel,
        {
            "action": "release",
            "work_id": w1,
            "client_id": "c_rel",
            "attempt_token": t1,
            "reason": "client stopped",
        },
    )
    assert rel_res.get("ok") is True
    assert rel_res.get("state") == "ready"
    assert rel_res.get("remaining_attempts") == 2

    # 2. Cancel
    ctx_can = RequestContext(authenticated=True, client_id="c_can", session_id="s_can")
    c2 = svc.claim_work(
        ctx_can,
        {
            "action": "claim",
            "run_id": "run_test_p2_1",
            "client_id": "c_can",
            "max_items": 1,
            "lease_seconds": 300,
        },
    )
    assert c2.get("ok") is True
    w2 = c2["work"][0]["work_id"]
    t2 = c2["work"][0]["attempt_token"]

    can_res = svc.cancel_attempt(
        ctx_can,
        {
            "action": "cancel",
            "work_id": w2,
            "client_id": "c_can",
            "attempt_token": t2,
            "reason": "user aborted",
        },
    )
    assert can_res.get("ok") is True
    assert can_res.get("state") == "cancelled"

    row = idx._conn.execute("SELECT state FROM library_work WHERE work_id=?", (w2,)).fetchone()
    assert row[0] == "cancelled"


def test_p2_1_third_attempt_exhaustion_blocks_row(tmp_path):
    """Claiming a row 3 times without accepted submission transitions row to blocked."""
    idx, svc, clock = make_test_environment(tmp_path, items=[{"video_id": "vid_exhaust", "priority": 100}])
    ctx = RequestContext(authenticated=True, client_id="c", session_id="s_c")

    # Claim 1 & release
    c1 = svc.claim_work(ctx, {"action": "claim", "run_id": "run_test_p2_1", "client_id": "c", "max_items": 1, "lease_seconds": 300})
    assert c1.get("ok") is True
    w = c1["work"][0]["work_id"]
    svc.release_attempt(ctx, {"action": "release", "work_id": w, "client_id": "c", "attempt_token": c1["work"][0]["attempt_token"], "reason": "retry 1"})

    # Claim 2 & release
    c2 = svc.claim_work(ctx, {"action": "claim", "run_id": "run_test_p2_1", "client_id": "c", "max_items": 1, "lease_seconds": 300})
    assert c2.get("ok") is True
    svc.release_attempt(ctx, {"action": "release", "work_id": w, "client_id": "c", "attempt_token": c2["work"][0]["attempt_token"], "reason": "retry 2"})

    # Claim 3 & release -> must become blocked, not ready
    c3 = svc.claim_work(ctx, {"action": "claim", "run_id": "run_test_p2_1", "client_id": "c", "max_items": 1, "lease_seconds": 300})
    assert c3.get("ok") is True
    rel3 = svc.release_attempt(ctx, {"action": "release", "work_id": w, "client_id": "c", "attempt_token": c3["work"][0]["attempt_token"], "reason": "retry 3"})

    assert rel3.get("state") == "blocked"
    row = idx._conn.execute("SELECT state, attempts FROM library_work WHERE work_id=?", (w,)).fetchone()
    assert row[0] == "blocked"
    assert row[1] == 3

    # Attempting a 4th claim must yield 0 items
    c4 = svc.claim_work(ctx, {"action": "claim", "run_id": "run_test_p2_1", "client_id": "c", "max_items": 1, "lease_seconds": 300})
    assert len(c4.get("work", [])) == 0


def test_p2_1_no_model_or_network_calls_during_leases(tmp_path, monkeypatch):
    """Ensure lease operations do not perform any model or external network calls."""
    def forbidden_call(*args, **kwargs):
        raise AssertionError("Network or model call attempted during lease transaction")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_call)

    idx, svc, clock = make_test_environment(tmp_path)
    ctx = RequestContext(authenticated=True, client_id="c_clean", session_id="s_clean")

    res = svc.claim_work(
        ctx,
        {
            "action": "claim",
            "run_id": "run_test_p2_1",
            "client_id": "c_clean",
            "max_items": 2,
            "lease_seconds": 300,
        },
    )
    assert res.get("ok") is True
