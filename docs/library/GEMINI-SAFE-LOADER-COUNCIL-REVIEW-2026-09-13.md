# Gemini Safe Loader Council Review (2026-09-13)

- Date: 2026-09-13
- Reviewer: gemini (Local Multi-Model Control Room)
- Project: uoink-library
- Review Type: Independent source review of three synthetic loader proposals
- Operating System Context: Windows (with cross-API stat considerations)
- Global Status: Uoink is not market-ready. Production remains commit `e8d058f`. Website and marketing remain paused.

---

## Executive Summary of Verdicts

1. **ASR Manifest Admission**: Accept for its narrow synthetic scope.
   - Reviewed Source: `docs/library/proof/asr-trusted-manifest-resolver-2026-09-13/proposal/trusted_asr_resolver.py`
   - Reviewed Source SHA-256: `16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833`
   - Verdict Reference: `docs/library/ASTRA-ASR-RESOLVER-VERDICT-2026-09-13.md`
   - Decision: Accept for its narrow synthetic scope. No new actionable source defects within the qualified synthetic boundary.

2. **VAD Plain-State Reader**: Accept for its narrow synthetic scope.
   - Reviewed Source: `docs/library/proof/vad-plain-state-reader-2026-09-13/preparation03/plain_state_reader.py`
   - Reviewed Source SHA-256: `3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c`
   - Verdict Reference: `docs/library/ASTRA-VAD-PLAIN-STATE-READER-VERDICT-2026-09-13.md`
   - Decision: Accept for its narrow synthetic scope. No new actionable source defects within the qualified synthetic boundary.

3. **VAD D1 Static Inspection Adapter**: Accept for its narrow synthetic scope.
   - Reviewed Source: `docs/library/proof/vad-d1-adapter-2026-09-13/proposal/inspect_adapter.py`
   - Reviewed Source SHA-256: `533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649`
   - Adjacent Sources: `buffer_basis.py`, `fixed_converter.py`, `zip_bounds.py`
   - Verdict Reference: `docs/library/ASTRA-VAD-D1-ADAPTER-VERDICT-2026-09-13.md`
   - Decision: Accept for its narrow synthetic scope. No new actionable source defects within the qualified synthetic boundary.

---

## Group 1: ASR Manifest Admission

- Source Path: `docs/library/proof/asr-trusted-manifest-resolver-2026-09-13/proposal/trusted_asr_resolver.py`
- Source SHA-256: `16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833`
- Historical Context: Qualified source16a5a124 passed 87 synthetic test cases in author and independent Astra runs with zero failures (exit 0). It resolved an earlier Windows cross-API `ctime` discrepancy where path observations reported birthtime while handle observations reported modification time.

### Source Evaluation

1. **Manifest Validation and Admission Boundary (`load_manifest`, lines 119–166)**:
   - Requires explicit `ManifestApproval` object (`line 121`).
   - Purpose check permits `"synthetic"` or `"real"` (`line 122`).
   - `REAL_APPROVAL` is initialized to `None` (`line 51`). Any attempt to load a real manifest fails immediately at `line 124` (`"Real manifest approval unavailable"`).
   - Enforces strict raw byte bound `<= MAX_MANIFEST` (64 KiB, `line 126`) and exact SHA-256 verification (`line 127`) before JSON parsing.
   - Uses `object_pairs_hook=pairs_unique` (`lines 107–112`) to forbid duplicate JSON keys, and rejects non-finite constants (`lines 129–130`).
   - Validates schema keys strictly: `schema == "uoink.asr-trusted-manifest.v1"` and `manifest_accepted is True` (`lines 135–137`).
   - Requires exactly 6 models matching the immutable specification table `MODEL_SPECS` (`lines 25–32`, `lines 138–144`).
   - Enforces exact asset membership for each model (tiny, base, small, medium, large, large-v3-turbo) matching expected names and counts (`lines 147–160`).
   - For synthetic mode, asserts `len(SYNTHETIC_PREFIX) <= size <= SYNTHETIC_MAX_FILE` (4,096 bytes) and valid 64-character lowercase hex digest (`lines 154–156`).
   - Enforces aggregate model and manifest byte limits: `MAX_MODEL` (4 GiB) and `MAX_ALL` (8 GiB) (`lines 160, 164`).

