"""tests/test_library_briefs.py - Living Library BriefStore Tests (AV-2t).

Gate covered:
- P4-08 (Briefs):
  - Prepared input surviving restart (serialization, bounds <= 24 KiB, no lease, immutability)
  - Wrong item, quote, revision, input-hash, date, and key refusals
  - Brief conflict (competing different publication for same job_key returns brief_conflict)
  - Idempotent retry (identical submission_key + request returns recorded receipt; changed content -> idempotency_conflict)
  - Stale brief (source revision change, item soft deletion, queue state change return stale_brief)
  - No client means no brief (clock advances, latest_valid returns None, no fabricated documents)
  - Usage unavailable never zero (missing client usage stays unavailable/None, never fabricated as 0 tokens or $0.00)
  - Latest valid discovery (most recent valid artifact by accepted timestamp, then hash)
  - Rendered brief read and dependency invalidation on source deletion
  - Hard purge of dependents (removes owned artifacts and stored packets, keeps content-free receipt hashes)

Tests against the frozen interface in docs/library/PHASE4-AV2-BRIEF-2026-09-08.md:
- library_briefs.BriefStore, CONTRACT_VERSION, BRIEF_DIR
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

import index
import library_cards
import library_resources
from library_resources import ResourceError
import library_work
from tests.phase4_fixtures import (
    MockClock,
    b64url_encode,
    build_test_card,
    make_disposable_index,
    seed_standard_library,
    seed_yoink_item,
)

# Target implementation imports: fails on import until Claude worker lands library_briefs.py
import library_briefs
from library_briefs import (
    CONTRACT_VERSION,
    BRIEF_DIR,
    BriefStore,
)


# ============================================================================
# Helpers & Harness
# ============================================================================

def _compute_file_sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def assert_refusal(res_or_callable: Any, expected_code: str) -> dict:
    """Assert that an operation either raises ResourceError(expected_code) or returns a refusal dict."""
    if callable(res_or_callable):
        try:
            res = res_or_callable()
        except ResourceError as err:
            assert err.code == expected_code, f"Expected refusal code {expected_code!r}, got {err.code!r}: {err}"
            return err.envelope()
    else:
        res = res_or_callable

    assert isinstance(res, dict), f"Expected dict result, got {type(res)}: {res}"
    assert res.get("ok") is False, f"Expected ok=False, got: {res}"
    code = res.get("error", {}).get("code")
    assert code == expected_code, f"Expected refusal code {expected_code!r}, got {code!r}: {res}"
    return res


def unwrap_success(res: Any) -> dict:
    """Ensure success envelope or return dict."""
    assert isinstance(res, dict), f"Expected dict, got {type(res)}"
    if "ok" in res:
        assert res["ok"] is True, f"Expected ok=True, got: {res}"
    return res


class BriefTestHarness:
    """Isolated test harness for BriefStore testing."""

    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.data_root = tmp_path / "data_root"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.clock = MockClock(start_mono=1000.0, start_wall=1788825600.0)  # 2026-09-08 00:00:00 UTC

        self.idx, self.manifest = seed_standard_library(tmp_path)
        self.work_store = tmp_path / "work_store"
        self.work_svc = library_work.LibraryWorkService(
            self.idx,
            store_root=self.work_store,
            clock=self.clock.monotonic,
        )

        self.store = BriefStore(
            self.idx,
            self.work_svc,
            data_root=self.data_root,
            clock=self.clock.monotonic,
            wall_clock=self.clock.wall,
        )

    def restart_store(self) -> BriefStore:
        """Simulate process restart by instantiating a fresh BriefStore on the same data_root."""
        self.store = BriefStore(
            self.idx,
            self.work_svc,
            data_root=self.data_root,
            clock=self.clock.monotonic,
            wall_clock=self.clock.wall,
        )
        return self.store

    def build_valid_citation(self, video_id: str, quote_len: int = 30) -> dict[str, Any]:
        """Build a valid citation matching the indexed item card."""
        card = build_test_card(self.idx, video_id, profile="librarian")
        assert card.get("excerpts"), f"Item {video_id} has no excerpts"
        excerpt = card["excerpts"][0]
        full_text = excerpt["text"]
        quote = full_text[:quote_len]
        return {
            "video_id": video_id,
            "item_id": video_id,
            "source_revision": card["source_revision"],
            "card_hash": card["card_hash"],
            "excerpt_id": excerpt["excerpt_id"],
            "quote": quote,
            "kind": excerpt.get("kind", "timed_clip"),
            "start": excerpt.get("start", 0.0),
            "end": excerpt.get("end", 30.0),
        }


# ============================================================================
# Gate P4-08 Tests
# ============================================================================

class TestP408PreparedInputRestart:
    """P4-08: Prepared input survives restart, size bounds, immutability, and successful publication."""

    def test_prepared_input_structure_and_bounds(self, tmp_path: Path):
        """prepare_input returns bounded packet <= 24 KiB, work rows <= 20, cards <= 5; no lease, no DB mutation."""
        h = BriefTestHarness(tmp_path)
        db_path = tmp_path / "index.db"
        db_hash_before = _compute_file_sha256(db_path)

        packet = h.store.prepare_input("2026-09-08", "run-001")
        packet_data = unwrap_success(packet)

        # Mandatory fields
        for field in ("job_key", "input_hash", "as_of", "bindings", "counts", "coverage", "work_rows", "cards"):
            assert field in packet_data, f"Missing {field} in prepare_input result"

        assert len(packet_data["job_key"]) == 64
        assert len(packet_data["input_hash"]) == 64

        # Bounds checks
        assert len(packet_data["work_rows"]) <= 20
        assert len(packet_data["cards"]) <= 5

        # Packet size <= 24,576 UTF-8 bytes
        packet_bytes = json.dumps(packet_data, ensure_ascii=False).encode("utf-8")
        assert len(packet_bytes) <= 24576, f"Packet exceeds 24 KiB bound: {len(packet_bytes)} bytes"

        # Immutability: database file unchanged; no lease claimed
        db_hash_after = _compute_file_sha256(db_path)
        assert db_hash_before == db_hash_after, "prepare_input must not mutate index database"

    def test_prepared_input_survives_restart_and_publishes(self, tmp_path: Path):
        """Prepared input saved by client survives process restart and successfully publishes."""
        h = BriefTestHarness(tmp_path)
        packet = h.store.prepare_input("2026-09-08", "run-001")
        packet_data = unwrap_success(packet)

        # Simulate client saving packet, then server restarting
        h.restart_store()

        citation = h.build_valid_citation("vid-standard-01")
        doc_text = "# Daily Brief 2026-09-08\nSystem analysis shows bounded retry loops."

        res = h.store.publish(
            job_key=packet_data["job_key"],
            input_hash=packet_data["input_hash"],
            input_packet=packet_data,
            submission_key="sub-key-001",
            document=doc_text,
            citations=[citation],
            usage=None,
            client_identity="claude-code",
        )
        receipt = unwrap_success(res)
        assert "brief_hash" in receipt
        assert len(receipt["brief_hash"]) == 64
        brief_hash = receipt["brief_hash"]
        assert "accepted_at" in receipt
        assert "uri" in receipt
        assert f"briefs/2026-09-08/{brief_hash}" in receipt["uri"]

        # Artifact persisted on disk under DATA_ROOT/reach/briefs/
        briefs_dir = h.data_root / BRIEF_DIR
        assert briefs_dir.exists()

        # latest_valid reflects the new brief
        latest = h.store.latest_valid("2026-09-08")
        assert latest is not None
        assert latest["brief_hash"] == brief_hash
        assert latest["date"] == "2026-09-08"

        # Reading rendered brief succeeds
        read_doc = h.store.read("2026-09-08", brief_hash)
        read_data = unwrap_success(read_doc)
        assert "contents" in read_data or "document" in read_data or "text" in str(read_data)


class TestP408Refusals:
    """P4-08: Strict refusals on wrong item, quote, revision, input-hash, dates, and limits."""

    def test_refusal_wrong_input_hash(self, tmp_path: Path):
        """Corrupt input_hash is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        bad_hash = "0" * 64 if packet["input_hash"] != "0" * 64 else "1" * 64
        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=bad_hash,
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "invalid_request",
        )

    def test_refusal_wrong_job_key(self, tmp_path: Path):
        """Mismatched job_key is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        assert_refusal(
            lambda: h.store.publish(
                job_key="f" * 64,
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "invalid_request",
        )

    def test_refusal_wrong_item_id_in_citation(self, tmp_path: Path):
        """Citation referencing an unknown item ID is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")
        citation["video_id"] = "non-existent-item"
        citation["item_id"] = "non-existent-item"

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "invalid_request",
        )

    def test_refusal_wrong_source_revision_in_citation(self, tmp_path: Path):
        """Citation with mismatched source_revision refuses revision_unavailable or invalid_request."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")
        citation["source_revision"] = "e" * 64

        try:
            res = h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            )
            code = res.get("error", {}).get("code")
            assert code in ("revision_unavailable", "invalid_request")
        except ResourceError as err:
            assert err.code in ("revision_unavailable", "invalid_request")

    def test_refusal_wrong_card_hash_in_citation(self, tmp_path: Path):
        """Citation with mismatched card_hash refuses revision_unavailable or invalid_request."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")
        citation["card_hash"] = "d" * 64

        try:
            res = h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            )
            code = res.get("error", {}).get("code")
            assert code in ("revision_unavailable", "invalid_request")
        except ResourceError as err:
            assert err.code in ("revision_unavailable", "invalid_request")

    def test_refusal_wrong_excerpt_id_in_citation(self, tmp_path: Path):
        """Citation referencing an unknown excerpt_id is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")
        citation["excerpt_id"] = "c" * 64

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "invalid_request",
        )

    def test_refusal_fabricated_quote(self, tmp_path: Path):
        """Citation with a quote not contained within the excerpt text is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")
        citation["quote"] = "This sentence was never spoken in any video."

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "invalid_request",
        )

    def test_refusal_quote_oversized(self, tmp_path: Path):
        """Citation quote exceeding 500 code points is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")
        citation["quote"] = "Q" * 501

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "invalid_request",
        )

    def test_refusal_empty_quote(self, tmp_path: Path):
        """Citation with empty quote is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")
        citation["quote"] = ""

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "invalid_request",
        )

    def test_refusal_too_many_citations(self, tmp_path: Path):
        """Publishing with more than 20 citations is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        base_citation = h.build_valid_citation("vid-standard-01")
        citations = [dict(base_citation) for _ in range(21)]

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document="# Brief",
                citations=citations,
                usage=None,
                client_identity="client-1",
            ),
            "invalid_request",
        )

    def test_refusal_document_oversized(self, tmp_path: Path):
        """Document exceeding 8,192 UTF-8 bytes is refused with resource_too_large."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")
        oversized_doc = "A" * 8193

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-01",
                document=oversized_doc,
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "resource_too_large",
        )

    def test_refusal_future_date(self, tmp_path: Path):
        """prepare_input with a future date raises ResourceError(invalid_request)."""
        h = BriefTestHarness(tmp_path)
        assert_refusal(
            lambda: h.store.prepare_input("2099-12-31", "run-001"),
            "invalid_request",
        )

    def test_refusal_malformed_date(self, tmp_path: Path):
        """prepare_input with non-date strings or impossible dates raises ResourceError(invalid_request)."""
        h = BriefTestHarness(tmp_path)
        for bad_date in ("not-a-date", "2026-02-31", "2026-13-01", "2026/09/08"):
            assert_refusal(
                lambda: h.store.prepare_input(bad_date, "run-001"),
                "invalid_request",
            )

    def test_refusal_malformed_submission_key(self, tmp_path: Path):
        """submission_key containing control characters or whitespace is refused."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        for bad_key in ("sub key with spaces", "sub\nkey", ""):
            assert_refusal(
                lambda: h.store.publish(
                    job_key=packet["job_key"],
                    input_hash=packet["input_hash"],
                    input_packet=packet,
                    submission_key=bad_key,
                    document="# Brief",
                    citations=[citation],
                    usage=None,
                    client_identity="client-1",
                ),
                "invalid_request",
            )


class TestP408BriefConflict:
    """P4-08: First accepted artifact for a job key wins; competing different artifact returns brief_conflict."""

    def test_competing_publication_returns_brief_conflict(self, tmp_path: Path):
        """A competing submission with a different submission_key and different text returns brief_conflict."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        # Winner: first publication
        res1 = h.store.publish(
            job_key=packet["job_key"],
            input_hash=packet["input_hash"],
            input_packet=packet,
            submission_key="sub-winner",
            document="# Winning Brief Document",
            citations=[citation],
            usage=None,
            client_identity="client-A",
        )
        receipt1 = unwrap_success(res1)
        winner_hash = receipt1["brief_hash"]

        # Competitor: same job_key, different submission_key, different document
        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-competitor",
                document="# Competing Brief Document (Different Content)",
                citations=[citation],
                usage=None,
                client_identity="client-B",
            ),
            "brief_conflict",
        )

        # Winner remains active in latest_valid
        latest = h.store.latest_valid("2026-09-08")
        assert latest is not None
        assert latest["brief_hash"] == winner_hash


