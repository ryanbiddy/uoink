# Phase 5 AZ-5h2 session (grok)

Worker: grok
Run: AZ-5h2 (preserve the inbound deadline and bound refusal frames)
Findings: BA-5 at activity storage waits and completed refusal frames.
AZ-5h is integrated at `8e3e4f0`. Base: `533ef6f` on `cc/living-library`
(`control-room/098fb14d-115-grok`). Do not commit. Astra independently
verifies both roots, then AZ-5g2 measures the integrated SHA and BA-4
rules. No acceptance claim.

No paid API, no `ANTHROPIC_API_KEY`, no model, no live index, no port 5179.
`librarian_apply_enabled` stays false. Astra's tests were not edited.
No existing test/helper edits. No installed SDK edits. No subagents.
No commit or push. No measurement-document edits.

Python 3.14.6. Disposable profile/output/temp under `_scratch/az5h2`.
User site-packages and pywin32 paths resolved on `PYTHONPATH` before
APPDATA redirect.

SDK: installed `mcp 1.28.1`; package pin `mcp==1.27.1`.

## Status

Complete as an implementation candidate, uncommitted. The AZ-5h transport
boundary stays the shipped entry (`bounded_stdio_server` /
`run_bounded_stdio_async`). Both frozen BA-5 cases pass. AZ-5d2 nested
admission, direct-handler deadline, and busy-timeout restoration stay in
place. Combined named-suite union: **570 passed, 6 failed**, 132.10
seconds. Logs: `_scratch/az5h2/combined.xml`.

The six failures are the frozen BA-4 SDK-route probe, the unary/clock
TypeError (Ryan), and four stale measurement-document assertions (AZ-5g2).
This run does not claim Phase 5 accepted.

## Repair

### Original inbound deadline through activity storage

`get_library_activity` was starting a fresh `time.monotonic()` clock after
inbound admission. With 1.5 s already elapsed, SQLite `BEGIN EXCLUSIVE`
waits then consumed another full 2.0 s budget (observed 4.668 s from
admission).

- When a transport scope is bound, domain execution uses
  `scope.admitted_at` as `start_time`. Deadline is that stamp plus 2.0 s
  through lock acquisition, initial `PRAGMA busy_timeout` save/set,
  snapshot enter, queries, and the AZ-5h serializer.
- Already-expired requests refuse `deadline_exceeded` before
  `_get_connection` / lock / snapshot. Converting a late response to a
  timeout cannot undo an excessive wait.
- Snapshot waits use remaining budget only. `PRAGMA busy_timeout` is
  saved, set to 0 (Windows overshoots a multi-second timeout), and
  restored on every exit. Locked snapshot/initial queries retry until the
  original deadline, then refuse `deadline_exceeded`.
- Direct/HTTP callers have no transport scope, so they still admit and
  start the clock at `get_library_activity`. Nested `adapter_admission`
  still skips a second slot. Shared guard remains two-active /
  60-per-minute.

### Completed-frame cap on refusals and inbound envelopes

A 65,536-character JSON-RPC string id was admitted, then replaced with an
error that still echoed the id (65,838 bytes).

- Inbound UTF-8 line bytes are bounded by the completed-frame cap
  (65,536) before parse, admit, or domain work.
- After parse, a request id that cannot appear in any valid JSON-RPC
  frame under the cap is rejected the same way.
- The shipped writer checks completed UTF-8 bytes on success, typed
  errors, and replacement refusals. If the original id still cannot fit,
  a fixed protocol rejection uses `id: null`. Accepted ids are preserved
  exactly. The frame is valid JSON; ids are never truncated.
- The installed SDK `JSONRPCError` type rejects `id=None`, so the null-id
  frame is product JSON, not an SDK dump.

## Original deadline propagation

1. `bounded_stdio_server` admits once on inbound parse.
   `admitted_at = time.monotonic()`, `deadline_at = admitted_at + 2.0`.
2. `Server._handle_request` binds that scope. Handlers nest.
3. `get_library_activity` / `_execute_activity` use `admitted_at` as
   `start_time` when the scope is bound.
4. Remaining time bounds index-lock `acquire`, busy-timeout arming,
   snapshot enter, and query retries. Progress handler interrupts at the
   original deadline. New SQLite opens use `timeout=0`.
5. AZ-5h writer still charges `JSONRPCMessage.model_dump_json` to the
   same deadline and releases on success, typed error, cancellation, and
   broken transport.

## Completed-frame limits

| Limit | Value | Applied at |
|---|---:|---|
| Completed outbound UTF-8 frame | 65,536 | every stdio write, including typed errors and replacements |
| Inbound protocol envelope | 65,536 | raw line before parse/admit |
| Tool/resource request payload | 8,192 | unchanged domain `MAX_REQUEST_BYTES` |
| Shared guard | 2 active, 60/min | unchanged `ReadGuard` |

Null-id protocol rejection (envelope cannot be accepted):

```json
{"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"Inbound request exceeds protocol limits"}}
```

## Frozen BA-4 probe (unchanged; did not exercise the shipped entry)

