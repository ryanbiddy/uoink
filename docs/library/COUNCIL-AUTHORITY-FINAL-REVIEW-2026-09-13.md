# Council Process-Authority Final Review (Gemini)

**Date**: 2026-09-13  
**Reviewer**: Gemini (isolated Control Room worktree `6bbf0095-0d8\gemini`)  
**Target Commit**: `747fb6b1ca579d2bb9d1c41688ff97bbe029dde1` (mirror repair; tree HEAD `4067de31e0ab3f0d1c1377b60c8a3db1fa6c76ed`)  
**Target File**: `library_mirror.py`  
**Git Blob SHA-1**: `cac85ac0b3937de8df542de9586a45723971594f`  
**Normalized LF SHA-256**: `843a08b1fba0364c2233fabb127197a0b2ca2be50c62930897666c3cfe220cdd`  
**Working Tree CRLF SHA-256**: `fd6db91a0a188eee16383e8a12b7fcb4bedf6edbba90b3840aa11e4087fab135`  
**Worker Source SHA-256**: `67432bf13905b8c28c2048ce51bbebd74490d463f8b1a4e08fdd3ce4e53a0a23`  
**Scope**: Bounded independent source review of committed mirror repair `747fb6b` across three process-authority boundaries.

---

## Verdict

**ACCEPTED** within the bounded scope of the three reviewed process-authority boundaries.

No actionable defect was found in production control flow for `library_mirror.py`. The implementation securely binds Windows process objects from relationship proof through mutation, safeguards handle reference counting and borrowed `Popen` lifetimes without lock contention, and maintains destination exclusion across overlapping discovery, launch, and cancellation.

**Scope Limits & Explicit Non-Certifications:**
- This verdict certifies only the process-authority control flow in `library_mirror.py` under commit `747fb6b`.
- It does not certify the release as a whole.
- It does not determine the root cause of tree08 test failures or relabel historical test counts (such as the initial 174 passed / 59 failed path-budget run).
- Runtime security, binary signing, installed package validation, and client gates remain separate and open.

---

## Boundary Analysis

### Boundary 1: Process Identity Held from Relationship Proof Through Mutation

**Mechanism Evaluated**: `_verified_toolhelp_children` (lines 623–673), `_discover_owned_children` (lines 1712–1788), `_record_writer_identity` (lines 2149–2179), `_assign_owned_handle` (lines 2401–2412), `_terminate_owned_handle` (lines 2414–2423).

1. **Proof & Pinning**: In `_verified_toolhelp_children`, parent liveness is checked against `parent_handle`. For each candidate child in `_windows_process_children`, `_open_ownership_handle(child_pid)` immediately acquires a native handle with `PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_QUOTA`.
2. **Sub-Millisecond Ordering**: The child's 100-nanosecond creation timestamp (`_windows_process_created_100ns`) is compared directly against `parent_native_created`. Any process claiming parentage born prior to the parent (even within the same millisecond) is rejected.
3. **Double Snapshot with Held Handles**: Both parent and child handles remain open while a second `_windows_process_children` snapshot confirms child membership. If parent liveness fails or the child disappears from the snapshot, `_win_close_handle` runs in `finally`.
4. **Direct Mutation**: Mutations do not re-query raw PIDs via `OpenProcess`. Instead, `_assign_owned_handle` and `_terminate_owned_handle` acquire the retained handle from `_owned_handles`, verify timestamp consistency, and pass the pinned handle directly to `AssignProcessToJobObject` or `TerminateProcess`. This prevents PID recycling between identity verification and mutation.
5. **Writer Publication**: `_record_writer_identity` requires an unverified writer PID to be discovered and proved through `owned_pids()`. The writer is published only after verifying liveness through its retained handle while holding `_state_lock`.

### Boundary 2: Concurrent Handle Use/Closure and Borrowed Popen Lifetime

**Mechanism Evaluated**: `_CountedNativeHandle` (lines 1570–1636), `_VaultIoSession._launch_worker` (lines 2014–2018), `_discover_owned_children` (lines 1736–1740).

1. **Reference Counting**: `_CountedNativeHandle` synchronizes callers via `self._guard`. `acquire()` returns `None` once `request_close()` is set, preventing new users from borrowing a terminating handle.
2. **Deferred Closure**: If users are active (`self._users > 0`), `request_close()` flags `self._close_requested = True`. The OS handle is closed only when the final active user calls `release()`.
3. **Borrowed `Popen` Retention**: The launcher process handle is borrowed with `owns_close=False` and `owner=proc`. This prevents Python from garbage-collecting the `subprocess.Popen` instance while any thread retains or uses the handle.
4. **Destructor Isolation**: In `release()` and `request_close()`, `self.owner` is set to `None` inside the lock, but `del owner_to_drop` runs strictly outside `self._guard` (lines 1615, 1630). This avoids lock inversion or deadlocks if `Popen.__del__` executes during teardown.

### Boundary 3: Cancellation and Destination Exclusion Overlap

**Mechanism Evaluated**: `_discover_owned_children` (lines 1712–1788), `terminate` / `_terminate_owned` (lines 2439–2529), `_session_launch_open` (lines 949–956), `_DestExclusionOwner` (lines 1250–1364).

1. **Exclusion Pinning During Discovery**: Before iterating over candidate children, `_discover_owned_children` invokes `owner.reserve()`, incrementing `_exclusive_holds`. `_session_launch_open()` checks `_discovery_users`, ensuring `_owner_blocks_replacement()` and `owner.needed()` report active ownership.
2. **Non-Blocking Cancellation**: If `terminate()` is invoked during discovery, it marks `self._dead = True`, observes `self._discovery_users > 0`, records `cancel_return_s`, and returns `False` immediately. It avoids blocking on native OS operations or holding `_state_lock` across process queries.
3. **Deferred Cleanup**: Any child proved during concurrent cancellation is published into `self._owned_handles`. When `_discover_owned_children` finishes, its `finally` block decrements `_discovery_users` and invokes `self.terminate()` if `self._dead` is set. This sweeps and terminates all newly registered children.
4. **Exclusion Release Order**: Destination exclusion is held across the entire discovery and deferred termination sequence. `owner.drop_exclusive()` and `owner.release_if_unneeded()` execute in the outermost `finally` block only after all owned processes are terminated.
5. **Accepted `ff67b84` Repair**: `_DestExclusionOwner` and `prepare()` remain intact, retaining their gate reservation and ownership transfer semantics.

---

## Review Scope Audit & Integrity

- **Source / Test Code Edits**: None. Working tree remains clean.
- **Test Execution**: No native test runs executed. Analysis conducted via static source reading.
- **Safety Boundaries**: No subagents invoked, no network or API calls made, no git commits or merges created. `librarian_apply_enabled` remains `False`.
