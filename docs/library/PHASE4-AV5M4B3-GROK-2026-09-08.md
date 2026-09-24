# AV-5m4b3 (grok)

Base: `cc/living-library` at `533ef6f` (AW-7 frozen; AV-5m4a2 `b833167`
integrated; AV-5m4b2 `3ddbb5ef` rejected). Starting point was the retained
complete original diff in
`docs/library/patches/av5m4b2-grok-rejected-2026-09-08.patch` applied with
`git apply --3way --ignore-whitespace`. Two conflicts in `library_mirror.py`
were resolved by keeping AV-5m4a2 recorded-temp identity (`_unlink_expected`,
handle-bound `_io_unlink`) and taking B2 lock generation / termination fields.
Binding, witness, staging and transport from AV-5m4a2 were not rewritten.

AV-5m4a3 concurrently owns temp allocation, publication and immediate
finally cleanup. Overlap is listed below; this run does not repair AW-6.

No commit, push, model, paid API, live index, port 5179, existing-test edits,
subagents, closure introspection, async Python exceptions, or destination-byte
rollback. `librarian_apply_enabled` remains false. Apply remains false. This
run does not claim Phase 4 accepted. Astra verifies and integrates before
AW-4 closes.

Python 3.14.6, pytest 9.1.1, `PYTHONDONTWRITEBYTECODE=1`. Disposable
`APPDATA`/`LOCALAPPDATA`/`TEMP`/`TMP` under `_scratch/av5m4b3/run/`.
`PYTHONPATH` is the worktree plus resolved pywin32
(`site-packages`, `win32`, `win32\lib`, `pythonwin`). `PATH` includes
`site-packages\pywin32_system32` so `pywintypes314.dll` loads without
restoring the user's APPDATA. `ANTHROPIC_API_KEY` absent. Short `--basetemp`
and disposable `-p shorttmp` (`mktemp("t")`) so dest+temp paths stay
≤ 240 characters.

## Repairs

1. **AW-7 late lease write.** Destination lease put/clear/read that can block
   run in the isolated vault worker (`lease_put`, `lease_clear`, `read`).
   `_run_cancellable` binds the original session, token and plan on the worker
   thread *before* `claim_lease` / `_write_dest_lease`. Timeout marks the
   session `_dead` immediately, sets the cancel event, then kills the job.
   A late parent `_write_dest_lease` refuses through that dead bound session
   before any destination syscall. A newer-token check immediately before
   parent `os.replace` is not used. Fixture seeding with no bound resync
   starts an explicit bounded isolated worker (no callback/name inspection).
   Kill-on-timeout does not parent-unlink the lease; a dead pid is not
   blocking, so exclusion stays fail-closed until death is proven.
2. **Local intent mutations.** `_atomic_local` re-checks operation
   generation/op_id immediately before `os.replace` when the path is an
   intent file. `_unlink_intent_file` re-checks immediately before unlink.
   A late operation cannot finish either mutation after a later resync owns
   the intent (`_op_seq` / `_lock_generation`). Ledger and binding writes are
   not generation-bound.
3. **SQLite ownership.** Removed CPython object-slot / separately loaded
   `sqlite3.dll` probing. `Index.write_transaction` records
   `_write_txn_owner = (id(connection), thread ident)` after `BEGIN IMMEDIATE`
   and clears it on commit/rollback. BriefStore reuses that marker for the
   active Index write-transaction case. An inherited deferred read or any
   unproven transaction refuses `stale_brief` / `database_busy` without
   rollback. A third connection's busy result is not proof. Idle connections
   still take `BEGIN IMMEDIATE`.
4. **Real-child timeout evidence.** Unintegrated B/B2 timeout tests no longer
   replace `session.call` with a parent wait after `NtSuspendProcess`. They
   suspend the real worker with production pointer-sized `OpenProcess` plus a
   `WINFUNCTYPE` `NtSuspendProcess` that does not clobber interned kernel32
   signatures, then prove stall with `PeekNamedPipe`: a ping is written to
   the child's stdin and stdout stays empty for 0.2 s while the pid is still
   alive. Child death, publication-budget wait, startup/termination bounds
   and independent user-edit bytes remain required. Original B/B2 versions
   stay in the retained patches. A parent-stub of `session.call` is a
   separate new test, not the child-stall proof.

Combined-union child-timeout tests that returned success in `av5m4b-wi`
pass here with the stall observation attached to the session
(`_stall_evidence`).

## Frozen parent interceptors and D15 (Ryan)

Nine frozen Phase 4 setup failures are preserved:

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

The eight interceptors still patch parent `os.replace` / `Path.unlink`; the
child performs the syscall. D15 still patches `Path.write_text`; production
persists binding via `_atomic_local` only.

## AW-6 (AV-5m4a3)

Frozen `test_aw6_finally_cleanup_preserves_replacement_at_allocated_temp`
failed in 0.43 s in the union (3.08 s with AW-7). Immediate finally cleanup
still deletes a replacement at the allocated temp name. Assigned to AV-5m4a3.
This run did not rewrite `_atomic_vault` finally identity.

AW-4's four cases pass. AW-5's three cases pass. AW-7 passes.

## Overlap with AV-5m4a3

Shared methods touched only for session/generation plumbing, not temp
identity:

- `_atomic_vault` — uses `_IO_CTX` plan/key; finally still calls one-argument
  `_io_unlink(tmp)` so the frozen cleanup injector and a3's identity work
  remain the owners of that path
