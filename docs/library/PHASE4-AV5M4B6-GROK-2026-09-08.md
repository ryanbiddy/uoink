# AV-5m4b6 (grok)

Base: `control-room/9577904a-b4f-grok` at `17f3714` (AW-10 retains B5
`a4af542b` alias failure and briefs this admission repair). Starting
point was the retained complete original diff in
`docs/library/patches/av5m4b5-grok-rejected-2026-09-08.patch` applied with
`git apply --3way --ignore-whitespace`. Independent AW-10 union of B5:
**267 passed, nine failed**, 132.05 s. Nine frozen Phase 4
interceptor/setup conflicts remain Ryan's. AW-10's junction-alias
admission is this run's implementation work.

No commit, push, model, paid API, live index, port 5179, existing-test
edits, subagents, closure introspection, async Python exceptions, or
destination-byte rollback. `librarian_apply_enabled` remains false
(`server.py` default; this run did not change it). This run does not claim
Phase 4 accepted. Astra independently verifies both roots and finishes
AW-4 afterward.

Python 3.14.x, pytest 9.x, `PYTHONDONTWRITEBYTECODE=1`. Disposable
`APPDATA`/`LOCALAPPDATA`/`TEMP`/`TMP` under `_scratch/av5m4b6/run/`.
`PYTHONPATH` is the worktree plus resolved pywin32
(`site-packages`, `win32`, `win32\lib`, `pythonwin`). `PATH` includes
`site-packages\pywin32_system32`. `ANTHROPIC_API_KEY` absent. Short
`--basetemp t` so dest+temp paths stay ≤ 240 characters. Selectors are the
PowerShell array `$av5m4b6Selectors`; automatic `$args` is never used.

## Overlap resolutions

`git apply --3way --ignore-whitespace` of
`patches/av5m4b5-grok-rejected-2026-09-08.patch` applied every file
cleanly. No conflict hunks. Applied production bytes match the AW-10
sealed final-source hashes.

| File | Resolution |
|---|---|
| `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` and B2/B3/B4/B5 reports | New files from the patch; kept as retained B-series reports. |
| `index.py` | Clean. SHA-256 `02aaf994cc98eac0e1dc1cd552bbdae22eeae1ab23422339277c2b68c790c781`. B3 `_write_txn_owner` and F/H2 `begin_media_publication(..., capture_binding=, input_files=)` remain. |
| `library_briefs.py` | Clean. SHA-256 `96891dbb9eb113fdd484da415d687bb437c612a47eff3081947e664351dcb556`. Supported Index write-transaction marker; no native SQLite pointer guesses; unproven inherited transactions refuse without caller rollback. |
| `library_mirror.py` | Clean apply, then B6 admission edits below. SHA-256 after B5 apply `99fc994219256aad23416e173da16d90fc57e8143be8d7e74e837f6b28355485`. A3 `_IO_CTX.authority`, creating file/volume/hash, bound Windows rename/delete, POSIX `unlink_exclusion_unavailable` / `replace_exclusion_unavailable` remain from the B5 bytes. |
| `library_mirror_vault_io.py` | Clean. SHA-256 `fba259c83b953edef1020e751e2eda7e42baf82bed321960e6d599e385a979b7`. B4 `bind` / `local_put` / `local_unlink` / `whoami` and A3 identity commands remain. Already staged in `build.ps1`. |
| B/B2/B3/B4/B5 tests | New unintegrated files from the patch. B4 late-parent setup repaired as authorized: original process is terminated before the later session starts; stale original plan and no-adoption assertions remain. Kernel-key metadata assertions updated to the shared admission gate; ownership behavior assertions are not weakened. |

Non-conflict preservation after B6 edits:

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
- `_canonical_dest` is still `normcase(abspath(normpath))` with no parent
  `realpath`. Destination/token/operation binding stays on the session and
  plan, independent of the admission-gate key.

## AW-10 retained failure (not relabeled)

`docs/library/proof/aw10-2026-09-08/aw10-alias/` — original **1 failed**,
2.90 s on B5 final source. Owned junction and target verified with
`Path.samefile`. First session through the target had a live writer and
no lease (writer PID 67860). Competitor process through the junction
started another live writer (competitor PID 70488, launcher 47392,
writer 62020). Competitor reported confirmed termination; the first
writer was still alive afterward. Destination mutex name hashed lexical
`normcase(abspath(normpath))`; the junction is a different lexical path.
That log stays the B5 observation. The frozen AW-10 acceptance file is
not edited.

B5 long-basetemp **252 passed, 24 failed** remains a separate failed
observation (`docs/library/proof/aw10-2026-09-08/worker/union.log`). Dest
paths exceeded the 240-character cap; it is not the named union.

