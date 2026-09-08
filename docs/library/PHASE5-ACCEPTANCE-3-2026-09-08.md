**PHASE 5 PART A NOT ACCEPTED**

Run BA-3, 2026-09-08. Reviewer: codex. Contract:
[phase5-v1](PHASE5-CONTRACT-2026-09-08.md). Reviewed candidate:
`235bfa640281da5c6a3ba8fb8230d0ccd024174b`, including AZ-4a `d895ff7`,
AZ-4b `9ec358b`, and integrated AZ-4c/AZ-4d `235bfa6`.

All existing acceptance tests pass. The repairs close BA-02 and preserve the
closed BA-06, but the other 12 items remain open. **62 new reproductions fail**
on required provenance, coverage, journal proof, read-boundary, transport,
dashboard and evaluation behavior. Acceptance with conditions would defer
required contract behavior, so it is not the ruling.

The full combined run returned **317 passed, 62 failed, 0 errors, 0 skips in
108.05 seconds**. The earlier rerun of the existing suites returned **317 passed
in 90.69 seconds**. These are fixture and source-review results, not an
installed-build or live-library receipt. Python was 3.14.6; Node was v24.18.0.

Only this report and three new test files were added. No implementation,
existing test, measurement document or contract was edited. No model, resident
helper, port 5179, live index, commit or merge was used. All project reads and
writes stayed in this dedicated worktree; application and temporary roots were
redirected to `_scratch/ba3`.

| Suite | Observed result |
|---|---:|
| `test_phase5_acceptance.py` | 66 passed |
| `test_phase5_dashboard.py` | 8 passed |
| `test_phase5_measurements.py` | 1 passed |
| `test_phase5_acceptance2.py` | 57 passed |
| `test_phase5_dashboard2.py` | 10 passed |
| `test_phase5_measurements2.py` | 4 passed |
| Six existing BA/BA-2 modules | **146 passed** |
| `tests/test_library_analysis_fixtures.py` | 28 passed |
| Registry: `test_phase0_registry_capture.py`, `test_source_subscriptions_registry.py` | 4 + 71 passed |
| Stdio: `test_c01_mcp_stdio.py`, `test_phase4_stdio.py`, `test_stdio_clip_tools.py` | 4 + 9 + 5 passed |
| Docs: `test_docs_live_contracts.py`, `test_current_doc_references.py` | 10 + 5 passed |
| Dashboard companions: sources API, sources UI, v324 UI | 13 + 18 + 4 passed |
| New `test_phase5_acceptance3.py` | **52 failed** |
| New `test_phase5_dashboard3.py` | **7 failed** |
| New `test_phase5_measurements3.py` | **3 failed** |

The dispatch's 145 count differs from the collected 146: BA-2 added 71 cases,
of which 70 failed and the dashboard focus/timer case already passed. The
command below includes the broader registry/stdio/docs/dashboard companion set
used in BA-2 and collects 317 existing cases; it is a larger selection than the
dispatch's reported 218.

The repair review follows [BA-2](PHASE5-ACCEPTANCE-2-2026-09-08.md). References
below use candidate line numbers. Reproduction names omit `test_phase5_ba3_`;
unless stated otherwise they live in
[`test_phase5_acceptance3.py`](../../tests/library_work_astra/test_phase5_acceptance3.py).
The tests assert required outcomes; none is an xfail.

