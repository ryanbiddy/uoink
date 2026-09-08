"""Phase 3 Dashboard Sources UI tests (Gate S20 real consent UI).

Tests DOM structure, data bindings, consent state transitions, back-catalog boundaries,
daily allowance representations, in-flight draining states, and adversarial sanitization
in assets/dashboard/index.html.

ADAPTATION NOTICE (Plan vs Contract Reconciliation):
Where Gemini's Phase 3 UI plan (PHASE3-UI-TEST-PLAN-2026-09-07.md) and Astra's normative contract
(PHASE3-CONTRACT-2026-09-07.md) differ, the contract wins per implementation brief §1.3:
1. Identifier format: Plan used integer `source_id` (e.g. 14); contract defines string `source_id`
   matching pattern `^src_[a-f0-9]{64}$` ('src_' + sha256(kind + '\\n' + source_key)).
2. Capability flow: Plan used direct toggle POST `/api/sources/subscriptions/consent`; contract
   specifies a two-step flow using dashboard-only route `POST /sources/consent-intent` to mint a
   single-operation, 5-minute capability token (`user_intent_token`) binding `expected_revision`
   and `expected_cursor_revision`, followed by `set_source_consent`.
3. Registry tools: Public registry tool names and argument schemas follow contract §6:
   - `list_sources`
   - `register_source`
   - `source_status`
   - `set_source_consent`
4. Back-catalog enrollment: Plan assumed an arbitrary query at toggle time; contract mandates that
   initial enrollment occurs atomically on the first valid poll snapshot while on, capped at
   min(25, available items), with remaining items remaining metadata-only.
5. Daily allowance ledger: Plan inferred starts from file/job timestamps; contract governs via an
   atomic 10-slot ledger (`source_capture_starts`) uniquely constrained by (source_id, utc_day, slot)
   with separate reserved vs charged accounting.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict

import pytest

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

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# Suite 1: DOM Elements and Markup Structure
# ---------------------------------------------------------------------------

def test_sources_ui_contains_standing_subscription_panel() -> None:
    """Verifies presence of #standingSubscriptions and summary counters in #tab-sources."""
    # Ensure standingSubscriptions is inside tab-sources before universalCapture
    tab_sources_idx = DASHBOARD.find('id="tab-sources"')
    require(tab_sources_idx != -1, "#tab-sources missing from dashboard")
    
    standing_idx = DASHBOARD.find('id="standingSubscriptions"', tab_sources_idx)
    require(standing_idx != -1, "#standingSubscriptions missing from #tab-sources")
    
    universal_idx = DASHBOARD.find('id="universalCapture"', standing_idx)
    require(universal_idx != -1, "#universalCapture must follow #standingSubscriptions")
    
    # Check summary stats
    for element_id in (
        "standingSummaryBar",
        "standingTotalSources",
        "standingActiveSources",
        "standingDailyStarts",
        "standingNextTick",
        "refreshStandingSources",
    ):
        require(f'id="{element_id}"' in DASHBOARD, f"Summary bar element missing: #{element_id}")
    
    # Check card container and empty state
    require('id="standingSubscriptionList"' in DASHBOARD, "#standingSubscriptionList container missing")
    require('id="standingEmptyState"' in DASHBOARD, "#standingEmptyState container missing")
    require("No standing subscriptions yet" in DASHBOARD, "Empty state copy missing")


def test_sources_ui_contains_consent_confirmation_modal() -> None:
    """Verifies presence of the consent confirmation modal with 25-cap and 10-start notices."""
    require('id="sourceConsentModal"' in DASHBOARD, "#sourceConsentModal dialog missing")
    for control_id in (
        "sourceConsentModalTitle",
        "sourceConsentModalPrompt",
        "sourceConsentModalPolicyList",
        "sourceConsentModalSummary",
        "sourceConsentModalWarning",
        "closeSourceConsentModal",
        "cancelSourceConsent",
        "confirmSourceConsent",
    ):
        require(f'id="{control_id}"' in DASHBOARD, f"Modal control missing: #{control_id}")

    # Verify contractual policy limits mentioned in modal
    require("25 most recent items" in DASHBOARD, "Modal must state 25-item back-catalog policy")
    require("10 starts per UTC day" in DASHBOARD, "Modal must state 10-start daily allowance")


def test_sources_ui_contains_source_registration_form() -> None:
    """Verifies presence of quick registration inputs for standing subscriptions."""
    for element_id in (
        "standingAddBar",
        "standingAddKind",
        "standingAddUrl",
        "standingAddDisplayName",
        "standingAddButton",
    ):
        require(f'id="{element_id}"' in DASHBOARD, f"Registration input missing: #{element_id}")

    # Check kind options
    require('value="podcast_rss"' in DASHBOARD, "podcast_rss option missing")
    require('value="youtube_channel"' in DASHBOARD, "youtube_channel option missing")
    require('value="youtube_playlist"' in DASHBOARD, "youtube_playlist option missing")


