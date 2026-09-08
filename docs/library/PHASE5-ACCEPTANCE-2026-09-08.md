**PHASE 5 PART A NOT ACCEPTED**

Run BA, 2026-09-08. Reviewer: codex. Contract: [phase5-v1](PHASE5-CONTRACT-2026-09-08.md).
Candidate reviewed: `df5ece2edc81d8b2d5db85362aeb2143b87e8344`, including AZ-2
`619766b` and the integrated Phase 4 changes. The
[BA brief](PHASE5-BA-BRIEF-2026-09-08.md) was opened first.

The supplied 28 tests pass, but their assertions do not establish the frozen
gates. The reader returns incorrect evidence populations, proves invalid
baselines, counts deleted memberships as current, and changes source capture
counts when publication mode is selected. The default dashboard request is
invalid. Actual stdio responses exceed the wire cap and lack the required trust
envelope. These are release blockers, not conditions to defer after acceptance.

Review and reproductions used this dedicated worktree, disposable migrated
SQLite databases, a fixed UTC clock for the new reader tests, and an isolated
Node DOM/transport double for dashboard behavior. No model, resident helper,
live index, port 5179, build installation, commit or merge was used. Runtime
implementation files remain unchanged. This is source and fixture acceptance;
it is not an installed-build computer-use receipt.

Observed results on Python 3.14.6 and Node v24.18.0:

| Suite | Observed result |
|---|---|
| `tests/test_library_analysis_fixtures.py` | 28 passed in 10.96 s |
| `tests/test_phase0_registry_capture.py` | 4 passed; registry has 85 tools |
| `tests/test_source_subscriptions_registry.py` | 71 passed |
| `tests/test_c01_mcp_stdio.py` | 4 passed; stdio has 29 tools |
| `tests/test_phase4_stdio.py` | 9 passed |
| `tests/test_stdio_clip_tools.py` | 3 passed, 2 failed |
| `tests/test_docs_live_contracts.py` | 10 passed |
| `tests/test_current_doc_references.py` | 5 passed |
| `tests/test_dashboard_sources_api.py` | 13 passed |
| `tests/test_dashboard_sources_ui.py` | 18 passed |
| `tests/test_dashboard_v324_ui.py` | 4 passed |
| Companion suites together | 141 passed, 2 failed in 22.71 s |
| `tests/library_work_astra/test_phase5_acceptance.py` | 65 failed, 1 passed |
| `tests/library_work_astra/test_phase5_dashboard.py` | 8 failed |
| `tests/library_work_astra/test_phase5_measurements.py` | 1 failed |
| New BA tests together, final rerun | 74 failed, 1 passed in 12.84 s; no collection errors or skips |

The two companion failures are
`test_clip_tools_are_on_stdio_and_the_count_is_25` and
`test_lock_step_inventories_agree`. Both retain a 25-tool expectation; the
candidate and current MCP documentation have 29. These are stale test oracles,
not evidence that the four additional tools should be removed. Fable must
reserve that test-file repair; it is outside BA's allowed edits.

The new tests assert required behavior and intentionally fail on the candidate.
They are not xfails. The passing read-authorizer check independently confirms
that activity aggregation does not read clips, claims or engagement tables.
Source review also found no activity model, network, poller, report cache or
report-write path. The descriptive flags remain false/null as required. These
correct boundaries do not repair the failures below.

Reproducing tests for BA-01 through BA-11 and BA-13 are in
[`test_phase5_acceptance.py`](../../tests/library_work_astra/test_phase5_acceptance.py).
Names in the next table omit their common `test_phase5_` prefix. The dashboard
and measurement rows name their separate files. Each repair needs a rerun on
the resulting integrated candidate.