| BA item | Disposition, evidence and exact remaining repair | New reproductions |
|---|---|---|
| BA-01: provenance and evidence | **Open.** The previously bare totals are wrapped; schema and observation digests exist; the tested tombstone predicate, selected publication group, membership-version label and source-capture key are corrected. But sample counts are attached only to `items.total` (`library_analysis.py:1662`); item shares lack denominator descriptors. Source-state metric IDs are advertised but return `not_found`. Per-shelf evidence checks operation-wide additions and referenced shelves, so Beta's zero additions can return Alpha's addition, and zero churn can return a metadata-only operation (`3408`). Journal evidence has headers without item identities or thin before/after changes (`3480`); deleted operations lack `item_deleted`. A historical Alpha start member is attributed to a nonexistent current `item_shelves` row. Tombstone metrics use a live-item scope (`1745`); combined events use the selected item clock/population (`2243`). A channel-only correction leaves the selected observation hash unchanged (`3020`). **Repair:** use one metric-to-support relation registry for every metric and denominator, with exact support/sample counts and per-metric scopes. Return canonical hashes over the supporting observations, retained journal identities and thin changes, deletion status, and replay support for historical endpoints. | `every_metric_reports_evidence_population` (5); `item_shares_have_distinct_denominator_evidence` (3); `source_state_metric_has_exact_evidence`; `zero_shelf_metric_has_no_unrelated_support` (2); `journal_evidence_contains_reconcilable_item_changes`; `deleted_journal_evidence_marks_identity`; `baseline_evidence_binds_retained_journal_support`; `deleted_metric_scope_is_tombstones`; `combined_event_scope_includes_journal_clock`; `channel_correction_changes_selected_observation_hash` |
| BA-02: creator hints | **Closed.** `_creator_hint_key` now groups by platform, field and trimmed value; whitespace-only author falls through to channel. Original strings remain in evidence; case/platform distinctions remain; displayed hint truncation is explicit. The BA-2 and original hint cases pass. These remain observed hints, without creator identity or independence claims. | Existing trimmed-hint, case, platform and truncation cases |
| BA-03: publication selection | **Open.** Tier precedence, fallback, normalized deduplication and conflict candidates are retained; selected total/group/bucket evidence uses the source relation. Availability evidence still uses `yoinks` and a hash of `{v,pub:true}` (`3148`), even when its instant comes from `source_items`. **Repair:** reuse the admitted candidate relation for publication availability as well as selected totals/groups/buckets; preserve source key, encoding, normalized instant, provenance and canonical observation hash. | `publication_availability_uses_candidate_relation` |
| BA-04: clocks and coverage | **Open.** Native decimal-text apply/version/run timestamps now count. Historical-null propagation covers item total, daily count and journal counts, but type counts, revision counts, event total and source-capture union still report zero before their retained history. Invalid revision dates are omitted while coverage says `retained_records` (`2130,2427`). An unproved initial-filing count is still zero (`1914`). **Repair:** apply coverage-aware nulls and recorded counts to every historical metric, track invalid clock exclusions and spans by the actual family, and keep initial filing unknown until its baseline is proved. Preserve valid current sizes and dated publication counts. | `no_history_is_null_across_remaining_metrics` (5); `invalid_revision_clock_marks_partial_coverage`; `initial_filing_is_unknown_without_baseline` |
| BA-05: journal proof | **Open.** No-change receipt gaps now work; request-hash and missing-inverse checks pass the old cases. `_validate_delta_structure` still accepts list confidence/assigned time, numeric source, object `evidence_json`, null version ID, and list-valued `exclusive_move` (`354`). Any nonempty receipt status other than no-change qualifies, including `failed` and `invented` (`1128`). Replay compares shelf IDs and primary flags only; mismatched inverse confidence still produces `journal_complete` and a denominator (`1189,1312`). **Repair:** validate complete service-emitted typed membership/policy rows, allowed successful receipt status and forward/inverse correspondence; compare the full relevant before state and final projection before proving history. Preserve independently valid recorded event counts when proof fails. Update abbreviated synthetic deltas to the real schema; do not relax validation to keep those fixtures green. | `typed_membership_fields_are_validated` (5); `nested_policy_fields_are_validated`; `apply_requires_successful_receipt_status` (2); `inverse_metadata_must_match_replayed_state` |
| BA-06: current sizes/live survivors | **Closed, unchanged.** Current memberships and initial-filing candidates exclude deleted/missing items; recorded operations survive deletion. Original soft-delete and initial-filing checks and the supplied survivor/restore scenario pass. Initial-filing availability and evidence remain BA-04/01 issues. | Existing survivor/current-size cases |
| BA-07: sources and windows | **Open in coverage only.** Support now follows selected A1/A2 items while A5 captures stay on capture time; cursor coverage says “latest enumeration at as_of.” But a source whose observations begin after the interval has a null count bound to another source's global `retained_records` coverage (`2015,2298,2457`). **Repair:** bind each source's observation metric to its own interval status, retained span and exclusions. Keep cursor enumeration separate and preserve the corrected support population. | `source_metric_has_its_own_history_status` |
| BA-08: read boundary | **Open.** Explicit `BEGIN DEFERRED` now gives coherent input reads under the Index lock; inherited writes remain uncommitted and refused. `Index.read_snapshot` exists (`index.py:525`), but the activity path implements its transaction directly. Its final generation check occurs before rollback (`library_analysis.py:2898,2920`). An external WAL writer commits an author correction during serialization; the reader returns success with the old author because `PRAGMA data_version` remains the snapshot's value. **Repair:** finish the snapshot, then revalidate generation while retaining the Index boundary through the decision to return; return `stale_report` on a changed generation, without retry. Use the shared boundary consistently. | `wal_commit_during_construction_is_detected` |
| BA-09: validation/adapters | **Open.** Extra interval fields and raw stdio duplicate keys are rejected, advertised stdio schema matches the registry, and closed storage has a Phase 5 envelope. However, `$`-anchored interval matching admits a trailing newline and reaches storage (`304`). Storage/deadline paths override the frozen retry policy with `retryable:false` (`827,832` and adapter deadline paths). **Repair:** require whole-string grammar before storage and apply the contract's retryable storage/rate/deadline/recovery mapping consistently through both adapters. `uoink_mcp_tools.py` remains the thin shared registry delegation; the stdio interception has its separate serialization path. | `interval_rejects_trailing_newline_before_storage` (2); `retryable_errors_retain_contract_semantics` (2) |
| BA-10: response bounds/trust | **Open.** Normal 25-item and both large measured stdio summaries now succeed within the cap; summary row shedding follows the required order. Details still refuse the entire page without dropping rows (`2760`): 20 ordinary long-author rows fail although a one-row request succeeds. A 600-byte item ID that fits the packet is rejected by an extra 512-byte identity limit (`2753`); only metric IDs have that contract limit. Shelf labels exceed 120 characters, and truncated subscription display names have no flag (`1878,2013`). **Repair:** budget and reduce whole detail rows with usable continuation; reject an identity only when it cannot fit mandatory output; preserve IDs and bound/mark every display label. Retain the untrusted text fence. | `detail_page_sheds_whole_rows_before_refusal`; `single_fitting_identity_is_preserved`; `all_display_labels_are_bounded_and_explicit` (2) |
| BA-11: bounded work | **Open.** Timed Index lock acquisition, SQLite busy/progress handling and the old render-deadline probe pass. The reader releases shared admission before adapter rendering (`672`); observed active counts are `[1,0]`. A three-second clock advance during the adapter's final `wire_bytes` call still returns success (`uoink_mcp.py:712`). The read also overwrites shared `busy_timeout` without restoring it (`857,2914`). **Repair:** carry one admission/deadline through final protocol serialization and check after it; restore temporary connection settings on every exit. Keep bounded lock/query behavior and the 64 MiB pre-materialization check. | `stdio_holds_admission_through_final_render`; `final_wire_serialization_is_inside_deadline`; `read_restores_shared_connection_busy_timeout` |
| BA-12: dashboard | **Open.** Original refresh/invalidation races, loading refusal, collection forward continuation, metric links and focus trap now pass. Evidence paging still adds 20 instead of using the returned offset five (`7926`). Overlapping pages of the same metric/collection let the older reply win; obsolete replies disable a newer pager, and obsolete rejected requests overwrite current evidence (`7673,7709,7735`). Displayed exclusions have no evidence links; publication view displays capture unavailability instead of seven unavailable publication dates (`7408`). **Repair:** give each page request a sequence token and ignore every obsolete success/error without UI mutation; use complete returned continuations for evidence and collections; bind all displayed exclusions to the selected clock and their evidence. | All seven cases in [`test_phase5_dashboard3.py`](../../tests/library_work_astra/test_phase5_dashboard3.py) |
| BA-13: faithfulness | **Open.** Arbitrary/unlabelled prose is now unscored, and appended prose, interval/revision/top-level basis counterexamples fail. The evaluator still lives in production and maps exact normalized prose to hard-coded assertions (`3974`). “Population” validation checks only that a family exists; it ignores each metric ID/scope/clock (`4084`). Wrong metric IDs, tombstone populations and publication-clock operations still score 1.0. Missing shelves satisfies `all([])`, and the recognized pin/move/undo paragraph scores 1.0 with two metadata-only applies and no supporting operation evidence. **Repair:** move explicit independently labelled assertions to a static evaluation harness; resolve each assertion to its actual metric, population, clock, interval, revisions and evidence, including each pin/direction/undo claim. Keep arbitrary narration deferred and unscored. | `labelled_assertions_require_actual_metric_bindings` (4); `labelled_pin_and_undo_assertions_need_operation_evidence` |
| BA-14: measurements | **Open.** Raw and actual stdio byte counts now reproduce, normal adapters succeed, and the ten-operation fixture is seeded from empty and requires proof. The document still says no row shedding, skipped replay, and actual-adapter timing for a hand-built serialization block. Those claims contradict captured output/source. The wider error-path memory and complete transport/admission measurements remain incomplete. **Repair:** regenerate the record from final full-reader/actual-adapter observations, replace the three false path descriptions, and distinguish measured limits from unmeasured coverage. Include the remaining budget paths after BA-10/11 repairs. | All three cases in [`test_phase5_measurements3.py`](../../tests/library_work_astra/test_phase5_measurements3.py) |

