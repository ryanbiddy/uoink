# Real Engine Connection 01: Implementation Report

## 1. Executive Summary & Delivery Scope
- **Directory**: `_scratch/real-engine-connection01`
- **Plan Reference**: `E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/real-engine-connection-next01/BRIEF.md` (SHA256: `140c4db6c85f7f606533324fa1f3b7d4f8e9922ba6b2c8189c380cd8e8086558`)
- **Source Map**: `SOURCE-INPUTS.json` (SHA256: `89caa88f3e88e08f0051326321fea9610192df2acf9ff1d8a4c8ea742a233d97`)
- **Repaired Base**: `core9e3a77d` (`_scratch/protected-engine-ownership-repair02/`) and `windows-interrupted-owner-native-proposal02`. The rejected `constructor01` implementation was not used.
- **Strict Compliance**: Source authoring only. No Python interpreter invocation, imports, compilation, unit test execution, subprocess launch, native stack access, checkpoint/model loading, or network calls.

---

## 2. Implemented Groups & Mechanical Deliverables

### Group 1: Authenticated Selection, ReadSet Adoption, and Namespace Lease
1. `pinned_buffer_namespace.py` / `pinned_buffer_namespace.diff`:
   - Added `AdmittedNamespaceRecord` dataclass bound to authenticated start, adopted ReadSet, manifest, and generation.
   - Added `buffers` property and `fresh_files_map()` on `PinnedBufferNamespace` to yield fresh shallow dictionary copies, ensuring B3 dictionary pops do not alter the retained immutable namespace.
2. `inherited_readset.py` / `inherited_readset.diff`:
   - Added `ADMITTED_FORMAT = "uoink.admitted-inherited-readset.v1"`.
   - Added `validate_admitted_manifest(...)` verifying choice, exact manifest SHA-256, member count (4 or 5), member names, unique inherited file handles, complete physical file identities, and namespace digest against the selected `Model` prior to handle operations.
   - Added `adopt_admitted(...)` on `InheritedReadSetAdoption` validating inherited flags via Win32 primitives, clearing inheritance, and confirming live status. Existing generated adoption route is preserved intact.

### Group 2: Owner Namespace Lease & Fixed Factory Registration
1. `worker_runtime_owner.py` / `worker_runtime_owner.diff`:
   - Added `_AdmittedNamespaceLease` dataclass tracking owner, generation, read set, pinned namespace, immutable buffers, model, profile, manifest SHA-256, and label.
   - Added `issue_admitted_namespace_lease(...)` and `assert_admitted_namespace_binding(...)` to `_WorkerRuntimeOwnerProposal`.
   - Added step-by-step custody methods: `_begin_admitted_engine(...)`, `_retain_admitted_engine_model(...)`, `_check_admitted_engine_model_ready(...)`, `_retain_admitted_engine_tokenizer(...)`, `_retain_admitted_engine_pipeline(...)`, `_publish_admitted_engine(...)`, and `_fail_admitted_engine(...)`.
   - Enforced single serial owner operation (`engine` phase); step retentions occur without nested operations; verified pipeline links to model and actual `vad_model` attribute before publication.
   - Retained attempt, returned objects, and namespace lease across generation revocation; logical revocation does not clear native custody.
2. `owned_generation_protocol.py` / `owned_generation_protocol.diff`:
   - Preserved exact baseline byte framing and constants on `GenerationChannel` (`header + body + mac`, `envelope={"op": ..., "payload": ...}`, `MAX_BODY=262144`, `MAX_DEPTH=10`).
   - Extended `WorkerBootstrap` with `_selected_model`, `_runtime_profile`, `_namespace_lease`, and `_engine`.
   - Added `bind_admitted_selection(...)` and `issue_admitted_namespace_lease(...)`.
   - Added separate `build_admitted_factory_product(...)` requiring admitted namespace lease before factory activity, leaving historical `build_factory_product(...)` and generated checks completely intact.
   - Added `_build_admitted_engine(...)` entering the single `engine` phase operation and delegating to `owned_asr_engine.execute_admitted_construction(...)`.

