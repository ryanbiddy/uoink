# Phase 3 S20 browser matrix receipt (condition C20, 2026-09-08)

Fable's observation receipt for Astra's condition C20 in
[PHASE3-ACCEPTANCE-6-2026-09-08.md](PHASE3-ACCEPTANCE-6-2026-09-08.md): "supply the
disposable candidate's full browser matrix: default off, pending/actual enrollment,
exhausted allowance, refresh errors, off with in-flight work, lost mutation response,
stale confirmation and restart. Match visible state to persisted service state."

Everything below was observed by Fable in Chrome against a disposable overlay; nothing
touched the resident helper (port 5179) or the live index. Screenshots and persisted-state
dumps are in `docs/library/proof/s20-2026-09-08/` (SHA256SUMS inside).

## Candidate and harness

| Item | Value |
|---|---|
| Branch / commit under test | `cc/living-library`, server bytes at `d2ec84a` (AS-02b fix); dashboard bytes as committed in `12339c3` |
| `assets/dashboard/index.html` sha256 | `c8e46d62e2681c15be303a42196c35b518d1b77f8ffae7dd31f2defbb9cd62f3` |
| `server.py` sha256 | `4941b29457a4eb80cb343ebf6ed54079fd7858bb75341f8d81f8f494c12c526f` |
| `source_subscriptions.py` sha256 | `c7070839060b168c1738cc4eaf606993df2e39dfbc8fb0cc80df64671eda7fa7` |
| Overlay launcher | `tests/library_work_astra/s20_matrix_launcher.py` (sha256 `8d2279f0745024a1347b121a62871c3285c1cffa1e0d4f3c24faf061f868b697`), derived from Astra's S21 launcher: isolated data root under `_scratch/`, socket/DNS/process/model guards, byte-identical server copy, fixture feed on loopback, plus a loopback control endpoint (`/ctl?mode=&entries=&advance_min=&tick=1&restart=1&state=1`) |
| Command | `python -B tests/library_work_astra/s20_matrix_launcher.py --execute-s20-matrix --hold-seconds 1800` with `PYTHONPATH=<checkout>`, `PHASE3_REQUIRE_IMPLEMENTATION=1`, `ANTHROPIC_API_KEY` unset |
| Browser | Chrome, Claude-in-Chrome tab, 1536x784 viewport; coordinate clicks; page `fetch` wrapped only for scenario 07 (see below) |
| Model calls / forbidden attempts | 0 / 0 in every overlay instance (the whisperx availability probe is the documented exemption) |

Three overlay instances were used. Scenarios 01-05 ran on the first instances (their hold
logs were overwritten by the next instance; the persisted-state dumps and screenshots were
captured at the time). Scenarios 06-07 ran on the instance whose log is
`overlay-1-hold.log` (dashboard `127.0.0.1:50515`, control `:50516`). Scenario 08 ran on a
fresh instance (`overlay-2-hold.log`, dashboard `:60909`, restarted on `:60235`) after a
launcher repair described under scenario 08. The launcher's feed, control and dashboard
ports differ per instance and appear in the screenshots.

## Matrix

Visible state was compared with the persisted service state read through the control
endpoint (`source_subscriptions`, `source_capture_starts`, `source_items`,
`source_consent_receipts`) at the moment of each screenshot.

