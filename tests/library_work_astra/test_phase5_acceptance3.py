"""BA-3 contract counterexamples, using disposable migrated databases only.

These assert required behavior. No xfails, production fixes, live index or helper.
"""
from __future__ import annotations

import json
import sqlite3
import time

import pytest

from test_phase5_acceptance import (
    INTERVAL, NOW, add_item, analysis, db, evidence, filed, isolate_reader,
    journal, library_resources, membership, report, seed, set_current,
    stdio_result,
)
from test_phase5_acceptance2 import source_fixture, value


def at_path(packet, path):
    for part in path:
        packet = packet[part]
    return packet


def descriptors(node, role):
    if isinstance(node, dict):
        if node.get("role") == role and node.get("metric_id"):
            yield node
        for child in node.values():
            yield from descriptors(child, role)
    elif isinstance(node, list):
        for child in node:
            yield from descriptors(child, role)


@pytest.mark.parametrize("path", [
    ("items", "by_source_type", 0, "count"),
    ("items", "daily_buckets", 0, "count"),
    ("shelf_activity", "current_memberships"),
    ("sources", "details", 0, "new_observations"),
    ("revisions", "taxonomy_versions_created"),
])
def test_phase5_ba3_every_metric_reports_evidence_population(db, path):
    source_fixture(db)
    packet = report(db)
    metric = at_path(packet, path)
    page = evidence(db, packet, metric["metric_id"])
    assert page["ok"], page
    d = {**metric, **metric["evidence"]}
    assert any(d.get(k) == page["total_rows"] for k in
               ("row_count", "evidence_row_count", "total_rows")), (path, d)
    assert any(d.get(k) == len(page["rows"]) for k in
               ("sample_count", "evidence_sample_count", "sample_rows")), (path, d)
    assert any(k in d for k in ("has_more", "more_rows", "evidence_has_more")), d


@pytest.mark.parametrize("collection", ["by_source_type", "by_creator_hint", "daily_buckets"])
def test_phase5_ba3_item_shares_have_distinct_denominator_evidence(db, collection):
    add_item(db, "a")
    add_item(db, "b", author="Another", source_type="podcast", yoinked_at="2026-09-06T12:00:00Z")
    db.commit()
    packet = report(db)
    metric = packet["items"][collection][0]["share"]
    assert metric["numerator"] == 1 and metric["denominator"] == 2
    refs = list(descriptors(metric, "denominator"))
    assert refs, metric
    page = evidence(db, packet, refs[0]["metric_id"])
    assert page["ok"] and page["total_rows"] == 2, page


def test_phase5_ba3_source_state_metric_has_exact_evidence(db):
    source_fixture(db)
    seed.insert_source_item(db, "sub", "uncaptured", first_seen_ms=seed.stamp("2026-09-05T13:00:00Z"))
    db.commit()
    packet = report(db)
    metric = packet["sources"]["details"][0]["new_observations_by_state"]["committed"]
    page = evidence(db, packet, metric["metric_id"])
    assert page["ok"] and page["total_rows"] == 1, page
    assert page["rows"][0]["source_key"] == "item_sub_entry"


@pytest.mark.parametrize("metric_kind", ["added", "churn"])
def test_phase5_ba3_zero_shelf_metric_has_no_unrelated_support(db, metric_kind):
    before = filed(db)
    if metric_kind == "added":
        after = [membership("beta")]
        add_item(db, "b")
        journal(db, 2, {"a": before, "b": []}, {"a": after, "b": [membership("alpha")]}, "2026-09-05T12:00:00Z")
        set_current(db, "b", [membership("alpha")])
    else:
        after = [dict(row, confidence=0.5) for row in before]
        journal(db, 2, {"a": before}, {"a": after}, "2026-09-05T12:00:00Z")
    set_current(db, "a", after)
    db.commit()
    packet = report(db)
    target_shelf = "beta" if metric_kind == "added" else "alpha"
    metric = next(r for r in packet["shelf_activity"]["shelves"] if r["shelf_id"] == target_shelf)[metric_kind]
    assert value(metric) == 0
    page = evidence(db, packet, metric["metric_id"])
    assert page["ok"] and page["total_rows"] == 0, page


