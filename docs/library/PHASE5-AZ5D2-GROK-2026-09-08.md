# Phase 5 AZ-5d2 session (grok)

Worker: grok
Run: AZ-5d2 (remove test-wrapper introspection from the adapter)
Findings: BA-09 validation/adapters; BA-10 response bounds; BA-11 bounded work
Base: `90151e7` on `cc/living-library` (`control-room/7afd1cb4-60e-grok`).
AZ-5d (`e739a5ec`, base `79f6961`) is rejected; complete diff retained in
`docs/library/patches/az5d-grok-rejected-2026-09-08.patch`.
Do not commit. Astra independently verifies and integrates. AZ-5g follows
the final implementation. No acceptance claim.

No paid API, no `ANTHROPIC_API_KEY`, no model, no live index, no port 5179.
`librarian_apply_enabled` stays false. Astra's tests were not edited.
No existing test/helper edits. No subagents. No commit or push.

Python 3.14.6. Disposable profile/output/temp under `_scratch/az5d2`.
User site-packages and pywin32 paths resolved on `PYTHONPATH` before
APPDATA redirect.

## Status

Complete as an implementation candidate, uncommitted. Production portions of
the retained AZ-5d patch were three-way applied, then the forbidden
`_read_activity` TypeError/closure fallback was removed. BA-09/10/11
repairs are in place. An independent actual-handler deadline test passes.
The frozen unary/clock wrapper case remains a TypeError for Ryan. Four
measurement-document failures remain AZ-5g work. This run does not claim
Phase 5 accepted.

Combined named-suite union (BA-3 set + AZ-5 adapters + new tests):
**470 passed, 5 failed**, 110.15 seconds. Logs: `_scratch/az5d2/logs/`.

## Apply

`library_analysis.py` and `uoink_mcp.py` at HEAD were still blobs
`e9d62b4` / `c6202fb` (unchanged since `79f6961`). Production hunks were
cut from the retained patch (report file excluded) and applied:

```
git apply --3way --verbose -- _scratch/az5d2/az5d-production-only.patch
```

Both files applied cleanly (no conflict). `_read_activity` was then deleted
so stdio calls `library_analysis.get_library_activity(args)` only.

## Repair

### BA-09 validation/adapters

- Interval start/end use whole-string grammar (`\A...\Z` + `fullmatch`).
  A trailing newline no longer matches `$` and never reaches storage.
- Storage/deadline/recovery/rate envelopes use the frozen retryable map.
  Explicit `retryable:false` overrides on those codes were removed. Stale
  reports stay non-retryable. `uoink_mcp_tools.get_library_activity` remains
  thin registry delegation (file not changed).

### BA-10 response bounds/trust

- Evidence/detail pages shed whole rows (and recompute continuation) before
  refusing. A one-row request that fits stays successful; a 20-row page that
  does not fit returns a prefix with `next.offset == len(rows)`.
- The extra 512-byte identity limit on `row_id`/`source_key` is gone. Only
  metric IDs keep that contract cap. A 600-byte item ID that fits is preserved.
- Shelf `label`/`name` and subscription `display_name` are capped at 120
  code points with `label_truncated` / `display_name_truncated`. Untrusted-text
  fence is untouched.

### BA-11 bounded work

- Stdio `activity_result` admits once via `adapter_admission()` and holds
  that admission through `render_tool_text` and `wire_bytes`. Direct/HTTP
  calls still admit and release inside `get_library_activity`.
- Nested `adapter_admission` uses a per-thread depth, not a boolean. An
  inner scope does not admit a second slot or release the outer one.
  `get_library_activity` skips admit/release while that depth is nonzero.
- Deadline is checked after final `wire_bytes`. Storage/deadline envelopes
  are retryable through the reader and the stdio adapter.
- Shared-connection `PRAGMA busy_timeout` is saved and restored on every
  exit of the snapshot try.

### Removed workaround

`_read_activity` is gone. No TypeError catch, no `__closure__` walk, no
callable inspection, test imports, test-name branches, fake success, or
exception relabelling. Production calls the public reader with `args` only.

## Independent implementation tests

`tests/test_phase5_az5d2.py` (new). Frozen acceptance files are not
replaced or deselected.

- `test_az5d2_actual_handler_deadline_during_final_wire_serialization`:
  calls the actual stdio handler. A compatible unary wrapper binds
  `clock=NOW` internally (production signature is `fn(args)`). After the
  reader returns, `wire_bytes` injects 3 s. Result is `deadline_exceeded`
  with `retryable: true`, admission is held during that `wire_bytes` call,
  and `_active == 0` after return.
- `test_az5d2_nested_adapter_admission_does_not_discard_outer_scope`:
  nested `adapter_admission` keeps `_active == 1`; inner exit and a nested
  `get_library_activity` do not release the outer scope.

This supplements the frozen case. It does not replace its result.

## Frozen unary/clock wrapper (Ryan)

