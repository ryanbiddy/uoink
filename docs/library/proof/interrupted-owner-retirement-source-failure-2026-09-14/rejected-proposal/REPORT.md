# Implementation Report: Interrupted Owned-Session Retirement

## 1. Executive Summary

This report documents the source-only candidate implementation of a bounded retirement and reconciliation route for an interrupted owned session following a completed next-segment exchange when native handle ownership is confirmed, per `docs/library/INTERRUPTED-OWNED-SESSION-RETIREMENT-BRIEF-2026-09-13.md` and `docs/library/proof/interrupted-owner-retirement-direction-2026-09-13/corrected/INPUTS.json`.

All work is source-only and confined strictly to `_scratch/interrupted-owned-session-retirement-implementation01/`. No candidate execution, Python compilation, test execution, native process creation, or model asset probing was performed. The original files under `docs/library/proof/...` remain byte-identical.

---

## 2. Problem Statement & Root Cause

When an admitted operation is interrupted by a `BaseException` (such as `KeyboardInterrupt`), `snapshot_lifecycle._call` revokes and quarantines the owned session (`record.phase = Phase.QUARANTINED`, `owner._revoked = True`). The unwinding of `_leased_admission` executes `_DurableLease.__exit__`, which invokes `manager._flush_quarantine`, appending a 4th frame (`QUARANTINED`) to the journal.

However, two architectural gaps blocked cleanup and lease clearance:
1. **Refusal by `close_and_join`**: `OwnedSession.close_and_join()` explicitly refuses quarantined sessions (`if self._closing or self._record.phase is Phase.QUARANTINED: return False`), preventing the adapter context from verifying closure or releasing `record.protection`.
2. **Refusal by `reconcile_retired_owner`**: The existing `DurableSnapshotLifecycle.reconcile_retired_owner()` required an already closed and verified session (`_closed_verified = True`, `record.protection is None`) with only 3 journal frames (`INITIALIZED`, `RESERVED`, `WORKER_BOUND`). It offered no connected mechanism to stop the live worker, observe native process exit, close retained handles, or clear the 4-frame quarantined journal.

---

## 3. Architecture & Implementation Seams

### 3.1. Manager-Owned Retirement Attempt (`durable_lifecycle.py`)
- Added `_InterruptedRetirement` record capturing manager, record, owner, token, service, gates, worker, permit, protection, gate, journal, raw quarantine bytes, head, revision, and delegate.
- Added `DurableSnapshotLifecycle.retire_and_reconcile_interrupted_owner(owner)` (aliased as `reconcile_interrupted_owner`):
  - **Lock Ordering**: Enforces manager lock -> token lock order to validate state and publish `_interrupted_retirements[key]`.
  - **Pre-Conditions**: Requires quarantined phase, revoked owner, `_active == 0`, unclosed verified `False`, non-closing, idle pipe pair (`active is False`, `operations == []`), and all endpoint, worker, and member `HandleRecord` instances confirmed and open.
  - **Collision Exclusion**: Refuses if `key` is present in `_entering`, `_retired_recoveries`, or `_interrupted_retirements`.
  - **Delegated Execution**: Performs process wait, job verification, handle closure, and journal I/O outside the manager lock.
  - **Post-Teardown Verification**: Re-checks attempt under manager lock, sets `owner._closed_verified = True`, `owner._closing = True`, and retires `record.protection = None`.
  - **Service Reconciliation**: Executes `service.reconcile_live(token)`. Validates appending and flushing of the 5th frame (`CLEARED`), journal handle closure, and gate release.
  - **Final Publication**: Verifies 5-frame journal (`INITIALIZED -> RESERVED -> WORKER_BOUND -> QUARANTINED -> CLEARED`) and sets `record.phase = Phase.RELEASED`.

### 3.2. Dedicated Setup & Observers (`generated_journal_setup.py`)
- Added `_interrupted_probe` registration to `GeneratedJournalSetup`.
- Added `before_interrupted_close(raw_tuple)`: Validates closure of the exact created journal handle and dispatches to the probe's `before_interrupted_close(token)` observer.
- Added `complete_interrupted_recovery()`: Verifies that the recovery journal contains the exact 5 confirmed frames, that the old owner and token remain revoked, and that all 5 sync flushes succeeded.

### 3.3. Interrupted Port, Probe & Coordinator (`generated_adapter_flow.py`)
- Added `_InterruptedOperationProbe`:
  - Armed before lease entry.
  - Fires during `port.next_segment` after the second segment exchange is completed (`self._next_index == 2`), raising `KeyboardInterrupt("fixed_after_second_segment_exchange")`.
  - `observe_interruption(error)` validates the 4-frame quarantined state after adapter and seam contexts unwind.
  - `bind_service_attempt(...)` binds the manager retirement attempt to the service reconciliation call.
  - `before_interrupted_close(token)` validates the 5th frame (`CLEARED`), 5 sync flushes, and gate release before journal handle closure.
