# Gemini Source-Only Corrective Council Review (2026-09-13)

- **Worker**: Gemini (`gemini`, Local Multi-Model Control Room)
- **Assigned Worktree**: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\371ebc24-906\gemini`
- **Correction Target**: `docs/library/GEMINI-WORKER-JOURNAL-ADAPTER-CORRECTION-2026-09-13.md`
- **Original Failed Report**: `docs/library/proof/worker-journal-council-failed-2026-09-13/ORIGINAL-GEMINI-REPORT.md` (36,931 bytes, SHA-256 `50a65888706d2a329318c73702b6f468c713d07f7e2bd4c48e423228f6fdda58`)
- **Review Basis**: `docs/library/proof/worker-journal-council-correction-brief-2026-09-13/BRIEF.md` (SHA-256 `74750efa942ab5e8f76e0ddcb2b42c1d9935e349b0183f318ea35a397753587a`), `ROOT-REVIEW.md`, `DISCREPANCIES.md`, `CORRECTION-INPUTS.json`
- **Correction Scope**: 33 catalog inputs (S01–S70 subset), 6,422 required lines across Groups 1, 2, and 3.
- **Review Boundary**: Purely read-only source and receipt review. No tests executed, candidate modules imported, launchers run, native/FFI code invoked, model/checkpoint assets accessed, support binaries read, live index queried, or network ports contacted. Historical failure history at commit `58335df` and corrected qualification history at commit `8fc32194` are strictly preserved without relabeling.

---

## Executive Summary & Group Dispositions

This review corrects factual errors, inaccurate citations, invented code blocks, and misattributed protocol mechanisms in the original council report. It establishes exact source alignment without granting runtime authority, changing test outcomes, or altering product code.

| Group | Target Scope | Audit Status | Primary Corrections Applied |
|---|---|---|---|
| **Group 1** | Runtime owner and actual `WorkerBootstrap` (Commit `bbe10d6`) | **CORRECTED** | Replaced 17 test identifiers with exact names from S17:5–21; separated S12 `_owner_operation` from G3 S42 `_factory_operation`; removed invented fixture quotation; corrected injected fault types to `KeyboardInterrupt` in S14:126 and S14:196; distinguished retained bootstrap product (`b._product`) from unpublished registry product (`b.registry._product is None`); corrected receipt paths to exact map paths ending in `runs/wbo01/stdout.json`; accurately characterized S07 fake PyTorch module/storage; retained deterministic nested re-entrancy limitation without mandating unapproved cross-thread suites. |
| **Group 2** | Windows journal invariants, locking and correction history (Commit `58335df` vs `8fc32194`) | **CORRECTED** | Traced `WindowsJournalStream`, `PersistenceUnconfirmed('native_journal_poisoned')`, `write_revision`, `confirmed_bytes`/`confirmed_revision`, and `confirmed_clean_head()` from S31; identified `_transition` as a module-level journal replay validator rather than a service dispatch method; withdrew original G2-1 and grounded private-caller boundaries in S46:39–41; corrected physical-key snapshot anchors (S35:337–343) and exclusive open (S31:276–277); replaced false patch text with exact 20-line diff from S51; preserved 63/2 failed history (S48/S49) and 65/0 corrected pass history (S60/S64); explicitly separated runner, launcher, and outer tool time intervals. |
| **Group 3** | Durable startup sequence and no-worker retirement | **CORRECTED** | Traced split startup sequence through actual method calls in S36, S32, S39, and S40; verified `primitives._resume_after_future_admission` at S40:158; corrected no-worker test entry point (`actual_flow.adapter.ensure_assets`), mutations, and all 6 fault labels from S54:468–495; distinguished `completion_evidence`, `confirm_teardown`, and `confirm_live_reconciliation` in S39; retained unpublished-worker stop identity rules (S36:234–243) and quarantine behavior (S45:149–168); qualified generic callback deadlock as an unmeasured concern rather than a source defect; confirmed closed native/model boundaries. |

---

## Group 1: Runtime Owner and Actual WorkerBootstrap

### 1. Verification of the 17 Qualified Case Identifiers
The original report listed paraphrased test names. The canonical ordered list of seventeen qualified cases resides in S17:5–21 (`EXPECTED-CASES.json`) and is validated against source definitions in S11:14–26 and S14:13–20:

**11 Unchanged Owner Controls (`generated_unit_cases.py` / S11:14–26, S17:5–15):**
1. `generated_unit_cases.OwnerContracts.test_01_actual_factory_publication_keeps_registry_identity`
2. `generated_unit_cases.OwnerContracts.test_02_foreign_vad_and_namespace_refused`
3. `generated_unit_cases.OwnerContracts.test_03_foreign_pcm_and_sample_rate_refused`
4. `generated_unit_cases.OwnerContracts.test_04_replaced_mutated_and_expired_pcm_refused`
5. `generated_unit_cases.OwnerContracts.test_05_overlapping_operation_and_release_refused`
6. `generated_unit_cases.OwnerContracts.test_06_revocation_blocks_publication_and_retains_owners`
7. `generated_unit_cases.OwnerContracts.test_07_real_constructor_pcm_and_filter_routes_remain_closed`
8. `generated_unit_cases.OwnerContracts.test_08_vad_only_retirement_blocks_publication`
9. `generated_unit_cases.OwnerContracts.test_09_replaced_completed_product_blocks_publication`
10. `generated_unit_cases.OwnerContracts.test_10_replaced_runtime_module_blocks_publication`
11. `generated_unit_cases.OwnerContracts.test_11_revoked_model_lease_blocks_publication`

**6 Actual Bootstrap Connection Controls (`connection_cases.py` / S14:13–20, S17:16–21):**
12. `connection_cases.BootstrapContracts.test_01_actual_bootstrap_build_register_use_release`
13. `connection_cases.BootstrapContracts.test_02_missing_guard_refuses_before_constructor`
14. `connection_cases.BootstrapContracts.test_03_registration_failure_retains_completed_product`
15. `connection_cases.BootstrapContracts.test_04_first_error_survives_both_revocation_failures`
16. `connection_cases.BootstrapContracts.test_05_release_cannot_overlap_use`
17. `connection_cases.BootstrapContracts.test_06_constructor_error_retains_inputs_before_factory_assignment`

### 2. Protocol Separation: S12 `_owner_operation` vs S42 `_factory_operation`
The original report conflated the Group 1 protocol with Group 3. Source inspection establishes their distinct structures:
- **Group 1 (`owned_generation_protocol.py`, S12:301–317)**: `WorkerBootstrap` exposes `_owner_operation(self, phase)`:
  ```python
  @contextmanager
  def _owner_operation(self, phase):
      try:
          owner = self.registry
          _require(type(owner) is _WorkerRuntimeOwnerProposal, "worker_owner_identity")
          with owner.operation(self._permit, phase) as token:
              _require(self._ready and self._started and not self._closed,
                       "worker_generation_not_started")
              self._channel._live()
              yield token
              with owner._lock:
                  owner._live_locked()
                  _require(not self._closed and self.registry is owner, "worker_publication_revoked")
      except BaseException as original:
          self.close_preserving(original)
          raise
  ```
  `_owner_operation` delegates directly to `owner.operation` (S09:99–119). Re-entrant or concurrent access raises `RuntimeOwnerRefusal('operation_already_active')` at S09:104. S12:181 defines `GenerationChannel._operation()`, an internal transport context manager.
- **Group 3 (`owned_generation_protocol.py`, S42:270–304)**: This older protocol defines `_factory_lock = RLock()`, `_factory_active = False`, and `_factory_operation(self)`. Entering while active raises `ProtocolRefusal('factory_operation_already_active')` (S42:298).

### 3. Fixture Mechanics & Removal of Invented Code Excerpt
The code block presented in lines 29–36 of the original report does not exist in `generated_bootstrap_fixture.py`.
- In S13:134, the fixture instantiates `bootstrap = protocol.WorkerBootstrap(channel, Registry, Factory)`.
- Lines S13:135–144 verify clean initial module globals (`guard._RUNTIME is None and previous_model is object`), set `Model = FakePyanNet`, and yield the fixture namespace without pre-asserting internal bootstrap attributes.
- The actual unbuilt pre-execution checks are located in `connection_cases.py` under the helper `begin(test, f)` (S14:38–63):
  ```python
  b = f.bootstrap
  test.assertIsNone(b.registry)
  test.assertIsNone(b._factory)
  test.assertEqual(f.runtime.events, [])
  ```
  After challenge acceptance, `b.registry` is created, and before factory construction, `b._factory` and `b._product` remain `None` (S14:60–61).

### 4. Accurate Injected Faults and Product Ownership
- **Constructor Fault (S14:192–214, `test_06`)**: The fault is injected by replacing `f.runtime.get_default_dtype` with a callable raising `KeyboardInterrupt('generated factory constructor context')` (S14:196–199), not `RuntimeError("fail_before_factory")`. Upon failure, `b._factory` is `None`, `b._factory_inputs` preserves the 4-tuple `(f.fixed, f.port, f.state, f.state_binding)` (S14:208–211), and `b.registry._active` is `False`.
- **Registration Fault (S14:122–142, `test_03`)**: The failure is injected by replacing `b.registry.register_vad_product_for_bootstrap` with a callable raising `KeyboardInterrupt('generated registration refusal')` (S14:126–129), not `_issue_for_bootstrap` raising `RuntimeOwnerRefusal("bad_registration")`.
- **Ownership State After Registration Failure**:
  - `b._factory._completed.vad is b._product` evaluates to `True` (S14:133): the bootstrap instance retains the built product reference.
  - The registry's internal product reference is unset: `b.registry._product is None` evaluates to `True` (S14:138).
  - The registry retains model and factory references in `b.registry._retained[3]` and `[4]` (S14:135–136).
  The distinction between bootstrap-held product and registry-held product is a material ownership boundary.

### 5. Dual Revocation Error Preservation
In S14:143–173 (`test_04`), when `register_vad_product_for_bootstrap` fails with `KeyboardInterrupt`, `b.registry.revoke_generation` raises `RuntimeError('generated owner revoke failure')`, and `b._channel.revoke` raises `ValueError('generated channel revoke failure')`:
- The primary exception (`KeyboardInterrupt`) survives and is re-raised (S14:162).
- Explanatory notes are attached to the primary exception via `BaseException.add_note` (`Worker revocation remains unconfirmed: ...`, S12:419).
- Both cleanup paths are attempted sequentially, and the bootstrap marks itself quarantined (`b._quarantined is True`, S14:165).

### 6. Qualification Runner and Receipt Paths
- **Runner Mechanics (`qualify_owner.py`, S15)**: S15 contains no `run_all` method. Capture handling is defined at S15:116–136 (`BoundedCapture`), test suite membership is checked at S15:158–168 (`CASE_GROUPS`, `CASE_CLASSES`), and test execution runs sequentially across `EXPECTED_CASES` at S15:182–190.
- **Receipt Paths**: The exact receipt paths in the repository catalog are:
  - Author run: `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/stdout.json` (S20, 163 lines, SHA-256 `0c9d129aed5415e765359de289c10587ca6cdcc46d5a94c47125a4a69e25b3b9`).
  - Independent confirmation: `docs/library/proof/worker-bootstrap-owner-2026-09-13/astra-worker-bootstrap-owner-confirmation01/runs/wbo01/stdout.json` (S24, 163 lines, SHA-256 `61b82279c19a61372a3ce085f66f4e6b750b0c849dfe6aa94274cb6fe466a672`).
  Shorthand notations like `author/stdout.json` or `independent/stdout.json` are historical note data, not exact repository paths.
- Both receipts record 17 passed cases, 0 failures, exit code 0, with elapsed times of 27.7490822 s (S20:142) and 27.4396958 s (S24:142).

### 7. Accurate Description of Fake Torch Support
- In S07:83–135 (`fake_torch_support.py`), `fake_torch()` constructs an isolated `types.ModuleType('torch')`. It provides `FakeTensor` (S07:21–81) backed by `FakeStorage` (S07:8–19).
- There is no `FakeTorchModule` class, and no tensor operations execute model forward passes or audio inference. S13:77–111 supplies a `FakePyanNet` mock with `build()`, `load_state_dict()`, and `eval()` methods. No inference or forward-pass execution occurs in these tests.

### 8. Group 1 Findings Reassessment
- **Finding G1-1**: The claim that `owned_generation_protocol.py` line 296 defines `_factory_operation` is **WITHDRAWN**. That member belongs to G3 S42. In G1 S12:301–317, re-entrancy is governed by `_owner_operation` and S09:99–119 `owner.operation`. The core limitation is **RETAINED**: S14:174–190 tests deterministic single-threaded nested overlap, not a preemptive multi-threaded OS schedule. No new multi-threaded test suite requirement is imposed by this correction.
- **Finding G1-2**: **RETAINED WITH ACCURATE CITATION**. The 34 test entries across S20 and S24 represent two executions of the identical 17 cases, validating reproducibility rather than 34 distinct behaviors.
- **Finding G1-3**: **RETAINED**. Real PyTorch and inference remain unexercised; all operations are bounded within fake tensor and storage harnesses.

---

## Group 2: Windows Journal Interface, Locking, and Correction History

### 1. Journal Stream Interface, Poisoning, and Confirmation Mechanics
- **Class and Exception Names**: The stream implementation in `windows_reservation_port.py` (S31:103) is `WindowsJournalStream`, not `WindowsReservationStream`. The error raised on poisoned operations (S31:69–71, 120) is `PersistenceUnconfirmed('native_journal_poisoned')`, not `KernelUnconfirmed('stream_is_poisoned')`.
- **Stream Methods and Revision Tracking**:
  - `WindowsJournalStream` provides `identity()`, `_call()`, `seek()`, `read()`, `write()`, `flush()`, and `sync()` (S31:118–195). It contains no `write_record()` or `truncate()` method.
  - `write(payload)` increments `self.write_revision += 1` at S31:175.
- **Confirmation State**:
  - `ConfirmedWindowsJournal` (S31:197–224) tracks durability through `self.confirmed_bytes` and `self.confirmed_revision` (S31:203–204).
  - Clean head inspection is provided by the method `confirmed_clean_head()` (S31:218–224), which verifies `self.confirmed_revision == self._stream.write_revision` before decoding rows.
- **Short Writes and Pre-I/O Refusal**:
  - Partial writes are completed in a loop in `reservation_file_port.py` (S33:60–66) and verified in `test_windows_reservations.py` (S54:240–246, `test_short_native_writes_complete_exact_journal`).
  - Pre-I/O argument refusal (`stream.seek(-1)`, `stream.read(0)`, `stream.write(b"")`) raises `PersistenceUnconfirmed` without incrementing API calls or setting `stream.poisoned` (S54:293–304, S47:9–10).
- **Physical Identity & Handle Exclusions**:
  - Physical snapshot binding is checked in `test_reservations.py` (S35:337–343, `test_physical_gate_ignores_semantic_aliases`) using synthetic `PhysicalSnapshot(volume, file_id)` records, not filesystem path alias resolution.
  - Exclusive journal handle creation in `WindowsGateRegistry.acquire()` (S31:265–294) calls Win32 `CreateFileW` with share mode `0` (S31:276–277) to ensure exclusive access.
  - Ancestor directory validation is performed in S31:86–100 (`_check_scope`) and S31:258–263 (`_ancestors`). The resolver's `_checked_chain()` in S38:205–214 is a separate asset path validator.

### 2. State Locks, Replay Validation, and Private Caller Boundaries
- **Replay Validator**: In `snapshot_reservations.py` (S32:76–100), `_transition(prior, row, generations)` is a module-level pure function validating journal frame sequences. It is not an instance method on `ReservationService`, does not acquire state locks, and does not dispatch operations.
- **Per-Token State Locking**: `ReservationService` operations (`bind_worker` S32:345–369, `quarantine` S32:402–427, and `_clear` S32:440–484) serialize transitions using per-reservation locks (`token._lock`), transition markers (`token.pending = object()`), and revision counters (`token.revision`).
- **Private Caller Boundary**: S46:39–41 explicitly defines the concurrency boundary:
  > "This relies on the private ReservationService pending/revision and gate-owner protocol excluding another operation; arbitrary concurrent direct stream or journal calls are not supported. Streams have no ownership-closing destructor."
- **Manager Lock During Sync**: In `test_reservations.py` (S35:650–670, `test_journal_sync_never_holds_manager_state_lock`), `manager._lock._is_owned()` is verified `False` during journal sync callbacks, confirming that disk I/O does not block manager lifecycle state transitions.

### 3. Exact Patch Bytes and Failure History Analysis
The original report misquoted the unapplied patch and misrepresented the initial test failure.
- **Original Failed Observation (Commit `58335df`)**:
  - Result: 63 passed, 2 failed, 0 skipped, with 6 failed subtests (S48:629–631, S49:8–10).
  - Failed case 1: `test_old_completion_cannot_clear_fresh_lease_record` (S48:411–420).
  - Failed case 2: `test_started_or_reserved_native_state_cannot_claim_no_worker_cleanup` with all 6 subtest faults failing (`start`, `resume`, `worker_reserved`, `native_permit`, `owner`, `retained_worker`) (S48:423–477).
- **Exact Patch Contents (`fixture-correction.UNAPPLIED.patch.txt`, S51:1–20)**:
  ```diff
  --- a/test_windows_reservations.py
  +++ b/test_windows_reservations.py
  @@ -486,7 +486,7 @@ class ActualAdapterNoWorkerContracts(unittest.TestCase):
                       return port.generated_admission
                   port.generated_admit = admit
                   with actual_flow.generated_authority_seams(port):
  -                    with self.assertRaises(AssertionError):
  +                    with self.assertRaises(actual_flow.operation_flow.adoption_flow.KernelUnconfirmed):
                           actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)
                   self.assertIn(f.physical, f.gates._held)
                   self.assertIsNone(port._no_worker_witness)
  @@ -499,7 +499,7 @@ class ActualAdapterNoWorkerContracts(unittest.TestCase):
               actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)
           f, next_port = self.port(f, "2" * 64)
           with next_port.lifecycle.read_lease(next_port.cwd, actual_flow.CHOICE, actual_flow.REVISION):
  -            with self.assertRaisesRegex(AssertionError, "current_retired_lifetime_required"):
  +            with self.assertRaisesRegex(actual_flow.operation_flow.adoption_flow.KernelUnconfirmed, "current_retired_lifetime_required"):
                   port.completion_evidence(None)
               self.assertFalse(next_port._no_worker_retired())
               self.assertIn(f.physical, f.gates._held)
  ```
  The patch changes the expected exception from `AssertionError` to `KernelUnconfirmed` around `adapter.ensure_assets` and `port.completion_evidence(None)`. It does not call `confirm_teardown` or `confirm_live_reconciliation` in the diff.
- **Corrected Qualification Runs (Commit `8fc32194`)**:
  - Author run: 65 passed, 0 failed, 33/33 subtests passed (S60:599–601); test runner time 0.0743584 s (S60:710); launcher time 0.5505172 s (S61:14); outer-tool wall time 0.9468553 s (S68:3).
  - Independent run: 65 passed, 0 failed, 33/33 subtests passed (S64:599–601); test runner time 0.0724728 s (S64:710); launcher time 0.5160142 s (S65:14); outer-tool wall time 0.9084892 s (S69:3).

### 4. Group 2 Findings Reassessment
- **Finding G2-1**: **WITHDRAWN AS WRITTEN AND RESTATED**. `_transition` is a replay validator, not a service dispatch method holding `self._lock`. Direct stream access is prevented by architecture rather than a product wrapper: `ReservationService` relies on the private pending/revision protocol, and streams are not exposed to external callers (S46:39–41).
- **Finding G2-2**: **CORRECTED**. The failure in commit `58335df` involved 2 tests and 6 subtests where the test expected `AssertionError` while implementation raised `KernelUnconfirmed`. The exact 20-line patch in S51 resolved both test cases without altering production implementation bytes.

---

## Group 3: Durable Startup Sequence, No-Worker Retirement, and Scope

### 1. Trace of the Durable Startup Sequence
The durable startup flow traces through distinct cooperating methods across S36, S32, S39, and S40:
1. **Suspended Worker Creation**: `DurableSnapshotLifecycle._kernel.start_owned_worker` calls `manager._delegate.create_suspended(protection, permit, profile)` (S36:209). In `GeneratedLifecyclePort` (S39:211–228), this creates the suspended child process and establishes the channel handshake.
2. **Worker Binding**: `manager._reservations.bind_worker(token, worker)` (S36:213, S32:345–369) logs the suspended worker's PID and creation time in the journal under `token._lock`, transitioning from `RESERVED` to `WORKER_BOUND`.
3. **Owned Resume**: Under `manager._lock`, `manager._reservations.resume_owned(token, manager._delegate.resume)` is invoked (S36:216–219, S32:378–393). In `GeneratedLifecyclePort.resume` (S40:153–160), the resume helper executes at **S40:158**:
   ```python
   def resume(self, worker):
       record = self._record(self.read_set, self.permit)
       _assert(worker is self.worker and record.phase is Phase.NATIVE_RESERVED
               and not record.owner._revoked, "exact_suspended_resume_owner")
       self._resume_attempted = True
       self.primitives._resume_after_future_admission(worker)
       return True
   ```
4. **Unlocked Finish Start**: `manager._delegate.finish_start(worker, permit, profile)` (S36:222) executes **outside both manager and reservation state locks**. In S39:229–245, this executes pipe bootstrap, read-set adoption, and policy handshake (`bind_generated_adapter_start` -> `generated_adapter_start_bound`).
5. **Publication**: In `DurableOwnedRuntimeFactory.open_owned_session` (S36:167–173), after `finish_start` succeeds and `record.phase` is confirmed unrevoked under `manager._lock`, `owner._worker = worker`, `record.phase = Phase.NATIVE_RUNNING`, and `owner` is returned.

### 2. Unpublished-Worker Stop & Error Handling
- **Stop Handling (S36:234–243, `stop_unpublished`)**: If an exception occurs after worker creation but prior to publication, `stop_unpublished(worker, permit, original)` is invoked. Authorization requires exact retained worker identity:
  ```python
  if worker is None or self._starts.get(permit) is not worker:
      raise LifecycleUnavailable("Exact retained unpublished worker required")
  ```
  PID data or caller authority cannot authorize process termination.
- **Pipe Quarantine (S45:149–168)**: `_quarantine` marks `pair.unconfirmed = True`, `read_set.unconfirmed = True`, and `worker.unconfirmed = True`. Uncertain handles and buffers are retained rather than discarded as clean.
- **Error Preservation**: Cleanup failures append notes to the primary exception via `BaseException.add_note` (S36:54, S36:229, S37:237).

### 3. Ensure Assets and Initial Admission Refusals
- In `asr_loading_adapter.py` (S37:133–160, `_leased_admission`), when `admit_snapshot()` raises `AdmissionRefusal` and `consent_given` is `False`, `AssetConsentRequired` is raised immediately.
- Tested in `test_windows_reservations.py` (S54:428–451, `test_initial_admission_refusal_closes_cleanly_before_consent_error` and `test_initial_admission_nonconsent_error_preserves_original_and_retires`), confirming clean lease exit without worker process creation.

### 4. No-Worker Teardown Witness & The Six Native Fault Branches
- **No-Worker Witness Generation (`generated_adapter_flow.py`, S39:127–152)**:
  - When `release_read` is called with `record.owner is None`, it verifies:
    ```python
    record.phase is Phase.PROTECTED and record.permit is None
    and record.protection is protection and self._never_started(protection)
    and token.worker is None and token.phase == "RESERVED" and not token.revoked
    and token.pending is None and token.generation == self.generation
    ```
  - It releases the read set (`release_read_set(protection)`), sets `self._no_worker_witness = (record, token, protection)`, and mints `self._completion = object()`.
- **Distinct Callback Methods (S39:153–172)**:
  - `completion_evidence(self, worker)`: returns `self._completion` if `_retirement_matches(worker)`.
  - `confirm_teardown(self, worker, evidence)`: consumes `self._completion` and returns `True`.
  - `confirm_live_reconciliation(self, worker, physical, generation, head, attempt)`: separate trusted observer requiring fresh verification of retired guards and matching generation.
- **The Six Invalid Native State Branches (S54:468–495)**:
  In `test_started_or_reserved_native_state_cannot_claim_no_worker_cleanup`:
  - Entry point: `actual_flow.adapter.ensure_assets(actual_flow.CHOICE, model_root=port.cwd)` (S54:490).
  - Injected faults:
    1. `fault='start'`: sets `port._start_attempted = True` (S54:475)
    2. `fault='resume'`: sets `port._resume_attempted = True` (S54:477)
    3. `fault='worker_reserved'`: sets `port.read_set.worker_reserved = True` (S54:479)
    4. `fault='native_permit'`: mutates `record.permit = object()` (S54:481)
    5. `fault='owner'`: mutates `record.owner = SimpleNamespace()` (S54:483)
    6. `fault='retained_worker'`: appends `SimpleNamespace(read_set=port.read_set)` to `f.primitives.workers` (S54:485)
  - Outcome: Each fault raises `KernelUnconfirmed`. The test verifies `f.physical in f.gates._held`, `port._no_worker_witness is None`, `port._completion is None`, and `not port.read_set.released`.
- **Stale Completion Test (S54:496–506)**:
  `test_old_completion_cannot_clear_fresh_lease_record` verifies that attempting to use an old port's `completion_evidence(None)` inside a subsequent lease raises `KernelUnconfirmed` with regex `"current_retired_lifetime_required"`.

### 5. Group 3 Findings Reassessment
- **Finding G3-1**: **QUALIFIED AS UNMEASURED CONCERN**. `finish_start` executes unlocked outside state locks by design (S36:220–224). The finding that callback re-entry could cause deadlocks is an unmeasured architectural observation, not an observed deadlock defect or a demonstrated bug in the code. No new ban on subsequent state-lock acquisition is warranted.
- **Finding G3-2**: **RETAINED**. Native Whisper/CTranslate2 execution, live process recovery, and C-level audio parsing remain unintegrated and unadmitted. `REAL_APPROVAL` remains `None` (S38:51).

---

## Line Coverage Inventory (33 Inputs, 6,422 Required Lines)

Every required line chunk across the 33 catalog inputs was read in bounded visible tool calls. Displayed line ranges and gap checks are recorded below:

| ID | Grp | Repository-Relative Path | Required Range | Displayed Range | Displayed Lines | Gaps | Status |
|---|---|---|---|---|---|---|---|
| **S07** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/fake_torch_support.py` | 1–137 | 1–137 | 137 | 0 | Full Rendered Coverage |
| **S09** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/worker_runtime_owner.py` | 1–292 | 1–292 | 292 | 0 | Full Rendered Coverage |
| **S11** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/generated_unit_cases.py` | 1–230 | 1–230 | 230 | 0 | Full Rendered Coverage |
| **S12** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/owned_generation_protocol.py` | 1–478 | 1–478 | 478 | 0 | Full Rendered Coverage |
| **S13** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/generated_bootstrap_fixture.py` | 1–157 | 1–157 | 157 | 0 | Full Rendered Coverage |
| **S14** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/connection_cases.py` | 1–214 | 1–214 | 214 | 0 | Full Rendered Coverage |
| **S15** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/qualify_owner.py` | 94–98, 116–236 | 94–98, 116–236 | 126 | 0 | Full Rendered Coverage |
| **S17** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/EXPECTED-CASES.json` | 1–23 | 1–23 | 23 | 0 | Full Rendered Coverage |
| **S20** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/worker-bootstrap-owner-instrument01/runs/wbo01/stdout.json` | 1–163 | 1–163 | 163 | 0 | Full Rendered Coverage |
| **S24** | G1 | `docs/library/proof/worker-bootstrap-owner-2026-09-13/astra-worker-bootstrap-owner-confirmation01/runs/wbo01/stdout.json` | 1–163 | 1–163 | 163 | 0 | Full Rendered Coverage |
| **S31** | G2 | `docs/library/proof/windows-reservation02-2026-09-13/author/windows_reservation_port.py` | 1–324 | 1–324 | 324 | 0 | Full Rendered Coverage |
| **S32** | G2 | `docs/library/proof/windows-reservation02-2026-09-13/author/snapshot_reservations.py` | 1–487 | 1–487 | 487 | 0 | Full Rendered Coverage |
| **S33** | G2 | `docs/library/proof/windows-reservation02-2026-09-13/author/reservation_file_port.py` | 1–106 | 1–106 | 106 | 0 | Full Rendered Coverage |
| **S35** | G2 | `docs/library/proof/windows-reservation02-2026-09-13/author/test_reservations.py` | 337–351, 650–670 | 337–351, 650–670 | 36 | 0 | Full Rendered Coverage |
| **S36** | G3 | `docs/library/proof/windows-reservation02-2026-09-13/author/durable_lifecycle.py` | 1–273 | 1–273 | 273 | 0 | Full Rendered Coverage |
| **S37** | G3 | `docs/library/proof/windows-reservation02-2026-09-13/author/asr_loading_adapter.py` | 1–91, 133–248 | 1–91, 133–248 | 207 | 0 | Full Rendered Coverage |
| **S38** | G3 | `docs/library/proof/windows-reservation02-2026-09-13/author/trusted_asr_resolver.py` | 45–55, 177–214 | 45–55, 177–214 | 49 | 0 | Full Rendered Coverage |
| **S39** | G3 | `docs/library/proof/windows-reservation02-2026-09-13/author/generated_adapter_flow.py` | 1–405 | 1–405 | 405 | 0 | Full Rendered Coverage |
| **S40** | G3 | `docs/library/proof/windows-reservation02-2026-09-13/author/generated_worker_flow.py` | 1–371 | 1–371 | 371 | 0 | Full Rendered Coverage |
| **S42** | G3 | `docs/library/proof/windows-reservation02-2026-09-13/author/owned_generation_protocol.py` | 1–33, 255–344, 410–422 | 1–33, 255–344, 410–422 | 136 | 0 | Full Rendered Coverage |
| **S45** | G3 | `docs/library/proof/windows-reservation02-2026-09-13/author/win32_private_pipe.py` | 149–200 | 149–200 | 52 | 0 | Full Rendered Coverage |
| **S46** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/author/API-AND-INTEGRATION.md` | 1–75 | 1–75 | 75 | 0 | Full Rendered Coverage |
| **S47** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/author/PEER-REVIEW03-POISONING.md` | 1–12 | 1–12 | 12 | 0 | Full Rendered Coverage |
| **S48** | G2/3 | `docs/library/proof/windows-reservation-failed-2026-09-13/proposal/windows-reservation01/stdout.json` | 410–477, 628–643, 738–743 | 410–477, 628–643, 738–743 | 90 | 0 | Full Rendered Coverage |
| **S49** | G2/3 | `docs/library/proof/windows-reservation-failed-2026-09-13/proposal/windows-reservation01/exit.json` | 1–15 | 1–15 | 15 | 0 | Full Rendered Coverage |
| **S51** | G2/3 | `docs/library/proof/windows-reservation-failed-2026-09-13/preparation/fixture-correction.UNAPPLIED.patch.txt` | 1–20 | 1–20 | 20 | 0 | Full Rendered Coverage |
| **S54** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/author/test_windows_reservations.py` | 196–506 | 196–506 | 311 | 0 | Full Rendered Coverage |
| **S60** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/author/windows-reservation02/stdout.json` | 1–713 | 1–713 | 713 | 0 | Full Rendered Coverage |
| **S61** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/author/windows-reservation02/exit.json` | 1–15 | 1–15 | 15 | 0 | Full Rendered Coverage |
| **S64** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/independent/windows-reservation02/stdout.json` | 1–713 | 1–713 | 713 | 0 | Full Rendered Coverage |
| **S65** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/independent/windows-reservation02/exit.json` | 1–15 | 1–15 | 15 | 0 | Full Rendered Coverage |
| **S68** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/actual/WINDOWS-RESERVATION02-AUTHOR-ACTUAL.json` | 1–7 | 1–7 | 7 | 0 | Full Rendered Coverage |
| **S69** | G2/3 | `docs/library/proof/windows-reservation02-2026-09-13/actual/WINDOWS-RESERVATION02-INDEPENDENT-ACTUAL.json` | 1–7 | 1–7 | 7 | 0 | Full Rendered Coverage |

