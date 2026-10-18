"""Service audit, first pass (run K, 2026-09-04): Claude reading Astra's library_work.py.

Frozen Python surface: PHASE2-RECONCILIATION-BRIEF-2026-09-04 (phase2-v1.1). Plan:
docs/library/SERVICE-AUDIT-PLAN-2026-09-04.md. Findings: docs/library/SERVICE-AUDIT-2026-09-04.md.

Scope of this pass, per the brief: transaction boundaries (A1, A5, A6, A12), the three
durable boundaries (B1, B3, B4, B6, B8), attempt-token and apply-key semantics (A2, A3, A4,
A14, A16), pin durability through rename (A15, P2-4), stale-undo refusal (A17), and the
section-D reading items that a test can pin (D1, D5).

Every case runs on an empty schema-27 database created under pytest's temp root, with a
temp authoritative store. The live index is never opened. No model, network or client
process runs; the only subprocesses are two copies of this repository's own service for
the cross-process lock case. Each test docstring quotes the contract text it enforces.

The auditor could not execute this file (worker sandbox); the orchestrator runs it with
``PYTHONPATH=. python -m pytest -q tests/test_library_service_audit.py -p no:cacheprovider``.
"""
from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from index import Index
from library_work import LibraryWorkService, RequestContext, canonical

ROOT = Path(__file__).resolve().parent.parent
T0 = 1000
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
CLIENT = RequestContext(authenticated=True, client_id="client", session_id="local",
                        operator=True, local_user_confirmed=True)
OTHER_SESSION = RequestContext(authenticated=True, client_id="client", session_id="foreign",
                               operator=True, local_user_confirmed=True)
OTHER_CLIENT = RequestContext(authenticated=True, client_id="other")
PATHS = {"s1": ["Testing"], "s2": ["Other"]}


def nodes(s1_path=("Testing",), s1_retired=False):
    first = dict(shelf_id="s1", path=list(s1_path), definition="Tests", include=["tests"], exclude=["other"])
    if s1_retired:
        first["retired"] = True
    return [first, dict(shelf_id="s2", path=["Other"], definition="Other", include=["other"], exclude=["tests"])]


