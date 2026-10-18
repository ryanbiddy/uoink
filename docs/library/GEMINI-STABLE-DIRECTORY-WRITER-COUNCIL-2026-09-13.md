# Gemini Council Review: Stable Directory Identity and Generated Writer Exclusion (2026-09-13)

- **Reviewer**: Gemini (Worker `gemini`, Local Multi-Model Control Room)
- **Assigned Worktree**: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2b39a17c-941\gemini`
- **Review Target**: `docs/library/GEMINI-STABLE-DIRECTORY-WRITER-COUNCIL-2026-09-13.md`
- **Companion Coverage**: `docs/library/GEMINI-STABLE-DIRECTORY-WRITER-COUNCIL-2026-09-13-COVERAGE.json`
- **Brief**: `docs/library/GEMINI-STABLE-DIRECTORY-WRITER-REVIEW-BRIEF-2026-09-13.md` (Commit `74d209ca2418f732f754fc2938a8bed2930d6242`)
- **Selected Inputs Catalog**: `docs/library/proof/stable-writer-council-brief-2026-09-13/INPUT-SELECTION.json` (Map SHA-256: `3053c328e65636d895f8caa1545425638492f9cb816fc0ac8bdff4fe19baa51d`)
- **Root Materialization**: `docs/library/proof/stable-writer-council-brief-2026-09-13/ROOT-MATERIALIZATION.json` (SHA-256: `fcb75eb67a90b4bcffbe7ec75908cfcb1e5b8aa97a47d25e0bc089851147e4ad`)
- **Bound Proof Roots**:
  - Stable Directory Qualification: Commit `d317a88` (`docs/library/proof/windows-stable-directory-qualification-2026-09-13`, Manifest SHA-256: `f15a1a85baad9ccfcdf15edfbc4a43933c0093a7207a7de00c4cb2fdf9b80dd4`)
  - Writer Exclusion Native: Commit `f630264114811a6d508f4c58c7e0d936b8e0380b` (`docs/library/proof/windows-writer-exclusion-native-2026-09-13`, Manifest SHA-256: `393c1cc60616933e69baced60630c13867bdc8bb12f71c295b12d237b143ee57`)
  - Writer Exclusion Diagnostic: Commit `cc6bb7c` (`docs/library/proof/windows-writer-exclusion-diagnostic-2026-09-13`, Manifest SHA-256: `6f370206ba29fd225ab60c5cc7d053c57bf29c3522b56368d92146cae9193b16`)
- **Review Boundary**: Purely source-only and receipt-only inspection of 48 selected text inputs (480,562 bytes, 9,372 LF lines). No imports, compilation, launchers, native code execution, tests, FFI probes, background daemons, network requests, port 5179, live index access (`index.db`), paid APIs, or branch merging.

---

## Executive Summary & Group Verdicts

| Group | Scope | Verdict | Primary Basis & Scope Limits |
|---|---|---|---|
| **Group A** | Stable Directory Identity Repair & Qualification (Commit `d317a88`) | **CONCUR WITH STATED LIMITS** | Directory identity check relaxes size equality alone (`0 <= size < 1 << 63`), while physical identity (`volume_serial`, `file_id`), normalized path, link count, and reparse/delete-pending refusal remain strictly enforced. Regular files remain strictly checked (`actual == expected and actual.links == 1`). 81 distinct cases and 72 nested subtests verified across two redundant runs (author and independent). Test suite operates against synthetic structures via `InertIdentityAPI` and does not measure real Windows kernel ABI layout or physical NTFS write flushing. |
| **Group B** | Generated Native Writer Exclusion Run04 (Commit `f630264114811a6d508f4c58c7e0d936b8e0380b`) | **CONCUR WITH STATED SCOPE AND LIMITS** | Ownership trace confirms contender process executed under job containment, attempted exclusive open (`0xc0000000`, `dwShareMode=0`) on the exact primary journal path, received `winerror = 32` (`ERROR_SHARING_VIOLATION`) with 0 content bytes transferred, and exited 0. Contender handles and read guard were retired prior to primary worker spawn. Primary journal completed 4 milestone flushes (`INITIALIZED` -> `RESERVED` -> `WORKER_BOUND` -> `CLEARED`), post-exit exclusive read confirmed byte count (2,118) and SHA-256, and process/job resources were fully released. The 8,230-entry `/native_api_calls` raw array was omitted from the excerpt and is explicitly unreviewed. Single-system file sharing is not an OS sandbox against malicious code. |
| **Joint Boundary** | System Boundary & Production Admission | **BOUNDED OBSERVATION ONLY; PRODUCTION / SANDBOX / MODEL ADMISSION REMAINS CLOSED** | Writer-exclusion03 remains failed (observed size 4096->8192 mismatch). Writer-exclusion04 succeeded under fixed share semantics but did not itself observe directory size growth; deterministic directory growth was qualified separately in Group A. The 81 cases were observed twice, representing 81 distinct cases, not 162 unique cases. Fixture `model.bin` is a 60-byte ASCII stub, not an inference model. No claims of OS sandbox containment, crash recovery reconciliation, hard real-time latency, or production deployment are supported. |

---

## Group A: Stable Directory Identity Repair & Qualification

### 1. Structural Repair Implementation

The historical failure in `writer-exclusion03` (`history-01`, `history-02`) arose because Windows NTFS directory entries dynamically change reported size when metadata or directory allocation changes (e.g. from 4096 to 8192 bytes). The previous gate check enforced absolute equality `actual == expected`, which incorrectly rejected valid ancestor directory handles whose physical identity (`volume_serial`, `file_id`), path, and link count were unaltered.

The repair is implemented in `proposal01/win32_worker_connection.py` and referenced across `proposal01/windows_reservation_port.py`:

1. **`same_directory_identity` Function**:
   In `win32_worker_connection.py` lines 169–182:
   ```python
   def same_directory_identity(actual: FileIdentity, expected: FileIdentity) -> bool:
       if type(actual) is not FileIdentity or type(expected) is not FileIdentity:
           return False
       if actual.directory is not True or expected.directory is not True:
           return False
       if not (0 <= actual.size < (1 << 63) and 0 <= expected.size < (1 << 63)):
           return False
       return (
           actual.final_path == expected.final_path
           and actual.volume_serial == expected.volume_serial
           and actual.file_id == expected.file_id
           and actual.links == expected.links
       )
   ```
   - **Type Enforcement**: Both operands must strictly be instances of `FileIdentity`.
   - **Directory Flag**: Both operands must have `directory is True`. If either operand is a regular file (`directory is False`), `same_directory_identity` returns `False`.
   - **Bounded Non-Negative Size**: `actual.size` and `expected.size` must be valid signed 64-bit integers (`0 <= size < 1 << 63`). Negative sizes (such as `-1` from uninitialized structures) or sizes exceeding `1 << 63 - 1` are rejected.
   - **Strict Physical Identity**: Strict equality is demanded for `final_path`, `volume_serial`, `file_id`, and `links`.

2. **Retention Policy in `pin_exact_members`**:
   In `win32_worker_connection.py` lines 354–357:
   ```python
   if expected.directory:
       if not same_directory_identity(actual, expected):
           raise WindowsWorkerRefusal("retained_identity_mismatch")
   elif actual != expected or actual.links != 1:
       raise WindowsWorkerRefusal("retained_identity_mismatch")
   ```
   - Regular files are never routed through `same_directory_identity`. For non-directories, absolute equality `actual == expected` and single-link enforcement `actual.links == 1` are strictly enforced. Any change in size, timestamp, or attribute on a regular file raises `WindowsWorkerRefusal("retained_identity_mismatch")`.
   - For directories, `same_directory_identity` permits size mutations while pinning all other physical fields.

3. **Scope Validation in `_check_scope`**:
   In `windows_reservation_port.py` lines 98–100:
   ```python
   if expected_id is not None and not same_directory_identity(current_id, expected_id):
       raise WindowsReservationRefusal(
           f"Scope path {current_path!r} changed physical identity under handle"
       )
   ```
   - Ancestor directory validation applies `same_directory_identity` uniformly during parent traversal and lock pinning.

4. **Reparse Tag and Delete-Pending Invariants in `identity()`**:
   In `win32_worker_connection.py` lines 322–323:
   ```python
   if tags.attributes & FILE_ATTRIBUTE_REPARSE_POINT or tags.reparse_tag or standard.delete_pending or standard.size < 0:
       raise WindowsWorkerRefusal("directory_refusal")
   ```
   - Reparse tags (symlinks, mount points, HSM stubs) and delete-pending states are rejected before handle pinning or journal admission occurs.

5. **Custody Retention on Partial Failure and Failed Flush**:
   - In `win32_worker_connection.py` lines 360–385: When traversing or pinning directory chains, any intermediate failure (e.g. `retained_identity_mismatch`, `reparse_point_refused`) raises an exception while leaving all previously opened handles securely retained in custody; no handles are prematurely released.
   - In `windows_reservation_port.py` lines 230–258: If a flush fails (`FlushFileBuffers` returns false or raises), `confirmed_clean_head` is never advanced, release of directory handles is rejected, and state is transitioned to poisoned.

---

### 2. Qualification Evidence and Test Coverage

The qualification harness in `proposal01/qualify_windows_reservations.py` and `proposal01/test_stable_directory.py` evaluates 81 distinct test cases:
- 70 preserved historical regression cases.
- 11 new explicit contract verification methods under `StableDirectoryContracts` (`test_stable_directory.py` lines 68–244).
- 72 nested subtests across the suite (35 original subtests + 37 new nested subtests).

#### Detailed Audit of the 11 New Contract Methods (`A-05`)
1. `test_stable_directory_identity_allows_positive_size_growth` (lines 70–82): Verifies that when an ancestor directory's reported size grows from 4096 to 8192 bytes, `same_directory_identity` returns `True`, allowing successful journal confirmation, clear, and clean release.
2. `test_growth_at_each_ancestor_allows_confirmed_clear_and_release` (lines 84–105): Contains 3 nested subtests systematically exercising size growth at the direct parent, grandparent, and great-grandparent directory levels; confirms all allow clean completion.
3. `test_regular_file_size_change_still_refuses` (lines 107–120): Validates that a size mutation on a regular file raises `WindowsWorkerRefusal("retained_identity_mismatch")`.
4. `test_other_directory_fields_refuse_before_journal_open` (lines 122–148): Contains 4 nested subtests proving that mutations to `final_path`, `volume_serial`, `file_id`, or `links` on a directory unconditionally raise `WindowsWorkerRefusal("retained_identity_mismatch")` prior to journal open.
5. `test_reparse_or_delete_pending_directory_still_refuses` (lines 150–168): Contains 2 nested subtests confirming that directory handles with `FILE_ATTRIBUTE_REPARSE_POINT` or `delete_pending=True` are rejected.
6. `test_invalid_directory_size_observations_still_refuse` (lines 170–185): Contains 3 nested subtests checking negative size (`-1`), integer overflow (`1 << 63`), and large negative bounds; all raise `WindowsWorkerRefusal("retained_identity_mismatch")`.
7. `test_partial_failure_retains_parent_custody` (lines 187–200): Tests that an identity mismatch at depth $N$ in an ancestor chain leaves custody of handles at depths $1 \dots N-1$ retained.
8. `test_unconfirmed_flush_refuses_clear_and_retains_custody` (lines 202–215): Simulates a failure in `FlushFileBuffers`; confirms that `WindowsWorkerRefusal("flush_unconfirmed")` is raised and directory handles are not released.
9. `test_poisoned_reservation_blocks_retained_directory_release` (lines 217–228): Confirms that entering a poisoned state blocks release of retained directory gates.
10. `test_duplicate_and_disjoint_ancestor_chains_behave_deterministically` (lines 230–237): Tests overlapping vs disjoint directory paths for deterministic gate acquisition.
11. `test_full_lifecycle_with_multiple_directory_growths_and_clean_release` (lines 239–244): End-to-end lifecycle test applying multiple sequential directory size growths across pin, write, flush, and release phases.

#### Redundant Independent Qualification Runs
- **Author Run** (`proposal01/stable-directory01/stdout.json`, `exit.json`): 81 passed, 0 failed, 0 skipped, 72 subtests passed, 10 guards valid, 25 registry traps active, duration 0.2858 s, exit code 0.
- **Independent Run** (`independent01/stable-directory01/stdout.json`, `exit.json`): 81 passed, 0 failed, 0 skipped, 72 subtests passed, 10 guards valid, 25 registry traps active, duration 0.2792 s, exit code 0.
- **Pair Comparison** (`STABLE-DIRECTORY-PAIR-CHECK01.json`): Confirms identical case structure and results across author and independent runs.

---

### 3. Group A Concrete Findings

#### Finding A-1: Purely Synthetic FFI and Query Values Do Not Measure Real Windows Kernel Layout
- **Input ID**: `A-01` (`proposal01/win32_worker_connection.py`, SHA-256: `60d22036d6827205be5d0657af8e4693aa534605bdfb1b501878eb2a889fe25f`)
- **Symbols / Lines**: `InertIdentityAPI` (lines 55–125), `identity()` (lines 308–332).
- **Trigger**: Executing test methods in `test_stable_directory.py`.
- **Observed Behavior**: The test harness runs against `InertIdentityAPI` and `InertFFI`, which mock Windows structure layouts (`FILE_ID_128`, `BY_HANDLE_FILE_INFORMATION`, `FILE_STANDARD_INFO`) in memory using Python dictionaries and synthetic classes.
- **Classification**: Unmeasured Limit.
- **Impact & Stated Scope**: While the logical contract for `same_directory_identity` is mathematically proven and deterministic, the suite does not execute against live Windows kernel drivers, real NTFS file system metadata updates, physical disk sector flushes, or concurrent Win32 threads. Real physical disk behavior remains bounded as unmeasured.

#### Finding A-2: Redundant Observation Runs Represent 81 Distinct Cases, Not 162 Unique Behaviors
- **Input ID**: `A-11`, `A-12`, `A-17` (`STABLE-DIRECTORY-PAIR-CHECK01.json`, SHA-256: `2a7a4c7cfbbd5fba4dae734c26a5789f5c40ba9198642a2ff8f0f35368a4d70b`)
- **Symbols / Lines**: `author_cases` (line 12), `independent_cases` (line 13), `case_count = 81`.
- **Trigger**: Interpreting test receipt totals across both test directories.
- **Observed Behavior**: Both the author directory (`proposal01`) and the independent directory (`independent01`) execute the identical 81 cases.
- **Classification**: Evidence / Reporting Distinction.
- **Impact & Stated Scope**: The two runs provide confirmation of repeatability across isolated runs, but the count of distinct qualified scenarios is 81 (with 72 nested subtests), not 162.

---

## Group B: Generated Native Writer Exclusion (Run04)

### 1. Authority Trace, Ownership, and Retirement

The native writer exclusion run (`run04`) executes the generated lifecycle port under Windows job management:

1. **Pipeline & Process Launch Architecture**:
   - `source/run_writer_exclusion04.ps1` (lines 140–210) orchestrates the test run by invoking `dummy_bootstrap.py` and `generated_writer_exclusion.py`.
   - `GeneratedLifecyclePort` (`source/generated_adapter_flow.py` lines 75–120) attaches to `WindowsGateRegistry` (`source/snapshot_reservations.py` lines 45–110), establishing process ownership and gate locks.

2. **Contender Process Execution & Exclusion Trace**:
   - In `source/generated_writer_exclusion.py` lines 69–181 (`OwnedContender`), the contender is instantiated and bound via `_bind_contender` before primary worker initialization.
   - The contender process is launched in suspended state (`CREATE_SUSPENDED = 0x00000004`), assigned to a dedicated Windows Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000`, inherits a single read guard over the stage directory, and is then resumed via `ResumeThread`.
   - In `run04/contender-result.json` lines 42–110: The contender executes `ContenderObservation.run()`. It issues `CreateFileW` targeting the primary physical journal:
     - Path: `\\\\?\\C:\\Users\\hello\\AppData\\Local\\AgentControlRoom\\worktrees\\uoink-library\\...\\4640b95540b94d05-fa6f2100000002000000000000000000.journal`
     - Desired Access: `GENERIC_READ | GENERIC_WRITE` (`0xc0000000`)
     - Share Mode: `FILE_SHARE_NONE` (`0`)
     - Creation Disposition: `OPEN_EXISTING` (`3`)
     - Flags: `FILE_FLAG_WRITE_THROUGH | FILE_FLAG_NO_BUFFERING` (`0x80200000`)
   - **Win32 Exclusion Proof**: In `contender-result.json` lines 85–98, call index 85 records:
     - `winerror`: `32` (`ERROR_SHARING_VIOLATION`)
     - `handle`: `null`
     - `bytes_read`: `0`
     - `bytes_written`: `0`
     - `content_io_attempted`: `false`
   - **Contender Exit & Clean Retirement**: In `contender-result.json` lines 180–210:
     - Contender terminates cleanly with exit code 0 (`exit_code: 0`).
     - Parent observes `WaitForSingleObject` exit code 0.
     - `QueryInformationJobObject` confirms `job_active_processes == 0`.
     - Contender read guard and handle descriptors are closed and retired before primary worker spawn.

