# Gemini Runtime Orchestration Council Review (2026-09-13)

- Date: 2026-09-13
- Reviewer: gemini (Local Multi-Model Control Room)
- Project: uoink-library
- Review Type: Independent text-only source review of three runtime orchestration proposals
- Operating System Context: Windows (with PowerShell native-exit capture and handle-quarantine requirements)
- Global Status: Uoink is not market-ready. Production remains commit `e8d058f`. Website and marketing remain paused.

---

## Executive Summary of Verdicts

1. **ASR Session Orchestration**: Accept for its narrow scope.
   - Reviewed Source: `docs/library/proof/asr-owned-adapter-2026-09-13/author-history209/asr-author03/adapter-preflight03/asr_loading_adapter.py`
   - Reviewed Source SHA-256: `03294344c0806b98b6d861c17371c1038c76dc0b874b9f756bf034187e849900`
   - Adjacent Contracts: `PORT-CONTRACTS.md`, `CALL-SITE-SPLICES.md`
   - Verdict Reference: `docs/library/ASTRA-ASR-ADAPTER-VERDICT-2026-09-13.md`
   - Decision: **Accept for its narrow scope**. The orchestration adheres strictly to its stated trusted-port contracts. Initial admission, explicit single-consent acquisition, fresh re-admission, constructor binding, lazy-use consumption inside session contexts, and lease quarantine on incomplete cleanup operate as specified. Real services and native exclusion interfaces remain absent.

2. **Plain-State Bridge**: Accept for its narrow scope.
   - Reviewed Source: `docs/library/proof/vad-native-state-bridge-2026-09-13/objects/b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2.txt`
   - Reviewed Source SHA-256: `b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2`
   - Port Contract: `docs/library/proof/vad-native-state-bridge-2026-09-13/objects/38a51bb9708302d2a29bc8d63bb6082934ee6b07abf720d0052b8cb897f82070.txt`
   - Verdict Reference: `docs/library/ASTRA-VAD-STATE-BRIDGE-VERDICT-2026-09-13.md`
   - Decision: **Accept for its narrow scope**. Input validation runs before any tensor allocation. Fixed 54-tensor schema and dense storage bounds are enforced. Pairwise address non-overlap and handle uniqueness are asserted before copy. Bounded 64 KiB chunk copying with immediate readback and full pre-factory state revalidation are verified. Temporary tensors are released in reverse order before product handoff, and failures dispose of partial products under cooperative deadlines. Real Torch ports and preemptive deadlines remain outside this synthetic boundary.

3. **Dormant Static Inspection Invocation**: Accept for its narrow scope.
   - Reviewed Sources:
     - Launcher: `docs/library/proof/vad-d1-wrapper-2026-09-13/preparation/before/launch_d1.py` (`bf865aff26515aa54e09ae046e53e6c9fb5efb688ccec676b170e8313af851e4`)
     - Child: `docs/library/proof/vad-d1-wrapper-2026-09-13/preparation/before/d1_child.py` (`577b1a22ebe5490ba28f5a56a46e5b3d3f5b85e077de3c1cafad6205aeb29a90`)
     - Repaired Wrapper: `docs/library/proof/vad-d1-wrapper-2026-09-13/preparation/run-root.repaired.ps1` (`11b56a5686d972c4ed212de21f2f2a23b0062da616a762701bda3434831cdb63`)
   - Verdict Reference: `docs/library/ASTRA-D1-INVOCATION-REVIEW-2026-09-13.md`
   - Decision: **Accept for its narrow scope**. Owner decision pins are dormant (`None`), refusing unconditionally before accessing filesystem paths or launching helpers. Exact nine-input root admission, isolated Python flags (`-I -S -B`), audit-hook restrictions (at most 1 artifact read, 1 exclusive output write, conversion trap), one-child lifetime, and 60-second execution bounds are verified. Repaired PowerShell wrapper disables native-error promotion and flushes raw exit bytes through a dedicated stream prior to log parsing. Pinned host paths (`PYTHON`, `CHECKOUT`, `FORBIDDEN`) remain configuration constraints for any future activation. Real checkpoint weights were not accessed.

