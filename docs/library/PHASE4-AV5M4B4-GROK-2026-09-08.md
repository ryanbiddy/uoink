# AV-5m4b4 (grok)

Base: `cc/living-library` at `564836c` (AW-8 rejects AV-5m4b3 `260ef22c`;
AV-5m4a3 `ffdbef4` integrated). Starting point was the retained complete
original diff in `docs/library/patches/av5m4b3-grok-rejected-2026-09-08.patch`
applied with `git apply --3way --ignore-whitespace`. B3's retained report is
`docs/library/PHASE4-AV5M4B3-GROK-2026-09-08.md` from that patch.

Independent AW-8 union of B3: **240 passed, fourteen failed**, 81.11 s
(`av5m4b3-wi`). Nine frozen Phase 4 interceptor/setup conflicts remain
Ryan's. AW-6 is already repaired by A3 in this checkout. Four B/B2/B3
actual-child stall tests failed in that union. Three AW-8 findings were
this run's implementation work.

No commit, push, model, paid API, live index, port 5179, existing-test
edits, subagents, closure introspection, async Python exceptions, or
destination-byte rollback. `librarian_apply_enabled` remains false
(`server.py` default; this run did not change it). This run does not claim
Phase 4 accepted. Astra independently verifies both roots and finishes
AW-4 afterward.

Python 3.14.6, pytest 9.1.1, `PYTHONDONTWRITEBYTECODE=1`. Disposable
`APPDATA`/`LOCALAPPDATA`/`TEMP`/`TMP` under `_scratch/av5m4b4/run/`.
`PYTHONPATH` is the worktree plus resolved pywin32
(`site-packages`, `win32`, `win32\lib`, `pythonwin`). `PATH` includes
`site-packages\pywin32_system32`. `ANTHROPIC_API_KEY` absent. Short
`--basetemp t` so dest+temp paths stay ≤ 240 characters. Selectors were
the PowerShell array `$pytestUnion` / `$pytestSel`; automatic `$args` was
never used. No unintended full-suite run was started or aborted.

## AW-8 retained failures (not relabeled)

Parent-hook diagnostics remain failed observations of B3's parent
boundaries. This run does not relabel them as passed.

1. `docs/library/proof/aw8-2026-09-08/intent_parent_diagnostic.py` —
   original **1 failed**, 0.32 s: after B3's generation check, parent
   `os.replace` still completed a stale intent write over operation B.
   Re-run on this source: **1 failed**, 3.29 s, at
   `Diagnostic requires the final parent replace boundary`. The parent
   `os.replace` hook no longer observes bound intent mutation. That is
   not a pass of the original diagnostic. New actual-child evidence is
   `test_inflight_isolated_intent_put_cannot_finish_after_writer_death`.
2. `docs/library/proof/aw8-2026-09-08/death_tracking_diagnostic.py` —
   original **1 failed**, 0.31 s: `_kill_vault_io` forgot a child whose
   `terminate()` returned False while `poll()` was still None, because
   `_dead` made `alive` false. Re-run on this source: **1 passed**, 0.23 s
   (`_scratch/av5m4b4/aw8/death-tracking.log`). The original failed log
   stays the B3 observation.
3. `docs/library/proof/aw8-2026-09-08/process-topology.json` —
   integrator session PID 72308 launched actual Python writer PID 60848.
   Suspending the session PID did not stall the writer. The four B/B2/B3
   stall tests failed in the 240/14 union. Those original failures stay
   failed observations. The stall helper now suspends the ready-reported
   writer and the owned tree (excluding conhost). This worker's
   interpreter is `C:\Python314\python.exe` directly: topology re-run
   recorded `session_pid == writer_pid` (direct), stall **passed**.

This run does not repeat B3's claim that a generation check immediately
before `os.replace` / `Path.unlink` proves a late parent cannot finish.

## Three repairs

1. **Actual final mutation.** Bound resync local intent replace/unlink,
   intent allocation records, binding and ledger writes go through the
   original isolated session (`local_put` / `local_unlink`) bound to
   session token, operation ID and lock generation. The worker holds that
   bind and refuses a mismatched or cancelled operation at the isolated
   `os.replace` / `os.unlink`. A late parent with a dead original session
   raises `operation is no longer live`; it does not adopt
   `self._vault_io` if that is a later session and does not fall back to
   parent `os.replace`. Intent persistence moved from the parent-before-
   start path into the cancellable `work()` after `_start_vault_io`.
   `_apply_receipts` binds the original session for ledger/binding
   writes. Unbound fixture seeding with a known dest uses
   `_with_isolated_lease_session` (no callback/name inspection). A
   generation check just before parent `os.replace` is not the
   protection. The dest mutex is not used to hold an unbounded parent
   syscall.