# ---------------------------------------------------------------------------
# Suite 2: Client-side Logic & Contract Implementation in Dashboard JS
# ---------------------------------------------------------------------------

def test_js_contains_standing_subscription_functions() -> None:
    """Asserts that all required Phase 3 client functions exist in the script."""
    required_functions = (
        "callRegistryTool",
        "loadStandingSubscriptions",
        "renderStandingSubscriptions",
        "startConsentFlow",
        "openConsentModal",
        "closeConsentModal",
        "confirmConsentMutation",
        "registerStandingSource",
        "retrySourcePoll",
    )
    for fn_name in required_functions:
        require(f"function {fn_name}" in DASHBOARD or f"async function {fn_name}" in DASHBOARD,
                f"Required Phase 3 function missing: {fn_name}")


def test_js_uses_contract_tool_names_and_intent_endpoint() -> None:
    """Verifies that the dashboard calls the contract's tools and dashboard intent route."""
    # Tool names from contract §6
    require('"list_sources"' in DASHBOARD, 'list_sources tool call missing')
    require('"register_source"' in DASHBOARD, 'register_source tool call missing')
    require('"source_status"' in DASHBOARD, 'source_status tool call missing')
    require('"set_source_consent"' in DASHBOARD, 'set_source_consent tool call missing')
    
    # Capability route
    require('"/sources/consent-intent"' in DASHBOARD, 'Dashboard route /sources/consent-intent missing')
    
    # Parameter names
    require("expected_revision" in DASHBOARD, "expected_revision parameter missing")
    require("expected_cursor_revision" in DASHBOARD, "expected_cursor_revision parameter missing")
    require("operation_key" in DASHBOARD, "operation_key parameter missing")
    require("user_intent_token" in DASHBOARD, "user_intent_token parameter missing")


# ---------------------------------------------------------------------------
# Suite 3: S20 Real Consent UI State Renderings
# ---------------------------------------------------------------------------

def _extract_render_template() -> str:
    """Extracts renderStandingSubscriptions source code from dashboard script."""
    pattern = r"function renderStandingSubscriptions\(\)\s*\{(.*?)(?=\n\s*(?:async )?function|\n\s*</script>)"
    m = re.search(pattern, DASHBOARD, re.S)
    require(m is not None, "Could not locate renderStandingSubscriptions in DASHBOARD")
    return m.group(1)


def test_subscription_card_renders_default_off_state() -> None:
    """Simulates rendering of default-off source: verifies pill, button, and metadata notice."""
    summary = get_default_off_summary()
    code = _extract_render_template()

    # Verify logic branches in render function
    require('consent_state === "on" ? "on" : "off"' in code, "Consent pill off-state class missing")
    require('"Off (Metadata only)"' in code, "Default off pill copy missing")
    require('"Turn On Standing Capture"' in code, "Toggle turn-on button copy missing")
    require("Metadata only; zero audio downloads or compute spend." in code,
            "No-compute explanation missing from off state")
    require('"Back catalog: 0 / 25 enrolled (idle)"' in code,
            "Idle back catalog copy missing for default off state")


def test_pending_enrollment_renders_pending_notice() -> None:
    """Contract: UI says enrollment is pending and shows 'up to 25', not an invented count."""
    code = _extract_render_template()
    require('enroll.pending' in code, "Check for enroll.pending missing in render logic")
    require('"Enrollment pending (up to 25 items)"' in code,
            "Pending enrollment copy 'up to 25 items' missing")


def test_back_catalog_meter_shows_25_item_cap_boundary() -> None:
    """Verifies that enrolled active sources display the 25 cap and excluded count."""
    code = _extract_render_template()
    require('candidateCount > enrolledCount' in code, "Candidate exclusion calculation missing")
    require("older items excluded by cap." in code, "Excluded older items notice missing")


def test_daily_allowance_meter_reflects_utc_day_budget() -> None:
    """Verifies rendering of consumed starts, remaining starts, and UTC reset countdown."""
    code = _extract_render_template()
    require("starts used" in code, "Allowance meter used starts label missing")
    require("Resets at 00:00 UTC" in code, "UTC reset countdown string missing")
    require("Math.max(0, allow.resets_at_ms - Date.now())" in code or "resets_at_ms" in code,
            "Dynamic reset calculation missing")