**Coverage Totals**: 33 files, 6,422 required lines, 6,422 lines rendered and displayed with 0 unrendered lines or gaps.

*Cryptographic Verification Note*: SHA-256 digests in this review are cited directly from `CORRECTION-INPUTS.json`. Root owns canonical cryptographic byte verification.

---

## Discrepancy Disposition Matrix

| Original Claim / Location | Actual Source State | Audit Disposition | Corrective Action & Reference |
|---|---|---|---|
| 27–28: False test names for 17 cases | S17:5–21, S11:14–26, S14:13–20 contain exact identifiers. | **CORRECTED** | Replaced with exact identifiers from S17:5–21. |
| 29–36: Invented fixture code block at S13:135–144 | S13:134 constructs bootstrap; S13:135–144 yields fixture namespace; S14:38–62 performs `begin()` assertions. | **CORRECTED** | Removed invented block; cited actual fixture setup (S13) and `begin()` pre-execution checks (S14). |
| 38, 43, 46: Wrong injected faults and product ownership | S14:196 and S14:126 inject `KeyboardInterrupt`. S14:133 requires `b._factory._completed.vad is b._product`; S14:138 requires `b.registry._product is None`. | **CORRECTED** | Documented exact `KeyboardInterrupt` faults and distinguished retained bootstrap product from unpublished registry product. |
| G1-1, 63–65: Attributed `_factory_operation` to G1 S12 | `_factory_operation` belongs to G3 S42:270–304. G1 S12:301–317 uses `_owner_operation` delegating to S09:99–119. | **CORRECTED / WITHDRAWN** | Withdrew wrong protocol attribution. Retained limitation that nested re-entrancy does not measure cross-thread schedules. |
| 70–71: Cites nonexistent `run_all` and wrong receipt paths | S15 has no `run_all` (lines 116–136 capture, 158–168 membership, 182–191 execution). Exact receipts are S20 and S24. | **CORRECTED** | Corrected S15 structure and cited exact catalog paths ending in `runs/wbo01/stdout.json`. |
| 79: Names `FakeTorchModule` and forward passes | S07:83–135 builds `types.ModuleType('torch')`; S13:77–111 defines `FakePyanNet`. No `FakeTorchModule` or forward pass exists. | **CORRECTED** | Accurately described fake storage/tensor modules; removed forward-pass claims. |
| 87–97: Mislocated physical key, open, short write, and revision checks | Physical alias refusal is S35:337–343; exclusive open is S31:265–294 (share mode 0); short writes are S54:240–246 and S33:60–66; revision invalidation is S54:283–291. | **CORRECTED** | Anchored claims to correct source lines; separated resolver ancestor checks from journal ancestor guards. |
| 92–97: Invented `WindowsReservationStream`, `KernelUnconfirmed`, `write_record`, `truncate` | S31:103 defines `WindowsJournalStream`; S31:69–71 uses `PersistenceUnconfirmed('native_journal_poisoned')`; write revision is S31:175; confirmed head is S31:218–224. | **CORRECTED** | Replaced invented names with exact source classes, exceptions, and methods. |
| 99–103, G2-1: Claimed `_transition` is service method holding `self._lock` | `_transition` (S32:76–100) is a module-level replay validator. S46:39–41 states private-caller boundary. | **CORRECTED / WITHDRAWN** | Withdrew G2-1 as written; grounded private-caller concurrency boundary in S46:39–41 and S35:650–670. |
| 114–126, 146: False patch text and misrepresented assertions | S51:1–20 patches exception types for `adapter.ensure_assets` and `port.completion_evidence(None)` with regex. | **CORRECTED** | Replaced excerpt with exact 20-line diff from S51; preserved regex requirement. |
| 112, 180, 191–198: Misrepresented 6 native faults and failure history | S48:410–477 records 2 failed cases and 6 failed subtests. S54:468–495 tests 6 faults via `ensure_assets` with `KernelUnconfirmed`. | **CORRECTED** | Documented all 6 fault labels, exact mutations (`record.permit`, `record.owner`), and preserved 63/2 failed history. |
| 105–106, G3-1: Misanchored reconciliation and introduced generic deadlock finding | Reconciliation is S32:440–484; `finish_start` runs unlocked by design (S36:220–224); resume helper is S40:158. | **CORRECTED** | Corrected anchors; verified `_resume_after_future_admission` at S40:158; qualified deadlock finding as unmeasured concern. |