class Harness:
    """One disposable index, one temp authoritative store, one injectable clock."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.db = tmp_path / "fixture.db"
        self.store = tmp_path / "library"
        self.clock = [T0]
        self.idx = Index.open(self.db)
        self.add_item("fixture")
        self.svc = LibraryWorkService(self.idx, self.store, clock=lambda: self.clock[0])
        tax = self.svc.approve_taxonomy(CLIENT, dict(version_id="v1", nodes=nodes()))
        assert tax["ok"], tax
        run = self.svc.prepare_run(CLIENT, dict(run_id="r1", version_id="v1", video_ids=["fixture"],
                                                prompt_hash="0" * 64))
        assert run["ok"], run

    # -- lifecycle -----------------------------------------------------------------
    def add_item(self, video_id):
        self.idx.upsert_yoink(dict(video_id=video_id, slug=video_id, title="Fixture", topic="Old",
                                   yoinked_at="2026-09-04", corpus_path="", sidecar_path=""))
        with self.idx.write_transaction() as c:
            c.execute("INSERT INTO clips(video_id,seq,start,end,text) VALUES(?,0,0,10,'Original source evidence.')",
                      (video_id,))

    def reopen(self):
        self.idx = Index.open(self.db)
        self.svc = LibraryWorkService(self.idx, self.store, clock=lambda: self.clock[0])

    def close(self):
        try:
            self.idx.close()
        except sqlite3.Error:
            pass

    # -- SQL and file observation ---------------------------------------------------
    def sql(self, query, *params):
        return [tuple(r) for r in self.idx._conn.execute(query, params).fetchall()]

    def one(self, query, *params):
        row = self.idx._conn.execute(query, params).fetchone()
        return None if row is None else tuple(row)

    def meta(self):
        return self.one("SELECT projection_revision,active_version_id,last_operation_sequence,recovery_state "
                        "FROM library_meta WHERE singleton=1")

    def state(self):
        return (self.sql("SELECT * FROM item_shelves ORDER BY video_id,shelf_id"),
                self.sql("SELECT * FROM library_item_policy ORDER BY video_id"))

    def memberships(self):
        return self.sql("SELECT shelf_id,source,locked,is_primary,confidence FROM item_shelves "
                        "WHERE video_id='fixture' ORDER BY shelf_id")

    def policy(self):
        row = self.one("SELECT exclusive_move FROM library_item_policy WHERE video_id='fixture'")
        return None if row is None else row[0]

    def journal(self):
        directory = self.store / "journal"
        return sorted(p.name for p in directory.glob("*.jsonl")) if directory.is_dir() else []

    def temps(self):
        directory = self.store / "journal"
        return sorted(p.name for p in directory.glob("*.tmp")) if directory.is_dir() else []

    # -- service calls ----------------------------------------------------------------
    def claim(self, run_id="r1"):
        r = self.svc.claim_work(CLIENT, dict(action="claim", run_id=run_id, client_id="client"))
        assert r["ok"] and len(r["work"]) == 1, r
        return r["work"][0]

    def submission(self, w, key="submit1", shelves=("s1",)):
        excerpt = w["card"]["excerpts"][0]
        memberships = [dict(shelf_id=s, shelf_path=PATHS[s], confidence=0.8,
                            evidence=dict(basis="packet", kind="timed_clip", excerpt_id=excerpt["excerpt_id"],
                                          card_hash=w["card"]["card_hash"], quote="source evidence"))
                       for s in shelves]
        a = {k: w[k] for k in ("work_id", "video_id", "attempt_token", "source_revision",
                               "taxonomy_revision", "packet_hash")}
        a.update(client_id="client", submission_key=key, schema_version=1,
                 usage=dict(status="unavailable", reason="fixture"),
                 result=dict(outcome="assigned", memberships=memberships))
        return a

    def submit(self, args):
        return self.svc.submit_result(CLIENT, args)

    def accept(self, shelves=("s1",)):
        s = self.submit(self.submission(self.claim(), shelves=shelves))
        assert s["ok"] and s["outcome"] == "accepted", s
        return s

    def approved(self, rev, key, activate=True):
        p = self.svc.preview_apply(CLIENT, dict(run_id="r1", expected_projection_revision=rev,
                                                activate_version=activate))
        assert p["ok"], p
        a = dict(preview_id=p["preview_id"], delta_hash=p["delta_hash"], operation_key=key,
                 expected_projection_revision=rev)
        r = self.svc.approve_preview(CLIENT, a)
        assert r["ok"], r
        return dict(mode="apply", **a)

    def intent(self, kind, operation):
        r = self.svc.mint_user_intent(CLIENT, dict(kind=kind, operation=operation))
        assert r["ok"], r
        return dict(operation, user_intent_token=r["user_intent_token"])

    def pin(self, operation):
        return self.svc.pin_shelf(CLIENT, self.intent("pin", operation))

    def undo(self, apply_id, rev, key):
        args = self.intent("undo", dict(apply_id=apply_id, expected_projection_revision=rev, operation_key=key))
        return self.svc.undo_apply(CLIENT, args), args


@pytest.fixture
def h(tmp_path):
    harness = Harness(tmp_path)
    yield harness
    harness.close()


class FaultConnection:
    """Delegate to the real sqlite3 connection; raise once on the first statement that
    starts with ``prefix`` so a storage fault lands inside an open transaction."""

    def __init__(self, conn, prefix):
        self._conn, self._prefix, self.fired = conn, prefix.upper(), False

    def execute(self, sql, *args):
        if not self.fired and sql.lstrip().upper().startswith(self._prefix):
            self.fired = True
            raise sqlite3.OperationalError("injected fault before " + self._prefix)
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


# =====================================================================================
# A. Transaction boundaries, tokens, keys
# =====================================================================================

def test_a1_claim_is_one_begin_immediate_across_two_connections(h):
    """Contract: "Claim uses Index.write_transaction() / BEGIN IMMEDIATE ... Store one current
    attempt per row; increment attempts only when a new claim succeeds." Two connections
    contend for the single ready row: exactly one token, attempts is 1."""
    second = Index.open(h.db)
    other = LibraryWorkService(second, h.store, clock=lambda: h.clock[0])
    barrier = threading.Barrier(2)

    def run(svc):
        barrier.wait()
        return svc.claim_work(CLIENT, dict(action="claim", run_id="r1", client_id="client"))

    try:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(run, [h.svc, other]))
    finally:
        second.close()
    assert all(r["ok"] for r in results), results
    packets = [w for r in results for w in r["work"]]
    assert len(packets) == 1, results
    assert h.sql("SELECT state,attempts FROM library_work") == [("leased", 1)]
    assert h.one("SELECT COUNT(*) FROM library_attempts WHERE state='current'") == (1,)
    assert h.one("SELECT attempt_token FROM library_attempts") == (packets[0]["attempt_token"],)


def test_a2_attempt_token_quality(h):
    """Contract: "Create a cryptographically random, at least 256-bit attempt token distinct
    from work ID, client ID and submission key." Schema token pattern ^[A-Za-z0-9_-]{43,128}$."""
    tokens = []
    for _ in range(3):
        w = h.claim()
        token = w["attempt_token"]
        assert TOKEN.fullmatch(token), token
        assert len(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) >= 32
        assert token not in {w["work_id"], "client", "submit1"}
        tokens.append(token)
        r = h.svc.release_attempt(CLIENT, dict(action="release", work_id=w["work_id"], client_id="client",
                                                attempt_token=token, reason="audit"))
        assert r["ok"], r
    assert len(set(tokens)) == 3
    assert sorted(t[0] for t in h.sql("SELECT attempt_token FROM library_attempts")) == sorted(tokens)


def test_a3_lease_clock_renewal_cap_and_owner(h):
    """Contract: "Leases default to 900 seconds ... renewal extends from server time but never
    past 3,600 seconds after the initial claim. The server clock determines expiry;
    now >= lease_expires_ms is expired." Renewal is "current owner only, before expiry"."""
    w = h.claim()
    assert w["lease_expires_ms"] == T0 + 900_000

    def renew(ctx=CLIENT, client="client", seconds=900):
        return h.svc.renew_attempt(ctx, dict(action="renew", work_id=w["work_id"], client_id=client,
                                             attempt_token=w["attempt_token"], lease_seconds=seconds))

    expected = [(800_000, 1_700_000), (1_600_000, 2_500_000), (2_400_000, 3_300_000),
                (3_200_000, 3_600_000), (3_500_000, 3_600_000)]
    for now, expiry in expected:
        h.clock[0] = T0 + now
        r = renew()
        assert r["ok"] and r["lease_expires_ms"] == T0 + expiry, (now, r)
        assert h.one("SELECT lease_expires_ms,lease_max_ms FROM library_attempts") == (T0 + expiry, T0 + 3_600_000)
    h.clock[0] = T0 + 3_600_000  # exactly the cap: expired, boundary inclusive
    r = renew()
    assert r["ok"] is False and r["error"]["code"] == "stale_attempt", r
    assert h.submit(h.submission(w))["error"]["code"] == "stale_attempt"
    assert h.one("SELECT state FROM library_attempts WHERE attempt_token=?", w["attempt_token"]) == ("expired",)
    assert h.one("SELECT state,attempts FROM library_work") == ("ready", 1)

    w = h.claim()  # attempt 2: owner checks
    before = h.one("SELECT lease_expires_ms FROM library_attempts WHERE attempt_token=?", w["attempt_token"])
    r = h.svc.renew_attempt(OTHER_CLIENT, dict(action="renew", work_id=w["work_id"], client_id="other",
                                                attempt_token=w["attempt_token"], lease_seconds=900))
    assert r["ok"] is False and r["error"]["code"] == "stale_attempt", r
    r = h.svc.renew_attempt(CLIENT, dict(action="renew", work_id=w["work_id"], client_id="other",
                                          attempt_token=w["attempt_token"], lease_seconds=900))
    assert r["ok"] is False and r["error"]["code"] == "forbidden", r
    assert h.one("SELECT lease_expires_ms FROM library_attempts WHERE attempt_token=?", w["attempt_token"]) == before
    assert h.one("SELECT state FROM library_attempts WHERE attempt_token=?", w["attempt_token"]) == ("current",)


