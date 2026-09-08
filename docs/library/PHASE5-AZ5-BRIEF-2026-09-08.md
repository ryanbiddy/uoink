# Phase 5 Part A repair brief, third round (runs AZ-5a..AZ-5g, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase5-v1`
([PHASE5-CONTRACT-2026-09-08.md](PHASE5-CONTRACT-2026-09-08.md)). Astra's BA-3 verdict
([PHASE5-ACCEPTANCE-3-2026-09-08.md](PHASE5-ACCEPTANCE-3-2026-09-08.md)) is the
specification: its per-item table names the exact remaining repair and the reproductions
in `tests/library_work_astra/test_phase5_acceptance3.py`,
`tests/library_work_astra/test_phase5_dashboard3.py` and
`tests/library_work_astra/test_phase5_measurements3.py` (62 failing on the candidate).
Base: the commit this brief lands in. Workers never commit; Fable integrates and runs every
suite. No worker runs a model, the resident helper, port 5179 or the live index; no
`ANTHROPIC_API_KEY`.

Rules for every run:

- Astra's tests are the target and may not be edited. The BA-3 table says explicitly for
  BA-05: "do not relax validation to keep those fixtures green"; update abbreviated
  synthetic fixtures in the implementation's own test helpers only where BA-3 says so.
- Existing suites stay green: `test_phase5_acceptance.py` (66), `test_phase5_dashboard.py`
  (8), `test_phase5_measurements.py` (1), `test_phase5_acceptance2.py` (57),
  `test_phase5_dashboard2.py` (10), `test_phase5_measurements2.py` (4),
  `tests/test_library_analysis_fixtures.py` (28), the registry/stdio/docs inventories.
- Write early; report observed counts and exact commands; note anything not implemented.
- Budget rule for the Claude worker: no subagents; targeted searches only.

## Run table

| Run | Engine | BA items | Reproductions to close | Files |
|---|---|---|---|---|
| AZ-5a | gemini | BA-01 provenance and evidence; BA-03 publication selection | `every_metric_reports_evidence_population` (5), `item_shares_have_distinct_denominator_evidence` (3), `source_state_metric_has_exact_evidence`, `zero_shelf_metric_has_no_unrelated_support` (2), `journal_evidence_contains_reconcilable_item_changes`, `deleted_journal_evidence_marks_identity`, `baseline_evidence_binds_retained_journal_support`, `deleted_metric_scope_is_tombstones`, `combined_event_scope_includes_journal_clock`, `channel_correction_changes_selected_observation_hash`, `publication_availability_uses_candidate_relation` | `library_analysis.py` (metric-to-support relation registry, denominators, evidence pages, observation hashes, publication availability) |
| AZ-5c | claude | BA-05 journal proof; BA-08 read boundary | `typed_membership_fields_are_validated` (5), `nested_policy_fields_are_validated`, `apply_requires_successful_receipt_status` (2), `inverse_metadata_must_match_replayed_state`, `wal_commit_during_construction_is_detected` | `library_analysis.py` (`_validate_delta_structure` ~354, receipt status ~1128, replay comparison ~1189/1312, snapshot generation recheck ~2898/2920 using `Index.read_snapshot`) |
| AZ-5e | grok | BA-12 dashboard | all seven cases in `test_phase5_dashboard3.py` | `assets/dashboard/index.html` (sequence token per page request, obsolete replies ignored without UI mutation, returned continuations for evidence and collections, exclusions bound to the selected clock with evidence links, publication view shows unavailable publication dates) |
| AZ-5b | grok, after AZ-5a lands | BA-04 clocks and coverage; BA-07 sources and windows | `no_history_is_null_across_remaining_metrics` (5), `invalid_revision_clock_marks_partial_coverage`, `initial_filing_is_unknown_without_baseline`, `source_metric_has_its_own_history_status` | `library_analysis.py` (coverage-aware nulls for every historical metric, invalid clock exclusions by family, initial filing unknown without a proved baseline, per-source history status) |
| AZ-5d | grok, after AZ-5b | BA-09 validation/adapters; BA-10 response bounds; BA-11 bounded work | `interval_rejects_trailing_newline_before_storage` (2), `retryable_errors_retain_contract_semantics` (2), `detail_page_sheds_whole_rows_before_refusal`, `single_fitting_identity_is_preserved`, `all_display_labels_are_bounded_and_explicit` (2), `stdio_holds_admission_through_final_render`, `final_wire_serialization_is_inside_deadline`, `read_restores_shared_connection_busy_timeout` | `library_analysis.py`, `uoink_mcp.py`, `uoink_mcp_tools.py` (whole-string grammar, contract retryable mapping, detail-row shedding with continuation, 512-byte limit only for metric IDs, bounded labels with truncation flags, one admission/deadline through final wire serialization, busy_timeout restored) |
| AZ-5f | claude, after AZ-5c | BA-13 faithfulness | `labelled_assertions_require_actual_metric_bindings` (4), `labelled_pin_and_undo_assertions_need_operation_evidence` | move the evaluator out of production into a static harness; resolve each labelled assertion to its actual metric, population, clock, interval, revisions and evidence, including pin/direction/undo claims |
| AZ-5g | gemini, after AZ-5d | BA-14 measurements | all three cases in `test_phase5_measurements3.py` | `docs/library/PHASE5-MEASUREMENTS-*.md` regenerated from final full-reader/actual-adapter observations; the three false path descriptions replaced; measured limits distinguished from unmeasured coverage |

## Commands

`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<worktree>`, no `ANTHROPIC_API_KEY`:

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py -k "<your reproductions>"
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance.py tests/library_work_astra/test_phase5_acceptance2.py tests/library_work_astra/test_phase5_dashboard.py tests/library_work_astra/test_phase5_dashboard2.py tests/library_work_astra/test_phase5_measurements.py tests/library_work_astra/test_phase5_measurements2.py tests/test_library_analysis_fixtures.py
python -B -m pytest -q -p no:cacheprovider tests/test_c01_mcp_stdio.py tests/test_phase4_stdio.py tests/test_stdio_clip_tools.py tests/test_phase0_registry_capture.py tests/test_docs_live_contracts.py tests/test_library_adapters.py
```

Dashboard runs also: `tests/test_dashboard_sources_api.py tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py`.