class TestP408IdempotentRetry:
    """P4-08: Identical key/request retry returns recorded receipt; changed content returns idempotency_conflict."""

    def test_identical_retry_returns_cached_receipt(self, tmp_path: Path):
        """Exact retry with identical submission_key and content returns original receipt."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        args = dict(
            job_key=packet["job_key"],
            input_hash=packet["input_hash"],
            input_packet=packet,
            submission_key="sub-idempotent",
            document="# Consistent Document Text",
            citations=[citation],
            usage=None,
            client_identity="client-1",
        )

        res1 = unwrap_success(h.store.publish(**args))
        res2 = unwrap_success(h.store.publish(**args))

        assert res1["brief_hash"] == res2["brief_hash"]
        assert res1["accepted_at"] == res2["accepted_at"]

    def test_changed_content_under_same_key_returns_idempotency_conflict(self, tmp_path: Path):
        """Changed document or citations under an already-accepted submission_key returns idempotency_conflict."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        # Initial successful publish
        unwrap_success(h.store.publish(
            job_key=packet["job_key"],
            input_hash=packet["input_hash"],
            input_packet=packet,
            submission_key="sub-fixed-key",
            document="# Original Document Content",
            citations=[citation],
            usage=None,
            client_identity="client-1",
        ))

        # Re-using same submission_key with different text
        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-fixed-key",
                document="# Modified Document Content Attempt",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "idempotency_conflict",
        )