| Defect | Observed failure and exact repair | Reproducing tests |
|---|---|---|
| BA-01: metric provenance and evidence | `library_analysis.py:1037-1055,1345-1353,1675-1739,2059-2308`: availability/exclusion totals, shelf mutations and event totals include bare integers. Daily evidence returns both days for a one-day bucket: 2 evidence rows for count 1. A current assigned count of 1 returns 0 evidence rows. Run count 0 returns a taxonomy row. Source capture count 2 returns one subscription identity. Invented metric suffixes return success. Shelf labels never resolve through `shelf_nodes`. Build an exact registry of computed metric IDs and their supporting relations; wrap every activity number, resolve numerator and distinct denominator evidence, report evidence row/sample counts, and bind each scope to its actual population/clock. Separate retained journal operations from survivor baseline metrics and capture metrics from observation metrics. Include database schema, query/version, taxonomy/run and source-observation bindings/digests. Resolve membership/event labels by version and expose active labels separately. Unknown IDs must be `not_found`. | `all_item_counts_have_metric_provenance`; `daily_evidence_is_the_bucket_population`; `only_returned_metric_ids_are_evidence_selectors`; `current_size_evidence_identifies_members`; `run_evidence_does_not_return_taxonomy_rows`; `source_capture_evidence_identifies_each_item`; `shelf_rows_resolve_labels_from_membership_version` |
| BA-02: observed creator hints | `library_analysis.py:766-775,996-1013,2132-2156`: platform strings are lowercased, so `YouTube` and `youtube` merge. Original author whitespace and channel observations disappear from evidence. Preserve exact platform/field/value keys, trim only the display hint, retain original observations and channel breakdowns, and mark label truncation explicitly. Keep creator identity unresolved. | `creator_platform_keys_are_not_case_folded`; `original_hint_and_channel_observations_survive_in_evidence` |
| BA-03: publication precedence and attribution | `library_analysis.py:843-915,2077-2100`: a linked source row with no publication instant suppresses a valid episode fallback, giving 0 instead of 1. Selected source publication evidence points at `yoinks`, omits its source-item identity and `adapter_normalized` provenance, and hides a disagreeing lower-tier episode date. Evaluate admissible candidates in each tier; fall back only when the higher tier has no admissible instant, never on higher-tier conflict. Disclose lower-tier disagreement and preserve candidate table/key, original encoding, normalized instant and observation hash. | `publication_falls_back_when_source_tier_has_no_instant`; `publication_evidence_identifies_adapter_observation`; `lower_tier_publication_disagreement_is_disclosed` |
| BA-04: clocks, coverage and rounding | `library_analysis.py:229-250,401-430,1750-1804`: a valid plus naive capture population is labelled `retained_records`, not `partial`. Prehistory has `no_history` but still returns historical value 0 instead of null with `recorded_count:0`. Fractional source milliseconds are admitted. `1/32` becomes 3.12%, not half-up 3.13%. Use distinct stored-clock parsers, integer source milliseconds, per-family exclusions/reasons/spans, null historical values when no history exists, and exact decimal half-up rounding. Keep current sizes and explicitly dated older publications readable under their own coverage. | `unavailable_dates_make_coverage_partial`; `prehistory_is_null_with_a_recorded_zero`; `source_millisecond_clock_requires_an_integer`; `ratios_round_decimal_halves_upward` |
| BA-05: journal validation and baseline proof | `library_analysis.py:1072-1208`: replay checks shelf-ID sets but ignores primary mismatches in inverse and final current state. A receipt hash mismatch also leaves a proved denominator of 1. Malformed nested inverse maps either crash or succeed. An invalid first apply date raises `TypeError` during coverage construction. Validate both full delta structures, matching receipt bindings and sequence/revision continuity; compare full relevant survivor membership state, including primary, through inverse replay and final projection. Admit timestamps before endpoint comparisons. Invalid shape must return `invalid_source_data`; invalid dates must yield labelled exclusions and unavailable baselines while preserving valid event counts. | `baseline_proof_checks_primary_and_receipt_bindings` (three cases); `malformed_nested_deltas_return_named_error` (three cases); `invalid_apply_date_is_an_exclusion_not_an_exception` |
| BA-06: survivor/current populations | `library_analysis.py:1278-1308`: soft-deleting a filed item leaves current assigned items at 1 and memberships at 2. A deleted item's interval filing enters survivor initial-filing count as 1. Filter current membership counts through live saved IDs, and restrict initial filing to currently live survivors absent from the starting assigned population. Retain the deleted item's recorded journal event; do not invent a removal. | `soft_deleted_members_do_not_count_as_current`; `initial_filing_uses_live_survivors` |
| BA-07: source counts and observation spans | `library_analysis.py:1429-1536`: a capture linked to an older publication has capture union 1 in capture view and 0 in publication view. An unlinked hint count of 1 has no source detail row. First and last observations are both derived from a combined endpoint list, so a missing first timestamp is invented from last-seen, and vice versa. Build A5 captures on capture time independently of A1/A2 selection; return unlinked hint rows with `source_id:null`, `identity_kind:creator_hint` and retained capture spans. Compute first-observed only from admitted first-seen values and last-item-seen only from admitted last-seen values. Label current cursor coverage as the latest enumeration, separately from enrollment and historical observation evidence. | `source_capture_clock_is_independent_of_publication_selector`; `unlinked_hints_have_source_rows_and_retained_capture_span`; `observation_endpoints_do_not_substitute_for_each_other` |
| BA-08: read snapshot and generation | `library_analysis.py:308-358,374-383,550-617`: an uncommitted capture is reported successfully, the Index lock is never entered, and reopening a connection after a clip-only correction produces the identical report revision. The nonce is process-wide and both new connections restart generation counters. Use the Index locking boundary and one coherent read snapshot, refuse an inherited write transaction without committing it, and change the reader/connection nonce on connection replacement. Bind every required input and detect a generation change through packet construction without retry. | `report_does_not_inherit_uncommitted_writes`; `reads_use_index_lock`; `replaced_connection_invalidates_clip_only_corrections` |
| BA-09: strict request and adapter contract | `library_analysis.py:173,510-548,REQUIRED_TABLES`; `uoink_mcp.py:377-402`: null selectors and summary pagination reach storage, list-valued detail crashes, and 1/2/4 fractional digits are accepted. A missing episode table raises SQLite's exception. Actual stdio silently drops an unknown argument, reports a domain validation error with `isError:false`, and advertises no read-only/idempotent annotations. Enforce the frozen schema before reads, preserve omitted-versus-null distinctions, accept only zero or three interval fractional digits, include all required tables in admission, and map storage/validation errors to the specified envelopes. Make HTTP and actual `tools/call` share validation/error semantics and annotations; reject duplicate keys at the raw transport boundary. Remove stdio's implicit summary offset/limit when enforcing detail-only pagination. | `invalid_selectors_fail_before_storage` (six cases); `interval_allows_only_zero_or_three_fractional_digits`; `missing_episode_table_is_feature_unavailable`; `stdio_unknown_arguments_are_rejected_before_read`; `stdio_errors_set_is_error`; `stdio_advertises_read_only_idempotent_annotations` |
| BA-10: wire bounds, trust and continuation | `library_analysis.py:1962-2044,2059-2308`: a 70,000-character item identity produces successful oversized evidence. Actual SDK stdio serialization of a 25-item report is **86,357 bytes**, above 65,536. Hostile source text lacks Phase 4's untrusted fence. When Unicode labels trigger shedding, joint rows become empty but pagination still says 20 returned, with continuation starting at 20. Bound the complete serialized protocol response on summary, detail, evidence and error paths; refuse an unfit identity without truncating it. Use Phase 4's canonical trust renderer. After each whole-row reduction, recompute returned/omitted/other counts and continuation offsets, including `events.next`, so the removed rows remain accessible. | `evidence_wire_cap_applies_to_oversized_identity`; `actual_stdio_envelope_stays_within_wire_cap`; `stdio_model_text_has_phase4_untrusted_fence`; `shedding_updates_omitted_counts_and_continuation` |
| BA-11: bounded work and shared admission | `library_analysis.py:75-96,448-471,600-666,1074-1112,1953-1956,2037-2039`: two admitted Phase 4 reads do not block a Phase 5 read. Once a query consumes the deadline, all subsequent reads still run. All 42 decoded forward/inverse maps from 21 operations remain resident together. The journal cap is evaluated only after all raw deltas are fetched. Reuse the process-wide Phase 4 admission guard for both active and rolling limits, include lock/query/aggregation/serialization in one deadline, interrupt or bound database work, and check between bounded work units. Measure UTF-8 journal bytes before materializing them, then stream validation/replay instead of retaining all decoded history. Return bounded named errors without background work or internal retry. | `reuses_phase4_active_read_limit`; `expired_query_stops_before_subsequent_queries`; `journal_does_not_retain_every_decoded_delta` |
| BA-12: dashboard behavior | `assets/dashboard/index.html:7040-7045,7095-7137,7174,7301-7354`: all presets append `.000Z` to an already fractional ISO string; the fixed-clock result is `2026-09-08T12:00:00.123.000Z`. Stale evidence does not fetch a new summary or disable old paging. A failed refresh leaves evidence callable, historical null displays as 0, an evidence error message becomes raw HTML, and opening the modal does not transfer keyboard focus. Use `toISOString()` directly; invalidate old evidence on mutations, stale/error and refresh transitions; fetch a new summary on stale; preserve null/unavailable states; escape error data; and manage modal focus/restoration. Complete numeric evidence links and ordinary collection pagination, then exercise visible/focus/60-second refresh and hidden behavior in executable UI tests. | All eight cases in [`test_phase5_dashboard.py`](../../tests/library_work_astra/test_phase5_dashboard.py) |
| BA-13: unsupported faithfulness judgments | `library_analysis.py:2375-2516`: the evaluator gives `passed:true, score:1.0` to “2 items were saved” when items total is 1 but operations total is 2. It also passes “There are 2 elephants in the yard” and an invented medieval-pottery topic. Replace global number matching and rehearsed word blacklists with independently labelled assertion fixtures bound to metric ID, population, clock, interval and revisions. Keep general narration and model evaluation deferred; do not ship this score as a validator for arbitrary prose. Empty narration has no accuracy score. | `faithfulness_requires_assertion_support_not_number_reuse` (three cases) |
| BA-14: measurement claims | The published 548-item journal size and claimed 10k row shedding disagree with the executed fixture. Other budget claims lack measurements of their stated paths. Correct the document from captured output and measure the omitted paths described below before using it as acceptance evidence. | [`test_phase5_measurements.py::test_phase5_measurement_548_journal_matches_report`](../../tests/library_work_astra/test_phase5_measurements.py) |

