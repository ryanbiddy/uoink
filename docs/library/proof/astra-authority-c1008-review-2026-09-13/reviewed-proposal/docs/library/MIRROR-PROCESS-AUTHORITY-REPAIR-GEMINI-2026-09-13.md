# Mirror Process Authority Repair (Gemini)

**Date**: 2026-09-13  
**Worker**: Gemini  
**Workspace**: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\c1008e0b-74f\gemini`  
**Reference Brief**: `docs/library/MIRROR-PROCESS-AUTHORITY-REPAIR-BRIEF-2026-09-13.md`  
**Verdict Reference**: `docs/library/ASTRA-MIRROR-PROCESS-AUTHORITY-VERDICT-2026-09-13.md`  
**Scope Boundary**: `library_mirror.py` process identity, child enumeration and adoption, liveness, and PID-based assignment and termination, plus focused synthetic regression tests in `tests/test_library_mirror_process_authority.py`. No edits to exclusion owner or prepare (Astra repairs these independently). No subagents, commits, or pushes.

---

## 1. Executive Summary and Repair Objectives

Following Astra's review of the initial diagnostic findings, this assignment implements and verifies the bounded process-authority repairs authorized by Ryan in `MIRROR-PROCESS-AUTHORITY-REPAIR-BRIEF-2026-09-13.md`.

The repair enforces four strict invariants across [library_mirror.py](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/c1008e0b-74f/gemini/library_mirror.py):
1. **Creation Order and Parent Identity Verification**: Toolhelp parent PID alone no longer authorizes child adoption. Preexisting orphan processes, children of exited or recycled parents, and children with unknown creation timestamps are rejected.
2. **Identity Preservation Across Parent Exit**: Previously verified and adopted child identities are preserved in `owned_pids()` and liveness tracking even after the launcher parent process exits.
3. **Definitive Death Retention**: Once an identity is confirmed dead—via `proc.poll()` or `_process_liveness`—that death is latched. Subsequent queries on recycled PIDs (such as `ERROR_ACCESS_DENIED`) cannot revert a dead process to `unknown`. Genuinely unresolved children continue to report `unknown`, preserving exclusion locks.
4. **Verified Handle Mutation**: PID-based process termination (`_win_terminate_pid`) and job assignment (`_win_assign_pid`) verify the process creation timestamp directly on the opened handle before issuing any mutation. Unverified or mismatched handles immediately refuse mutation.

All repairs were verified against the native verifier using inert PIDs and mocked kernel observations. Real processes were never launched, suspended, or terminated.

---

## 2. Detailed Source Modifications in `library_mirror.py`

### 2.1 Enforce Verified Identity on PID Termination and Job Assignment
In `_win_terminate_pid` and `_win_assign_pid`, mutation now strictly requires `created_ms` and verifies it against the opened handle:

```python
def _win_terminate_pid(pid: int | None, created_ms: int | None = None) -> bool:
    """Terminate only the recorded process identity. Recycled PIDs are skipped."""
    if os.name != "nt" or not isinstance(pid, int) or pid <= 0 or created_ms is None:
        return False
    k32 = _kernel32()
    handle = k32.OpenProcess(_PROCESS_TERMINATE | _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ctypes.get_last_error() in (87, 0)
    try:
        actual = _windows_process_created_ms(handle)
        if actual is None or abs(actual - int(created_ms)) > _PROCESS_START_TOLERANCE_MS:
            return False
        from ctypes import wintypes
        code = wintypes.DWORD()
        if k32.GetExitCodeProcess(handle, ctypes.byref(code)) and int(code.value) != _STILL_ACTIVE:
            return True
        return bool(k32.TerminateProcess(handle, 1))
    finally:
        k32.CloseHandle(handle)


def _win_assign_pid(job, pid: int | None, created_ms: int | None = None) -> bool:
    if job is None or os.name != "nt" or not isinstance(pid, int) or pid <= 0 or created_ms is None:
        return False
    k32 = _kernel32()
    handle = k32.OpenProcess(
        _PROCESS_SET_QUOTA | _PROCESS_TERMINATE | _PROCESS_QUERY_LIMITED_INFORMATION,
        False, int(pid),
    )
    if not handle:
        return False
    try:
        actual = _windows_process_created_ms(handle)
        if actual is None or abs(actual - int(created_ms)) > _PROCESS_START_TOLERANCE_MS:
            return False
        return bool(k32.AssignProcessToJobObject(job, handle))
    finally:
        k32.CloseHandle(handle)
```

In `_VaultIoSession._launch`:
```python
if os.name == "nt":
    for pid in self.owned_pids():
        if pid != self.pid:
            with self._state_lock:
                if not self._dead and self.job is not None:
                    _win_assign_pid(self.job, pid, self._created_for_pid(pid))
```

### 2.2 Unknown Fallback in `_process_liveness`
When an expected `created_ms` is provided but `_windows_process_created_ms(handle)` or `_posix_process_created_ms(pid)` returns `None`, the process identity cannot be confirmed. The function now returns `"unknown"` rather than falling through to `"alive"`:

```python
            if created_ms is not None:
                actual = _windows_process_created_ms(handle)
                if actual is None:
                    return "unknown"
                if abs(actual - int(created_ms)) > _PROCESS_START_TOLERANCE_MS:
                    return "dead"
            return "alive"
```

### 2.3 Child Enumeration and Identity Preservation in `owned_pids()`
`_VaultIoSession` now tracks latched dead identities in `self._dead_identities`. `owned_pids()` preserves all previously proven children from `self._owned_created` even if the parent exits, and gates new Toolhelp discovery on verified parent liveness and creation ordering:

```python
        # Preserve already proven owned child identities even after parent exits
        for pid, created in list(self._owned_created.items()):
            add(pid, exe=self._owned_exe.get(pid, ""), created=created)

        if os.name == "nt" and self.pid:
            parent_alive = True
            if self.proc is not None:
                try:
                    if self.proc.poll() is not None:
                        parent_alive = False
                except Exception:
                    parent_alive = False
            if parent_alive and _pid_is_alive(self.pid, self.created_ms):
                parent_created = self.created_ms or _process_created_ms(self.pid)
                if parent_created is not None:
                    for child in _windows_process_children(self.pid):
                        child_pid = int(child.get("pid") or 0)
                        if child_pid <= 0 or child_pid in seen or child_pid in self._owned_created:
                            continue
                        exe = str(child.get("exe") or "")
                        if _is_console_host(exe):
                            continue
                        child_created = _process_created_ms(child_pid)
                        if child_created is None or child_created < (parent_created - _PROCESS_START_TOLERANCE_MS):
                            continue
                        self._owned_created[child_pid] = child_created
                        add(child_pid, exe=exe, created=child_created)
```

### 2.4 Definitive Death Latching in `physical_liveness()`
`physical_liveness()` respects `proc.poll()` definitive death without overriding it via raw PID queries. For each tracked identity `(pid, created_ms)`, once confirmed `"dead"`, the identity is recorded in `self._dead_identities` and never re-queried by raw PID:

```python
        states: list[str] = []
        proc = self.proc
        launcher_proven_dead = False
        if proc is not None:
            try:
                poll = proc.poll()
            except Exception:
                states.append("unknown")
            else:
                if poll is None:
                    return "alive"
                launcher_proven_dead = True
                states.append("dead")
                if self.pid:
                    self._dead_identities.add((self.pid, self.created_ms))

        writer = self.writer_pid
        if writer:
            writer_identity = (writer, self.writer_created_ms)
            if writer_identity in self._dead_identities:
                states.append("dead")
            else:
                st = _process_liveness(writer, self.writer_created_ms)
                if st == "dead":
                    self._dead_identities.add(writer_identity)
                states.append(st)

        if self.pid and not launcher_proven_dead:
            launcher_identity = (self.pid, self.created_ms)
            if launcher_identity in self._dead_identities:
                states.append("dead")
            else:
                st = _process_liveness(self.pid, self.created_ms)
                if st == "dead":
                    self._dead_identities.add(launcher_identity)
                states.append(st)

        for pid, created in list(self._owned_created.items()):
            if pid in (self.pid, self.writer_pid):
                continue
            child_identity = (pid, created)
            if child_identity in self._dead_identities:
                states.append("dead")
            else:
                st = _process_liveness(pid, created)
                if st == "dead":
                    self._dead_identities.add(child_identity)
                states.append(st)

        if "alive" in states:
            return "alive"
        if "unknown" in states:
            return "unknown"
        return "dead"
```

### 2.5 Safe Writer Fallback in `_adopt_owned_tree()`
In `_adopt_owned_tree()`, fallback adoption of a python child as `writer_pid` now checks parent liveness and enforces child creation order:

```python
    def _adopt_owned_tree(self) -> None:
        self.owned_pids()
        if self.writer_pid is None and os.name == "nt" and self.pid:
            parent_alive = True
            if self.proc is not None:
                try:
                    if self.proc.poll() is not None:
                        parent_alive = False
                except Exception:
                    parent_alive = False
            if parent_alive and _pid_is_alive(self.pid, self.created_ms):
                parent_created = self.created_ms or _process_created_ms(self.pid)
                if parent_created is not None:
                    for child in _windows_process_children(self.pid):
                        exe = str(child.get("exe") or "").lower()
                        if "python" in exe and not _is_console_host(exe):
                            child_pid = int(child["pid"])
                            child_created = _process_created_ms(child_pid)
                            if child_created is None or child_created < (parent_created - _PROCESS_START_TOLERANCE_MS):
                                continue
                            self.writer_pid = child_pid
                            self.writer_created_ms = child_created
                            self._owned_created[child_pid] = child_created
                            self._owned_exe[child_pid] = str(child.get("exe") or "")
                            break
```

---

## 3. Synthetic Regression Test Suite

The regression suite in [tests/test_library_mirror_process_authority.py](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/c1008e0b-74f/gemini/tests/test_library_mirror_process_authority.py) contains 11 focused tests observing actual `EffectRecorder` objects:

| Test Name | Boundary Condition | Verified Safe Behavior |
|---|---|---|
| `test_refuse_preexisting_orphan_child` | Child created at $T_0$, launcher at $T_1$ ($T_0 < T_1$) | Refused adoption in `owned_pids()`, `owns_pid()`, `_owned_created`, and `_adopt_owned_tree()` |
| `test_refuse_children_of_exited_parent` | Launcher has exited (`proc.poll() == 0`) | Refuses Toolhelp enumeration; children not adopted |
| `test_refuse_children_of_recycled_parent` | Parent PID exists in OS with mismatched start time | `_pid_is_alive` detects recycled PID; child enumeration skipped |
| `test_refuse_unknown_creation_time_adoption` | Query for child or parent creation time returns `None` | Refuses adoption for unverified creation times |
| `test_valid_child_adoption_positive_control` | Legitimate child created after running parent | Child successfully admitted into `owned_pids()` and `_owned_created` |
| `test_previously_owned_child_survives_parent_exit` | Parent exits while previously adopted child still runs | Child remains in `owned_pids()`; session stays `alive`; exclusion held until child dies |
| `test_death_followed_by_unknown_retains_definitive_death` | Confirmed dead writer re-queried after OS PID recycling | Identity remains latched as `"dead"`; does not revert to `"unknown"` |
| `test_exited_popen_plus_unknown_other_child_retains_exclusion` | Launcher exited; separate owned child returns `"unknown"` | `physical_liveness()` is `"unknown"`; `physically_alive()` is `True`; exclusion held |
| `test_missing_or_mismatched_creation_time_refuses_kill_and_assignment` | Missing `created_ms`, mismatched time, or query failure | `_win_terminate_pid` and `_win_assign_pid` return `False`; 0 kernel mutations |
| `test_matching_creation_time_positive_control_for_kill_and_assignment` | Matching `created_ms` on open handle | `_win_terminate_pid` calls `TerminateProcess`; `_win_assign_pid` calls `AssignProcessToJobObject` |
| `test_process_liveness_creation_query_failure_returns_unknown` | `GetProcessTimes` returns `None` when checking expected identity | `_process_liveness()` returns `"unknown"`, avoiding false `"alive"` fallthrough |

---

## 4. Verification History and Preservation Record

All attempts were run with the native verifier under the prescribed environment (`IG_FORBIDDEN_LIVE=C:\Users\hello\AppData\Local\Uoink\index.db`, `PYTHONDONTWRITEBYTECODE=1`, `PHASE3_REQUIRE_IMPLEMENTATION=1`).

### Baseline (Label: `gemini-repair-baseline-01`)
- **Target**: `tests/test_library_mirror_process_authority.py` against untouched source.
- **Result**: 9 failed, 2 passed in 0.33 s (Exit 1).
- **Outcome**: Confirmed all 9 safety defects fail against unrepaired code.
- **Sealed Artifacts**: `docs/library/proof/gemini-mirror-authority-repair-2026-09-13/gemini-repair-baseline-01/`.

### Attempt 1 (Label: `gemini-repair-run-01`)
- **Target**: `tests/test_library_mirror_process_authority.py` after source repair.
- **Result**: 10 passed, 1 failed in 0.27 s (Exit 1).
- **Failure Cause**: In `test_matching_creation_time_positive_control_for_kill_and_assignment`, the mock `_mock_k32` did not substitute `wintypes.DWORD` with a `FakeDWORD`. `code.value` remained default 0, which evaluated as `int(code.value) != _STILL_ACTIVE (0x103)`. `_win_terminate_pid` interpreted the process as already terminated and returned `True` before calling `k32.TerminateProcess`, leaving `recorder.terminated_handles` empty.
- **Repair Reason Recorded**: Test mock updated to provide `FakeDWORD` and identity-passthrough `byref`, ensuring the active process reaches `TerminateProcess`.
- **Sealed Artifacts**: `docs/library/proof/gemini-mirror-authority-repair-2026-09-13/gemini-repair-run-01/`, `test_library_mirror_process_authority_attempt1.py`.

### Attempt 2 (Label: `gemini-repair-run-02`)
- **Target**: Repaired test mock and repaired source.
- **Command**:
  ```powershell
  $env:PYTHONDONTWRITEBYTECODE="1"; $env:PHASE3_REQUIRE_IMPLEMENTATION="1"; $env:IG_FORBIDDEN_LIVE="C:\Users\hello\AppData\Local\Uoink\index.db"; & "E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe" "E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\integrator_verify.py" --root "C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\c1008e0b-74f\gemini" --label "gemini-repair-run-02" --runxfail tests/test_library_mirror_process_authority.py
  ```
- **Result**: 11 passed in 0.23 s (Exit 0).
- **Sealed Artifacts**: `docs/library/proof/gemini-mirror-authority-repair-2026-09-13/gemini-repair-run-02/`.

---

## 5. Unresolved Risks and Qualifications

1. **Tree08 Failure Count**: In accordance with Astra's verdict, tree08 produced fifty mirror failures plus the historical AT6 gap (not fifty-one mirror failures).
2. **Causal Attribution**: Demonstrating that synthetic orphan adoption, PID recycling, and exit amnesia reproduce and are repaired does not prove they were the sole cause of tree08's cascade. Astra's independent repair of owner reservation and cancellation handoff addresses mutex lifetime; both repairs must be synthesized and validated together.
3. **Sequential Phase 4 Verification**: Gemini has not executed real mirror test suites or acquired the shared gate, adhering strictly to assignment boundaries. Astra will run the shared-gate Phase 4 suites sequentially in both roots after reviewing this patch.