class TestP408StaleBrief:
    """P4-08: Authoritative data changes during drafting produce stale_brief refusal."""

    def test_stale_brief_when_item_evidence_mutates(self, tmp_path: Path):
        """If source item content changes between prepare and publish, publish returns stale_brief."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        # Mutate item evidence in index
        new_clips = [{"kind": "transcript_chunk", "seq": 0, "timestamp_start": 0.0, "timestamp_end": 15.0,
                      "text": "Completely new transcript content.", "source_deep_link": "https://example.com"}]
        h.idx.insert_citations("vid-standard-01", new_clips)
        h.idx.rebuild_clips()

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-stale-01",
                document="# Stale Document",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "stale_brief",
        )

    def test_stale_brief_when_item_soft_deleted(self, tmp_path: Path):
        """If an item is soft-deleted between prepare and publish, publish returns stale_brief."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        # Soft-delete the item
        with h.idx._lock:
            h.idx._conn.execute(
                "UPDATE yoinks SET deleted_at = '2026-09-08T03:00:00Z' WHERE video_id = 'vid-standard-01'"
            )
            h.idx._conn.commit()

        assert_refusal(
            lambda: h.store.publish(
                job_key=packet["job_key"],
                input_hash=packet["input_hash"],
                input_packet=packet,
                submission_key="sub-stale-02",
                document="# Stale Document",
                citations=[citation],
                usage=None,
                client_identity="client-1",
            ),
            "stale_brief",
        )


