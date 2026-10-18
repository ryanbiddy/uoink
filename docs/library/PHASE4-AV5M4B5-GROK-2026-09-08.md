# AV-5m4b5 (grok)

Base: `control-room/a4af542b-c8b-grok` at `39d7e19` (AW-9 retains B4
`e2580c74` failures and briefs this repair). Starting point was the
retained complete original diff in
`docs/library/patches/av5m4b4-grok-rejected-2026-09-08.patch` applied with
`git apply --3way`. Independent AW-9 union of B4: **255 passed, nine
failed**, 134.12 s. Nine frozen Phase 4 interceptor/setup conflicts remain
Ryan's. Three additional AW-9 findings are this run's implementation work.

No commit, push, model, paid API, live index, port 5179, existing-test
edits, subagents, closure introspection, async Python exceptions, or
destination-byte rollback. `librarian_apply_enabled` remains false
(`server.py` default; this run did not change it). This run does not claim
Phase 4 accepted. Astra independently verifies both roots and finishes
AW-4 afterward.

Python 3.14.x, pytest 9.x, `PYTHONDONTWRITEBYTECODE=1`. Disposable
`APPDATA`/`LOCALAPPDATA`/`TEMP`/`TMP` under `_scratch/av5m4b5/run/`.
`PYTHONPATH` is the worktree plus resolved pywin32
(`site-packages`, `win32`, `win32\lib`, `pythonwin`). `PATH` includes
`site-packages\pywin32_system32`. `ANTHROPIC_API_KEY` absent. Short
`--basetemp t` so dest+temp paths stay ≤ 240 characters. Selectors are the
PowerShell array `$av5m4b5Selectors`; automatic `$args` is never used.

## Overlap resolutions

`git apply --3way` of `patches/av5m4b4-grok-rejected-2026-09-08.patch`
applied every file cleanly. No conflict hunks.

| File | Resolution |
|---|---|
| `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` and B2/B3/B4 reports | New files; kept as retained B-series reports. |
| `index.py` | Clean. B3 `_write_txn_owner` and F/H2 `begin_media_publication(..., capture_binding=, input_files=)` remain. |
| `library_briefs.py` | Clean. Supported Index write-transaction marker; no native SQLite pointer guesses; unproven inherited transactions refuse without caller rollback. |
| `library_mirror.py` | Clean. A3 `_IO_CTX.authority`, creating file/volume/hash, bound Windows rename/delete, POSIX `unlink_exclusion_unavailable` / `replace_exclusion_unavailable` remain from the B4 bytes. |
| `library_mirror_vault_io.py` | Clean. B4 `bind` / `local_put` / `local_unlink` / `whoami` and A3 identity commands remain. |
| B/B2/B3/B4 tests | New unintegrated files from the patch. Vacuous B4 `or True` writer-exe assertion removed; other behavioral assertions kept. |

Non-conflict preservation after B5 edits:

- A3 `ffdbef4`: creating-file authority, bound Windows rename/delete,
  write-error cleanup, unsupported POSIX refusal.
- F/H2 / BC-3f: `Index.begin_media_publication(..., capture_binding=,
  input_files=)` untouched.
- B3 Index write-transaction marker in `library_briefs.py` kept.
- B4 isolated final local intent/binding/ledger replace and unlink stay
  inside the original session. No parent fallback or adoption of a later
  session. `_canonical_dest` is still `normcase(abspath(normpath))` with
  no parent `realpath`.

## AW-9 retained failures (not relabeled)

Parent-hook / setup diagnostics remain failed observations. This run does
not relabel them as passed.

1. `docs/library/proof/aw9-2026-09-08/draft/` and `aw9-final/` —
   original **2 failed**, 0.96 s then 1.01 s on final source:
   unknown writer forgotten after launcher exit; destination mutex
   acquired by competitor PID 12276 while original writer PID 68796
   remained alive after the owning thread returned before a lease.
