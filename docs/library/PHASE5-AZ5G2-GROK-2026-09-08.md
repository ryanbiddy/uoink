# Phase 5 AZ-5g2 session (grok)

Worker: grok
Run: AZ-5g2 (complete and seal the final measurement record)
Base: `d1d5fb8b3eca802f14ae53de3d6562df30b9129d` (`079170c1f70f4addcfaed15006a51f751ae60f67` git tree).
AZ-5h2 is integrated at `45bb2f6`. Do not commit. Astra independently verifies
both roots and completes BA-4. No acceptance claim.

No paid API, no `ANTHROPIC_API_KEY`, no model, no live index, no port 5179.
`librarian_apply_enabled` stays false. Astra's tests were not edited.
No existing test/helper, production, adapter or contract edits. No subagents.
No commit or push. Apply remains false.

Python 3.14.6. Installed `mcp 1.28.1`; package pin `mcp==1.27.1`.
Disposable profile/output/temp under `_scratch/az5g2`.
User site-packages plus `win32`, `win32/lib`, `pythonwin`, and
`pywin32_system32` resolved on `PYTHONPATH` before APPDATA redirect.

## Status

Complete as a measurement-only candidate, uncommitted. The actual shipped
stdio entry (`bounded_stdio_server` / `run_bounded_stdio_async`) was driven
on this checkout. Complete reader packets and JSON-RPC frames are retained.
Named verification union: **574 passed, 2 failed**, 132.08 seconds.
Logs: `_scratch/az5g2/combined.xml`.

The two remaining failures are the frozen BA-4 SDK-route probe and the
unary/clock TypeError (Ryan). The four stale measurement-document
assertions assigned to this refresh now pass. This run does not claim
Phase 5 accepted.

## Pre-refresh archive (byte-exact)

| Field | Value |
|---|---|
| Working-tree bytes | 9684 |
| Working-tree SHA-256 | `4745bd1db6efcd14e9b0aeb930ba0193981e4024b0ec91f4ad27a1f96da20ea0` |
| Git blob | `c3c8e1b72d3354bdfe85b1ce881e1e765aa28ea0` |
| Source commit | `d1d5fb8b3eca802f14ae53de3d6562df30b9129d` |
| Source tree | `079170c1f70f4addcfaed15006a51f751ae60f67` |
| Archive | `docs/library/proof/az5g2-2026-09-08/original-PHASE5-AZ-MEASUREMENTS-2026-09-08.md` |

Failed assertions retained in that original document:

1. Row shedding described as absent (`without pruning` / `row shedding did not occur`).
2. `baseline replay path was skipped`.
3. Hand-built transport serialization labelled as `actual stdio adapter`.
4. Stale raw JSON byte counts 58,738 / 58,640.

## Rejected AZ-5g artifact (not acceptance)

`docs/library/patches/az5g-gemini-partial-rejected-2026-09-08.patch`
SHA-256 `88a91ef8f62839f7f180683bcc03dc17105d6771d37b597fc6dec56bc91148b8`.
Extracted partial JSON:
`docs/library/proof/az5g2-2026-09-08/rejected-az5g-gemini-5e9baea5-partial-measurements.json`.

That partial hardcodes `git_tree_hash` to the old document blob, uses
returned sample lengths (and null event totals) as `totals`, omits complete
packets and wire frames, and predates AZ-5h/AZ-5h2. It is reference only.

## Measurement

Harness: `python -B scripts/measure_phase5_az5g2.py` (exit 0, ~50 s after
fixture seed). Machine-readable record:
`docs/library/proof/az5g2-2026-09-08/observations.json`.
`uoink_mcp.mcp.run_stdio_async is uoink_mcp.run_bounded_stdio_async` = True.

Shipped-entry frames are exact `stdout.write` bytes from
`bounded_stdio_server`, including the terminating newline in the proof
files. Table JSON-RPC sizes are completed UTF-8 before that newline (the
65,536-byte cap). Handler-only dumps and the hand-built envelope are
labelled by scope and are not the shipped entry.

| Path | Raw reader JSON | Shipped JSON-RPC | Notes |
|---|---:|---:|---|
| 548 primary | 58,035 | 64,732 | events 0/550 shed; joint 12/20; creators 20/20; live reader through shipped entry; `isError` false |
| 10,000 primary | 57,968 | 64,601 | events 0/10002 shed; joint 13/50; creators 20/50; `isError` false |
| 548 proved replay | 57,894 | 64,595 | `journal_complete`, empty reasons |
| 548 three memberships | 57,671 | 64,362 | 1,644 memberships; journal 405,026 |
| 50 items / 10 operations | 34,917 | 39,378 | `journal_complete`; journal 234,590 |
| 100k observations | 28,790 | 32,351 | `no_history`; no journal |
| 70 MiB journal refusal | 221 | 329 | `resource_too_large`, `retryable` false; shipped `isError` true |
| Injected reader deadline | 190 | — | `deadline_exceeded`, `retryable` true, before lock acquisition |
| Shipped expired inbound | — | 295 | AZ-5h2 original deadline; `isError` true; message `Service deadline exceeded during serialization` |
| Hand-built envelope | — | 64,743 | labelled hand-built; 0.47 ms; does not invoke stdio |
| Handler-only 548 / 10k | — | 64,732 / 64,601 | captured packet through request handler; not `bounded_stdio_server` |

