# Phase 5 SDK serialization repair (grok)

Worker: grok
Worktree: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\8cef3e8a-3ad\grok`
Brief: `docs/library/RYAN-PHASE5-SDK-REPAIR-2026-09-09.md`
Do not commit or push. No existing test/fixture/assertion edits. No installed
SDK edits. No subagents. Part B remains deferred. No live index, port 5179,
paid API, or `ANTHROPIC_API_KEY`.

## Status

Complete as an uncommitted implementation candidate. The installed SDK
`stdio_server` + registered `Server.run` route now retains one process-guard
admission through the actual `JSONRPCMessage.model_dump_json` call, then
refuses expired or oversize success with the same envelopes as the shipped
writer. The shipped `bounded_stdio_server` entry is unchanged in behavior.

Named union required by the brief: **266 passed, 0 failed, 0 skipped**,
134.26 seconds. BA-4 passes. The corrected unary-clock probe passes. Astra
verifies independently in both roots before integration. No acceptance claim
for the full tree.

## Sealed baseline (not rerun as a second unlabeled measurement)

Corrected tree `4a35316`, retained under
`docs/library/proof/ryan-corrected-01-2026-09-09`:

`tests/library_work_astra/test_phase5_ba4_acceptance.py::test_ba4_actual_sdk_serialization_retains_admission_and_deadline`

```
AssertionError: Expired actual serialization emitted success; active admissions=[0]
```

The probe imports `mcp.server.stdio.stdio_server` and runs
`uoink_mcp.mcp._mcp_server.run` on those streams. Admission was released in
the tool handler before the SDK writer's `model_dump_json`. The historical
"old route" classification is not treated as a pass.

## Repair

Product change is confined to `uoink_mcp.py`. Direct handler/HTTP callers and
the shipped bounded writer keep their existing admit/release.

1. Budgeted requests that never entered `bounded_stdio_server` admit once in
   the registered `_handle_request` wrapper
   (`_ensure_inbound_transport_scope`). Duplicate ids reuse the inbound
   scope, so the shipped entry does not take a second slot.
2. `Server.run` on the original SDK stdio streams installs an outermost
   `JSONRPCMessage.model_dump_json` around whatever is currently bound,
   including a test patch. The SDK writer still performs the dump. After that
   dump returns, expired success becomes retryable `deadline_exceeded`,
   oversize success becomes `resource_too_large`, the completed-frame cap
   still applies, and the slot is released. Typed errors pass through.
3. While `bounded_stdio_server` is entered, `Server.run` does not install that
   wrapper. `_deliver_bounded_outbound` remains the settlement path for the
   shipped entry.

Independent cases in `tests/test_phase5_sdk_original_route.py` (new; existing
tests untouched) drive the SDK `stdio_server` route for a complete success
packet and for the delayed-dump refusal.

## Repair / retry record

| Step | Question | Result |
|---|---|---|
| Sealed baseline `4a35316` | Does BA-4 fail on the SDK `stdio_server` route with `_active==0` during dump? | Yes. Retained in `proof/ryan-corrected-01-2026-09-09`. Not rerun. |
| Repair R1 | Hold admission through actual SDK dump on `Server.run` when the product writer is not in use; refuse expired success. | Source in `uoink_mcp.py`. |
| Post-repair focus | BA-4 + new original-route cases | **3 passed**, 1.86 s. No retry. |
| Post-repair named union | Brief selectors | **266 passed**, 134.26 s. No retry. |

No second repair. Failed sealed outcome retained. Part B not run.

## Environment

- Python `C:\Python314\python.exe` 3.14.6
- Installed MCP `1.28.1` at user site-packages
- Runner: retained
  `docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py`
  (bytecode disabled, `pytest -p no:cacheprovider`, `ig_paths`, audit guard)
- `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`,
  `PHASE3_REQUIRE_IMPLEMENTATION=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
- `ANTHROPIC_API_KEY` removed in the child
- `PYTHONPATH`: scratch guard, worktree, user site-packages, pywin32 paths
  (resolved before APPDATA redirect)
- Scratch profile/temp under `_scratch/phase5-sdk-focus` and
  `_scratch/phase5-sdk-union`; `UOINK_INDEX_PATH` is an unused scratch file
- Guard refuses live `%LOCALAPPDATA%\Uoink\index.db`, port 5179, external
  sockets, and real model processes

`git diff --check` clean.

## Commands and outcomes

Focus (post-repair):

```
python -B docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py --root <worktree> --label phase5-sdk-focus tests/library_work_astra/test_phase5_ba4_acceptance.py tests/test_phase5_sdk_original_route.py
```

**3 passed**, 1.86 s. Log/XML: `_scratch/phase5-sdk-focus/`.

Named union:

```
python -B docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py --root <worktree> --label phase5-sdk-union tests/library_work_astra/test_phase5_ba4_acceptance.py tests/library_work_astra/test_phase5_acceptance.py tests/library_work_astra/test_phase5_acceptance2.py tests/library_work_astra/test_phase5_acceptance3.py tests/library_work_astra/test_phase5_ba5_acceptance.py tests/library_work_astra/test_phase5_dashboard.py tests/library_work_astra/test_phase5_dashboard2.py tests/library_work_astra/test_phase5_dashboard3.py tests/library_work_astra/test_phase5_measurements.py tests/library_work_astra/test_phase5_measurements2.py tests/library_work_astra/test_phase5_measurements3.py tests/test_library_analysis_fixtures.py tests/test_phase5_az5d2.py tests/test_phase5_az5h.py tests/test_phase5_az5h2.py tests/test_phase5_sdk_original_route.py tests/test_phase4_stdio.py
```

**266 passed, 0 failed, 0 skipped**, 134.26 s (`tests.xml` `tests="266"`).
Includes BA-4, the unary-clock probe, BA-5, AZ-5d2/h/h2, analysis fixtures,
and Phase 4 stdio. Log/XML: `_scratch/phase5-sdk-union/`.

## Limits

- Full tree not run. Astra verifies both roots before integration.
- Dashboard 24,576-byte target remains a separate failed measurement. This
  brief does not relabel or repeat it.
- Part B remains deferred.
- No installed-package or real-client receipt is inferred.
- Original SDK route settlement wraps `model_dump_json` only for the lifetime
  of `Server.run` when the product writer is not active. Installed SDK files
  were not edited.

## Files changed

- `uoink_mcp.py` — admit budgeted requests on the registered low-level
  handler when no transport scope exists; settle the actual SDK dump on
  `Server.run` for that route; keep `bounded_stdio_server` as the shipped
  writer
- `tests/test_phase5_sdk_original_route.py` — new independent original-route
  cases
- `docs/library/RYAN-PHASE5-SDK-WORKER-2026-09-09.md` — this report

No existing test, fixture, assertion, skip, or parameter was edited.
