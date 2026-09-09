# Phase 5 AZ-5h session (grok)

Worker: grok
Run: AZ-5h (charge the actual final transport serialization)
Findings: BA4-01 at the shipped SDK JSON-RPC dump; shared Phase 4/5/6
stdio lifetime. AZ-5d2 repairs preserved. AZ-5g Gemini partial refresh is
retained and was not applied.
Base: `e0d8bef` on `cc/living-library` (`control-room/f62e5609-861-grok`).
Do not commit. Astra independently verifies both roots, then AZ-5g2
measures the integrated SHA and BA-4 rules. No acceptance claim.

No paid API, no `ANTHROPIC_API_KEY`, no model, no live index, no port 5179.
`librarian_apply_enabled` stays false. Astra's tests were not edited.
No existing test/helper edits. No installed SDK edits. No subagents.
No commit or push.

Python 3.14.6. Disposable profile/output/temp under `_scratch/az5h`.
User site-packages and pywin32 paths resolved on `PYTHONPATH` before
APPDATA redirect.

SDK: installed `mcp 1.28.1`; package pin `mcp==1.27.1`.

## Status

Complete as an implementation candidate, uncommitted. The shipped stdio
entry is now `uoink_mcp.run_bounded_stdio_async` (`mcp.run_stdio_async`).
Budgeted requests admit once on inbound parse, handlers nest on that slot,
the writer delegates serialization to the real
`JSONRPCMessage.model_dump_json`, then checks UTF-8 bytes and remaining
time before write/flush, and releases on success, typed error,
cancellation, and broken transport.

The frozen BA-4 probe still uses the installed SDK `stdio_server` imported
before this wrapper. It does not exercise the shipped entry. Exact result
below. AZ-5d2 actual-handler and nested-admission tests still pass. Four
measurement-document failures remain AZ-5g2 work. The unary/clock wrapper
remains a TypeError for Ryan. This run does not claim Phase 5 accepted.

Combined named-suite union (AZ-5h + AZ-5d2 + BA-4 probe + AZ-5d2 modules):
**477 passed, 6 failed**, 126.10 seconds. Logs:
`_scratch/az5h/combined.xml`.

## Apply

AZ-5g's incomplete refresh is retained at
`docs/library/patches/az5g-gemini-partial-rejected-2026-09-08.patch` and
was not applied. No portion integrated. Measurement documents were not
edited.

## Request / response lifetime

Shipped entry (`python uoink_mcp.py` / `mcp.run(transport="stdio")`):

1. `bounded_stdio_server` reads a line and validates with the existing
   strict `JSONRPCMessage.model_validate_json` (duplicate keys still
   rejected).
2. A budgeted inbound request (`tools/call` of
   `get_library_activity` / Phase 4 read and brief tools /
   `export_cited_range`, plus `resources/list`, `resources/read`,
   `prompts/get`) admits once on the shared process guard. Deadline is
   that `time.monotonic()` stamp plus 2.0 s. Initialize, `tools/list`,
   `prompts/list`, `resources/templates/list`, ping, and notifications
   do not take a library slot.
3. `Server._handle_request` is wrapped on the product server instance
   (not an SDK file edit) so the handler task binds that request-id
   scope. Nested `adapter_admission`, `get_library_activity`,
   `LibraryReader._operation`, and `_admitted_export` skip a second
   admit/release.
4. The SDK session still builds the real `JSONRPCMessage`. The product
   writer calls `message.model_dump_json(by_alias=True, exclude_none=True)`,
   then measures `len(text.encode("utf-8"))` and the same deadline.
5. An expired **success** becomes a bounded retryable `deadline_exceeded`
   with the original request id (tool `CallToolResult.isError` with the
   Phase 5 envelope for `get_library_activity`; Phase 4 envelope or
   JSON-RPC `-32603` with `error.data` for resources/prompts). It is not
   relabelled as a generic internal error. An already-typed error is
   delivered as-is. Oversize success becomes `resource_too_large`
   (`retryable: false`) under the existing 65,536-byte wire cap.
6. The frame is written and flushed once, then the slot is released.

Direct handler/HTTP callers have no transport scope, so AZ-5d2's
handler-level admit/release is unchanged.

### Cancellation and flush

- Every outbound frame is flushed after write, matching the SDK writer.
- `notifications/cancelled` marks the request. A later success frame for
  that id is not delivered. Admission is released in the writer `finally`.
- A broken `stdout.write` / closed stream also releases in that `finally`.
- Server/task-group teardown calls `release_all_transport_scopes`.
- Release is idempotent. No extra admission for the same request id.

## Frozen BA-4 probe (unchanged; did not exercise the shipped entry)

