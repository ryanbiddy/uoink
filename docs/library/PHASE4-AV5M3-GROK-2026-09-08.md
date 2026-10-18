# AV-5m3 (grok)

Base: `cc/living-library` at `79f6961` (includes AV-5r `99e9412` and AV-5m1 `9489141`).
AV-5m2 (`6b5e5f1e`) is rejected; production portions of
`docs/library/patches/av5m2-grok-rejected-2026-09-08.patch` were applied with
three-way integration. Not taken from that patch: `_replace_callback_overwrites_dest`
(closure/`observe == "user_edit"` inspection), `PyThreadState_SetAsyncExc`,
in-memory inflight-thread exclusion on one Mirror, or destination-byte rollback.

No commit, push, model, paid API, live index, port 5179, or existing-test edits.
`librarian_apply_enabled` remains false. Astra verifies before AW-4; this run
does not claim Phase 4 accepted.

Python 3.14.6, pytest 9.x, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=<worktree>;<user site-packages>`, `ANTHROPIC_API_KEY` absent.
Disposable `APPDATA`/`TEMP` under `_scratch/av5m3/run/`. Short `--basetemp`
under `_scratch/m3*`. Unit `tmp_path` shortened with `mktemp("t")` (long pytest
node names exceed the mirror's 240-character path cap in this worktree).

## Repairs

- **D12** — outstanding temp generations are retained until cleanup succeeds.
  A temp is bound to path **and** content hash; a recorded path is not deletion
  authority. Failure to persist that allocation refuses the publish. Failed
  cleanup stays on the intent. Frozen AW-3 D12 cases inject failure by patching
  in-process `mirror.os.replace`; publication now mutates the vault in a child,
  so those injectors never fire. New tests exercise the isolated I/O boundary.
- **D13** — vault mutation (write/fsync/replace/unlink) runs in one isolated
  child process per resync (`library_mirror_vault_io.py`), assigned to a
  Windows kill-on-close job (process group on POSIX). The caller's deadline
  kills that worker and waits until it can no longer mutate the destination.
  Destination exclusion is a dest-keyed durable lease, not an in-memory list
  on one Mirror. No callback/closure inspection, no async Python exception, no
  rollback over destination bytes. Source/dependency checks stay in the parent
  immediately before publication. Worker startup is measured outside the
  publication budget.
- **D14** — `Library.md` intent hash is the exact bytes about to be replaced.
- **D15** — destination-binding persistence is atomic+durable (`Path.write_text`
  then fsync/replace) and must succeed before initialization/export authority;
  errors refuse rather than acknowledge. Missing/corrupt binding after prior
  consent requires reconciliation. Have-synced is not inferred from ledger
  generations or an empty dictionary.
- **BriefStore** — `_sqlite_writer_exclusion` no longer rolls back an already
  active caller transaction. Independent `BEGIN IMMEDIATE` exclusion is used
  only when the connection is idle. Receipt-before-freshness is unchanged.

## Frozen D13 (Ryan)

`test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes` installs one
`blocked_replace` wrapper for both `visibility` and `user_edit`. The user-edit
bytes are written only after the forbidden post-timeout `os.replace`. Preventing
that replace also prevents the wrapper from creating the personal bytes. The
implementation does not inspect the fixture. Both frozen observation cases, the
later-sync case (it asserts the in-process wrapper entered), AW-2's
`test_d13_replace_syscall_cannot_complete_after_timeout`, and the three frozen
D12 injectors remain **failed observations**, not passes.

AW `test_timed_out_vault_worker_cannot_publish_after_return` (blocks
`_atomic_vault`, not `os.replace`) still passes: the isolated worker is killed
and destination bytes are not rolled back.

## New tests

`tests/test_phase4_av5m3_isolation.py` (7 passed):

- real worker startup/replace/terminate; mutation time separate from startup
- timeout kills the worker; an independent user editor's bytes are kept
- a live dest-keyed worker lease blocks a second Mirror
- recorded temp hash mismatch does not delete user bytes
- failed isolated replace retains the temp generation
- `_sqlite_writer_exclusion` preserves a caller `write_transaction`
- idle-connection publication exclusion still holds

## Commands and counts

| Group | Command | Result | Time |
|---|---|---|---|
| AW+AW-2 | `pytest tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py` | **58 passed, 2 failed** | 21.36 s |
| AW-3 | `pytest tests/library_work_astra/test_phase4_aw3_acceptance.py` | **11 passed, 6 failed** | 8.21 s |
| Unit | `pytest tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py tests/test_library_mirror.py tests/test_library_mirror_wiring.py tests/test_phase4_stdio.py tests/test_c01_mcp_stdio.py` | **133 passed** | 30.88 s |
| New | `pytest tests/test_phase4_av5m3_isolation.py` | **7 passed** | 4.60 s |

JUnit: `_scratch/av5m3/run/{aw,aw3,u,n}.xml`.

AW+AW-2 failures (in-process `os.replace` intercept vs isolated child):

- `test_purge_removes_intent_owned_actual_temp_name`
- `test_d13_replace_syscall_cannot_complete_after_timeout`

AW-3 failures (same intercept; D13 fixture contradiction recorded above):

- `test_d12_retry_keeps_ownership_of_interrupted_temp`
- `test_d12_control_hard_purge_removes_unedited_recorded_temp`
- `test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement`
- `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[visibility]`
- `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[user_edit]`
- `test_d13_timed_out_writer_cannot_erase_a_later_successful_sync`

AW-3 still green: D01–D03, D07–D10, D14, D15, and the unedited recorded-temp
control does not run as a pass because it shares `interrupted_item_temp`.

Limitation: a child interpreter is started once per resync, not per file.
Hung `os.replace` in that child is terminated with the job/process. Frozen
fixtures that patch `mirror.os.replace` in the parent do not observe that
syscall.

## Files

- `library_mirror.py` — D12–D15, isolated vault I/O session, dest lease
- `library_mirror_vault_io.py` — isolated worker main
- `library_briefs.py` — preserve caller SQLite transaction
- `tests/test_phase4_av5m3_isolation.py` — new focused tests
- `docs/library/PHASE4-AV5M3-GROK-2026-09-08.md` — this report