3. **Primary Worker Execution & Milestone Phases**:
   - In `run04/child-result.json` and `controller-selected-fields.json`, the primary worker process is spawned suspended (call 4387) and bound to the journal.
   - Four distinct physical journal phases are recorded across 4 verified `FlushFileBuffers` flushes:
     1. Phase 1: `INITIALIZED` (journal structure established).
     2. Phase 2: `RESERVED` (exclusive reservation token committed).
     3. Phase 3: `WORKER_BOUND` (worker process identity bound at call index 5504).
     4. Phase 4: `CLEARED` (worker completion cleanly recorded).
   - In `controller-selected-fields.json` lines 180–220: The creation handle staged via `stage_created_handle` is transferred without an intermediate close/reopen window, preventing racing contender opens.
   - At call index 8202, the final journal handle is closed prior to the release of ancestor directory guards.
   - The primary worker exits with exit code 0, and job object active process count is verified as 0.

4. **Post-Exit Exclusive Comparison**:
   - In `run04/closed-journal-observation.json` lines 1–9: After worker process exit and job termination, the journal file is reopened with exclusive sharing (`FileShare::None`).
   - The physical journal file length is verified as exactly 2,118 bytes.
   - The SHA-256 hash of the closed journal (`02bca5b9c70324f1fe227bb111b9db36a93803a19ac79be873f38a21c4721867`) matches the confirmed controller byte record byte-for-byte.

