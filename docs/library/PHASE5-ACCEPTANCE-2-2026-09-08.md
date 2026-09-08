**PHASE 5 PART A NOT ACCEPTED**

Run BA-2, 2026-09-08. Reviewer: codex. Contract:
[phase5-v1](PHASE5-CONTRACT-2026-09-08.md). Integrated candidate:
`87e5fb654a78c57d8ee179c1e5752195cdc4fbe6`, including repairs `7e68878`,
`e45bc77`, `9b6f7c6`, `87e5fb6` and dashboard repair `21d52ab`.

The original 75 BA tests and all 28 supplied fixtures pass. The repairs close
specific counterexamples but leave release blockers in provenance, stored
clocks, journal proof, transport behavior, bounded work, dashboard state and
evaluation. BA-06 is closed. The other BA items remain open as detailed below.
Acceptance with conditions would defer required behavior, so it is not the ruling.

The final combined run produced **247 passed, 70 failed, 0 errors, 0 skips in
65.17 seconds**. All 70 failures are newly added BA-2 counterexamples. They assert
required behavior and are not xfails. The original BA test files are unchanged
across the repair commits. No implementation file was changed in this review.

Review used this dedicated worktree, disposable databases migrated through 0028,
a fixed UTC clock, the actual registered MCP handlers and SDK raw stdio decoder,
and shipped dashboard JavaScript executed in Node with a DOM/transport double.
No model, resident helper, port 5179, live index, commit or merge was used. These
are source and fixture results, not an installed-build or live-library receipt.
Runtime versions were Python 3.14.6 and Node v24.18.0.

| Suite | Independently observed result |
|---|---:|
| `tests/library_work_astra/test_phase5_acceptance.py` | 66 passed |
| `tests/library_work_astra/test_phase5_dashboard.py` | 8 passed |
| `tests/library_work_astra/test_phase5_measurements.py` | 1 passed |
| Original BA suites together | 75 passed; separate run 15.54 s |
| `tests/test_library_analysis_fixtures.py` | 28 passed; separate run 13.77 s |
| `tests/test_phase0_registry_capture.py` | 4 passed |
| `tests/test_source_subscriptions_registry.py` | 71 passed |
| `tests/test_c01_mcp_stdio.py` | 4 passed |
| `tests/test_phase4_stdio.py` | 9 passed |
| `tests/test_stdio_clip_tools.py` | 5 passed |
| `tests/test_docs_live_contracts.py` | 10 passed |
| `tests/test_current_doc_references.py` | 5 passed |
| `tests/test_dashboard_sources_api.py` | 13 passed |
| `tests/test_dashboard_sources_ui.py` | 18 passed |
| `tests/test_dashboard_v324_ui.py` | 4 passed |
| Registry/stdio/docs/dashboard companions together | 143 passed; separate run 15.84 s |
| New `test_phase5_acceptance2.py` | 57 failed |
| New `test_phase5_dashboard2.py` | 9 failed, 1 passed |
| New `test_phase5_measurements2.py` | 4 failed |
| Final combined run | 70 failed, 247 passed; 317 collected |

An initial invocation without a local `--basetemp` hit a permissions error in
pytest's default temporary directory: 18 passed and 57 setup errors. That was a
harness setup failure, not a product result. The completed runs above use local
temporary directories; the final run also redirects application/output roots.

The repair review follows the original [BA ruling](PHASE5-ACCEPTANCE-2026-09-08.md).
Line references below refer to the integrated candidate. Reproduction names omit
the prefix `test_phase5_ba2_`; they are in
[`test_phase5_acceptance2.py`](../../tests/library_work_astra/test_phase5_acceptance2.py)
unless another file is named.