2. **Unconfirmed death is not forgotten.** `_dead` is cancelled admission.
   `physically_alive()` is process/writer/owned-tree liveness. `alive` is
   admitted and physical. `_kill_vault_io` / `_stop_vault_io` /
   `_start_vault_io` / `_forget_session` forget only when physical death
   is proven. `terminate()` returns False and keeps the session, dest
   lease (writer pid), and dest mutex when the tree is still running.
   Lease is written with `writer_pid` after ready; the period before a
   lease exists is covered by the dest mutex and by refusing to start a
   second worker while the first is physically live. Shutdown/kill/start
   failure paths call `terminate()` and do not release exclusion on an
   unconfirmed child. Cross-process exclusion is dest-hash kernel mutex
   plus dest-local lease; it does not use TEMP/profile. Parent
   `os.path.realpath` is not used for dest identity (`_canonical_dest` is
   `normcase(abspath(normpath))`). Dest `exists` / marker / manifest
   probes still run in a parent cancellable thread: that timeout does
   not kill a hung dest syscall, and this report does not claim those
   waits are bounded.
3. **Actual writer process topology.** Ready includes `pid: os.getpid()`.
   That is the writer. `owned_pids()` is the Popen pid, writer pid, and
   Toolhelp children except conhost. Children are assigned to the
   kill-on-close job after ready. `terminate()` TerminateJobObject plus
   TerminateProcess on each owned pid, then waits. Stall proof suspends
   the writer (and owned tree) after `owns_pid` verification, writes a
   ping, and requires empty stdout for 0.2 s while the writer is still
   alive. Startup, publication budget and termination stay separate
   fields. The parent-stub `session.call` test remains a separate case.
   Python processes are not broadly stopped.

## Overlap resolutions

`git apply --3way --ignore-whitespace` applied `index.py`,
`library_briefs.py` and `library_mirror_vault_io.py` cleanly.
`library_mirror.py` had four conflicts:

| Region | Resolution |
|---|---|
| `_IO_CTX` header | Kept A3 comment and `_IO_CTX`. Took B3 `_k32`, `_dest_hold_guard`, `_dest_holds`. |
| `Mirror.__init__` | Did **not** restore A3-removed `_unlink_expected`. Took B3 `_vault_io_termination_s`, `_lock_generation`, `_lock_acquired`, `_op_seq`. |
| `_atomic_vault` | Kept A3 plan/key instance fallback, bind `_IO_CTX.session` only if unset, creating-file `_IO_CTX.authority` through replace and finally unlink. Dropped B3's duplicated mkdir/tmp prefix (already in the A3 try body). |
| `_require_vault_io` | Both sides identical; kept prefer `_IO_CTX.session`. Later edited to refuse `_dead` / non-physical and to refuse adopting a later `self._vault_io` when plan.io disagrees. |

Non-conflict preservation:

- A3 `ffdbef4`: `_IO_CTX.authority`, creating file/volume/hash checks,
  bound Windows rename/delete, write-error cleanup, POSIX
  `unlink_exclusion_unavailable` / `replace_exclusion_unavailable`.
- F/H2 / BC-3f: `Index.begin_media_publication(..., capture_binding=,
  input_files=)` untouched. B3 `_write_txn_owner` landed on
  `write_transaction` only.
- B3 Index write-transaction marker in `library_briefs.py` kept.
  No native SQLite object-pointer guesses. Unproven inherited
  transactions refuse without caller rollback.

## Frozen parent interceptors and D15 (Ryan)

Nine frozen Phase 4 setup failures are preserved and failed in the union:

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

AW-4 4/4, AW-5 3/3, AW-6 1/1, AW-7 1/1. A3 identity 4/4. AV-5m3 7/7.
A2 binding 7/7.

## New and repaired tests

`tests/test_phase4_av5m4b4_lifetime.py` (6 passed):

- unconfirmed `terminate() -> False` does not forget the session
- late parent with `_dead` original session refuses and does not adopt later
- in-flight isolated intent `local_put` while the writer is stalled cannot
  overwrite independent bytes after writer death
- ready `whoami` pid is the writer and is owned
- dest mutex / `_canonical_dest` do not call parent `os.path.realpath`
- live worker without a lease still blocks `_start_vault_io`

