"""Sample fixture payloads representing source summary and status objects

Matches contract schema for list_sources and source_status.
"""
from __future__ import annotations

from typing import Any, Dict


def get_default_off_summary() -> Dict[str, Any]:
    return {
        "source_id": "src_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "kind": "podcast_rss",
        "canonical_url": "https://example.com/podcast.xml",
        "display_name": "The Architecture of Memory",
        "adapter": "podcast_rss_v1",
        "consent_state": "off",
        "revision": 0,
        "consent_epoch": 0,
        "detection_enabled": True,
        "archived": False,
        "poll_interval_min": 60,
        "boundary": "none",
        "enrollment": {
            "cap": 25,
            "enrolled": 0,
            "initial_completed": False,
            "known_candidates": 5,
            "pending": False,
            "remaining_initial_slots": 25,
            "coverage": "complete",
        },
        "allowance": {
            "utc_day": "2026-09-07",
            "cap": 10,
            "reserved": 0,
            "charged": 0,
            "remaining": 10,
            "resets_at_ms": 1757376000000,
            "capture_not_before_ms": 0,
            "hold_reason": None,
            "hold_until_ms": None,
        },
        "detection": {
            "revision": 1,
            "last_poll_attempt_ms": 1757275200000,
            "last_poll_success_ms": 1757275200000,
            "next_poll_at_ms": 1757278800000,
            "observed_count": 5,
            "coverage": "complete",
            "truncated": 0,
            "error_count": 0,
            "last_error": None,
        },
        "counts_by_state": {
            "observed": 5,
            "eligible": 0,
            "reserved": 0,
            "started": 0,
            "uncertain": 0,
            "committed": 0,
            "failed": 0,
            "deleted": 0,
        },
    }


def get_pending_enrollment_summary() -> Dict[str, Any]:
    s = get_default_off_summary()
    s["consent_state"] = "on"
    s["revision"] = 1
    s["consent_epoch"] = 1
    s["boundary"] = "initial"
    s["enrollment"]["pending"] = True
    s["enrollment"]["enrolled"] = 0
    s["enrollment"]["initial_completed"] = False
    return s


def get_enrolled_active_summary() -> Dict[str, Any]:
    s = get_default_off_summary()
    s["consent_state"] = "on"
    s["revision"] = 1
    s["consent_epoch"] = 1
    s["boundary"] = "none"
    s["initial_enrollment_completed_ms"] = 1757275200000
    s["enrollment"]["pending"] = False
    s["enrollment"]["enrolled"] = 25
    s["enrollment"]["initial_completed"] = True
    s["enrollment"]["remaining_initial_slots"] = 0
    s["enrollment"]["known_candidates"] = 67
    s["allowance"]["reserved"] = 1
    s["allowance"]["charged"] = 3
    s["allowance"]["remaining"] = 6
    s["counts_by_state"]["eligible"] = 21
    s["counts_by_state"]["committed"] = 3
    s["counts_by_state"]["reserved"] = 1
    return s


def get_allowance_exhausted_summary() -> Dict[str, Any]:
    s = get_enrolled_active_summary()
    s["allowance"]["reserved"] = 0
    s["allowance"]["charged"] = 10
    s["allowance"]["remaining"] = 0
    return s


def get_legacy_hold_summary() -> Dict[str, Any]:
    s = get_default_off_summary()
    s["consent_state"] = "on"
    s["revision"] = 1
    s["consent_epoch"] = 1
    s["allowance"]["hold_reason"] = "legacy_accounting_hold"
    s["allowance"]["hold_until_ms"] = 1757376000000
    s["allowance"]["remaining"] = 0
    return s


def get_draining_summary() -> Dict[str, Any]:
    s = get_default_off_summary()
    s["consent_state"] = "off"
    s["revision"] = 2
    s["consent_epoch"] = 1
    s["allowance"]["charged"] = 1
    s["allowance"]["remaining"] = 9
    s["in_flight"] = [
        {
            "start_id": "st_test_001",
            "item_id": "si_test_001",
            "entry_id": "aom-ep-105-atomic-slots",
            "title": "Episode 105: Durable Ledgers and Atomic Slots",
            "canonical_url": "https://example.com/audio/ep105.mp3",
            "eligibility": "back_catalog",
            "state": "started",
            "actual_starts": 1,
            "retry_at_ms": None,
            "blocked_reason": None,
            "utc_day": "2026-09-07",
            "video_id": None,
            "committed_at_ms": None,
            "classification_state": "not_captured",
            "work_id": None,
        }
    ]
    return s


def get_unreachable_error_summary() -> Dict[str, Any]:
    s = get_default_off_summary()
    s["detection"]["error_count"] = 3
    s["detection"]["last_error"] = {
        "code": "feed_unreachable",
        "message": "HTTP 503: Service Unavailable (upstream server overloaded)",
    }
    s["detection"]["next_poll_at_ms"] = 1757282400000
    return s
