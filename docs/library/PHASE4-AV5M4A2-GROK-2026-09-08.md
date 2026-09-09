# AV-5m4a2 (grok)

Base: `cc/living-library` at `d9ccba5` (includes AV-5m3 `270e569` and
BC-3d `897f0d2`). Gemini AV-5m4a `eb32f3b4` timed out without its required
report. Its complete partial diff was applied with three-way apply from
`docs/library/patches/av5m4a-gemini-timeout-rejected-2026-09-08.patch`
(CRLF normalized to LF first; check then apply were clean) as a starting
point only. Bounded corrections 1–4 from the AV-5m4a2 brief follow.

No commit, push, model, paid API, live index, port 5179, existing-test
edits, fixture inspection or subagents. `librarian_apply_enabled` remains
false. AV-5m4b independently owns lifetime/exclusion; this run did not
rewrite `_VaultIoSession.terminate`, job assignment, dest lease paths or
`_run_cancellable`. Astra independently verifies both roots and integrates.

Python 3.14.6, pytest 9.1.1, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=<worktree>;<user site-packages>;<user site-packages>\win32;
<user site-packages>\win32\lib;<user site-packages>\pythonwin`,
`ANTHROPIC_API_KEY` absent. Disposable `APPDATA`/`TEMP` under
`_scratch/r/`. Short `--basetemp t` for unit suites (temp sidecar names
plus the 64-hex item path exceed the mirror's 240-character cap under a
longer `_scratch/...` basetemp in this worktree). AW env fixtures already
use `mktemp("a")`.

## Repairs

1. **Binding / witness.** `_write_dest_binding` no longer uses
   `Path.write_text`. Consent time is persisted in the binding
   (`consented_at_ms`). The durable authority witness
   (`reach/mirror/authority_witness.json`) is written first via
   `_atomic_local`, then the binding; witness persistence failures raise.
   A failed initial write unlinks both files if they did not already
   exist, so it cannot leave usable partial authority. Missing binding
   after prior export (witness `have_synced` or ledger synced entries)
   returns `"missing"` and requires reconciliation. A real newer consent
   (`consented_at_ms` greater than the prior record) can authorize a
   destination change.

2. **No unlink fallbacks.** `_try_unlink_recorded_temp` no longer catches
   `TypeError` and retries without identity. `_io_unlink` requires the
   isolated worker and does not mutate in the parent. An unavailable
   isolated mutation path raises and recorded cleanup is retained.
   Frozen `test_failed_replace_retains_temp_generation` still patches the
   one-argument `_io_unlink`; identity for recorded temps is bound on
   `self._unlink_expected` before that call, not passed as extra kwargs.

3. **Identity at destructive I/O.** The worker opens the path with
   Windows `CreateFileW` (`GENERIC_READ|DELETE`, `FILE_SHARE_READ` only,
   reparse not followed), checks volume/file identity and content through
   that handle (`os.fstat` / hash on the bound fd), and deletes that
   bound file with `FileDispositionInfo`. Replace/rename of the held file
   is sharing-blocked (WinError 32). POSIX uses open/fstat plus
   rename-verify-unlink. Unknown records (no `file_id`) have no deletion
   authority and return `"failed"`. If exclusion cannot be established,
   unlink returns `unlink_exclusion_unavailable` and cleanup is retained.
   Volume id (`st_dev`) and file id (`st_ino`) are recorded from the
   write fd and carried on pending temps.

4. **Staging.** `library_mirror_vault_io.py` is in `build.ps1` validation
   and copy lists and in `installer/uoink.iss`. The source-only staged
   worker starts under `python -I` (isolated mode: no PYTHONPATH, no user
   site), `cwd` = stage, writes a disposable file, returns `file_id`, and
   exits 0.

## Worker protocol (for Astra / AV-5m4b)

Minimal identity extension only:

- `write` → `{ok, hash, file_id, volume_id}` from the creating fd
- `file_id` → `{ok, file_id, volume_id}`
- `unlink` optional `expected_file_id`, `expected_volume_id`,
  `expected_hash` → `{ok}`, `{ok, gone}`, `{ok, not_ours}`, or
  `{ok: false, error: "unlink_exclusion_unavailable"}`

## Frozen observations (Ryan)

Eight parent-interceptor failures are unchanged: the child performs the
syscall, so the parent's patched `mirror.os.replace` / `Path.unlink` is
never entered.

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

**D15 setup mismatch (new failed observation).**
`test_d15_failed_destination_binding_persistence_does_not_allow_readoption`
patches `Path.write_text` on the binding path. Production no longer
calls `Path.write_text`; durable persistence is `_atomic_local` only
(tmp + fsync + replace). The interceptor never fires, first resync
succeeds, and `assert ... and not binding.exists()` fails. Kept failed.
Direct write was not restored.

AW-4's four frozen cases all pass (missing binding, failed atomic
update, same-byte replacement, staged worker present).

## New tests

`tests/test_phase4_av5m4a2_binding.py` (7 passed), plus the seven AV-5m3
isolation tests still pass (14 in that group):

- failed initial binding write leaves no binding or witness
- witness persistence failure is not swallowed; prior binding bytes kept
- `_io_unlink` without a worker refuses and retains the file
- unknown temp record (no file_id) has no deletion authority
- worker unlink preserves a same-byte replacement file
- newer consent authorizes a destination change
- staged worker starts, writes, exits with no source-tree runtime import

## Commands and counts

| Group | Command | Result | Time |
|---|---|---|---|
| AW+AW-2 | `pytest tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py` | **58 passed, 2 failed** | 23.60 s |
| AW-3+AW-4 | `pytest tests/library_work_astra/test_phase4_aw3_acceptance.py tests/library_work_astra/test_phase4_aw4_acceptance.py` | **14 passed, 7 failed** (AW-4 4/4 pass; AW-3 adds D15 to the six interceptors) | 11.10 s |
| Unit | `pytest tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py tests/test_library_mirror.py tests/test_library_mirror_wiring.py tests/test_phase4_stdio.py tests/test_c01_mcp_stdio.py` | **133 passed** | 33.06 s |
| New | `pytest tests/test_phase4_av5m3_isolation.py tests/test_phase4_av5m4a2_binding.py` | **14 passed** | 6.89 s |

Combined: **219 passed, 9 failed**. JUnit under `_scratch/av5m4a2/{aw,aw34}.xml`,
`_scratch/unit-final.xml`, `_scratch/new2.xml`.

AW-3 still green: D01–D03, D07–D10, D14. D15 is the write_text mismatch
above. The unedited recorded-temp control does not run as a pass because
it shares `interrupted_item_temp`.

## Staged-worker proof

`build.ps1 -StageSourceOnly -SourceStagePath <worktree>/_scratch/a2s-*`
copies `library_mirror_vault_io.py`. Launch:

```
python -B -I <stage>/library_mirror_vault_io.py
```

`cwd` = stage, `PYTHONPATH` = stage (ignored by `-I`). Write of
`isolated-stage-write` to a disposable file under the stage succeeded
with a non-zero `file_id`; shutdown returned 0. Isolated mode does not
load the live source tree or user site.

## Limitations

- One child interpreter per resync, not per file (unchanged from AV-5m3).
- `_atomic_vault` finally still calls one-argument `_io_unlink` so the
  frozen AV-5m3 cleanup injector keeps working; recorded-temp deletion
  is the identity-checked path.
- Redirecting `APPDATA` without putting pywin32's `win32` / `win32\lib`
  on `PYTHONPATH` makes `python -P` stdio children fail to import `mcp`
  (`pywintypes`). Resolved by including those installed paths.
- Phase 4 is not accepted here. Astra verifies both roots and integrates
  with AV-5m4b via three-way apply.

## Files

- `library_mirror.py` — binding/witness, recorded-temp identity, no
  parent unlink fallback
- `library_mirror_vault_io.py` — handle-bound identity unlink; write
  returns volume/file id
- `build.ps1` — validate and stage `library_mirror_vault_io.py`
- `installer/uoink.iss` — install the worker
- `tests/test_phase4_av5m4a2_binding.py` — new focused tests
- `docs/library/PHASE4-AV5M4A2-GROK-2026-09-08.md` — this report