---

## Status of Original Council Findings

- **Finding G1-1**: **RESTATED**. The attribution to `_factory_operation` is withdrawn; G1 uses `_owner_operation` (S12:301–317) and `owner.operation` (S09:99–119). The finding that single-threaded nested re-entrancy lockout does not measure multi-threaded cross-thread schedules is **SURVIVING AS A SCOPE LIMITATION**.
- **Finding G1-2**: **SURVIVING**. 17 unique cases qualified across two redundant runs (S20 and S24).
- **Finding G1-3**: **SURVIVING**. Pure Python fake harness only; real PyTorch and inference remain unmeasured and unadmitted.
- **Finding G2-1**: **WITHDRAWN AS WRITTEN; RESTATED UNDER S46**. `_transition` is not a dispatch method holding `self._lock`. Concurrency exclusion for journal streams is enforced by architecture: streams are private to `ReservationService` (S46:39–41).
- **Finding G2-2**: **SURVIVING WITH ACCURATE CITATION**. The initial failure at commit `58335df` (63 passed, 2 failed) was corrected by the exact 20-line test exception patch in S51 without implementation changes.
- **Finding G3-1**: **QUALIFIED**. Unlocked execution of `finish_start` (S36:220–224) is by design. Potential callback re-entrancy is noted as an unmeasured design consideration, not an observed deadlock or product defect.
- **Finding G3-2**: **SURVIVING**. Native Whisper/CTranslate2 execution and live Windows process recovery remain unopened; `REAL_APPROVAL` remains `None` (S38:51).
