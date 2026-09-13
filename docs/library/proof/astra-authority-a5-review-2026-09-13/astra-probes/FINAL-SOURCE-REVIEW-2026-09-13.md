# Grok a5e7ba0d final source review

Verdict: hold this proposal for two remaining repairs. The review covers the
finished worker source, its report, and the fourteen handle-lifetime controls.
No product files or worker files were changed by this reviewer. No test,
compiler, process API, native gate, model, network, or installed-state action
was executed. Astra owns independent verification of the worker's suite and
the four corrected scratch probes.

Worker: `a5e7ba0d-26f2-401b-973c-e2d0cb0bb884`.
Worktree: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\a5e7ba0d-26f\grok`.
HEAD: `4b8dc95912ae74fcdcc0dccf5f9d862d08207fb2`.
Reviewed Git diff: `library_mirror.py`, blob `fe1d3d6` to `4681cf0`.

## P1: a distinct ready writer bypasses relationship verification

At `library_mirror.py:1936`, launch accepts the ready message's numeric writer
PID. For a writer distinct from the launcher, line 1941 reads the current
creation time of that PID. `owned_pids()` then adds this writer at line 1644
before verified child discovery. The discovery loop skips an already-seen PID
at line 1659. A later job assignment at line 1951 therefore accepts the newly
recorded identity without proving that process is the writer or a child.

The concrete boundary is a distinct writer that sends its ready line and then
exits before the PID lookup. Its PID can identify a foreign replacement when
the lookup occurs. This case does not recycle the launcher's PID or disregard
its retained Popen handle. The foreign writer need not appear in any Toolhelp
relationship snapshot: the direct ready path has already registered it.

The corrected scratch probe drives actual `launch()`, adoption, ownership,
and fake `AssignProcessToJobObject`. Relationship discovery returns no valid
child, while the distinct writer PID describes a foreign epoch. It checks
registration and the assignment recorder together. Execution is pending with
the integrator; this review does not supply a pass/fail count for that probe.

Validate and retain the distinct writer's original identity before registering
it, then use that authority for assignment and termination. Apply the same
policy when a bind response changes the writer PID; carrying over the previous
writer timestamp cannot establish the new process's identity.

## P1: failed acquisition releases another caller's job lease

At lines 1948-1953, launch calls `_release_job_handle()` in `finally` even if
`_acquire_job_handle()` returned `None`. Cancellation can set `_dead` while
`terminate()` owns the job lease acquired at line 2292. Launch's acquisition
then refuses at line 2220, but its unconditional release decrements that other
caller's use count. The count can reach zero while fake or real job termination
is still using the handle, defeating the intended deferred-close guarantee.

The scratch probe drives real launch and termination callers. It pauses an
inert job-termination callback after acquisition, resumes the cancelled launch,
and checks that the terminator's lease remains in use. It releases the pause
and joins its Python test thread in `finally`. This exercises the production
caller; the worker's direct helper tests do not cover this interleaving.

Release only a lease that this invocation acquired, preferably through a token
or context manager. Audit the corresponding process-handle loop at lines
2302-2310: it also releases an existing wrapper after a failed acquisition.
That second occurrence is a repair audit item, not a separately reproduced
production interleaving in this review.

## Scope and corrections

The final diff does not modify the accepted `ff67b84` exclusion-owner
reservation, attach/sweep definitions, or the prepare reservation-release
finally block. The same-PID writer branch now reuses the launcher's recorded
creation identity. Existing unknown-child retention and distinct-epoch cases
remain represented in the worker tests.

The worker reports 32 passed and 3 failed in its first new-control attempt,
then 35 passed after documented fixture setup corrections. Those are worker
reported measurements, not tests executed by this reviewer. Both attempts are
described in the reviewed report; the failed attempt must remain retained.

The first scratch draft's missing-original-creation fallback probe was invalid:
it retained Popen's original handle while inventing reuse of that same numeric
PID. It was withdrawn before execution. Its bytes, exact removal diff, and
reason remain beside this verdict. No retained-Popen raw-PID fallback defect is
claimed here. No same-millisecond counterexample is claimed either. The two
findings above do not establish the cause of tree08's fifty mirror failures.

## Reviewed SHA256 hashes

| File | SHA256 |
|---|---|
| `library_mirror.py` | `073058f98829fc7bb9359812b9e3d85828f08ce956d65a01441794987ffc752f` |
| `docs/library/MIRROR-AUTHORITY-REPAIR02-GROK-2026-09-13.md` | `ae020118c0417c8d3cac86a93df5c65a8856b7291bb31ecaef0f71f8a0bf8d66` |
| `tests/test_mirror_process_handle_lifetime.py` | `1fec835cf12cded6bb0f78564b2085354863ad2c6e821c0c28419cb009b74379` |
| `tests/test_library_mirror_process_authority.py` | `74221830187d566a9bede12ff01dfaf61ed674e9bfb6581a7ab4bac2550bf602` |
| `tests/test_mirror_process_identity_boundaries.py` | `b621d87273d75ee2fee84c8c73f78f98dd3809f6e19e1161ec8bfcc1cb8679c3` |