The [AZ measurements document](PHASE5-AZ-MEASUREMENTS-2026-09-08.md) clearly
labels its fixtures synthetic. Its recorded raw JSON byte counts, 10k journal
bytes and Q1/Q3 index scan plans reproduce. Its historical timing values cannot
be authenticated from an earlier console log in this checkout; fresh timings
are observations of this run, not replacements silently attributed to AZ.

| Quantity | BA: synthetic 548 | BA: synthetic 10,000 | Interpretation |
|---|---:|---:|---|
| First rerun construction | 384.08 ms | 317.77 ms | Reader call as implemented, including its internal serialization |
| Extra `json.dumps` serialization | 4.13 ms | 0.52 ms | Raw dictionary serialization, not transport serialization |
| Traced Python peak | 3,546.3 KiB | 54,467.3 KiB | Different measurement passes; not process RSS |
| Raw dictionary bytes | 59,693 | 59,843 | Reproduces AZ values; both exceed the 24,576-byte dashboard target |
| Actual journal bytes, dimension audit | 74,856 (73.1015625 KiB) | 1,050,054 | AZ's 548 value of 54.8 KiB is incorrect |
| Membership rows | 822 | 10,000 | 1–2 per item at 548; exactly 1 per item at 10k |
| Source observations | 548 | 10,000 | No 100k-observation case measured |
| Applied operations | 1 | 1 | Each is a full-library apply |
| Returned event / creator / joint rows | 20 / 20 / 20 | 20 / 20 / 20 | The claimed 10k array shedding did not occur |