### Group 3: Owned ASR Engine & Private WhisperX Constructor Entry
1. `owned_asr_engine.py`:
   - Defines `EngineRefusal` and `_EngineConstructionPolicy` (enforcing `device='cpu'`, `compute_type in ('int8', 'float32')`, `device_index=0`, positive threads/workers, and fixed `beam_size=1, best_of=1`).
   - Defines `OwnedASREngine` wrapping owner, pipeline, model, VAD, namespace lease, and generation.
   - Defines `execute_admitted_construction(...)` executing within the serial owner operation:
     - Validates attempt, owner, active namespace lease, and registered VAD.
     - Enforces 5-file buffer presence, refusing 4-file models, missing tokenizers, and missing or empty preprocessor bytes.
     - Forwards a fresh shallow dictionary copy into constructor.
     - Retains model immediately after constructor return and verifies readiness before constructing tokenizer.
     - Retains tokenizer immediately after return.
     - Constructs options and pipeline, retaining pipeline immediately.
     - Verifies immutable pinned namespace buffers survived dictionary mutation.
     - Publishes admitted engine and returns `OwnedASREngine`.
   - Defines `construct_owned_asr_engine(...)` entry point delegating to `WorkerBootstrap._build_admitted_engine(...)`.
2. `after/whisperx/asr.py` / `asr.diff`:
   - Preserves public `load_model(...)` and its strict refusals unchanged.
   - Adds private `_load_admitted_model_from_namespace(...)`:
     - Does not accept replacement runtime from caller; binds directly to `require_owned_runtime()`.
     - Validates `type(vad_model) is VoiceActivitySegmentation`.
     - Calls `require_owned_namespace(...)` to verify namespace lease and VAD bindings on `_RUNTIME`.
     - Refuses four-file models and empty preprocessor bytes before any path service.
     - Enforces fixed CPU policy and beam/best-of constraint of 1.
3. `after/whisperx/_uoink_owned.py` / `_uoink_owned.diff`:
   - Adds `require_owned_namespace(namespace_record, vad)` validating both namespace binding and VAD binding on active `_RUNTIME`.

---

## 3. Inert Test Controls: `test_real_engine_connection.py`
A comprehensive 15-case inert test suite covers all required positive and negative controls:
1. `test_01_authenticated_selection_and_member_mismatch_refused`: Manifest validation refuses choice, digest, count, or handle collisions.
2. `test_02_pre_begin_cancel_admits_no_buffers_or_factory`: Pre-begin cancel consumes control frame, resets ready, and admits no buffer or factory allocation.
3. `test_03_copied_or_forged_lease_refused`: Rejection of caller-constructed, forged, or foreign namespace leases.
4. `test_04_successful_admitted_engine_construction_positive`: End-to-end positive control verifying 5-file forwarding, object retention, buffer survival, and publication.
5. `test_05_four_file_model_refused_before_path_service`: Honest refusal of 4-file models lacking preprocessor config.
6. `test_06_empty_preprocessor_bytes_refused`: Refusal of empty preprocessor config bytes preventing B3 filesystem probing.
7. `test_07_missing_or_empty_tokenizer_bytes_refused`: Refusal of absent or empty tokenizer bytes preventing Hub fallback.
8. `test_08_buffer_mutation_immunity`: Proves pinned namespace buffers remain intact when constructor pops dictionary keys.
9. `test_09_cpu_and_options_policy_mismatch_refused`: Refuses non-CPU devices, unsupported compute types, non-zero device index, and beam_size/best_of != 1.
10. `test_10_revocation_during_construction_retains_returned_objects`: Revocation during construction retains returned objects on attempt and refuses publication.
11. `test_11_tokenizer_constructor_failure_retains_model`: Tokenizer constructor failure preserves previously returned model on attempt.
12. `test_12_pipeline_constructor_failure_retains_model_and_tokenizer`: Pipeline constructor failure preserves previously returned model and tokenizer on attempt.
13. `test_13_publication_refusal_after_revocation`: Explicit check that attempting publication on revoked attempt/owner fails.
14. `test_14_secondary_cleanup_failure_preserves_first_error`: Preserves original constructor error identity with PEP 678 note if cleanup raises.
15. `test_15_nested_or_overlapping_operation_refused`: Prevents reentrant or overlapping operations within an active engine phase.

All test fixtures use inert mocks with exact Win32 argument offsets and zero direct heavy imports.

---

## 4. Honest Status of Prerequisites & Closed Gates
1. **Prerequisites Absent**:
   - `REAL_APPROVAL`, `RELEASE_AUTHORITY`, and `RUNTIME_PROFILE` remain absent in accordance with project governance.
   - No real model authority is manufactured or claimed.
2. **Path Fallbacks Closed**:
   - Four-file model preprocessor filesystem fallback remains strictly closed.
   - Tokenizer Hugging Face Hub fallback remains strictly closed.
3. **Separate Downstream Gates**:
   - PCM decoding, audio filters, inference cursors, completion metadata, D3 acquisition, and D4 native stack admission remain separate subsequent gates.
