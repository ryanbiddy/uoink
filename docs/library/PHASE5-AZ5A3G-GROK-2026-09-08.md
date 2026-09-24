# Phase 5 AZ-5a3g session (grok)

Worker: grok
Run: AZ-5a3g (Phase 5 Part A repair)
Findings: BA-01 provenance/evidence, BA-03 publication selection;
restore 20 creator rows after rejected AZ-5a2 compact-evidence patch
Base: `fc544f2` on `cc/living-library` (`control-room/54108a1f-060-grok`)
Do not commit. Astra verifies and integrates.

Gemini dispatch `bbd68b73` produced no diff (quota). Preserve that failed
dispatch. No paid API, no `ANTHROPIC_API_KEY`, no model, no live index,
no port 5179. `librarian_apply_enabled` stays false.

## Status

Complete, uncommitted. Applied
`docs/library/patches/az5a2-claude-2026-09-08.patch` onto current
`library_analysis.py` with a three-way merge against blob `80f7195`
(`6acab390:library_analysis.py`). Preserved AZ-5b coverage-aware nulls /
per-source coverage and the AZ-5f `library_faithfulness` import (did not
restore the inlined evaluator). Compacted summary evidence so the
25-creator fixture keeps 20 creator rows. BA-09/10/11 and BA-14
measurement-document refresh remain queued.

## Repair

`library_analysis.py` only.

- Metric-to-support registry in `provenance.relations`.
- One lookup (`_lookup_evidence` / `_rows_for`) binds summary counts and
  serves `detail: evidence`. Support rows are never inlined on the
  summary.
- Compact numerator evidence: `{role, row_count, sample_count, has_more}`.
  The enclosing metric already has `metric_id` (dashboard
  `activityMetricId`, Astra `{**metric, **evidence}`). Denominator
  references stay `{metric_id, role}` so they resolve without the parent.
- Observation hashes stay on paged evidence rows. AZ-5a2's first-page
  digest is not attached on summary descriptors and is not a population
  hash. `row_count` is the exact support population.
- BA-01/BA-03 row builders from the retained patch: journal thin
  before/after changes, `item_deleted`, replay bound to retained applies,
  tombstone/events scopes, channel in the selected observation hash,
  publication availability reuses the candidate relation.
- AZ-5b kept: `coverage_ref`, `_metric_value_or_zero`, invalid-revision
  partial coverage, initial filing `None` without a proved baseline,
  per-source coverage records, no-history nulls across remaining
  historical metrics.

## Fixture-only measurements

Reader JSON (`json.dumps`) and `_calculate_transport_bytes` (serialized
adapter representation; not a real stdio child). Disposable profile/temp
under `_scratch/az5a3g/run`. User site-packages and pywin32 paths resolved
before APPDATA redirect. The integrator's first helper import failure
(missing pywin32 on a redirected profile) is retained as a failed setup
attempt; this is the authorized corrected measurement.

AZ-5a2 historical observation (16:25 PDT; not current): empty 31-day
51,668 / 58,289 with 0 creators; 25-creator 57,704 / 64,411 with **12**
creator rows.

| Fixture | Raw JSON bytes | Serialized transport bytes | Returned creator rows |
|---|---:|---:|---:|
| Empty 31-day interval | 46,343 | 52,286 | 0 (31 daily buckets) |
| 25-creator pagination | 58,013 | 64,930 | 20 (required: 20) |

25-creator shed packet also: joint 2/25, events 0/25, sources 20/25,
creator `other_count` 5. `items.total` evidence
`{role:numerator, row_count:25, sample_count:20, has_more:true}`. Cap
65,536; both packets succeed.

548/10k cost-fixture raw JSON now 57,950 / 57,909 (published measurement
doc still 58,738 / 58,640). AZ-5g refreshes that document after AZ-5d.
Do not treat the historical published sizes as current.

## Commands and observed counts

Environment: `PYTHONDONTWRITEBYTECODE=1`, PYTHONPATH = worktree +
`site.getusersitepackages()` + `win32` / `win32/lib` / `pythonwin`,
worktree-local APPDATA/TEMP, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, no
`ANTHROPIC_API_KEY`.

```
python -B -m pytest -q -p no:cacheprovider tests/test_library_analysis_fixtures.py
```
**28 passed**, 17.72 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py -k "<BA-01/BA-03 reproductions>"
```
**18 passed**, 34 deselected, 2.40 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py -k "<AZ-5b/5c/5f reproductions>"
```
**23 passed**, 29 deselected, 2.54 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance.py tests/library_work_astra/test_phase5_acceptance2.py tests/library_work_astra/test_phase5_dashboard.py tests/library_work_astra/test_phase5_dashboard2.py tests/library_work_astra/test_phase5_measurements.py tests/library_work_astra/test_phase5_measurements2.py
```
**145 passed, 1 failed**, 39.64 s. Failure is
`test_phase5_ba2_measurement_document_payloads_match_capture`
(published 58,738/58,640 vs captured raw 57,950/57,909). AZ-5g work.

```
python -B -m pytest -q -p no:cacheprovider tests/test_c01_mcp_stdio.py tests/test_phase4_stdio.py tests/test_stdio_clip_tools.py tests/test_phase0_registry_capture.py tests/test_docs_live_contracts.py tests/test_library_adapters.py
```
**126 passed**, 15.47 s

```
python -B -m pytest -q -p no:cacheprovider tests/test_dashboard_sources_api.py tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py
```
**35 passed**, 0.33 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_dashboard3.py
```
**7 passed**, 0.31 s

Full `test_phase5_acceptance3.py` + `test_phase5_measurements3.py`:
**41 passed, 14 failed**. Failures are BA-09/10/11 (AZ-5d, 11 cases) and
BA-14 (AZ-5g, 3 cases). Astra's tests were not edited.

No commit.