---

## Group 1: ASR Session Orchestration

### Identification and Scope
- Source File: `docs/library/proof/asr-owned-adapter-2026-09-13/author-history209/asr-author03/adapter-preflight03/asr_loading_adapter.py`
- SHA-256: `03294344c0806b98b6d861c17371c1038c76dc0b874b9f756bf034187e849900`
- Adjacent Documents: `PORT-CONTRACTS.md`, `CALL-SITE-SPLICES.md`
- Test Verification Context: 58 cases passed independently twice (author run in 0.004348 s, Astra run in 0.004171 s; exit 0, empty stderr).

### Detailed Evaluation

1. **Bootstrap Authority and Global Boundary (`lines 26–65, 72–85`)**:
   - Module-level authorities (`RELEASE_AUTHORITY`, `RUNTIME_PROFILE`, `SNAPSHOT_LIFECYCLE`, `RUNTIME_FACTORY`, `ACQUISITION_SERVICE`) default to `None`.
   - `policy_status()` returns read-only configuration status without reading disk caches or importing model libraries.
   - `_release` (`lines 87–112`) validates that `choice` belongs to `SUPPORTED_CHOICES` and that `RELEASE_AUTHORITY` is an instance of `ReleaseAuthority`.
   - Manifest approval requires `resolver.REAL_APPROVAL is not None` and identity check `authority.manifest_approval is resolver.REAL_APPROVAL` with `purpose == "real"`.
   - Canonical local Windows root is verified: absolute path, no `..` segments, single-letter drive followed by `:`, matching `str(bound_root) == authority.data_root`.
   - Caller root must match bound root directly for transcription, or `bound_root / "models" / "whisper"` for reliability (`root_kind == "reliability"`).

2. **Initial Admission, Explicit Acquisition, and Fresh Re-Admission (`_leased_admission`, lines 122–150)**:
   - Requires explicit boolean `consent_given`.
   - Enters read lease via `lifecycle.read_lease(str(store), choice, selected.revision)` managed by an `ExitStack`.
   - Calls `resolver.admit_snapshot(trusted, choice, store, snapshot)`.
   - If initial admission raises `resolver.AdmissionRefusal`:
     - Closes the existing read lease (`stack.close()`).
     - If `consent_given` is `False`, immediately raises `AssetConsentRequired` chained from the refusal (`lines 137–138`).
     - If `consent_given` is `True`, requires `ACQUISITION_SERVICE is not None` and calls `service.acquire_and_publish(_plan(authority, selected, snapshot), consent_given=True)`.
     - Deliberately ignores the return value or path from `acquire_and_publish`.
     - Requests a fresh read lease on the stack and runs fresh `resolver.admit_snapshot`. If second admission fails, the error propagates out; acquisition is never retried.
   - Any constructor, iteration, or inference failure occurring downstream in `_model_session` bypasses this block entirely and cannot trigger acquisition.

3. **Constructor Binding and Session Lifecycle (`_model_session`, lines 182–212)**:
   - Validates `_runtime_profile` (`lines 163–180`), asserting matching `profile_id`, `device == "cpu"`, `compute_type in ("int8", "float32")`, and valid token-formatted VAD contracts (`whisperx_fixed_vad_contract` or `capture_vad_contract`).
   - Signals native session entry via `lease.begin_native_session()` (`line 188`) before opening the runtime.
   - Opens owned session via `RUNTIME_FACTORY.open_owned_session(profile)`.
   - Binds snapshot via `resolver.bind_for_constructor(admission)`.
   - For WhisperX: creates fixed VAD via `runtime.make_fixed_vad(profile.whisperx_fixed_vad_contract)` and loads model via `runtime.whisperx_load_model` with `vad_model=vad` and `local_files_only=True`.
   - For reliability fallback: calls `runtime.verify_capture_vad_contract` (when applicable) and loads model via `runtime.faster_whisper_model` with `local_files_only=True`.
   - Asserts non-None model reference and yields model within the context.

