"""BA-2 counterexamples: required phase5-v1 behavior, without xfails.

Disposable migrated databases, fixed UTC time, real registry/stdio adapters.
No model, resident helper, network listener, or live index.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

import library_cards
import uoink_mcp_tools
from test_phase5_acceptance import (
    INTERVAL, NOW, add_episode, add_item, analysis, db, evidence, filed,
    isolate_reader, journal, library_resources, mcp_types, membership, report,
    seed, set_current, stdio_result, uoink_mcp,
)


def value(metric):
    return metric.get("value") if isinstance(metric, dict) else metric


def source_fixture(db):
    add_item(db)
    seed.insert_subscription(db, "sub")
    seed.insert_source_item(db, "sub", "entry", video_id="a",
                            published_at_ms=seed.stamp("2026-09-05T12:00:00Z"),
                            first_seen_ms=seed.stamp("2026-09-05T12:00:00Z"),
                            last_seen_ms=seed.stamp("2026-09-05T12:00:00Z"))
    seed.insert_cursor(db, "sub")
    db.commit()


@pytest.mark.parametrize("path", [
    ("events", "total"),
    ("items", "publication_unavailable_by_reason", "missing_unindexed"),
    ("shelf_activity", "shelves", 0, "added"),
    ("shelf_activity", "shelves", 0, "removed"),
    ("shelf_activity", "shelves", 0, "net"),
    ("sources", "details", 0, "new_observations_by_state", "committed"),
])
def test_phase5_ba2_remaining_activity_counts_are_metrics(db, path):
    filed(db)
    seed.insert_subscription(db, "sub")
    seed.insert_source_item(db, "sub", "entry", video_id="a",
                            first_seen_ms=seed.stamp("2026-09-05T12:00:00Z"))
    db.commit()
    result = report(db)
    assert result["ok"], result
    metric = result
    for key in path:
        metric = metric[key]
    assert isinstance(metric, dict) and {"metric_id", "scope_ref", "evidence", "value", "unit"} <= metric.keys(), (path, metric)


def test_phase5_ba2_ratio_denominator_has_addressable_evidence(db):
    filed(db)
    packet = report(db)
    metric = packet["shelf_activity"]["churn"]
    assert metric["denominator"] == 1
    # No prescribed spelling for the descriptor container; it must resolve a
    # distinct denominator relation through the contract's evidence mechanism.
    def descriptors(obj):
        if isinstance(obj, dict):
            if obj.get("role") == "denominator" and obj.get("metric_id"):
                yield obj
            for child in obj.values():
                yield from descriptors(child)
        elif isinstance(obj, list):
            for child in obj:
                yield from descriptors(child)
    refs = list(descriptors(metric))
    assert refs, metric
    result = evidence(db, packet, refs[0]["metric_id"])
    assert result["ok"] and result["total_rows"] == 1, result


def test_phase5_ba2_provenance_binds_schema_and_observation_digests(db):
    source_fixture(db)
    p = report(db)["provenance"]
    # Envelope schema_version=1 is not the migrated database schema version.
    for concept, alternatives in {
        "input database schema": ("input_schema_version", "database_schema_version", "db_schema_version"),
        "taxonomy/run digest": ("taxonomy_run_digest", "revisions_digest", "taxonomy_run_hash"),
        "source observation digest": ("source_observation_digest", "source_observation_hash", "source_observations_digest"),
    }.items():
        assert any(k in p for k in alternatives), (concept, p.keys())


def test_phase5_ba2_metric_evidence_reports_population_and_sample_counts(db):
    source_fixture(db)
    metric = report(db)["items"]["total"]
    # Descriptors may be nested or flattened; these are the required logical
    # quantities, not activity totals inferred from a sampled page.
    descriptor = {**metric, **metric["evidence"]}
    for aliases in [("evidence_row_count", "row_count", "total_rows"),
                    ("evidence_sample_count", "sample_count", "sample_rows"),
                    ("has_more", "more_rows", "evidence_has_more")]:
        assert any(key in descriptor for key in aliases), (aliases, descriptor)


@pytest.mark.parametrize("family,field,clock", [
    ("sources", "linked_capture_union_count", "capture_time"),
    ("sources", "multiply_linked_capture_count", "capture_time"),
])
def test_phase5_ba2_source_capture_scope_uses_capture_clock(db, family, field, clock):
    source_fixture(db)
    packet = report(db, date_basis="publication_time")
    metric = packet[family][field]
    assert packet["provenance"]["scopes"][metric["scope_ref"]]["clock"] == clock


def test_phase5_ba2_journal_scope_includes_deleted_recorded_items(db):
    filed(db)
    db.execute("UPDATE yoinks SET deleted_at='2026-09-06T00:00:00Z'")
    db.commit()
    packet = report(db, interval={"start": "2026-09-01T12:00:00Z", "end": "2026-09-07T00:00:00Z"})
    assert value(packet["shelf_activity"]["applied_operations"]) == 1
    scope = packet["provenance"]["scopes"][packet["shelf_activity"]["applied_operations"]["scope_ref"]]
    assert scope["population"] != "current_live_survivors", scope


def test_phase5_ba2_zero_metadata_events_have_no_support_rows(db):
    before = filed(db)
    after = [membership("beta")]
    journal(db, 2, {"a": before}, {"a": after}, "2026-09-05T12:00:00Z")
    set_current(db, "a", after)
    db.commit()
    packet = report(db)
    # Metadata-only activity is absent even though an apply is present.
    metric = packet["shelf_activity"]["metadata_only_item_events"]
    assert value(metric) == 0
    rows = evidence(db, packet, metric["metric_id"])
    assert rows["ok"] and rows["total_rows"] == 0, rows


def test_phase5_ba2_start_size_evidence_contains_baseline_support(db):
    filed(db)
    packet = report(db)
    metric = next(r for r in packet["shelf_activity"]["shelves"] if r["shelf_id"] == "alpha")["start_size"]
    assert value(metric) == 1
    result = evidence(db, packet, metric["metric_id"])
    assert result["ok"] and result["total_rows"] > 0, result


def test_phase5_ba2_tombstone_evidence_filters_capture_interval(db):
    add_item(db, "inside", deleted_at="2026-09-08T00:00:00Z")
    add_item(db, "outside", yoinked_at="2026-09-01T00:00:00Z", deleted_at="2026-09-05T00:00:00Z")
    db.commit()
    packet = report(db)
    assert value(packet["items"]["deleted_items_excluded"]) == 1
    result = evidence(db, packet, "items.deleted_items_excluded")
    assert {r["row_id"] for r in result["rows"]} == {"inside"}, result
    assert result["rows"][0]["event_time"] == "2026-09-05T12:00:00.000Z"


def test_phase5_ba2_unlocated_evidence_includes_naive_capture(db):
    add_item(db, yoinked_at="2026-09-05T12:00:00", deleted_at="2026-09-06T00:00:00Z")
    db.commit()
    packet = report(db)
    assert value(packet["items"]["deleted_items_unlocated"]) == 1
    result = evidence(db, packet, "items.deleted_items_unlocated")
    assert result["total_rows"] == 1, result


def test_phase5_ba2_membership_label_uses_its_version(db):
    filed(db)
    seed.insert_shelf_version(db, "v2")
    db.execute("UPDATE shelf_nodes SET name='Original Alpha' WHERE version_id='v1' AND shelf_id='alpha'")
    db.execute("UPDATE shelf_nodes SET name='Renamed Alpha' WHERE version_id='v2' AND shelf_id='alpha'")
    db.execute("UPDATE library_meta SET active_version_id='v2'")
    db.commit()
    row = next(r for r in report(db)["shelf_activity"]["shelves"] if r["shelf_id"] == "alpha")
    assert row["label"] == "Original Alpha", row
    assert row["active_label"] == "Renamed Alpha"


@pytest.mark.parametrize("variant", ["padded", "blank_author"])
def test_phase5_ba2_trimmed_hint_keys_group_without_losing_originals(db, variant):
    if variant == "padded":
        add_item(db, "a", author="  Same Author  ")
        add_item(db, "b", author="Same Author")
    else:
        add_item(db, "a", author="   ", channel="Same Channel")
        add_item(db, "b", author="", channel="Same Channel")
    db.commit()
    rows = report(db)["items"]["by_creator_hint"]
    assert len(rows) == 1 and value(rows[0]["count"]) == 2, rows


def test_phase5_ba2_hint_truncation_is_explicit(db):
    add_item(db, author="A" * 200)
    db.commit()
    row = report(db)["items"]["by_creator_hint"][0]
    assert len(row["hint"]) < 200
    assert any("truncat" in k and bool(v) for k, v in row.items()), row


def test_phase5_ba2_publication_group_evidence_preserves_source_attribution(db):
    source_fixture(db)
    packet = report(db, date_basis="publication_time")
    metric = packet["items"]["by_source_type"][0]["count"]
    result = evidence(db, packet, metric["metric_id"])
    assert result["total_rows"] == 1
    assert result["rows"][0]["source_table"] == "source_items", result
    assert result["rows"][0]["source_key"] == "item_sub_entry"


def test_phase5_ba2_publication_conflict_evidence_retains_candidates(db):
    source_fixture(db)
    seed.insert_source_item(db, "sub", "second", video_id="a",
                            published_at_ms=seed.stamp("2026-09-06T12:00:00Z"))
    db.commit()
    packet = report(db, date_basis="publication_time")
    assert value(packet["items"]["publication_time_unavailable"]) == 1
    result = evidence(db, packet, "items.publication_time_unavailable")
    text = json.dumps(result)
    assert "item_sub_entry" in text and "item_sub_second" in text, result["rows"]


def test_phase5_ba2_source_capture_evidence_keys_resolve_to_reported_table(db):
    source_fixture(db)
    packet = report(db)
    result = evidence(db, packet, packet["sources"]["details"][0]["captures_in_interval"]["metric_id"])
    row = result["rows"][0]
    key_columns = {"source_items": "item_id", "yoinks": "video_id", "podcast_episodes": "id"}
    assert row["source_table"] in key_columns, row
    key = key_columns[row["source_table"]]
    assert db.execute(f"SELECT 1 FROM {row['source_table']} WHERE {key}=?", (row["source_key"],)).fetchone(), row


def test_phase5_ba2_observation_hash_changes_with_observed_author(db):
    add_item(db, author="Before")
    db.commit()
    before = evidence(db, report(db), "items.total")["rows"][0]
    db.execute("UPDATE yoinks SET author='After'")
    db.commit()
    after = evidence(db, report(db), "items.total")["rows"][0]
    assert before["details"]["author"] != after["details"]["author"]
    assert before["observation_hash"] != after["observation_hash"]


def test_phase5_ba2_evidence_uses_phase4_canonical_hash():
    observation = {"hint": "<source>&`"}
    expected = hashlib.sha256(library_cards.serialize_card(observation).encode()).hexdigest()
    assert analysis.canonical_json_hash(observation) == expected


def test_phase5_ba2_native_epoch_text_apply_counts(db):
    filed(db)
    db.execute("UPDATE library_applies SET created_at=?", (str(seed.stamp("2026-09-05T12:00:00Z")),))
    db.commit()
    packet = report(db)
    assert packet["ok"], packet
    assert value(packet["shelf_activity"]["applied_operations"]) == 1, packet["coverage"]


@pytest.mark.parametrize("encoding", ["2026-09-05T12:00:00Z", str(seed.stamp("2026-09-05T12:00:00Z"))])
@pytest.mark.parametrize("kind", ["taxonomy", "run"])
def test_phase5_ba2_revision_creation_clocks_count(db, encoding, kind):
    seed.insert_shelf_version(db, "v1", created_at=encoding)
    if kind == "run":
        db.execute("INSERT INTO library_runs(run_id,version_id,manifest_hash,state,policy_json,created_at) VALUES ('run1','v1',?,'closed','{}',?)", ("a" * 64, encoding))
    db.commit()
    field = "taxonomy_versions_created" if kind == "taxonomy" else "runs_created"
    packet = report(db)
    assert value(packet["revisions"][field]) == 1, packet["revisions"]


@pytest.mark.parametrize("path", [("items", "daily_buckets", 0, "count"), ("shelf_activity", "applied_operations"), ("sources", "details", 0, "new_observations")])
def test_phase5_ba2_prehistory_is_null_in_every_historical_metric(db, path):
    filed(db)
    seed.insert_subscription(db, "sub")
    seed.insert_source_item(db, "sub", "entry", video_id="a", first_seen_ms=seed.stamp("2026-09-08T00:00:00Z"))
    db.commit()
    # Source row qualifies by capture, with observations beginning after interval.
    interval = INTERVAL if path[0] == "sources" else {"start": "2026-08-25T00:00:00Z", "end": "2026-08-26T00:00:00Z"}
    node = report(db, interval=interval)
    for part in path:
        node = node[part]
    assert isinstance(node, dict) and node["value"] is None and node.get("recorded_count") == 0, node


def test_phase5_ba2_no_change_receipt_gap_keeps_proved_baseline(db):
    before = filed(db)
    db.execute("INSERT INTO library_operation_receipts VALUES ('no_change', ?, 2, ?, ?)", ("a" * 64, "b" * 64, '{"status":"no_change"}'))
    after = [membership("beta")]
    seed.insert_apply(db, "move", 3, 1, 2, created_at="2026-09-05T12:00:00Z",
                      forward_delta={"items": {"a": after}, "policies": {}},
                      inverse_delta={"items": {"a": before}, "policies": {}})
    set_current(db, "a", after)
    db.commit()
    packet = report(db)
    assert packet["coverage"]["cov_shelf_activity"]["coverage_status"] == "journal_complete", packet["coverage"]
    assert packet["shelf_activity"]["churn"]["denominator"] == 1


@pytest.mark.parametrize("delta", [
    {"items": {"a": [{"shelf_id": []}]}, "policies": {}},
    {"items": {}, "policies": {"a": 3}},
    {"items": {"a": [{"shelf_id": "alpha", "is_primary": "yes"}]}, "policies": {}},
])
def test_phase5_ba2_invalid_nested_values_return_named_error(db, delta):
    filed(db)
    db.execute("UPDATE library_applies SET forward_json=?", (json.dumps(delta),))
    db.commit()
    try:
        result = report(db)
    except Exception as exc:
        pytest.fail(f"Source shape escaped as {type(exc).__name__}: {exc}")
    assert result.get("ok") is False and result.get("error", {}).get("code") == "invalid_source_data", result.get("coverage", result)


@pytest.mark.parametrize("damage", ["request_hash", "receipt_status", "missing_inverse_item"])
def test_phase5_ba2_baseline_requires_full_receipt_and_inverse_binding(db, damage):
    filed(db)
    if damage == "request_hash":
        db.execute("UPDATE library_operation_receipts SET request_hash=?", ("f" * 64,))
    elif damage == "receipt_status":
        db.execute("UPDATE library_operation_receipts SET receipt_json='{" + '"status":"no_change"' + "}'")
    else:
        db.execute("UPDATE library_applies SET inverse_json='{\"items\":{},\"policies\":{}}'")
    db.commit()
    result = report(db)
    assert result.get("ok") is False or result["shelf_activity"]["churn"]["denominator"] is None, result.get("shelf_activity", result)


def test_phase5_ba2_publication_support_uses_selected_items(db):
    source_fixture(db)
    db.execute("UPDATE source_items SET published_at_ms=?", (seed.stamp("2023-09-05T12:00:00Z"),))
    db.commit()
    packet = report(db, date_basis="publication_time")
    assert value(packet["items"]["total"]) == 0
    assert packet["support_level"] == "none", packet["support_level"]


def test_phase5_ba2_cursor_is_labelled_latest_enumeration(db):
    source_fixture(db)
    packet = report(db)
    window = packet["sources"]["details"][0]["observation_window"]
    assert any("latest" in str(v).lower() and "enumeration" in str(v).lower() for v in window.values()), window


def test_phase5_ba2_reads_hold_sqlite_snapshot(db):
    add_item(db)
    db.commit()
    transactions = []
    db.set_trace_callback(lambda sql: transactions.append(db.in_transaction) if sql.startswith("SELECT video_id, source_type") else None)
    try:
        assert report(db)["ok"]
    finally:
        db.set_trace_callback(None)
    assert transactions == [True], transactions
    assert not db.in_transaction


def test_phase5_ba2_storage_exception_has_named_envelope(db):
    db.close()
    try:
        packet = report(db)
    except sqlite3.Error as exc:
        pytest.fail(f"Storage exception escaped instead of storage_unavailable: {exc}")
    assert packet["ok"] is False and packet["error"]["code"] == "storage_unavailable", packet


def test_phase5_ba2_unknown_interval_field_rejected_before_storage(monkeypatch):
    reads = []
    monkeypatch.setattr(analysis, "_get_connection", lambda: (reads.append(True), None, analysis.error_envelope("storage_unavailable", "spy"), False))
    result = analysis.get_library_activity({"interval": {**INTERVAL, "extra": True}}, clock=NOW)
    assert not reads, "Unknown nested argument reached storage"
    assert result["error"]["code"] == "validation_error"


def test_phase5_ba2_raw_stdio_duplicate_keys_rejected_before_read(db, monkeypatch):
    import anyio
    import io
    from mcp.server.stdio import stdio_server

    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    raw = ('{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
           '{"name":"get_library_activity","arguments":{"interval":' + json.dumps(INTERVAL) +
           ',"date_basis":"publication_time","date_basis":"capture_time"}}}\n')
    reads = []
    real_connect = analysis._get_connection
    monkeypatch.setattr(analysis, "_get_connection", lambda: (reads.append(True), real_connect())[1])

    async def invoke():
        async with stdio_server(stdin=anyio.wrap_file(io.StringIO(raw)), stdout=anyio.wrap_file(io.StringIO())) as (incoming, outgoing):
            try:
                message = await incoming.receive()
                if isinstance(message, Exception):
                    return
                request = mcp_types.CallToolRequest.model_validate(message.message.root.model_dump())
                await uoink_mcp.mcp._mcp_server.request_handlers[mcp_types.CallToolRequest](request)
            finally:
                await outgoing.aclose()
    anyio.run(invoke)
    assert not reads, "Actual SDK raw stdio decoder admitted duplicate date_basis keys"


def test_phase5_ba2_transaction_refusal_uses_frozen_error_code(db):
    add_item(db)
    result = report(db)
    assert result["ok"] is False
    assert result["error"]["code"] in {"validation_error", "not_found", "stale_report", "feature_unavailable", "storage_unavailable", "invalid_source_data", "recovery_pending", "resource_too_large", "deadline_exceeded", "rate_limited"}, result
    assert db.in_transaction, "Read must not commit or roll back its caller's writes"


def test_phase5_ba2_stdio_schema_matches_registry():
    result = asyncio.run(uoink_mcp.mcp._mcp_server.request_handlers[mcp_types.ListToolsRequest](mcp_types.ListToolsRequest(method="tools/list"))).root
    actual = next(t.inputSchema for t in result.tools if t.name == "get_library_activity")
    expected = uoink_mcp_tools.TOOL_REGISTRY["get_library_activity"].input_schema
    assert actual == expected


def test_phase5_ba2_small_normal_stdio_summary_succeeds(db, monkeypatch):
    for i in range(25):
        add_item(db, str(i), author=f"Author {i}")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    direct = report(db)
    assert direct["ok"]
    result = stdio_result({"interval": INTERVAL})
    assert not result.isError, result.content[0].text
    assert len(json.dumps({"jsonrpc": "2.0", "id": 1, "result": result.model_dump(mode="json", exclude_none=True)}, ensure_ascii=False).encode()) <= 65536


def test_phase5_ba2_long_label_evidence_remains_accessible(db):
    add_item(db, author="a" * 600)
    db.commit()
    packet = report(db)
    result = evidence(db, packet, "items.total")
    assert result["ok"], result
    assert result["rows"][0]["row_id"] == "a"


def test_phase5_ba2_lock_wait_obeys_deadline(db, monkeypatch):
    lock = threading.RLock()
    ready = threading.Event()
    release = threading.Event()
    def holder():
        with lock:
            ready.set()
            release.wait(0.35)
    thread = threading.Thread(target=holder)
    thread.start()
    assert ready.wait(1)
    monkeypatch.setattr(analysis, "SERVICE_DEADLINE_SEC", 0.05)
    start = time.perf_counter()
    try:
        result = report(SimpleNamespace(_conn=db, _lock=lock))
        elapsed = time.perf_counter() - start
    finally:
        release.set()
        thread.join(1)
    assert result["error"]["code"] == "deadline_exceeded", result
    assert elapsed < 0.20, f"50 ms deadline blocked on Index lock for {elapsed:.3f} s"


def test_phase5_ba2_sqlite_busy_wait_obeys_deadline(db, monkeypatch):
    path = db.execute("PRAGMA database_list").fetchone()[2]
    # Use SQLite's rollback journal so a genuine exclusive writer blocks reads.
    db.execute("PRAGMA journal_mode=DELETE")
    ready = threading.Event()
    release = threading.Event()
    def holder():
        other = sqlite3.connect(path)
        try:
            other.execute("BEGIN EXCLUSIVE")
            ready.set()
            release.wait(0.35)
        finally:
            other.rollback()
            other.close()
    thread = threading.Thread(target=holder)
    thread.start()
    assert ready.wait(1)
    monkeypatch.setattr(analysis, "SERVICE_DEADLINE_SEC", 0.05)
    start = time.perf_counter()
    try:
        result = report(db)
        elapsed = time.perf_counter() - start
    finally:
        release.set()
        thread.join(1)
    assert result["error"]["code"] == "deadline_exceeded", result
    assert elapsed < 0.20, f"50 ms deadline blocked in SQLite for {elapsed:.3f} s"


def test_phase5_ba2_stdio_serialization_is_inside_deadline(db, monkeypatch):
    add_item(db)
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    monotonic = time.monotonic
    real_render = library_resources.render_tool_text
    offset = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: monotonic() + offset[0])
    def slow_render(packet):
        offset[0] += 3.0
        return real_render(packet)
    monkeypatch.setattr(library_resources, "render_tool_text", slow_render)
    result = stdio_result({"interval": INTERVAL})
    assert result.isError and "deadline_exceeded" in result.content[0].text, result.content[0].text[:300]


@pytest.mark.parametrize("damage", ["appended_claim", "wrong_interval", "missing_revisions", "wrong_clock"])
def test_phase5_ba2_labelled_prose_cannot_bypass_assertion_binding(damage):
    packet = {
        "ok": True, "date_basis": "capture_time", "report_revision": "a" * 64,
        "interval": {"start": "2026-09-06T00:00:00.000Z", "end": "2026-09-06T18:00:00.000Z"},
        "items": {"total": {"value": 1}},
        "shelf_activity": {"applied_operations": {"value": 2}, "shelves": [{"shelf_id": "sh_alpha", "net": 0}]},
    }
    narration = "Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item. Net shelf membership remained unchanged."
    if damage == "appended_claim":
        narration += " The moon consists of cheese and 9000 creators agree."
    elif damage == "wrong_interval":
        packet["interval"] = {"start": "2026-08-01T00:00:00Z", "end": "2026-08-02T00:00:00Z"}
    elif damage == "missing_revisions":
        packet.pop("report_revision")
    else:
        packet["date_basis"] = "publication_time"
    result = analysis.evaluate_narration_faithfulness(narration, packet)
    assert result["passed"] is False, result
