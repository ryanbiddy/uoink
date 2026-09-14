# Fixed Controller Resume/Publication Boundary Implementation Report

**Date**: 2026-09-14  
**Author**: Worker `gemini`  
**Workspace**: `_scratch/controller-resume-publication-implementation01`  
**Brief**: `docs/library/CONTROLLER-RESUME-PUBLICATION-IMPLEMENTATION-BRIEF-2026-09-14.md` (`691bc362c8aa2fd1b3e9623a2638dc68617d585a129a8dfee00e41dd0a822d36`)  
**Frozen Plan**: `docs/library/proof/controller-boundary-plan-2026-09-14/plan/BRIEF.md` (`2dfb90f807e83dc6124a3cadadd9ebd07badbec7896b266168669396d0aa865f`)  
**Source Bindings**: `SOURCE-BINDINGS.json` (`00c3e86b6ba90b41e9077c5efd14e666b1ed8654e1763e1eb3a04304bfe7e72b`, 8 inputs, 227,073 bytes)  
**Execution Mode**: Source-only implementation and 10 proposed controls. No qualification admission or Python execution.

---

## 1. Executive Summary

This source-only implementation addresses three connected defects in the controller lifecycle boundary for `uoink-library`:
1. Retaining fixed controller classification at factory entry outside locks so failed or substituted controller attempts cannot fall back to generated starts.
2. Rechecking current selection snapshots and custody immediately before resuming the worker (`_validate_controller_pre_resume`), under `manager._lock` then `token._lock`.
3. Rechecking current selection snapshots inside the factory publication block (`_validate_controller_worker_stage(..., 'finish_start')`), under `manager._lock` then `token._lock`, prior to publishing the worker to the session and transitioning phase to `NATIVE_RUNNING`.

All 8 donor source inputs from read-only checkout `E:\AI\projects\uoink\checkouts\Yoink-library` were verified against their exact byte counts and SHA-256 hashes. Derivatives were created strictly within the dedicated Control Room worktree under `_scratch/controller-resume-publication-implementation01`. Complete immutable `before/` copies, mechanical full unified diffs, an inert fixture, 10 proposed unexecuted test cases, `EXPECTED-CASES.json`, and `SOURCE-INPUTS.json` have been produced.

---

## 2. Three Defect Repairs

### Defect 1: Controller Classification Refusal Rule (`asr_loading_adapter.py`)
- **Location**: Appended private helper `_classify_controller_attempt(profile, permit)` in `asr_loading_adapter.py`.
- **Mechanism**:
  - Checks whether `permit` is a controller permit or `profile` is an exact `_ControllerASRStart`.
  - Enforces exact type match (`type(profile) is _ControllerASRStart`). Controller subclasses, foreign types, dictionaries, or copied startups offered against a controller permit raise `AdapterUnavailable` immediately before worker creation.
  - Requires valid issued/consumed custody matching the candidate profile in the internal registry (`_CONTROLLER_STARTUPS`). Unissued controller instances offered against a controller permit are refused.
  - Retains the classification outcome for the duration of the start attempt, preventing removed registry entries or custody modifications from falling back to generated start flows.
  - When non-controller profiles/permits are supplied, returns `is_controller=False`, leaving the unchanged generated sentinel and binding gates intact (`generated_worker_flow.py` and `generated_adapter_flow.py`).

### Defect 2: Pre-Resume Boundary Selection Check (`durable_lifecycle.py` & `asr_loading_adapter.py`)
- **Location**:
  - `_validate_controller_pre_resume(startup, full_permit, session, worker)` and locked core `_validate_controller_pre_resume_locked` appended to `asr_loading_adapter.py`.
  - Invoked in `_DurableKernel.start_owned_worker` after `bind_worker` succeeds and before `resume_owned`.
- **Lock Discipline**:
  - Takes `manager._lock` first, then `token._lock` second.
  - Retains both locks across `_validate_controller_pre_resume` and throughout the subsequent call to `resume_owned`.