4. **Quarantine After Incomplete Cleanup (`lines 208–212`)**:
   - `finally` block verifies `runtime is not None and runtime.close_and_join() is True`.
   - If `runtime` failed to open, threw an unhandled exception, or `close_and_join()` returned `False` or raised:
     - Raises `NativeCleanupUnconfirmed("Native cleanup unconfirmed; snapshot lease must remain quarantined")`.
     - Skips `lease.confirm_native_closed()`.
     - The outer `ExitStack.close()` in `_leased_admission` terminates the lease while in the unconfirmed state, retaining quarantine in the lifecycle manager per `PORT-CONTRACTS.md`.

5. **Call-Site Splices and Lazy Consumption (`CALL-SITE-SPLICES.md`)**:
   - Splices in `whisper_runner.py` and `uoink_reliability.py` wrap model use within `with` contexts.
   - `whisper_runner.py` consumes generator segments immediately: `segments = list(result.get("segments") or [])` (`line 15`).
   - `uoink_reliability.py` consumes generator segments within the context: `return _transcript_entries_from_segments(segments)` in `transcribe_media` and `word_rows = _words_from_segments(segments)` in `detect_unreliable_spans`. Both helper functions iterate the generator completely inside the `with` block before returning or clustering.
   - Waveform decoding contract remains an explicit unmet precondition: input waveform must originate from an owned validated decoder, not an unverified file path.

6. **Historical Instrument Defect and Native-Exit Verification**:
   - In earlier test preflights, a local `$LASTEXITCODE` assignment shadowed PowerShell global process state, recording `native_exit=null`.
   - Per brief instructions, this historical failed receipt remains recorded and intact.
   - `run_preflight03.ps1` explicitly repaired this by setting `$PSNativeCommandUseErrorActionPreference=$false`, resetting `$global:LASTEXITCODE=$null`, executing python via `-I -S -B`, capturing `$global:LASTEXITCODE`, and immediately writing `native-exit.json` through a dedicated `IO.FileStream` with `Flush($true)` before postchecks.
   - This qualifies the repaired test instrument; the passing 58 cases in `adapter-preflight03` confirm the orchestration logic under simulated services.

### Scope and Limitations
- Orchestration only; real implementation of `SNAPSHOT_LIFECYCLE`, `ACQUISITION_SERVICE`, and `RUNTIME_FACTORY` remains absent.
- The twenty missing production model file hashes remain unpopulated.
- Python lease tracking does not provide an OS-level file lock against external processes. Windows filesystem exclusion and separate process containment remain necessary before native integration.

### Group 1 Verdict
**Accept for its narrow scope**. No findings within the tested orchestration boundary.

---

## Group 2: Plain-State Bridge

### Identification and Scope
- Source File: `docs/library/proof/vad-native-state-bridge-2026-09-13/objects/b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2.txt`
- SHA-256: `b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2`
- Port Contract: `docs/library/proof/vad-native-state-bridge-2026-09-13/objects/38a51bb9708302d2a29bc8d63bb6082934ee6b07abf720d0052b8cb897f82070.txt`
- Test Verification Context: 61 cases passed independently twice (author run in 3.8746 s, Astra run in 3.9587 s; exit 0, empty stderr, empty audit denials).

### Detailed Evaluation

1. **Pre-Allocation Verification (`lines 184–189, 110–136`)**:
   - `exercise_synthetic_bridge` initializes `_Budget(deadline_seconds)` (`MAX_SECONDS = 30.0`).
   - Invokes `reader.verify_bytes(snapshot, approval, deadline_seconds=budget.remaining())` before any tensor port method is called.
   - `_validate_verified` checks that `verified.snapshot is snapshot`, `verified.sha256 == profile.output_sha256`, `verified.profile_id == profile.profile_id`, and verifies exact schema: 54 tensors matching `FIXED_SHAPES`, starting at byte offset > 8, total data bytes equal to 5,891,996, and total elements equal to 1,472,999.