| BA item | Repair disposition and remaining required behavior | Reproductions |
|---|---|---|
| BA-01 — provenance and evidence: **open** | The seven item totals now have metric wrappers; daily evidence filters its bucket, invented selectors fail, current assigned evidence identifies members, and run evidence no longer returns taxonomy rows. But `library_analysis.py:1456,1559-1561,1703,1922` still emits bare publication-reason, per-shelf mutation, source-state and event totals. Scopes at `1939-1998` label source captures as observation time and recorded journal operations as live survivors. There is no input database schema binding, taxonomy/run digest, source-observation digest, denominator evidence descriptor, or per-metric support/sample count. `2679-2718` returns all tombstones on the deletion clock for capture exclusions and drops naive unlocated captures. `2929-2968` returns interval applies for unrelated metrics: zero metadata events has one support row; a proved start size of one has no support. Source capture evidence names `source_items` but gives a video ID that is not its key. Hashes omit observed author changes and use a different serializer from Phase 4. Shelf labels at `1518-1565` prefer the active version rather than the membership's version. **Repair:** finish the metric-to-relation registry, wrap every activity count, provide distinct denominator and exact supporting observations, canonical observation hashes and complete bindings; resolve labels by version and expose active labels separately. | `remaining_activity_counts_are_metrics` (6); `ratio_denominator_has_addressable_evidence`; `provenance_binds_schema_and_observation_digests`; `metric_evidence_reports_population_and_sample_counts`; `source_capture_scope_uses_capture_clock` (2); `journal_scope_includes_deleted_recorded_items`; `zero_metadata_events_have_no_support_rows`; `start_size_evidence_contains_baseline_support`; `tombstone_evidence_filters_capture_interval`; `unlocated_evidence_includes_naive_capture`; `membership_label_uses_its_version`; `source_capture_evidence_keys_resolve_to_reported_table`; `observation_hash_changes_with_observed_author`; `evidence_uses_phase4_canonical_hash` |
| BA-02 — creator hints: **open** | Case folding is removed and original author/channel strings survive item evidence. However, `1349-1418` groups by the untrimmed value: `"  Same Author  "` and `"Same Author"` produce two visually identical rows. Whitespace-only author blocks a valid channel fallback. Display truncation has no explicit flag. **Repair:** use the frozen `(platform, field, trimmed-value)` grouping key, choose a nonempty trimmed author before channel, preserve originals and channel breakdowns, and mark display truncation. The first review's phrase “trim only the display hint” was imprecise; the frozen contract explicitly requires a trimmed grouping value and remains authoritative. | `trimmed_hint_keys_group_without_losing_originals` (2); `hint_truncation_is_explicit` |
| BA-03 — publication selection: **open** | Higher-tier missing dates now fall back, valid higher-tier dates win, and total evidence discloses one lower-tier disagreement. Group evidence at `2721-2857` still attributes selected source publication observations to `yoinks`. Conflict evidence at `2670-2688` omits the conflicting source-item identities and candidate instants. **Repair:** reuse the admitted publication candidate relation for total, availability, exclusion, group and bucket evidence, retaining table/key, encoding, normalized time, provenance and canonical hash for selected/conflicting observations. Preserve the repaired precedence and deduplication rules. | `publication_group_evidence_preserves_source_attribution`; `publication_conflict_evidence_retains_candidates` |
| BA-04 — clocks and coverage: **open** | Decimal half-up rounding, fractional-millisecond rejection, mixed valid/naive capture coverage and the top-level prehistory total are repaired. But `922-926` admits epoch creation dates only if already numeric; SQLite stores `LibraryWorkService._stamp()` output as decimal **text**. An in-window native apply therefore counts zero. Revision counts/evidence at `1792-1803,1850-1875,3117-3148` accept neither ISO nor epoch text, so a real creation row also counts zero. Only `items.total` is changed to historical null at `2047-2049`; daily, journal and source observation metrics still report zero before history. Source/revision coverage lacks meaningful spans and exclusions. **Repair:** separate native creation-clock admission from integer source milliseconds, use it consistently in counts/events/evidence, and apply per-family availability, spans, reasons and null historical metrics throughout. | `native_epoch_text_apply_counts`; `revision_creation_clocks_count` (4); `prehistory_is_null_in_every_historical_metric` (3) |
| BA-05 — journal proof: **open** | Primary mismatches and authoritative receipt-hash mismatches now prevent proof; the three original malformed containers return errors; invalid first dates no longer crash coverage. Yet `904` requires apply sequence `idx+1`, rejecting a valid no-change receipt gap. `_validate_delta_structure` at `310-326` admits scalar policies and invalid primary values; a list-valued shelf ID raises `TypeError`. Receipt reads omit request hashes and receipt status; absent inverse item keys can still produce a proved baseline. **Repair:** validate complete typed forward/inverse structures and their correspondence, all relevant receipt bindings/status, contiguous receipts and projection revisions; permit apply gaps accounted for by no-change receipts. Retain valid recorded counts when proof fails. | `no_change_receipt_gap_keeps_proved_baseline`; `invalid_nested_values_return_named_error` (3); `baseline_requires_full_receipt_and_inverse_binding` (3) |
| BA-06 — live survivors/current sizes: **closed** | `1475-1506` filters current memberships and initial filing through live survivors. The original soft-deletion and initial-filing tests pass, as do supplied deleted-survivor/restore scenarios. Deleted recorded operations remain counted; no removal is fabricated. Baseline availability and the scope/evidence labels remain separate open issues under BA-01/04/05. | Original `soft_deleted_members_do_not_count_as_current`, `initial_filing_uses_live_survivors`; supplied `test_activity_deleted_journal_survivors_and_restore` |
| BA-07 — source populations/windows: **open** | A5 captures now stay on capture time; unlinked hint rows and separate first/last observation endpoints are present. But `1768-1774` also moves **support_level** to the capture population. A publication report with zero selected items says `single_source`. Cursor coverage remains an unqualified `complete` value with no “latest enumeration at as_of” binding. **Repair:** keep A5 on capture time while deriving descriptive support from the A1/A2 selected population; label cursor coverage separately from interval observation history and retain per-source coverage/exclusions. | `publication_support_uses_selected_items`; `cursor_is_labelled_latest_enumeration` |
| BA-08 — read boundary: **open** | Index `_lock` is entered, inherited transactions are refused without committing, and connection replacement changes the nonce. `index.py` has no Phase 5 snapshot helper; `library_analysis.py:662-689` performs separate autocommit SELECTs, with no `BEGIN`/snapshot. Trace records `in_transaction=False` during the first input read. Generation comparison catches many mutations after construction but does not create the required coherent input snapshot. **Repair:** hold the existing Index boundary and one explicit read transaction across input collection/construction and check generation before return; preserve refusal of inherited writes and connection invalidation. Avoid retaining report data for reuse. | `reads_hold_sqlite_snapshot`; original generation and Index-lock cases remain green |
| BA-09 — validation/adapters: **open** | The intercepted stdio call preserves top-level arguments; null/detail/fractional grammar checks, required episode-table admission, `isError` and annotations now pass. But extra **interval** fields reach storage. The actual SDK stdio decoder accepts duplicate `date_basis` keys and reaches the reader; HTTP's strict decoder is not shared by that path. `tools/list` still exposes FastMCP's permissive interval object and nullable selectors rather than the registry schema. A closed connection raises `sqlite3.ProgrammingError`; inherited writes return non-contract `invalid_state`. **Repair:** validate the entire request before reads, reject duplicates at both raw boundaries, advertise the same schema, and convert storage/refusal paths into frozen Phase 5 envelopes. | `unknown_interval_field_rejected_before_storage`; `raw_stdio_duplicate_keys_rejected_before_read`; `stdio_schema_matches_registry`; `storage_exception_has_named_envelope`; `transaction_refusal_uses_frozen_error_code` |
| BA-10 — response bounds/trust: **open** | The real stdio success path now uses Phase 4's trust fence and emits bounded output. Raw summary shedding updates continuation counts correctly. However, `uoink_mcp.py:662-679` replaces a normal 25-item result with `resource_too_large`, using a **Phase 4** error envelope. Both measured large fixtures do the same. The old wire test passes because it never requires success. The aggregator bounds only raw dictionary JSON; protocol expansion is handled by refusal instead of continued whole-row reduction. At `2320-2330`, every string in evidence `details` is treated as an identity, making an ordinary 600-character author inaccessible. **Repair:** budget the complete transport result, shed whole optional rows with usable continuation before refusing mandatory content, preserve Phase 5 envelopes, and distinguish stable IDs from display/source text. | `small_normal_stdio_summary_succeeds`; `long_label_evidence_remains_accessible`; measurement stdio cases |
| BA-11 — bounded work: **open** | Shared Phase 4 admission is used. Journal UTF-8 bytes are summed in SQLite before delta materialization, and decoded history is streamed instead of retained wholesale. Deadline checks stop after the original delayed Q1 case. But lock entry is unbounded; no SQLite progress/deadline or busy-wait budget is installed. With a 50 ms test budget, an Index lock blocks for about 352 ms and SQLite for about 370 ms, then returns deadline failure. Stdio serialization after the reader's guard/deadline can consume an injected extra three seconds and still return success. **Repair:** use one remaining-time budget for lock acquisition, SQLite execution/busy waits, bounded aggregation units and final protocol serialization, while holding shared admission through the last step. No detached work or automatic retry. | `lock_wait_obeys_deadline`; `sqlite_busy_wait_obeys_deadline`; `stdio_serialization_is_inside_deadline` |
| BA-12 — dashboard: **open** | Presets, error escaping, basic focus transfer, null total rendering, failed-refresh invalidation and stale-summary refresh pass the original eight cases. The new executable focus/60-second/hidden test also passes. But `activityEvidenceCallable` ignores loading; late evidence can repopulate invalidated state and re-enable paging; an older summary can overwrite a newer one. Pagers increment by 20 even when the server returns only five rows with next offset five. Shares, shelf endpoints and shelf churn lack evidence links. The modal focus trap ignores rendered item buttons. **Repair:** bind responses to the active request/revision generation, disable access during refresh, discard obsolete replies, follow returned continuations, connect all displayed metrics and derive the focus trap from actual enabled modal descendants. | All cases in [`test_phase5_dashboard2.py`](../../tests/library_work_astra/test_phase5_dashboard2.py); 9 fail, 1 passes |
| BA-13 — faithfulness: **open** | Empty narration now has no score, and the three original adversarial strings fail. But `_match_labelled_fixture` at `3397-3424` selects expected assertions through phrase matching, including those exact adversarial strings. The success branch checks a few values while ignoring fixture population/clock/interval/revisions and the rest of the prose. Appending “The moon consists of cheese and 9000 creators agree” to a recognized sentence returns `passed:true, score:1.0`. Wrong interval, missing revision and wrong clock also pass. A general token/word evaluator remains at `3503-3630`. **Repair:** move static labelled examples to an explicit independent assertion-evaluation harness, validate all required bindings and every assertion, and leave arbitrary narration unscored/deferred. Do not present phrase recognition as faithfulness validation. | `labelled_prose_cannot_bypass_assertion_binding` (4) |
| BA-14 — measurements: **open** | The 548 journal correction reproduces and extra scenarios now run. The main payload table is stale, its “wire” values are raw JSON, the hand-built transport bypasses the actual adapter and exceeds the wire cap, and the ten-operation case fails baseline proof. Several older verification claims remain unsupported. **Repair:** replace the record from captured final-reader/actual-transport observations; correct fixture/serialization labels, seed a valid multi-operation baseline, and measure/assert the omitted resource paths described below. | All four cases in [`test_phase5_measurements2.py`](../../tests/library_work_astra/test_phase5_measurements2.py) |