2. **Windows Path and Handle Identity Comparisons (`_cross_api_identity`, lines 178–186; `_identity`, lines 172–176)**:
   - On Windows (`os.name == "nt"`), `lstat()` reports birthtime in `st_ctime_ns`, whereas `fstat()` on an open handle reports file modification time.
   - `_cross_api_identity` handles this difference: it extracts `st_birthtime_ns`, requires that it is an integer (`line 183`), and compares `(st_dev, st_ino, st_mode, st_nlink, st_size, st_mtime_ns, birthtime)` across path and handle observations.
   - Full same-API observations compare all eight fields via `_identity` (`lines 172–176`), preserving strict checks across identical observation channels.
   - In `_hash_asset` (`lines 226–252`), `_cross_api_identity` is validated between initial path check and handle open (`line 232`), and again between handle open and post-read path check (`line 246`). `_identity` is validated between open handle and closed handle (`line 243`), and between before-path and after-path checks (`line 245`).
   - This identity verification sequence prevents file swapping before, during, or after streaming reads under the quiescent-directory assumption.

3. **Path Traversal and Link Defense (`_checked_chain`, lines 205–215; `_unlinked_stat`, lines 189–195)**:
   - `_checked_chain` checks every path segment from root anchor to target.
   - `_unlinked_stat` verifies `not stat.S_ISLNK(mode)` and checks that reparse point attribute `0x400` is not present (`line 191`), blocking symlinks and Windows NTFS junctions.
   - Regular files must have `st_nlink == 1` (`line 194`), rejecting hard links.
   - `path.resolve(strict=True) == str(path)` (`line 213`) rejects 8.3 short names and ancestor aliasing.

4. **Exact Directory Inventory (`_inventory`, lines 217–224)**:
   - Uses `os.scandir` to verify that the snapshot directory contains only the expected asset files.
   - Fails if extra entries exist or expected entries are missing.
   - `admit_snapshot` runs `_inventory` both before and after hashing all assets (`lines 273, 275`), detecting newly added or removed files.

5. **Constructor Rebind (`bind_for_constructor`, lines 285–293)**:
   - Calls `admit_snapshot` a second time and requires `current == admission` (`lines 288–289`).
   - Because `Admission` and `FileObservation` are frozen dataclasses containing file stat tuples and content digests, any change between initial admission and binding causes a refusal.
   - Returns a `LocalBinding` dataclass containing local snapshot paths and metadata.
   - Sets `constructor_called = False` and `real_runtime_approved = False`. It does not import faster-whisper, instantiate native objects, or perform network requests.

### Threat Assumptions and Scope Boundary

- **Within Stated Assumption (Private, Quiescent Directory)**:
  Under the assumption that the snapshot directory is private to the process and quiescent (no concurrent writers), the proposal contains no path to admit an unapproved asset or wrong-file path. Every file name, size, digest, and prefix must match the approved manifest.
- **Outside Stated Assumption (Risks and Lifecycle Limits)**:
  1. *TOCTOU Race on Downstream Native Reopen*: `bind_for_constructor` returns a filesystem path (`current.snapshot`) for downstream use. When an external native engine (such as CTranslate2) opens the directory, Python's handle-preserving stat checks are inactive. A concurrent writer in a non-quiescent environment could replace files between Python verification and native load.
  2. *Filesystem Permissions*: The proposal does not enforce or verify OS ACLs/DACLs on ancestor folders. A shared host or permissive ACL environment violates the private-directory precondition.
  3. *Real Model Trust Anchor Absence*: `REAL_APPROVAL` is `None`. Twenty public-plan file hashes remain absent. No real model assets can pass admission without code modification and documentary approval.
  4. *Native Loader Safety*: Admission does not evaluate whether downstream C++ parsers are safe against memory corruption when reading model binaries.

### Group 1 Conclusion
Accept for its narrow synthetic scope.

---

## Group 2: VAD Plain-State Reader

- Source Path: `docs/library/proof/vad-plain-state-reader-2026-09-13/preparation03/plain_state_reader.py`
- Source SHA-256: `3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c`
- Historical Context: Source3962d355 passed 82 synthetic test cases twice across author and Astra runs with zero failures (exit 0). It resolved an earlier failure (vpr02, 75/1) where deeply nested JSON bypassed syntax refusal and reached schema validation.