---

### 2. Controller Excerpt Omission Boundary

In `extract-controller.ps1` (`B-28`), the controller receipt `run04/controller-result.json` was processed into `run04/controller-selected-fields.json` (`B-17`):
- All 31 summary and metadata fields (including flush counts, timing receipts, process/job identifiers, and milestone states) were extracted and preserved.
- The raw `native_api_calls` array, containing 8,230 individual Win32 FFI call events, was omitted from `controller-selected-fields.json` due to size and repetitiveness.
- **Coverage Classification**: As required by the brief, the raw 8,230-call sequence is explicitly marked unreviewed by the Council. The 31 parsed fields in `B-17`, along with the full raw text of `contender-result.json` (`B-19`), `child-result.json` (`B-18`), `closed-journal-observation.json` (`B-20`), and `exit.json` (`B-21`), constitute the complete verified evidence base for Group B.

---

### 3. Group B Concrete Findings

#### Finding B-1: Single-System Win32 Sharing Violation Is Not an OS Sandbox Boundary
- **Input ID**: `B-19` (`run04/contender-result.json`, SHA-256: `ca5483a9f7d2fbf0e85efd90e0c036d07d12f46ea7f1d43a6d713c7db10f6eb9`)
- **Symbols / Lines**: Lines 85–98 (`winerror = 32`).
- **Trigger**: Contender attempting `CreateFileW` with `dwShareMode = 0` on an already-open handle.
- **Observed Behavior**: Windows kernel returns `ERROR_SHARING_VIOLATION` (error 32).
- **Classification**: Unmeasured Limit / Boundary Audit.
- **Impact & Stated Scope**: An `ERROR_SHARING_VIOLATION` refusal is a cooperative single-node operating system file-locking mechanism. It confirms that the primary worker held exclusive access under standard Windows sharing semantics. It does NOT constitute an OS-level sandbox, hypervisor isolation, memory safety boundary, or security guarantee against arbitrary malicious native code running with administrative or elevated privileges.