2. **Shape and Storage Facts Verification (`_facts`, lines 138–154)**:
   - For every allocation, calls `tensor_port.inspect_owned(handle)`.
   - Validates `TensorFacts`: `ordinary_tensor is True`, `contiguous is True`, `requires_grad is False`, `owned is True`, `no_external_aliases is True`.
   - Enforces `dtype == "F32"`, `device == "cpu"`, `layout == "strided"`.
   - Storage offset must be 0; storage start must be 4-byte aligned within 64-bit integer range; storage size must equal `prod(shape) * 4`.

3. **Aliasing and Range Checks (`lines 193–204`)**:
   - Requires `handle is not None` and confirms `handle` is not already present in `allocations`.
   - Places `(handle, descriptor, None)` into `allocations` immediately upon return, ensuring ownership tracking precedes any fallible inspection or copy.
   - Enforces pairwise address non-overlap against all preceding allocations:
     `facts.storage_start + facts.storage_bytes <= prior.storage_start or prior.storage_start + prior.storage_bytes <= facts.storage_start`.

4. **Bounded Copying and Bitwise Readback (`lines 205–215`)**:
   - Copies data in bounded chunks of `CHUNK_BYTES = 65_536` (`lines 206–214`).
   - Passes immutable bytes snapshot slice: `memoryview(snapshot)[begin:end].tobytes()`. Never passes writable buffers.
   - Calls `tensor_port.copy_owned_f32le(handle, offset, chunk)`.
   - Immediately checks readback via `_check_readback`: asserts returned bytes match the written chunk exactly in length and byte content.
   - Verifies tensor facts did not mutate during copy (`line 215`).

5. **Final Revalidation and Product Transfer (`lines 219–238`)**:
   - `phase = 'final_state_validation'`: verifies dictionary structure matches all 54 fixed keys.
   - Loops through all 54 allocated tensors: re-verifies `_facts` against cached baseline, and re-reads every 64 KiB chunk against original snapshot bytes.
   - Passes dictionary copy to `factory_port.build_strict_owned(dict(state))`.
   - Requires non-None product, wrapping it in `SyntheticResult`.

6. **Cleanup and Failure Disposal Paths (`lines 242–267`)**:
   - Clears `state` dictionary.
   - Iterates `reversed(allocations)`, invoking `tensor_port.release_owned(handle)`. Catches all `BaseException` errors and appends to `cleanup_errors`.
   - Re-checks deadline after tensor cleanup.
   - If any primary exception occurred, or if any cleanup error was recorded, or if deadline expired:
     - Disposes of completed product (if returned) via `factory_port.release_product(product)`.
     - Raises `BridgeRefusal(failure_phase, len(cleanup_errors))` chained from the primary cause.
   - Product is transferred to caller only when all 54 tensor releases succeed and deadline check passes.
   - Unconditional entry refusal: `build_real_vad(*args, **kwargs)` raises `BridgeRefusal('real_authority_absent')` at line 165.

### Scope and Limitations
- Fake port testing: all 61 cases exercise synthetic bytearray-backed memory buffers.
- Real Torch allocation, native readback via C++ pointers, and PyTorch model assembly are not implemented.
- The cooperative deadline check cannot preempt an uncooperative or blocked native call.
- Memory non-overlap checks use synthetic integer arithmetic; they do not observe virtual memory layout under Windows memory management.

### Group 2 Verdict
**Accept for its narrow scope**. No findings within the tested synthetic bridge boundary.

---

## Group 3: Dormant Static Inspection Invocation

### Identification and Scope
- Launcher File: `docs/library/proof/vad-d1-wrapper-2026-09-13/preparation/before/launch_d1.py` (`bf865aff26515aa54e09ae046e53e6c9fb5efb688ccec676b170e8313af851e4`)
- Child File: `docs/library/proof/vad-d1-wrapper-2026-09-13/preparation/before/d1_child.py` (`577b1a22ebe5490ba28f5a56a46e5b3d3f5b85e077de3c1cafad6205aeb29a90`)
- Repaired Wrapper: `docs/library/proof/vad-d1-wrapper-2026-09-13/preparation/run-root.repaired.ps1` (`11b56a5686d972c4ed212de21f2f2a23b0062da616a762701bda3434831cdb63`)
- Verdict Reference: `docs/library/ASTRA-D1-INVOCATION-REVIEW-2026-09-13.md`
- Test Verification Context: 12 cases in each root passed without failures (5.7517 s and 5.6574 s; exit 0, empty stderr, 13 inputs unchanged); 4 separate controls matched.
- Restriction Note: The actual artifact (`pytorch_model.bin`) was not opened or accessed during this review.