### Source Evaluation

1. **Whole-Input Identity Before Parse (`verify_bytes`, lines 220–232)**:
   - Verifies profile via `_approved_profile(profile)` (`line 221`).
   - Requires `type(snapshot) is bytes` and `8 < len(snapshot) <= MAX_OUTPUT` (6 MiB, `line 223`).
   - Confirms length matches `profile.output_size` (`line 224`).
   - Computes SHA-256 of the complete snapshot in 64 KiB chunks before reading header fields (`lines 226–230`).
   - Rejects snapshot if SHA-256 does not match `profile.output_sha256` (`line 232`). Parsing does not proceed on corrupted or mismatched input.

2. **Nesting Depth and String Parsing Boundary (`_check_json_depth`, lines 150–172; `_header_document`, lines 174–188)**:
   - Bounded scanner runs before JSON parsing: checks structural nesting depth `<= MAX_JSON_DEPTH` (3 levels, `line 167`).
   - Accounts for string quotes (`"`) and backslash escapes (`\`), ensuring braces inside strings do not alter structural depth counts (`lines 156–162`).
   - Checks cooperative deadline every 1,024 bytes during scan (`line 155`).
   - Uses `json.loads` with `object_pairs_hook=_strict_pairs` (`lines 132–137`) to forbid duplicate keys.
   - Uses `parse_int=_json_integer` (`lines 140–143`) to bound integer length to `<= 10` digits, preventing conversion denial-of-service.
   - Uses `parse_float=_reject_json_number` and `parse_constant=_reject_json_number` (`lines 146–147`), rejecting floats, NaN, and Infinity in the header.

3. **Canonical Header Encoding and Layout (`verify_bytes`, lines 234–246)**:
   - Unpacks 8-byte little-endian header length `header_size` (`line 234`).
   - Asserts `0 < header_size <= MAX_HEADER` (32 KiB) and 8-byte alignment `header_size % 8 == 0` (`line 235`).
   - Validates exact file coverage: `data_start + DATA_BYTES == len(snapshot)` (`line 237`), where `DATA_BYTES = 5,891,996`. Trailing bytes or truncation are refused.
   - Re-serializes the parsed header using `json.dumps(..., sort_keys=True, separators=(',', ':'))`, adds 8-byte space padding, and requires byte-level equality with input header bytes (`lines 242–246`). Rejects non-canonical JSON, non-ASCII characters, and non-space padding.

4. **Exact Canonical Schema and Dense Offsets (`_descriptors`, lines 190–216)**:
   - Schema mandates exactly 54 tensors matching `FIXED_SHAPES` (`lines 31–65, 191–192`).
   - Each tensor must declare `dtype == "F32"` (`line 199`).
   - Tensor shapes must match expected shapes exactly (`lines 201–203`).
   - Data offsets must be contiguous, dense, and non-overlapping: `offsets == [cursor, end]` (`line 211`), with `cursor` advancing by `count * 4` bytes.
   - Total element count must equal 1,472,999 and total data bytes must equal 5,891,996 (`line 215`).

5. **Finite F32 Binary Scan (`verify_bytes`, lines 248–252)**:
   - Reads every 4-byte slice in the 5.89 MB data payload via `struct.iter_unpack('<I', ...)`.
   - Rejects non-finite values using mask check: `bits & 0x7F800000 != 0x7F800000` (`line 251`).
   - Rejects IEEE 754 NaN and Infinity values across all 54 tensors.

6. **Immutable Slices and Deadlines (`VerifiedState`, lines 89–103; `_Budget`, lines 105–115)**:
   - `VerifiedState.tensor_bytes(key)` returns a `memoryview` slice of the immutable `snapshot` bytes (`lines 97–102`).
   - Cooperative deadline checking occurs across every processing loop.

### Authority Boundary and Practical Bypass Analysis

- **Authority Boundary**:
  - `_approved_profile` requires `profile.purpose == 'synthetic'` (`line 120`).
  - `REAL_PROFILE` is `None` (`line 18`). Real checkpoint approval is not reachable.
  - `profile.output_sha256 != ORIGINAL_SHA256` (`line 126`) ensures synthetic profiles cannot be used on the original checkpoint.
  - Caller-constructed `ApprovalProfile` or `VerifiedState` objects carry no external authority. The output description explicitly marks `native_or_model_qualified: False` and `release_approved: False` (`line 257`).
- **Practical Bypass Assessment**:
  - Within Python memory, an unconstrained caller could manually construct a `VerifiedState` object. The specification states that in-memory objects do not constitute an authority mechanism. Downstream components must rely on verified byte pipelines with explicit cryptographic anchors, not caller-passed dataclass objects.
  - `verify_bytes` does not construct PyTorch tensors or allocate native tensor memory; bridging to CPU tensors remains an open lifecycle task.

### Group 2 Conclusion
Accept for its narrow synthetic scope.

---

## Group 3: VAD D1 Static Inspection Adapter

- Source Path: `docs/library/proof/vad-d1-adapter-2026-09-13/proposal/inspect_adapter.py`
- Source SHA-256: `533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649`
- Adjacent Files:
  - `buffer_basis.py` (checked via proof suite)
  - `fixed_converter.py` (checked via proof suite)
  - `zip_bounds.py` (checked via proof suite)
- Historical Context: Source533c8abee passed 54 synthetic test cases twice in author and Astra runs with zero failures (exit 0).

### Source Evaluation

1. **Approval-Before-Path and Dormant Wrapper (`inspect_reviewed_real_file`, lines 155–187; `_profile`, lines 55–83)**:
   - `D1_OWNER_APPROVAL` is initialized to `None` (`line 29`).
   - `inspect_reviewed_real_file` enforces `type(D1_OWNER_APPROVAL) is InspectionApproval` (`line 157`) before any filesystem path resolution or access.
   - In `_profile`, `archive.REAL_PROFILE` must be `None` (`line 56`), preventing shared profile activation with the converter.
   - For synthetic mode, `profile.archive_sha256 != ORIGINAL_SHA256` (`line 74`).
   - For real mode, `profile.archive_sha256 == ORIGINAL_SHA256` (17,719,103 bytes) and the SHA-256 of JSON-serialized members must match `KNOWN_INVENTORY_SHA256` (`lines 80–82`).

2. **Fixed Identity and Inventory (`_profile`, lines 62–72; lines 24–25)**:
   - Requires exactly 131 archive members matching `EXPECTED_NAMES`: `"archive/data.pkl"`, `"archive/version"`, and `"archive/data/0"` through `"archive/data/128"` (`lines 24, 62`).
   - Total uncompressed size bounded by `MAX_INPUT` (32 MiB, `line 70`).
   - Members `archive/data/4`, `archive/data/5`, and `archive/version` must have lengths 500, 500, and 2 bytes (`lines 25, 72`).

3. **Stored ZIP Parsing and CRC Integrity (`_inspect`, lines 95–129; `fixed_converter.py`, lines 199–270)**:
   - Enforces stored ZIP only (`method == 0`, `fixed_converter.py line 210`).
   - Verifies CRC-32 for every member (`fixed_converter.py line 266`, `inspect_adapter.py lines 108–109`).
   - Rejects overlapping member extents, unreferenced prefixes, and unreferenced gaps (`fixed_converter.py lines 250–265`).

4. **Version and Selected Buffer Inspection (`_inspect`, lines 113–129)**:
   - Interprets only 1,002 bytes out of the 17.7 MB archive:
     - `archive/version`: 2 bytes (`EXPECTED_VERSION = b"3\n"`). Marked explicitly as a source prediction (`line 88`).
     - `archive/data/4`: 500 bytes (SincNet window buffer).
     - `archive/data/5`: 500 bytes (SincNet time vector buffer).
   - Reports `interpreted_payload_bytes: 1002` (`line 123`).

5. **Opaque Remaining Payloads (`_inspect`, lines 89–92)**:
   - `archive/data.pkl` is never unpickled or parsed.
   - The other 127 data storages are not interpreted or decoded.
   - The receipt explicitly reports `pickle_interpreted: False`, `other_storage_values_interpreted: False`, `conversion_performed: False`, and `conversion_profile_activated: False` (`lines 89–91`).

6. **Analytic Buffer Basis and Writer Authentication Distinction (`buffer_basis.py`, lines 46–72)**:
   - `compare_buffers` evaluates `archive/data/4` and `archive/data/5` against reference values:
     - `window[i] = 0.54 - 0.46 * cos(2 * pi * i / 250)` for `i in range(125)` (`line 19`).
     - `time_vector[k] = 2 * pi * k / 16000` for `k in range(-125, 0)` (`line 20`).
   - Validates that finite binary32 words match within `ULP_LIMIT = 8` (`line 5`).
   - Requires that exactly one endian orientation (little or big) matches both buffers (`exactly_one`, lines 24–29, 62).
   - Explicitly records `writer_authenticated: False` and `other_storages_validated: False` (`lines 69–71`).
   - The mathematical consistency of two selected buffers does not establish writer authentication or guarantee that the remaining 127 storages use the same endianness, layout, or valid numerical data.

7. **Refusal and Reporting (`inspect_snapshot`, lines 139–153)**:
   - Structured JSON receipts are bounded by `MAX_RECEIPT` (16 KiB, `line 134`).
   - Deterministic exit codes: 0 for clean inspection, 2 for refusal/deadline, 1 for unexpected exception (`lines 141–147`).
   - Has bounded fallback receipt if JSON serialization fails (`lines 150–152`).

### Group 3 Specific Observations and Limits

- *Finding 3-1: Hardcoded Host Path in Dormant Real Wrapper*:
  - **Location**: `docs/library/proof/vad-d1-adapter-2026-09-13/proposal/inspect_adapter.py#L26`
  - **Reviewed Source Hash**: `533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649`
  - **Severity**: Low / Configuration Limit (Non-defect in synthetic scope)
  - **Concrete Trigger**: Activating real owner approval on a machine where the repository is not located at `E:\AI\projects\uoink\checkouts\Yoink-library`.
  - **Consequence**: `contained_unlinked` will reject paths outside the hardcoded root, raising `Refusal("Path outside the fixed allowed root")`.
  - **Smallest Repair**: Parameterize `ROOT` or resolve it relative to repository root if real execution is authorized in a future lifecycle decision. Because the wrapper is dormant and guarded by `D1_OWNER_APPROVAL is None`, this does not affect synthetic qualification.

### Group 3 Conclusion
Accept for its narrow synthetic scope.

---

## Comprehensive Council Summary

| Loader Group | Reviewed Source File | Source SHA-256 | Synthetic Cases | Result |
| :--- | :--- | :--- | :--- | :--- |
| **ASR Manifest Admission** | `proof/asr-trusted-manifest-resolver-2026-09-13/proposal/trusted_asr_resolver.py` | `16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833` | 87 passed / 0 failed | **Accept for its narrow synthetic scope** |
| **VAD Plain-State Reader** | `proof/vad-plain-state-reader-2026-09-13/preparation03/plain_state_reader.py` | `3962d355cffe928f78b741d2d920cc9c727a9fbd10305e20462b60f4cef9990c` | 82 passed / 0 failed | **Accept for its narrow synthetic scope** |
| **VAD D1 Static Inspection** | `proof/vad-d1-adapter-2026-09-13/proposal/inspect_adapter.py` | `533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649` | 54 passed / 0 failed | **Accept for its narrow synthetic scope** |

---

## Unresolved Items and Future Qualification Boundaries

1. **Release and Market Readiness Status**:
   - Uoink is not market-ready.
   - Public website and marketing activities remain paused.
   - Production remains pinned at commit `e8d058f`.

2. **Gaps Not Closed by Inert Source Review**:
   - *Real Artifact and Model Weight Approval*: `REAL_APPROVAL` in ASR, `REAL_PROFILE` in VAD reader/converter, and `D1_OWNER_APPROVAL` in D1 adapter remain `None`.
   - *Native Runtime Reopen and TOCTOU*: Native loaders (CTranslate2, ONNX Runtime, PyTorch C++ bindings) operate outside Python handle validation. Safe native loading requires either an OS-level sandbox or open file handle handoff.
   - *Historical Tree Gap (AT6)*: The full tree failure at commit `56d9d4c` (2,796 passed, 1 failed, 3 skipped) remains open and is not addressed by synthetic proof packages.
   - *Downstream Tensor Instantiation*: Neither VAD reader nor D1 adapter creates executable tensors or calls model inference engines.
   - *Package Signing and Client Distribution*: Installer packages, wheel signatures, and distribution infrastructure are not verified or approved by this review.