The no-content-analysis boundary remains intact in the inspected reader: no
claims/clips/engagement read, model call, source fetch, report cache or report
write was added. The original authorizer check passes. Descriptive flags remain
false/null. That does not validate the separately callable prose evaluator.

The green tests do not establish broader gates. The supplied provenance test
checks only `items.total`; the parity test calls the Python convenience wrapper
rather than actual `tools/call`; the dashboard test searches for source strings.
The journal-shape fixture contains a no-change gap but never requires its
baseline to be proved. The revision evidence regression uses an empty run
population. The old malformed-shape cases exercise containers, not their typed
contents. The wire assertion allows an error response; the benchmark checks raw
JSON size without asserting the real adapter's success. The faithfulness cases
are recognized directly by production phrase checks. These are concrete reasons
the 103 original Phase 5 passes coexist with the new failures, without alleging
intent by the implementer.

The supplied fixture changes were also inspected: the prehistory expectation
was correctly strengthened from zero to null plus `recorded_count:0`, admission
reset was added, benchmark scenarios were appended, and more evaluator examples
were added. Those changes do not repair the gaps above. The first BA report's
detailed assertion audit remains relevant where the supplied assertions are
unchanged.

The [AZ measurement document](PHASE5-AZ-MEASUREMENTS-2026-09-08.md) is explicitly
synthetic. Fresh, unwrapped benchmark output from the **last benchmark block of
the final combined run** is reproduced below. These timings are BA-2 observations;
they do not authenticate or replace AZ's earlier timings under AZ's name.