### Detailed Evaluation

1. **Closed Decision Pins and Dormant Refusal**:
   - `launch_d1.py` sets `OWNER_DECISION_SHA256 = None` (`line 12`). When `None`, lines 66–69 print `status: dormant_owner_approval_absent` and exit 3 without launching a child process or touching artifact paths.
   - `d1_child.py` sets `OWNER_DECISION_SHA256 = None` (`line 23`). When `None`, lines 81–84 print `status: dormant_owner_approval_absent` and exit 3 without artifact access or helper execution.
   - Both entry points refuse unconditionally in their dormant state.

2. **Root Admission and Exact Source Bounds**:
   - Both parent and child require isolated interpreter execution: `sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode` (`-I -S -B`).
   - Requires environment binding `IG_FORBIDDEN_LIVE == r'C:\Users\hello\AppData\Local\Uoink\index.db'`.
   - `no_links()` verifies all path ancestors: rejects symlinks (`stat.S_ISLNK`) and NTFS reparse points (`st_file_attributes & 0x400`).
   - Validates exact SHA-256 hashes for nine root files against `ROOT-ADMISSION.json` and five pinned helper hashes (`inspect_adapter.py`, `fixed_converter.py`, `zip_bounds.py`, `buffer_basis.py`, `known-inventory.json`).

3. **Child Execution Boundary and Audit Hooks (`d1_child.py`, lines 107–159)**:
   - Scrubbed process environment: retains only `SYSTEMROOT`/`WINDIR`; sets offline flags (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, etc.); redirects all user directories (`TEMP`, `TMP`, `HOME`, `USERPROFILE`, `APPDATA`) to the isolated run directory.
   - `sys.addaudithook` enforces strict event restrictions:
     - `open`: Permits non-writing opens only for known inputs. Permits reading `ARTIFACT` at most once (`access['artifact_opens'] == 0`), only while `access['active']` is true. Permits writing `OUTPUT` at most once with `O_EXCL | O_CREAT | O_WRONLY`, only while `access['active']` is true. All other file opens are denied.
     - `import`: Denies any import outside `sys.modules` and the four reviewed modules (`zip_bounds`, `fixed_converter`, `buffer_basis`, `inspect_adapter`). Heavy libraries (`torch`, `transformers`, `pickle`, etc.) trigger immediate refusal.
     - Denies `socket.*`, `subprocess.*`, `ctypes.*`, `winreg.*`, and all filesystem mutation APIs (`os.mkdir`, `os.remove`, etc.).
   - Path metadata wrappers (`stat`, `lstat`, `readlink`, `os.path.realpath`) deny live index metadata and restrict paths to known inputs and active real metadata.
   - Conversion trap (`lines 196–200`): Overwrites converter methods (`convert_bytes`, `convert_reviewed_real_file`, `load_fixed_plan`, `reject_nonfinite`, `encode_safetensors`) with `no_conversion` raising `RuntimeError('D1 conversion trap')`.

4. **One-Child Lifetime and Timeout Enforcements**:
   - Parent creates execution directory `execution-d1-real-01` with `exist_ok=False`, establishing a persistent one-shot claim.
   - Launches exactly one child via `subprocess.run(command, timeout=60, close_fds=True)`.
   - Catches `TimeoutExpired` and logs failure with `timed_out: True`.
   - Child resets `adapter.D1_OWNER_APPROVAL = None` and `access['active'] = False` in `finally` block (`lines 212–215`).

