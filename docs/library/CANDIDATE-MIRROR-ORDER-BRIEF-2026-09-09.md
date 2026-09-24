# Candidate full-tree mirror investigation

Frozen candidate `6c313ea` completed the full tree with only S21 excluded:
2,102 passed, 92 failed, three skipped, one existing xfail, 550.41 seconds.
Retain this failed result. Relative to the earlier 26-failure baseline, 67
additional failures are mirror-related and one old D15 assertion no longer
fails. That absence does not overturn the frozen D15 ruling: surrounding
exports now refuse before the behavior that the old test was meant to observe.

All seven initial AW-10/11/12 ownership tests passed. The first extra failure
is AW-2 `test_d09_resync_repairs_missed_refresh`, whose initial ordinary export
returns `destination_unavailable` with OSError. Later mirror checks fail at
the same setup boundary. The focused 32-file union previously passed 286
tests with nine frozen failures in a different file order. This establishes
a question about retained state; it does not yet prove test contamination or
an implementation defect.

Run a bounded diagnostic prefix in the full-tree order: AW-10, both AW-11
files, both AW-12 files, then the first failing AW-2 export. Keep tests and
assertions unchanged. A scratch-only observer may record live/retained owner
and session identities before/after tests and record/rethrow startup errors;
it must not reset global state, release a gate, kill a writer or change a
result. If the reduced prefix does not reproduce, extend only from the
recorded original test order. Preserve every diagnostic result and command.

Identify the first retained owner/lease condition and its source. Repair only
after a concrete reproduction and written repair scope. If a real product
defect is found, add an independent reproduction and follow the worker/
integration verification loop. If a frozen test's setup is inconsistent with
the contract, record its exact cause for Ryan; do not edit it or quietly
replace the full tree with passing shards. A new full-tree run requires the
documented repair and a fresh receipt. Hold the installer build until this
additional failure set has a supported disposition.

The first diagnostic reproduced seven passes followed by the failed ordinary
export in 9.15 seconds. It showed no retained session, live exclusion owner
or held mutex. The log instead reports `operation is no longer live` from
the thread-local I/O binding. Extend the observer with that binding and its
dead/session identity; the original observer omitted this field. Run only
AW-11's put case followed by the first failed AW-2 export. This is an
instrumentation repair against an already reproduced diagnostic, not a new
full-tree attempt. Do not clear the observed context.

The two-case diagnostic reproduced one pass/one failure in 2.51 seconds.
AW-11's teardown calls `session.terminate()` and directly sets
`env.mirror._vault_io=None`. The exact dead session remains in the main
thread's `_IO_CTX.session` after teardown and before the next fixture. No
process, mutex or exclusion owner remains. Production `_stop_vault_io` and
`_kill_vault_io` instead call `_forget_session` after proven death, clearing
the originating binding. Do not remove that refusal from production: it
protects late helpers from adoption of a new operation.

Record a separate synthetic control of two ordinary production event/resync
lifecycles and of an originating private helper closed through the production
stop method, followed by a fresh ordinary export. Inspect context and process
state without resetting it. This does not repair or rerun the original tests.
If the control succeeds, request Ryan's ruling for consistent teardown of
the frozen private-helper fixture, retaining the failed combined suite and
the old D15 failure rather than treating its contaminated pass as closure.
