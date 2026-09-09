# AV-5m4b (grok)

Base: `cc/living-library` at `98d8b35` (AW-4 recorded ownership defects; contains
AV-5m3 `270e569`). AV-5m4a owns destination binding, temp identity and package
staging in parallel; this run did not edit those regions. Astra verifies and
integrates both with three-way apply, then finishes AW-4. This run does not
claim Phase 4 accepted.

No commit, push, model, paid API, live index, port 5179, existing-test edits,
subagents, closure introspection, async Python exceptions, or destination-byte
rollback. `librarian_apply_enabled` remains false. Apply remains false.

Python 3.14.6, pytest 9.x, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=<worktree>;<user site-packages>`, `ANTHROPIC_API_KEY` absent.
Disposable `APPDATA`/`TEMP` under `_scratch/av5m4b/run/`. Short `--basetemp`
under `_scratch/av5m4b/*` and `_scratch/m4u2`. Unit `tmp_path` shortened with
a disposable `-p shorttmp` plugin (`mktemp("t")`); long pytest node names
exceed the mirror's 240-character path cap in this worktree.

## Repairs

- **Child lifetime** — Windows job APIs use pointer-sized `HANDLE` restype/
  argtypes. Kill-on-close job creation and `AssignProcessToJobObject` must
  succeed before the ready handshake returns; startup/assignment failure
  terminates the child and raises, with no lease and no vault mutation. POSIX
  still starts a new session and terminates with `killpg`. `terminate()` waits
  a bounded `_WORKER_TERMINATE_S` (2.0 s) and clears the dest lease only after
  death is confirmed; a wait timeout keeps the lease and process reference.
  Startup is bounded at `_WORKER_STARTUP_S` (2.0 s), not 15 s. `startup_s` and
  `termination_s` are recorded separately; timeout refusals include both.
  Total caller time is the measured resync wall time and includes startup,
  publication budget wait, and termination.
- **Per-operation ownership** — each resync binds an immutable I/O session,
  cancel event, plan and lock generation on the worker thread (`_IO_CTX`).
  `_require_vault_io` prefers that thread-local session, so a timed-out parent
  thread cannot use a later resync's writer, plan or key. Late lease cleanup
  matches `token` and will not unlink a newer generation. Failed isolated I/O
  does not fall back to an unbounded parent dest read (`_io_sha256` requires a
  live session). Missing destinations refuse before taking a dest-local lock.
- **Stable exclusion** — writer lock and lease live on the destination
  (`.uoink-mirror-writer.lock` / `.uoink-mirror-writer.lease`), not under
  `tempfile.gettempdir()`. Two processes with different TEMP/profile roots
  addressing the same vault share that namespace. Lease records pid, process
  start time and a random token; a live PID with a mismatched start time is
  treated as reuse/dead. Corrupt or unreadable live lease records fail closed
  (`destination_unavailable`). A missing destination falls back to the ledger
  lock so disconnected-vault status/events still return without creating dest
  files. Existing scope/manifest/dependency checks are unchanged.
- **BriefStore** — `_sqlite_writer_exclusion` still reuses an active write
  transaction and still uses idle `BEGIN IMMEDIATE`. An inherited deferred
  read (`in_transaction` without a reserved lock) refuses `stale_brief` /
  `database_busy` without rolling back caller work, so it does not pretend to
  exclude another writer.

No worker protocol extension. AV-5m4a may add file-identity fields; Astra can
merge without a 4b protocol conflict.

## Frozen parent interceptors (Ryan)

The eight frozen parent `os.replace` / `Path.unlink` observations remain
**failed**. The child performs the real syscall. New tests do not relabel them.

## AW-4 cases assigned to AV-5m4a

Reported, not repaired:

| Case | Result |
|---|---|
| AW4-01 missing binding after empty replacement vault | failed — still grants initialization |
| AW4-02 direct `Path.write_text` before `_atomic_local` | failed — prior binding bytes change |
| AW4-03 same-content different-inode temp cleanup | failed — hash-only identity deletes the replacement |
| AW4-04 staged `library_mirror_vault_io.py` | failed — source stage omits the worker |

## New tests

`tests/test_phase4_av5m4b_lifetime.py` (7 passed):

- dest lock/lease paths ignore process TEMP roots
- Windows job-assignment failure refuses before mutation
- child-boundary timeout (suspended real worker) confirms death; independent
  user editor bytes are kept; startup/termination/total caller time reported
- timed-out parent session cannot mutate after a later resync on the same Mirror
- second process with a different TEMP root is excluded
- corrupt lease does not grant the destination
- inherited deferred SQLite read refuses exclusion without rollback; an
  independent writer can still `BEGIN IMMEDIATE`

## Commands and counts

Environment for every command below:

```
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<worktree>;<user site-packages>
ANTHROPIC_API_KEY absent
APPDATA/LOCALAPPDATA/TEMP/TMP under _scratch/av5m4b/run/
```

| Group | Command | Result | Time |
|---|---|---|---|
| AW+AW-2 | `pytest tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py` | **58 passed, 2 failed** | 20.70 s |
| AW-3 | `pytest tests/library_work_astra/test_phase4_aw3_acceptance.py` | **11 passed, 6 failed** | 6.14 s |
| AW-4 | `pytest tests/library_work_astra/test_phase4_aw4_acceptance.py` | **4 failed** | 1.89 s |
| Unit | `pytest -p shorttmp tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py tests/test_library_mirror.py tests/test_library_mirror_wiring.py tests/test_phase4_stdio.py tests/test_c01_mcp_stdio.py` | **133 passed** | 30.60 s |
| AV-5m3 | `pytest tests/test_phase4_av5m3_isolation.py` | **7 passed** | 3.15 s |
| New | `pytest tests/test_phase4_av5m4b_lifetime.py` | **7 passed** | 2.48 s |

JUnit: `_scratch/av5m4b/run/{aw,aw3,aw4,u,m3,n}.xml`.

AW+AW-2 failures (parent `os.replace` intercept vs isolated child):

- `test_purge_removes_intent_owned_actual_temp_name`
- `test_d13_replace_syscall_cannot_complete_after_timeout`

AW-3 failures (same intercept family; D13 fixture contradiction unchanged):

- `test_d12_retry_keeps_ownership_of_interrupted_temp`
- `test_d12_control_hard_purge_removes_unedited_recorded_temp`
- `test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement`
- `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[visibility]`
- `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[user_edit]`
- `test_d13_timed_out_writer_cannot_erase_a_later_successful_sync`

AW-3 still green: D01–D03, D07–D10, D14, D15. The unedited recorded-temp
control shares `interrupted_item_temp` and does not run as a pass.

Limits: one child interpreter per resync, not per file. Hung child I/O is
killed with the job/process group; death is confirmed before the lease is
dropped. Frozen fixtures that patch `mirror.os.replace` in the parent do not
observe that syscall. Publication budget remains the caller's `budget_s`;
startup and termination are bounded and reported beside it, not hidden by
excluding a 15-second ready wait. Unit suites in this worktree need short
`tmp_path` names because dest+temp paths must stay ≤ 240 characters.

## Files

- `library_mirror.py` — job APIs, death-confirmed terminate, thread-local
  session/plan/key, dest-stable lock/lease, pid-reuse/corrupt-lease fail-closed
- `library_briefs.py` — deferred-read vs write-transaction exclusion
- `tests/test_phase4_av5m4b_lifetime.py` — new focused tests
- `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` — this report
