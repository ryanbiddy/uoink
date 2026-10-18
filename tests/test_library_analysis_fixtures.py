"""tests/test_library_analysis_fixtures.py - Phase 5 Acceptance Gates & Fixture Tests.

Contract: phase5-v1 (docs/library/PHASE5-CONTRACT-2026-09-08.md).
Implements every test name from the contract's acceptance table:
- Seven gate tests:
  1. test_gate1_backlog_import_vs_steady_capture
  2. test_gate2_cross_posted_clips_not_independent_creators
  3. test_gate3_creator_dual_channel_unmerged_hints
  4. test_gate4_deletion_invalidates_derived_report
  5. test_gate5_undo_correction_reverts_journal_and_invalidates
  6. test_gate6_single_source_interval_thin_support
  7. test_gate7_pre_observation_interval_coverage_gap
- Activity and provenance tests:
  8. test_activity_interval_half_open_utc
  9. test_activity_mixed_stored_clocks
  10. test_activity_publication_dedup_and_conflict
  11. test_activity_denominator_and_pagination
  12. test_activity_journal_shapes_and_no_change_receipts
  13. test_activity_primary_only_and_initial_filing
  14. test_activity_history_chain_and_clock_regression
  15. test_activity_deleted_journal_survivors_and_restore
  16. test_activity_source_observation_windows
  17. test_activity_source_overlap_and_legacy_link
  18. test_activity_corrections_outside_interval
  19. test_activity_provenance_for_every_metric
  20. test_activity_registry_stdio_http_parity
  21. test_activity_read_has_no_side_effects
  22. test_activity_wire_budget_and_untrusted_labels
  23. test_activity_deadline_and_work_bounds
  24. test_activity_cost_548_and_10000
  25. test_activity_dashboard_evidence_and_staleness
  26. test_activity_whats_new_semantic_parity
  27. test_activity_part_b_remains_deferred
  28. test_narration_faithfulness_metric
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

import library_analysis
import library_resources
from index import Index
import uoink_mcp_tools
import uoink_mcp


ROOT_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Test DB Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_reader():
    library_analysis.reset_rate_limiter()
    yield
    library_analysis.reset_rate_limiter()


@pytest.fixture
def tmp_dir():
    p = Path(tempfile.mkdtemp(prefix="uoink_p5_test_"))
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


def create_fixture_db(tmp_dir: Path, name: str = "fixture.db") -> sqlite3.Connection:
    """Create an isolated SQLite database and apply migrations 0001 through 0028."""
    db_path = tmp_dir / name
    idx = Index.open(db_path)
    conn = idx._conn
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def stamp(iso_str: str) -> int:
    """Convert UTC ISO string to epoch milliseconds."""
    dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def insert_yoink(
    conn: sqlite3.Connection,
    video_id: str,
    *,
    yoinked_at: Optional[str] = "2026-09-01T12:00:00.000Z",
    source_type: str = "video",
    platform: str = "youtube",
    author: str = "Author One",
    channel: str = "Channel One",
    deleted_at: Optional[str] = None,
    title: str = "Title",
    metadata_json: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO yoinks ("
        "  video_id, slug, channel, title, topic, hook_type, yoinked_at, deleted_at, "
        "  corpus_path, sidecar_path, schema_version, source_type, platform, author, metadata_json"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            video_id,
            f"slug-{video_id}",
            channel,
            title,
            "test_topic",
            "hook",
            yoinked_at,
            deleted_at,
            "corpus",
            "sidecar",
            2,
            source_type,
            platform,
            author,
            metadata_json,
        ),
    )


def insert_subscription(
    conn: sqlite3.Connection,
    source_id: str,
    *,
    kind: str = "youtube_channel",
    adapter: str = "youtube_channel_rss_v1",
    display_name: str = "Display Name",
    created_at_ms: int = 1788264000000,
    legacy_feed_id: Optional[int] = None,
    archived: int = 0,
) -> None:
    det = 0 if archived else 1
    consent = "off" if archived else "on"
    conn.execute(
        "INSERT INTO source_subscriptions ("
        "  source_id, kind, source_key, canonical_url, display_name, adapter, "
        "  detection_enabled, archived, consent_state, revision, consent_epoch, boundary, "
        "  created_at_ms, updated_at_ms, legacy_feed_id"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 'none', ?, ?, ?)",
        (
            source_id,
            kind,
            f"key_{source_id}",
            f"https://example.com/{source_id}",
            display_name,
            adapter,
            det,
            archived,
            consent,
            created_at_ms,
            created_at_ms,
            legacy_feed_id,
        ),
    )


def insert_cursor(
    conn: sqlite3.Connection,
    source_id: str,
    *,
    revision: int = 1,
    last_poll_success_ms: Optional[int] = None,
    last_poll_attempt_ms: Optional[int] = None,
    coverage: str = "complete",
    observed_count: int = 10,
    truncated: int = 0,
) -> None:
    conn.execute(
        "INSERT INTO source_detection_cursors ("
        "  source_id, revision, last_poll_attempt_ms, last_poll_success_ms, coverage, observed_count, truncated"
        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source_id, revision, last_poll_attempt_ms, last_poll_success_ms, coverage, observed_count, truncated),
    )


def insert_source_item(
    conn: sqlite3.Connection,
    source_id: str,
    entry_id: str,
    *,
    video_id: Optional[str] = None,
    published_at_ms: Optional[int] = None,
    first_seen_ms: int = 1788264000000,
    last_seen_ms: int = 1788264000000,
    state: Optional[str] = None,
) -> None:
    st = state or ("committed" if video_id else "observed")
    item_id = f"item_{source_id}_{entry_id}"
    conn.execute(
        "INSERT INTO source_items ("
        "  item_id, source_id, entry_id, capture_key, canonical_url, title, "
        "  published_at_ms, first_seen_ms, last_seen_ms, first_scan_revision, "
        "  metadata_json, eligibility, state, video_id"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '{}', 'none', ?, ?)",
        (
            item_id,
            source_id,
            entry_id,
            f"ck_{source_id}_{entry_id}",
            f"https://example.com/{entry_id}",
            f"Title {entry_id}",
            published_at_ms,
            first_seen_ms,
            last_seen_ms,
            st,
            video_id,
        ),
    )


def insert_shelf(conn: sqlite3.Connection, shelf_id: str, created_at: str = "2026-09-01T00:00:00.000Z") -> None:
    conn.execute("INSERT OR IGNORE INTO shelves (shelf_id, created_at) VALUES (?, ?)", (shelf_id, created_at))
    versions = [r[0] for r in conn.execute("SELECT version_id FROM shelf_versions").fetchall()]
    for vid in versions:
        conn.execute(
            "INSERT OR IGNORE INTO shelf_nodes (version_id, shelf_id, parent_shelf_id, name, path_json, definition, include_json, exclude_json, retired) "
            "VALUES (?, ?, NULL, ?, ?, 'definition', '[]', '[]', 0)",
            (vid, shelf_id, shelf_id, json.dumps([shelf_id])),
        )


def insert_shelf_version(
    conn: sqlite3.Connection,
    version_id: str,
    revision_hash: Optional[str] = None,
    status: Optional[str] = None,
    created_at: str = "2026-09-01T00:00:00.000Z",
) -> None:
    rev_hash = revision_hash or hashlib.sha256(f"rev_{version_id}".encode("utf-8")).hexdigest()
    if status is None:
        has_active = conn.execute("SELECT 1 FROM shelf_versions WHERE status='active'").fetchone()
        st = "approved" if has_active else "active"
    else:
        st = status
    conn.execute(
        "INSERT OR IGNORE INTO shelf_versions (version_id, revision_hash, status, created_at) VALUES (?, ?, ?, ?)",
        (version_id, rev_hash, st, created_at),
    )
    shelves = [r[0] for r in conn.execute("SELECT shelf_id FROM shelves").fetchall()]
    for sid in shelves:
        conn.execute(
            "INSERT OR IGNORE INTO shelf_nodes (version_id, shelf_id, parent_shelf_id, name, path_json, definition, include_json, exclude_json, retired) "
            "VALUES (?, ?, NULL, ?, ?, 'definition', '[]', '[]', 0)",
            (version_id, sid, sid, json.dumps([sid])),
        )


MEMBERSHIP_COLUMNS = (
    "video_id", "shelf_id", "version_id", "source_revision", "source", "locked",
    "is_primary", "confidence", "evidence_json", "assigned_at",
)


def membership_row(
    video_id: str,
    shelf_id: str,
    *,
    is_primary: int = 1,
    version_id: str = "v1",
    source_revision: str = "rev",
    source: str = "user",
    locked: int = 0,
    confidence: Optional[float] = 1.0,
    evidence_json: Optional[str] = "{}",
    assigned_at: str = "2026-09-01T10:00:00.000Z",
) -> dict:
    """One complete item_shelves row, as the library service journals it (BA-05)."""
    return {
        "video_id": video_id,
        "shelf_id": shelf_id,
        "version_id": version_id,
        "source_revision": source_revision,
        "source": source,
        "locked": locked,
        "is_primary": is_primary,
        "confidence": confidence,
        "evidence_json": evidence_json,
        "assigned_at": assigned_at,
    }


def policy_row(video_id: str, exclusive_move: int = 1) -> dict:
    """One library_item_policy row as the library service journals it."""
    return {"video_id": video_id, "exclusive_move": exclusive_move}


def set_item_shelves(conn: sqlite3.Connection, video_id: str, rows: list) -> None:
    """Make item_shelves hold exactly ``rows`` (complete membership rows) for ``video_id``."""
    conn.execute("DELETE FROM item_shelves WHERE video_id=?", (video_id,))
    for row in rows:
        conn.execute(
            "INSERT INTO item_shelves (video_id, shelf_id, version_id, source_revision, source, locked, is_primary, confidence, evidence_json, assigned_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(row.get(col, video_id if col == "video_id" else None) for col in MEMBERSHIP_COLUMNS),
        )


def insert_apply(
    conn: sqlite3.Connection,
    apply_id: str,
    operation_sequence: int,
    before_rev: int,
    after_rev: int,
    *,
    kind: str = "apply",
    created_at: str = "2026-09-01T12:00:00.000Z",
    forward_delta: Optional[dict] = None,
    inverse_delta: Optional[dict] = None,
    undo_of: Optional[str] = None,
) -> None:
    f_json = json.dumps(forward_delta or {"items": {}, "policies": {}})
    i_json = json.dumps(inverse_delta or {"items": {}, "policies": {}})
    auth_hash = hashlib.sha256(f"{apply_id}_{operation_sequence}_{before_rev}_{after_rev}".encode("utf-8")).hexdigest()
    req_hash = hashlib.sha256(f"req_{apply_id}".encode("utf-8")).hexdigest()
    receipt_json = json.dumps({"status": "applied", "apply_id": apply_id})
    op_key = f"op_key_{apply_id}"

    conn.execute(
        "INSERT INTO library_operation_receipts ("
        "  operation_key, request_hash, operation_sequence, authoritative_record_hash, receipt_json"
        ") VALUES (?, ?, ?, ?, ?)",
        (
            op_key,
            req_hash,
            operation_sequence,
            auth_hash,
            receipt_json,
        ),
    )
    conn.execute(
        "INSERT INTO library_applies ("
        "  apply_id, operation_key, request_hash, kind, before_revision, after_revision, operation_sequence, "
        "  authoritative_record_hash, forward_json, inverse_json, receipt_json, undo_of, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            apply_id,
            op_key,
            req_hash,
            kind,
            before_rev,
            after_rev,
            operation_sequence,
            auth_hash,
            f_json,
            i_json,
            receipt_json,
            undo_of,
            created_at,
        ),
    )
    conn.execute(
        "UPDATE library_meta SET projection_revision=?, last_operation_sequence=? WHERE singleton=1",
        (after_rev, operation_sequence),
    )


# ---------------------------------------------------------------------------
# Seven Acceptance Gates (test_gate1_* to test_gate7_*)
# ---------------------------------------------------------------------------

def test_gate1_backlog_import_vs_steady_capture(tmp_dir):
    """Gate 1: 200 backlog items vs 5 steady captures over 5 days.

    Day 1 gives A1 201 captures vs A2 1 publication. Historical publications cannot
    be called current publishing activity.
    """
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Seed 1 source subscription for the backlog and steady series
    insert_subscription(conn, "src_dev", display_name="Steady Dev")
    insert_cursor(conn, "src_dev", last_poll_success_ms=stamp("2026-09-06T00:00:00Z"))

    # 200 backlog items captured on Day 1 (2026-09-01T10:00:00Z), published 2022-2024
    for i in range(1, 201):
        vid = f"backlog_{i:03d}"
        insert_yoink(conn, vid, yoinked_at="2026-09-01T10:00:00.000Z", author="Backlog Author", channel="Dev Channel")
        pub_ms = stamp(f"2023-05-{(i % 28) + 1:02d}T10:00:00Z")
        insert_source_item(conn, "src_dev", f"e_backlog_{i:03d}", video_id=vid, published_at_ms=pub_ms, first_seen_ms=stamp("2026-09-01T10:00:00Z"))

    # 5 steady items: 1 per day (2026-09-01 through 2026-09-05)
    for d in range(1, 6):
        vid = f"steady_day_{d}"
        cap_iso = f"2026-09-0{d}T12:00:00.000Z"
        pub_iso = f"2026-09-0{d}T11:00:00.000Z"
        insert_yoink(conn, vid, yoinked_at=cap_iso, author="Steady Dev", channel="Dev Channel")
        insert_source_item(conn, "src_dev", f"e_steady_{d}", video_id=vid, published_at_ms=stamp(pub_iso), first_seen_ms=stamp(cap_iso))

    conn.commit()

    # Query Day 1 with capture_time (A1)
    req_a1 = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res_a1 = library_analysis.get_library_activity(req_a1, db=conn, clock=fixed_as_of)
    assert res_a1["ok"] is True
    assert res_a1["items"]["total"]["value"] == 201
    assert "capture_is_not_publication" in res_a1["warnings"]
    assert res_a1["analysis_scope"] == "descriptive"
    assert res_a1["trend_eligible"] is False
    assert res_a1["independent_creator_count"] is None
    assert res_a1["independent_creators_minimum_met"] is False

    # Query Day 1 with publication_time (A2)
    req_a2 = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "publication_time",
    }
    res_a2 = library_analysis.get_library_activity(req_a2, db=conn, clock=fixed_as_of)
    assert res_a2["ok"] is True
    assert res_a2["items"]["total"]["value"] == 1
    assert res_a2["analysis_scope"] == "descriptive"
    assert res_a2["trend_eligible"] is False


def test_gate2_cross_posted_clips_not_independent_creators(tmp_dir):
    """Gate 2: Three cross-posted clips yield 3 captures, no content-origin claim.

    Aggregator succeeds with the clips table unread; independent_creator_count is null.
    """
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Insert 3 yoinks across 3 platforms with identical content
    insert_yoink(conn, "clip_yt_1", yoinked_at="2026-09-05T10:00:00.000Z", platform="youtube", author="AlphaCorp", channel="AlphaYT")
    insert_yoink(conn, "clip_tt_2", yoinked_at="2026-09-05T11:00:00.000Z", platform="tiktok", author="AlphaCorp", channel="AlphaTikTok")
    insert_yoink(conn, "clip_x_3", yoinked_at="2026-09-05T12:00:00.000Z", platform="x", author="AlphaCorp", channel="AlphaX")

    # Insert identical clip text into clips table (migration 0024)
    for idx, vid in enumerate(("clip_yt_1", "clip_tt_2", "clip_x_3"), 1):
        conn.execute(
            "INSERT INTO clips (clip_id, video_id, seq, start, end, text) "
            "VALUES (?, ?, 1, 0.0, 15.0, 'Breaking news on artificial intelligence milestone.')",
            (idx, vid),
        )
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    assert res["items"]["total"]["value"] == 3
    # 3 distinct platform-qualified hint rows
    assert len(res["items"]["by_creator_hint"]) == 3
    assert res["independent_creator_count"] is None
    assert res["independent_creators_minimum_met"] is False
    assert res["support_level"] == "unresolved"


def test_gate3_creator_dual_channel_unmerged_hints(tmp_dir):
    """Gate 3: Same author string across YouTube and podcast stays 2 platform-qualified hints."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # 2 items on YouTube with exact same author "Alice Smith"
    insert_yoink(conn, "vid_yt_1", yoinked_at="2026-09-05T10:00:00.000Z", platform="youtube", author="Alice Smith", channel="Alice Channel")
    insert_yoink(conn, "vid_yt_2", yoinked_at="2026-09-05T11:00:00.000Z", platform="youtube", author="Alice Smith", channel="Alice Channel")

    # 1 item on podcast with author "Alice Smith"
    insert_yoink(conn, "vid_pod_1", yoinked_at="2026-09-05T12:00:00.000Z", platform="podcast", author="Alice Smith", channel="Alice Podcast")

    # 1 item with case variant "alice smith"
    insert_yoink(conn, "vid_yt_3", yoinked_at="2026-09-05T13:00:00.000Z", platform="youtube", author="alice smith", channel="Alice Channel")

    # 1 item with unknown/empty hint
    insert_yoink(conn, "vid_unk_1", yoinked_at="2026-09-05T14:00:00.000Z", platform="youtube", author="", channel="")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    assert res["items"]["total"]["value"] == 5

    hints = res["items"]["by_creator_hint"]
    # Check that YouTube 'Alice Smith' has count 2
    yt_alice = next(h for h in hints if h["platform"] == "youtube" and h["hint"] == "Alice Smith")
    assert yt_alice["count"]["value"] == 2

    # Check podcast 'Alice Smith' is separate with count 1
    pod_alice = next(h for h in hints if h["platform"] == "podcast" and h["hint"] == "Alice Smith")
    assert pod_alice["count"]["value"] == 1

    # Case variant stays separate
    case_variant = next(h for h in hints if h["platform"] == "youtube" and h["hint"] == "alice smith")
    assert case_variant["count"]["value"] == 1

    # Unknown hint is present
    unk_hint = next(h for h in hints if h["hint"] == "unknown")
    assert unk_hint["count"]["value"] == 1
    assert res["independent_creators_minimum_met"] is False