def test_a4_three_claim_ceiling_survives_release_expiry_and_invalid_submit(h):
    """Contract: "Do not reset the three-claim ceiling through release, invalid output,
    cancellation or arbitrary client fields. An exhausted row remains visible ... Once three
    claims have been consumed, refreshed work also needs a new run." """
    w1 = h.claim()
    r = h.svc.release_attempt(CLIENT, dict(action="release", work_id=w1["work_id"], client_id="client",
                                            attempt_token=w1["attempt_token"], reason="stop"))
    assert r["ok"] and r["state"] == "ready" and r["remaining_attempts"] == 2, r
    w2 = h.claim()
    h.clock[0] = w2["lease_expires_ms"]
    assert h.svc.expire_attempts(CLIENT, {}) == dict(ok=True, schema_version=1, expired=1)
    assert h.one("SELECT state,attempts FROM library_work") == ("ready", 2)
    w3 = h.claim()
    bad = h.submission(w3, key="invalid")
    bad["result"] = dict(outcome="assigned", memberships=[])
    s = h.submit(bad)
    assert s["ok"] and s["outcome"] == "rejected" and s["retryable"] is False, s
    assert h.one("SELECT state,attempts FROM library_work") == ("blocked", 3)
    empty = h.svc.claim_work(CLIENT, dict(action="claim", run_id="r1", client_id="client"))
    assert empty["ok"] and empty["work"] == [], empty
    refresh = h.svc.refresh_run_item(CLIENT, dict(run_id="r1", video_id="fixture", reason="again"))
    assert refresh["ok"] is False and refresh["error"]["code"] == "attempts_exhausted", refresh
    listed = h.svc.list_work(CLIENT, dict(run_id="r1"))
    assert listed["counts"] == {"blocked": 1} and listed["items"][0]["attempts"] == 3, listed
    assert sorted(r[0] for r in h.sql("SELECT state FROM library_attempts")) == ["cancelled", "expired", "submitted"]
    assert h.one("SELECT COUNT(*) FROM library_submissions") == (1,)
    assert h.one("SELECT COUNT(*) FROM library_proposals") == (0,)


def test_a5_receipts_are_checked_before_lease_checks(h):
    """Contract: "An identical retry of a completed submission returns that recorded response,
    even after the lease has expired ... A changed request under that key, or a second result
    under a consumed attempt token, returns idempotency_conflict. Check recorded receipts
    before current-lease checks, after authentication." """
    w = h.claim()
    a = h.submission(w)
    s = h.submit(a)
    assert s["ok"] and s["outcome"] == "accepted", s
    before = (h.sql("SELECT * FROM library_submissions"), h.sql("SELECT * FROM library_proposals"))
    assert len(before[0]) == 1 and len(before[1]) == 1
    h.clock[0] = w["lease_expires_ms"] + 1
    again = h.submit(a)
    assert again == s
    assert canonical(again) == h.one("SELECT response_json FROM library_submissions")[0]
    changed = json.loads(json.dumps(a))
    changed["usage"]["reason"] = "one byte differs"
    assert h.submit(changed)["error"]["code"] == "idempotency_conflict"
    second = dict(a, submission_key="second-key", result=dict(outcome="unmapped", reason="changed my mind"))
    r = h.submit(second)
    assert r["ok"] is False and r["error"]["code"] == "idempotency_conflict" and r["error"]["retryable"] is False, r
    assert (h.sql("SELECT * FROM library_submissions"), h.sql("SELECT * FROM library_proposals")) == before
    assert h.one("SELECT state FROM library_work") == ("accepted",)


def test_a5_stale_token_without_receipt_writes_nothing(h):
    """Contract: "A stale token with no recorded matching submission returns stale_attempt
    and writes no proposal." """
    w = h.claim()
    h.clock[0] = w["lease_expires_ms"]
    r = h.submit(h.submission(w))
    assert r["ok"] is False and r["error"]["code"] == "stale_attempt" and r["error"]["retryable"] is True, r
    assert h.one("SELECT COUNT(*) FROM library_submissions") == (0,)
    assert h.one("SELECT COUNT(*) FROM library_proposals") == (0,)
    assert h.one("SELECT state FROM library_attempts") == ("expired",)
    assert h.one("SELECT state,attempts FROM library_work") == ("ready", 1)


