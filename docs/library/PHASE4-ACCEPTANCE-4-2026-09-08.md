# AW-4: isolated writer integrated, Phase 4 still unaccepted

AV-5m3 removes test-specific cancellation and moves vault mutation to a child
process. The integrator applied it with three-way integration after independent
verification. Worker and checkout each produced **209 passed, eight failed**,
64.43 s and 67.72 s. This is an intermediate implementation, not acceptance.

The eight failures are unchanged parent-process replacement interceptors:
AW's purge-temp case, AW-2's blocked replacement, three AW-3 temp cases and
three AW-3 cancellation cases. The child performs the real syscall, so the
parent's patched callback is never entered. The D13 user-edit contradiction
also remains. Ryan must authorize fixtures that observe the actual isolated
boundary while preserving their behavioral assertions. These results stay
failed; seven new implementation-test passes cannot replace them.

Four additional frozen reproductions are in
`tests/library_work_astra/test_phase4_aw4_acceptance.py`. All four fail
(2.43 s; `_scratch/aw4-review`) on the integrated AV-5m3 content:

| Finding | Observed behavior | Required repair |
|---|---|---|
| AW4-01 | Delete the prior binding and replace the vault with an empty directory. Resync returns success and exports under old consent. | Missing prior binding must require reconciliation. Preserve independent evidence of prior authority; absence cannot mean fresh consent. |
| AW4-02 | Fail `_atomic_local` during a binding update. The prior binding bytes have already changed. | Remove the direct write before atomic persistence. Preserve prior durable state on failure. |
| AW4-03 | Replace an allocated temp with a different file containing identical bytes. Cleanup deletes that replacement. | Bind allocation to file identity as well as path/hash; validate current identity at the destructive boundary. |
| AW4-04 | Run the real source-only staging path. It succeeds but omits `library_mirror_vault_io.py`. | Include the required worker in source validation and every package staging path, and verify its launch from the stage. |

The worker lifecycle also needs repair from source review before D13 can close:

- `terminate` suppresses a wait timeout, clears the lease and forgets the process
  regardless of whether death was established. Windows job assignment is not
  checked; API declarations omit pointer-sized handle signatures.
- The old parent thread can remain alive after timeout. It accesses mutable
  `self._vault_io`, `_active_plan` and `_active_key`; a subsequent resync can
  replace those objects. The operation must retain its own immutable session
  and cancellation state so late work cannot use a new writer.
- Lease/lock names depend on each process's temporary directory. Processes
  addressing the same vault with different temp roots can evade exclusion.
- The seven new tests kill a real child, but the timeout scenario blocks the
  parent `_atomic_vault` function. Add evidence at the child boundary and during
  parent loss; do not describe the current tests as a hung-syscall observation.

These are implementation tasks, not Ryan decisions. Bound total startup,
publication and termination time, reporting their separate measured components.
Do not hide a 15-second startup or a termination wait outside a claimed
two-second end-to-end budget. Preserve current source/dependency checks and
the caller's SQLite work; an inherited deferred read transaction is not proof
of an existing SQLite write lock.

D14's exact index intent and the earlier D01-D03/D07-D10 reproductions remain
green. Final AW-4 regression/client acceptance waits for the repair briefs.
The real-client rerun has not started; the old AW receipt stays partial and
installed Inno receipts remain Ryan's gate. No live index, helper or model was
used for this review.