The dimension audit ran the original cost test with a wrapper recording fixture
counts and result rows. Both sizes return
`baseline_reason:["interval_precedes_first_apply"]`: the request starts at
midnight and the first apply is at 10:00. Thus the timed path parses deltas but
skips baseline replay. No measurement establishes the replay budget, multiple
large historical operations, three memberships per item, or the 100k-observation
case. The 10k memory pass raises the service deadline to 30 seconds and does not
assert that pass's success. The 548 timing includes tracemalloc; the main 10k
timing does not. Their relative timings are not a controlled scaling comparison.

“Combined Query Execution <15/<45 ms” is not recorded by the cited test. The
Q1/Q3 query-plan statements run only on the 548 fixture; both reported plans
match the rerun. There is no elapsed/memory measurement of the 70 MiB refusal
or of actual lock/query exhaustion. The stated SQL sum is not the implementation:
the reader fetches every delta, then counts UTF-8 bytes in Python. The claimed
concurrency/rate verification is absent from `test_activity_read_has_no_side_effects`,
which checks only `total_changes`. The deletion test changes storage between
requests; it does not verify concurrent mutation during a read. A 128 MiB process
budget is not frozen by phase5-v1, and tracemalloc does not measure total process
memory. Preserve these distinctions in the repaired measurement record.