- **Invariants Checked**:
  - Current issued/consumed custody snapshots and token record matching permit identity.
  - Permit identity, lease active, protection intact, live token in manager.
  - Token phase `WORKER_BOUND`, no pending operation, no revocation, no persistence failure, `resume_attempted=False`.
  - Exact worker identity matching `token.worker` and `kernel._starts[permit.identity]`.
  - Session phase `NATIVE_RESERVED`, `session._worker is None`, and live idle session.
- **Outcome on Failure**:
  - If any check fails, worker is never resumed (`resume_owned` is skipped).
  - The exact worker is stopped via `_stop_unpublished_worker(worker, "pre_resume_validation_failed")`, local revocation occurs, and the original exception propagates.

### Defect 3: Final Publication Selection Check (`durable_lifecycle.py`)
- **Location**: Inside `DurableOwnedRuntimeFactory.open_owned_session`.
- **Lock Discipline**:
  - Takes `manager._lock` first, then retrieves `token = manager._token(record.key)` and takes `token._lock` second.
  - Both locks are held across `_validate_controller_worker_stage(startup, full_permit, session, worker, 'finish_start')`, the assignment `owner._worker = worker`, and the transition `owner._phase = Phase.NATIVE_RUNNING`.
- **Invariants Checked**:
  - Re-evaluates stage validation against the retained controller attempt after `finish_start` returns from the delegate.
  - Verifies token state remains `WORKER_BOUND`, resume was attempted, worker identity is preserved, and no lease exit or revocation occurred.
- **Outcome on Failure**:
  - Publication is refused: `owner._worker` remains `None`.
  - The returned worker is stopped via `_stop_unpublished_worker(worker, "post_finish_validation_failed")`.
  - Original validation exception is preserved and propagated.

---

## 3. Lock Discipline and Reentrancy Verification

The lock hierarchy strictly adheres to the established protocol across all operations:
$$\text{Lock Order: } \texttt{manager.\_lock} \longrightarrow \texttt{token.\_lock}$$

1. **Strict Monotonic Ordering**: `manager._lock` is always acquired prior to `token._lock`. Neither lock is acquired in reverse order or interleaved with foreign locks.
2. **Outside-Lock Boundaries**:
   - Controller attempt classification occurs at factory entry outside all locks.
   - Module resolution (`asr_loading_adapter` binding) occurs at factory entry outside all locks.
   - Delegate methods (`create_suspended_worker`, `bind_worker`, `finish_start`) execute outside state locks.
3. **Reentrancy**:
   - In `_DurableKernel.start_owned_worker`, `token._lock` is an `RLock` (derived from `snapshot_reservations.Reservation`).
   - The kernel acquires `manager._lock` then `token._lock`, calls `_validate_controller_pre_resume`, and passes execution directly into `resume_owned` while retaining both locks.
   - `resume_owned` re-enters `token._lock` safely, sets `resume_attempted = True`, and invokes `resume_port` without deadlock.
4. **Atomicity**:
   - In `open_owned_session`, the publication check, worker assignment, and native running phase transition occur as a single atomic critical section under both locks.

---

## 4. Finite Import-Closure Proposal for Qualification

### Current Module Topology
- `asr_loading_adapter.py` imports `durable_lifecycle` at lines 13, 253, and 548.
- Adding a top-level reverse import in `durable_lifecycle.py` would introduce a circular module dependency.
- To maintain a clean acyclic import graph:
  - `durable_lifecycle.py` imports `asr_loading_adapter` dynamically at factory entry (`open_owned_session`) outside locks, after module initialization is complete.
  - The factory creates a private `_ControllerAttempt(is_controller, startup, permit, adapter)` data record and passes it to `_DurableKernel.start_owned_worker`.
  - In accordance with the brief and plan constraints, no record field, constructor argument, or delegate method supplies a validator callback. The kernel invokes helper methods directly on the bound adapter module reference.

