# AV-5m4b2: finish lifetime and exclusion after AW-5

Engine: Grok. Read AV-5m4b, AW-4 and this brief. AV-5m4b `5c22dbae` is
rejected, with its complete original production diff, seven proposed tests
and report retained in `patches/av5m4b-grok-rejected-2026-09-08.patch`.
The integrator's full union produced **214 passed, 14 failed**, 65.52 seconds
(`av5m4b-wi`): the eight old parent interceptors, four AW-4 cases assigned
to AV-5m4a2, and two of the new child-timeout tests. The latter returned
success where a timeout refusal was expected. The worker reported those
seven tests passing separately; that does not replace the failed combined
observation. Diagnose and record this difference in the repaired full union.
Start from current `cc/living-library`. Three-way apply that patch, preserving
any concurrently integrated binding/temp-identity work from AV-5m4a2.

New frozen `tests/library_work_astra/test_phase4_aw5_acceptance.py` has
**two failed, one passed**, 6.84 seconds in the worker (`aw5-review`).
Real parent loss correctly kills the assigned Windows child; retain that
repair. The other two findings prevent acceptance:

1. `_sqlite_reserved_lock_available` confuses another connection's write
   reservation with our ownership. With our deferred read open and a second
   connection in BEGIN IMMEDIATE, the probe is busy and our publication is
   incorrectly admitted. Establish exclusion on the actual authoritative
   connection (without rollback or changing user rows), or positively prove
   that connection owns it. A third-connection failure cannot prove who owns
   the lock. Preserve active caller work and the valid write-transaction case.
2. The new destination-local lease write runs in the caller before the
   cancellable work starts. Blocking that write traps resync beyond five
   seconds despite a 0.1 s publication budget and separate 2 s startup and
   termination bounds. Move every destination lock/lease access that can
   block into an appropriate cancellable boundary. Keep cross-process
   exclusion stable across TEMP/profile roots. Do not move unbounded vault
   writes to a Python thread that may mutate after timeout. A stable local
   kernel lock with isolated destination I/O is one possible design; choose
   a design that proves the required behavior, not a fixture-specific path.

Also inspect late local intent/cleanup mutations: the timed-out parent thread
may still be finishing a path/hash read. Every later local write or deletion
must remain bound to its original generation, not a later resync's current
intent. Keep exclusion until all old mutators are unable to write. Unknown
process liveness or unreadable ownership must refuse, not mean dead. Audit
lease-write failure after startup for leaked child/job ownership. Record
separate timings and total caller time honestly.

Run the full AV-5m4b named suites, the unchanged AW-5 file and focused new
implementation tests for these findings and late intent preservation. The
three new AW-5 acceptance tests are frozen. Existing committed tests/helpers
are frozen. The seven *unintegrated proposed implementation tests* in the
retained patch may be revised where they asserted a particular lock-file
location instead of the contract; retain their original version in the patch,
explain that change, and preserve their cross-process exclusion, child-death
and user-edit assertions. Do not weaken a required outcome.

AV-5m4a2 owns authority binding, temp identity and staging. Avoid unnecessary
edits there. Any overlap must be listed for Astra's three-way integration.
Write `docs/library/PHASE4-AV5M4B2-GROK-2026-09-08.md` immediately, then record
exact commands/results and unresolved limits. No live index, port 5179,
models, API key, paid API, commits, pushes or subagents. Apply stays false.
Use short disposable roots and resolved dependencies. No Phase 4 acceptance
claim before Astra's independent worktree/checkout verification and AW-4 closeout.
