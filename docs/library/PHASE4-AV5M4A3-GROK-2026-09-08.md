# AV-5m4a3 (grok)

Base: `cc/living-library` at `831714d` (AW-6 frozen; AV-5m4a2 integrated at
`b833167`). AV-5m4a2 remains in tree: binding/witness, recorded-temp
identity, no parent unlink fallback, staged worker. This run repairs the
frozen AW-6 immediate-finally cleanup loss and the same identity gap on
child write-error cleanup and temp-to-destination publication.

No commit, push, model, paid API, live index, port 5179, existing-test
edits, fixture inspection, unlink bypasses, or subagents.
`librarian_apply_enabled` remains false. AV-5m4b2 independently owns
lifetime/exclusion in a parallel worktree. This run does not rewrite
`terminate`, job assignment, dest lease paths or `_run_cancellable`.
Astra independently verifies both roots and reviews the merged
lifetime/identity behavior.

Python 3.14.6, pytest 9.1.1, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=<worktree>;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32\lib;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\pythonwin`,
`ANTHROPIC_API_KEY` absent. Disposable `APPDATA`/`LOCALAPPDATA`/`TEMP`/`TMP`
under `_scratch/r/`. Short `--basetemp t` (temp sidecar names plus the
64-hex item path exceed the mirror's 240-character cap under a longer
`_scratch/...` basetemp in this worktree). AW env fixtures already use
`mktemp("a")`.

## Repairs

1. **Immediate finally cleanup.** `_atomic_vault` still calls one-argument
   `_io_unlink(tmp)` so frozen injectors stay valid. Identity is no longer
   taken from instance-global `self._unlink_expected` (removed). The creating
   write's file/volume id and content hash are bound on thread-local
   `_IO_CTX.authority` for that allocation before replace and through the
   finally unlink. `_io_unlink` / `_io_replace` read that original operation,
   not a later resync's instance fields. Finally unlinks only when that
   creating identity is bound; a pathname whose current identity does not
   match returns `not_ours` and is not deleted. Unresolved intent is left
   for retry (AW-6 plus
   `test_finally_cleanup_retains_intent_when_temp_name_changed_owners`).
2. **Child write-error cleanup.** Windows write uses `CreateFileW`
   (`GENERIC_READ|GENERIC_WRITE|DELETE`, `FILE_SHARE_READ`, `CREATE_NEW`).
   A failed write sets `FileDispositionInfo` on that handle before close.
   It does not `os.unlink(path)` after the creating handle is gone.
   POSIX write-error does not path-unlink after close (fail-closed retain).
3. **Temp-to-destination publication.** Parent `_io_replace` refuses unless
   `_IO_CTX.authority` has the creating `file_id`. The child then opens the
   source by handle, checks volume/file id and hash through that handle, and
   renames the held file (`FileRenameInfo`, `ReplaceIfExists`). A replaced
   temp is `not_ours` and is not adopted as the publication source. There is
   no path-`os.replace` fallback when identity is present. Unbound
   `session.replace` (no `expected_file_id`) still path-replaces so frozen
   `test_vault_io_worker_startup_and_terminate_are_real` is unchanged; parent
   publication never takes that unbound path.
4. **POSIX.** The AV-5m4a2 rename/check/restore unlink is not general
   exclusion from independent writers and could overwrite a new pathname on
   restore. This is a Windows release; POSIX identity unlink and identity
   replace refuse with `unlink_exclusion_unavailable` /
   `replace_exclusion_unavailable` and retain cleanup.

## Overlap with AV-5m4b2 (for Astra three-way)

AV-5m4b2 owns session lifetime/exclusion. Preserve its thread-local
operation context. This run introduces the same module `_IO_CTX` name the
rejected 4b patch used, stores allocation authority on it, and prefers
`_IO_CTX.session` in `_require_vault_io` when present. It does not set
plan/session in `_run_cancellable` or `_vault_work`. `_atomic_vault` binds
`_IO_CTX.session` only when unset, then restores.

Methods both runs may touch:

| Method / symbol | This run | AV-5m4b2 |
|---|---|---|
| `_IO_CTX` | add; `authority`; optional `session` bind inside `_atomic_vault` only if unset | `session` / `plan` / `key` from `_run_cancellable` / `_vault_work` / `_apply_op` |
| `_require_vault_io` | prefer `_IO_CTX.session` when set | same prefer |
| `_atomic_vault` | bind creating identity through replace + finally unlink; read plan/key from `_IO_CTX` with instance fallback | read plan/key from `_IO_CTX` only |
| `_io_unlink` | one-arg seam; identity from `_IO_CTX.authority` | may keep calling one-arg |
| `_io_replace` | two-arg seam; identity from `_IO_CTX.authority` | likely untouched |
| `_try_unlink_recorded_temp` | bind `_IO_CTX.authority` instead of `self._unlink_expected` | likely untouched |
| `_VaultIoSession.replace` | optional expected identity kwargs | likely untouched |
| `_run_cancellable`, `_start_vault_io`, `_stop_vault_io`, `_kill_vault_io`, `terminate`, dest lease/lock | **not edited** | owned by 4b2 |
| `library_mirror_vault_io.py` write/replace/unlink | identity-bound write-error + replace | no protocol conflict if 4b2 adds none |

Do not drop 4b2's `_IO_CTX.session` / `plan` / `key`. Authority is an
additional field. `_try_unlink_recorded_temp` save/restores it around the
one-arg `_io_unlink` call.

Worker protocol (identity extension from AV-5m4a2 plus replace):

- `write` → `{ok, hash, file_id, volume_id}`; failed write deletes the
  creating handle, not a later pathname
- `unlink` optional `expected_file_id`, `expected_volume_id`,
  `expected_hash` → `{ok}`, `{ok, gone}`, `{ok, not_ours}`, or
  `{ok: false, error: "unlink_exclusion_unavailable"}`
- `replace` optional `expected_file_id`, `expected_volume_id`,
  `expected_hash` → `{ok}`, `{ok, not_ours}`, or
  `{ok: false, error: "replace_exclusion_unavailable"}`. Missing identity
  keeps path replace for the frozen startup test; parent publication always
  sends identity.

## Frozen observations (Ryan)

Nine parent-interceptor / D15 setup failures stay failed. AW-6 passes.

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

D15 remains the `Path.write_text` setup mismatch from AV-5m4a2. Direct
write was not restored.

## New tests

`tests/test_phase4_av5m4a3_identity.py` (**4 passed**):

- child write-error does not unlink a replacement planted after the creating handle closes
- worker replace refuses a replaced temp and does not publish it
- immediate finally cleanup retains unresolved intent when the allocated name changed owners
- recorded cleanup still preserves a same-byte replacement

AW-6 (`test_aw6_finally_cleanup_preserves_replacement_at_allocated_temp`) **1 passed**.
AV-5m3 isolation 7 and AV-5m4a2 binding 7 still pass.

## Commands and counts

Environment for every command below:

```
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<worktree>;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\win32\lib;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages\pythonwin
ANTHROPIC_API_KEY absent
APPDATA/LOCALAPPDATA/TEMP/TMP under _scratch/r/
--basetemp t
```

| Group | Command | Result | Time |
|---|---|---|---|
| AW+AW-2 | `pytest tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py` | **58 passed, 2 failed** | 24.50 s |
| AW-3+AW-4 | `pytest tests/library_work_astra/test_phase4_aw3_acceptance.py tests/library_work_astra/test_phase4_aw4_acceptance.py` | **14 passed, 7 failed** (AW-4 4/4 pass; AW-3 adds D15 to the six interceptors) | 11.11 s |
| AW-6 | `pytest tests/library_work_astra/test_phase4_aw6_acceptance.py` | **1 passed** | 0.69 s |
| Unit | `pytest tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py tests/test_library_mirror.py tests/test_library_mirror_wiring.py tests/test_phase4_stdio.py tests/test_c01_mcp_stdio.py` | **133 passed** | 32.26 s |
| Prior new | `pytest tests/test_phase4_av5m3_isolation.py tests/test_phase4_av5m4a2_binding.py` | **14 passed** | 6.82 s |
| New | `pytest tests/test_phase4_av5m4a3_identity.py` | **4 passed** | 1.65 s |

Combined named suites: **224 passed, 9 failed**. JUnit under
`_scratch/av5m4a3/{aw,aw34,aw6,unit,prior,new}.xml`. Isolated roots only.

AW-4's four frozen cases all pass. AV-5m3 isolation and AV-5m4a2 binding
remain 14/14. The nine frozen interceptor/D15 failures are unchanged.

## Boundary proof

- AW-6: `_io_replace` injector moves the allocation aside, plants independent
  bytes at the temp name, raises. Finally `_io_unlink` is identity-bound and
  leaves both the replacement and the held original. Destination bytes
  unchanged.
- Write-error: in-process `_handle` write with injected `os.write` failure;
  replacement planted in `os.close` after the creating handle is closed;
  personal bytes remain.
- Replace: real `_VaultIoSession` child; allocation renamed aside; same-path
  replacement is not published; dest prior bytes kept.

## Limitations

- One child interpreter per resync, not per file (unchanged).
- POSIX deletion/publication exclusion is unsupported here; refuse and retain.
- Windows handle rename/delete is the proven primitive. Do not describe the
  old POSIX rename/check/restore sequence as general exclusion.
- Unbound child `replace` (no expected file id) still path-replaces. Parent
  `_atomic_vault` never uses that path.
- Redirecting `APPDATA` without putting pywin32's `win32` / `win32\lib` on
  `PYTHONPATH` makes `python -P` stdio children fail to import `mcp`
  (`pywintypes`). Resolved by including those installed paths.
- Phase 4 is not accepted here. Astra verifies both roots and integrates
  with AV-5m4b2 via three-way apply.

## Files

- `library_mirror.py` — `_IO_CTX` authority, no instance-global unlink identity,
  identity-bound `_io_replace` / finally unlink
- `library_mirror_vault_io.py` — handle-bound write-error cleanup and identity
  replace; POSIX identity commands fail closed
- `tests/test_phase4_av5m4a3_identity.py` — new focused tests
- `docs/library/PHASE4-AV5M4A3-GROK-2026-09-08.md` — this report