`test_phase5_ba3_final_wire_serialization_is_inside_deadline` still fails.
It installs unary `read(args)`, then `stdio_result` at
`tests/library_work_astra/test_phase5_acceptance.py:427-431` wraps that
symbol as `real_read(arguments, clock=NOW)`. Production calls
`get_library_activity(args)`, so the lambda supplies `clock=` and the
unary probe raises:

```
TypeError: test_phase5_ba3_final_wire_serialization_is_inside_deadline.<locals>.read()
got an unexpected keyword argument 'clock'
```

at `test_phase5_acceptance.py:430`. The deadline probe never runs. Ryan
must authorize a compatible fixture setup. The helper was not edited.
The failure is not a pass.

## Files changed

- `library_analysis.py`
- `uoink_mcp.py`
- `tests/test_phase5_az5d2.py` (new)
- `docs/library/PHASE5-AZ5D2-GROK-2026-09-08.md` (this report)

`uoink_mcp_tools.py` unchanged. No Astra test or helper edits.
`git diff --check` clean.

## Fixture-only measurements (not AZ-5g)

Reader JSON (`json.dumps`) from the existing BA-2 capture helper.
Disposable roots under `_scratch/az5d2`.

| Fixture | Observed raw JSON bytes | Creator rows |
|---|---:|---:|
| 548-item cost fixture | 58,035 | 20 |
| 10,000-item cost fixture | 57,968 | 20 |

Published measurement doc still 58,738 / 58,640. AZ-5g refreshes that
document. Injected expired-clock envelope is `deadline_exceeded` with
`retryable: true` (190 raw bytes).

## Commands and observed counts

Environment: `PYTHONDONTWRITEBYTECODE=1`, PYTHONPATH = worktree +
`site.getusersitepackages()` + `win32` / `win32/lib` / `pythonwin`
(resolved before APPDATA redirect), worktree-local APPDATA/TEMP under
`_scratch/az5d2`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, no
`ANTHROPIC_API_KEY`.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5d2.py
```
**2 passed**, 1.38 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py -k "interval_rejects or retryable_errors or detail_page_sheds or single_fitting_identity or all_display_labels or stdio_holds_admission or final_wire_serialization or read_restores_shared"
```
**10 passed, 1 failed**, 41 deselected, 1.97 s. Failure is the frozen
unary/clock TypeError.

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py -k "<BA-01/BA-03 reproductions>"
```
**18 passed**, 34 deselected, 2.68 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py -k "<AZ-5b/5c/5f reproductions>"
```
**23 passed**, 29 deselected, 2.43 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py
```
**51 passed, 1 failed**, 4.69 s. Same frozen TypeError.

```
python -B -m pytest -q -p no:cacheprovider tests/test_library_analysis_fixtures.py
```
**28 passed**, 19.83 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance.py tests/library_work_astra/test_phase5_acceptance2.py tests/library_work_astra/test_phase5_dashboard.py tests/library_work_astra/test_phase5_dashboard2.py tests/library_work_astra/test_phase5_measurements.py tests/library_work_astra/test_phase5_measurements2.py tests/test_library_analysis_fixtures.py
```
**173 passed, 1 failed**, 67.51 s. Failure is
`test_phase5_ba2_measurement_document_payloads_match_capture`
(published 58,738/58,640 vs captured raw 58,035/57,968). AZ-5g work.

```
python -B -m pytest -q -p no:cacheprovider tests/test_c01_mcp_stdio.py tests/test_phase4_stdio.py tests/test_stdio_clip_tools.py tests/test_phase0_registry_capture.py tests/test_docs_live_contracts.py tests/test_library_adapters.py
```
**126 passed**, 25.12 s

```
python -B -m pytest -q -p no:cacheprovider tests/test_dashboard_sources_api.py tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py
```
**35 passed**, 0.33 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_dashboard3.py
```
**7 passed**, 0.31 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_measurements3.py
```
**3 failed**, 19.28 s. All three are BA-14 measurement-document cases (AZ-5g).

```
python -B -m pytest -q -p no:cacheprovider tests/test_source_subscriptions_registry.py tests/test_current_doc_references.py
```
**76 passed**, 4.95 s

Combined union (new tests + BA-3 modules + AZ-5 adapters + dashboard
companions + registry/docs extras), `--junitxml=_scratch/az5d2/combined.xml`:

**470 passed, 5 failed**, 110.15 s.

## Remaining failures (not passes)

1. `test_phase5_ba3_final_wire_serialization_is_inside_deadline` —
   TypeError at `stdio_result` (`clock=` into a unary probe). Ryan.
2. `test_phase5_ba2_measurement_document_payloads_match_capture` — AZ-5g.
3. `test_phase5_ba3_measurement_record_acknowledges_observed_row_shedding` — AZ-5g.
4. `test_phase5_ba3_measurement_record_does_not_claim_replay_was_skipped` — AZ-5g.
5. `test_phase5_ba3_measurement_record_labels_handbuilt_transport_timing` — AZ-5g.

Astra's tests were not edited. No commit.
