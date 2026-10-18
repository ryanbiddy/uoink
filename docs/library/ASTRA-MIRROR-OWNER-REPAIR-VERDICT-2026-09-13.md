# Writer admission now survives preparation

Accept the bounded owner reservation repair. Before the patch, a normal sweep
could release a newly acquired writer gate before prepare attached its session.
The controlled original probe failed at b62aab3 and remains sealed at 92c0fde.
After the patch, the same interleaving retains the gate until cancellation;
acquire and release occur on the same owner thread.

A new owner reserves admission before its thread exposes the acquired gate.
Context reuse also reserves it. Preparation transfers that hold to the session
and drops the reservation on success or failure. A sweep rechecks concurrent
reservations and attachments before stopping the owner. Stopping owners refuse
new work, and owner-thread waits happen outside the global guard. Unknown or
launching children continue to retain admission.

The worktree passed twelve focused cases, including the unchanged original
diagnostic, and all 184 Phase 4/new-owner cases in 118.28 s. Astra applied its raw
Git diff with git apply --3way. The checkout passed the same twelve focused
cases and all 184 Phase 4/new-owner cases in 126.38 s. Eleven new regression
cases are added; no existing test, fixture, mark or assertion changed. Git blob
checks bind the same source and tests in both roots.

The first draft's eleven passes did not expose recursive entry into the
non-reentrant global guard. Independent review caught it before broader tests.
The corrected draft detaches under the guard without reacquiring it, and adds
a strict-guard test for ordinary stale cleanup. A further review change makes
thread exceptions fail the concurrency cases. Both earlier drafts and all
focused outcomes remain in the proof bundle. Final independent static review
found no further actionable reservation or cleanup defect; that reviewer did
not execute the suites. Astra performed the runs above.

This accepts the owner handoff repair only. It does not establish the cause of
tree08's fifty mirror failures, clear its failed result, or authorize release.
Gemini process-authority repair c1008e0b is still in progress. Qualify the combined
source afterward with a fresh complete tree and installed package evidence.
Package09 has not been built. Websites and marketing remain paused.