`tests/library_work_astra/test_phase5_ba4_acceptance.py` imports
`from mcp.server.stdio import stdio_server` **before** `uoink_mcp`, then
calls `uoink_mcp.mcp._mcp_server.run` on those SDK streams. Serialization
happens in the installed SDK `stdout_writer`, after handler release. The
probe was not edited.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5d2.py tests/library_work_astra/test_phase5_ba4_acceptance.py
```

**2 passed, 1 failed**, 1.40 s.

```
AssertionError: Expired actual serialization emitted success; active admissions=[0]
assert False
tests/library_work_astra/test_phase5_ba4_acceptance.py:95
```

Route limitation: this probe never enters `bounded_stdio_server`. It is
not evidence that the shipped entry still emits success after a delayed
final dump. Independent actual-entry tests cover that entry.

## Independent tests

`tests/test_phase5_az5h2.py` (new). Frozen acceptance files are not
replaced or deselected. AZ-5h's seven actual-entry tests remain.

- `test_az5h2_expired_inbound_refuses_before_storage`
- `test_az5h2_remaining_budget_sqlite_wait_keeps_inbound_deadline`
- `test_az5h2_normal_accepted_ids_are_preserved` (int `2` and string
  `"activity-ok"`)
- `test_az5h2_deadline_and_rate_refusal_frames_stay_within_wire_cap`
- `test_az5h2_protocol_rejection_uses_null_id_and_releases_admission`
- `test_az5h2_typed_error_frame_is_capped`

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5h2.py
```

**7 passed**, 2.14 s.

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_ba5_acceptance.py
```

**2 passed**, 2.56 s.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5h.py
```

**7 passed**, 3.89 s.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5d2.py
```

**2 passed**, 1.50 s.

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

- `library_analysis.py` — inbound `admitted_at` as activity start;
  refuse before storage; remaining-budget SQLite waits; restore
  `PRAGMA busy_timeout`
- `uoink_mcp.py` — inbound envelope bound; completed-frame cap on
  typed errors and replacement refusals; null-id protocol rejection
- `tests/test_phase5_az5h2.py` (new)
- `docs/library/PHASE5-AZ5H2-GROK-2026-09-08.md` (this report)

No Astra test or helper edits. No installed SDK edits.
`git diff --check` clean. Measurement documents were not edited.

## Now-stale measurement assertions (AZ-5g2)

Do not change measurement documents in this run. Observed this session
from the existing synthetic capture (not a new sealed record):

| Fixture | Observed raw JSON bytes | Actual stdio bytes (handler capture) |
|---|---:|---:|
| 548-item cost fixture | 58,035 | 64,732 |
| 10,000-item cost fixture | 57,968 | 64,601 |

Published measurement doc still 58,738 / 58,640. Injected deadline raw
envelope is 190 bytes `deadline_exceeded` / `retryable: true` with
message `Service deadline exceeded before lock acquisition`. 70 MiB
journal refusal 221 raw bytes. Transport-ser 0.55–0.67 ms / 64,743
bytes. Shedding is still described as absent (20 creator rows observed).
Replay is still described as skipped. The Transport Serialization row
still claims "actual stdio adapter".

## Commands and observed counts

Environment: `PYTHONDONTWRITEBYTECODE=1`, PYTHONPATH = worktree +
`site.getusersitepackages()` + `win32` / `win32/lib` / `pythonwin`
(resolved before APPDATA redirect), worktree-local APPDATA/TEMP under
`_scratch/az5h2`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, no
`ANTHROPIC_API_KEY`.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5h.py
```
**7 passed**, 3.89 s

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5h2.py
```
**7 passed**, 2.14 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_ba5_acceptance.py
```
**2 passed**, 2.56 s

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5d2.py
```
**2 passed**, 1.50 s

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase5_az5d2.py tests/library_work_astra/test_phase5_ba4_acceptance.py
```
**2 passed, 1 failed**, 1.40 s. Failure is the frozen BA-4 SDK-route probe.

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_acceptance3.py
```
**51 passed, 1 failed**, 7.15 s. Failure is the frozen unary/clock TypeError.

```
python -B -m pytest -q -p no:cacheprovider tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py
```
**84 passed**, 6.94 s

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase5_measurements.py tests/library_work_astra/test_phase5_measurements2.py tests/library_work_astra/test_phase5_measurements3.py
```
**4 passed, 4 failed**, 69.55 s. Failures are the four AZ-5g2 measurement-document cases.

Combined union (AZ-5h + AZ-5h2 + AZ-5d2 + BA-4 + BA-5 + BA-3 modules +
AZ-5 adapters + dashboard companions + Phase 4 resources/prompts/briefs
+ registry/docs extras), `--junitxml=_scratch/az5h2/combined.xml`:

**570 passed, 6 failed**, 132.10 s.

## Remaining failures (not passes)

1. `test_ba4_actual_sdk_serialization_retains_admission_and_deadline` —
   frozen SDK `stdio_server` route; success with `active admissions=[0]`.
   Report only; the shipped entry is covered by `tests/test_phase5_az5h.py`
   and `tests/test_phase5_az5h2.py`.
2. `test_phase5_ba3_final_wire_serialization_is_inside_deadline` —
   TypeError at `stdio_result` (`clock=` into a unary probe). Ryan.
3. `test_phase5_ba2_measurement_document_payloads_match_capture` — AZ-5g2.
4. `test_phase5_ba3_measurement_record_acknowledges_observed_row_shedding` — AZ-5g2.
5. `test_phase5_ba3_measurement_record_does_not_claim_replay_was_skipped` — AZ-5g2.
6. `test_phase5_ba3_measurement_record_labels_handbuilt_transport_timing` — AZ-5g2.

Astra's tests were not edited. No commit.