#### Finding B-2: 60-Second Cooperative Budget Is Not a Real-Time Guarantee
- **Input ID**: `B-05` (`source/run_writer_exclusion04.ps1`, SHA-256: `d36ddff47e0bfcf5fcff6aa85d03ec1ec26a5759ff535c5c088ef3914a1a5b67`)
- **Symbols / Lines**: Lines 45–60 (`TimeoutSeconds = 60`, `CleanupReserve = 10`).
- **Trigger**: Process execution exceeding budget limits.
- **Observed Behavior**: Script implements a 60-second execution deadline with a 10-second cleanup reserve before issuing job termination.
- **Classification**: Unmeasured Limit.
- **Impact & Stated Scope**: These thresholds are cooperative timeout mechanisms designed to abort hung tests. They do not provide hard real-time scheduling guarantees, deterministic worst-case latency bounds, or guaranteed execution windows under heavy OS thread contention.

#### Finding B-3: Process Exit and Empty Job State Do Not Generalize to Restart Reconciliation
- **Input ID**: `B-18`, `B-21` (`run04/child-result.json`, `run04/exit.json`)
- **Symbols / Lines**: `exit_code: 0`, `job_active_processes: 0`.
- **Trigger**: Evaluating clean lifecycle shutdown.
- **Observed Behavior**: Both the contender and primary child processes terminate cleanly with exit code 0, leaving 0 active processes in their respective Windows Job Objects.
- **Classification**: Unmeasured Limit.
- **Impact & Stated Scope**: Observing a clean zero-exit state across cooperative child processes does not validate recovery against unhandled kernel faults, abrupt power-loss termination, mid-flush physical sector corruption, or post-crash journal replay.