The existing tests were not weakened by editing their assertions: the six
BA/BA-2 files have no diff between `b53e62a` and the reviewed candidate. The
supplied fixture changes correctly seed the first multi-operation inverse as
empty, align its times, and add `journal_complete`/empty-reasons assertions.
The narration fixture also adds the hard-coded `a…a` revision expected by the
evaluator. That makes its binding present; it does not establish independent
assertion evaluation.

Green results still establish narrower behavior than several gate names imply.
BA-2's sample-count case inspects only `items.total`; its denominator case only
global churn. The source-state case checks a metric wrapper, not its evidence
page. Historical endpoint evidence only had to contain a row. Shape tests
covered three nested bad values, and receipt status tested only `no_change`.
The snapshot case checks `in_transaction`, without a concurrent WAL commit.
The deadline case slows text rendering, not the final wire serializer or guard
lifetime. Dashboard continuation tested collections, not evidence; its races
did not overlap two pages of the same metric. The evaluator tests damage
top-level fields, not the bound metric scopes or each assertion in the prose.
The new tests exercise these specific gaps rather than infer completeness from
the old pass count.

The no-content-analysis boundary remains intact in the reviewed report path:
no claims/clips/engagement query, model/network invocation, source-text walk,
report cache or report write was added. Descriptive flags remain false/null as
required. The existing authorizer/side-effect tests pass within their stated
scope. This does not establish the correctness of the separately callable
faithfulness evaluator or eliminate the shared-connection timeout side effect.

