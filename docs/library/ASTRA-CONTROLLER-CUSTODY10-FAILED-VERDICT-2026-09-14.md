# Controller10 failed qualification — 2026-09-14

The first controller10 invocation failed: **8 passed, 2 failed, 0 skipped**;
104 subtests ran, with **102 passing and 2 failing**. Source checkpoint is
`71df9d3`; admission `405207/0` selected author PINS `25f30270`, and actual
`6ba3f1/1` records the outer failure. The original result remains failed.
The confirmation copy has not been admitted or run.

Root `edc0e3/0` and independent `6606ae/0` verify the failed record, not a passing qualification: all
fifteen source inputs, three controls and eleven child hashes match, all ten
guards hold, 23 output files are present, stderr is empty and child/qualification
exits are both 1. The result has no guard denials, registry denials or heavy
imports; twelve metadata and 25 registry traps remain installed.

Two subcases expected the wrong exception family. The wrong-permit input is
refused by the existing factory's `SessionClosed("Native permit is stale or
already consumed")` check. The active-owner fault reaches the new fixed factory
check after bind and raises `SessionClosed("Factory start owner is not live and
unpublished")` before resume. `SessionClosed` is a sibling of
`LifecycleUnavailable`, not its subclass. The tests already import it, but
their shared REFUSALS tuple contains only AdapterUnavailable/LifecycleUnavailable.

The wrong-permit case therefore leaves assertions 149–155 unexecuted; the active
case leaves assertions 301–309 unexecuted. Those retention, restoration and
no-resume checks remain unverified for the two inputs. The earlier source review
missed this exception mismatch; a successful review did not establish execution.
Neither observed refusal justifies changing the product exception hierarchy or
weakening the source checks.

The proposed correction changes only the two relevant expected-exception
arguments: select SessionClosed for wrong_permit at line 128 and for active at
line 300; preserve the existing expectation for every other fault. Keep global
REFUSALS, all inputs, messages, IDs, helper bodies and later assertions unchanged.
The exact unapplied diff is SHA256 `f1c8950dfbe84ddbeb5838cdc518a25a2c5eaed2011802ea8dab7e1c25aa4e8a`,
under `proof/controller-custody10-failed-2026-09-14/test-contract-diagnosis/PROPOSED-EXPECTATIONS.UNAPPLIED.patch.txt`.
Independent failure verdict `01ebffd7` and author diagnosis `de4e20a2` agree on
the existing exception contract; the latter is not an independent test review.
This assertion edit requires Ryan's approval. His earlier approval at `58335df`
was limited to the two older KernelUnconfirmed expectations and does not apply.

After approval, use a fresh documented repair brief and new input/run identities,
review the complete corrected test delta and instruments, then separately admit
author and confirmation. Preserve this failure and all original bytes. No rerun,
confirmation, model/D1/D2 access or native invocation follows from this verdict.
Source-only preparation for the separate generated Windows compatibility check
may continue, but its invocation waits for corrected controller qualification.