def test_gate4_deletion_invalidates_derived_report(tmp_dir):
    """Gate 4: Soft-deletion drops live total from 5 to 4, changes binding, old detail request refuses stale_report."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    for i in range(1, 6):
        insert_yoink(conn, f"item_{i}", yoinked_at=f"2026-09-05T1{i}:00:00.000Z")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res1 = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res1["ok"] is True
    assert res1["items"]["total"]["value"] == 5
    rev1 = res1["report_revision"]

    # Soft-delete item_5
    conn.execute("UPDATE yoinks SET deleted_at='2026-09-05T18:00:00.000Z' WHERE video_id='item_5'")
    conn.commit()

    # Re-request summary
    res2 = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res2["ok"] is True
    assert res2["items"]["total"]["value"] == 4
    assert res2["items"]["deleted_items_excluded"] == 1
    rev2 = res2["report_revision"]
    assert rev2 != rev1

    # Attempt detail request using stale rev1
    detail_req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "detail": "creator_hints",
        "expected_revision": rev1,
    }
    res_detail = library_analysis.get_library_activity(detail_req, db=conn, clock=fixed_as_of)
    assert res_detail["ok"] is False
    assert res_detail["error"]["code"] == "stale_report"


def test_gate5_undo_correction_reverts_journal_and_invalidates(tmp_dir):
    """Gate 5: Pin then undo reproduces 2 ops, 2 item-change events, 4 mutations, net 0, 1/1 churn."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Seed 1 live item
    insert_yoink(conn, "vid_undo_1", yoinked_at="2026-09-01T10:00:00.000Z")
    insert_shelf(conn, "sh_alpha")
    insert_shelf(conn, "sh_beta")
    insert_shelf_version(conn, "v1")
    conn.commit()

    # Complete journaled rows; each inverse equals the replayed before state exactly.
    alpha_seed = membership_row("vid_undo_1", "sh_alpha", source_revision="rev1", assigned_at="2026-09-01T10:00:00.000Z")
    beta_pinned = membership_row("vid_undo_1", "sh_beta", source_revision="rev1", locked=1, confidence=None, assigned_at="2026-09-06T02:00:00.000Z")
    alpha_restored = membership_row("vid_undo_1", "sh_alpha", source_revision="rev1", assigned_at="2026-09-06T04:00:00.000Z")

    # Operation 1 (Seed prior to queried interval): files vid_undo_1 in sh_alpha at 2026-09-01T10:00:00.000Z
    f_op1 = {"items": {"vid_undo_1": [alpha_seed]}, "policies": {}}
    i_op1 = {"items": {"vid_undo_1": []}, "policies": {}}
    insert_apply(conn, "app_01", 1, 0, 1, created_at="2026-09-01T10:00:00.000Z", forward_delta=f_op1, inverse_delta=i_op1)

    # Operation 2 (in interval): pin/move from Alpha to Beta at 2026-09-06T02:00:00.000Z
    f_op2 = {"items": {"vid_undo_1": [beta_pinned]}, "policies": {}}
    i_op2 = {"items": {"vid_undo_1": [alpha_seed]}, "policies": {}}
    insert_apply(conn, "app_02", 2, 1, 2, created_at="2026-09-06T02:00:00.000Z", forward_delta=f_op2, inverse_delta=i_op2)

    # Operation 3 (in interval): undo of app_02, returns from Beta to Alpha at 2026-09-06T04:00:00.000Z
    f_op3 = {"items": {"vid_undo_1": [alpha_restored]}, "policies": {}}
    i_op3 = {"items": {"vid_undo_1": [beta_pinned]}, "policies": {}}
    insert_apply(conn, "app_03", 3, 2, 3, kind="undo", undo_of="app_02", created_at="2026-09-06T04:00:00.000Z", forward_delta=f_op3, inverse_delta=i_op3)

    # Set current membership in item_shelves to match ending projection (vid_undo_1 in sh_alpha)
    set_item_shelves(conn, "vid_undo_1", [alpha_restored])
    conn.commit()

    # Query full interval [2026-09-06T00:00:00.000Z, 2026-09-06T18:00:00.000Z)
    req = {
        "interval": {"start": "2026-09-06T00:00:00.000Z", "end": "2026-09-06T18:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    sa = res["shelf_activity"]
    assert sa["applied_operations"]["value"] == 2
    assert sa["item_change_events"]["value"] == 2
    assert sa["membership_mutations"]["value"] == 4
    assert sa["affected_items"]["value"] == 1

    # Shelves net
    alpha_row = next(s for s in sa["shelves"] if s["shelf_id"] == "sh_alpha")
    beta_row = next(s for s in sa["shelves"] if s["shelf_id"] == "sh_beta")
    assert alpha_row["added"] == 1 and alpha_row["removed"] == 1 and alpha_row["net"] == 0
    assert beta_row["added"] == 1 and beta_row["removed"] == 1 and beta_row["net"] == 0
    assert alpha_row["start_size"]["value"] == 1
    assert alpha_row["end_size"]["value"] == 1
    assert beta_row["start_size"]["value"] == 0
    assert beta_row["end_size"]["value"] == 0

    # Churn: 1/1 = 100.0%
    assert sa["churn"]["numerator"] == 1
    assert sa["churn"]["denominator"] == 1
    assert sa["churn"]["percent"] == 100.0

    # Narrower interval [2026-09-06T00:00:00.000Z, 2026-09-06T03:00:00.000Z) ending before undo
    req_narrow = {
        "interval": {"start": "2026-09-06T00:00:00.000Z", "end": "2026-09-06T03:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res_narrow = library_analysis.get_library_activity(req_narrow, db=conn, clock=fixed_as_of)
    assert res_narrow["ok"] is True
    sa_n = res_narrow["shelf_activity"]
    assert sa_n["applied_operations"]["value"] == 1
    alpha_n = next(s for s in sa_n["shelves"] if s["shelf_id"] == "sh_alpha")
    beta_n = next(s for s in sa_n["shelves"] if s["shelf_id"] == "sh_beta")
    assert alpha_n["net"] == -1
    assert beta_n["net"] == 1


def test_gate6_single_source_interval_thin_support(tmp_dir):
    """Gate 6: Three linked items yield single_source; removing links yields unresolved with unlinked hint groups."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_subscription(conn, "src_solitary", display_name="Solitary Feed")
    insert_cursor(conn, "src_solitary", last_poll_success_ms=stamp("2026-09-07T12:00:00Z"))

    for i in range(1, 4):
        vid = f"sol_{i}"
        insert_yoink(conn, vid, yoinked_at=f"2026-09-07T1{i}:00:00.000Z", author="Solo Host", channel="Solitary Feed")
        insert_source_item(conn, "src_solitary", f"entry_{i}", video_id=vid, first_seen_ms=stamp("2026-09-07T10:00:00Z"))
    conn.commit()

    req = {
        "interval": {"start": "2026-09-07T00:00:00.000Z", "end": "2026-09-08T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    assert res["items"]["total"]["value"] == 3
    assert res["sources"]["active_sources_count"]["value"] == 1
    assert res["support_level"] == "single_source"
    assert res["sources"]["unlinked_hint_groups_count"]["value"] == 0

    # Remove the source links
    conn.execute("DELETE FROM source_items")
    conn.commit()

    res_unlinked = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res_unlinked["ok"] is True
    assert res_unlinked["sources"]["active_sources_count"]["value"] == 0
    assert res_unlinked["sources"]["unlinked_hint_groups_count"]["value"] > 0
    assert res_unlinked["support_level"] == "unresolved"


def test_gate7_pre_observation_interval_coverage_gap(tmp_dir):
    """Gate 7: Query before history returns null historical activity with no_history; older verified pub date remains countable."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Earliest recorded capture is 2026-01-01T00:00:00.000Z
    # But item has verified publication instant in June 2025: 2025-06-15T12:00:00.000Z
    insert_yoink(conn, "pioneer_1", yoinked_at="2026-01-01T00:00:00.000Z")
    insert_subscription(conn, "src_pioneer", created_at_ms=stamp("2026-01-01T00:00:00Z"))
    insert_source_item(
        conn,
        "src_pioneer",
        "entry_p1",
        video_id="pioneer_1",
        published_at_ms=stamp("2025-06-15T12:00:00Z"),
        first_seen_ms=stamp("2026-01-01T00:00:00Z"),
    )
    conn.commit()

    # Query June 2025 under capture_time: prehistory
    req_pre = {
        "interval": {"start": "2025-06-01T00:00:00.000Z", "end": "2025-06-30T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res_pre = library_analysis.get_library_activity(req_pre, db=conn, clock=fixed_as_of)
    assert res_pre["ok"] is True
    assert res_pre["items"]["total"]["value"] is None
    assert res_pre["items"]["total"]["recorded_count"] == 0
    assert res_pre["coverage"]["cov_capture"]["coverage_status"] == "no_history"
    assert res_pre["shelf_activity"]["churn"]["value"] is None

    # Query June 2025 under publication_time: the 2025 publication date is verified and countable
    req_pub = {
        "interval": {"start": "2025-06-01T00:00:00.000Z", "end": "2025-06-30T00:00:00.000Z"},
        "date_basis": "publication_time",
    }
    res_pub = library_analysis.get_library_activity(req_pub, db=conn, clock=fixed_as_of)
    assert res_pub["ok"] is True
    assert res_pub["items"]["total"]["value"] == 1
    assert res_pub["coverage"]["cov_publication"]["coverage_status"] == "retained_records"


# ---------------------------------------------------------------------------
# Specific Activity, Clock & Boundary Tests (test_activity_*)
# ---------------------------------------------------------------------------

def test_activity_interval_half_open_utc(tmp_dir):
    """Test half-open [start, end) interval semantics, leap day, rolling 31 buckets, and validation errors."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Item exactly at start, item in middle, item exactly at end
    insert_yoink(conn, "item_start", yoinked_at="2026-09-01T00:00:00.000Z")
    insert_yoink(conn, "item_mid", yoinked_at="2026-09-01T12:00:00.000Z")
    insert_yoink(conn, "item_end", yoinked_at="2026-09-02T00:00:00.000Z")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    # Start included, end excluded -> exactly 2 items
    assert res["items"]["total"]["value"] == 2

    # Leap day valid: 2024-02-29
    leap_as_of = datetime.datetime(2024, 3, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    req_leap = {
        "interval": {"start": "2024-02-28T00:00:00.000Z", "end": "2024-02-29T23:59:59.000Z"},
        "date_basis": "capture_time",
    }
    res_leap = library_analysis.get_library_activity(req_leap, db=conn, clock=leap_as_of)
    assert res_leap["ok"] is True

    # 30-day rolling window spanning 31 calendar days -> exactly 31 daily buckets
    req_31 = {
        "interval": {"start": "2026-08-01T12:00:00.000Z", "end": "2026-08-31T12:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res_31 = library_analysis.get_library_activity(req_31, db=conn, clock=fixed_as_of)
    assert res_31["ok"] is True
    assert len(res_31["items"]["daily_buckets"]) == 31

    # Rejected cases:
    # 1. start >= end
    r1 = library_analysis.get_library_activity(
        {"interval": {"start": "2026-09-02T00:00:00Z", "end": "2026-09-01T00:00:00Z"}},
        db=conn,
        clock=fixed_as_of,
    )
    assert r1["ok"] is False and r1["error"]["code"] == "validation_error"

    # 2. future beyond as_of
    r2 = library_analysis.get_library_activity(
        {"interval": {"start": "2026-09-01T00:00:00Z", "end": "2026-09-10T00:00:00Z"}},
        db=conn,
        clock=fixed_as_of,
    )
    assert r2["ok"] is False and r2["error"]["code"] == "validation_error"

    # 3. duration > 30 days
    r3 = library_analysis.get_library_activity(
        {"interval": {"start": "2026-07-01T00:00:00Z", "end": "2026-08-15T00:00:00Z"}},
        db=conn,
        clock=fixed_as_of,
    )
    assert r3["ok"] is False and r3["error"]["code"] == "validation_error"

    # 4. naive timestamps (missing Z)
    r4 = library_analysis.get_library_activity(
        {"interval": {"start": "2026-09-01T00:00:00", "end": "2026-09-02T00:00:00"}},
        db=conn,
        clock=fixed_as_of,
    )
    assert r4["ok"] is False and r4["error"]["code"] == "validation_error"


def test_activity_mixed_stored_clocks(tmp_dir):
    """Test offset ISO, GMT RSS, and epoch ms normalization into same UTC bucket, plus naive/date-only exclusions."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # 1. Offset ISO: 2026-09-01T14:00:00+02:00 -> 2026-09-01T12:00:00.000Z
    insert_yoink(conn, "v_offset", yoinked_at="2026-09-01T14:00:00+02:00")

    # 2. Episode with GMT RSS date: "Tue, 01 Sep 2026 12:00:00 GMT" -> 2026-09-01T12:00:00.000Z
    insert_yoink(conn, "v_rss", yoinked_at="2026-09-01T12:00:00.000Z")
    conn.execute("INSERT INTO podcast_feeds (id, feed_url, title, added_at) VALUES (1, 'https://feed.example.com/rss', 'Podcast', '2026-09-01T00:00:00.000Z')")
    conn.execute(
        "INSERT INTO podcast_episodes (id, feed_id, guid, yoink_video_id, published_at, status, discovered_at) "
        "VALUES (1, 1, 'guid_1', 'v_rss', 'Tue, 01 Sep 2026 12:00:00 GMT', 'ready', '2026-09-01T00:00:00.000Z')"
    )

    # 3. Source item with epoch ms: 1788264000000 -> 2026-09-01T12:00:00.000Z
    insert_yoink(conn, "v_epoch", yoinked_at="2026-09-01T12:00:00.000Z")
    insert_subscription(conn, "sub_c", display_name="Sub C")
    insert_source_item(conn, "sub_c", "e_c", video_id="v_epoch", published_at_ms=1788264000000)

    # 4. Local-naive capture: "2026-09-01T12:00:00" -> timezone_unknown exclusion
    insert_yoink(conn, "v_naive", yoinked_at="2026-09-01T12:00:00")

    # 5. Date-only publication: "2026-09-01" -> date_only exclusion
    insert_yoink(conn, "v_dateonly", yoinked_at="2026-09-01T12:00:00.000Z")
    conn.execute(
        "INSERT INTO podcast_episodes (id, feed_id, guid, yoink_video_id, published_at, status, discovered_at) "
        "VALUES (2, 1, 'guid_2', 'v_dateonly', '2026-09-01', 'ready', '2026-09-01T00:00:00.000Z')"
    )
    conn.commit()

    req = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    # v_offset, v_rss, v_epoch, v_dateonly entered UTC bucket (total 4). v_naive excluded due to timezone_unknown
    assert res["items"]["total"]["value"] == 4
    assert res["items"]["capture_time_unavailable"] == 1
    assert res["items"]["live_population"] == 5

    # Check publication view
    req_pub = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "publication_time",
    }
    res_pub = library_analysis.get_library_activity(req_pub, db=conn, clock=fixed_as_of)
    assert res_pub["ok"] is True
    assert res_pub["items"]["publication_unavailable_by_reason"]["date_only"] >= 1


def test_activity_publication_dedup_and_conflict(tmp_dir):
    """Episode + 2 source links count 1 item; conflicting chosen tier excludes item; uncaptured observations excluded."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Item 1: linked to 1 episode and 2 source items with agreeing timestamps
    insert_yoink(conn, "v_agree", yoinked_at="2026-09-01T12:00:00.000Z")
    insert_subscription(conn, "sub_1", display_name="Sub 1")
    insert_subscription(conn, "sub_2", display_name="Sub 2")
    conn.execute("INSERT INTO podcast_feeds (id, feed_url, title, added_at) VALUES (1, 'https://f.com', 'Pod', '2026-09-01T00:00:00.000Z')")
    conn.execute("INSERT INTO podcast_episodes (id, feed_id, guid, yoink_video_id, published_at, status, discovered_at) VALUES (1, 1, 'g1', 'v_agree', '2026-09-01T12:00:00.000Z', 'ready', '2026-09-01T00:00:00.000Z')")
    insert_source_item(conn, "sub_1", "e1", video_id="v_agree", published_at_ms=1788264000000)
    insert_source_item(conn, "sub_2", "e2", video_id="v_agree", published_at_ms=1788264000000)

    # Item 2: linked to 2 source items with conflicting publication timestamps (Tier 1 conflict)
    insert_yoink(conn, "v_conflict", yoinked_at="2026-09-01T12:00:00.000Z")
    insert_source_item(conn, "sub_1", "e_c1", video_id="v_conflict", published_at_ms=1788264000000)
    insert_source_item(conn, "sub_2", "e_c2", video_id="v_conflict", published_at_ms=1788350400000)

    # Uncaptured observation (video_id is NULL)
    insert_source_item(conn, "sub_1", "e_uncaptured", video_id=None, published_at_ms=1788264000000)
    conn.commit()

    req = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "publication_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    # Exactly 1 item counted (v_agree), v_conflict excluded with conflict, uncaptured ignored
    assert res["items"]["total"]["value"] == 1
    assert res["items"]["publication_unavailable_by_reason"]["conflict"] == 1


def test_activity_denominator_and_pagination(tmp_dir):
    """Top-20 plus other equals disjoint full partition; 0/0 is null; detail pages retain full denominators."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Seed 25 items with 25 distinct creator hints
    for i in range(1, 26):
        insert_yoink(conn, f"v_{i:02d}", yoinked_at="2026-09-01T12:00:00.000Z", author=f"Creator {i:02d}", channel=f"Channel {i:02d}")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    summary = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert summary["ok"] is True
    assert summary["items"]["total"]["value"] == 25

    pg = summary["pagination"]["creator_hints"]
    assert pg["total_rows"] == 25
    assert pg["returned_rows"] == 20
    assert pg["omitted_rows"] == 5
    assert pg["other_count"] == 5

    # Top-20 sum + other_count == total (20 + 5 == 25)
    top20_sum = sum(r["count"]["value"] for r in summary["items"]["by_creator_hint"])
    assert top20_sum + pg["other_count"] == summary["items"]["total"]["value"]

    # Detail page retains full summary denominators
    rev = summary["report_revision"]
    detail_req = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "detail": "creator_hints",
        "expected_revision": rev,
        "offset": 20,
        "limit": 20,
    }
    detail_res = library_analysis.get_library_activity(detail_req, db=conn, clock=fixed_as_of)
    assert detail_res["ok"] is True
    assert len(detail_res["rows"]) == 5
    # Denominator in share ratios of detail page rows remains 25
    for r in detail_res["rows"]:
        assert r["share"]["denominator"] == 25


def test_activity_journal_shapes_and_no_change_receipts(tmp_dir):
    """Test delta shapes (empty arrays, policy-only, metadata-only, activation-only, receipt gaps, malformed JSON)."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_shape_1", yoinked_at="2026-09-01T10:00:00.000Z")
    insert_shelf(conn, "sh_1")
    insert_shelf_version(conn, "v1")
    insert_shelf_version(conn, "v2")
    conn.commit()

    # 1. Op 1: policy-only change
    f_pol = {"items": {}, "policies": {"v_shape_1": policy_row("v_shape_1", 1)}}
    i_pol = {"items": {}, "policies": {"v_shape_1": None}}
    insert_apply(conn, "app_pol", 1, 0, 1, created_at="2026-09-01T10:00:00.000Z", forward_delta=f_pol, inverse_delta=i_pol)

    # 2. Receipt sequence 2 is a NO-CHANGE receipt (no apply row)
    nc_hash = hashlib.sha256(b"no_change_op").hexdigest()
    conn.execute(
        "INSERT INTO library_operation_receipts (operation_key, request_hash, operation_sequence, authoritative_record_hash, receipt_json) "
        "VALUES ('no_change_op', ?, 2, ?, '{\"status\":\"no_change\"}')",
        (nc_hash, nc_hash),
    )

    # 3. Op 2: metadata-only change (evidence_json / confidence changed, shelf set unchanged)
    f_meta = {"items": {"v_shape_1": [membership_row("v_shape_1", "sh_1", source="agent", confidence=0.9, evidence_json='{"score":0.9}')]}, "policies": {}}
    i_meta = {"items": {"v_shape_1": [membership_row("v_shape_1", "sh_1", source="agent", confidence=0.5, evidence_json='{"score":0.5}')]}, "policies": {}}
    insert_apply(conn, "app_meta", 3, 1, 2, created_at="2026-09-01T12:00:00.000Z", forward_delta=f_meta, inverse_delta=i_meta)

    # 4. Op 3: activation-only delta (active_version_id changes from v1 to v2)
    f_act = {"items": {}, "policies": {}, "active_version_id": "v2"}
    i_act = {"items": {}, "policies": {}, "active_version_id": "v1"}
    insert_apply(conn, "app_act", 4, 2, 3, created_at="2026-09-01T13:00:00.000Z", forward_delta=f_act, inverse_delta=i_act)
    conn.commit()

    req = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    sa = res["shelf_activity"]
    assert sa["policy_change_events"]["value"] == 1
    assert sa["metadata_only_item_events"]["value"] == 1
    assert sa["activation_events"]["value"] == 1
    assert sa["membership_mutations"]["value"] == 0

    # Malformed JSON shape in forward_delta refuses invalid_source_data
    conn.execute("UPDATE library_applies SET forward_json='{\"bad_shape\": 1}' WHERE apply_id='app_act'")
    conn.commit()
    res_bad = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res_bad["ok"] is False
    assert res_bad["error"]["code"] == "invalid_source_data"


def test_activity_primary_only_and_initial_filing(tmp_dir):
    """Primary-only change adds no membership mutations but counts in churn; first filing counted in initial_filing."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_prim", yoinked_at="2026-09-01T10:00:00.000Z")
    insert_yoink(conn, "v_init", yoinked_at="2026-09-01T10:00:00.000Z")
    insert_shelf(conn, "sh_1")
    insert_shelf(conn, "sh_2")
    insert_shelf_version(conn, "v1")

    # Op 1: Prior baseline setup (files v_prim into sh_1 and sh_2, primary=sh_1)
    prim_base = [
        membership_row("v_prim", "sh_1", is_primary=1, source_revision="r1", assigned_at="2026-09-01T10:00:00.000Z"),
        membership_row("v_prim", "sh_2", is_primary=0, source_revision="r1", assigned_at="2026-09-01T10:00:00.000Z"),
    ]
    f_op1 = {"items": {"v_prim": prim_base}, "policies": {}}
    i_op1 = {"items": {"v_prim": []}, "policies": {}}
    insert_apply(conn, "app_base", 1, 0, 1, created_at="2026-09-01T10:00:00.000Z", forward_delta=f_op1, inverse_delta=i_op1)

    # Op 2 (in interval): Primary-only change for v_prim (primary becomes sh_2, no add/remove)
    prim_swapped = [
        membership_row("v_prim", "sh_1", is_primary=0, source_revision="r1", assigned_at="2026-09-05T12:00:00.000Z"),
        membership_row("v_prim", "sh_2", is_primary=1, source_revision="r1", assigned_at="2026-09-05T12:00:00.000Z"),
    ]
    f_op2 = {"items": {"v_prim": prim_swapped}, "policies": {}}
    i_op2 = {"items": {"v_prim": prim_base}, "policies": {}}
    insert_apply(conn, "app_prim", 2, 1, 2, created_at="2026-09-05T12:00:00.000Z", forward_delta=f_op2, inverse_delta=i_op2)

    # Op 3 (in interval): Initial filing for v_init (first time assigned)
    init_rows = [membership_row("v_init", "sh_1", source_revision="r1", assigned_at="2026-09-05T14:00:00.000Z")]
    f_op3 = {"items": {"v_init": init_rows}, "policies": {}}
    i_op3 = {"items": {"v_init": []}, "policies": {}}
    insert_apply(conn, "app_init", 3, 2, 3, created_at="2026-09-05T14:00:00.000Z", forward_delta=f_op3, inverse_delta=i_op3)

    # Set item_shelves to match ending projection
    set_item_shelves(conn, "v_prim", prim_swapped)
    set_item_shelves(conn, "v_init", init_rows)
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    sa = res["shelf_activity"]
    assert sa["primary_change_events"]["value"] == 1
    assert sa["initial_filing_items"]["value"] == 1
    # v_prim changed, so churn numerator is 1, denominator is 1 (v_prim was assigned at baseline, v_init was not)
    assert sa["churn"]["numerator"] == 1
    assert sa["churn"]["denominator"] == 1
    assert sa["churn"]["percent"] == 100.0


def test_activity_history_chain_and_clock_regression(tmp_dir):
    """Test that missing receipt, revision gap, mismatched inverse, clock regression refuse baseline proof."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_regress", yoinked_at="2026-09-01T10:00:00.000Z")
    insert_shelf(conn, "sh_1")
    insert_shelf_version(conn, "v1")

    # Op 1 at 12:00
    insert_apply(conn, "app_1", 1, 0, 1, created_at="2026-09-01T12:00:00.000Z")
    # Op 2 at 10:00 (CLOCK REGRESSION: earlier than Op 1!)
    insert_apply(conn, "app_2", 2, 1, 2, created_at="2026-09-01T10:00:00.000Z")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    # Baseline proof failed due to clock regression -> churn value is null, reason baseline_unavailable
    assert res["shelf_activity"]["churn"]["value"] is None
    assert res["shelf_activity"]["churn"]["reason"] == "baseline_unavailable"
    # Valid retained event counts still reported
    assert res["shelf_activity"]["applied_operations"]["value"] == 2


def test_activity_deleted_journal_survivors_and_restore(tmp_dir):
    """Journal events survive deletion; survivor baseline denominator excludes deleted item and recomputes."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_live", yoinked_at="2026-09-01T10:00:00.000Z")
    insert_yoink(conn, "v_deleted", yoinked_at="2026-09-01T10:00:00.000Z", deleted_at="2026-09-05T12:00:00.000Z")
    insert_shelf(conn, "sh_1")
    insert_shelf_version(conn, "v1")

    # Op 1: files both v_live and v_deleted
    live_rows = [membership_row("v_live", "sh_1", source_revision="r1")]
    f_op1 = {
        "items": {
            "v_live": live_rows,
            "v_deleted": [membership_row("v_deleted", "sh_1", source_revision="r1")],
        },
        "policies": {},
    }
    i_op1 = {"items": {"v_live": [], "v_deleted": []}, "policies": {}}
    insert_apply(conn, "app_both", 1, 0, 1, created_at="2026-09-01T10:00:00.000Z", forward_delta=f_op1, inverse_delta=i_op1)

    # Current item_shelves has v_live only (since v_deleted is tombstoned)
    set_item_shelves(conn, "v_live", live_rows)
    conn.commit()

    req = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    # Journal operation is counted
    assert res["shelf_activity"]["applied_operations"]["value"] == 1
    # Survivor denominator excludes v_deleted -> only v_live is in survivor baseline
    assert res["shelf_activity"]["current_assigned_items"]["value"] == 1


def test_activity_source_observation_windows(tmp_dir):
    """Enrollment-only source has no observation window; archived source with activity remains; tombstones preserve span."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # 1. Enrollment-only source (no observations)
    insert_subscription(conn, "src_enroll_only", display_name="Enroll Only")

    # 2. Archived source with activity in interval
    insert_subscription(conn, "src_archived", display_name="Archived Active", archived=1)
    insert_yoink(conn, "v_arch", yoinked_at="2026-09-05T12:00:00.000Z")
    insert_source_item(
        conn,
        "src_archived",
        "entry_arch",
        video_id="v_arch",
        first_seen_ms=stamp("2026-09-05T10:00:00Z"),
        last_seen_ms=stamp("2026-09-05T14:00:00Z"),
        state="deleted",  # tombstone preserves span
    )
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    # Archived source appears because it has qualifying activity
    arch_row = next((s for s in res["sources"]["details"] if s["source_id"] == "src_archived"), None)
    assert arch_row is not None
    assert arch_row["observation_window"]["first_observed_at"] is not None
    # Enrollment only source has no activity in interval, so not in active_sources
    enroll_row = next((s for s in res["sources"]["details"] if s["source_id"] == "src_enroll_only"), None)
    assert enroll_row is None


def test_activity_source_overlap_and_legacy_link(tmp_dir):
    """Item linked to 2 sources contributes 1 union item and 1 per source; legacy podcast feed deduplicates."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_overlap", yoinked_at="2026-09-05T12:00:00.000Z")
    insert_subscription(conn, "src_a", display_name="Source A")
    insert_subscription(conn, "src_b", display_name="Source B")
    insert_source_item(conn, "src_a", "e_a", video_id="v_overlap", first_seen_ms=stamp("2026-09-05T10:00:00Z"))
    insert_source_item(conn, "src_b", "e_b", video_id="v_overlap", first_seen_ms=stamp("2026-09-05T10:00:00Z"))
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    srcs = res["sources"]
    assert srcs["linked_capture_union_count"]["value"] == 1
    assert srcs["multiply_linked_capture_count"]["value"] == 1
    # Each source has 1 capture
    s_a = next(s for s in srcs["details"] if s["source_id"] == "src_a")
    s_b = next(s for s in srcs["details"] if s["source_id"] == "src_b")
    assert s_a["captures_in_interval"]["value"] == 1
    assert s_b["captures_in_interval"]["value"] == 1


def test_activity_corrections_outside_interval(tmp_dir):
    """Mutations outside the interval (or PRAGMA data_version writes) invalidate old report revision bindings."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_target", yoinked_at="2026-09-05T12:00:00.000Z", author="Original Author")
    insert_yoink(conn, "v_outside", yoinked_at="2024-01-01T12:00:00.000Z", author="Outside Author")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res1 = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res1["ok"] is True
    rev1 = res1["report_revision"]

    # Modify outside item
    conn.execute("UPDATE yoinks SET author='Corrected Outside Author' WHERE video_id='v_outside'")
    conn.commit()

    res2 = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res2["ok"] is True
    rev2 = res2["report_revision"]
    assert rev2 != rev1


def test_activity_provenance_for_every_metric(tmp_dir):
    """Every metric resolves to query_id, clock, interval, revisions, and exact paged evidence."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_prov", yoinked_at="2026-09-05T12:00:00.000Z", source_type="video", author="Prov Author")
    insert_shelf(conn, "sh_prov")
    insert_shelf_version(conn, "v1")
    f_op = {"items": {"v_prov": [membership_row("v_prov", "sh_prov", assigned_at="2026-09-05T12:00:00.000Z")]}, "policies": {}}
    i_op = {"items": {"v_prov": []}, "policies": {}}
    insert_apply(conn, "app_prov", 1, 0, 1, created_at="2026-09-05T12:00:00.000Z", forward_delta=f_op, inverse_delta=i_op)
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    summary = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert summary["ok"] is True
    scopes = summary["provenance"]["scopes"]

    # Check metric structure
    total_m = summary["items"]["total"]
    assert total_m["metric_id"] == "items.total"
    assert total_m["unit"] == "saved_items"
    assert total_m["scope_ref"] in scopes
    assert scopes[total_m["scope_ref"]]["query_id"] == "Q1"

    # Fetch evidence for items.total
    ev_req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "detail": "evidence",
        "metric_id": "items.total",
        "expected_revision": summary["report_revision"],
    }
    ev_res = library_analysis.get_library_activity(ev_req, db=conn, clock=fixed_as_of)
    assert ev_res["ok"] is True
    assert len(ev_res["rows"]) == 1
    assert ev_res["rows"][0]["row_id"] == "v_prov"
    assert "observation_hash" in ev_res["rows"][0]