B/B2/B3 unintegrated tests: stall helper now suspends the actual writer /
owned tree. Intent tests attach the original session so writes use isolated
`local_put`. Behavioral assertions, child-death, time bounds and independent
user-edit checks are unchanged. Original failed stall output remains in
`docs/library/proof/aw8-2026-09-08/union.log`. The parent-stub test stays a
separate blocking-boundary case.

## Commands and counts

Environment for every command below:

```
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<worktree>;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32\lib;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\pythonwin
PATH=<site-packages>\pywin32_system32;...
ANTHROPIC_API_KEY absent
APPDATA/LOCALAPPDATA/TEMP/TMP under _scratch/av5m4b4/run/
--basetemp t
selectors: PowerShell $pytestUnion / $pytestSel (never $args)
```

| Group | Command | Result | Time |
|---|---|---|---|
| B4+A3 | `pytest tests/test_phase4_av5m4b4_lifetime.py tests/test_phase4_av5m4a3_identity.py` | **10 passed** | 2.58 s |
| B/B2/B3 | `pytest tests/test_phase4_av5m4b_lifetime.py tests/test_phase4_av5m4b2_lifetime.py tests/test_phase4_av5m4b3_lifetime.py` | **21 passed** | 12.95 s |
| Prior | `pytest tests/test_phase4_av5m3_isolation.py tests/test_phase4_av5m4a2_binding.py tests/library_work_astra/test_phase4_aw4_acceptance.py tests/library_work_astra/test_phase4_aw5_acceptance.py tests/library_work_astra/test_phase4_aw6_acceptance.py tests/library_work_astra/test_phase4_aw7_acceptance.py` | **23 passed** | 19.03 s |
| AW+AW-2+AW-3 | `pytest tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py tests/library_work_astra/test_phase4_aw3_acceptance.py` | **68 passed, 9 failed** | 42.01 s |
| Union | B3 named files plus A3 identity plus B4 | **255 passed, 9 failed** | 119.38 s |

Union JUnit: `_scratch/av5m4b4/junit/union.xml`
sha256 `ee514ce7b1e3134853b6f8acda1ae0712785db97f6362aa08c0684c9625d8508`.

Union failures are exactly the nine frozen Ryan observations. AW-6 and the
four former stall tests passed in this union.

## Process / operation lifetime

- One child interpreter per resync. Writer identity is the ready/`whoami`
  pid. Owned tree is assigned to a kill-on-close job. Startup
  `_WORKER_STARTUP_S` (2.0 s) and termination `_WORKER_TERMINATE_S` (2.0 s)
  are recorded separately on timeout refusals.
- Publication budget is the caller's `budget_s`. Total caller time includes
  startup, budget wait and termination.
- Live exclusion: dest-hash kernel mutex (no parent `realpath`) and
  dest-local lease keyed by writer pid. Held until physical death is
  proven. POSIX flocks the dest-local lock file when the dest exists.
- Bound operations refuse dest and local persistence after `_dead`.
  Unknown process liveness still fail-closed.

## Limits

- Dest `exists`, volume-marker and manifest probes still use a parent
  Python thread with a timeout. That does not kill a hung dest syscall.
  Those entry points are not claimed bounded.
- This machine's CPython is a direct worker (`session_pid == writer_pid`).
  The integrator launcher topology is implemented and covered by ready pid
  plus owned-tree suspend/kill; it was not reproduced here as a second
  process.
- ctypes `NtSuspendProcess` stall proof is Windows-specific; POSIX uses
  `SIGSTOP`.
- Phase 4 is not accepted here.

## Files

- `library_mirror.py` — isolated bound local persistence, physical vs
  cancelled liveness, writer tree, dest identity without parent realpath
- `library_mirror_vault_io.py` — `bind`, `local_put`, `local_unlink`,
  `whoami`, ready pid; A3 identity commands unchanged
- `index.py` — B3 `_write_txn_owner`; F/H2 media publication args kept
- `library_briefs.py` — Index write-transaction ownership marker
- `tests/test_phase4_av5m4b_lifetime.py` — stall helper uses actual writer
- `tests/test_phase4_av5m4b2_lifetime.py` — session-bound late intent
- `tests/test_phase4_av5m4b3_lifetime.py` — session-bound late intent/unlink
- `tests/test_phase4_av5m4b4_lifetime.py` — AW-8 finding tests
- `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` — retained B report
- `docs/library/PHASE4-AV5M4B2-GROK-2026-09-08.md` — retained B2 report
- `docs/library/PHASE4-AV5M4B3-GROK-2026-09-08.md` — retained B3 report
- `docs/library/PHASE4-AV5M4B4-GROK-2026-09-08.md` — this report
