# Protected ASR Constructor Connection Report

This proposal delivers the namespace-to-constructor connection specified in `docs/library/PROTECTED-ASR-CONSTRUCTOR-BRIEF-2026-09-14.md` under `_scratch/protected-asr-constructor01`.

## Implemented Behavior

### 1. Native02 Namespace / Adoption Authority
- **Private record issuance**: `WorkerBootstrap.issue_admitted_namespace()` privately requests an `_AdmittedNamespace` token from `_WorkerRuntimeOwnerProposal` and returns an `AdmittedNamespaceRecord` containing the authenticated start identity, adopted `ReadSet`, manifest reference, generation token, and immutable `PinnedBufferNamespace`.
- **Identity enforcement**: `worker_runtime_owner.py` verifies record identity (`record._token is self._admitted_namespace`), generation matching (`record.generation is self._generation`), and readset/manifest alignment. Callers cannot fabricate authority by instantiating records, passing dictionary buffers, or modifying module variables.
- **Buffer preservation**: `PinnedBufferNamespace.fresh_files_map()` creates an independent shallow copy `dict(self._buffers)`. Downstream constructors popping keys (such as `tokenizer.json` or `preprocessor_config.json`) mutate only the transient dictionary, leaving the immutable `MappingProxyType` buffers intact.
- **ReadSet materialization**: `InheritedReadSet.materialize_admitted()` returns the immutable namespace and marks adoption receipts.

### 2. Owned ASR Engine & WhisperX Constructor Seam
- **Owned engine module**: Created `owned_asr_engine.py` defining `OwnedASREngine`, `EngineRefusal`, model family schemas (`FOUR`, `FIVE`), and `construct_owned_asr_engine()`.
- **Constructor invocation**: `whisperx/asr.py` exposes private `load_owned_model_from_namespace()` accepting the admitted namespace record, device (`cpu`), compute type (`int8`), and options. Public `load_model()` remains unconditionally refused.
- **Tokenizer requirement**: `load_owned_model_from_namespace()` verifies `tokenizer.json` exists in namespace buffers before touching any model constructor. Filesystem and Hugging Face Hub fallbacks are blocked.
- **VAD binding**: Connects the worker owner's verified VAD model (`silero_vad.onnx`) and factory port.
- **Companion delta isolation for 4-file models**:
  In B3 (`recipe/B2.py:741`), when `preprocessor_config.json` is missing, line 741 executes:
  ```python
  elif os.path.isfile(config_path):
  ```
  For memory models (`uoink-memory-*`), this probes the local filesystem. To avoid filesystem fallback without modifying accepted B3 code, captured feature extractor defaults (`FEATURE_EXTRACTOR_DEFAULTS`) are recorded in `owned_asr_engine.py`, and 4-file models (`tiny`, `base`, `small`, `medium`) raise `EngineRefusal` citing `COMPANION_DELTA_B3_NO_PATH`.
- **5-file models**: Models providing `preprocessor_config.json` (`large`, `large-v3-turbo`) bypass line 741 via `if preprocessor_bytes:` and forward clean buffer maps into the B3 constructor.

### 3. Worker Owner Connection & Lifecycle Safety
- **Early registration**: `connect_engine_before_construction()` registers engine ownership before constructor calls or allocations occur.
- **Post-construction verification**: `register_engine_product()` rechecks namespace authority, model identity, VAD identity, and operation identity prior to releasing the constructed engine.
- **Error preservation & uncertain ownership**: Construction failures preserve the initial exception. If cleanup raises a secondary error or if the generation was revoked during construction, the engine record is transitioned to quarantine (`quarantine_engine()`), preserving references for process retirement without leaking unowned handles.
- **Service boundary**: Existing generated services remain intact. Decoder, inference, and cursor routing are excluded from this deliverable.

### 4. Focused Inert Test Suite
`test_protected_asr_constructor.py` provides 13 unit tests exercising constructor inputs, identity checks, and ownership states using inert fake CT2/WhisperModel/VAD fixtures without executing production models or spawning processes.

## Identified B3 Companion Delta

- **Location**: `recipe/B2.py`, line 741 (and corresponding B3 wheel source)
- **Current code**:
  ```python
  preprocessor_bytes = files.pop("preprocessor_config.json", None)
  if preprocessor_bytes:
      ...
  elif os.path.isfile(config_path):
      ...
  ```
- **Required companion delta**:
  ```python
  elif not files and os.path.isfile(config_path):
  ```
  Combined with falling back to default feature extractor parameters (`feature_size=80`, `sampling_rate=16000`, `hop_length=160`, `chunk_length=30`, `n_fft=400`) when `files` is present but `preprocessor_config.json` is absent.
- **Status in this proposal**: Accepted B3 source is untouched. The 4-file path remains closed and raises `EngineRefusal` pointing to this delta until qualified.

## Qualification Suites & New Test IDs

### Unchanged Pre-existing Suites
- **fake33**: 33 test cases unchanged (`_scratch/runtime-owner-native-fake33-2026-09-13/author-preparation/EXPECTED-CASES.json`)
- **whisperx50**: 50 test cases unchanged (`_scratch/whisperx-owned-builder-proposal01/EXPECTED-CASES.json`)

### New Test Case IDs (13 cases)
1. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_01_five_file_forwarding_preserves_namespace_and_returns_engine_ownership`
2. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_02_four_file_model_policy_tiny_refuses_path_probe_and_identifies_companion_delta`
3. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_03_four_file_model_policy_base_refuses_path_probe_and_identifies_companion_delta`
4. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_04_four_file_model_policy_small_refuses_path_probe_and_identifies_companion_delta`
5. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_05_four_file_model_policy_medium_refuses_path_probe_and_identifies_companion_delta`
6. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_06_missing_tokenizer_refused_before_constructor_and_hub_fallback`
7. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_07_preprocessor_path_fallback_blocked_without_companion_delta`
8. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_08_forged_caller_created_namespace_refused_by_owner`
9. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_09_stale_and_revoked_namespace_refused_by_owner`
10. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_10_foreign_namespace_from_different_owner_refused`
11. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_11_cpu_and_options_mismatch_refused`
12. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_12_constructor_failure_preserves_first_error_and_retains_uncertain_owner`
13. `test_protected_asr_constructor.ProtectedASRConstructorCases.test_13_revocation_and_cleanup_failure_retains_process_retirement_path`

## Unresolved Source Issues

None. All four deliverables are complete and aligned with native02 and owner protocols. The B3 4-file constructor limitation is handled safely by closing the path with explicit refusal rather than allowing filesystem probes or altering B3 out-of-band.

## Unexecuted Checks

In accordance with strict assignment constraints:
- No Python execution occurred (no `python.exe`, no test runs, no syntax check processes, no imports).
- No model weights, checkpoints, audio samples, or external networks were accessed.
- All structural validation was performed via passive diff inspection, source mapping, and file hash generation.