`tests/library_work_astra/test_phase5_ba4_acceptance.py` imports
`from mcp.server.stdio import stdio_server` **before** `uoink_mcp`, then
calls `uoink_mcp.mcp._mcp_server.run` on those SDK streams. Serialization
therefore happens in the installed SDK `stdout_writer`, after handler
release. The probe was not edited.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5d2.py tests/library_work_astra/test_phase5_ba4_acceptance.py
```

**2 passed, 1 failed**, 1.45 s.

```
AssertionError: Expired actual serialization emitted success; active admissions=[0]
assert False
tests/library_work_astra/test_phase5_ba4_acceptance.py:95
```

Route limitation: this probe never enters `bounded_stdio_server`. It is
not evidence that the shipped entry still emits success after a delayed
final dump. Independent actual-entry tests below drive that entry.

## Independent actual-entry tests

`tests/test_phase5_az5h.py` (new). Frozen acceptance files are not
replaced or deselected.

- `test_az5h_shipped_entry_is_bounded_stdio`
- `test_az5h_actual_stdio_entry_deadline_during_sdk_serialization`:
  initialize + `tools/call get_library_activity` through
  `bounded_stdio_server`; 3 s injected in
  `JSONRPCMessage.model_dump_json` for id 2. Result is
  `deadline_exceeded` with `retryable: true`, admission held during that
  dump, `_active == 0` after return. Request id 2 is preserved.
- `test_az5h_actual_stdio_entry_releases_on_cancellation`
- `test_az5h_actual_stdio_entry_releases_on_broken_write`
- `test_az5h_phase4_resource_list_deadline_uses_same_transport`
- `test_az5h_oversize_actual_frame_is_resource_too_large`
- `test_az5h_notifications_and_initialize_do_not_hold_admission`

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5h.py
```

**7 passed**, 4.02 s.

AZ-5d2 tests remain green:

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5d2.py
```

**2 passed** (included in the 1.45 s command above).

## Frozen unary/clock wrapper (Ryan)

`test_phase5_ba3_final_wire_serialization_is_inside_deadline` still fails.
It installs unary `read(args)`, then `stdio_result` wraps that symbol as
`real_read(arguments, clock=NOW)`. Production calls
`get_library_activity(args)`, so the lambda supplies `clock=` and the
unary probe raises:

```
TypeError: test_phase5_ba3_final_wire_serialization_is_inside_deadline.<locals>.read()
got an unexpected keyword argument 'clock'
```

at `test_phase5_acceptance.py:430`. Ryan must authorize a compatible
fixture setup. The helper was not edited. The failure is not a pass.

## Files changed

- `library_resources.py` — transport request scope; nested `_operation`
- `library_analysis.py` — nest `adapter_admission` / `get_library_activity`
  when a transport scope is bound; test isolation resets transport scopes
  and the guard clock
- `library_media.py` — nest `_admitted_export` on the same scope
- `uoink_mcp.py` — `bounded_stdio_server`, shipped `run_bounded_stdio_async`,
  instance wrap of `_handle_request`
- `tests/test_phase5_az5h.py` (new)
- `docs/library/PHASE5-AZ5H-GROK-2026-09-08.md` (this report)

No Astra test or helper edits. No installed SDK edits.
`git diff --check` clean. AZ-5g patch not applied.

## Now-stale measurement assertions (AZ-5g2)

Do not change measurement documents in this run. Observed this session
from the existing synthetic capture (not a new sealed record):

| Fixture | Observed raw JSON bytes | Actual stdio bytes (handler capture) |
|---|---:|---:|
| 548-item cost fixture | 58,035 | 64,732 |
| 10,000-item cost fixture | 57,968 | 64,601 |

Published measurement doc still 58,738 / 58,640. Combined-run extra
notes for AZ-5g2: hand-built transport-ser 0.70 ms / 64,743 bytes;
injected deadline raw envelope 190 bytes `retryable: true`; 70 MiB
journal refusal 221 raw bytes. The Transport Serialization row still
claims "actual stdio adapter". Replay is still described as skipped.
Shedding is still described as absent (20 creator rows observed). AZ-5h
also changes the shipped transport path, so AZ-5g2 must name the final
source SHA and the path it actually executes.

## Commands and observed counts

Environment: `PYTHONDONTWRITEBYTECODE=1`, PYTHONPATH = worktree +
`site.getusersitepackages()` + `win32` / `win32/lib` / `pythonwin`
(resolved before APPDATA redirect), worktree-local APPDATA/TEMP under
`_scratch/az5h`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, no
`ANTHROPIC_API_KEY`.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5h.py
```
**7 passed**, 4.02 s

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5d2.py tests/library_work_astra/test_phase5_ba4_acceptance.py
```
**2 passed, 1 failed**, 1.45 s. Failure is the frozen BA-4 SDK-route probe.

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py
```
**51 passed, 1 failed**, 4.32 s. Failure is the frozen unary/clock TypeError.

```
python -B -m pytest -q -p no:cacheprovider tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py
```
**84 passed**, 6.61 s

Combined union (AZ-5h + AZ-5d2 + BA-4 + BA-3 modules + AZ-5 adapters +
dashboard companions + registry/docs extras),
`--junitxml=_scratch/az5h/combined.xml`:

**477 passed, 6 failed**, 126.10 s.

## Remaining failures (not passes)

1. `test_ba4_actual_sdk_serialization_retains_admission_and_deadline` —
   frozen SDK `stdio_server` route; success with `active admissions=[0]`.
   Report only; the shipped entry is covered by `tests/test_phase5_az5h.py`.
2. `test_phase5_ba3_final_wire_serialization_is_inside_deadline` —
   TypeError at `stdio_result` (`clock=` into a unary probe). Ryan.
3. `test_phase5_ba2_measurement_document_payloads_match_capture` — AZ-5g2.
4. `test_phase5_ba3_measurement_record_acknowledges_observed_row_shedding` — AZ-5g2.
5. `test_phase5_ba3_measurement_record_does_not_claim_replay_was_skipped` — AZ-5g2.
6. `test_phase5_ba3_measurement_record_labels_handbuilt_transport_timing` — AZ-5g2.

Astra's tests were not edited. No commit.