def test_activity_registry_stdio_http_parity(tmp_dir):
    """Tool registered in TOOL_REGISTRY, stdio, and HTTP produce identical responses; unknown fields fail before DB."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)
    library_analysis.set_analysis_db(conn)

    insert_yoink(conn, "v_parity", yoinked_at="2026-09-05T12:00:00.000Z")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }

    # 1. TOOL_REGISTRY
    res_reg = uoink_mcp_tools.call_tool("get_library_activity", req)
    assert res_reg["ok"] is True

    # 2. stdio function in uoink_mcp
    res_stdio = uoink_mcp.get_library_activity(
        interval=req["interval"],
        date_basis="capture_time",
    )
    assert res_stdio["ok"] is True

    # Verify semantic equivalence
    assert res_reg["report_revision"] == res_stdio["report_revision"]
    assert res_reg["items"]["total"]["value"] == res_stdio["items"]["total"]["value"]

    # Unknown field fails validation before read
    bad_req = dict(req)
    bad_req["unauthorized_key"] = "test"
    res_bad = uoink_mcp_tools.call_tool("get_library_activity", bad_req)
    assert res_bad["ok"] is False
    assert res_bad["error"]["code"] == "validation_error"

    library_analysis.set_analysis_db(None)


def test_activity_read_has_no_side_effects(tmp_dir):
    """Querying get_library_activity leaves DB and filesystem completely unmodified; no rows written."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_ro", yoinked_at="2026-09-05T12:00:00.000Z")
    conn.commit()

    # Capture initial page count and schema version
    init_changes = conn.total_changes
    db_file = tmp_dir / "fixture.db"
    init_mtime = db_file.stat().st_mtime_ns

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    assert conn.total_changes == init_changes