def test_a6_submit_is_all_or_nothing(h):
    """Contract: "Valid assigned result: accepted; store immutable submission and proposed
    memberships; no current labels written." A storage fault after the submission row is
    written must leave no submission, no attempt change and no work change."""
    w = h.claim()
    real = h.idx._conn
    fault = FaultConnection(real, "INSERT INTO library_proposals")
    h.idx._conn = fault
    try:
        r = h.submit(h.submission(w))
    finally:
        h.idx._conn = real
    assert fault.fired
    assert r["ok"] is False and r["error"]["code"] == "storage_error", r
    text = canonical(r)
    assert "injected" not in text and h.root.name not in text
    assert real.in_transaction is False
    assert h.one("SELECT COUNT(*) FROM library_submissions") == (0,)
    assert h.one("SELECT COUNT(*) FROM library_proposals") == (0,)
    assert h.one("SELECT COUNT(*) FROM item_shelves") == (0,)
    assert h.one("SELECT state FROM library_attempts") == ("current",)
    assert h.one("SELECT state,attempts FROM library_work") == ("leased", 1)
    assert h.one("SELECT disposition FROM library_manifest") == ("waiting",)
    assert h.one("SELECT run_revision FROM library_runs") == (1,)
    s = h.submit(h.submission(w))
    assert s["ok"] and s["outcome"] == "accepted", s
    assert h.one("SELECT COUNT(*) FROM library_proposals") == (1,)
    assert h.one("SELECT COUNT(*) FROM item_shelves") == (0,)


def test_a12_apply_publishes_record_before_any_db_write(h):
    """Contract: "write and flush a temporary operation record and atomically publish it; only
    then project it in the DB transaction. Do not acknowledge success before file publication
    and DB commit." Observed through the three documented crash_hook boundaries with an
    independent reader connection (WAL: readers see only committed state)."""
    h.accept()
    args = h.approved(rev=0, key="apply1")
    h.svc.librarian_apply_enabled = True
    reader = sqlite3.connect(str(h.db), timeout=5)
    seen = []

    def hook(boundary):
        committed = tuple(reader.execute(
            "SELECT projection_revision,last_operation_sequence FROM library_meta").fetchone())
        receipts = reader.execute("SELECT COUNT(*) FROM library_operation_receipts").fetchone()[0]
        seen.append((boundary, len(h.journal()), len(h.temps()), committed, receipts,
                     (h.store / "pins.json").exists()))

    h.svc.crash_hook = hook
    try:
        r = h.svc.apply_preview(CLIENT, args)
    finally:
        reader.close()
    assert r["ok"] and r["after_revision"] == 1, r
    assert [s[0] for s in seen] == ["before_file_publication", "after_publication_before_db_commit",
                                    "after_db_commit_before_response"], seen
    before, published, committed = seen
    assert before[1:5] == (0, 1, (0, 0), 0), before        # temp flushed, nothing published
    assert published[1:5] == (1, 0, (0, 0), 0), published  # published, DB still unchanged
    assert committed[1:] == (1, 0, (1, 1), 1, True), committed
    assert canonical(r) == h.one("SELECT receipt_json FROM library_operation_receipts")[0]


def test_a14_apply_key_replay_and_zero_delta_receipt(h):
    """Contract: "Replaying the same operation key/request returns its original receipt without
    changing the revision; changed content under that key is a conflict. A zero-delta apply
    returns a no-change receipt and does not create a fictitious revision ... a no-change
    receipt advances only the operation sequence." """
    h.accept()
    args = h.approved(rev=0, key="apply1")
    h.svc.librarian_apply_enabled = True
    r = h.svc.apply_preview(CLIENT, args)
    assert r["ok"] and r["after_revision"] == 1 and r["no_change"] is False, r
    state, journal = h.state(), h.journal()
    replay = h.svc.apply_preview(CLIENT, args)
    assert replay == r
    assert canonical(replay) == h.one("SELECT receipt_json FROM library_operation_receipts WHERE operation_key='apply1'")[0]
    assert h.state() == state and h.journal() == journal and h.meta() == (1, "v1", 1, "ready")
    assert h.one("SELECT COUNT(*) FROM library_applies") == (1,)
    altered = h.svc.apply_preview(CLIENT, dict(args, expected_projection_revision=1))
    assert altered["ok"] is False and altered["error"]["code"] == "idempotency_conflict", altered
    assert h.state() == state and h.journal() == journal
    zero = h.svc.apply_preview(CLIENT, h.approved(rev=1, key="apply2"))
    assert zero["ok"] and zero["no_change"] is True and zero["apply_id"] is None and zero["undo_target"] is None, zero
    assert (zero["before_revision"], zero["after_revision"], zero["operation_sequence"]) == (1, 1, 2)
    assert h.meta() == (1, "v1", 2, "ready")
    assert h.one("SELECT COUNT(*) FROM library_operation_receipts") == (2,)
    assert h.one("SELECT COUNT(*) FROM library_applies") == (1,)
    assert len(h.journal()) == 2 and h.state() == state