## Required repair

Writer admission is a single Windows kernel mutex
`Local\uoink-mirror-writer-admission`, acquired by the dedicated B5
lifetime owner thread before any writer `Popen`. The dest string is not
hashed into the name. Junction aliases, trailing-slash aliases, and
unrelated destinations therefore share one kernel object without parent
`realpath`.

**Concurrency tradeoff.** Unrelated vaults serialize on this gate. Two
resyncs aimed at distinct existing directories wait for each other even
when their files cannot collide. That is accepted for this bounded
repair: lexical hashing cannot prove physical identity, and parent
`realpath` is dest I/O. POSIX keeps dest-local flock (this run's
evidence is Windows).

Same-thread non-recursion keys `_dest_holds` on that gate identity, so a
second acquire from the owning thread refuses even when the request
carries a different lexical destination. Owner reuse is only
`_EXCL_CTX` (the admitted operation). Process-global `_dest_owners`
lookup is removed so a foreign thread or helper cannot adopt an existing
owner. A replacement mutator is refused while an attached session is
`_launching`, physically alive, or of unknown liveness. Abandoned
(`WAIT_ABANDONED`) is recorded and is not writer death. Proven death
still detaches and releases; a later owner can acquire without a leaked
gate.

Helper `_VaultIoSession.start` / `prepare` and `Mirror._start_vault_io`
share that boundary. `_run_cancellable` propagates `_EXCL_CTX` from the
bound session's owner so context stays inside the admitted operation.
Sessions keep their own dest, token and operation id.

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

`tests/test_phase4_av5m4b6_lifetime.py`:

- owned junction alias from another process refuses before the first
  lease; first writer stays alive
- same-process foreign thread refuses through the target and through the
  junction
- unrelated destination is serialized on the shared gate (tradeoff) and
  is admitted after proven death
- helper start refuses a replacement mutator while launch is in progress
  and while the first writer is live / unknown
- same-thread non-recursion uses the gate identity across different
  lexical destinations
- session dest/token stay bound independently of the gate key
- startup / operation / termination / caller-return remain separate
  fields
- proven death still releases; abandoned is not death

AW-10 frozen acceptance is run unchanged. Original failed AW-10 output
remains in `docs/library/proof/aw10-2026-09-08/`.

## Commands and counts

Environment for every command below:

```
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<worktree>;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32\lib;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\pythonwin
PATH=<site-packages>\pywin32_system32;...
ANTHROPIC_API_KEY absent
APPDATA/LOCALAPPDATA/TEMP/TMP under _scratch/av5m4b6/run/
--basetemp t
selectors: PowerShell $av5m4b6Selectors (never $args)
```

Union selectors: every file in the B5 brief, plus
`tests/test_phase4_av5m4b5_lifetime.py`, unchanged
`tests/library_work_astra/test_phase4_aw10_acceptance.py`, and
`tests/test_phase4_av5m4b6_lifetime.py`.

### Failed observation 1 (retained, not relabeled)

`_scratch/av5m4b6/failed-union-1/union-short.log` — **55 failed, 229 passed**, 256.39 s.
sha256 `4dd9ab2d70f897eea58ad8a4d1719a5e51dc9596af8e22687f10942990d2bed4`.

JUnit: `_scratch/av5m4b6/failed-union-1/union.xml`.

Focus B6+AW-10+B5+B4 was **23 passed**, 22.12 s, before this union. AW-10 passed in the union too. The extra failures were a leaked shared gate, not a relabel of AW-10.

Cause, repaired before rerun:

1. Nested `_exclusive` reused `_EXCL_CTX` on the same thread. Frozen
   `test_destination_lock_is_shared_across_local_ledgers` is a second
   Mirror operation, not the same admitted operation. It expected
   `_LockTimeout` and DID NOT RAISE. `_exclusive` now always acquires;
   `_EXCL_CTX` reuse stays on `prepare()` / helper start only.
2. `needed()` treated any attached session as live, including proven-dead
   sessions that never detached. That held the shared gate across later
   destinations. `needed()` / `release_if_unneeded()` now keep the gate
   only for `_launching` or `physically_alive()` mutators, and
   `_acquire_dest_exclusion` prunes proven-dead owners first.

The nine frozen interceptor/D15 failures in that log remain failed
observations. Long-path B5 **252 passed, 24 failed** is still retained
in `docs/library/proof/aw10-2026-09-08/worker/union.log`.

### Failed observation 2 (retained, not relabeled)

