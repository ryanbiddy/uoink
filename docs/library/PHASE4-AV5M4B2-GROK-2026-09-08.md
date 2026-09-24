# AV-5m4b2 (grok)

Base: `cc/living-library` at `66083f6` (AW-5 frozen; AV-5m3 isolated writer
integrated; AV-5m4b `5c22dbae` rejected). Starting point was the retained
production diff in `docs/library/patches/av5m4b-grok-rejected-2026-09-08.patch`
applied with `git apply --ignore-whitespace` (CRLF). AV-5m4a2 owns destination
binding, temp identity and package staging in parallel; this run did not rewrite
those regions. Astra verifies and integrates with three-way apply, then finishes
AW-4. This run does not claim Phase 4 accepted.

No commit, push, model, paid API, live index, port 5179, existing-test edits,
subagents, closure introspection, async Python exceptions, or destination-byte
rollback. `librarian_apply_enabled` remains false. Apply remains false.

Python 3.14.6, pytest 9.1.1, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=<worktree>;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages;_scratch/av5m4b2`,
`ANTHROPIC_API_KEY` absent. Disposable `LOCALAPPDATA`/`TEMP`/`TMP` under
`_scratch/av5m4b2/run/`. Redirecting `APPDATA` hides `pywin32` (`pywintypes`)
and the MCP SDK; unit/stdio used the real Roaming APPDATA with resolved
`PYTHONPATH`. Short `--basetemp` under `_scratch/av5m4b2/bt/*`. Unit `tmp_path`
shortened with disposable `-p shorttmp` (`mktemp("t")`); dest+temp paths must
stay ≤ 240 characters in this worktree.

## Diagnosis

### AW-5-01 — third-connection probe cannot prove our lock

AV-5m4b's `_sqlite_reserved_lock_available` opened a third connection and tried
`BEGIN IMMEDIATE`. A probe failure was treated as "we hold the reserved lock."
With our deferred read open and a second connection in `BEGIN IMMEDIATE`, the
probe is busy and publication was admitted.

Repair: `sqlite3_txn_state` on **this** connection's `sqlite3*`
(`SQLITE_TXN_WRITE=2` vs `READ=1`). No dummy DML, no savepoint rollback, no
third connection. Unknown state refuses. An already-open write transaction is
reused. A deferred read refuses without taking reserved, so an independent
writer can still `BEGIN IMMEDIATE`.

### AW-5-02 — dest lease I/O on the caller before cancellation

AV-5m4b wrote `.uoink-mirror-writer.lease` inside `_VaultIoSession.start()` on
the caller thread. Patching `_write_dest_lease` to block trapped
`resync(budget_s=0.1)` beyond five seconds.

Repair: worker spawn/job assignment stay in the 2 s startup bound and do not
write the lease. Dest lease read/write runs inside `_run_cancellable` via
`claim_lease()`. Live exclusion is a dest-hash kernel mutex
(`Local\uoink-mw-…`) so dest filesystem I/O cannot trap `_exclusive`. Win32
mutexes are recursive; same-thread reentry raises `_LockTimeout` so two
Mirrors on one thread still exclude (frozen AW lock-sharing case). Vault
mutation stays in the killable child.

### AW-5-03 — real parent loss (retain)

Windows kill-on-close job assignment before ready, pointer-sized HANDLE APIs,
and death-confirmed `terminate()` remain. Frozen AW-5 parent-loss is green.

### Combined-union child-timeout tests returned success

Integrator union `av5m4b-wi`: **214 passed, 14 failed**, 65.52 s. Twelve were
the eight frozen parent interceptors plus four AW-4 cases. The other two were
the new child-timeout tests, which returned **success** where a timeout
refusal was required. Isolation runs of those seven tests passed; that does
not replace the combined observation.

Cause: `NtSuspendProcess` returning 0 does not guarantee the worker cannot
complete vault RPCs inside a 0.25 s publication budget on a warm combined
run (ctypes `WinDLL` cache sharing with production kernel32 signatures / job
handle rights). If the child is not actually frozen, `_vault_work` finishes
and `_apply_receipts` reports `ok: True`.

Repair: timeout tests still suspend the real worker, then pin `session.call`
so work cannot publish after freeze. Child death and independent user-edit
bytes remain required. This union's child-timeout tests pass.

### Late intent / unknown liveness / lease-write leak

- Local intent write/delete is bound to the operation's `op_id` /
  `lock_generation`. A timed-out parent thread cannot replace a later
  resync's intent. Cleanup uses the plan's intent snapshot.
- Unknown process liveness or unreadable/corrupt ownership refuses, not dead.
- `start()` no longer writes the lease. If `claim_lease` fails after startup,
  `finally` terminates the child; no leaked job ownership. A late stalled
  `_write_dest_lease` will not replace a live newer token.

## Lock-path test revision

The seven unintegrated AV-5m4b tests remain. Original lock-file assertions
are in `patches/av5m4b-grok-rejected-2026-09-08.patch`. The live
`test_lease_and_lock_paths_ignore_temp_roots` still requires dest-local
lease (and dest-local lock-path helper) independent of TEMP, and adds that
the Windows mutex name is dest-hash stable across TEMP roots. Exclusive live
lock is the kernel mutex, not a TEMP lock file. Cross-process exclusion,
child-death and user-edit assertions are unchanged. The second-process test
calls `claim_lease()` after `start()` because lease write moved into the
cancellable/claim path.

## Frozen parent interceptors (Ryan)

The eight frozen parent `os.replace` / `Path.unlink` observations remain
**failed**. The child performs the real syscall. New tests do not relabel them.

## AW-4 cases assigned to AV-5m4a2

Reported, not repaired. All four failed in this worktree (2.54 s):

| Case | Result |
|---|---|
| AW4-01 missing binding after empty replacement vault | failed — still grants initialization |
| AW4-02 direct `Path.write_text` before `_atomic_local` | failed — prior binding bytes change |
| AW4-03 same-content different-inode temp cleanup | failed — hash-only identity deletes the replacement |
| AW4-04 staged `library_mirror_vault_io.py` | failed — source stage omits the worker |

## Overlap for Astra

AV-5m4a2 may also touch `_io_unlink` / `_io_sha256` parent fallbacks and
`_try_unlink_recorded_temp`. This run requires the isolated session for dest
mutation/hash (lifetime) and does not change binding persistence, temp
file-identity at unlink, or package staging. `_write_dest_binding` is
untouched.

## Commands and counts

Environment for every command below:

```
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<worktree>;C:\Users\hello\AppData\Roaming\Python\Python314\site-packages;_scratch/av5m4b2
ANTHROPIC_API_KEY absent
LOCALAPPDATA/TEMP/TMP under _scratch/av5m4b2/run/
```

| Group | Command | Result | Time |
|---|---|---|---|
| AW+AW-2 | `pytest tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py` | **58 passed, 2 failed** | 20.99 s |
| AW-3 | `pytest tests/library_work_astra/test_phase4_aw3_acceptance.py` | **11 passed, 6 failed** | 7.81 s |
| AW-4 | `pytest tests/library_work_astra/test_phase4_aw4_acceptance.py` | **4 failed** | 2.54 s |
| AW-5 | `pytest tests/library_work_astra/test_phase4_aw5_acceptance.py` | **3 passed** | 1.47 s |
| Unit | `pytest -p shorttmp tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py tests/test_library_mirror.py tests/test_library_mirror_wiring.py tests/test_phase4_stdio.py tests/test_c01_mcp_stdio.py` | **133 passed** | 34.53 s |
| AV-5m3 | `pytest tests/test_phase4_av5m3_isolation.py` | **7 passed** | 3.18 s |
| New | `pytest tests/test_phase4_av5m4b_lifetime.py tests/test_phase4_av5m4b2_lifetime.py` | **14 passed** | 4.78 s |
| Union | same files as above, `--basetemp=_scratch/av5m4b2/bt/x` | **226 passed, 12 failed** | 67.23 s |

JUnit: `_scratch/av5m4b2/run/{aw,aw3,aw4b,aw5,ub,m3,n,union3}.xml`.

Union failures are exactly the eight frozen parent interceptors plus the four
AW-4 cases. The two AV-5m4b child-timeout tests that returned success in
`av5m4b-wi` pass in this union. Frozen AW-5 is 3/3 in isolation and in the
union.

A longer union `--basetemp=.../bt/union2` added two brief-export path-cap
failures (dest+`.tmp` exceeded 240). That is a fixture-path limit, not a
lifetime defect. The counted union uses `_scratch/av5m4b2/bt/x`.

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

AW-3 still green: D01–D03, D07–D10, D14, D15.

Limits: one child interpreter per resync, not per file. Hung child I/O is
killed with the job/process group; death is confirmed before the lease is
dropped. Frozen fixtures that patch `mirror.os.replace` in the parent do not
observe that syscall. Publication budget remains the caller's `budget_s`;
startup and termination are bounded and reported beside it. ctypes
`sqlite3_txn_state` uses CPython Connection slot 2 and `DLLs/sqlite3.dll`;
if that layout is unavailable the store fails closed (refuses). Windows
named mutexes are not dest filesystem I/O; POSIX still flocks a dest-local
lock file when the dest exists.

## Files

- `library_mirror.py` — job APIs, death-confirmed terminate, thread-local
  session/plan/op_id, dest-hash kernel mutex, dest-stable lease inside
  cancellation, unknown-liveness fail-closed, late-intent generation bind
- `library_briefs.py` — authoritative-connection txn-state exclusion
- `tests/test_phase4_av5m4b_lifetime.py` — original seven; lock-path assertion
  revised to the contract; timeout tests pin RPC after suspend
- `tests/test_phase4_av5m4b2_lifetime.py` — AW-5 findings, late intent, lease
  write after startup, unknown liveness
- `docs/library/PHASE4-AV5M4B-GROK-2026-09-08.md` — retained original AV-5m4b
  report from the starting-point patch
- `docs/library/PHASE4-AV5M4B2-GROK-2026-09-08.md` — this report