def test_activity_wire_budget_and_untrusted_labels(tmp_dir):
    """Worst-case unicode, escaped labels, HTML/script tags stay <= 65536 bytes; truncation is explicit."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Insert items with hostile / unicode / HTML strings
    hostile_author = "<script>alert('xss')</script> &amp; 🚀" * 10
    hostile_title = "Title with <xml>tags</xml> and \"quotes\" and 'apostrophes'" * 5
    for i in range(1, 50):
        insert_yoink(
            conn,
            f"v_hostile_{i:02d}",
            yoinked_at="2026-09-05T12:00:00.000Z",
            author=f"{hostile_author}_{i}",
            title=hostile_title,
        )
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True

    serialized = json.dumps(res, ensure_ascii=False).encode("utf-8")
    assert len(serialized) <= library_analysis.MAX_RESPONSE_BYTES
    # Truncation check
    for hint in res["items"]["by_creator_hint"]:
        assert len(hint["hint"]) <= library_analysis.MAX_LABEL_CODEPOINTS


def test_activity_deadline_and_work_bounds(tmp_dir, monkeypatch):
    """Delayed execution yields deadline_exceeded; over-64-MiB journal yields resource_too_large."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_work", yoinked_at="2026-09-05T12:00:00.000Z")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }

    # 1. Simulate deadline exceeded
    real_monotonic = time.monotonic
    call_count = [0]
    def fake_monotonic():
        call_count[0] += 1
        if call_count[0] > 1:
            return real_monotonic() + 10.0
        return real_monotonic()

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    res_deadline = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    monkeypatch.setattr(time, "monotonic", real_monotonic)

    assert res_deadline["ok"] is False
    assert res_deadline["error"]["code"] == "deadline_exceeded"

    # 2. Over-64-MiB journal:
    huge_json = json.dumps({"items": {"v_work": [{"data": "x" * (35 * 1024 * 1024)}]}})
    insert_apply(conn, "app_huge", 1, 0, 1, forward_delta={"items": {}, "policies": {}}, inverse_delta={"items": {}, "policies": {}})
    conn.execute("UPDATE library_applies SET forward_json=?, inverse_json=? WHERE apply_id='app_huge'", (huge_json, huge_json))
    conn.commit()

    res_huge = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res_huge["ok"] is False
    assert res_huge["error"]["code"] == "resource_too_large"