def test_a15_pin_move_unpin_semantics_and_exact_inverse(h):
    """Contract: "pin adds/locks that membership, preserving other memberships ... move replaces
    all memberships with one primary locked membership and sets an item-level exclusive-move
    policy ... pin to another shelf while exclusive returns a conflict ... unpin leaves the
    membership in place, clears its lock and any exclusive policy that it owns ... Model
    confidence is null for locked user rows. Every operation preserves its exact inverse." """
    h.accept(shelves=("s1", "s2"))
    h.svc.librarian_apply_enabled = True
    r = h.svc.apply_preview(CLIENT, h.approved(rev=0, key="apply1"))
    assert r["ok"] and r["after_revision"] == 1, r
    assert h.memberships() == [("s1", "agent", 0, 1, 0.8), ("s2", "agent", 0, 0, 0.8)]
    s1 = h.state()

    pin = h.pin(dict(video_id="fixture", shelf_id="s2", action="pin", expected_projection_revision=1,
                     operation_key="pin-s2"))
    assert pin["ok"] and pin["after_revision"] == 2, pin
    assert h.memberships() == [("s1", "agent", 0, 1, 0.8), ("s2", "user", 1, 0, None)]
    assert h.policy() is None

    undo, _ = h.undo(pin["apply_id"], rev=2, key="undo-pin")
    assert undo["ok"] and undo["after_revision"] == 3, undo
    assert h.state() == s1

    move = h.pin(dict(video_id="fixture", shelf_id="s2", action="move", expected_projection_revision=3,
                      operation_key="move-s2"))
    assert move["ok"] and move["after_revision"] == 4, move
    assert h.memberships() == [("s2", "user", 1, 1, None)] and h.policy() == 1
    s4 = h.state()

    conflict = h.svc.mint_user_intent(CLIENT, dict(kind="pin", operation=dict(
        video_id="fixture", shelf_id="s1", action="pin", expected_projection_revision=4, operation_key="pin-x")))
    assert conflict["ok"] is False and conflict["error"]["code"] == "exclusive_move_conflict", conflict
    assert h.state() == s4

    unpin = h.pin(dict(video_id="fixture", shelf_id="s2", action="unpin", expected_projection_revision=4,
                       operation_key="unpin-s2"))
    assert unpin["ok"] and unpin["after_revision"] == 5, unpin
    assert h.memberships() == [("s2", "user", 0, 1, None)] and h.policy() is None

    redo, _ = h.undo(unpin["apply_id"], rev=5, key="undo-unpin")
    assert redo["ok"] and redo["after_revision"] == 6, redo
    assert h.state() == s4
    assert h.one("SELECT COUNT(*) FROM item_shelves WHERE locked=1 AND confidence IS NOT NULL") == (0,)
    assert h.one("SELECT COUNT(*) FROM library_applies") == (6,)
    assert h.one("PRAGMA foreign_key_check") is None


def test_a16_user_intent_binds_operation_session_and_expiry(h):
    """Contract: the capability "binds the canonical operation (excluding the token), expected
    revision, user session and a 5-minute expiry. It is consumed atomically with the operation,
    with identical retries allowed ... no registry tool mints this token." """
    op = dict(video_id="fixture", shelf_id="s1", action="pin", expected_projection_revision=0, operation_key="k1")
    args = h.intent("pin", op)

    def refused(request, ctx=CLIENT):
        r = h.svc.pin_shelf(ctx, request)
        assert r["ok"] is False and r["error"]["code"] == "invalid_user_intent", (request, r)

    refused(dict(args, action="move"))
    refused(dict(args, shelf_id="s2"))
    refused(dict(args, expected_projection_revision=1))
    refused(dict(args, operation_key="k2"))
    refused(args, OTHER_SESSION)
    refused(dict(args, user_intent_token="A" * 43))
    r = h.svc.pin_shelf(RequestContext(authenticated=True, client_id="client"), args)
    assert r["ok"] is False and r["error"]["code"] == "user_intent_required", r
    expired = h.intent("pin", dict(op, operation_key="k-expired"))
    h.clock[0] = T0 + 300_000
    refused(expired)
    h.clock[0] = T0
    assert h.meta() == (0, None, 0, "ready") and h.journal() == []
    assert h.one("SELECT COUNT(*) FROM library_user_intents WHERE consumed_by IS NOT NULL") == (0,)

    receipt = h.svc.pin_shelf(CLIENT, args)
    assert receipt["ok"] and receipt["after_revision"] == 1, receipt
    assert h.sql("SELECT consumed_by FROM library_user_intents WHERE consumed_by IS NOT NULL") == [("k1",)]
    assert h.svc.pin_shelf(CLIENT, args) == receipt
    refused(args, OTHER_SESSION)
    refused(dict(args, operation_key="k3", expected_projection_revision=1))
    assert h.meta() == (1, None, 1, "ready") and len(h.journal()) == 1


def test_a17_undo_rules_and_stale_undo_refusal(h):
    """Contract: "Initially allow only a target whose after_revision is the current revision
    ... it guarantees that undo cannot overwrite a newer pin ... Repeating the undo key returns
    its stored receipt; attempting a second undo of the same target with a different key
    conflicts. The newer undo operation may itself be undone with a new key." """
    h.accept()
    h.svc.librarian_apply_enabled = True
    applied = h.svc.apply_preview(CLIENT, h.approved(rev=0, key="apply1"))
    assert applied["ok"] and applied["after_revision"] == 1, applied
    s1 = h.state()
    stale = h.intent("undo", dict(apply_id=applied["apply_id"], expected_projection_revision=1,
                                  operation_key="undo-apply"))
    pin = h.pin(dict(video_id="fixture", shelf_id="s2", action="pin", expected_projection_revision=1,
                     operation_key="pin-s2"))
    assert pin["ok"] and pin["after_revision"] == 2, pin
    s2 = h.state()

    r = h.svc.undo_apply(CLIENT, stale)  # confirmed before the pin, delivered after it
    assert r["ok"] is False and r["error"]["code"] == "revision_conflict", r
    assert r["error"]["details"] == dict(expected_revision=1, current_revision=2), r
    assert h.state() == s2 and h.meta() == (2, "v1", 2, "ready")
    mint = h.svc.mint_user_intent(CLIENT, dict(kind="undo", operation=dict(
        apply_id=applied["apply_id"], expected_projection_revision=2, operation_key="undo-apply-2")))
    assert mint["ok"] is False and mint["error"]["code"] == "revision_conflict", mint

    undo, undo_args = h.undo(pin["apply_id"], rev=2, key="undo-pin")
    assert undo["ok"] and undo["after_revision"] == 3, undo
    assert h.state() == s1
    assert h.svc.undo_apply(CLIENT, undo_args) == undo and h.meta() == (3, "v1", 3, "ready")
    second = h.svc.mint_user_intent(CLIENT, dict(kind="undo", operation=dict(
        apply_id=pin["apply_id"], expected_projection_revision=3, operation_key="undo-pin-again")))
    assert second["ok"] is False and second["error"]["code"] in {"revision_conflict", "undo_conflict"}, second
    forged = dict(undo_args, operation_key="undo-pin-again", expected_projection_revision=3)
    assert h.svc.undo_apply(CLIENT, forged)["error"]["code"] == "invalid_user_intent"
    assert h.state() == s1

    redo, _ = h.undo(undo["apply_id"], rev=3, key="undo-undo")
    assert redo["ok"] and redo["after_revision"] == 4, redo
    assert h.state() == s2
    late = h.svc.mint_user_intent(CLIENT, dict(kind="undo", operation=dict(
        apply_id=applied["apply_id"], expected_projection_revision=4, operation_key="undo-apply-late")))
    assert late["ok"] is False and late["error"]["code"] == "revision_conflict", late
    assert h.one("SELECT COUNT(*) FROM library_applies") == (4,)


