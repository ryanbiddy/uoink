"""Phase 3 handoff gates: S16 (publication crash boundaries), S17 (Phase 2
enqueue and replay), S18 (classification waiting states). Contract:
docs/library/PHASE3-CONTRACT-2026-09-07.md, "Post-commit classification handoff".

The Phase 2 service is the real library_work.LibraryWorkService on a
temporary index with an approved fixture taxonomy; no model, client or
network is involved. Nothing here edits library_work.py.

Run: python -m pytest -q tests/test_source_subscriptions_handoff.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    Clock, FakeAdapter, FakeBackend, MINUTE_MS, OPERATOR, REGISTRY, T0, items, make_service,
    open_index, register, rows, snapshot, starts, status, turn_on, vid,
)

import source_subscriptions as ss  # noqa: E402
from library_work import LibraryWorkService, RequestContext as LibraryContext  # noqa: E402

PROMPT_HASH = "7" * 64


def _publish(idx, video_id, *, clips=True):
    idx.upsert_yoink(dict(video_id=video_id, slug=f"slug-{video_id}", title=f"Title {video_id}",
                          topic="Old", yoinked_at="2026-09-07", corpus_path="", sidecar_path="",
                          metadata_json='{"url": "https://www.youtube.com/watch?v=' + video_id + '"}'))
    if clips:
        with idx.write_transaction() as conn:
            conn.execute("INSERT INTO clips(video_id, seq, start, end, text) VALUES (?, 0, 0, 10, ?)",
                         (video_id, f"Evidence for {video_id}"))


def _approve_taxonomy(idx, tmp_path, clock):
    library = LibraryWorkService(idx, tmp_path / "library", clock=clock)
    operator = LibraryContext(authenticated=True, client_id="operator", session_id="s_op",
                              operator=True, local_user_confirmed=True)
    result = library.approve_taxonomy(operator, {
        "version_id": "tax_v1",
        "nodes": [{"shelf_id": "shelf_alpha", "path": ["Alpha"], "definition": "Alpha shelf",
                   "include": ["alpha"], "exclude": ["other"]}]})
    assert result["ok"] is True, result
    return library


def _env(tmp_path, *, n_items=2):
    idx = open_index(tmp_path)
    clock = Clock()
    adapter = FakeAdapter([snapshot([vid(i) for i in range(1, n_items + 1)], coverage="window")])
    backend = FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    sid = register(service)["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    return idx, service, clock, backend, sid


def _outbox(service):
    return rows(service, "SELECT * FROM source_classification_outbox ORDER BY capture_key")


# ---- S16 publication crash boundaries ------------------------------------------
def test_s16_partial_publication_never_gets_premature_work(tmp_path):
    idx, service, clock, backend, sid = _env(tmp_path)
    backend.outcome = ss.CaptureOutcome("in_flight")
    backend.probe_result = "unknown"
    assert service.advance_source(sid)["outcome"] == "in_flight"
    start = backend.runs[0]
    entry = next(i["entry_id"] for i in items(service, sid) if i["item_id"] == start["item_id"])
    # Stop after the corpus file/sidecar only: no index row, no completion call.
    assert service.reconcile_on_startup()["uncertain"] == 1
    assert _outbox(service) == []
    # Stop after the item upsert but before citations/clips and completion.
    _publish(idx, entry, clips=False)
    assert service.reconcile_on_startup()["succeeded"] == 1
    assert [r["state"] for r in _outbox(service)] == ["pending"]
    assert rows(service, "SELECT state FROM source_capture_starts")[0]["state"] == "succeeded"
    # Without a taxonomy/prompt policy the item stays visibly unfiled.
    dispatched = service.dispatch_classification_outbox()
    assert dispatched[0]["outcome"] == "waiting_configuration"
    record = next(i for i in status(service, sid)["items"] if i["entry_id"] == entry)
    assert record["capture_state"] == "committed"
    assert record["classification"]["state"] == "waiting_configuration"
    assert record["video_id"] == entry
    idx.close()


def test_s16_outbox_failure_does_not_roll_back_publication_and_is_repaired(tmp_path):
    idx, service, clock, backend, sid = _env(tmp_path)
    assert service.advance_source(sid)["outcome"] == "succeeded"
    assert len(_outbox(service)) == 1
    # Simulate a crash after the ledger/item commit but before the outbox row.
    with idx.write_transaction() as conn:
        conn.execute("DELETE FROM source_classification_outbox")
    record = status(service, sid)["items"]
    committed = next(i for i in record if i["capture_state"] == "committed")
    assert committed["classification"]["state"] == "pending", "visible as unfiled, not lost"
    assert service.reconcile_on_startup()["outbox_repaired"] == 1
    assert [r["state"] for r in _outbox(service)] == ["pending"]
    assert service.reconcile_on_startup()["outbox_repaired"] == 0, "exactly one handoff"
    # Provenance survives in the item record: source URL/type stay intact.
    assert committed["canonical_url"] == f"https://www.youtube.com/watch?v={committed['entry_id']}"
    idx.close()


# ---- S17 Phase 2 enqueue and replay ------------------------------------------------
def test_s17_one_frozen_single_item_run_per_capture_with_verified_replay(tmp_path):
    idx, service, clock, backend, sid = _env(tmp_path)
    library = _approve_taxonomy(idx, tmp_path, clock)
    policy = service.configure_classification_policy(OPERATOR, {"version_id": "tax_v1",
                                                                "prompt_hash": PROMPT_HASH})
    assert policy["ok"] is True
    assert service.advance_source(sid)["outcome"] == "succeeded"
    video_id = starts(service, sid)[0]["video_id"]
    _publish(idx, video_id)
    result = service.dispatch_classification_outbox()[0]
    assert result["outcome"] == "enqueued"
    outbox = _outbox(service)[0]
    run_id = ss.classification_run_id(f"youtube:{video_id}")
    assert outbox["run_id"] == run_id and outbox["state"] == "enqueued"
    assert outbox["version_id"] == "tax_v1" and outbox["prompt_hash"] == PROMPT_HASH
    assert outbox["work_id"] and len(outbox["source_revision"]) == 64
    run = rows(service, "SELECT * FROM library_runs WHERE run_id=?", (run_id,))[0]
    manifest = rows(service, "SELECT * FROM library_manifest WHERE run_id=?", (run_id,))
    work = rows(service, "SELECT * FROM library_work WHERE run_id=?", (run_id,))
    assert run["version_id"] == "tax_v1" and run["state"] == "collecting"
    assert [m["video_id"] for m in manifest] == [video_id]
    assert manifest[0]["source_revision"] == outbox["source_revision"]
    assert len(work) == 1 and work[0]["state"] == "ready" and work[0]["work_id"] == outbox["work_id"]
    # Display: ready work without a client lease is waiting_for_client.
    record = next(i for i in status(service, sid)["items"] if i["video_id"] == video_id)
    assert record["classification"] == {"state": "waiting_for_client", "work_id": outbox["work_id"],
                                        "run_id": run_id}
    # Replay: a second dispatcher after prepare_run committed but before the
    # outbox acknowledged adopts the identical run; no second run or work row.
    with idx.write_transaction() as conn:
        conn.execute("UPDATE source_classification_outbox SET state='pending', work_id=NULL "
                     "WHERE capture_key=?", (outbox["capture_key"],))
    other = make_service(idx, clock=clock, backend=backend)
    replay = other.dispatch_classification_outbox()[0]
    assert replay["outcome"] == "enqueued" and replay["run_id"] == run_id
    assert rows(service, "SELECT COUNT(*) AS n FROM library_runs")[0]["n"] == 1
    assert rows(service, "SELECT COUNT(*) AS n FROM library_work")[0]["n"] == 1
    assert _outbox(service)[0]["work_id"] == outbox["work_id"]
    # A conflicting run under the frozen id blocks; existing manifests unchanged.
    other_video = vid(2)
    _publish(idx, other_video)
    key2 = f"youtube:{other_video}"
    with idx.write_transaction() as conn:
        conn.execute("INSERT INTO source_classification_outbox (capture_key, video_id, committed_at_ms, "
                     "state, updated_at_ms) VALUES (?, ?, ?, 'pending', ?)",
                     (key2, other_video, clock.now, clock.now))
    operator = LibraryContext(authenticated=True, client_id="operator", session_id="s_op",
                              operator=True, local_user_confirmed=True)
    hijack = library.prepare_run(operator, {"run_id": ss.classification_run_id(key2), "version_id": "tax_v1",
                                            "video_ids": [video_id], "prompt_hash": PROMPT_HASH})
    assert hijack["ok"] is True
    conflict = service.dispatch_classification_outbox()[0]
    assert conflict["outcome"] == "blocked" and conflict["code"] == "classification_conflict"
    assert conflict["reason"] == "manifest_mismatch"
    assert rows(service, "SELECT state, last_error_code FROM source_classification_outbox "
                         "WHERE capture_key=?", (key2,))[0] == {"state": "blocked",
                                                                 "last_error_code": "classification_conflict"}
    assert rows(service, "SELECT COUNT(*) AS n FROM library_manifest WHERE run_id=?", (run_id,))[0]["n"] == 1
    assert rows(service, "SELECT manifest_hash FROM library_runs WHERE run_id=?", (run_id,))[0]["manifest_hash"] == run["manifest_hash"]
    idx.close()


def test_s17_two_dispatchers_race_produce_one_run(tmp_path):
    import threading
    idx, service, clock, backend, sid = _env(tmp_path)
    _approve_taxonomy(idx, tmp_path, clock)
    service.configure_classification_policy(OPERATOR, {"version_id": "tax_v1", "prompt_hash": PROMPT_HASH})
    assert service.advance_source(sid)["outcome"] == "succeeded"
    video_id = starts(service, sid)[0]["video_id"]
    _publish(idx, video_id)
    other = make_service(idx, clock=clock, backend=backend)
    barrier = threading.Barrier(2)
    results: list = []

    def run(svc):
        barrier.wait()
        results.extend(svc.dispatch_classification_outbox())

    threads = [threading.Thread(target=run, args=(service,)), threading.Thread(target=run, args=(other,))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    outcomes = sorted(r["outcome"] for r in results)
    assert outcomes in (["enqueued"], ["enqueued", "skipped"], ["enqueued", "enqueued"]), results
    assert rows(service, "SELECT COUNT(*) AS n FROM library_runs")[0]["n"] == 1
    assert rows(service, "SELECT COUNT(*) AS n FROM library_work")[0]["n"] == 1
    assert _outbox(service)[0]["state"] == "enqueued"
    idx.close()


# ---- S18 classification waiting states ------------------------------------------------
def test_s18_distinct_waiting_conditions_keep_the_item_visible(tmp_path):
    idx, service, clock, backend, sid = _env(tmp_path, n_items=3)
    assert service.advance_source(sid)["outcome"] == "succeeded"
    video_id = starts(service, sid)[0]["video_id"]
    _publish(idx, video_id)

    def display():
        return next(i for i in status(service, sid)["items"] if i["video_id"] == video_id)["classification"]

    # No configured taxonomy/prompt.
    assert service.dispatch_classification_outbox()[0]["outcome"] == "waiting_configuration"
    assert display()["state"] == "waiting_configuration"
    # Consent cannot configure the policy; only a trusted operator can.
    denied = service.configure_classification_policy(REGISTRY, {"version_id": "tax_v1", "prompt_hash": PROMPT_HASH})
    assert denied["error"]["code"] == "user_intent_required"
    unapproved = service.configure_classification_policy(OPERATOR, {"version_id": "missing", "prompt_hash": PROMPT_HASH})
    assert unapproved["error"]["code"] == "validation_error"
    # Unavailable Phase 2 service.
    library = _approve_taxonomy(idx, tmp_path, clock)
    service.configure_classification_policy(OPERATOR, {"version_id": "tax_v1", "prompt_hash": PROMPT_HASH})
    original = service._prepare_run
    service._prepare_run = lambda frozen, vid_: ss.error_envelope("service_unavailable", "down", retryable=True)
    unavailable = service.dispatch_classification_outbox()[0]
    assert unavailable["outcome"] == "pending" and unavailable["code"] == "service_unavailable"
    assert display()["state"] == "pending" and display()["error_code"] == "service_unavailable"
    service._prepare_run = original
    # Deleted source: blocked, item record keeps its capture, no re-capture.
    idx.soft_delete_yoink(video_id)
    blocked = service.dispatch_classification_outbox()[0]
    assert blocked["outcome"] == "blocked" and blocked["code"] == "item_deleted"
    assert display()["state"] == "blocked"
    assert len(backend.runs) == 1, "never re-captures"
    idx.restore_yoink(video_id)
    with idx.write_transaction() as conn:
        conn.execute("UPDATE source_classification_outbox SET state='pending', last_error_code=NULL")
    # No client lease: ready work shows waiting_for_client; nothing is spawned.
    assert service.dispatch_classification_outbox()[0]["outcome"] == "enqueued"
    assert display()["state"] == "waiting_for_client"
    # Pinned/revised source after enqueue: Phase 2 accounts for it (blocked
    # disposition), and the source view mirrors that state without recapture.
    work = rows(service, "SELECT * FROM library_work")[0]
    with idx.write_transaction() as conn:
        conn.execute("UPDATE library_work SET state='blocked' WHERE work_id=?", (work["work_id"],))
    assert display()["state"] == "blocked"
    assert len(backend.runs) == 1 and len(starts(service, sid)) == 1
    idx.close()


def test_s18_linked_preexisting_capture_reports_not_requested(tmp_path):
    idx, service, clock, backend, sid = _env(tmp_path)
    _publish(idx, vid(1))
    assert service.advance_source(sid)["outcome"] == "linked"
    record = next(i for i in status(service, sid)["items"] if i["entry_id"] == vid(1))
    assert record["classification"] == {"state": "not_requested", "work_id": None}
    assert _outbox(service) == []
    assert service.dispatch_classification_outbox() == []
    idx.close()