### Qualification Import Closure Proposal
In the future isolated qualification process:
1. Canonical module names `durable_lifecycle` and `asr_loading_adapter` are mapped into `sys.modules` pointing directly to the derivative paths under `_scratch/controller-resume-publication-implementation01/`.
2. `controller_boundary_fixture.py` and `test_controller_resume_publication.py` import directly from canonical names:
   ```python
   from durable_lifecycle import DurableOwnedRuntimeFactory, DurableKernel, ...
   from asr_loading_adapter import _classify_controller_attempt, _validate_controller_pre_resume, ...
   ```
3. Existing accepted 95 test and fixture bytes remain untouched and completely isolated under `startup_fixture_adapter` as regression evidence.
4. Real authority entries (specifically `_fixed_real_worker_start`) remain closed and unreferenced.

---

## 5. Summary of the 10 Proposed Controls & Regression Baseline

The 10 proposed controls in `test_controller_resume_publication.py` verify the repaired boundaries using inert lower services and deterministic call logging:

| Case # | Test Identifier | Boundary / Condition Exercised |
|:---|:---|:---|
| 1 | `test_actual_controller_startup_sequence_order_and_lock_ownership` | Verifies correct call sequence: durable bind precedes single resume, finish precedes final check, worker published under both locks. |
| 2 | `test_selection_or_value_change_before_resume_stops_worker_without_resume` | Selection change after binding causes pre-resume check refusal; worker stopped with 0 resume calls. |
| 3 | `test_token_record_worker_substitution_before_resume_refuses` | Token worker substitution before resume refuses and halts worker without resume. |
| 4 | `test_already_attempted_resume_refuses_before_resume_without_reset` | Pre-resume check refuses if `resume_attempted=True` without resetting token state. |
| 5 | `test_selection_change_after_finish_start_refuses_publication_and_stops_worker` | Selection change after `finish_start` triggers factory publication check refusal; returned worker stopped. |
| 6 | `test_revocation_or_lease_exit_at_either_boundary_preserves_first_error` | Revocation or lease expiry at pre-resume or publication boundary preserves original error; stops worker. |
| 7 | `test_classification_refuses_foreign_subclassed_or_unissued_controller_without_generated_fallback` | Controller subclasses, unissued controllers, or foreign profiles against controller permits refuse without generated fallback. |
| 8 | `test_removed_or_substituted_custody_after_classification_refuses_without_fallback` | Post-classification custody tampering or registry removal refuses without falling back to generated route. |
| 9 | `test_unchanged_generated_route_preserves_gates_and_wrong_profile_refusal` | Unchanged generated profile route passes existing gates; wrong generated profile is refused properly. |
| 10 | `test_canonical_import_identity_and_closed_real_entries_restored` | Verifies canonical import identities, closed real worker entry (`_fixed_real_worker_start`), and clean module restoration. |

**Preserved Regression Baseline**:  
The accepted 95 test/fixture bytes (`fc17b67`, 95/0/0) are strictly preserved in their original closure and provide regression evidence. Candidate files were not executed or imported.

---

## 6. Source and Derivative Hashes

### Source Inputs (Verified from Read-Only Donor)
| Relative Donor Path | Size (Bytes) | SHA-256 Hash |
|:---|---:|:---|
| `_scratch/real-startup-authority-repair01/inputs/durable_lifecycle.py` | 32,833 | `3c8963eaa02bbc1d810ee2632d0363303bfe05ec6ceeef73771ca8005a00ece3` |
| `_scratch/controller-worker-stage-repair01/asr_loading_adapter.py` | 34,968 | `2f12cbf5a5f1142f892aa34df7d23af77107148b448fb4294329532e36be63ee` |
| `_scratch/windows-interrupted-owner-native-proposal02/snapshot_reservations.py` | 23,634 | `e80ae881fa4af9cc7d1a3e4a06624f5b19abe4de09aec3844e8a541449335b98` |
| `_scratch/real-startup-authority-repair01/startup_authority_fixture.py` | 8,556 | `fe82ffe16117a9a74b3194e607c86c69b4411076337965ccb5d78c8a9cec897a` |
| `_scratch/real-startup-authority-repair01/FIXTURE-LOADER-CONTRACT.md` | 2,397 | `8e59a89853faeb21c4ce8694fe7613856e44baed3feabe5c891174044b9952c4` |
| `_scratch/windows-interrupted-owner-native-proposal02/generated_worker_flow.py` | 22,853 | `1ab240d60ceaca130ac85f5d2e908ef5895da5297f35d78a1caba1c62e622238` |
| `_scratch/windows-interrupted-owner-native-proposal02/generated_adapter_flow.py` | 90,105 | `24844bf419e4d34adaf0d5c5a2678de33a4796de86dad0f83b7e386f1785f961` |
| `_scratch/admitted-controller-connection-plan01/PLAN.md` | 11,727 | `20574f4516c1443347b8eb2f948379628a432b7ae51ba04cb437a7dea64ffad5` |
| **Total (8 inputs)** | **227,073** | |