def test_p24_pin_survives_rename_and_activation_and_blocks_on_retirement(h):
    """Contract: "A rename retains identity" (shelf_id is stable across versions); P2-4 "rename
    retains identity ... Preserve pins through every ... taxonomy/activation and apply
    transition"; "A taxonomy change that retires a pinned identity blocks activation until the
    user explicitly resolves that pin." """
    pin = h.pin(dict(video_id="fixture", shelf_id="s1", action="pin", expected_projection_revision=0,
                     operation_key="pin-s1"))
    assert pin["ok"] and pin["after_revision"] == 1, pin
    assert h.memberships() == [("s1", "user", 1, 1, None)]  # no primary existed: it becomes primary
    pinned_rows = h.state()[0]

    v2 = h.svc.approve_taxonomy(CLIENT, dict(version_id="v2", parent_version_id="v1", nodes=nodes(("QA",))))
    assert v2["ok"], v2
    assert v2["revision_hash"] != h.one("SELECT revision_hash FROM shelf_versions WHERE version_id='v1'")[0]
    run = h.svc.prepare_run(CLIENT, dict(run_id="r2", version_id="v2", video_ids=["fixture"], prompt_hash="1" * 64))
    assert run["ok"], run
    assert h.one("SELECT disposition FROM library_manifest WHERE run_id='r2'") == ("pinned",)
    assert h.one("SELECT state FROM library_work WHERE run_id='r2'") == ("blocked",)

    p = h.svc.preview_apply(CLIENT, dict(run_id="r2", expected_projection_revision=1, activate_version=True))
    assert p["ok"], p
    assert p["summary"]["blocking_reasons"] == [] and (p["changed_items"], p["baseline_items"]) == (0, 1), p
    assert p["delta"] == dict(items={}, policies={}, active_version_id="v2"), p["delta"]
    assert [e["disposition"] for e in p["manifest_exclusions"]] == ["pinned"]
    a = dict(preview_id=p["preview_id"], delta_hash=p["delta_hash"], operation_key="activate-v2",
             expected_projection_revision=1)
    assert h.svc.approve_preview(CLIENT, a)["ok"]
    h.svc.librarian_apply_enabled = True
    applied = h.svc.apply_preview(CLIENT, dict(mode="apply", **a))
    assert applied["ok"] and applied["after_revision"] == 2, applied
    assert h.state()[0] == pinned_rows
    assert h.meta() == (2, "v2", 2, "ready")
    assert h.one("SELECT name,path_json FROM shelf_nodes WHERE version_id='v2' AND shelf_id='s1'") == ("QA", '["QA"]')
    assert h.sql("SELECT version_id,status FROM shelf_versions ORDER BY version_id") == [("v1", "approved"), ("v2", "active")]

    v3 = h.svc.approve_taxonomy(CLIENT, dict(version_id="v3", parent_version_id="v2",
                                             nodes=nodes(("QA",), s1_retired=True)))
    assert v3["ok"], v3
    assert h.svc.prepare_run(CLIENT, dict(run_id="r3", version_id="v3", video_ids=["fixture"], prompt_hash="2" * 64))["ok"]
    p3 = h.svc.preview_apply(CLIENT, dict(run_id="r3", expected_projection_revision=2, activate_version=True))
    assert p3["ok"], p3
    assert dict(code="retired_pin", video_id="fixture") in p3["summary"]["blocking_reasons"], p3["summary"]
    a3 = dict(preview_id=p3["preview_id"], delta_hash=p3["delta_hash"], operation_key="activate-v3",
              expected_projection_revision=2)
    refused = h.svc.approve_preview(CLIENT, a3)
    assert refused["ok"] is False and refused["error"]["code"] == "incomplete_manifest", refused
    assert h.state()[0] == pinned_rows and h.meta() == (2, "v2", 2, "ready")

    undo, _ = h.undo(applied["apply_id"], rev=2, key="undo-activate")
    assert undo["ok"] and undo["after_revision"] == 3, undo
    assert h.state()[0] == pinned_rows
    assert h.meta() == (3, None, 3, "ready")
    assert h.one("PRAGMA foreign_key_check") is None


# =====================================================================================
# B. Durable boundaries
# =====================================================================================

def test_b1_fault_before_publication_leaves_nothing_committed(h):
    """Plan B1 (in-process form). Contract: "Ignore incomplete temporary files." A fault after
    the temp record is flushed but before the atomic publish leaves no committed record, an
    unchanged DB, recovery_state ready, and the same request then succeeds fresh exactly once."""
    args = h.intent("pin", dict(video_id="fixture", shelf_id="s1", action="pin",
                                expected_projection_revision=0, operation_key="b1"))

    def hook(boundary):
        if boundary == "before_file_publication":
            raise OSError("injected disk fault")

    h.svc.crash_hook = hook
    r = h.svc.pin_shelf(CLIENT, args)
    assert r["ok"] is False and r["error"]["code"] == "storage_error", r
    assert "injected" not in canonical(r) and h.root.name not in canonical(r)
    assert h.journal() == [] and h.temps() == []
    assert h.meta() == (0, None, 0, "ready")
    assert h.one("SELECT COUNT(*) FROM item_shelves") == (0,)
    assert h.one("SELECT consumed_by FROM library_user_intents") == (None,)
    h.svc.crash_hook = lambda boundary: None
    again = h.svc.pin_shelf(CLIENT, args)
    assert again["ok"] and again["after_revision"] == 1 and again["operation_sequence"] == 1, again
    assert len(h.journal()) == 1 and h.meta() == (1, None, 1, "ready")