Every supplied test name was checked against its actual assertions. “Partial”
below means that a pass proves only the described subset. The expected behavior
remains the full corresponding row in the contract's acceptance table.

| Supplied test name | Assertion audit |
|---|---|
| `test_gate1_backlog_import_vs_steady_capture` | Core fixture verified: all 205 rows, day-one capture 201/publication 1, backlog warning and capture independence flags. Publication independence flags are not all asserted. |
| `test_gate2_cross_posted_clips_not_independent_creators` | Three clips/items and hints, null creator count and unresolved support are asserted. No spy/authorizer proves the clips table unread; BA adds that passing check. |
| `test_gate3_creator_dual_channel_unmerged_hints` | Exact same-platform authors, cross-platform authors, case variants and unknown bucket counts are checked. Original hint/channel evidence and exact platform case are missed (BA-02). |
| `test_gate4_deletion_invalidates_derived_report` | Five-to-four, one tombstone, changed binding and stale creator-detail request are verified. It does not test mutation during construction or an actual evidence request. |
| `test_gate5_undo_correction_reverts_journal_and_invalidates` | Seeded 2 operations, 2 item changes, 4 mutations, net zero, endpoint sizes and 1/1 churn are asserted. The narrower interval is read only after undo; there is no before/after invalidation assertion or missing-seed case. |
| `test_gate6_single_source_interval_thin_support` | Exact links, single source, then removed links and unresolved support are checked. Unlinked hint count is checked, but required unlinked source rows/spans are absent (BA-07). |
| `test_gate7_pre_observation_interval_coverage_gap` | Incorrect oracle: requires capture total `value:0` with `no_history`; only churn is required null. Older publication remains countable, but historical-null semantics are not enforced (BA-04). |
| `test_activity_interval_half_open_utc` | Start/end counts, valid leap day, 31 buckets, reversed/future/overlong/naive rejection are checked. Fractional grammar and other malformed bounds are not checked (BA-09). |
| `test_activity_mixed_stored_clocks` | Checks capture total 4, one unavailable date and a date-only publication exclusion. Never asserts the publication total, shared normalized bucket/evidence instant, or machine-timezone/DST independence. |
| `test_activity_publication_dedup_and_conflict` | Core episode/two-link dedup, chosen-tier conflict and uncaptured exclusion verified. Empty higher tier fallback and lower-tier disagreement are missing (BA-03). |
| `test_activity_denominator_and_pagination` | Checks a 25-hint partition and the second page's denominator. No empty 0/0, unknowns, overlap, all-page traversal or post-shedding metadata assertions (BA-10). |
| `test_activity_journal_shapes_and_no_change_receipts` | Checks policy/metadata/activation counts and missing forward keys. Does not assert applied/no-change event totals or baseline continuity, exercise same-time ordering, or validate nested/inverse shapes (BA-05). |
| `test_activity_primary_only_and_initial_filing` | Checks primary event count, one initial filing and 1/1 churn. Does not assert the pair-mutation count or an empty-baseline null percentage. |
| `test_activity_history_chain_and_clock_regression` | Only seeds a clock regression. Its interval also precedes the first apply, independently forcing baseline failure. Missing receipt/revision, inverse mismatch, current-only seed, empty journal and future applies are not exercised. |
| `test_activity_deleted_journal_survivors_and_restore` | Seeds a tombstone but manually omits its current membership. Asserts one operation and one current assigned item only. No deletion transition, hard purge, restore or survivor denominator is tested (BA-06). |
| `test_activity_source_observation_windows` | Checks archived-row presence, a non-null first observation, and absence of enrollment-only activity. Does not check exact endpoints, cursor coverage/truncation or continuity wording (BA-07). |
| `test_activity_source_overlap_and_legacy_link` | Two direct links, one union and per-source counts are checked. No legacy feed/episode is seeded; no same-display-name negative join is tested. |
| `test_activity_corrections_outside_interval` | One same-connection out-of-window author update changes the hash. All other named correction types, external writes and connection replacement are missing (BA-08). |
| `test_activity_provenance_for_every_metric` | Checks only `items.total`'s ID/unit/Q1 scope and one evidence identity/hash. No recursive metric inventory, denominator reconciliation, bucket, mutation, source or revision evidence is checked (BA-01). |
| `test_activity_registry_stdio_http_parity` | Calls registry and the Python stdio wrapper, compares revision and item total. No HTTP handler or actual SDK `tools/call`, duplicate JSON keys, read-before-validation spy, or missing table/storage case (BA-09/10). |
| `test_activity_read_has_no_side_effects` | Asserts unchanged `conn.total_changes` only. Reads mtime but never compares it. No filesystem snapshot, forbidden-call spies, recovery checks or concurrency/rate assertions. |
| `test_activity_wire_budget_and_untrusted_labels` | Measures raw dictionary JSON and remaining hint lengths. Does not inspect actual envelopes, explicit truncation, evidence fences, links, controls, or continuation after reduction (BA-10). |
| `test_activity_deadline_and_work_bounds` | Checks final error codes after a fake monotonic jump and a 70 MiB payload. Does not bound elapsed refusal, query/lock interruption, subsequent work, retries or memory (BA-11). |
| `test_activity_cost_548_and_10000` | Records the raw-response paths described above. No proved replay path, error-path measurement, actual wire envelope or combined query timing; published fixture claims differ (BA-14). |
| `test_activity_dashboard_evidence_and_staleness` | Only searches HTML for identifiers/strings. Does not execute the broken presets, evidence navigation, stale refresh, visibility/focus behavior, keyboard interactions or mutations (BA-12). |
| `test_activity_whats_new_semantic_parity` | Calls a seam that delegates to the same reader and compares item/applied counts and revision; rejects integer days 0/31. No expected taxonomy/run counts, history labels, or bounded combined-event sample. Reserved prompt integration remains outstanding. |
| `test_activity_part_b_remains_deferred` | Populated claims plus two items preserve descriptive flags and omit claims/contradictions. No many-source/repeated-clip variant or forbidden-call spy. Source review and BA's authorizer support the no-content-analysis boundary. |
| `test_narration_faithfulness_metric` | Rehearsed examples pass/fail as asserted. They reward blacklist and global-number matching, without assertion-level evidence bindings. BA's unrelated entity, wrong-population count and unlisted topic all receive 1.0 (BA-13). |