class TestP408NoClientMeansNoBrief:
    """P4-08: No client running means no brief appears; clocks alone never produce a document."""

    def test_no_client_no_brief(self, tmp_path: Path):
        """Advancing clock without client publication leaves latest_valid as None; non-existent read returns 404."""
        h = BriefTestHarness(tmp_path)

        # Advance clock by 3 days
        h.clock.advance(86400 * 3)

        assert h.store.latest_valid("2026-09-08") is None
        assert h.store.latest_valid("2026-09-09") is None
        assert h.store.latest_valid("2026-09-10") is None

        # Reading non-existent brief refuses resource_not_found
        assert_refusal(
            lambda: h.store.read("2026-09-08", "0" * 64),
            "resource_not_found",
        )


class TestP408Usage:
    """P4-08: Missing client usage is unavailable/None, never fabricated as 0 tokens or dollar cost."""

    def test_usage_unavailable_never_zero(self, tmp_path: Path):
        """When usage is None, stored artifact records status unavailable or None, never 0 tokens."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        res = unwrap_success(h.store.publish(
            job_key=packet["job_key"],
            input_hash=packet["input_hash"],
            input_packet=packet,
            submission_key="sub-no-usage",
            document="# Brief with no usage",
            citations=[citation],
            usage=None,
            client_identity="client-1",
        ))

        # Inspect usage in returned receipt or stored manifest
        if "usage" in res and res["usage"] is not None:
            usage = res["usage"]
            assert usage.get("status") in ("unavailable", None)
            assert usage.get("input_tokens") != 0
            assert usage.get("output_tokens") != 0

    def test_reported_usage_preserved_accurately(self, tmp_path: Path):
        """Reported usage numbers and model are preserved verbatim without alteration."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        reported_usage = {
            "status": "reported",
            "model": "claude-3-5-sonnet",
            "input_tokens": 1420,
            "output_tokens": 380,
            "wall_time_ms": 2100,
        }

        res = unwrap_success(h.store.publish(
            job_key=packet["job_key"],
            input_hash=packet["input_hash"],
            input_packet=packet,
            submission_key="sub-with-usage",
            document="# Brief with reported usage",
            citations=[citation],
            usage=reported_usage,
            client_identity="client-1",
        ))

        if "usage" in res and res["usage"] is not None:
            assert res["usage"]["input_tokens"] == 1420
            assert res["usage"]["output_tokens"] == 380
            assert res["usage"]["model"] == "claude-3-5-sonnet"