def test_activity_cost_548_and_10000(tmp_dir):
    """Measure synthetic 548 and 10,000 item libraries; record journal bytes, elapsed time, peak memory, and query plans."""
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # -----------------------------------------------------------------------
    # Part 1: Synthetic 548-Item Library
    # -----------------------------------------------------------------------
    conn_548 = create_fixture_db(tmp_dir, "db_548.db")
    insert_shelf(conn_548, "shelf_alpha")
    insert_shelf(conn_548, "shelf_beta")
    insert_shelf_version(conn_548, "v1")
    insert_subscription(conn_548, "sub_bulk", display_name="Bulk Channel")

    f_items_548: Dict[str, list] = {}
    for i in range(1, 549):
        vid = f"vid_548_{i:04d}"
        insert_yoink(conn_548, vid, yoinked_at="2026-09-01T12:00:00.000Z", author=f"Author {i % 20}", channel="Bulk Channel")
        insert_source_item(conn_548, "sub_bulk", f"entry_{i}", video_id=vid, first_seen_ms=stamp("2026-09-01T10:00:00Z"))
        # 1-3 memberships each
        sh_list = ["shelf_alpha"] if (i % 2 == 0) else ["shelf_alpha", "shelf_beta"]
        f_items_548[vid] = [membership_row(vid, s, is_primary=1 if s == "shelf_alpha" else 0) for s in sh_list]

    insert_apply(
        conn_548,
        "app_full_548",
        1,
        0,
        1,
        created_at="2026-09-01T10:00:00.000Z",
        forward_delta={"items": f_items_548, "policies": {}},
        inverse_delta={"items": {vid: [] for vid in f_items_548}, "policies": {}},
    )
    for vid, rows in f_items_548.items():
        set_item_shelves(conn_548, vid, rows)
    conn_548.commit()

    # Query plans
    qp_q1 = conn_548.execute("EXPLAIN QUERY PLAN SELECT video_id, source_type, author, channel, platform, yoinked_at, deleted_at FROM yoinks ORDER BY video_id ASC").fetchall()
    qp_q3 = conn_548.execute("EXPLAIN QUERY PLAN SELECT apply_id, operation_key, kind, before_revision, after_revision, operation_sequence, authoritative_record_hash, forward_json, inverse_json, undo_of, created_at FROM library_applies ORDER BY operation_sequence ASC").fetchall()

    req_548 = {
        "interval": {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }

    tracemalloc.start()
    t0 = time.perf_counter()
    res_548 = library_analysis.get_library_activity(req_548, db=conn_548, clock=fixed_as_of)
    t1 = time.perf_counter()
    ser_548 = json.dumps(res_548, ensure_ascii=False).encode("utf-8")
    t2 = time.perf_counter()
    _, peak_548 = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert res_548["ok"] is True
    assert res_548["items"]["total"]["value"] == 548
    assert len(ser_548) <= library_analysis.MAX_RESPONSE_BYTES
    construction_time_548 = (t1 - t0)
    serialization_time_548 = (t2 - t1)
    assert construction_time_548 < library_analysis.SERVICE_DEADLINE_SEC

    # -----------------------------------------------------------------------
    # Part 2: Synthetic 10,000-Item Library
    # -----------------------------------------------------------------------
    conn_10k = create_fixture_db(tmp_dir, "db_10k.db")
    insert_shelf(conn_10k, "shelf_main")
    insert_shelf_version(conn_10k, "v1")
    insert_subscription(conn_10k, "sub_10k", display_name="Massive 10k Channel")

    conn_10k.commit()
    f_items_10k: Dict[str, list] = {}
    with conn_10k:
        for i in range(1, 10001):
            vid = f"vid_10k_{i:05d}"
            insert_yoink(conn_10k, vid, yoinked_at="2026-09-01T12:00:00.000Z", author=f"Author {i % 50}", channel="Massive 10k Channel")
            insert_source_item(conn_10k, "sub_10k", f"e_10k_{i}", video_id=vid, first_seen_ms=stamp("2026-09-01T10:00:00Z"))
            f_items_10k[vid] = [membership_row(vid, "shelf_main")]
            conn_10k.execute(
                "INSERT INTO item_shelves (video_id, shelf_id, version_id, source_revision, source, locked, is_primary, confidence, evidence_json, assigned_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(f_items_10k[vid][0][col] for col in MEMBERSHIP_COLUMNS),
            )

    insert_apply(
        conn_10k,
        "app_full_10k",
        1,
        0,
        1,
        created_at="2026-09-01T10:00:00.000Z",
        forward_delta={"items": f_items_10k, "policies": {}},
        inverse_delta={"items": {vid: [] for vid in f_items_10k}, "policies": {}},
    )
    conn_10k.commit()

    c_journal = conn_10k.execute("SELECT SUM(LENGTH(forward_json) + LENGTH(inverse_json)) FROM library_applies").fetchone()
    journal_bytes_10k = c_journal[0] if c_journal else 0

    t0_10k = time.perf_counter()
    res_10k = library_analysis.get_library_activity(req_548, db=conn_10k, clock=fixed_as_of)
    t1_10k = time.perf_counter()
    ser_10k = json.dumps(res_10k, ensure_ascii=False).encode("utf-8")
    t2_10k = time.perf_counter()

    assert res_10k["ok"] is True
    assert res_10k["items"]["total"]["value"] == 10000
    assert len(ser_10k) <= library_analysis.MAX_RESPONSE_BYTES
    construction_time_10k = (t1_10k - t0_10k)
    serialization_time_10k = (t2_10k - t1_10k)
    assert construction_time_10k < library_analysis.SERVICE_DEADLINE_SEC

    # Measure peak memory under tracemalloc with relaxed deadline for debug tracing
    old_deadline = library_analysis.SERVICE_DEADLINE_SEC
    try:
        library_analysis.SERVICE_DEADLINE_SEC = 30.0
        tracemalloc.start()
        _ = library_analysis.get_library_activity(req_548, db=conn_10k, clock=fixed_as_of)
        _, peak_10k = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        library_analysis.SERVICE_DEADLINE_SEC = old_deadline

    # Print measurement stats to test output
    print(f"\n[SYNTHETIC MEASUREMENT 548-ITEM]: Construction={construction_time_548*1000:.2f}ms, Ser={serialization_time_548*1000:.2f}ms, PeakMem={peak_548/1024:.1f}KiB, WireBytes={len(ser_548)}")
    print(f"[SYNTHETIC MEASUREMENT 10K-ITEM]: Construction={construction_time_10k*1000:.2f}ms, Ser={serialization_time_10k*1000:.2f}ms, PeakMem={peak_10k/1024:.1f}KiB, WireBytes={len(ser_10k)}, JournalBytes={journal_bytes_10k}")
    print(f"[SYNTHETIC QUERY PLAN Q1]: {[tuple(r) for r in qp_q1]}")
    print(f"[SYNTHETIC QUERY PLAN Q3]: {[tuple(r) for r in qp_q3]}")

    # -----------------------------------------------------------------------
    # Part 3: Proved Baseline Replay (Interval covering first apply)
    # -----------------------------------------------------------------------
    req_replay = {
        "interval": {"start": "2026-09-01T10:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    t0_rep = time.perf_counter()
    res_replay = library_analysis.get_library_activity(req_replay, db=conn_548, clock=fixed_as_of)
    t1_rep = time.perf_counter()
    assert res_replay["ok"] is True
    assert res_replay["coverage"]["cov_shelf_activity"]["coverage_status"] == "journal_complete"
    assert not res_replay["coverage"]["cov_shelf_activity"]["reasons"]
    time_replay = (t1_rep - t0_rep)

    # -----------------------------------------------------------------------
    # Part 4: Error and Refusal Paths (70 MiB journal and deadline expiry)
    # -----------------------------------------------------------------------
    conn_refusal = create_fixture_db(tmp_dir, "db_refusal.db")
    insert_yoink(conn_refusal, "v_refuse", yoinked_at="2026-09-01T12:00:00.000Z")
    huge_payload = json.dumps({"items": {"v_refuse": [{"data": "x" * (35 * 1024 * 1024)}]}})
    insert_apply(conn_refusal, "app_huge_refusal", 1, 0, 1, forward_delta={"items": {}, "policies": {}}, inverse_delta={"items": {}, "policies": {}})
    conn_refusal.execute("UPDATE library_applies SET forward_json=?, inverse_json=? WHERE apply_id='app_huge_refusal'", (huge_payload, huge_payload))
    conn_refusal.commit()

    t0_refuse = time.perf_counter()
    res_refusal = library_analysis.get_library_activity(req_548, db=conn_refusal, clock=fixed_as_of)
    t1_refuse = time.perf_counter()
    assert res_refusal["ok"] is False
    assert res_refusal["error"]["code"] == "resource_too_large"
    time_refusal_70mib = (t1_refuse - t0_refuse)

    # Deadline expiry refusal
    old_monotonic = time.monotonic
    call_count = [0]
    def fake_monotonic():
        call_count[0] += 1
        if call_count[0] > 1:
            return old_monotonic() + 10.0
        return old_monotonic()
    try:
        time.monotonic = fake_monotonic
        t0_dl = time.perf_counter()
        res_dl = library_analysis.get_library_activity(req_548, db=conn_548, clock=fixed_as_of)
        t1_dl = time.perf_counter()
        assert res_dl["ok"] is False
        assert res_dl["error"]["code"] == "deadline_exceeded"
        time_refusal_deadline = (t1_dl - t0_dl)
    finally:
        time.monotonic = old_monotonic

    # -----------------------------------------------------------------------
    # Part 5: Actual Transport Serialization (MCP Stdio Envelope)
    # -----------------------------------------------------------------------
    t0_trans = time.perf_counter()
    transport_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": (
                        library_resources.DOCUMENT_PREFACE
                        + library_resources.DOCUMENT_FENCE_OPEN
                        + json.dumps(res_548, ensure_ascii=False)
                        + library_resources.DOCUMENT_FENCE_CLOSE
                    ),
                }
            ],
            "isError": False,
        },
    }
    ser_transport = json.dumps(transport_payload, ensure_ascii=False).encode("utf-8")
    t1_trans = time.perf_counter()
    time_transport_ser = (t1_trans - t0_trans)
    bytes_transport = len(ser_transport)

    # -----------------------------------------------------------------------
    # Part 6: Three Memberships Per Item (548 items x 3 = 1,644 memberships)
    # -----------------------------------------------------------------------
    conn_3mem = create_fixture_db(tmp_dir, "db_3mem.db")
    insert_shelf(conn_3mem, "shelf_a")
    insert_shelf(conn_3mem, "shelf_b")
    insert_shelf(conn_3mem, "shelf_c")
    insert_shelf_version(conn_3mem, "v1")
    insert_subscription(conn_3mem, "sub_3mem", display_name="3Mem Channel")
    f_items_3mem: Dict[str, list] = {}
    for i in range(1, 549):
        vid = f"vid_3mem_{i:04d}"
        insert_yoink(conn_3mem, vid, yoinked_at="2026-09-01T12:00:00.000Z", author=f"Author {i % 20}", channel="3Mem Channel")
        insert_source_item(conn_3mem, "sub_3mem", f"entry_3_{i}", video_id=vid, first_seen_ms=stamp("2026-09-01T10:00:00Z"))
        f_items_3mem[vid] = [
            membership_row(vid, "shelf_a", is_primary=1),
            membership_row(vid, "shelf_b", is_primary=0),
            membership_row(vid, "shelf_c", is_primary=0),
        ]
        set_item_shelves(conn_3mem, vid, f_items_3mem[vid])
    insert_apply(
        conn_3mem,
        "app_full_3mem",
        1,
        0,
        1,
        created_at="2026-09-01T10:00:00.000Z",
        forward_delta={"items": f_items_3mem, "policies": {}},
        inverse_delta={"items": {vid: [] for vid in f_items_3mem}, "policies": {}},
    )
    conn_3mem.commit()
    t0_3mem = time.perf_counter()
    res_3mem = library_analysis.get_library_activity(req_548, db=conn_3mem, clock=fixed_as_of)
    t1_3mem = time.perf_counter()
    assert res_3mem["ok"] is True
    time_3mem = (t1_3mem - t0_3mem)

    # -----------------------------------------------------------------------
    # Part 7: Multi-Operation Journal (10 applied operations)
    # -----------------------------------------------------------------------
    conn_multi = create_fixture_db(tmp_dir, "db_multi.db")
    insert_shelf(conn_multi, "shelf_alpha")
    insert_shelf(conn_multi, "shelf_beta")
    insert_shelf_version(conn_multi, "v1")
    insert_subscription(conn_multi, "sub_multi", display_name="Multi Channel")
    for i in range(1, 51):
        insert_yoink(conn_multi, f"vid_m_{i:02d}", yoinked_at="2026-09-01T12:00:00.000Z")
    prev_delta: Dict[str, list] = {f"vid_m_{i:02d}": [] for i in range(1, 51)}
    for op_seq in range(1, 11):
        at_iso = f"2026-09-01T{10 + (op_seq - 1) // 6:02d}:{((op_seq - 1) % 6) * 10:02d}:00.000Z"
        sh_curr = "shelf_alpha" if op_seq % 2 == 1 else "shelf_beta"
        # Each inverse is the exact replayed before state: the previous forward rows.
        f_delta = {vid: [membership_row(vid, sh_curr, assigned_at=at_iso)] for vid in prev_delta}
        i_delta = prev_delta
        insert_apply(conn_multi, f"app_m_{op_seq}", op_seq, op_seq - 1, op_seq, created_at=at_iso, forward_delta={"items": f_delta, "policies": {}}, inverse_delta={"items": i_delta, "policies": {}})
        prev_delta = f_delta
    for vid, rows in prev_delta.items():
        set_item_shelves(conn_multi, vid, rows)
    conn_multi.commit()
    t0_multi = time.perf_counter()
    res_multi = library_analysis.get_library_activity(req_replay, db=conn_multi, clock=fixed_as_of)
    t1_multi = time.perf_counter()
    assert res_multi["ok"] is True
    assert res_multi["coverage"]["cov_shelf_activity"]["coverage_status"] == "journal_complete"
    assert not res_multi["coverage"]["cov_shelf_activity"]["reasons"]
    time_multi = (t1_multi - t0_multi)

    # -----------------------------------------------------------------------
    # Part 8: 100k-Observation Case
    # -----------------------------------------------------------------------
    conn_100k = create_fixture_db(tmp_dir, "db_100k.db")
    insert_subscription(conn_100k, "sub_100k", display_name="Massive 100k Source")
    insert_yoink(conn_100k, "vid_obs_1", yoinked_at="2026-09-01T12:00:00.000Z")
    obs_rows = [
        (f"item_obs_{i}", "sub_100k", f"entry_{i}", f"ck_obs_{i}", f"https://example.com/{i}", f"Title {i}", None, 1788264000000, 1788264000000, 1, "{}", "none", "observed", None)
        for i in range(100000)
    ]
    conn_100k.executemany(
        "INSERT INTO source_items (item_id, source_id, entry_id, capture_key, canonical_url, title, published_at_ms, first_seen_ms, last_seen_ms, first_scan_revision, metadata_json, eligibility, state, video_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        obs_rows,
    )
    conn_100k.commit()
    t0_100k = time.perf_counter()
    res_100k = library_analysis.get_library_activity(req_548, db=conn_100k, clock=fixed_as_of)
    t1_100k = time.perf_counter()
    assert res_100k["ok"] is True
    time_100k = (t1_100k - t0_100k)

    print(f"[SYNTHETIC MEASUREMENT REPLAY-548]: Construction={time_replay*1000:.2f}ms, Proved={res_replay['coverage']['cov_shelf_activity']['coverage_status'] == 'journal_complete'}")
    print(f"[SYNTHETIC MEASUREMENT REFUSAL]: 70MiB={time_refusal_70mib*1000:.2f}ms, Deadline={time_refusal_deadline*1000:.2f}ms")
    print(f"[SYNTHETIC MEASUREMENT TRANSPORT-SER]: Time={time_transport_ser*1000:.2f}ms, Bytes={bytes_transport}")
    print(f"[SYNTHETIC MEASUREMENT 3-MEMBERSHIPS]: Construction={time_3mem*1000:.2f}ms, Items=548, Memberships=1644")
    print(f"[SYNTHETIC MEASUREMENT MULTI-OP-JOURNAL]: Construction={time_multi*1000:.2f}ms, Operations=10")
    print(f"[SYNTHETIC MEASUREMENT 100K-OBSERVATIONS]: Construction={time_100k*1000:.2f}ms, Observations=100000")