def test_phase5_ba3_journal_evidence_contains_reconcilable_item_changes(db):
    before = filed(db)
    after = [membership("beta")]
    journal(db, 2, {"a": before}, {"a": after}, "2026-09-05T12:00:00Z")
    set_current(db, "a", after)
    db.commit()
    packet = report(db)
    page = evidence(db, packet, "shelf_activity.membership_removals")
    assert page["ok"] and value(packet["shelf_activity"]["membership_removals"]) == 1
    encoded = json.dumps(page["rows"])
    assert '"a"' in encoded and '"alpha"' in encoded and '"beta"' in encoded, page["rows"]
    assert "forward_json" not in encoded and "inverse_json" not in encoded


def test_phase5_ba3_deleted_journal_evidence_marks_identity(db):
    filed(db)
    db.execute("UPDATE yoinks SET deleted_at='2026-09-06T00:00:00Z'")
    db.commit()
    packet = report(db, interval={"start": "2026-09-01T12:00:00Z", "end": INTERVAL["end"]})
    page = evidence(db, packet, "shelf_activity.applied_operations")
    assert page["ok"]
    assert "item_deleted" in json.dumps(page["rows"]), page["rows"]


def test_phase5_ba3_baseline_evidence_binds_retained_journal_support(db):
    before = filed(db)
    after = [membership("beta")]
    journal(db, 2, {"a": before}, {"a": after}, "2026-09-05T12:00:00Z")
    set_current(db, "a", after)
    db.commit()
    packet = report(db)
    page = evidence(db, packet, "shelf_activity.shelves.alpha.start_size")
    assert page["ok"] and page["total_rows"] == 1
    # Alpha no longer exists in current item_shelves: its historical evidence
    # must identify the retained apply(s), not a fabricated current table key.
    encoded = json.dumps(page["rows"])
    assert "library_applies" in encoded and "apply_1" in encoded, page["rows"]


def test_phase5_ba3_deleted_metric_scope_is_tombstones(db):
    add_item(db, deleted_at="2026-09-06T00:00:00Z")
    db.commit()
    packet = report(db)
    metric = packet["items"]["deleted_items_excluded"]
    assert value(metric) == 1
    scope = packet["provenance"]["scopes"][metric["scope_ref"]]
    assert scope["population"] != "current_live_saved_items", scope


def test_phase5_ba3_combined_event_scope_includes_journal_clock(db):
    filed(db)
    packet = report(db, interval={"start": "2026-09-01T12:00:00Z", "end": INTERVAL["end"]})
    metric = packet["events"]["total"]
    scope = packet["provenance"]["scopes"][metric["scope_ref"]]
    assert scope["population"] != "current_live_saved_items", scope
    assert "applied_journal_time" in json.dumps(scope), scope


def test_phase5_ba3_channel_correction_changes_selected_observation_hash(db):
    add_item(db, author="", channel="Before")
    db.commit()
    first = evidence(db, report(db), "items.total")["rows"][0]
    db.execute("UPDATE yoinks SET channel='After'")
    db.commit()
    second = evidence(db, report(db), "items.total")["rows"][0]
    assert first["details"]["channel"] != second["details"]["channel"]
    assert first["observation_hash"] != second["observation_hash"]


def test_phase5_ba3_publication_availability_uses_candidate_relation(db):
    source_fixture(db)
    packet = report(db, date_basis="publication_time")
    selected = evidence(db, packet, "items.total")["rows"][0]
    available = evidence(db, packet, "items.publication_time_available")["rows"][0]
    assert available["source_table"] == selected["source_table"] == "source_items", available
    assert available["source_key"] == selected["source_key"] == "item_sub_entry"
    assert available["observation_hash"] == selected["observation_hash"]