- Extended `GeneratedLifecyclePort`:
  - `retire_interrupted_worker(attempt)`: Respects the previous one-stop latch (`worker.shutdown_started`), establishes process exit via `WaitForSingleObject` and `GetExitCodeProcess` (!= 259), validates empty job via `QueryInformationJobObject` (`active_processes == 0`), closes handles individually, marks `pair.closed = True`, `read_set.released = True`, and mints `_interrupted_witness`.
  - `_interrupted_retired(worker)`: Validates the distinct witness without requiring aggregate history flags (`pair.unconfirmed`, `worker.unconfirmed`, `read_set.unconfirmed`) to be cleared.
  - `confirm_live_reconciliation(...)`: Validates `_interrupted_retired(worker)` and binds service attempt.
- Added `InterruptedCleanupCoordinator`:
  - Validates quarantined owner state after context exit.
  - Verifies that `reservations.complete` refuses revoked owners.
  - Verifies that ordinary `reconcile_retired_owner` refuses unretired owners.
  - Drives `retire_and_reconcile_interrupted_owner(session)`.
- Added `controller_interrupted_recovery_flow(port)`: Drives the actual adapter path under interruption, exercises the coordinator, validates release, and confirms old facade/stream refusal.

---

## 4. Deliverables Inventory

All artifacts are located in `_scratch/interrupted-owned-session-retirement-implementation01/`:

1. `durable_lifecycle.py`: Derivative implementing `_InterruptedRetirement` and `retire_and_reconcile_interrupted_owner`.
2. `durable_lifecycle.patch`: Unified diff against `docs/library/proof/runtime-owner-native-cancel-2026-09-13/native-preparation/durable_lifecycle.py`.
3. `generated_journal_setup.py`: Derivative implementing `before_interrupted_close` and `complete_interrupted_recovery`.
4. `generated_journal_setup.patch`: Unified diff against `docs/library/proof/runtime-owner-native-cancel-2026-09-13/native-preparation/generated_journal_setup.py`.
5. `generated_adapter_flow.py`: Derivative implementing `_InterruptedOperationProbe`, `retire_interrupted_worker`, `_interrupted_retired`, `InterruptedCleanupCoordinator`, and `controller_interrupted_recovery_flow`.
6. `generated_adapter_flow.patch`: Unified diff against `docs/library/proof/runtime-owner-native-cancel-2026-09-13/native-preparation/generated_adapter_flow.py`.
7. `test_interrupted_owner_retirement.py`: Six unexecuted proposed test contracts.
8. `read_coverage.json`: Complete record of all 16 inspected source and fixture texts (S01–S16) with line counts.
9. `REPORT.md`: This comprehensive implementation report.

---

## 5. Test Suite Architecture (`test_interrupted_owner_retirement.py`)

The test suite implements the exact six required test methods using an inert in-memory fixture (`InterruptedFixture`):

1. `test_actual_adapter_interruption_preserves_error_and_quarantine`: Verifies that interruption after the 2nd segment exchange preserves error identity, produces 4 confirmed journal frames, flushes 4 times, leaves owner and token quarantined and revoked, and refuses ordinary completion.
2. `test_confirmed_idle_owner_retires_and_reconciles_once`: Verifies that a confirmed idle quarantined owner retires and reconciles successfully, appending the 5th frame (`CLEARED`), releasing the gate, closing all native handles, and releasing `record.protection`, while refusing subsequent duplicate reconciliation attempts.
3. `test_foreign_stale_active_or_pending_attempt_refuses`: Subtests across 16 invalid manager/owner/permit/token states (foreign owner, replaced record/token/service, active operation, unrevoked owner, pending attempts) confirming refusal before clear.
4. `test_retained_io_or_uncertain_handle_refuses_without_retirement`: Subtests across 15 retained I/O and handle uncertainty faults (active pair, non-empty operations, unconfirmed handles, foreign handles) confirming custody retention without retirement.
5. `test_unobserved_exit_nonempty_job_or_close_failure_retains_custody`: Subtests across exit observation and handle closure faults (creation time change, wait timeout, still-active exit code, non-zero job processes, `CloseHandle` failure) confirming that owner remains quarantined and custody is preserved.
6. `test_reentrant_or_clear_failure_preserves_first_error_and_gate`: Verifies reentrancy refusal without holding manager lock over I/O, sync failure handling, revocation during sync, and changed manager state before final publication.

---

## 6. Unresolved Connections & Honesty Gap Report

- **Unmeasured Candidate**: In accordance with the prompt and brief instructions, no candidate execution, import, compilation, or test run was performed. All new behavior is unmeasured.
- **Model & Kernel Authority**: Real model resolution remains unconfigured (`real_resolver.REAL_APPROVAL is None`), and D3 asset acquisition and D4 native ML are unactivated.
- **Aggregate History Invariant**: Aggregate quarantine history flags (`pair.unconfirmed`, `worker.unconfirmed`, `read_set.unconfirmed`) remain `True` and are never cleared.
- **No Native Bootstrap Changes**: Neither the native launcher nor the child bootstrap was modified. Native process termination relies strictly on existing bounded APIs (`WaitForSingleObject`, `GetExitCodeProcess`, `QueryInformationJobObject`, `CloseHandle`).
