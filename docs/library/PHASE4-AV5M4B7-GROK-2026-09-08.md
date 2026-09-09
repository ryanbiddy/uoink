# AV-5m4b7 (grok)

Base: `control-room/b00703c8-7ca-grok` at `7995c0e` (AW-11 retains B6
`9577904a` cancelled-launch and foreign-helper failures and briefs this
lifetime repair). Starting point was the retained complete original diff in
`docs/library/patches/av5m4b6-grok-rejected-2026-09-08.patch` applied with
`git apply --3way --ignore-whitespace`. Independent AW-11 verification of
B6: **275 passed, nine failed**, 153.63 s; the additional AW-11 cases are
**three failed**, 0.88 s. Nine frozen Phase 4 interceptor/setup conflicts
remain Ryan's. AW-11's cancelled-launch retention and foreign helper
adoption are this run's implementation work.

No commit, push, model, paid API, live index, port 5179, existing-test
edits, subagents, closure introspection, async Python exceptions, or
destination-byte rollback. `librarian_apply_enabled` remains false
(`server.py:919` default; this run did not change it). This run does not
claim Phase 4 accepted. Astra independently verifies both roots and
finishes AW-4 afterward.

Python 3.14.6, pytest 9.x, `PYTHONDONTWRITEBYTECODE=1`. Disposable
`APPDATA`/`LOCALAPPDATA`/`TEMP`/`TMP` under `_scratch/av5m4b7/run/`.
`PYTHONPATH` is the worktree plus resolved pywin32
(`site-packages`, `win32`, `win32\lib`, `pythonwin`). `PATH` includes
`site-packages\pywin32_system32`. `ANTHROPIC_API_KEY` absent. Short
`--basetemp t` so dest+temp paths stay ≤ 240 characters. Selectors are the
PowerShell array `$av5m4b7Selectors`; automatic `$args` is never used.

## Overlap resolutions

`git apply --3way --ignore-whitespace` of
`patches/av5m4b6-grok-rejected-2026-09-08.patch` applied every file
cleanly. No conflict hunks. Applied production bytes match the AW-11
sealed B6 final-source hashes.

| File | Resolution |
|---|---|
| `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` and B2/B3/B4/B5/B6 reports | New files from the patch; kept as retained B-series reports. |
| `index.py` | Clean. SHA-256 `02aaf994cc98eac0e1dc1cd552bbdae22eeae1ab23422339277c2b68c790c781`. B3 `_write_txn_owner` and F/H2 `begin_media_publication(..., capture_binding=, input_files=)` remain. |
| `library_briefs.py` | Clean. SHA-256 `96891dbb9eb113fdd484da415d687bb437c612a47eff3081947e664351dcb556`. Supported Index write-transaction marker; no native SQLite pointer guesses; unproven inherited transactions refuse without caller rollback. |
| `library_mirror.py` | Clean apply, then B7 launch/helper edits below. SHA-256 after B6 apply `89e31c2e6aebb6f575a835511645904b415d0cadb54ed32265e8fe750038e791`. After B7 `8b670a0cdde7660abdfa3c96b16a968d52c59d7acb86caba4616f8de1001e953`. |
| `library_mirror_vault_io.py` | Clean, unchanged after apply. SHA-256 `fba259c83b953edef1020e751e2eda7e42baf82bed321960e6d599e385a979b7`. |
| B/B2/B3/B4/B5/B6 tests | New unintegrated files from the patch. Not edited in this run. |

Non-conflict preservation after B7 edits:

- A3 creating-file authority, bound Windows rename/delete, write-error
  cleanup, unsupported POSIX refusal.
- F/H2 / BC-3f: `Index.begin_media_publication(..., capture_binding=,
  input_files=)` untouched.
- B3 Index write-transaction marker in `library_briefs.py` kept.
- B4 isolated final local intent/binding/ledger replace and unlink stay
  inside the original session. No parent fallback or adoption of a later
  session.
- B5 dedicated lifetime owner thread, unknown-liveness retention, failed
  start retain-before-Popen, identity-checked terminate.
- B6 shared Windows admission gate and unrelated-destination serialization
  tradeoff. `_canonical_dest` is still `normcase(abspath(normpath))` with
  no parent `realpath`. Destination/token/operation binding stays on the
  session and plan, independent of the admission-gate key.

## AW-11 retained failures (not relabeled)

`docs/library/proof/aw11-2026-09-08/aw11/` — original **3 failed**, 0.88 s
on B6 final source. Frozen files are
`tests/library_work_astra/test_phase4_aw11_start_cancel_acceptance.py` and
`tests/library_work_astra/test_phase4_aw11_foreign_helper_acceptance.py`.
Those files are not edited.

1. Prepared session cancelled before `Popen`: cancellation reported death,
   dropped Mirror/global retention and released the gate. Resuming the
   original caller started launcher PID 70036 and writer PID 62724. The
   writer was physically alive, admission was cancelled, no owner remained
   held, and no lease or content-mutation command had been sent. This is an
   untracked idle child, not post-timeout publication.