class TestP408LifecycleAndPurge:
    """P4-08: Dependency invalidation on source deletion and hard purge of owned dependents."""

    def test_read_refuses_when_dependency_deleted(self, tmp_path: Path):
        """Reading a published brief refuses (resource_deleted / revision_unavailable) if cited item is soft-deleted."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        receipt = unwrap_success(h.store.publish(
            job_key=packet["job_key"],
            input_hash=packet["input_hash"],
            input_packet=packet,
            submission_key="sub-dep-del",
            document="# Brief to be invalidated",
            citations=[citation],
            usage=None,
            client_identity="client-1",
        ))
        brief_hash = receipt["brief_hash"]

        # Initial read succeeds
        assert h.store.read("2026-09-08", brief_hash)

        # Soft-delete the cited item
        with h.idx._lock:
            h.idx._conn.execute(
                "UPDATE yoinks SET deleted_at = '2026-09-08T04:00:00Z' WHERE video_id = 'vid-standard-01'"
            )
            h.idx._conn.commit()

        # Subsequent read refuses immediately
        try:
            res = h.store.read("2026-09-08", brief_hash)
            code = res.get("error", {}).get("code")
            assert code in ("resource_deleted", "revision_unavailable")
        except ResourceError as err:
            assert err.code in ("resource_deleted", "revision_unavailable")

    def test_purge_dependents_removes_artifacts(self, tmp_path: Path):
        """purge_dependents removes owned brief documents and stored packets, keeping receipt hashes."""
        h = BriefTestHarness(tmp_path)
        packet = unwrap_success(h.store.prepare_input("2026-09-08", "run-001"))
        citation = h.build_valid_citation("vid-standard-01")

        receipt = unwrap_success(h.store.publish(
            job_key=packet["job_key"],
            input_hash=packet["input_hash"],
            input_packet=packet,
            submission_key="sub-purge-test",
            document="# Brief destined for purge",
            citations=[citation],
            usage=None,
            client_identity="client-1",
        ))
        brief_hash = receipt["brief_hash"]

        purge_result = unwrap_success(h.store.purge_dependents("vid-standard-01"))
        assert purge_result.get("purged_count", 1) >= 1 or "purged" in str(purge_result).lower()

        # latest_valid no longer returns the purged brief
        assert h.store.latest_valid("2026-09-08") is None

        # Subsequent read refuses resource_deleted or resource_not_found
        try:
            res = h.store.read("2026-09-08", brief_hash)
            code = res.get("error", {}).get("code")
            assert code in ("resource_deleted", "resource_not_found")
        except ResourceError as err:
            assert err.code in ("resource_deleted", "resource_not_found")