| Quantity/path | BA-2 captured value | Meaning |
|---|---:|---|
| 548 construction / extra raw serialization | 411.30 ms / 3.55 ms | Construction includes the reader's internal raw serialization; tracing is enabled here. |
| 548 traced Python peak / raw JSON | 3,641.7 KiB / 61,341 bytes | The main document still says 59,693 bytes. This is not protocol size. |
| 10,000 construction / extra raw serialization | 319.61 ms / 0.43 ms | Main timing has tracing disabled. |
| 10,000 traced Python peak / raw JSON | 56,626.1 KiB / 61,383 bytes | Peak is from a separate pass with a 30-second deadline; the supplied test does not assert that pass's success. The main document says 59,843 bytes. |
| Separate proved 548 baseline | 17.94 ms | `journal_complete`, no reasons, interval begins at the first apply. |
| Over-budget journal refusal | 55.53 ms | `resource_too_large`; actual deltas total 73,400,398 bytes. Raw error is 221 bytes. |
| Injected deadline refusal | 0.76 ms | `deadline_exceeded`; raw error is 166 bytes. This is clock injection, not a blocked-lock/query measurement. |
| Benchmark's hand-built transport | 0.48 ms / 67,697 bytes | Reproduces the document's byte count but exceeds 65,536. It uses its own JSON/text envelope, bypassing the shipped adapter. |
| 548 items / three memberships each | 55.01 ms | 1,644 memberships; baseline unavailable for the chosen primary interval. |
| 50 items / ten operations | 4.03 ms | `ok:true`, **partial**, `mismatched_inverse_projection`; not successful baseline replay. |
| 100,000 observations / one saved item | 643.49 ms | Reader succeeds; zero journal operations. This is a separate dimension case. |