| # | Scenario | Browser-visible state | Persisted service state | Match |
|---|---|---|---|---|
| 01 | Default off | New source row: "Off (Metadata only)", capture active 0, 0/10 starts, enrollment 0/25 idle (`01-default-off.jpg`) | consent off, detection on, revision 0, epoch 0, 0 items, 0 receipts | yes |
| 02a | Consent modal | "Enable standing capture" modal with back-catalog (25), daily allowance (10), standing ingest copy (`02a-consent-modal.jpg`) | no mutation yet: the intent is minted only on confirm | yes |
| 02b | Pending enrollment | After confirm: "On (Standing capture)", "Enrollment pending (up to 25 items)", toast "Standing capture enabled. Back-catalog enrollment in progress." (`02b-on-enrollment-pending.jpg`) | consent on, revision 1, epoch 1, boundary `initial`, 0 items, 1 receipt | yes |
| 02c | Actual enrollment | After the first poll: "Back catalog: 3 / 25 items enrolled", observed 3 (`02c-actual-enrollment.jpg`) | 3 items `back_catalog` (two eligible, one committed by the first capture pass), 1 start succeeded | yes |
| 03 | Refresh error (rerun after AS-7) | Feed answering HTTP 500 on poll: badge `degraded: http_500: HTTP 500`, fetch notice `http_500: HTTP 500 (1 consecutive failure)`, 1/10 starts today, Captured items (2), 3/25 enrolled, observed 3 (`03-refresh-error.jpg`) | Complete package frozen before and after the screenshot (`03-refresh-error.state.json`, `03-refresh-error.state.after-screenshot.json`, identical except `observed_at_ms`): cursor `last_error_code=http_500`, `source_status.detection.consecutive_failures=1`, allowance charged 1 for `2026-09-09`, two succeeded starts in the ledger (one charged on `2026-09-08` before the injected clock advance, one by the capture pass of the failed-poll tick), items committed 2 | yes |
| 04 | Exhausted allowance | 10/10 starts used, "Daily allowance reached", enrollment 14/25, Library shows the 10 captured items (`04a-exhaustion-library-10-items.jpg`, `04b-exhaustion-sources.jpg`) | 10 starts succeeded for the UTC day, charged 10, eligible items remain eligible without new reservations | yes |
| 05 | Stale confirmation | Modal opened at revision 1; a concurrent operator changed consent (revision 2) before confirm; confirm answered HTTP 409 stale revision, toast "Source was modified concurrently. Refreshed with latest server state.", row shows the operator's state (`05a-stale-confirmation-modal-open.jpg`, `05b-stale-confirmation-refused-refreshed.jpg`) | consent off, revision 2 (set by the concurrent operation), no receipt for the refused confirm | yes |
| 06 | Off with in-flight work | Capture stalled in a slow audio download: "In-flight capture (1 active)", "started (attempt 1/3)"; Turn Off modal shows "Draining in-flight work: 1 active download/transcription in progress will finish cleanly. Unstarted reservations will be released."; after confirm: pill "Draining in-flight work", banner "Standing capture turned off. No new downloads will start. 1 active item will finish cleanly.", capture active 0, allowance still 1/10 (`06a`, `06b`, `06c`) | consent off, revision 2, epoch 1, receipts 2; start `st_ea4ccabd7` still `started` (not killed), item 3 `started`, other items eligible; the start later finished `succeeded` and item 3 `committed` (`07a.state.txt`) | yes |
| 07a | Lost mutation response, single transport | Page `fetch` wrapped so the MCP transport's response is discarded after the server answered 200. The dashboard's fallback (`POST /tools/set_source_consent`, same `operation_key`, same token) got the replayed receipt: toast "Standing capture enabled", row On (`07a-lost-mcp-response-retry-replayed.jpg`) | consent on, revision 3, epoch 2, receipts 3: one receipt for two requests (operation-key replay returned the original receipt; no second transition, no consumed-token failure) | yes |
| 07b | Lost mutation response, both transports | Both responses discarded after the server answered 200 each: toast "Consent update failed: Failed to fetch"; the `finally` refresh shows Off and capture active 0, which is the server's truth (`07b-lost-both-responses-failed-toast-refreshed-off.jpg`) | consent off, revision 4, receipts 4 (applied once; the second request replayed) | yes |
| 08 | Restart | Capture in flight (slot 2, stalled 420 s download): On, 2/10, "started (attempt 1/3)" (`08a`). Control `restart=1` closed the listening helper, re-bound on a fresh ephemeral port and ran `reconcile_on_startup()`. Fresh page load on the new port: On, 2/10, "In-flight capture (1 active)" with the item labelled `uncertain (attempt 1/3)` (`08b`); Library shows the item committed before the restart (`08c`) | reconcile `{released 0, leases_expired 0, succeeded 0, failed 0, uncertain 1}`; start `st_e38e3a6f` `uncertain`, item 2 `uncertain` with `actual_starts 1`, slot charge preserved (2), consent on revision 1 unchanged | yes |

Every scenario matched. No relabelling: scenario 08's `uncertain` outcome is what the
production reconciliation persisted for a start whose executor could not be verified after
the restart (the AS-6 ledger rule: charged and uncertain, no redispatch).

## Supersession record (AS-7)

Astra's AS-7 ruled scenario 03's first pair inconsistent: its hand-written summary read
nonexistent source-row fields and the screenshot showed a second charge the summary did not
explain. Scenario 03 was rerun on a fourth overlay (`overlay-4-hold.log`) with the launcher's
state dump extended to the complete package (detection cursors, consent receipts, the public
`source_status` objects, `observed_at_ms`), taken before and after the screenshot with no tick
between. The new pair supersedes the first; the AS-7 selector's expected "2/10" belongs to
the superseded image (the new image shows 1/10 for the current UTC day with two ledger starts
across the injected day boundary). `03-refresh-error.pre-strip-fix.jpg` is the same frozen
state rendered before the fetch-notice strip was changed to show `detection.error`.

## Defects found and repaired while executing the matrix (committed in `12339c3`)

1. Consent intent minted before confirmation. `startConsentFlow` posted to
   `/sources/consent-intent` without `confirmed: true` as the modal opened, so the route
   answered 403 `user_intent_required` and the toast rendered `[object Object]`. The intent
   is now minted by `confirmConsentMutation` as the confirmed click, bound to the revisions
   displayed when the modal opened; `consentErrorMessage()` renders structured errors.
   Scenarios 02, 05, 06 and 07 exercise the repaired path.
2. Health badge read fields the status route does not emit. It now reads
   `detection.consecutive_failures` and `detection.error.{code,message}`; scenario 03 shows
   `degraded: http_500`.

Both are dashboard-only changes; `tests/test_dashboard_sources_ui.py`,
`tests/test_dashboard_sources_api.py`, `tests/test_dashboard_v324_ui.py` and the Phase 5
dashboard suites pass (53).

## Launcher notes (Fable-only tooling, not an acceptance surface)

- The first restart attempt bound the helper to its previous fixed port; the S21 socket
  guard permits only ephemeral binds, so the handler raised and the first instance lost its
  helper (trace at the end of `overlay-1-hold.log`). The restart handler now re-binds on
  port 0, updates `server.PORT`, and reports the new dashboard URL; the control handler also
  applies `advance_min` before `tick`. Scenario 08 was re-run on a fresh instance with the
  repaired launcher; scenarios 01-07 were unaffected (their state was recorded before the
  failed restart).
- The overlay restart keeps the Python process alive (only the listening helper is
  replaced), so the in-flight capture thread survives; `reconcile_on_startup()` still ran
  exactly as at process start and classified the start as uncertain. A process-level
  restart with a real child is covered by `PHASE3-S22-RECEIPT-2026-09-08.md` and
  `docs/library/proof/procrec-2026-09-08/`.

## What this receipt does not claim

- No installed Inno package was used (C22 remains Ryan's).
- Scenario 07 wraps the page's `fetch` to discard responses; the server-side requests were
  real and are recorded in `07-lost-mutation-response.notes.txt`.
- The screenshots are JPEG captures of the Chrome tab; the persisted-state dumps are the
  authoritative comparison basis.