2. Foreign thread with no session or exclusion context called
   `_atomic_local` / `_unlink_intent_file` on the same Mirror. The unbound
   fallback selected live `self._vault_io`. Put replaced
   `{"owner":"original"}` with `{"owner":"foreign"}` through writer PID
   57928. Unlink deleted the original intent through writer PID 5900. Both
   helpers returned success with the original writers still alive.

B6 named union **275 passed, 9 failed**, 132.64 s remains a failed
observation (`docs/library/proof/aw11-2026-09-08/worker/union-short.log`,
sha256 `d47889df6e438d1b7340e2d305d60752efc3b4dd8645cc6a1d185a8aefb184d6`).
B6 failed union 1 **229 passed, 55 failed** and failed union 2
**272 passed, 12 failed** remain retained under
`docs/library/proof/aw11-2026-09-08/worker/failed-union-1/` and
`failed-union-2/`. B5 long-basetemp **252 passed, 24 failed** remains in
`docs/library/proof/aw10-2026-09-08/worker/union.log`.

## Required repair

1. **Cancelled launch retention.** `_VaultIoSession` distinguishes
   prepared (`_launching`, `proc is None`), actual `Popen` in progress
   (`_popen_in_progress`), running, and cancelled (`_dead`). A short
   `_state_lock` covers those transitions and is not held across `Popen`
   or a pipe read. `terminate()` of an unstarted or in-flight `Popen`
   sets cancelled admission, records `cancel_return_s`, and returns
   without claiming physical death, closing a job launch still uses, or
   dropping retain/owner. A cancelled launch that has not entered `Popen`
   refuses before process creation and `_abandon_unstarted` once no
   launch can follow. If `Popen` already started, the child or failure is
   registered on the original session and cleaned up there. Unknown
   liveness still retains; proven death still releases.
2. **Foreign helper refusal.** Unbound `_atomic_local` /
   `_unlink_intent_file` no longer adopt live `self._vault_io` from a
   foreign thread. Reuse is the admitted operation (`_IO_CTX` / plan) or
   an explicit originating-helper binding: `_start_vault_io` binds
   `_IO_CTX` on the starting thread, and same-thread fallback also
   requires `session._origin_thread_id == threading.get_ident()`. A bound
   dead or cancelled session refuses and does not fall back to a later
   writer. `_run_cancellable` still propagates operation context.
   `_with_isolated_lease_session` reuses a live operation session only
   when `_canonical_dest` matches the requested dest; the shared gate
   name is not dest identity. No process-global owner lookup.

## Frozen parent interceptors and D15 (Ryan)

Nine frozen Phase 4 setup failures are preserved and must remain failed
in the union:

| Suite | Case |
|---|---|
| AW | `test_purge_removes_intent_owned_actual_temp_name` |
| AW-2 | `test_d13_replace_syscall_cannot_complete_after_timeout` |
| AW-3 | `test_d12_retry_keeps_ownership_of_interrupted_temp` |
| AW-3 | `test_d12_control_hard_purge_removes_unedited_recorded_temp` |
| AW-3 | `test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement` |
| AW-3 | `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[visibility]` |
| AW-3 | `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[user_edit]` |
| AW-3 | `test_d13_timed_out_writer_cannot_erase_a_later_successful_sync` |
| AW-3 | `test_d15_failed_destination_binding_persistence_does_not_allow_readoption` |

## New tests

`tests/test_phase4_av5m4b7_lifetime.py` (**4 passed**):

- cancellation during a controlled actual `Popen` handoff: cancel returns
  in `cancel_return_s` ~1.7 µs with session/owner/gate retained; child
  PID is registered on the original session after `Popen` returns; no
  lease and no mutation commands (idle child is not post-timeout
  publication); eventual `terminate()` confirms death and releases the
  gate. Startup, cancel-return and termination remain separate fields.
- launch failure after cancellation: injected `Popen` error, zero
  children, no launcher/writer pid, retain/owner released, gate freed.
- originating-thread `_atomic_local` / `_unlink_intent_file` succeed
  through the original writer; foreign thread refuses with original
  intent bytes unchanged.
- lease helper reuses the original dest and refuses a samefile junction
  alias and an unrelated dest. `_canonical_dest` differs; the shared
  gate key matches. No parent `realpath`.

Unchanged AW-11 frozen files now pass on these bytes.

## Commands and counts

Environment for every command below:

```
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<worktree>;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32\lib;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\pythonwin
PATH=<site-packages>\pywin32_system32;...
ANTHROPIC_API_KEY absent
APPDATA/LOCALAPPDATA/TEMP/TMP under _scratch/av5m4b7/run/
--basetemp t
selectors: PowerShell $av5m4b7Selectors (never $args)
```

Union selectors: every file in the B5 brief, plus
`tests/test_phase4_av5m4b5_lifetime.py`, unchanged
`tests/library_work_astra/test_phase4_aw10_acceptance.py`,
`tests/test_phase4_av5m4b6_lifetime.py`, both AW-11 files, and
`tests/test_phase4_av5m4b7_lifetime.py`.