2. `docs/library/proof/aw9-2026-09-08/aw9-startup/` —
   original **1 failed**, 3.12 s: startup missing-ready plus unsuccessful
   termination; after caller exit competitor acquired the dest mutex
   while launcher PID 53108 remained alive. `Mirror._vault_io` did not
   retain the session. Simulated uncertainty; not a claim that Windows
   termination failed naturally.

Those original logs stay the B4 observation. New B5 tests and the frozen
AW-9 acceptance files are separate evidence.

B4's optional writer-executable assertion ended in `or True`; that clause
proved nothing and is removed. Other PID assertions and actual-child stall
results remain.

## Three repairs

1. **Unknown physical liveness is unresolved ownership.**
   `_process_liveness` still returns `alive`, `dead`, or `unknown`.
   `physical_liveness()` aggregates launcher poll, writer, session pid and
   owned-tree identity. `physically_alive()` is true unless every tracked
   pid is proven dead. Unknown is not cancelled admission (`_dead`) and
   not proven death. `_pid_is_alive` remains the proven-alive predicate
   (`== "alive"`) so lease-query handling of unknown stays a separate
   path. `_kill_vault_io`, `_stop_vault_io`, `_start_vault_io`,
   `_forget_session` and exclusion release forget only after proven
   death. A launcher `poll() != None` does not turn an unknown writer
   into dead. Terminate records created-ms per owned pid and refuses
   `TerminateProcess` when the live process start time does not match;
   executable name is never a kill key.

2. **Actual mutex ownership outlives the request thread.**
   Windows mutex ownership is the acquiring thread. `_exclusive` and
   helper `prepare()` establish a dedicated owner thread *before* any
   writer `Popen`. That thread calls `WaitForSingleObject` / `ReleaseMutex`
   itself and stays responsible until every attached mutator is proven
   dead and no exclusive section still holds. Storing a handle on the
   session is not ownership. `WAIT_ABANDONED` is recorded and is not
   evidence that an old writer is dead. Caller return is covered before
   a lease exists and after it exists. Shutdown/kill/start/forget only
   signal the owner thread to release after proven death. Dest identity
   is `_canonical_dest` (normcase/abspath/normpath, trailing-slash
   aliases); no parent `realpath`. Cross-process exclusion remains the
   dest-hash kernel mutex plus dest-local lease, independent of TEMP /
   profile. POSIX keeps the dest-local flock fd in the same owner thread.

3. **Failed-start sessions are retained before the process starts.**
   `Mirror._start_vault_io` calls `prepare()` (token, dest, exclusion,
   retain) and stores `_vault_io` *before* `launch()` (`Popen`, job
   assign, ready). Helper `_VaultIoSession.start` is `prepare` plus
   `launch`. If job assignment or readiness fails and `terminate()` is
   unconfirmed, process ownership and dest exclusion remain after the
   exception and after the caller thread exits. Cleanup releases only
   after proven physical death. Confirmed death still drops the session
   and lets a later owner acquire without a leaked gate.

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

`tests/test_phase4_av5m4b5_lifetime.py` (9 passed):

- unknown writer after launcher exit is retained (not forgotten)
- dest exclusion survives owning-thread exit before a lease, with a real
  competitor process observation
- dest exclusion survives owning-thread exit after a lease, with a real
  competitor process observation
- startup failure (missing ready, unconfirmed terminate) keeps exclusion
  and `_vault_io` after caller-thread exit
- helper-created startup failure keeps exclusion
- competitor cannot acquire before or after lease; proven death then
  allows a later competitor to acquire (no leaked gate); startup /
  operation / termination / caller-return times are separate fields
- recycled PID / mismatched created-ms is not terminated
- `WAIT_ABANDONED` recorded on the owner is not writer death
- dest aliases share the owner; TEMP/profile roots do not

AW-9 frozen acceptance files were not edited. They passed from these
repairs. Original failed AW-9 outputs remain in
`docs/library/proof/aw9-2026-09-08/`.

## Commands and counts

Environment for every command below:

