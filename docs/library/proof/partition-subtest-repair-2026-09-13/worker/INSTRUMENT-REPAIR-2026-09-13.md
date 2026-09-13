# Receipt I/O repair before unit03

The unit02 attempt is incomplete. Raw pytest and the outer verifier both exited 1, the log records an internal observer callback error, and no partition session receipt was produced. Do not assign a completed pass/fail count to that attempt.

The unchanged mirror observer test `test_invalid_paths_are_rejected_before_open` replaces `Path.open` with a rejection function while its call report is delivered. The partition receipt callback attempted a fresh `Path.open` for every report, so this test's controlled replacement interrupted the observer. The synthetic probe used the same pattern. Executed source snapshots and hashes are retained under `unit02-launch/inputs`; the partial report files and raw verifier logs remain unchanged.

Repair only those two instruments: open their fresh JSONL streams during startup, write and flush each report through the held stream, and close it at session finish. This preserves per-report evidence and avoids calling a test-replaced filesystem entry point during reporting. No test, fixture or product code changes. Unit03 repeats the same 116-case synthetic selection under a fresh label after this documented repair. The deliberate failed native03 smoke remains valid evidence; collection/pass checks use fresh labels against the final instrument bytes.

Native04 repeats the deliberate combined failure smoke after the same stream repair, with partition receipts, the passive mirror observer and the heavy-import guard active together. Its expected failure is preserved; this confirms the final instruments capture failed subtests and promoted parent reports as well as passing reports.