def test_b3_fault_inside_db_transaction_after_partial_writes(h):
    """Plan B3 (in-process form). Contract: "Once the file is durable, that operation is
    committed to the authoritative sequence: if DB projection fails, report recovery_pending
    and block later mutations until replay ... return the original receipt to retries." """
    args = h.intent("pin", dict(video_id="fixture", shelf_id="s1", action="move",
                                expected_projection_revision=0, operation_key="b3"))
    original = h.svc._project_delta
    partial_rows = []

    def partial(conn, delta):
        original(conn, delta)  # item_shelves and policy rows are written ...
        partial_rows.append(conn.execute("SELECT COUNT(*) FROM item_shelves").fetchone()[0])
        raise sqlite3.OperationalError("injected after partial writes")  # ... then the DB fails

    h.svc._project_delta = partial
    r = h.svc.pin_shelf(CLIENT, args)
    h.svc._project_delta = original
    assert partial_rows == [1]
    assert r["ok"] is False and r["error"]["code"] == "recovery_pending" and r["error"]["retryable"] is True, r
    assert "injected" not in canonical(r) and h.root.name not in canonical(r)
    records = h.journal()
    assert len(records) == 1 and h.temps() == []
    assert h.meta() == (0, None, 0, "pending")
    assert h.one("SELECT COUNT(*) FROM item_shelves") == (0,)
    assert h.one("SELECT COUNT(*) FROM library_item_policy") == (0,)
    assert h.one("SELECT COUNT(*) FROM library_operation_receipts") == (0,)
    assert h.one("SELECT COUNT(*) FROM library_applies") == (0,)
    assert h.one("SELECT consumed_by FROM library_user_intents") == (None,)
    blocked = h.svc.claim_work(CLIENT, dict(action="claim", run_id="r1", client_id="client"))
    assert blocked["ok"] is False and blocked["error"]["code"] == "recovery_pending", blocked

    recovered = h.svc.recover_operations(CLIENT, {})
    assert recovered["ok"] and recovered["replayed"] == 1 and recovered["projection_revision"] == 1, recovered
    assert h.meta() == (1, None, 1, "ready")
    assert h.sql("SELECT video_id,shelf_id,version_id,source,locked,is_primary,confidence FROM item_shelves") == \
        [("fixture", "s1", "v1", "user", 1, 1, None)]
    assert h.one("SELECT exclusive_move FROM library_item_policy") == (1,)
    assert h.one("SELECT COUNT(*) FROM library_applies") == (1,)
    assert h.one("SELECT consumed_by FROM library_user_intents") == ("b3",)
    record = json.loads((h.store / "journal" / records[0]).read_text(encoding="utf-8"))
    retry = h.svc.pin_shelf(CLIENT, args)
    assert retry == record["receipt"], (retry, record["receipt"])
    assert h.journal() == records and h.meta() == (1, None, 1, "ready")


def test_b4_fault_after_commit_before_response(h):
    """Plan B4 (in-process form). After commit the DB and record agree, recovery_state stays
    ready, and the retried request returns the stored receipt without a second record."""
    args = h.intent("pin", dict(video_id="fixture", shelf_id="s1", action="pin",
                                expected_projection_revision=0, operation_key="b4"))

    def hook(boundary):
        if boundary == "after_db_commit_before_response":
            raise OSError("injected response fault")

    h.svc.crash_hook = hook
    r = h.svc.pin_shelf(CLIENT, args)
    assert r["ok"] is False and r["error"]["code"] == "storage_error" and r["error"]["retryable"] is True, r
    assert h.meta() == (1, None, 1, "ready")
    assert h.one("SELECT COUNT(*) FROM library_operation_receipts") == (1,)
    assert len(h.journal()) == 1 and (h.store / "pins.json").is_file()
    h.svc.crash_hook = lambda boundary: None
    retry = h.svc.pin_shelf(CLIENT, args)
    assert retry["ok"] and retry["after_revision"] == 1 and retry["operation_sequence"] == 1, retry
    assert canonical(retry) == h.one("SELECT receipt_json FROM library_operation_receipts")[0]
    assert len(h.journal()) == 1 and h.meta() == (1, None, 1, "ready")


def test_b6_missing_committed_record_stops_visibly(h):
    """Plan B6. Contract: "stop visibly on a corrupt or missing committed record. Recovery must
    not skip a damaged record and continue." Deleting the last record only is also a stop."""
    first = h.pin(dict(video_id="fixture", shelf_id="s1", action="pin", expected_projection_revision=0,
                       operation_key="one"))
    second = h.pin(dict(video_id="fixture", shelf_id="s2", action="pin", expected_projection_revision=1,
                        operation_key="two"))
    assert first["ok"] and second["ok"] and second["after_revision"] == 2, (first, second)
    names = h.journal()
    assert len(names) == 2
    paths = [h.store / "journal" / n for n in names]
    saved = [p.read_bytes() for p in paths]
    forged = dict(video_id="fixture", shelf_id="s1", action="unpin", expected_projection_revision=2,
                  operation_key="three", user_intent_token="A" * 43)
    for victim in (0, 1):
        paths[victim].unlink()
        r = h.svc.recover_operations(CLIENT, {})
        assert r["ok"] is False and r["error"]["code"] == "recovery_conflict", (victim, r)
        assert h.meta()[3] == "conflict"
        claim = h.svc.claim_work(CLIENT, dict(action="claim", run_id="r1", client_id="client"))
        assert claim["ok"] is False and claim["error"]["code"] in {"recovery_pending", "recovery_conflict"}, claim
        pin = h.svc.pin_shelf(CLIENT, forged)
        assert pin["ok"] is False and pin["error"]["code"] == "recovery_conflict", pin
        assert h.svc.list_work(CLIENT, dict(run_id="r1"))["ok"] is True
        assert h.meta()[:3] == (2, None, 2)
        paths[victim].write_bytes(saved[victim])
    r = h.svc.recover_operations(CLIENT, {})
    assert r["ok"] and r["replayed"] == 0 and r["operation_sequence"] == 2, r
    assert h.meta() == (2, None, 2, "ready")