@pytest.mark.parametrize("path", [
    ("items", "by_source_type", 0, "count"),
    ("revisions", "taxonomy_versions_created"),
    ("revisions", "runs_created"),
    ("events", "total"),
    ("sources", "linked_capture_union_count"),
])
def test_phase5_ba3_no_history_is_null_across_remaining_metrics(db, path):
    source_fixture(db)
    seed.insert_shelf_version(db, "v1", created_at="2026-09-05T12:00:00Z")
    db.execute("INSERT INTO library_runs(run_id,version_id,manifest_hash,state,policy_json,created_at) VALUES ('r','v1',?,'closed','{}','2026-09-05T12:00:00Z')", ("a" * 64,))
    db.commit()
    packet = report(db, interval={"start": "2026-08-25T00:00:00Z", "end": "2026-08-26T00:00:00Z"})
    metric = at_path(packet, path)
    assert isinstance(metric, dict) and metric["value"] is None and metric.get("recorded_count") == 0, (path, metric)


def test_phase5_ba3_invalid_revision_clock_marks_partial_coverage(db):
    seed.insert_shelf_version(db, "valid", created_at="2026-09-05T12:00:00Z")
    seed.insert_shelf_version(db, "naive", created_at="2026-09-05T12:00:00")
    db.commit()
    cov = report(db)["coverage"]["cov_revisions"]
    assert cov["coverage_status"] == "partial" and cov.get("exclusions"), cov


def test_phase5_ba3_source_metric_has_its_own_history_status(db):
    source_fixture(db)
    db.execute("UPDATE source_items SET first_seen_ms=?, last_seen_ms=?", (seed.stamp("2026-09-08T00:00:00Z"),) * 2)
    seed.insert_subscription(db, "older")
    seed.insert_source_item(db, "older", "entry", first_seen_ms=seed.stamp("2026-09-01T12:00:00Z"))
    db.commit()
    packet = report(db)
    metric = next(r for r in packet["sources"]["details"] if r["source_id"] == "sub")["new_observations"]
    assert metric["value"] is None
    scope = packet["provenance"]["scopes"][metric["scope_ref"]]
    cov = packet["coverage"][metric.get("coverage_ref", scope["coverage_ref"]) ]
    assert cov["coverage_status"] == "no_history", cov


def test_phase5_ba3_initial_filing_is_unknown_without_baseline(db):
    filed(db)
    db.execute("DELETE FROM library_applies")
    db.commit()
    packet = report(db)
    assert packet["shelf_activity"]["churn"]["denominator"] is None
    assert value(packet["shelf_activity"]["initial_filing_items"]) is None


@pytest.mark.parametrize("field,bad", [
    ("confidence", []), ("source", 7), ("assigned_at", []),
    ("evidence_json", {}), ("version_id", None),
])
def test_phase5_ba3_typed_membership_fields_are_validated(db, field, bad):
    filed(db)
    raw = json.loads(db.execute("SELECT forward_json FROM library_applies").fetchone()[0])
    raw["items"]["a"][0][field] = bad
    db.execute("UPDATE library_applies SET forward_json=?", (json.dumps(raw),))
    db.commit()
    packet = report(db)
    assert not packet["ok"] and packet["error"]["code"] == "invalid_source_data", packet.get("coverage", packet)


def test_phase5_ba3_nested_policy_fields_are_validated(db):
    filed(db)
    raw = json.loads(db.execute("SELECT forward_json FROM library_applies").fetchone()[0])
    raw["policies"] = {"a": {"video_id": "a", "exclusive_move": []}}
    db.execute("UPDATE library_applies SET forward_json=?", (json.dumps(raw),))
    db.commit()
    packet = report(db)
    assert not packet["ok"] and packet["error"]["code"] == "invalid_source_data", packet.get("coverage", packet)


@pytest.mark.parametrize("status", ["failed", "invented"])
def test_phase5_ba3_apply_requires_successful_receipt_status(db, status):
    filed(db)
    db.execute("UPDATE library_operation_receipts SET receipt_json=?", (json.dumps({"status": status}),))
    db.commit()
    packet = report(db)
    assert not packet["ok"] or packet["shelf_activity"]["churn"]["denominator"] is None, packet.get("coverage", packet)