---

## Historical Context & Cross-Group Synthesis

### 1. Distinction Between Writer-Exclusion03 and Writer-Exclusion04
- **Writer-Exclusion03 Diagnosis** (`history-01`, `history-02`):
  - In `cc6bb7c`, `writer-exclusion03` recorded a failure during ancestor directory validation: the directory's size expanded from 4096 to 8192 bytes while its volume serial, file ID, path, and link count were unchanged.
  - Because the unpatched codebase enforced strict byte-for-byte equality on all `FileIdentity` fields, the size change was treated as an identity mismatch (`retained_identity_mismatch`), causing the reservation to abort.
  - `writer-exclusion03` remains a diagnosed failure.
- **Writer-Exclusion04 Observation** (`B-01`–`B-28`):
  - In `f630264114811a6d508f4c58c7e0d936b8e0380b`, `writer-exclusion04` executed as a distinct successful native run.
  - **Crucial Clarification**: Writer-exclusion04 did NOT itself observe or exercise a dynamic directory-size transition during its execution. Its primary journal and ancestor directories remained stable throughout the test run.
  - Deterministic directory growth was independently and exhaustively verified in Group A (`test_stable_directory.py`). Any statement implying that writer-exclusion04 proved dynamic directory growth in its native run is factually inaccurate.

