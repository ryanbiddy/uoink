# Process identity and handle-lifetime repair02 (Grok)

**Date**: 2026-09-13
**Worker**: grok
**Worktree**: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\a5e7ba0d-26f\grok`
**HEAD**: `4b8dc95912ae74fcdcc0dccf5f9d862d08207fb2` (`control-room/a5e7ba0d-26f-grok`)
**Accepted owner repair**: `ff67b84` (reserve/attach/sweep unchanged)
**Rejected proposal used as draft**: Gemini `c1008e0b` (11 worker pass / 10 Astra identity boundaries fail)
**Briefs**: `MIRROR-PROCESS-AUTHORITY-REPAIR02-BRIEF-2026-09-13.md`, `ASTRA-AUTHORITY-C1008-REVIEW-2026-09-13.md`
**Proof**: `docs/library/proof/grok-authority-repair02-2026-09-13/`

No commits, pushes, subagents, live index, port 5179, model execution, fetch, paid API, website, marketing, or complete-tree claim.

## 1. Starting draft

Checkout `library_mirror.py` before edits:
`docs/library/proof/grok-authority-repair02-2026-09-13/baseline/library_mirror.py`
sha256 `83fd37895cc6bf4670ea4b85a6fdb3a3f0631d9b041b6192f737d13c89479584`.

Applied
`docs/library/proof/astra-authority-c1008-review-2026-09-13/proposed-product-and-tests.diff`
with `git apply --3way`. It applied cleanly. Owner `reserve` / `drop_exclusive` / prepare finally-block survived. That draft is not accepted.

Worker and Astra test files were restored to the exact reviewed-proposal bytes after `git apply` rewrote CRLF:

| File | sha256 |
|---|---|
| `tests/test_library_mirror_process_authority.py` | `74221830187d566a9bede12ff01dfaf61ed674e9bfb6581a7ab4bac2550bf602` |
| `tests/test_mirror_process_identity_boundaries.py` | `b621d87273d75ee2fee84c8c73f78f98dd3809f6e19e1161ec8bfcc1cb8679c3` |

Those hashes match the archived c1008 fixtures. Assertions were not edited.

## 2. Four groups

Process identity is `(pid, created_ms)` with exact equality. `_PROCESS_START_TOLERANCE_MS` remains defined and is used only by `_lease_holder_status` so dest-lease wire formats are not rewritten. Ownership, adoption, owned-PID liveness, kill, and job assignment do not use it.

### Group 1 — no tolerance on ownership or mutation

`_handle_creation_matches` requires exact `GetProcessTimes` identity on the opened handle. `_win_terminate_pid` and `_win_assign_pid` still refuse missing `created_ms` and failed queries. A child with `created_ms < parent_created_ms` is not adopted, including a one-millisecond-older orphan.

### Group 2 — identity held across discovery and action

`_verified_toolhelp_children` does not treat a Toolhelp PID plus a later timestamp as proof. It requires a recorded parent identity, re-checks that identity after the snapshot and after the child query, re-snapshots, and requires the child PID still to belong to that parent with the same creation identity. Already proved `_owned_created` children stay listed after parent exit.

Job handles use `_CountedNativeHandle`: `CloseHandle` waits until the use count is zero. Launch assignment acquires the job handle, drops the cancellation `_state_lock`, then calls `_win_assign_pid`. Terminate does the same for `TerminateJobObject`. A borrowed Popen `_handle` is retained with `owns_close=False` so the session never closes Popen's handle. Discovery does not `OpenProcess` extra handles (the Astra/worker discovery tests mock `_process_created_ms` only).

### Group 3 — unknown recorded parent is not filled

`parent_created = self.created_ms or _process_created_ms(self.pid)` is gone. `_recorded_identity_is_alive` returns false when `created_ms` is None. `owned_pids` `add()` no longer self-authenticates a missing timestamp from a later PID query.

### Group 4 — canonicalize a writer that is the Popen launcher

`_writer_is_canonical_launcher` is true when `writer_pid == pid` and the writer has no separate epoch, or the same epoch. Distinct recorded epochs that share a numeric PID are not merged. If Popen `poll()` proves the launcher dead and the writer is that launcher, `physical_liveness` latches dead and does not call `_process_liveness` for a failed second timestamp query. Launch records writer created time from the retained Popen handle when writer and launcher are the same PID.

## 3. New synthetic controls

`tests/test_mirror_process_handle_lifetime.py` (not a committed acceptance fixture). Fail-closed fake kernel: unmocked `OpenProcess` / `TerminateProcess` / `AssignProcessToJobObject` / `GetProcessTimes` record refusal and return 0. Effect recorders prove mutation refusal and legitimate success.

Controls include: fail-closed refusal, exact-match kill/assign, 1 ms retained-handle refusal, retained-handle terminate without `OpenProcess`, deferred job `CloseHandle`, borrowed Popen handle not closed, launcher identity from `_handle` not a later PID query, missing parent identity, same-PID distinct epoch not merged, canonical writer death with unknown timestamp, verified child adoption, unknown-child exclusion retention, session terminate via retained child handle, assignment without holding `_state_lock`.

Attempt 1 of this file is preserved. Attempt 2 changed setup only (DWORD write-through and inert stream attributes). Diff: `docs/library/proof/grok-authority-repair02-2026-09-13/diffs/handle-lifetime-setup-attempt1-to-attempt2.diff`.

## 4. Verification

Interpreter: `E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe`
Verifier: `E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\integrator_verify.py`
`--root` this worktree, `--runxfail`, fresh `--label`.

Environment: `IG_FORBIDDEN_LIVE=C:\Users\hello\AppData\Local\Uoink\index.db`, `PYTHONDONTWRITEBYTECODE=1`, `PHASE3_REQUIRE_IMPLEMENTATION=1`; provider keys/tokens/endpoint overrides scrubbed. `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.