def test_phase5_ba3_inverse_metadata_must_match_replayed_state(db):
    before = filed(db)
    wrong_before = [dict(r, confidence=0.1) for r in before]
    after = [dict(r, confidence=0.5) for r in before]
    journal(db, 2, {"a": wrong_before}, {"a": after}, "2026-09-05T12:00:00Z")
    set_current(db, "a", after)
    db.commit()
    packet = report(db)
    assert not packet["ok"] or packet["shelf_activity"]["churn"]["denominator"] is None, packet.get("coverage", packet)


def test_phase5_ba3_wal_commit_during_construction_is_detected(db, monkeypatch):
    add_item(db)
    db.commit()
    db.execute("PRAGMA journal_mode=WAL")
    path = db.execute("PRAGMA database_list").fetchone()[2]
    other = sqlite3.connect(path)
    real_measure = analysis._calculate_transport_bytes
    writes = []
    def concurrent_write(packet):
        if not writes:
            assert db.in_transaction
            other.execute("UPDATE yoinks SET author='Corrected'")
            other.commit()
            writes.append(True)
        return real_measure(packet)
    monkeypatch.setattr(analysis, "_calculate_transport_bytes", concurrent_write)
    try:
        packet = report(db)
    finally:
        other.close()
    assert writes
    assert not packet["ok"] and packet["error"]["code"] == "stale_report", packet.get("items", packet)


def test_phase5_ba3_read_restores_shared_connection_busy_timeout(db):
    add_item(db)
    db.commit()
    db.execute("PRAGMA busy_timeout=5432")
    assert report(db)["ok"]
    assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5432


@pytest.mark.parametrize("kind", ["storage", "deadline"])
def test_phase5_ba3_retryable_errors_retain_contract_semantics(db, monkeypatch, kind):
    if kind == "storage":
        db.close()
        packet = report(db)
    else:
        monotonic = time.monotonic
        start = monotonic()
        packet = analysis._execute_activity({"interval": INTERVAL}, db=db, clock=NOW, start_time=start - 3)
    assert not packet["ok"]
    assert packet["error"]["code"] == {"storage": "storage_unavailable", "deadline": "deadline_exceeded"}[kind]
    assert packet["error"]["retryable"] is True, packet


@pytest.mark.parametrize("field", ["start", "end"])
def test_phase5_ba3_interval_rejects_trailing_newline_before_storage(monkeypatch, field):
    reads = []
    def connect():
        reads.append(True)
        return None, None, analysis.error_envelope("storage_unavailable", "spy"), False
    monkeypatch.setattr(analysis, "_get_connection", connect)
    interval = {**INTERVAL, field: INTERVAL[field] + "\n"}
    packet = analysis.get_library_activity({"interval": interval}, clock=NOW)
    assert not reads and packet["error"]["code"] == "validation_error", (reads, packet)


def test_phase5_ba3_detail_page_sheds_whole_rows_before_refusal(db):
    for i in range(20):
        add_item(db, str(i), author="A" * 1400)
    db.commit()
    packet = report(db)
    assert packet["ok"], packet
    args = {**packet["provenance"]["evidence_request"], "metric_id": "items.total"}
    one = analysis.get_library_activity({**args, "limit": 1}, db=db, clock=NOW)
    assert one["ok"], one
    page = analysis.get_library_activity(args, db=db, clock=NOW)
    assert page["ok"], page
    assert 0 < len(page["rows"]) < 20
    assert page["next"]["offset"] == len(page["rows"])


def test_phase5_ba3_single_fitting_identity_is_preserved(db):
    vid = "v" * 600
    add_item(db, vid)
    db.commit()
    packet = report(db)
    assert packet["ok"], packet
    page = evidence(db, packet, "items.total")
    assert page["ok"] and page["rows"][0]["row_id"] == vid, page