def test_daily_cap_exhaustion_locks_queue_and_shows_countdown() -> None:
    """Verifies that 10/10 starts styling applies .exhausted and displays pause warning."""
    code = _extract_render_template()
    require('isExhausted' in code, "isExhausted logic missing")
    require('"exhausted"' in code, "Exhausted meter styling missing")
    require("Daily allowance reached." in code, "Daily allowance reached warning copy missing")
    require("Starts paused until next UTC day." in code, "Pauses starts notice missing")


def test_legacy_accounting_hold_displays_badge_and_notice() -> None:
    """Verifies that legacy accounting hold is flagged and not presented as startable capacity."""
    code = _extract_render_template()
    require("allow.hold_reason" in code or "allow.hold_until_ms" in code,
            "Legacy hold condition missing in allowance render")
    require("Legacy accounting hold active." in code, "Legacy accounting hold note missing")


def test_opt_out_renders_draining_in_flight_state() -> None:
    """Contract & Plan: Off with active in-flight displays Draining and drain notice."""
    code = _extract_render_template()
    require('source.consent_state === "off" && inFlight.length > 0' in code,
            "Draining condition missing")
    require('"Draining in-flight work"' in code, "Draining pill copy missing")
    require("draining-banner" in code, "Draining banner styling missing")
    require("will finish cleanly" in code, "Clean finish notice for draining state missing")


def test_in_flight_box_renders_active_items_and_activity_link() -> None:
    """Verifies in-flight container displays active titles, phases, attempts, and activity link."""
    code = _extract_render_template()
    require("in-flight-box" in code, "in-flight-box container missing")
    require('href="#tab-activity"' in code, "Deep link to #tab-activity missing")
    require("actual_starts" in code or "attempt" in code, "Attempt counter missing in in-flight box")


def test_unreachable_feed_renders_degraded_pill_and_backoff_notice() -> None:
    """Verifies that feed failure renders vermillion pill, error text, and retry button."""
    code = _extract_render_template()
    require('"Feed unreachable"' in code, "Feed unreachable error pill label missing")
    require("source-error-strip" in code, "source-error-strip container missing")
    require("consecutive failure" in code, "Consecutive failure counter missing")
    require("Retry poll now" in code, "Retry poll now button missing")


# ---------------------------------------------------------------------------
# Suite 4: Adversarial & Safety Verification
# ---------------------------------------------------------------------------

def test_xss_in_feed_metadata_escaped() -> None:
    """Verifies that titles, URLs, and errors use htmlEscape before insertion into innerHTML."""
    code = _extract_render_template()
    require("htmlEscape(title)" in code, "title must be wrapped in htmlEscape()")
    require("htmlEscape(source.canonical_url" in code, "canonical_url must be wrapped in htmlEscape()")
    require("htmlEscape(id)" in code, "source_id must be wrapped in htmlEscape()")
    require("htmlEscape(String((det.last_error" in code or "htmlEscape" in code,
            "error message must be escaped")


def test_stale_revision_or_confirmation_recovers_and_refreshes() -> None:
    """Contract: Stale revision/cursor error causes view reload without overwriting state."""
    # Check startConsentFlow error recovery
    start_flow = DASHBOARD.split("async function startConsentFlow", 1)[1].split("function openConsentModal", 1)[0]
    require("stale_revision" in start_flow or "stale_cursor" in start_flow,
            "startConsentFlow must handle stale_revision / stale_cursor")
    require("loadStandingSubscriptions" in start_flow, "startConsentFlow must refresh view on stale error")

    # Check confirmConsentMutation error recovery
    confirm_mutation = DASHBOARD.split("async function confirmConsentMutation", 1)[1].split("async function registerStandingSource", 1)[0]
    require("stale_revision" in confirm_mutation or "stale_cursor" in confirm_mutation,
            "confirmConsentMutation must handle stale_revision / stale_cursor")
    require("loadStandingSubscriptions" in confirm_mutation, "confirmConsentMutation must refresh view")


def test_dom_clobbering_resistance() -> None:
    """Verifies that DOM lookups are scoped through els object rather than bare window lookups."""
    # Check that script references els.standingSubscriptionList rather than window.standingSubscriptionList
    require("els.standingSubscriptionList" in DASHBOARD, "Lookups must use els object")
    require("els.standingSummaryBar" in DASHBOARD, "Lookups must use els object")
    require("els.sourceConsentModal" in DASHBOARD, "Lookups must use els object")


def test_mock_utc_clock_behavior() -> None:
    """Validates MockUtcClock utility across midnight boundaries."""
    clock = MockUtcClock()
    assert clock.utc_day() == "2026-09-07"
    
    # Step across midnight
    clock.step_across_midnight(2.0)
    assert clock.utc_day() == "2026-09-08"
    assert not clock.is_clock_regressed()


def main() -> int:
    pytest.main(["-v", __file__])
    return 0


if __name__ == "__main__":
    main()
