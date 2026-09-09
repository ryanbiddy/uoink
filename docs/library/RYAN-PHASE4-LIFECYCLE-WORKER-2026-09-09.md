# Phase 4 lifecycle worker report (Grok, 2026-09-09)

Worker: Grok. Worktree: dedicated Control Room tree for run `cc391d36-97f`.
No commit, push, existing-test edit, live index, port 5179, model subprocess,
or paid API. `ANTHROPIC_API_KEY` unset. Integrator verifies independently.

Interpreter: `C:\Python314\python.exe` 3.14.6. User site-packages
`C:\Users\hello\AppData\Roaming\Python\Python314\site-packages`. Guard and
`sitecustomize` copied from
`docs/library/proof/ryan-corrected-01-2026-09-09/`. Disposable profile under
this worktree `_scratch/<label>`. No other checkout is referenced from worker
code.

## Question

Why does the corrected full tree on `4a35316` fail five cases in
`tests/test_phase4_av5m4b_lifetime.py` in original order:

1. `test_job_assignment_failure_refuses_before_mutation` — after refused
   job assignment, `_foreign_vault_worker_alive` is still true.
2. Four later cases refuse their first ordinary `export()` with
   `destination_unavailable` / `OSError`, captured log
   `operation is no longer live` at `_atomic_local` during
   `on_committed_event` ledger save.

A focused pass is not closure of the full-tree failure.

## Diagnostic (preserved before any production edit)

Observer `docs/library/proof/ryan-phase4-lifecycle-2026-09-09/p4_snap.py`
records context/session/owner/child identity. It does not reset globals,
release a gate, kill a writer, or change a result.

### Focused file, original order

```
C:\Python314\python.exe -B docs/library/proof/ryan-phase4-lifecycle-2026-09-09/run_focused.py --root <worktree> --label p4life-diag0 tests/test_phase4_av5m4b_lifetime.py
```

**7 passed in 8.01s.** `_IO_CTX.session` null, no retained sessions, no live
owners, before and after every case. Isolated job assignment is not the
full-tree defect. Proof: `diag-isolated/` (log sha256
`d26e3de9447772ea09dd66490055840ae84d7a8b7c32b906cbab6a7e13a629df`).

### Prefix that matches collection order: AV-5m4b7 then this file

```
... --label p4life-prefix-b7 tests/test_phase4_av5m4b7_lifetime.py tests/test_phase4_av5m4b_lifetime.py
```

**5 failed, 6 passed in 6.93s.** The five failures are exactly the full-tree
lifetime cases. Proof: `diag-prefix-b7/` (log sha256
`9751c4f631dc0623ab2ea8a47c321ab87bf7672cbae7a3fbf6d9f0cb9fd370be`).

After `test_originating_helper_succeeds_foreign_helper_refuses`:

- `_IO_CTX.session` remains `_VaultIoSession@21b87525d10`
- `_dead` true, `alive` false, `physical_liveness` `"dead"`, `proc_poll` null
- `writer_pid` 76312, `pid` null, `lease_written` false, exclusion already gone
- originating Thread object **is** the pytest thread
- `bound_must_refuse_dest` true, no plan
- the same dead session is still bound at job-assignment setup and at every
  later `export()`

`session.terminate()` on the origin thread proved child death and dropped
retain/exclusion, but left the originating `_IO_CTX` binding.
`_read_dest_lease` then returns `unavailable`, so `_foreign_vault_worker_alive`
is true for a later dest. `_atomic_local` during `on_committed_event` raises
`operation is no longer live`.

AW-12 prefix plus this file passed 11 tests: those originating starts run on
another thread whose locals die with it.

Cause: originating-operation cleanup after proven death, not a live unassigned
child on the job-assignment dest.

## Repair (documented before the first rerun)

`library_mirror.py` only. sha256 after repair
`c09827c3dedbc8a46c10f9732275221a2a5d8dcb3b04c24532bcef9827b63924`
(204204 bytes).

1. After confirmed `terminate()` and `_abandon_unstarted()`, the originating
   Thread object unbinds this session from its `_IO_CTX`. A foreign thread
   cannot. Launch/assignment still open keeps the binding. Retain and
   Windows exclusion rules are unchanged. An expired bound operation still
   refuses dest I/O and later-session adoption through `_atomic_local`.