def test_activity_dashboard_evidence_and_staleness():
    """Verify UI panel in assets/dashboard/index.html enforces UTC labels, unavailable states, keyboard nav, refresh timer."""
    html_path = ROOT_DIR / "assets" / "dashboard" / "index.html"
    assert html_path.exists(), "assets/dashboard/index.html must exist"
    content = html_path.read_text(encoding="utf-8")

    # 1. Panel declaration
    assert 'class="library-activity-panel"' in content
    assert 'id="libraryActivityPanel"' in content
    assert 'aria-label="Library activity"' in content
    assert '<h2>Library activity</h2>' in content or '<h2 class="activity-title"' in content

    # 2. Presets 1, 7, 30 days and custom UTC interval with 'Z'
    assert 'data-preset="1"' in content
    assert 'data-preset="7"' in content
    assert 'data-preset="30"' in content
    assert 'activityApplyCustomBtn' in content
    assert 'activityDateBasis' in content

    # 3. Unavailable state handling
    assert 'Unavailable' in content
    assert 'activityCustomError' in content

    # 4. Keyboard evidence navigation and modal
    assert 'activityEvidenceModal' in content
    assert 'activity-evidence-trigger' in content
    assert 'closeEvidenceBtn' in content

    # 5. Stale detection and new summary trigger
    assert 'stale_report' in content or 'report_revision' in content

    # 6. Visibility change & focus refresh timer (60000ms)
    assert 'startLibraryActivityTimer' in content
    assert 'stopLibraryActivityTimer' in content
    assert 'visibilitychange' in content
    assert '60000' in content

    # 7. No port 5179 references in activity panel or code
    act_idx = content.find('id="libraryActivityPanel"')
    assert act_idx != -1
    assert '5179' not in content[act_idx : act_idx + 8000]
    assert 'fetch("http://127.0.0.1:5179' not in content
    assert 'fetch("http://localhost:5179' not in content


