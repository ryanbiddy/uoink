# AV-5m4b: close isolated-writer lifetime and exclusion gaps

Engine: Grok. Start at current `cc/living-library`, containing AV-5m3.
Read `PHASE4-ACCEPTANCE-4-2026-09-08.md`, AV-5m3 and AW-3. Repair the
lifecycle findings in AW-4 as general behavior. This run can proceed beside
AV-5m4a, which owns destination binding, temp identity and package staging.

1. Establish child lifetime and death. Use correct pointer-sized Windows API
   declarations, require successful kill-on-close job assignment before any
   vault mutation, and fail closed on startup/assignment failure. On POSIX,
   terminate the process group as claimed. Keep exclusion/lease until death
   is confirmed; do not suppress wait failure, clear the lease and forget a
   potentially live writer. Bound startup and termination, report separate
   timings and total caller time. Do not claim two seconds by excluding
   unbounded preparation or a 15-second startup.
2. Bind the parent work to its own immutable I/O session and cancellation
   token. A timed-out parent thread must never use a new resync's session,
   plan, key or local intent state. Preserve cross-instance/process destination
   exclusion until every old mutator is unable to write. Late cleanup cannot
   touch a newer generation. Avoid fallback from failed isolated I/O to an
   unbounded parent read of the disconnected vault.
3. Use a stable destination lock/lease namespace across processes with
   different temp/profile roots. Protect ownership against PID reuse and
   corrupt/missing live ownership records; a best-effort JSON PID alone is
   not an exclusive lease. Keep existing scope/manifest/dependency checks.
4. `BriefStore._sqlite_writer_exclusion` preserves an active transaction now,
   but a deferred read transaction need not exclude another writer. Refuse
   or safely establish exclusion without rolling back caller work. Keep the
   valid active write-transaction case and idle independent-writer check.

Add focused new implementation tests for actual child-boundary cancellation,
parent loss, an independent user edit, later resync on the same Mirror, a
second process with a different temp root, and the inherited deferred read
transaction. Never inspect callback closures, inject async Python exceptions,
roll back destination bytes or modify any existing test/helper. The eight
frozen parent os.replace interceptors remain failed observations for Ryan.

Avoid unnecessary edits to binding/temp-ledger/staging regions reserved to
AV-5m4a. Coordinate through the final report; Astra integrates both with
three-way apply. Run AW/AW-2/full AW-3, seven AV-5m3 implementation tests,
resources, prompts, briefs, mirror, mirror wiring, Phase 4 stdio and C01 plus
your new tests. AW-4's four known failures are assigned to AV-5m4a; report them
without attempting overlapping repairs.

Write `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` early, with exact
commands, observed timings/counts and limits. Use short disposable roots and
resolved dependencies. No live index, port 5179, model, API key, paid API,
commits, pushes or subagents. Apply remains false. Astra verifies independently
and completes AW-4 before the real-client rerun.