- `_io_unlink` / `_try_unlink_recorded_temp` — AV-5m4a2 handle identity kept
- `_require_vault_io` / `_run_cancellable` — thread-local session/token/plan
- `library_mirror_vault_io.py` `_handle` — added `read`, `lease_put`,
  `lease_clear`; write/replace/unlink identity commands unchanged

## New tests

`tests/test_phase4_av5m4b3_lifetime.py` (7 passed):

- unproven inherited `BEGIN IMMEDIATE` refuses without rollback
- Index write-transaction owner is `(id(conn), thread)` and is reused
- late `_atomic_local` cannot finish after a later resync owns the intent
- late intent unlink cannot finish after a later resync owns the intent
- dead bound session refuses lease write before touching the destination
- real-child stall timeout keeps an independent user editor
- parent-stub of `session.call` is a separate blocking-boundary case

B/B2 unintegrated tests were revised only for real-child stall proof and
plan cleanup; original versions remain in the retained patches.

## Commands and counts

Environment for every command below:

```
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<worktree>;<user site-packages>;<user site-packages>\win32;<user site-packages>\win32\lib;<user site-packages>\pythonwin
PATH=<user site-packages>\pywin32_system32;<user site-packages>\win32;...
ANTHROPIC_API_KEY absent
APPDATA/LOCALAPPDATA/TEMP/TMP under _scratch/av5m4b3/run/
```

| Group | Command | Result | Time |
|---|---|---|---|
| AW+AW-2 | `pytest tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py` | **58 passed, 2 failed** | 22.37 s |
| AW-3 | `pytest tests/library_work_astra/test_phase4_aw3_acceptance.py` | **10 passed, 7 failed** | 6.90 s |
| AW-4 | `pytest tests/library_work_astra/test_phase4_aw4_acceptance.py` | **4 passed** | 4.37 s |
| AW-5 | `pytest tests/library_work_astra/test_phase4_aw5_acceptance.py` | **3 passed** | 1.50 s |
| AW-6+AW-7 | `pytest tests/library_work_astra/test_phase4_aw6_acceptance.py tests/library_work_astra/test_phase4_aw7_acceptance.py` | **1 passed, 1 failed** (AW-7 pass; AW-6 a3) | 3.08 s |
| Unit | `pytest -p shorttmp tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py tests/test_library_mirror.py tests/test_library_mirror_wiring.py tests/test_phase4_stdio.py tests/test_c01_mcp_stdio.py` | **133 passed** | 33.10 s |
| Impl | `pytest tests/test_phase4_av5m3_isolation.py tests/test_phase4_av5m4a2_binding.py tests/test_phase4_av5m4b_lifetime.py tests/test_phase4_av5m4b2_lifetime.py tests/test_phase4_av5m4b3_lifetime.py` | **35 passed** | 15.41 s |
| Union | same files as above, `--basetemp=_scratch/av5m4b3/bt/u` | **244 passed, 10 failed** | 91.55 s |

JUnit: `_scratch/av5m4b3/junit/{union,g-aw,g-aw3,g-aw4,g-aw5,g-aw67,g-unit,g-impl}.xml`.

Union failures are exactly the nine frozen Ryan observations plus AW-6.
AW-3 still green: D01–D03, D07–D10, D14. AW-4 4/4, AW-5 3/3, AW-7 1/1.

## Process / operation lifetime

- One child interpreter per resync, assigned to a kill-on-close job before
  ready. Startup `_WORKER_STARTUP_S` (2.0 s) and termination
  `_WORKER_TERMINATE_S` (2.0 s) are recorded separately on timeout refusals.
- Publication budget is the caller's `budget_s`. Total caller time includes
  startup, budget wait and termination.
- Live exclusion is a dest-hash kernel mutex, dest-stable across TEMP/profile
  roots. POSIX flocks the dest-local lock file when the dest exists.
- Bound operations refuse dest I/O after `_dead` or cancel. Unknown process
  liveness still fail-closed.

## Limits

- One child interpreter per resync, not per file.
- Hung dest filesystem I/O is killable only after the isolated worker has
  started. Kernel mutex acquisition is not dest filesystem I/O.
- ctypes `NtSuspendProcess` stall proof is Windows-specific; POSIX uses
  `SIGSTOP` plus `select` on stdout.
- Phase 4 is not accepted here.

## Files

- `library_mirror.py` — isolated lease I/O, dead-session refuse, intent
  mutation at `_atomic_local` / `_unlink_intent_file`, dest-stable exclusion
- `library_mirror_vault_io.py` — `read`, `lease_put`, `lease_clear`
- `library_briefs.py` — Index write-transaction ownership marker
- `index.py` — `_write_txn_owner` bound to connection/thread
- `tests/test_phase4_av5m4b_lifetime.py` — B tests; real-child stall
- `tests/test_phase4_av5m4b2_lifetime.py` — B2 findings; stall, no call stub
- `tests/test_phase4_av5m4b3_lifetime.py` — AW-7 / intent interleaving /
  SQLite marker / real-child evidence / parent-stub
- `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` — retained B report
- `docs/library/PHASE4-AV5M4B2-GROK-2026-09-08.md` — retained B2 report
- `docs/library/PHASE4-AV5M4B3-GROK-2026-09-08.md` — this report