Selectors: the two retained synthetic files plus the new handle-lifetime controls. No real mirror suite. No shared Windows gate.

### grok-repair02-run-01 (exit 1)

32 passed, 3 failed in 0.58 s.

All 11 worker assertions and 10 Astra identity boundaries passed. The three failures were new-control setup: `GetExitCodeProcess` did not write `STILL_ACTIVE` through `ctypes.byref` (DWORD stayed 0, so terminate returned before `TerminateProcess` — same class of mock bug as Gemini attempt 1), and the inert Popen stub lacked `stdin`/`stdout`/`stderr`. Product code was not changed. Reason: `docs/library/proof/grok-authority-repair02-2026-09-13/drafts/repair02-run-02-reason.txt`. Failed log preserved under `runs/grok-repair02-run-01/`.

### grok-repair02-run-02 (exit 0)

35 passed in 0.43 s (junit `tests="35"` `failures="0"` `errors="0"` `skipped="0"` `time="0.396"`).

Breakdown: 11 worker + 10 Astra boundaries + 14 handle-lifetime controls.

Command (from `_scratch/grok-repair02-run-02/results.json`):

```
E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe -B E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\integrator_verify.py --root C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\a5e7ba0d-26f\grok --label grok-repair02-run-02 --runxfail tests/test_library_mirror_process_authority.py tests/test_mirror_process_identity_boundaries.py tests/test_mirror_process_handle_lifetime.py
```

## 5. Files changed (uncommitted)

- `library_mirror.py` — process identity, discovery revalidation, writer canonicalization, counted native handles. Owner exclusion path not edited after the 3-way apply.
- `tests/test_library_mirror_process_authority.py` — new, exact c1008 worker bytes
- `tests/test_mirror_process_identity_boundaries.py` — new, exact c1008 Astra bytes
- `tests/test_mirror_process_handle_lifetime.py` — new controls
- `docs/library/MIRROR-AUTHORITY-REPAIR02-GROK-2026-09-13.md` — this report
- `docs/library/proof/grok-authority-repair02-2026-09-13/` — baseline, drafts, diffs, run logs

Product diff vs HEAD: `docs/library/proof/grok-authority-repair02-2026-09-13/diffs/final-library_mirror.diff`.

## 6. Unresolved

Synthetic identity repair does not establish tree08's original cause. No real process test ran here. Astra reviews the final diff and runs real Phase 4 suites sequentially in both roots. No complete-tree or release-readiness claim.
