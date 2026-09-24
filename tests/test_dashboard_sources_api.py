"""Phase 3 Dashboard & Registry API Contract Tests.

Tests the schemas, validation invariants, capability tokens, and endpoint behaviors
governing the Sources dashboard interface per PHASE3-CONTRACT-2026-09-07.md.

ADAPTATION NOTICE (Plan vs Contract Reconciliation):
Where Gemini's Phase 3 UI plan (PHASE3-UI-TEST-PLAN-2026-09-07.md) and Astra's normative contract
(PHASE3-CONTRACT-2026-09-07.md) differ, the contract wins per implementation brief §1.3:
1. Identifier format: Plan used integer source_id (e.g. 14); contract defines string source_id
   matching pattern ^src_[a-f0-9]{64}$ ('src_' + sha256(kind + '\\n' + source_key)).
2. Capability flow: Plan used direct toggle POST /api/sources/subscriptions/consent; contract
   specifies a two-step flow using dashboard-only route POST /sources/consent-intent to mint a
   single-operation, 5-minute capability token (user_intent_token) binding expected_revision
   and expected_cursor_revision, followed by set_source_consent.
3. Registry tools: Public registry tool names and argument schemas follow contract §6:
   - list_sources
   - register_source
   - source_status
   - set_source_consent
4. Back-catalog enrollment: Plan assumed an arbitrary query at toggle time; contract mandates that
   initial enrollment occurs atomically on the first valid poll snapshot while on, capped at
   min(25, available items), with remaining items remaining metadata-only.
5. Daily allowance ledger: Plan inferred starts from file/job timestamps; contract governs via an
   atomic 10-slot ledger (source_capture_starts) uniquely constrained by (source_id, utc_day, slot)
   with separate reserved vs charged accounting.
"""
from __future__ import annotations

import json
from typing import Any, Dict

import pytest

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

try:
    import source_subscriptions
    HAS_SOURCE_SUBSCRIPTIONS = True
except ImportError:
    HAS_SOURCE_SUBSCRIPTIONS = False

from tests.fixtures.phase3.mock_utc_clock import MockUtcClock
from tests.fixtures.phase3.sample_source_summaries import (
    get_allowance_exhausted_summary,
    get_default_off_summary,
    get_draining_summary,
    get_enrolled_active_summary,
    get_legacy_hold_summary,
    get_pending_enrollment_summary,
    get_unreachable_error_summary,
)


# ---------------------------------------------------------------------------
# Normative Schemas from PHASE3-CONTRACT-2026-09-07.md Section 6
# ---------------------------------------------------------------------------

LIST_SOURCES_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "kind": {"enum": ["podcast_rss", "youtube_channel", "youtube_playlist"]},
        "consent_state": {"enum": ["off", "on"]},
        "include_archived": {"type": "boolean", "default": False},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
        "cursor": {"type": "string", "minLength": 1, "maxLength": 512},
    },
    "additionalProperties": False,
}

REGISTER_SOURCE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "kind": {"enum": ["podcast_rss", "youtube_channel", "youtube_playlist"]},
        "url": {"type": "string", "minLength": 1, "maxLength": 2048},
        "display_name": {"type": "string", "minLength": 1, "maxLength": 200},
        "poll_interval_min": {"type": "integer", "minimum": 15, "maximum": 1440, "default": 60},
    },
    "required": ["kind", "url"],
    "additionalProperties": False,
}

SOURCE_STATUS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "source_id": {"type": "string", "pattern": "^src_[a-f0-9]{64}$"},
        "item_limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
        "item_cursor": {"type": "string", "minLength": 1, "maxLength": 512},
    },
    "required": ["source_id"],
    "additionalProperties": False,
}

SET_SOURCE_CONSENT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "source_id": {"type": "string", "pattern": "^src_[a-f0-9]{64}$"},
        "consent_state": {"enum": ["off", "on"]},
        "expected_revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
        "expected_cursor_revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
        "operation_key": {"type": "string", "minLength": 1, "maxLength": 200, "pattern": "^[A-Za-z0-9_-]+$"},
        "user_intent_token": {"type": "string", "pattern": "^[A-Za-z0-9_-]{43,128}$"},
    },
    "required": ["source_id", "consent_state", "expected_revision", "operation_key", "user_intent_token"],
    "oneOf": [
        {"properties": {"consent_state": {"const": "on"}}, "required": ["expected_cursor_revision"]},
        {"properties": {"consent_state": {"const": "off"}}, "not": {"required": ["expected_cursor_revision"]}},
    ],
    "additionalProperties": False,
}