```
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<worktree>;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32\lib;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\pythonwin
PATH=<site-packages>\pywin32_system32;...
ANTHROPIC_API_KEY absent
APPDATA/LOCALAPPDATA/TEMP/TMP under _scratch/av5m4b5/run/
--basetemp t
selectors: PowerShell $av5m4b5Selectors (never $args)
Python C:\Python314\python.exe 3.14.6
```

Union selectors (exact named set plus new B5 tests): 24 files as listed
in the brief, plus `tests/test_phase4_av5m4b5_lifetime.py`.

| Group | Command | Result | Time |
|---|---|---|---|
| Focus | `$av5m4b5Focus` B5+AW-9+B/B2/B3/B4+A3 | **43 passed** | 24.00 s |
| Long-basetemp | `$av5m4b5Selectors --basetemp _scratch/av5m4b5/union-t` | **252 passed, 24 failed** | 137.25 s |
| Union | `$av5m4b5Selectors --basetemp t` | **267 passed, 9 failed** | 131.53 s |

The long-basetemp run is retained at `_scratch/av5m4b5/union.log`. Dest
paths exceeded the 240-character cap; it is not the named union. The
named union is `_scratch/av5m4b5/union-short.log`.

Union JUnit: `_scratch/av5m4b5/junit/union.xml`
sha256 `4c51affee2539686a1b56cfe03a31033ce2056d69892be58b8abab30645b0e39`.

Union failures are exactly the nine frozen Ryan observations. AW-9's
three lifetime cases passed in this union (2 + 1). B4 independent union
was 255 passed / 9 failed; this union is 255 + 3 AW-9 + 9 B5 = 267
passed / 9 failed.

## Process / operation lifetime

- Exclusion owner thread is created before `Popen`. It acquires and
  releases the dest mutex itself. Caller-thread exit does not abandon it.
- One child interpreter per resync. Writer identity is the ready/`whoami`
  pid plus created-ms. Owned tree is assigned to a kill-on-close job.
  Startup `_WORKER_STARTUP_S` (2.0 s) and termination `_WORKER_TERMINATE_S`
  (2.0 s) stay separate from the publication budget.
- Failed start retains the session on `Mirror._vault_io` (and the helper
  retain set) until proven death.
- Live exclusion: dest-hash kernel mutex (no parent `realpath`) and
  dest-local lease keyed by writer pid. Held until physical death is
  proven. POSIX flocks the dest-local lock file from the owner thread
  when the dest exists.
- Bound operations refuse dest and local persistence after `_dead`.
  Unknown process liveness fail-closed (blocks new ownership).

## Limits

- Dest `exists`, volume-marker and manifest probes still use a parent
  Python thread with a timeout. That does not kill a hung dest syscall.
  Those entry points are not claimed bounded.
- Process exit of the parent cannot keep a Windows mutex without a living
  owner thread or process. Kill-on-close job assignment remains the
  process-exit path for assigned children. Unassigned failed-start
  children stay excluded only while this process still runs the owner
  thread. atexit attempts terminate; it does not wait unbounded.
- ctypes `NtSuspendProcess` stall proof is Windows-specific; POSIX uses
  `SIGSTOP`.
- Phase 4 is not accepted here.

## Files

- `library_mirror.py` — unknown-as-unresolved liveness, dest exclusion
  owner thread, failed-start retain-before-Popen, identity-checked
  terminate
- `library_mirror_vault_io.py` — unchanged from B4 apply (A3 identity +
  B4 local mutation)
- `index.py` — unchanged from B4 apply (B3 marker + F/H2 media args)
- `library_briefs.py` — unchanged from B4 apply
- `tests/test_phase4_av5m4b4_lifetime.py` — removed vacuous `or True`
- `tests/test_phase4_av5m4b5_lifetime.py` — new B5 tests
- `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` — retained B report
- `docs/library/PHASE4-AV5M4B2-GROK-2026-09-08.md` — retained B2 report
- `docs/library/PHASE4-AV5M4B3-GROK-2026-09-08.md` — retained B3 report
- `docs/library/PHASE4-AV5M4B4-GROK-2026-09-08.md` — retained B4 report
- `docs/library/PHASE4-AV5M4B5-GROK-2026-09-08.md` — this report