5. **Durable Exit Ordering in Repaired PowerShell Wrapper (`run-root.repaired.ps1`)**:
   - Sets `$PSNativeCommandUseErrorActionPreference = $false` (`line 2`), preventing PowerShell 7.6.5 from throwing terminating script exceptions on non-zero child return codes.
   - Runs child process with stdout/stderr redirection.
   - Captures `$LASTEXITCODE` into `$rawExit` (`line 17`).
   - Immediately persists `$rawExit` to `raw-exit.txt` using a dedicated .NET `FileStream` configured with `FileMode::CreateNew`, `FileShare::Read`, and `FileOptions::WriteThrough`, followed by `Flush($true)` (`lines 19–29`).
   - Records `actual-exit.json` before reading or echoing log contents.
   - Exits with `$rawExit`.
   - Verified across 12 cases and 4 original controls: native exit codes (including non-zero error exits) survive subsequent postcheck steps without truncation.

6. **Configuration Limits (Host Pinned Paths)**:
   - `PYTHON = r'C:\Python314\python.exe'` and `CHECKOUT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')` are hardcoded in `launch_d1.py` and `d1_child.py`.
   - These paths represent fixed host execution constraints; running on alternative environments or directory structures will require a reviewed configuration patch when activation is contemplated.
   - Because `OWNER_DECISION_SHA256` remains `None`, this constraint is dormant and does not invalidate the review.

### Group 3 Verdict
**Accept for its narrow scope**. No defects within the dormant static inspection boundary.

---

## Comprehensive Review Matrix

| Component Group | Primary Source Reviewed | Source SHA-256 | Test Coverage Evidence | Council Decision |
| :--- | :--- | :--- | :--- | :--- |
| **1. ASR Session Orchestration** | `asr_loading_adapter.py` | `03294344c0806b98b6d861c17371c1038c76dc0b874b9f756bf034187e849900` | 58 cases passed (author & Astra independent runs) | **Accept for its narrow scope** |
| **2. Plain-State Bridge** | `b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2.txt` | `b3ff126f29942e7daaf51e463ca9f35c4c423b6c638dbc38e5246946a8b7a6b2` | 61 cases passed (author & Astra independent runs) | **Accept for its narrow scope** |
| **3. Dormant D1 Invocation** | `launch_d1.py` / `d1_child.py` / `run-root.repaired.ps1` | `bf865aff...` / `577b1a22...` / `11b56a56...` | 12 cases passed (repaired wrapper) + 4 controls | **Accept for its narrow scope** |

---

## Remaining Native, Package, and Installed Limits

1. **Market and Production Boundary**:
   - The product is not market-ready.
   - Production remains pinned at commit `e8d058f`.
   - Public marketing, website updates, and client releases remain strictly paused.

2. **Real Port and Runtime Absences**:
   - In ASR adapter: `RELEASE_AUTHORITY`, `RUNTIME_PROFILE`, `SNAPSHOT_LIFECYCLE`, `RUNTIME_FACTORY`, and `ACQUISITION_SERVICE` remain unconfigured (`None`). The 20 production asset digests, approved VAD model artifact, and capture VAD contract remain unresolved.
   - In Plain-State bridge: Real PyTorch tensor allocations, C-pointer memory verification, model assembly via `build_strict_owned`, and native unpickling remain absent. Passing tests exercise synthetic bytearray allocations only.
   - In D1 static inspection: Owner approval pin (`OWNER_DECISION_SHA256`) remains `None`. No artifact weights were inspected, converted, or admitted.

3. **Operating System and Concurrency Boundaries**:
   - Python-level lease management and audit hooks do not constitute an OS-level sandbox.
   - Windows directory locking against concurrent unprivileged or privileged writers across native path reopening (TOCTOU) remains an open requirement for future runtime worker architecture.
   - Cooperative deadline checking cannot interrupt blocked native C/C++ execution. Preemptive process-level isolation is required for production integration.
   - Historical test instrument failures (e.g. ASR null native exit) remain documented in the record; new valid runs qualify the repaired harness, not the historical failure.