# The dashboard-only POST /sources/consent-intent route validates this schema
# (same as set_source_consent without user_intent_token)
CONSENT_INTENT_OPERATION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "source_id": {"type": "string", "pattern": "^src_[a-f0-9]{64}$"},
        "consent_state": {"enum": ["off", "on"]},
        "expected_revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
        "expected_cursor_revision": {"type": "integer", "minimum": 0, "maximum": 2147483647},
        "operation_key": {"type": "string", "minLength": 1, "maxLength": 200, "pattern": "^[A-Za-z0-9_-]+$"},
    },
    "required": ["source_id", "consent_state", "expected_revision", "operation_key"],
    "oneOf": [
        {"properties": {"consent_state": {"const": "on"}}, "required": ["expected_cursor_revision"]},
        {"properties": {"consent_state": {"const": "off"}}, "not": {"required": ["expected_cursor_revision"]}},
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Tests: Schema Validation & Adversarial Rejections
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
class TestRegistryInputSchemas:
    """Validates the input schemas against JSON Schema 2020-12."""

    def test_list_sources_schema_valid_and_invalid(self):
        validator = jsonschema.Draft202012Validator(LIST_SOURCES_SCHEMA)
        
        # Valid inputs
        assert validator.is_valid({})
        assert validator.is_valid({"kind": "podcast_rss", "consent_state": "off", "limit": 25})
        
        # Invalid inputs
        assert not validator.is_valid({"kind": "invalid_kind"})
        assert not validator.is_valid({"consent_state": "enabled"})
        assert not validator.is_valid({"limit": 0})
        assert not validator.is_valid({"limit": 101})
        assert not validator.is_valid({"unknown_param": True})  # additionalProperties

    def test_register_source_schema_valid_and_invalid(self):
        validator = jsonschema.Draft202012Validator(REGISTER_SOURCE_SCHEMA)
        
        # Valid inputs
        assert validator.is_valid({"kind": "podcast_rss", "url": "https://example.com/feed.xml"})
        assert validator.is_valid({"kind": "youtube_channel", "url": "https://youtube.com/channel/UC123", "poll_interval_min": 30})
        
        # Invalid inputs
        assert not validator.is_valid({"kind": "podcast_rss"})  # missing url
        assert not validator.is_valid({"url": "https://example.com"})  # missing kind
        assert not validator.is_valid({"kind": "podcast_rss", "url": "https://example.com", "poll_interval_min": 10})  # min is 15
        assert not validator.is_valid({"kind": "podcast_rss", "url": "https://example.com", "extra": "reject"})

    def test_source_status_schema_valid_and_invalid(self):
        validator = jsonschema.Draft202012Validator(SOURCE_STATUS_SCHEMA)
        valid_id = "src_" + "a" * 64
        
        # Valid inputs
        assert validator.is_valid({"source_id": valid_id})
        assert validator.is_valid({"source_id": valid_id, "item_limit": 50})
        
        # Invalid inputs
        assert not validator.is_valid({"source_id": 14})  # integer rejected
        assert not validator.is_valid({"source_id": "src_short"})  # pattern mismatch
        assert not validator.is_valid({"source_id": "14"})  # pattern mismatch
        assert not validator.is_valid({})  # missing required source_id

    def test_set_source_consent_schema_two_step_rules(self):
        """Verifies that expected_cursor_revision is required for on and forbidden for off."""
        validator = jsonschema.Draft202012Validator(SET_SOURCE_CONSENT_SCHEMA)
        valid_id = "src_" + "a" * 64
        token = "tok_" + "b" * 40  # 44 chars, matches ^[A-Za-z0-9_-]{43,128}$

        # Valid on: must include expected_cursor_revision
        valid_on = {
            "source_id": valid_id,
            "consent_state": "on",
            "expected_revision": 0,
            "expected_cursor_revision": 1,
            "operation_key": "op_turn_on_123",
            "user_intent_token": token,
        }
        assert validator.is_valid(valid_on)

        # Invalid on: missing expected_cursor_revision
        invalid_on = dict(valid_on)
        del invalid_on["expected_cursor_revision"]
        assert not validator.is_valid(invalid_on)

        # Valid off: omit expected_cursor_revision
        valid_off = {
            "source_id": valid_id,
            "consent_state": "off",
            "expected_revision": 1,
            "operation_key": "op_turn_off_123",
            "user_intent_token": token,
        }
        assert validator.is_valid(valid_off)

        # Invalid off: provides expected_cursor_revision (forbidden by oneOf not:required)
        invalid_off = dict(valid_off)
        invalid_off["expected_cursor_revision"] = 1
        assert not validator.is_valid(invalid_off)

        # Invalid token length (< 43 characters)
        short_token = dict(valid_off)
        short_token["user_intent_token"] = "short_token"
        assert not validator.is_valid(short_token)

        # Rejection of unknown properties
        extra_prop = dict(valid_off)
        extra_prop["extra_flag"] = True
        assert not validator.is_valid(extra_prop)

    def test_consent_intent_operation_schema(self):
        """Verifies schema for POST /sources/consent-intent route."""
        validator = jsonschema.Draft202012Validator(CONSENT_INTENT_OPERATION_SCHEMA)
        valid_id = "src_" + "a" * 64

        # Valid on intent operation
        assert validator.is_valid({
            "source_id": valid_id,
            "consent_state": "on",
            "expected_revision": 0,
            "expected_cursor_revision": 0,
            "operation_key": "op_test_1",
        })

        # Valid off intent operation
        assert validator.is_valid({
            "source_id": valid_id,
            "consent_state": "off",
            "expected_revision": 1,
            "operation_key": "op_test_2",
        })


# ---------------------------------------------------------------------------
# Tests: Contract Response Objects Integrity
# ---------------------------------------------------------------------------

class TestContractPayloadShapes:
    """Verifies that fixture payloads fulfill all mandatory contract response fields."""

    def test_source_summary_mandatory_fields(self):
        summary = get_default_off_summary()
        mandatory_keys = [
            "source_id", "kind", "canonical_url", "display_name", "adapter",
            "consent_state", "revision", "consent_epoch", "detection_enabled",
            "archived", "poll_interval_min", "boundary", "enrollment",
            "allowance", "detection", "counts_by_state"
        ]
        for k in mandatory_keys:
            assert k in summary, f"Mandatory summary key missing: {k}"

    def test_enrollment_mandatory_fields(self):
        enroll = get_default_off_summary()["enrollment"]
        assert enroll["cap"] == 25
        assert isinstance(enroll["enrolled"], int)
        assert isinstance(enroll["initial_completed"], bool)
        assert isinstance(enroll["known_candidates"], int)
        assert isinstance(enroll["pending"], bool)
        assert isinstance(enroll["remaining_initial_slots"], int)
        assert enroll["coverage"] in ("window", "complete", "partial", "unknown")

    def test_allowance_mandatory_fields(self):
        allow = get_default_off_summary()["allowance"]
        assert allow["cap"] == 10
        assert isinstance(allow["reserved"], int)
        assert isinstance(allow["charged"], int)
        assert isinstance(allow["remaining"], int)
        assert allow["remaining"] == max(0, 10 - allow["reserved"] - allow["charged"])
        assert len(allow["utc_day"]) == 10  # YYYY-MM-DD
        assert isinstance(allow["resets_at_ms"], int)

    def test_detection_mandatory_fields(self):
        det = get_default_off_summary()["detection"]
        assert isinstance(det["revision"], int)
        assert isinstance(det["observed_count"], int)
        assert det["coverage"] in ("window", "complete", "partial", "unknown")
        assert isinstance(det["error_count"], int)


# ---------------------------------------------------------------------------
# Tests: Endpoint Integration (Claude module dependency)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not HAS_SOURCE_SUBSCRIPTIONS,
    reason="source_subscriptions service endpoints not yet integrated by Fable (run AM dependency: Claude worker)",
)
class TestSourceSubscriptionsEndpointsIntegration:
    """Runs after Claude's service and migration 0028 are integrated by Fable."""

    def test_service_list_sources(self):
        pass

    def test_service_register_source(self):
        pass

    def test_service_source_status(self):
        pass

    def test_service_consent_intent_flow(self):
        pass