Fresh BA-3 measurements below come from the **last, standalone supplied
benchmark block in the combined run**. Its reader-only timings are separate
from the instrumented dimension/adapter audit. They are BA-3 observations, not
retroactive authentication of AZ's timings.

| Quantity/path | BA-3 observation | Interpretation |
|---|---:|---|
| 548 construction / extra raw serialization | 698.16 ms / 3.07 ms | Construction includes internal serialization and tracemalloc overhead. |
| 548 traced Python peak / raw JSON | 3,939.2 KiB / 59,281 bytes | Python heap, not RSS; raw bytes are not protocol bytes. |
| 10,000 construction / extra raw serialization | 411.51 ms / 0.35 ms | Main timing is untraced. |
| 10,000 traced Python peak / raw JSON | 61,180.9 KiB / 59,190 bytes | Heap comes from the separate relaxed-deadline tracing pass. |
| Proved 548 baseline | 39.91 ms | `journal_complete`, empty reasons. |
| 73,400,398-byte journal refusal | 51.01 ms | `resource_too_large`; 221-byte raw envelope. |
| Injected expired clock | 0.09 ms | `deadline_exceeded`; 191-byte raw envelope, actually `retryable:false`. This is not a blocked-lock/query measurement. |
| Hand-built transport serialization | 0.47 ms / 65,263 bytes | The supplied benchmark's Part 5 constructs its own JSON/text envelope; it does not invoke the stdio handler. |
| 548 items / 1,644 memberships | 48.33 ms | Successful reader; primary interval baseline remains unavailable. |
| 50 items / 10 operations | 4.47 ms | Successful, proved replay; 76,890 journal bytes. |
| One item / 100,000 observations | 921.16 ms | Successful observation scan; separate dimension case, no journal. |

The actual shipped stdio handler audit independently reproduces these sizes:

| Fixture | Journal bytes | Actual stdio result | Retained summary rows: events / creators / joint / sources / shelves |
|---|---:|---:|---|
| 548 primary: 822 memberships, 548 observations | 74,856 | Success, 65,252 bytes | 0 / 20 / 16 / 1 / 2 |
| 10,000 primary: 10,000 memberships and observations | 1,050,054 | Success, 65,095 bytes | 0 / 20 / 17 / 1 / 1 |
| 548 proved interval | 74,856 | Success, 65,131 bytes | 0 / 20 / 15 / 1 / 2 |
| 548 / three memberships each | 123,902 | Success, 64,735 bytes | 0 / 20 / 14 / 1 / 3 |
| 50 / ten operations | 76,890 | Success, 35,404 bytes | 20 / 1 / 1 / 1 / 2 |
| One / 100,000 observations | 0 | Success, 27,862 bytes | 1 / 1 / 1 / 2 / 0 |

