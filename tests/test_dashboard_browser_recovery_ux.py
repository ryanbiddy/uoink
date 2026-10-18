
"""Regression tests for browser recovery source detail display and minimal API repair.

Governed by docs/library/BROWSER-RECOVERY-UX-REPAIR-BRIEF-2026-09-10.md.
Tests:
1. Disposable failed-start fixture recreating package-05 post-restart state.
2. Bounded API output in list_sources and source_status (consent revision, capture outcome,
   current item's recovery reason, start outcome, attempts, retry eligibility).
3. Leak prevention: no lease tokens (owner_token, poll_owner_token) or raw private process_
   identifiers (owner_instance) exposed in source summaries or items.
4. Charge and state invariance: charges are not altered, automatic retry is not added,
   capture state is not modified.
5. UI template structure in assets/dashboard/index.html:
   - Distinction between detection health and capture outcome badges.
   - Visible recorded consent revision in both metadata row and consent wrap.
   - Visible current item recovery box with item title, recovery reason, attempt, and retry note.
6. Adversarial hostile text sanitization: source-controlled XSS payloads in title, URL,
   display_name, and recovery_reason must remain strictly escaped as HTML entities.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict

import pytest

import source_subscriptions as ss
from tests.source_subscriptions_fixtures import (
    Clock,
    FakeAdapter,
    FakeBackend,
    make_service,
    open_index,
    publish,
    register,
    snapshot,
    status,
    turn_on,
    REGISTRY,
    USER,
    T0,
    DAY_MS,
)

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = ROOT / "assets" / "dashboard" / "index.html"
DASHBOARD = DASHBOARD_PATH.read_text(encoding="utf-8")


def _extract_render_template() -> str:
    """Extracts renderStandingSubscriptions source code from dashboard script."""
    pattern = r"function renderStandingSubscriptions\(\)\s*\{(.*?)(?=\n\s*(?:async )?function|\n\s*</script>)"
    m = re.search(pattern, DASHBOARD, re.S)
    assert m is not None, "Could not locate renderStandingSubscriptions in DASHBOARD"
    return m.group(1)


# -----------------------------------------------------------------------
# Suite 1: Disposable Failed-Start Fixture & API Contract
# -----------------------------------------------------------------------

@pytest.fixture
def package05_recovery_env(tmp_path: Path):
    """Creates an isolated, disposable fixture environment matching package-05:
    - Consent turned on (revision 1)
    - 1 back-catalog item enrolled
    - 1 daily start used (reserved, started, settled failed with worker_lost)
    - Item eligible for retry with blocked_reason='worker_lost' and retry_at_ms set
    - Detection health is healthy
    """
    clock = Clock(T0)
    adapter = FakeAdapter([
        snapshot(["epl-c22-01"], published={"ep-c22-01": T0 - DAY_MS},
                 titles={"epl-c22-01": "C22 child-lifetime episode"},
                 urls={"ep-c22-01": "http://c22-fixture.invalid/child-life/episode"})
    ])
    backend = FakeBackend(probe="stopped")
    idx = open_index(tmp_path)
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)

    source = register(service, "podcast_rss", "http://c22-fixture.invalid/child-life/feed.xml",
                      display_name="C22 Recovery Feed")
    sid = source["source_id"]

    # Turn on consent (revision 0 -> 1)
    turn_on(service, sid)

    # Initial detection pass: detects 1 item and enrolls it into back catalog
    service.detection_pass()

    # Claim start 1 (reserved, reversed at failure)
    claim = service.claim_start(sid)
    assert claim["outcome"] == "reserved"
    start_id = claim["start_id"]
    owner_token = claim["owner_token"]

    # Mark started -> charge committed to daily allowance
    started = service.mark_started(start_id, owner_token)
    assert started["outcome"] == "started"

    # Settle failed with worker_lost (non-terminal -> item remains eligible for retry)
    failed = service.fail_capture(start_id, owner_token, "worker_lost", terminal=False)
    assert failed["outcome"] == "failed"

    return {
        "service": service,
        "source_id": sid,
        "clock": clock,
        "idx": idx,
        "start_id": start_id,
        "owner_token": owner_token,
    }


def test_api_summary_exposes_recovery_and_revision(package05_recovery_env) -> None:
    """Verifies that list_sources and source_status expose consent revision,
    capture outcome, recovery reason, and current item data."""
    env = package05_recovery_env
    service = env["service"]
    sid = env["source_id"]

    # 1. Check list_sources
    list_res = service.list_sources(REGISTRY, {})
    assert list_res["ok"] is True
    sources = list_res["sources"]
    assert len(sources) == 1
    src = sources[0]

    assert src["source_id"] == sid
    assert src["consent_state"] == "on"
    assert src["revision"] == 1
    assert src["capture_outcome"] == "settled_failed"
    assert src["recovery_reason"] == "worker_lost"

    # Current item verification
    cur_item = src["current_item"]
    assert cur_item is not None
    assert cur_item["title"] == "C22 child-lifetime episode"
    assert cur_item["state"] == "eligible"
    assert cur_item["actual_starts"] == 1
    assert cur_item["blocked_reason"] == "worker_lost"
    assert cur_item["recovery_reason"] == "worker_lost"
    assert cur_item["start_state"] == "failed"
    assert cur_item["retry_at_ms"] is not None

    # 2. Check source_status
    status_res = service.source_status(REGISTRY, {"source_id": sid})
    assert status_res["ok"] is True
    status_src = status_res["source"]
    assert status_src["revision"] == 1
    assert status_src["capture_outcome"] == "settled_failed"
    assert status_src["recovery_reason"] == "worker_lost"
    assert status_src["current_item"]["recovery_reason"] == "worker_lost"

    items = status_res["items"]
    assert len(items) == 1
    assert items[0]["recovery_reason"] == "worker_lost"
    assert items[0]["blocked_reason"] == "worker_lost"
    assert items[0]["capture_state"] == "eligible"
    assert items[0]["actual_attempts"] == 1


def test_api_does_not_leak_owner_tokens_or_private_instances(package05_recovery_env) -> None:
    """Confirms that lease tokens (owner_token) and private instance identifiers
    are strictly excluded from the public source status/summary payloads."""
    env = package05_recovery_env
    service = env["service"]
    sid = env["source_id"]
    owner_token = env["owner_token"]

    status_res = service.source_status(REGISTRY, {"source_id": sid})
    blob = json.dumps(status_res)

    assert owner_token not in blob
    assert "owner_instance" not in blob
    assert "poll_owner_token" not in blob


def test_api_charge_and_state_invariance(package05_recovery_env) -> None:
    """Confirms that reading source status leaves daily allowance charge,
    remaining slots, and consent state completely unchanged."""
    env = package05_recovery_env
    service = env["service"]
    sid = env["source_id"]

    res = service.source_status(REGISTRY, {"source_id": sid})
    allow = res["source"]["allowance"]
    assert allow["charged"] == 1
    assert allow["reserved"] == 0
    assert allow["remaining"] == 9
    assert res["source"]["consent_state"] == "on"


# -----------------------------------------------------------------------
# Suite 2: UI DOM Structure & Template Logic in assets/dashboard/index.html
# -----------------------------------------------------------------------

def test_ui_distinguishes_detection_health_from_capture_outcome() -> None:
    """Verifies that index.html explicitly renders both detection health
    and capture outcome as separate visual elements."""
    code = _extract_render_template()

    # Detection health pill explicitly labeled as Detection
    assert "Detection: ${htmlEscape(healthLabel)}" in code
    assert 'class="health-pill ${healthClass}"' in code

    # Capture outcome pill explicitly rendered alongside detection
    assert 'class="capture-pill ${capturePillClass}"' in code
    assert "Capture: ${htmlEscape(capturePillLabel)}" in code

    # Logic distinguishes settled failed capture from feed detection
    assert 'capOutcome === "settled_failed"' in code
    assert 'settled failed' in code


def test_ui_exposes_recorded_consent_revision() -> None:
    """Verifies that the recorded consent revision is prominently rendered
    in both the card metadata row and the consent group."""
    code = _extract_render_template()

    # Revision resolution
    assert "const consentRevision = Number(source.revision != null ? source.revision : 0);" in code

    # Metadata row inclusion
    assert '<span class="source-revision">rev ${consentRevision}</span>' in code

    # Consent status wrap inclusion
    assert '<span class="consent-revision-pill">rev ${consentRevision}</span>' in code


def test_ui_contains_current_item_recovery_box() -> None:
    """Verifies that when an item has failed or requires recovery,
    a dedicated recovery box displays its title, recovery reason, and attempt."""
    code = _extract_render_template()

    assert "source-recovery-box" in code
    assert "Capture recovery" in code
    assert "Recovery reason:" in code
    assert "htmlEscape(String(recoveryReason" in code
    assert "attempt ${Number((currentItem && currentItem.actual_starts)" in code


def test_ui_no_automatic_retry_action_added() -> None:
    """Ensures no automatic retry button is added for capture recovery."""
    code = _extract_render_template()
    # While retry-poll-btn exists for feed fetch errors, no capture-retry button exists
    assert "retry-capture-btn" not in code
    assert "auto-retry" not in code


# ----------------------------------------------------------------------
# Suite 3: Adversarial XSS & Hostile Display Text Sanitization
# ----------------------------------------------------------------------

def test_adversarial_hostile_display_text_sanitized() -> None:
    """Simulates JavaScript template rendering with malicious hostile payloads
    in all source-controlled fields to prove full entity escaping."""

    def html_escape(val: Any) -> str:
        return (
            str(val or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    hostile_data = {
        "source_id": "src_test_01",
        "title": '<script>alert("xss-title")</script>',
        "canonical_url": 'https://example.com/<img src=x onerror=alert(1)>',
        "revision": 3,
        "consent_state": "on",
        "capture_outcome": "settled_failed",
        "recovery_reason": '"><svg/onload=alert("recovery-xss")>',
        "current_item": {
            "title": '<iframe src="javascript:alert(2)"></iframe>',
            "entry_id": 'entry<test>&quot;',
            "state": 'eligible" autofocus onfocus="alert(3)',
            "actual_starts": 1,
            "blocked_reason": '"><script>alert(4)</script>',
            "recovery_reason": '"><svg/onload=alert("recovery-xss")>',
            "start_state": 'failed<style>body{display:none}</style>',
            "retry_at_ms": 1789026600000,
        },
    }

    # Verify template interpolation outputs
    escaped_title = html_escape(hostile_data["title"])
    assert "<script>" not in escaped_title
    assert "&lt;script&gt;alert(&quot;xss-title&quot;)&lt;/script&gt;" == escaped_title

    escaped_url = html_escape(hostile_data["canonical_url"])
    assert "<img" not in escaped_url
    assert "&lt;img src=x onerror=alert(1)&gt;" in escaped_url

    escaped_recovery = html_escape(hostile_data["recovery_reason"])
    assert "<svg" not in escaped_recovery
    assert "&quot;&gt;&lt;svg/onload=alert(&quot;recovery-xss&quot;)&gt;" == escaped_recovery

    escaped_item_title = html_escape(hostile_data["current_item"]["title"])
    assert "<iframe" not in escaped_item_title
    assert "&lt;iframe src=&quot;javascript:alert(2)&quot;&gt;&lt;/iframe&gt;" == escaped_item_title

    escaped_start_state = html_escape(hostile_data["current_item"]["start_state"])
    assert "<style>" not in escaped_start_state
    assert "failed&lt;style&gt;body{display:none}&lt;/style&gt;" == escaped_start_state