2. `_foreign_vault_worker_alive`: lease `unavailable` caused by a proven-dead
   bound session is not a live foreign worker. `corrupt` and unknown liveness
   still block.

`Mirror._forget_session` uses the same unbind. No fixture edits. No global
reset from a test.

## Reruns

### Repair 1, same reproducing prefix

```
... --label p4life-repair1-b7 tests/test_phase4_av5m4b7_lifetime.py tests/test_phase4_av5m4b_lifetime.py
```

**11 passed in 12.89s.** After the originating helper, `_IO_CTX.session` is
null and `bound_must_refuse_dest` is false at job-assignment setup. Proof:
`repair1-b7/` (log sha256
`2baa7196ac7118cd7ed3f0fe16f2530530ba68bd9f403cf3f85bb6b67994fd49`).

### Required named union (lifetime files, then AW files, then `test_library_mirror.py`)

Resolved selectors (every `test_phase4_aw*.py` under `tests/library_work_astra`
exists; there is no AW-8 file):

- `tests/test_phase4_av5m4b_lifetime.py` … `av5m4b7_lifetime.py`
- `tests/test_phase4_aw12_termination_owner.py`
- `tests/library_work_astra/test_phase4_aw_acceptance.py`
- `tests/library_work_astra/test_phase4_aw2_acceptance.py` … `aw7`, `aw9`,
  `aw9_startup`, `aw10`, both AW-11, both AW-12
- `tests/test_library_mirror.py`

```
... --label p4life-repair1-union <selectors above>
```

**159 passed, 10 failed in 154.28s.** Proof: `repair1-union/` (log sha256
`abcebcfb620786d6e303e3c61eb4eade38db395921f7797450d9538abf738131`).

The five lifetime cases are not among the failures. The eight unchanged
parent-interception failures from product brief section 3 remain visible:

- `test_d13_replace_syscall_cannot_complete_after_timeout`
- `test_d12_retry_keeps_ownership_of_interrupted_temp`
- `test_d12_control_hard_purge_removes_unedited_recorded_temp`
- `test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement`
- `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[visibility]`
- `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[user_edit]`
- `test_d13_timed_out_writer_cannot_erase_a_later_successful_sync`
- `test_purge_removes_intent_owned_actual_temp_name`

Two additional failures in this union, both brief export:

- `test_real_brief_mirror_is_removed_when_dependency_deleted`
- `test_d09_fresh_resync_exports_shelf_and_brief[brief]`

Those two also fail on **unmodified HEAD** when run as that pair
(`p4life-baseline-briefs`, **2 failed, 1 passed in 3.20s**, log sha256
`0498aedbd4df3c9595058bf3aa611d08c088c30de8f837d85b6392f604c69c81`).
They are not in the sealed 20-failure full tree. They are not introduced by
this lifecycle diff. They remain unresolved here.

### Order experiment (not the required-list result)

AW-10/11/12 before ordinary AW and `test_library_mirror.py`
(`p4life-repair1-union2`): **21 failed, 148 passed in 141.33s.** Extra
failures are missing item files after those ownership tests. Retained under
`repair1-union2/`. Do not treat this as the named union.

## Unresolved

- Eight parent-interception / D12–D13 / purge-temp failures stay product
  defects under the existing isolated-child writer. This brief does not
  authorize changing those interception boundaries.
- Two brief-export assertions fail in this runner as a small pair on HEAD
  and in the named union. Not claimed fixed. Not claimed as a lifecycle
  regression.
- A focused lifetime pass and the AV-5m4b7 prefix pass do not close the
  sealed full-tree result on `4a35316`. Integrator verifies this worktree.
- No commits. No paid API. No live index. No port 5179.

## Files

- `library_mirror.py` — originating unbind after proven death; conservative
  liveness after a dead bound session
- `docs/library/RYAN-PHASE4-LIFECYCLE-WORKER-2026-09-09.md` — this report
- `docs/library/proof/ryan-phase4-lifecycle-2026-09-09/` — observer, runner,
  preserved failed and passing logs