### Focus (B7 + AW-11)

`$av5m4b7Focus` — **7 passed**, 10.02 s.
JUnit: `_scratch/av5m4b7/junit/focus.xml`
sha256 `73961a35af47eca16c6a38ec1e8b512266cd2c4153f3263ab8af7c177cc8c2ec`.

### Failed observation 1 (retained, not relabeled)

`_scratch/av5m4b7/failed-union-1/union-short.log` — **281 passed, 10 failed**,
137.89 s. sha256
`58aa82fdd497a7baf299c9681a8ae51b4dd3da066f83ec22dab04bade13947f7`.
JUnit sha256
`edabee214df4adf610ef35156fca1bf17203c67c65fc32c55984420932db837b`.

Nine frozen interceptor/D15 cases plus
`test_originating_helper_succeeds_foreign_helper_refuses`
(`OSError: operation is no longer live` at `_atomic_local`). AW-11
foreign-helper cleanup terminates the original session without forgetting
thread-local `_IO_CTX`. The next helper start on the pytest thread left
that dead session bound, so the originating put refused.

Repair before rerun: `_bind_originating_helper` still leaves a live bound
operation in place. A dead or cancelled leftover is replaced by the
session this thread just started. That is originating-helper binding for
a new start, not later-session adoption during a still-bound dead
operation. Bound dead `_atomic_local` without a new start still refuses.

Order check after that repair (AW-11 foreign helper then the originating
helper): **3 passed**, 9.38 s.

### Named union (final source bytes)

| Group | Command | Result | Time |
|---|---|---|---|
| Focus | `$av5m4b7Focus` B7+AW-11 | **7 passed** | 10.02 s |
| Union 1 | `$av5m4b7Selectors --basetemp t` | **281 passed, 10 failed** retained | 137.89 s |
| Union | `$av5m4b7Selectors --basetemp t` | **282 passed, 9 failed** | 145.57 s |

Named union JUnit: `_scratch/av5m4b7/junit/union.xml`
sha256 `063e4d3876bec046db4e243309bd54b850b807fa988cbbc38203303ea87db241`.
Log sha256 `affe9fb879e966b37825793bfa4079c76ef2bb5d83b241ff04f6544669322aef`.

Union failures are exactly the nine frozen Ryan observations. AW-9
lifetime, AW-10 junction, AW-11 cancel/helper, A3 identity, F/H2/BC-3f
media bindings, B5 lifetime, B6 alias/shared-gate, and B7 tests passed.
B6 independent union was 275 passed / 9 failed; this union is
275 + 3 AW-11 + 4 B7 = 282 passed / 9 failed.

The second-union pytest warning is `Unknown config option:
console_output_file` from `-o` on that command. It is not a product
failure.

Python `C:\Python314\python.exe` 3.14.6. `librarian_apply_enabled`
remains false at `server.py:919`. No commit, push, model, live index, or
port 5179.

## Process / operation lifetime

- Shared Windows admission gate is acquired by the B5 owner thread
  before `Popen`. Caller-thread exit does not abandon it.
- Prepared / `Popen`-in-progress / running / cancelled are distinct.
  Cancel of an unstarted or in-flight launch returns boundedly and keeps
  retain/owner until launch refuses or registers the child.
- One child interpreter per resync. Writer identity is the ready/`whoami`
  pid plus created-ms. Owned tree is assigned to a kill-on-close job.
  Startup `_WORKER_STARTUP_S` (2.0 s) and termination
  `_WORKER_TERMINATE_S` (2.0 s) stay separate from the publication budget
  and from `cancel_return_s`.
- Failed start retains the session until proven death. Cancelled
  unstarted launch releases once no launch can follow.
- Bound operations refuse dest and local persistence after `_dead`.
  Unknown process liveness fail-closed (blocks new ownership).

## Limits

- Dest `exists`, volume-marker and manifest probes still use a parent
  Python thread with a timeout. That does not kill a hung dest syscall.
  Those entry points are not claimed bounded.
- Unrelated destinations serialize on Windows. POSIX dest-local flock is
  unchanged.
- Process exit of the parent cannot keep a Windows mutex without a living
  owner thread or process. Kill-on-close job assignment remains the
  process-exit path for assigned children.
- ctypes `NtSuspendProcess` stall proof is Windows-specific; POSIX uses
  `SIGSTOP`.
- Phase 4 is not accepted here.

## Files

- `library_mirror.py` — launch state lock, cancel-before-Popen refusal,
  Popen-in-progress retention, originating-helper binding, dest-validated
  lease-helper reuse, foreign `_vault_io` adoption removed
- `library_mirror_vault_io.py` — unchanged from B6 apply
- `index.py` — unchanged from B6 apply
- `library_briefs.py` — unchanged from B6 apply
- `tests/test_phase4_av5m4b7_lifetime.py` — new B7 tests
- `docs/library/PHASE4-AV5M4B7-GROK-2026-09-08.md` — this report
- `_scratch/av5m4b7/failed-union-1/` — retained failed union, not relabeled