These actual-wire measurements serialize
`JSONRPCResponse.model_dump_json(by_alias=True, exclude_none=True)` with request
ID 1, excluding the terminating newline. The audit feeds captured reader
packets through the shipped handler to isolate transport behavior; it does not
time a second complete read. The 25-item stdio acceptance case does invoke the
full reader. Both primary fixtures shed all 20 event rows and some joint rows.
Both attempt replay before rejecting baseline proof because their interval
starts before the first apply. The measurement document's contrary statements
remain false. The separate BA-3 replay probe observes populated replay state
before that early-interval refusal.

Q1 and Q3 plans reproduce `SCAN yoinks USING INDEX sqlite_autoindex_yoinks_1`
and `SCAN library_applies USING INDEX sqlite_autoindex_library_applies_3`.
The benchmark obtains those plans on the 548 fixture, not both scales as the
table implies. No isolated query timing is recorded. No new peak-memory
measurement covers the dense-membership, extended replay, 100k-observation or
refusal paths. The main scales and 100k-observation case are separate fixtures;
they do not demonstrate a combined 10k-item/100k-observation/full-journal case.
The 24,576-byte dashboard target is missed and is explicitly a target, not an
acceptance-blocking hard limit by itself.

The measurement tests were tightened after the combined run so that a future
genuine no-shedding implementation can satisfy a no-shedding claim, and the
replay claim is checked against observed replay state. Their separate rerun is
**3 failed, 0 errors in 18.63 seconds**, recorded in
`_scratch/ba3/measurement-check.txt` and its JUnit receipt. These test-only
refinements do not change the 62 demonstrated defects.

Exact commands for Fable, in PowerShell from this worktree:

```powershell
Set-Location -LiteralPath 'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\af84712a-348\codex'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LOCALAPPDATA = Join-Path $PWD '_scratch/ba3/appdata'
$env:UOINK_OUTPUT_DIR = Join-Path $PWD '_scratch/ba3/output'
$env:TEMP = Join-Path $PWD '_scratch/ba3/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:LOCALAPPDATA,$env:UOINK_OUTPUT_DIR | Out-Null

python -m pytest -q -s -p no:cacheprovider --tb=short --basetemp=_scratch/ba3/recheck --junitxml=_scratch/ba3/recheck.xml tests/library_work_astra/test_phase5_acceptance.py tests/library_work_astra/test_phase5_dashboard.py tests/library_work_astra/test_phase5_measurements.py tests/library_work_astra/test_phase5_acceptance2.py tests/library_work_astra/test_phase5_dashboard2.py tests/library_work_astra/test_phase5_measurements2.py tests/library_work_astra/test_phase5_acceptance3.py tests/library_work_astra/test_phase5_dashboard3.py tests/library_work_astra/test_phase5_measurements3.py tests/test_library_analysis_fixtures.py tests/test_phase0_registry_capture.py tests/test_source_subscriptions_registry.py tests/test_c01_mcp_stdio.py tests/test_phase4_stdio.py tests/test_stdio_clip_tools.py tests/test_docs_live_contracts.py tests/test_current_doc_references.py tests/test_dashboard_sources_api.py tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py

git diff --check
git status --short
```

The recorded combined command used `--basetemp=_scratch/ba3/final`,
`--junitxml=_scratch/ba3/final.xml`, and captured stdout/stderr in
`_scratch/ba3/final.txt`. The original-suite receipt is `baseline.txt/xml`.
Scratch receipts are ignored local artifacts; the portable evidence is this
report and the three new test files. The combined invocation runs the supplied
benchmark four times through separate test modules; keep those timing blocks
distinct. Reproductions use migrated disposable databases, fixed clocks, the
actual registry/stdio seams, a real external WAL connection, and shipped
dashboard JavaScript executed in Node with a DOM/transport double.

Handoff: **BA-3 review complete; Part A not accepted.** Integrate repairs for
BA-01, BA-03/04/05, and BA-07 through BA-14, then rerun the command above. Files
changed: this report and `test_phase5_acceptance3.py`,
`test_phase5_dashboard3.py`, `test_phase5_measurements3.py`. Evidence: 317
existing passes and 62 new failing reproductions. No open scope questions;
changes remain uncommitted.