An instrumented audit of the same fixtures records the dimensions and passes
the captured reader packets through the actual shipped stdio handler. Its timing
includes audit overhead, so it is not used as reader-only timing above.

| Fixture | Memberships | Observations | Applies | UTF-8 journal bytes | Actual stdio outcome |
|---|---:|---:|---:|---:|---|
| 548 primary | 822 | 548 | 1 | 74,856 | Error, 431 bytes |
| 10,000 primary | 10,000 | 10,000 | 1 | 1,050,054 | Error, 431 bytes |
| 548 proved baseline | 822 | 548 | 1 | 74,856 | Error, 431 bytes |
| 548 three memberships | 1,644 | 548 | 1 | 123,902 | Error, 431 bytes |
| Ten operations | 50 | 0 | 10 | 80,040 | Success, 29,855 bytes; baseline unproved |
| 100,000 observations | 0 | 100,000 | 0 | 0 | Success, 24,359 bytes |

Actual stdio sizes use `JSONRPCResponse.model_dump_json(by_alias=True,
exclude_none=True)` with request ID 1, excluding the terminating newline. The
431-byte results are `resource_too_large` errors with
`contract_version:phase4-v1-2026-09-08`. They are not small successful reports.
The 25-item reproduction invokes the full reader through actual `tools/call`,
independently of the captured-packet transport audit.