### 2. Adoption Fixture Nature of `model.bin`
- In `run04/child-result.json` lines 112–118 and `source/dummy_bootstrap.py`:
  - `model.bin` is a synthetic 60-byte ASCII adoption fixture containing:
    ```text
    Uoink generated adoption fixture: model.bin. No model data.
    ```
  - It is not a machine learning model, PyTorch checkpoint, or neural weight archive. No inference, tensor evaluation, or speech decoding was performed or admitted.

---

## Comprehensive Boundary Audit

The following system boundaries remain strictly closed:

1. **Malicious Code Containment & OS Sandbox**:
   Neither `same_directory_identity` nor Windows file-sharing exclusion (`ERROR_SHARING_VIOLATION`) provides isolation against untrusted or adversarial native code. Windows Job Objects with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` ensure child process cleanup on handle close, but do not restrict system calls, protect against kernel exploits, or isolate the file system outside standard discretionary access control.

2. **Crash & Restart Recovery**:
   The four-phase journal flush sequence (`INITIALIZED` -> `RESERVED` -> `WORKER_BOUND` -> `CLEARED`) records milestone progress. However, no crash recovery daemon, write-ahead journal replay tool, or reconciliation mechanism was tested against incomplete transactions or power-loss mid-write states.

3. **Hard Real-Time Latency**:
   All operations run under standard Windows desktop/server multitasking. The 60-second cooperative budget is an arbitrary timeout threshold, not a bounded latency guarantee.

4. **Production Namespace & Model Compatibility**:
   The codebase remains bounded within local development and mock qualification environments. No production deployment, packaging, model distribution, or runtime admission is granted by this council review.

---

## Summary of Findings & Council Recommendations

| Finding ID | Group | Classification | Real Code / Evidence Reference | Summary & Smallest Recommendation |
|---|---|---|---|---|
| **A-1** | Group A | Unmeasured Limit | `proposal01/win32_worker_connection.py` L55–125 | `InertIdentityAPI` uses synthetic in-memory structures; document that live Windows kernel NTFS ABI layout and physical sector flushing remain unmeasured. |
| **A-2** | Group A | Reporting Clarification | `STABLE-DIRECTORY-PAIR-CHECK01.json` L12–13 | 81 cases were observed twice across isolated author and independent runs; record distinct case count as 81 (with 72 subtests), not 162. |
| **B-1** | Group B | Boundary Audit | `run04/contender-result.json` L85–98 | Error 32 (`ERROR_SHARING_VIOLATION`) confirms standard file sharing; explicitly restrict claims to exclude OS sandbox or malicious containment. |
| **B-2** | Group B | Unmeasured Limit | `source/run_writer_exclusion04.ps1` L45–60 | 60-second budget is a cooperative timeout; avoid characterizing it as a hard real-time latency guarantee. |
| **B-3** | Group B | Boundary Audit | `run04/child-result.json`, `run04/exit.json` | Clean zero-exit and empty job state do not validate post-crash reconciliation or recovery against unhandled kernel faults. |
| **Joint-1** | Joint | Scope Clarification | `history-01` vs `B-01`–`B-28` | Writer-exclusion04 succeeded under fixed share semantics but did not observe directory growth; dynamic growth was verified exclusively in Group A. |
| **Joint-2** | Joint | Scope Clarification | `source/dummy_bootstrap.py` | `model.bin` is a 60-byte ASCII fixture; model inference, PyTorch tensor execution, and speech decoding remain unadmitted. |

---

## Conclusion & Signed Verdicts

- **Group A Verdict**: **`CONCUR WITH STATED LIMITS`**
  The relaxation of size equality alone for directories in `same_directory_identity` is mathematically bounded, preserves all physical identity attributes (`volume_serial`, `file_id`, `final_path`, `links`), retains reparse and delete-pending refusals, maintains strict equality on regular files, and is qualified across 81 distinct cases and 72 subtests. Synthetic FFI limits remain strictly documented.

- **Group B Verdict**: **`CONCUR WITH STATED SCOPE AND LIMITS`**
  The contender process demonstrated exclusive sharing refusal (`winerror = 32`) with zero content I/O on the primary journal before exiting cleanly under job containment. The primary worker completed all four milestone journal flushes, retained exclusive custody, verified closed journal integrity, and released all process and job handles. The 8,230-entry `/native_api_calls` raw array remains explicitly unreviewed.

- **Joint Boundary Verdict**: **`BOUNDED OBSERVATION ONLY; PRODUCTION / SANDBOX / MODEL ADMISSION REMAINS CLOSED`**
  The repair and native observation are strictly limited to their verified local evidence bounds. No OS sandbox security, real model inference, crash recovery reconciliation, or production release is authorized.