@pytest.mark.parametrize("kind", ["shelf", "source"])
def test_phase5_ba3_all_display_labels_are_bounded_and_explicit(db, kind):
    if kind == "shelf":
        filed(db)
        db.execute("UPDATE shelf_nodes SET name=?", ("A" * 200,))
    else:
        source_fixture(db)
        db.execute("UPDATE source_subscriptions SET display_name=?", ("A" * 200,))
    db.commit()
    packet = report(db)
    row = packet["shelf_activity"]["shelves"][0] if kind == "shelf" else packet["sources"]["details"][0]
    label = row["label"] if kind == "shelf" else row["display_name"]
    assert len(label) <= 120, row
    assert any("truncat" in k and bool(v) for k, v in row.items()), row


def test_phase5_ba3_stdio_holds_admission_through_final_render(db, monkeypatch):
    add_item(db)
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    guard = library_resources.process_guard()
    real_render = library_resources.render_tool_text
    active = []
    def render(packet):
        active.append(guard._active)
        return real_render(packet)
    monkeypatch.setattr(library_resources, "render_tool_text", render)
    result = stdio_result({"interval": INTERVAL})
    assert not result.isError
    assert active and all(n > 0 for n in active), active


def test_phase5_ba3_final_wire_serialization_is_inside_deadline(db, monkeypatch):
    add_item(db)
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    real_read = analysis.get_library_activity
    real_wire = library_resources.wire_bytes
    monotonic = time.monotonic
    finished = [False]
    elapsed = [0.0]
    def read(args):
        packet = real_read(args)
        finished[0] = True
        return packet
    def wire(payload):
        if finished[0]:
            elapsed[0] += 3.0
        return real_wire(payload)
    monkeypatch.setattr(analysis, "get_library_activity", read)
    monkeypatch.setattr(library_resources, "wire_bytes", wire)
    monkeypatch.setattr(time, "monotonic", lambda: monotonic() + elapsed[0])
    result = stdio_result({"interval": INTERVAL})
    assert result.isError and "deadline_exceeded" in result.content[0].text, result.content[0].text[:180]


NARRATION = "Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item. Net shelf membership remained unchanged."


def narration_packet():
    return {
        "ok": True, "date_basis": "capture_time", "report_revision": "a" * 64,
        "interval": {"start": "2026-09-06T00:00:00.000Z", "end": "2026-09-06T18:00:00.000Z"},
        "provenance": {"scopes": {
            "items": {"population": "current_live_saved_items", "clock": "capture_time"},
            "ops": {"population": "recorded_journal_operations", "clock": "applied_journal_time"},
        }},
        "items": {"total": {"metric_id": "items.total", "scope_ref": "items", "value": 1}},
        "shelf_activity": {"applied_operations": {"metric_id": "shelf_activity.applied_operations", "scope_ref": "ops", "value": 2},
                           "shelves": [{"shelf_id": "sh_alpha", "net": 0}]},
    }


@pytest.mark.parametrize("damage", ["wrong_metric_id", "wrong_population", "wrong_metric_clock", "no_shelves"])
def test_phase5_ba3_labelled_assertions_require_actual_metric_bindings(damage):
    packet = narration_packet()
    if damage == "wrong_metric_id":
        packet["items"]["total"]["metric_id"] = "sources.active_sources_count"
    elif damage == "wrong_population":
        packet["provenance"]["scopes"]["items"]["population"] = "retained_tombstones"
    elif damage == "wrong_metric_clock":
        packet["provenance"]["scopes"]["ops"]["clock"] = "publication_time"
    else:
        packet["shelf_activity"].pop("shelves")
    result = analysis.evaluate_narration_faithfulness(NARRATION, packet)
    assert not result["passed"], result


def test_phase5_ba3_labelled_pin_and_undo_assertions_need_operation_evidence():
    text = "Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item. A pin operation initially moved the item from Alpha to Beta, followed by an undo operation that returned it to Alpha. Net shelf membership across the interval remained unchanged."
    packet = narration_packet()
    # Two metadata-only applies with net zero cannot support a pin/move/undo.
    packet["events"] = {"rows": [{"kind": "apply"}, {"kind": "apply"}]}
    result = analysis.evaluate_narration_faithfulness(text, packet)
    assert not result["passed"], result