### Derivative Files in Scratch Directory
| Derivative File Path | Size (Bytes) | SHA-256 Hash |
|:---|---:|:---|
| `before/durable_lifecycle.py` | 32,833 | `3c8963eaa02bbc1d810ee2632d0363303bfe05ec6ceeef73771ca8005a00ece3` |
| `before/asr_loading_adapter.py` | 34,968 | `2f12cbf5a5f1142f892aa34df7d23af77107148b448fb4294329532e36be63ee` |
| `durable_lifecycle.py` | 34,002 | `4eeeade5384ca8172c3724a3ee2a6574ca6801e3af3408f177e586c9cd9a4dc3` |
| `asr_loading_adapter.py` | 42,939 | `94e522e622b8de3304ef48c97258a91692e70f22c3112dd6afabd6b493438611` |
| `durable_lifecycle.diff` | 9,173 | `bf1e477feb591e448f54266a7699d9d3d033fed665e7d7465d62f9c4a05713a9` |
| `asr_loading_adapter.diff` | 8,321 | `360be788a6673b4f50cb21c490b0f4e62d8a7b262fa8b5486eda8250b2ef6e91` |
| `controller_boundary_fixture.py` | 9,592 | `e9229f73dc8d004a71a6c45f73cae7e57985cf3458ca00a96dbb2120bcfbf215` |
| `controller_boundary_fixture.py.diff` | 9,853 | `cd283a0048b18b73f080488c766bb0e55007b6c69373acfe727cbde9cdcc1051` |
| `test_controller_resume_publication.py` | 11,682 | `b2c4b52127e3a51a43b05367124993c0bb4ed1f621b7eab20d63ac5d97113511` |
| `test_controller_resume_publication.py.diff` | 11,978 | `c02c4220f80a984f27bcc918f600a76283c94e90a3be359ec1df5566ca150dea` |
| `EXPECTED-CASES.json` | 1,412 | `401a3149a38ca03fc49ea150575340318e736b612c3941539a7c6d8b8c2e58f0` |
| `SOURCE-INPUTS.json` | 5,449 | `6abf08a7f718d7aa6d19f995e12408f582704841095d618fda787c4c292cd1d3` |
| `REPORT.md` | *(this file)* | |

---

## 7. Record of Draft Corrections

All source files, diff files, fixture modules, tests, and expected case definitions were produced cleanly on first pass formatted with standard line feeds (`\n`, LF) and UTF-8 encoding without BOM.
- **Draft correction record**: During derivative manifestation, an intermediate trial added `REPORT.md` to `SOURCE-INPUTS.json` (increasing its size from 5,449 bytes to 5,659 bytes, SHA256 `88f2f9640d867e80b0c87921a9f37d226754d13e25122a80004443b2b3673043`). Because inclusion of `REPORT.md` in `SOURCE-INPUTS.json` creates a circular self-referential hash dependency, `SOURCE-INPUTS.json` was reverted before freezing to its exact original 5,449 bytes and SHA256 `6abf08a7f718d7aa6d19f995e12408f582704841095d618fda787c4c292cd1d3`.
- No other text collisions, drafting errors, or replacement retries occurred.
- Zero Python (`python.exe`), testing (`pytest`), compilation, native, or Git operations were executed during generation.
- All donor source inputs remained completely untouched in read-only status.
