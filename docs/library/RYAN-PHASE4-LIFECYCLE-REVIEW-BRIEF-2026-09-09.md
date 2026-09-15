# Preserve a cancelled operation after child cleanup

Astra's final review of lifecycle worker `cc391d36` distinguishes two
contexts: a finished standalone helper and a resync plan still unwinding
after cancellation. The worker unbinds both when the originating thread
confirms child death. A plan can still hold the cancelled operation.

Run one new synthetic review case before accepting the diff: start an actual
isolated helper, bind a resync-shaped plan to that session, cancel it and
confirm termination on its originating thread. A subsequent destination lease
write from that still-bound plan must refuse, without starting a replacement
worker or writing destination bytes. Use the current isolated integrator
guard and the unchanged AW environment. Existing tests remain frozen.

Also terminate the original helper from a different thread, then hold a new
actual helper and its lease on another thread. The original thread retains
its dead operation binding and cannot read the destination. Its ownership
check must still report blocking ownership while the new helper is alive.
This separately tests the worker's unreadable-lease exception.

If it fails, preserve the complete worker patch, failed probe and named union.
Limit the correction to distinguishing standalone-helper cleanup from a bound
operation. Keep the cancelled plan's authority fence until its owning scope
unwinds. An unreadable lease must continue to block admission: proof that our
old child died does not prove a foreign owner absent. Remove any exception
that treats those two facts as equivalent. Do not relax exclusion, late-write
refusal, actual Thread identity, launch retention or foreign-helper controls.

Verify the new case, AV-5m4b7 followed by the original lifetime file, then the
complete named lifecycle/AW/mirror union in both roots. Any additional failures
remain visible and need source review against the prior baseline. No test
reordering can turn a failed measurement into a passing one. No live index,
5179, models, paid API, commits by workers or new fetch.