Fable must reserve repairs in `library_analysis.py`, the Index read boundary,
registry/stdio adapters, dashboard, AZ fixtures/measurement document and the
stale stdio inventory tests. No migration or model work is justified by this
review. Complete the 28 contract scenarios with independent expected values,
not only comparisons between two calls to the same implementation. Measure
normal reads with proved baseline replay, bounded error/refusal paths, and actual
transport serialization. Then rerun BA on the integrated revision; the existing
passing fixtures alone cannot close these defects.

Exact reproduction commands from this worktree, in PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\61241f04-ffe\codex'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LOCALAPPDATA = Join-Path $PWD 'tests/library_work_astra/_work/phase5-ba/appdata'
$env:UOINK_OUTPUT_DIR = Join-Path $PWD 'tests/library_work_astra/_work/phase5-ba/output'
$env:TEMP = Join-Path $PWD 'tests/library_work_astra/_work/phase5-ba/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:LOCALAPPDATA,$env:UOINK_OUTPUT_DIR | Out-Null

python -m pytest -q -s -p no:cacheprovider tests/test_library_analysis_fixtures.py

python -m pytest -q -p no:cacheprovider tests/test_phase0_registry_capture.py tests/test_source_subscriptions_registry.py tests/test_c01_mcp_stdio.py tests/test_phase4_stdio.py tests/test_stdio_clip_tools.py tests/test_docs_live_contracts.py tests/test_current_doc_references.py tests/test_dashboard_sources_api.py tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py

python -m pytest -q -s -p no:cacheprovider --basetemp=tests/library_work_astra/_work/phase5-ba/final --junitxml=tests/library_work_astra/_work/phase5-ba/results.xml tests/library_work_astra/test_phase5_acceptance.py tests/library_work_astra/test_phase5_dashboard.py tests/library_work_astra/test_phase5_measurements.py --tb=short

git diff --check
git status --short
```

The JUnit file is disposable local evidence under the ignored `_work` directory.
The checked-in reproductions and commands are the portable evidence. They must
pass after the exact repairs, alongside the repaired contract fixtures and
companion suites. Do not commit or merge as part of BA.