CHILD = '''
import json, sys, time
from pathlib import Path
from index import Index
from library_work import LibraryWorkService, RequestContext, decode_json
root, n = Path(sys.argv[1]), sys.argv[2]
idx = Index.open(root / "fixture.db")
svc = LibraryWorkService(idx, root / "library", clock=lambda: 1000)
ctx = RequestContext(authenticated=True, client_id="client", session_id="local", operator=True,
                     local_user_confirmed=True)
args = decode_json((root / ("request" + n + ".json")).read_bytes())
(root / ("ready" + n)).write_text("ready")
while not (root / "go").exists():
    time.sleep(0.01)
print(json.dumps(svc.pin_shelf(ctx, args)), flush=True)
idx.close()
'''


def test_b8_two_processes_pin_serialise_through_the_store_lock(h):
    """Plan B8. Contract: "All projection-changing service calls serialize through a process
    lock and a cross-process lock for that store. Recheck revisions under the lock." Exactly one
    process wins at the expected revision; the other gets a conflict; no gap, no duplicate."""
    for n in "01":
        args = h.intent("pin", dict(video_id="fixture", shelf_id="s1", action="pin",
                                    expected_projection_revision=0, operation_key="proc" + n))
        (h.root / f"request{n}.json").write_text(canonical(args), encoding="utf-8")
    script = h.root / "pin_child.py"
    script.write_text(CHILD, encoding="utf-8")
    h.idx.close()
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    children = [subprocess.Popen([sys.executable, str(script), str(h.root), n], cwd=str(ROOT), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for n in "01"]
    outputs = []
    try:
        deadline = time.monotonic() + 90
        for n, child in zip("01", children):
            while not (h.root / ("ready" + n)).exists():
                assert child.poll() is None, child.communicate()
                assert time.monotonic() < deadline, "child did not start"
                time.sleep(0.01)
        (h.root / "go").write_text("go")
        for child in children:
            out, err = child.communicate(timeout=90)
            assert child.returncode == 0, (out, err)
            outputs.append(json.loads(out.strip().splitlines()[-1]))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()
    h.reopen()
    winners = [o for o in outputs if o["ok"]]
    losers = [o for o in outputs if not o["ok"]]
    assert len(winners) == 1 and winners[0]["after_revision"] == 1 and winners[0]["operation_sequence"] == 1, outputs
    assert len(losers) == 1 and losers[0]["error"]["code"] == "revision_conflict", outputs
    assert len(h.journal()) == 1 and h.meta() == (1, None, 1, "ready")
    assert h.one("SELECT COUNT(*) FROM library_operation_receipts") == (1,)
    assert h.one("SELECT COUNT(*) FROM library_applies") == (1,)
    assert sorted(r[0] is not None for r in h.sql("SELECT consumed_by FROM library_user_intents")) == [False, True]
    assert h.memberships() == [("s1", "user", 1, 1, None)]


# =====================================================================================
# D. Reading items a test can pin
# =====================================================================================

def test_d1_service_has_no_model_network_or_process_imports():
    """D-17 and contract: the service "never call[s] a model"; nothing may import a network
    client or spawn a process. library_cards may import only urllib.parse (pure parsing)."""
    source = (ROOT / "library_work.py").read_text(encoding="utf-8")
    for token in ("urllib", "requests", "httpx", "anthropic", "openai", "subprocess", "socket", "asyncio", "http"):
        assert re.search(rf"^\s*(?:import|from)\s+{token}\b", source, re.M) is None, token
    cards = (ROOT / "library_cards.py").read_text(encoding="utf-8")
    assert re.findall(r"^\s*(?:import|from)\s+(urllib\S*)", cards, re.M) == ["urllib.parse"]
    for token in ("requests", "httpx", "anthropic", "openai", "subprocess", "socket"):
        assert re.search(rf"^\s*(?:import|from)\s+{token}\b", cards, re.M) is None, token


def test_d5_service_never_deletes_or_rewrites_history_tables():
    """Contract: "preserves old attempt/submission records ... No adapter deletes rejection
    history" and "Persist all receipts in library_operation_receipts and the authoritative
    operation stream." No statement in the service may delete or update those tables."""
    source = (ROOT / "library_work.py").read_text(encoding="utf-8").upper()
    for forbidden in ("DELETE FROM LIBRARY_SUBMISSIONS", "UPDATE LIBRARY_SUBMISSIONS",
                      "DELETE FROM LIBRARY_ATTEMPTS", "DELETE FROM LIBRARY_APPLIES",
                      "UPDATE LIBRARY_APPLIES", "DELETE FROM LIBRARY_OPERATION_RECEIPTS",
                      "UPDATE LIBRARY_OPERATION_RECEIPTS", "DELETE FROM LIBRARY_MANIFEST",
                      "DELETE FROM LIBRARY_WORK", "DELETE FROM LIBRARY_RUNS"):
        assert forbidden not in source, forbidden
