# Dormant Controller-to-Child Namespace Implementation Report

**Unit Scope:** Controller-to-child namespace connection and child-local lease issuance over verified model buffers.  
**Provenance / Base Commit:** `9c87ec216768fcd7b86cc97c9c8779f1fdafa49a` (Startup authority fake81 proof `docs/library/proof/startup-authority-fake81-2026-09-14`).  
**Addendum:** `docs/library/proof/real-child-namespace-plan-2026-09-14/plan/MEMBER-SCOPE-CORRECTION.md` superseding fixed-5 wording with 4- or 5-member scope per model spec.  
**Execution Admission:** False (Source preparation and proposed test suite only; no candidate Python execution).

---

## 1. Implemented Changes

1. **Change 1: Separate Post-Consumption Controller Validation (`asr_loading_adapter.py`)**
   - Preserved `_validate_controller_startup(startup, permit, session)` requiring `session._worker is None`, `token.worker is None`, and `record.phase is Phase.NATIVE_RESERVED`.
   - Added `_validate_controller_stage(token, startup, release, selection, profile)` and locked helper `_validate_controller_stage_locked` to validate durable bindings and publication advance after `_consume_controller_startup`.
   - Binds registered startup, immutable selection/manifest/profile values, admission, consumed session, permit, reservation, and retained worker.

2. **Change 2: Fixed Coordinator Module (`admitted_namespace_flow.py`)**
   - Implemented `AdmittedControllerPort` reusing `PrivatePipeController.attach_to_suspended_worker(pair, read_set, ...)`.
   - Consumes controller authority before process work; retains attempt, pair, worker, and channel custody across all calls and errors.
   - Supplies `ControllerHandshake(channel, session, permit.token, primitives, worker)` with token identity while controller retains permit wrapper.
   - Implemented `child_admitted_flow` for child-side pipe client adoption, private bootstrap decoding, process creation time verification, challenge/ready handshake, envelope verification, begin/cancel handling, materialization, and lease issuance.

3. **Change 3: Authenticated Admitted Envelope & Adoption (`inherited_readset.py`)**
   - Preserved generated route functions (`controller_manifest`, `validate_manifest`).
   - Added `controller_admitted_envelope` and `validate_admitted_envelope` using schema `"uoink.admitted-inherited-readset.v1"`.
   - Binds canonical envelope digest (distinct from manifest digest) to generation, child source sha256, and process creation time.
   - Refuses omissions, extra members, handle aliasing, and physical identity collisions before content reads.
   - Enforces 4-member scope for tiny/base/small/medium (with `vocabulary.txt`) and 5-member scope for large/large-v3-turbo (with `preprocessor_config.json` and `vocabulary.json`).
   - Added `AdmittedReadSetAdoption` with `adopt_admitted`, `materialize_admitted`, `release_unread`, and `release_after_reads`.

4. **Change 4: Child-Local Lease Issuance & Protocol (`owned_generation_protocol.py`)**
   - Preserved generated wire protocol and channel sequencing.
   - In `WorkerBootstrap`: added envelope binding to `accept_initial_control`; begin binds `envelope_sha256`; cancel releases unread handles and writes `closed` frame.
   - Added `AdmittedNamespaceLease` and `issue_admitted_namespace` executed under `self._owner_operation("issue_admitted_namespace")`.
   - Registered issued leases into `_ISSUED_ADMITTED_LEASES`; added `validate_admitted_lease` verifying issuance identity, non-revocation, bootstrap status, and completed buffers.
   - Preserved refusal for `activate_real_worker`.

5. **Change 5: Retained Materialization Custody (`pinned_buffer_namespace.py`)**
   - `PinnedBufferNamespace.materialize()` retains `self.materialization_attempt = _MaterializationAttempt(self, read_set, assets)` before buffer reads.
   - Tracks `partial_chunks` and `completed_buffers` across reading; retains them on failure.
   - Preserves original exception in `materialization_error` and does not discard custody on cleanup.

---

## 2. Proposed Test Suite & 17 Controls

Implemented in `admitted_namespace_fixture.py` and `test_admitted_child_namespace.py`:
1. `test_01_admitted_issued_success_five_member`: Pre/post-stage success for 5-member large model (`preprocessor_config.json` and `vocabulary.json`).
2. `test_02_foreign_or_copied_startup_session_permit_refusal`: Foreign or copied startup/session/permit refused.
3. `test_03_changed_release_or_profile_after_consumption_refusal`: Altered release authority or profile after consumption refused.
4. `test_04_substituted_worker_read_set_source_creation_time_refusal`: Substituted worker, read set, source sha256, or creation time refused.
5. `test_05_independent_channel_or_key_refusal`: Independently constructed channel or incorrect master key refused.
6. `test_06_changed_envelope_selection_or_profile_refusal`: Tampered envelope selection or profile refused.
7. `test_07_missing_or_extra_envelope_members_refusal`: Missing or extra envelope members refused.
8. `test_08_aliased_inherited_handles_refusal`: Aliased handles across envelope members refused.
9. `test_09_physical_identity_or_inheritance_mismatch_refusal`: Physical identity collision across members refused.
10. `test_10_materialization_before_begin_refusal`: Materialization attempted prior to begin refused.
11. `test_11_initial_cancel_without_buffers`: Initial cancel releases unread adoption; zero buffers materialized.
12. `test_12_begin_cancel_replay_refusal`: Begin/cancel replay or out-of-order execution refused.
13. `test_13_copied_lease_or_namespace_refusal`: Arbitrary or copied lease/namespace refused by validator.
14. `test_14_short_read_or_hash_failure_retains_partial_custody`: Short read or corrupted hash retains partial chunks and custody.
15. `test_15_revocation_before_publication_retains_returned_custody`: Revocation before publication retains custody and refuses publication.
16. `test_16_cleanup_failure_preserves_original_exception`: Cleanup failure preserves original failure exception.
17. `test_17_admitted_issued_success_four_member`: Positive 4-member model (tiny/base/small/medium with `vocabulary.txt`, no `preprocessor_config.json`).

All 17 control IDs are frozen in `EXPECTED-CASES.json`.

---

## 3. Verified Invariants & Closed Seams

- **Dormant Boundary:** Connection stops after issuing child-local lease over verified buffers.
- **Still-Closed Seams:**
  - `_fixed_real_worker_start` remains unavailable.
  - `activate_real_worker` remains unavailable and raises `ProtocolRefusal`.
  - `acquire_real_read_namespace` remains unavailable.
  - `activate_real_loader` remains unavailable.
  - Real authority globals (`RELEASE_AUTHORITY`, `RUNTIME_PROFILE`, `SNAPSHOT_LIFECYCLE`, `RUNTIME_FACTORY`, `ACQUISITION_SERVICE`, `REAL_APPROVAL`) remain absent (`None`).
  - No native DLL calls, live process execution, filesystem I/O, or port 5179.
  - Constructors, VAD options, PCM filters, inference, and diarization stay outside this unit.
- **Provenance & Integrity:**
  - Mechanical full unified diffs generated and verified with round-trip reconstruction for all four modified source files (`asr_loading_adapter.diff`, `pinned_buffer_namespace.diff`, `inherited_readset.diff`, `owned_generation_protocol.diff`).
  - Byte counts and SHA-256 hashes recorded in `SOURCE-INPUTS.json` and `HASHES.json`.