Replay projection on the 548 primary interval was observed populated
(`replayed_state_observed=true`) before `interval_precedes_first_apply`.
Journal 548 = 214,596 bytes (209.6 KiB). Q1/Q3 on the actual 548 fixture:
`SCAN yoinks USING INDEX sqlite_autoindex_yoinks_1` and
`SCAN library_applies USING INDEX sqlite_autoindex_library_applies_3`.

Timing vs tracing (not equivalent):

| Pass | Time | Label |
|---|---:|---|
| 548 untraced construction | 61.22 ms | normal |
| 548 traced heap | 1004.96 ms / 5253.9 KiB | diagnostic tracemalloc, 2.0 s deadline |
| 10k untraced construction | 641.30 ms | normal |
| 10k traced heap | 16057.02 ms / 78388.7 KiB | diagnostic tracemalloc, **30.0 s relaxed deadline** |
| 70 MiB traced heap | 18.7 KiB | diagnostic; not a normal timing result |
| Deadline traced heap | 5.9 KiB | diagnostic |

The 24,576-byte dashboard target is missed (58,035 / 57,968 raw;
64,732 / 64,601 shipped). That is a target, not a fixed
acceptance-blocking limit. The fixed envelope is 65,536 completed UTF-8
bytes. Construction times and heap figures are measured observations, not
guarantees.

Unmeasured here (not claimed passing): concurrent load / rate-limit
enforcement, concurrent WAL snapshot isolation, a combined
10k-item + 100k-observation + full-journal case, and blocked-lock remaining
budget as a timing row (AZ-5h2 tests cover that path).

## Named verification union

Explicit selectors in `scripts/run_phase5_az5g2_union.py` (task-specific
tuple, never PowerShell `$args`). First Windows `os.execv` attempt did not
wait; the runner now uses `subprocess.run`.

```
python -B scripts/run_phase5_az5g2_union.py
```

**574 passed, 2 failed**, 132.08 s. JUnit `_scratch/az5g2/combined.xml`
(`tests="576" failures="2" errors="0"`).

AZ-5h 7/7, AZ-5h2 7/7, AZ-5d2 2/2, BA-5 2/2, all three measurement
generations (including the four previously stale document cases) pass.

## Remaining failures (not passes)

1. `test_ba4_actual_sdk_serialization_retains_admission_and_deadline` —
   frozen SDK `stdio_server` route; success with `active admissions=[0]`.
   Report only; the shipped entry is covered by `tests/test_phase5_az5h.py`
   and `tests/test_phase5_az5h2.py`.
2. `test_phase5_ba3_final_wire_serialization_is_inside_deadline` —
   TypeError at `stdio_result` (`clock=` into a unary probe). Ryan.

The four document assertions assigned to this refresh now pass:

- `test_phase5_ba2_measurement_document_payloads_match_capture`
- `test_phase5_ba3_measurement_record_acknowledges_observed_row_shedding`
- `test_phase5_ba3_measurement_record_does_not_claim_replay_was_skipped`
- `test_phase5_ba3_measurement_record_labels_handbuilt_transport_timing`

## Environment and commands

`PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, no
`ANTHROPIC_API_KEY`. PYTHONPATH = worktree + user site-packages +
`win32` / `win32/lib` / `pythonwin` / `pywin32_system32` (resolved before
APPDATA redirect). Worktree-local APPDATA/TEMP/UOINK_OUTPUT_DIR under
`_scratch/az5g2`.

```
python -B scripts/measure_phase5_az5g2.py
```
exit 0. 548 raw 58035 / shipped 64732; 10k raw 57968 / shipped 64601;
replay observed True.

```
python -B scripts/run_phase5_az5g2_union.py
```
**574 passed, 2 failed**, 132.08 s.

```
git diff --check
git status --short
```
`--check` clean after removing markdown hard-break trailing spaces.
No production, test, helper, adapter or contract edits.

## Files changed

- `docs/library/PHASE5-AZ-MEASUREMENTS-2026-09-08.md` (regenerated after archive)
- `docs/library/PHASE5-AZ5G2-GROK-2026-09-08.md` (this report)
- `scripts/measure_phase5_az5g2.py`
- `scripts/run_phase5_az5g2_union.py`
- `docs/library/proof/az5g2-2026-09-08/` (byte-exact original, rejected extract,
  packets/frames, observations, SHA-256 manifest)

No commit.