`_scratch/av5m4b6/failed-union-2/union-short.log` — **12 failed, 272 passed**,
137.21 s. sha256 `07801a00545dfbd523dd1935a8184aafd5e0383ae65c7e218241d6a4fffaaf87`.

Nine frozen interceptor/D15 cases plus three helper `_start_vault_io`
calls that wait only `_WORKER_STARTUP_S` (2 s) outside `_exclusive`:
`test_aw4_temp_cleanup_preserves_same_content_replacement_file`,
`test_recorded_temp_hash_does_not_delete_user_bytes`,
`test_failed_replace_retains_temp_generation`. AW-10, B5 and B6 passed
in that union. The shared gate still held a prior mutator; resync can
wait the publication budget (2 s) and then those helpers timed out.

Repair before rerun: Mirror helper `_start_vault_io` takes `_exclusive`
when no admitted `_EXCL_CTX` owner exists, after refusing a live or
pre-Popen launching session. That is the same operation-scoped owner
as resync, not a foreign adoption. `_launching` keeps the gate only
before `Popen`; proven-dead sessions with a stale flag do not.

Focused follow-up after that wrap (24 passed, 3 failed): helper
`_start_vault_io` held the gate, then `_atomic_local` started a second
writer through `_with_isolated_lease_session`. B5 hid that by adopting a
process-global dest owner. Repair: unbound local intent I/O uses the live
`_vault_io` mutator; `_with_isolated_lease_session` reuses the admitted
operation's live session and does not launch a replacement.

Focus after that repair: **27 passed**, 25.15 s
(`_scratch/av5m4b6/junit/focus4.xml`).

### Named union (final source bytes)

| Group | Command | Result | Time |
|---|---|---|---|
| Focus | `$av5m4b6Focus` B6+AW-10+B5+B4 | **23 passed** | 22.12 s |
| Focus 4 | plus dest-lock + AW-4 temp + two AV-5m3 helpers | **27 passed** | 25.15 s |
| Union 1 | `$av5m4b6Selectors --basetemp t` | **229 passed, 55 failed** retained | 256.39 s |
| Union 2 | same selectors after gate-leak repair | **272 passed, 12 failed** retained | 137.21 s |
| Union | `$av5m4b6Selectors --basetemp t` | **275 passed, 9 failed** | 132.64 s |

Named union JUnit: `_scratch/av5m4b6/junit/union.xml`
sha256 `df2ae90a71d31298fce253527f8fd9cfd2a84e16067732acaaea29c2e3727075`.
Log sha256 `d47889df6e438d1b7340e2d305d60752efc3b4dd8645cc6a1d185a8aefb184d6`.

Union failures are exactly the nine frozen Ryan observations. AW-9
lifetime, AW-10 junction, A3 identity, F/H2/BC-3f media bindings, B5
lifetime, and B6 alias/shared-gate tests passed. B5 independent union
was 267 passed / 9 failed; this union is 267 + 1 AW-10 + 7 B6 = 275
passed / 9 failed.

Python `C:\Python314\python.exe` 3.14.6. `librarian_apply_enabled` remains
false at `server.py:919`. No commit, push, model, live index, or port 5179.

## Process / operation lifetime

- Shared Windows admission gate is acquired by the B5 owner thread
  before `Popen`. Caller-thread exit does not abandon it.
- One child interpreter per resync. Writer identity is the ready/`whoami`
  pid plus created-ms. Owned tree is assigned to a kill-on-close job.
  Startup `_WORKER_STARTUP_S` (2.0 s) and termination `_WORKER_TERMINATE_S`
  (2.0 s) stay separate from the publication budget.
- Failed start retains the session until proven death.
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

- `library_mirror.py` — shared Windows admission gate, operation-scoped
  owner reuse, replacement-mutator refusal, `_launching` retain, helper
  `_start_vault_io` exclusive admission, live `_vault_io` for unbound
  local I/O
- `library_mirror_vault_io.py` — unchanged from B5 apply
- `index.py` — unchanged from B5 apply
- `library_briefs.py` — unchanged from B5 apply
- `tests/test_phase4_av5m4b_lifetime.py` — kernel-key metadata names the
  shared gate
- `tests/test_phase4_av5m4b4_lifetime.py` — late-parent setup terminates
  original first; kernel-key metadata names the shared gate
- `tests/test_phase4_av5m4b5_lifetime.py` — kernel-key metadata names the
  shared gate
- `tests/test_phase4_av5m4b6_lifetime.py` — new B6 tests
- `docs/library/PHASE4-AV5M4B6-GROK-2026-09-08.md` — this report
- `_scratch/av5m4b6/failed-union-1/` and `failed-union-2/` — retained
  failed unions, not relabeled
