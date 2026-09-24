# Browser Recovery UX Bounded Repair: Worker Report

- **Worker**: gemini
- **Date**: 2026-09-11
- **Task**: Implement bounded source display and minimal API repair per `docs/library/BROWSER-RECOVERY-UX-REPAIR-BRIEF-2026-09-10.md`
- **Worktree**: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\ac33fef6-703\gemini`

---

## 1. Problem Summary

Package-05 post-restart browser observation showed consent enabled, 1 of 25 back-catalog items enrolled, 1 of 10 daily starts used, and zero active or queued Activity rows. Feed detection health displayed "Healthy", while the underlying capture start had failed with code `worker_lost` and its item was eligible for retry.

The dashboard UI had three visibility gaps:
1. It conflated feed detection health with capture execution health. A source with working RSS/atom polling showed green "Healthy" even when capture starts were failing or dead.
2. It omitted the source consent revision number (`revision`).
3. It omitted the failed capture state and recovery reason (`worker_lost`) for the enrolled item.

Per the repair brief, this repair required:
- Distinguishing detection health from capture outcome.
- Exposing the recorded consent revision.
- Showing the current item's recovery reason using existing bounded status data.
- Preserving HTML escaping across all source-controlled fields.
- Ensuring zero leakage of lease tokens (`owner_token`, `poll_owner_token`) or process IDs (`owner_instance`).
- Strictly avoiding automatic retries, charge changes, or forced capture toggling.
- Adding separate regression tests without altering existing acceptance tests or markers.

---

## 2. Implementation Changes

### `source_subscriptions.py`
1. Added helper method `_capture_outcome_and_current_item(conn, source, allowance, in_flight, counts, now)`.
   - Inspects the latest `source_capture_starts` row and associated `source_items` row for the source.
   - Derives `capture_outcome`: `"archived"`, `"off"`, `"draining"`, `"in_flight"`, `"settled_failed"`, `"uncertain"`, `"succeeded"`, `"allowance_exhausted"`, `"completed"`, or `"idle"`.
   - Populates `current_item` dict with bounded, public fields: `item_id`, `entry_id`, `title`, `state`, `actual_starts`, `blocked_reason`, `recovery_reason`, `retry_at_ms`, and `start_state`.
   - Extracts `recovery_reason` from `blocked_reason` or `release_or_failure_code`.
2. Updated `_summary()` to return:
   - `"capture_outcome": capture_outcome`
   - `"recovery_reason": recovery_reason`
   - `"current_item": current_item`
3. Updated `_item_record()` to expose `"recovery_reason"` bounded to 200 safe characters when present.
4. Security & Privacy Audit:
   - Neither `owner_token` nor `poll_owner_token` is included in `_summary()` or `_item_record()`.
   - Neither `owner_instance` nor any raw PID is included.
   - No database mutations, charge deductions, or retry triggers were introduced.

### `assets/dashboard/index.html`
1. CSS additions:
   - Distinct capture pill styling: `.capture-pill` with variants `.ready`, `.idle`, `.in-flight`, `.draining`, `.uncertain`, `.exhausted`, `.failed`, `.off`.
   - Revision pill styling: `.consent-revision-pill`.
   - Recovery block styling: `.source-recovery-box`, `.source-recovery-head`, `.source-recovery-item`, `.source-recovery-meta`, `.source-recovery-reason`.
2. Template rendering in `renderStandingSubscriptions()`:
   - Distinct badges: `<span class="health-pill ${healthClass}">Detection: ${htmlEscape(healthLabel)}</span>` and `<span class="capture-pill ${capturePillClass}">Capture: ${htmlEscape(capturePillLabel)}</span>`.
   - Consent revision displayed in metadata line (`<span class="source-revision">rev ${consentRevision}</span>`) and alongside consent pill (`<span class="consent-revision-pill">rev ${consentRevision}</span>`).
   - Recovery panel rendered when recovery or settled failed status exists (`.source-recovery-box`). Shows item title, attempt count (`1/3`), recovery reason (`worker_lost`), start state (`failed`), and retry eligibility notice (`eligible for retry`).
   - All source-controlled strings are passed through `htmlEscape()`.

### `tests/test_dashboard_browser_recovery_ux.py` (New)
Added 8 regression tests organized into three suites:
1. **Suite 1: Disposable Failed-Start Fixture & API Contract**
   - `test_package05_source_summary_exposes_recovery_and_revision`: verifies `revision == 1`, `capture_outcome == "settled_failed"`, `recovery_reason == "worker_lost"`, and `current_item` fields.
   - `test_source_status_endpoint_returns_recovery_fields`: verifies HTTP-level JSON output from `/api/sources/{id}/status`.
   - `test_no_lease_token_or_process_id_leakage`: asserts `owner_token`, `poll_owner_token`, `owner_instance` are absent from source summaries and item records.
   - `test_charge_and_retry_invariance`: confirms starts count remains 1, remaining allowance remains 9, and no automatic retry mutation occurred.
2. **Suite 2: UI DOM & Template String Verification**
   - `test_dashboard_template_renders_detection_and_capture_distinctly`: checks for `Detection:` and `Capture:` labels and distinct CSS classes.
   - `test_dashboard_template_renders_consent_revision_and_recovery_box`: checks for `source-revision`, `consent-revision-pill`, and `source-recovery-box`.
   - `test_no_auto_retry_trigger_in_ui_render`: verifies no automated fetch/POST triggers exist in the rendering path.
3. **Suite 3: Adversarial Hostile Display Text Sanitization**
   - `test_adversarial_hostile_display_text_sanitized`: tests hostile strings with `<script>`, `<iframe src=...>`, `<img onerror=...>`, and `<svg onload=...>` against `html_escape()`, confirming character entities replace tag delimiters and attribute quotes.

---

## 3. Verification Evidence

### Verification Command
Run within the dedicated worktree using the guarded integrator script and native Python interpreter:

```powershell
$env:IG_FORBIDDEN_LIVE = "$env:LOCALAPPDATA\Uoink\index.db"
$python = "E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe"
$script = "E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/integrator_verify.py"
$phase3 = (Get-ChildItem tests/library_work_astra/test_phase3_*.py | Where-Object { $_.Name -ne 'test_phase3_s21.py' } | ForEach-Object { "tests/library_work_astra/" + $_.Name })
& $python $script --root $PWD --label "browser-recovery-worker-01" tests/test_dashboard_sources_ui.py tests/test_dashboard_sources_api.py tests/test_dashboard_browser_recovery_ux.py @phase3
```

### Verification Outcome
- **Total test cases**: 221
- **Passed**: 220
- **Failed**: 1 (Historical AT6 exit status failure, strictly expected)
- **Execution duration**: 39.54s
- **Output log location**: `_scratch/browser-recovery-worker-01/tests.log`
- **Result JSON**: `_scratch/browser-recovery-worker-01/results.json`

The single failure is:
```text
FAILED tests/library_work_astra/test_phase3_acceptance7.py::test_as7_c21_at6_receipt_records_process_exit_status
AssertionError: ('Retained AT6 receipt has no explicit successful process exit status', {})
```
This is the retained historical failure documented across all prior Phase 3 runs (standing rule: historical AT6 lacks explicit exit status).

Every other suite passed:
- `tests/test_dashboard_sources_ui.py`: 12 passed
- `tests/test_dashboard_sources_api.py`: 19 passed
- `tests/test_dashboard_browser_recovery_ux.py`: 8 passed
- Phase 3 strict suites (acceptance 3-9 except AT6 exit status, concurrency, harness, integration, migration, publication, recovery, repairs, support): 181 passed

---

## 4. Integrity and Non-Regression Confirmation
- No existing acceptance tests were modified.
- No skip, xfail, or assertion lines in existing test files were touched.
- Live database `%LOCALAPPDATA%\Uoink\index.db` was not opened or accessed.
- Port 5179 was not contacted.
- `ANTHROPIC_API_KEY` was unset during all test executions.
- All modifications are confined to `source_subscriptions.py`, `assets/dashboard/index.html`, `tests/test_dashboard_browser_recovery_ux.py`, and this document.

---

## 5. Downstream Boundary
This worker run is restricted to the local worktree. Rebuilding the installer package, candidate sealing, and collecting fresh post-restart browser observations on an installed target are downstream responsibilities for the integrator.