The 548 journal size is exactly 73.1015625 KiB, confirming that correction. The
10,000 primary packet still retains 20 event, 20 creator, 20 joint, one source
and one shelf row; no initial rows are shed. The 548 primary retains two shelf
rows. Both primary baselines end with `interval_precedes_first_apply`. In the
current implementation replay is attempted before that final interval check, so
this reason is not evidence that replay work was skipped. The ten-operation
fixture starts with a nonempty inverse against an empty projection and the
request starts before its first operation. It must be reseeded before claiming
full progression/replay verification.

Q1 and Q3 plans reproduce `SCAN yoinks USING INDEX sqlite_autoindex_yoinks_1`
and `SCAN library_applies USING INDEX sqlite_autoindex_library_applies_3` on
the 548 fixture. No captured output establishes the document's “Combined Query
Execution <15/<45 ms” figures. The cost test neither isolates those query times
nor runs those plan checks at every scale. The UTF-8 refusal SQL now correctly
uses `LENGTH(CAST(... AS BLOB))`; the document's plain `LENGTH(text)` description
is inaccurate for non-ASCII JSON.

The document still attributes concurrency/rate verification to
`test_activity_read_has_no_side_effects`, which checks `total_changes`; it never
tests concurrency or rate limits. The implementation now uses the shared
`library_resources` process guard rather than the advertised `_active_reads_sem`.
The deletion-between-requests test does not prove concurrent snapshot isolation.
No new peak-memory measurement covers the extended replay, three-membership,
ten-operation, 100k-observation or refusal paths. Tracemalloc is not process RSS;
the 548/10k timing passes use different tracing settings. The 24,576-byte dashboard
target is missed by the primary raw packets. These limitations belong in the
measurement record; an overall “within bounds” claim is not supported.

Exact commands for Fable, from this worktree in PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\7aed1747-713\codex'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LOCALAPPDATA = Join-Path $PWD '_scratch/ba2/appdata'
$env:UOINK_OUTPUT_DIR = Join-Path $PWD '_scratch/ba2/output'
$env:TEMP = Join-Path $PWD '_scratch/ba2/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:LOCALAPPDATA,$env:UOINK_OUTPUT_DIR | Out-Null

python -m pytest -q -s -p no:cacheprovider --tb=short --basetemp=_scratch/ba2/recheck --junitxml=_scratch/ba2/recheck.xml tests/library_work_astra/test_phase5_acceptance.py tests/library_work_astra/test_phase5_dashboard.py tests/library_work_astra/test_phase5_measurements.py tests/library_work_astra/test_phase5_acceptance2.py tests/library_work_astra/test_phase5_dashboard2.py tests/library_work_astra/test_phase5_measurements2.py tests/test_library_analysis_fixtures.py tests/test_phase0_registry_capture.py tests/test_source_subscriptions_registry.py tests/test_c01_mcp_stdio.py tests/test_phase4_stdio.py tests/test_stdio_clip_tools.py tests/test_docs_live_contracts.py tests/test_current_doc_references.py tests/test_dashboard_sources_api.py tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py

git diff --check
git status --short
```

The recorded final invocation used `--basetemp=_scratch/ba2/final`,
`--junitxml=_scratch/ba2/final.xml` and captured stdout/stderr in
`_scratch/ba2/final.txt`. Local receipts are ignored scratch files; the portable
evidence is the three new test files and this report. The combined measurement
run executes the supplied benchmark through the original measurement audit,
the new instrumented audit and the standalone supplied test, in that order;
keep the three timing blocks distinct.

Only this report and `test_phase5_acceptance2.py`, `test_phase5_dashboard2.py`,
`test_phase5_measurements2.py` were added. No fixes were silently applied to the
candidate. Fable must reserve the reader/Index/adapters/dashboard and measurement
repairs, integrate them and rerun these gates. No migration or model work is
needed to address the demonstrated defects. There are no open scope questions.