def test_activity_whats_new_semantic_parity(tmp_dir):
    """whats_new_adapter matches direct get_library_activity invocation for same clock and days."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    insert_yoink(conn, "v_wn_1", yoinked_at="2026-09-05T12:00:00.000Z")
    insert_shelf(conn, "sh_wn")
    insert_shelf_version(conn, "v1")
    f_op = {"items": {"v_wn_1": [membership_row("v_wn_1", "sh_wn", assigned_at="2026-09-05T12:00:00.000Z")]}, "policies": {}}
    i_op = {"items": {"v_wn_1": []}, "policies": {}}
    insert_apply(conn, "app_wn", 1, 0, 1, created_at="2026-09-05T12:00:00.000Z", forward_delta=f_op, inverse_delta=i_op)
    conn.commit()

    # Call whats_new_adapter
    res_wn = library_analysis.whats_new_adapter(conn, days=7, as_of=fixed_as_of)
    assert res_wn["ok"] is True

    # Call get_library_activity directly
    dt_end = fixed_as_of
    dt_start = dt_end - datetime.timedelta(days=7)
    req_direct = {
        "interval": {
            "start": library_analysis.format_canonical_utc(dt_start),
            "end": library_analysis.format_canonical_utc(dt_end),
        },
        "date_basis": "capture_time",
    }
    res_direct = library_analysis.get_library_activity(req_direct, db=conn, clock=fixed_as_of)
    assert res_direct["ok"] is True

    assert res_wn["items"]["total"]["value"] == res_direct["items"]["total"]["value"]
    assert res_wn["shelf_activity"]["applied_operations"]["value"] == res_direct["shelf_activity"]["applied_operations"]["value"]
    assert res_wn["report_revision"] == res_direct["report_revision"]

    # Invalid days raises ValueError
    with pytest.raises(ValueError):
        library_analysis.whats_new_adapter(conn, days=0)
    with pytest.raises(ValueError):
        library_analysis.whats_new_adapter(conn, days=31)


def test_activity_part_b_remains_deferred(tmp_dir):
    """Empty or populated claims, many sources and repeated clips cannot enable trends, contradiction output, or models."""
    conn = create_fixture_db(tmp_dir)
    fixed_as_of = datetime.datetime(2026, 9, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Populate claims table (migration 0008)
    conn.execute(
        "INSERT INTO claims (video_id, claim_text, check_worthiness, status, extracted_at) "
        "VALUES ('v1', 'contradiction between v1 and v2', 0.95, 'verified', '2026-09-05T12:00:00Z')"
    )
    insert_yoink(conn, "v1", yoinked_at="2026-09-05T12:00:00.000Z")
    insert_yoink(conn, "v2", yoinked_at="2026-09-05T12:00:00.000Z")
    conn.commit()

    req = {
        "interval": {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-06T00:00:00.000Z"},
        "date_basis": "capture_time",
    }
    res = library_analysis.get_library_activity(req, db=conn, clock=fixed_as_of)
    assert res["ok"] is True
    assert res["analysis_scope"] == "descriptive"
    assert res["trend_eligible"] is False
    assert res["independent_creator_count"] is None
    assert res["independent_creators_minimum_met"] is False
    assert "claims" not in res
    assert "contradictions" not in res


def test_narration_faithfulness_metric():
    """Static labelled examples: compliant Alpha/Beta passes; wrong count, wrong clock, invented topic, unsupported consensus, reversed direction fail."""
    packet = {
        "ok": True,
        "report_revision": "a" * 64,
        "interval": {
            "start": "2026-09-06T00:00:00.000Z",
            "end": "2026-09-06T18:00:00.000Z",
            "date_basis": "capture_time",
        },
        "support_level": "single_source",
        "trend_eligible": False,
        "independent_creators_minimum_met": False,
        "warnings": ["capture_is_not_publication"],
        "items": {
            "total": {"value": 1},
            "by_creator_hint": [{"hint": "Solo Dev", "count": {"value": 1}}],
        },
        "shelf_activity": {
            "applied_operations": {"value": 2},
            "item_change_events": {"value": 2},
            "affected_items": {"value": 1},
            "membership_mutations": {"value": 4},
            "net_membership_changes": {
                "sh_alpha": {"net": 0},
                "sh_beta": {"net": 0},
            },
            "shelves": [
                {"shelf_id": "sh_alpha", "added": 1, "removed": 1, "net": 0},
                {"shelf_id": "sh_beta", "added": 1, "removed": 1, "net": 0},
            ],
            "churn": {"value": 1, "numerator": 1, "denominator": 1, "percent": 100.0},
        },
        "sources": {
            "details": [{"source_id": "src_1", "display_name": "Solo Channel"}],
        },
        "evidence_archive_dates": ["2023-05-10"],
        "known_topics": ["artificial intelligence"],
    }

    # 1. Compliant narration (Case A) -> PASS
    narration_ok = (
        "Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item. "
        "A pin operation initially moved the item from Alpha to Beta, followed by an undo operation that returned it to Alpha. "
        "Net shelf membership across the interval remained unchanged."
    )
    res_ok = library_analysis.evaluate_narration_faithfulness(narration_ok, packet)
    assert res_ok["passed"] is True
    assert res_ok["score"] == 1.0
    assert len(res_ok["failures"]) == 0

    # 2. Wrong count / hallucinated number (Case B) -> FAIL
    narration_bad_count = "On September 6, 2026, Solo Dev published 5 videos."
    res_count = library_analysis.evaluate_narration_faithfulness(narration_bad_count, packet)
    assert res_count["passed"] is False
    assert any("hallucinated_number" in f for f in res_count["failures"])

    # 3. Wrong clock / temporal slippage (Case D) -> FAIL
    narration_bad_clock = "Podcasters published 1 new episode on September 6, 2026."
    res_clock = library_analysis.evaluate_narration_faithfulness(narration_bad_clock, packet)
    assert res_clock["passed"] is False
    assert any("temporal_basis_slippage" in f for f in res_clock["failures"])

    # 4. Invented topic -> FAIL
    narration_bad_topic = "On September 6, 1 item covering quantum thermodynamics was saved."
    res_topic = library_analysis.evaluate_narration_faithfulness(narration_bad_topic, packet)
    assert res_topic["passed"] is False
    assert any("invented_topic" in f for f in res_topic["failures"])

    # 5. Unsupported consensus (Case C) -> FAIL
    narration_bad_consensus = "On September 6, creators broadly aligned around new topics, demonstrating widespread community agreement."
    res_consensus = library_analysis.evaluate_narration_faithfulness(narration_bad_consensus, packet)
    assert res_consensus["passed"] is False
    assert any("unsupported_consensus_claim" in f for f in res_consensus["failures"])

    # 6. Missing denominator / baseline unavailable -> FAIL
    packet_no_baseline = dict(packet)
    packet_no_baseline["shelf_activity"] = dict(packet["shelf_activity"])
    packet_no_baseline["shelf_activity"]["churn"] = {"value": None, "numerator": None, "denominator": None, "reason": "baseline_unavailable"}
    narration_missing_denom = "On September 6, 100% of items experienced churn."
    res_denom = library_analysis.evaluate_narration_faithfulness(narration_missing_denom, packet_no_baseline)
    assert res_denom["passed"] is False
    assert any("missing_denominator" in f for f in res_denom["failures"])

    # 7. Reversed direction -> FAIL
    narration_bad_dir = "On September 6, Alpha shelf grew significantly across the interval."
    res_dir = library_analysis.evaluate_narration_faithfulness(narration_bad_dir, packet)
    assert res_dir["passed"] is False
    assert any("directional_inconsistency" in f for f in res_dir["failures"])

    # 8. Numerically matching but unrelated fact -> FAIL
    narration_unrelated = "There are 2 rabbits in the yard."
    res_unrelated = library_analysis.evaluate_narration_faithfulness(narration_unrelated, packet)
    assert res_unrelated["passed"] is False
    assert any("unrelated_entity_claim" in f for f in res_unrelated["failures"])

    # 9. Explicit archive date from evidence -> PASS
    narration_archive = (
        "Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item originally published on 2023-05-10. "
        "Net shelf membership remained unchanged."
    )
    res_archive = library_analysis.evaluate_narration_faithfulness(narration_archive, packet)
    assert res_archive["passed"] is True

    # 10. Strengthened assertions: non-blacklist unrelated entity -> FAIL
    res_elephants = library_analysis.evaluate_narration_faithfulness("There are 2 elephants in the yard.", packet)
    assert res_elephants["passed"] is False
    assert any("unrelated_entity_claim" in f for f in res_elephants["failures"])

    # 11. Strengthened assertions: wrong population count -> FAIL
    res_wrong_pop = library_analysis.evaluate_narration_faithfulness("2 items were saved.", packet)
    assert res_wrong_pop["passed"] is False
    assert any("hallucinated_number" in f for f in res_wrong_pop["failures"])

    # 12. Strengthened assertions: unlisted topic -> FAIL
    res_pottery = library_analysis.evaluate_narration_faithfulness("1 item about medieval pottery was saved.", packet)
    assert res_pottery["passed"] is False
    assert any("invented_topic" in f for f in res_pottery["failures"])

    # 13. Empty narration has no accuracy score -> FAIL with score=None
    res_empty = library_analysis.evaluate_narration_faithfulness("", packet)
    assert res_empty["passed"] is False
    assert res_empty["score"] is None
    assert "empty_narration" in res_empty["failures"]
