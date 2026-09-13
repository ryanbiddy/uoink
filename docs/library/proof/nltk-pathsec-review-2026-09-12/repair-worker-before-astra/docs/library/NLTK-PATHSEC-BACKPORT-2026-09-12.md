# NLTK Pathsec Backport Review: GHSA-8mgp-746c-j5xp

**Date**: 2026-09-12  
**Worker**: gemini  
**Status**: Qualification Ready (Source patch, deterministic preparation utility, and regression suite complete)  
**Advisory**: GHSA-8mgp-746c-j5xp / CVE-2026-81726 / PYSEC-2026-3740  
**Target Component**: NLTK 3.10.3 (staged candidate)

---

## 1. Executive Summary

Advisory **GHSA-8mgp-746c-j5xp** identifies a sandbox bypass in NLTK `<= 3.10.3` where six public model-artifact persistence and loading routines bypass `nltk.pathsec` containment policy by using built-in `open()` or unvalidated filesystem APIs. Because no upstream 3.10.4 release exists, a reviewed source backport was prepared directly against the staged candidate tree.

The repair routes every affected model read, write, and directory creation through `nltk.pathsec` policy, enforces upfront containment validation, eliminates sandbox-broadening vectors, uses guarded directory creation helpers, and enforces path boundaries while strictly preserving authorized inside-root operations.

No model weights were loaded, no pickled checkpoints were deserialized, and no model inference was executed during qualification. All serialization and training boundaries were mocked upfront.

---

## 2. Deliverables Summary

| Deliverable | Path | Role / Description |
|---|---|---|
| **Patch Documentation** | `vendor/nltk-pathsec/README.md` | Vulnerability analysis, coverage matrix, and honest platform boundary distinctions. |
| **Exact Source Patch** | `vendor/nltk-pathsec/nltk-3.10.3-pathsec.patch` | Clean unified diff covering the 6 APIs across 3 files against NLTK 3.10.3. |
| **Preparation Utility** | `scripts/prepare_nltk_pathsec_backport.py` | Fail-closed utility that verifies original SHA-256 hashes before copying and directly applying the unified diff with exclusive receipt creation. |
| **Focused Test Suite** | `tests/test_nltk_pathsec_backport.py` | 28 test cases pairing outside-root refusals with inside controls in isolated child processes with mocked serialization boundaries. |

---

## 3. Covered APIs & Technical Implementation

The patch covers exactly the six APIs specified by GHSA-8mgp-746c-j5xp across three source files:

1. **`TransitionParser.train`** (`nltk/parse/transitionparser.py`):
   - Validates `modelfile` containment upfront with `pathsec.validate_path(modelfile, context="TransitionParser.train")` before scratch file allocation or training starts.
   - Replaces raw `open(modelfile, "wb")` with `pathsec.open(modelfile, "wb", context="TransitionParser.train")`.

2. **`TransitionParser.parse`** (`nltk/parse/transitionparser.py`):
   - Replaces raw `open(modelFile, "rb")` with `pathsec.open(modelFile, "rb", context="TransitionParser.parse")`.
   - Preserves downstream `allowlisted_pickle_load` verification.

3. **`AveragedPerceptron.save`** (`nltk/tag/perceptron.py`):
   - Adds upfront `pathsec.validate_path(path, context="AveragedPerceptron.save")`.
   - Replaces built-in `open(path, "w")` with `pathsec.open(path, "w", context="AveragedPerceptron.save")`.

4. **`AveragedPerceptron.load`** (`nltk/tag/perceptron.py`):
   - Adds upfront `pathsec.validate_path(path, context="AveragedPerceptron.load")`.
   - Replaces built-in `open(path)` with `pathsec.open(path, "r", context="AveragedPerceptron.load")`.

5. **`PerceptronTagger.save_to_json`** (`nltk/tag/perceptron.py`):
   - Validates `lang` and filename parameters against path traversal via `_validate_name_component`.
   - Validates constructor language code upfront via `_validate_name_component(self.lang, "language code")`.
   - Validates `loc` directory upfront with `pathsec.validate_path(loc, context="PerceptronTagger.save_to_json")`.
   - Eliminates sandbox widening: deprecated `_authorize_private_dir` is replaced with a no-op sentinel so caller-supplied directories are never appended to `nltk.data.path`.
   - Windows: creates directories via `os.makedirs(loc, exist_ok=True)`, re-validates landed path with `validate_path`, and writes files via `pathsec.open`.
   - POSIX: pins directory descriptor with `_open_private_model_dir`, re-validates landed path with `_fd_realpath(fd)`, and writes with `O_NOFOLLOW | 0o600`.

6. **`save_maxent_params`** (`nltk/classify/maxent.py`):
   - Adds upfront `pathsec.validate_path(tab_dir, context="save_maxent_params")`.
   - Uses existing guarded helpers:
     - On POSIX: calls `_open_private_model_dir` to enforce atomic `0o700` creation and `O_DIRECTORY | O_NOFOLLOW` descriptor pinning.
     - On Windows: creates directory with `os.makedirs(tab_dir, exist_ok=True)` and re-validates landed path via `validate_path(tab_dir, context="save_maxent_params")`.
   - Routes writes for `weights.txt`, `mapping.tab`, `labels.txt`, and `alwayson.tab` through `pathsec.open(..., "w", context="save_maxent_params", newline="")`.
   - Preserves original `None` return value (no unrelated return-value changes).

---

## 4. Verification Evidence & Focused Suite Results

### Preparation Utility Check
Executed deterministic preparation utility against staged NLTK 3.10.3:
```powershell
python scripts/prepare_nltk_pathsec_backport.py `
  --src E:/AI/projects/uoink/checkouts/Yoink-library/installer/staging/python/Lib/site-packages/nltk `
  --dst C:/Users/hello/AppData/Local/Temp/test_nltk_prep_run `
  --receipt C:/Users/hello/AppData/Local/Temp/test_nltk_prep_run/nltk-pathsec-receipt.json
```
- **Patch SHA-256**: `56d70eece6711a52d0082b066f79ff1388c1cbe6db19d3eb09bf98b5ae11f71b`
- **Original Source Hashes**:
  - `classify/maxent.py`: `11f704cf6cd2a43b51cb13634e9cdbc46b0e8394e1e291e9b66036d6a59c2583`
  - `parse/transitionparser.py`: `ed55985d08ed38333d007c5e5c19170a4dc19009e871ab616d198a3da92eea70`
  - `tag/perceptron.py`: `9d619a5ce7533c7eb388a70fedca8dcf0fb78279e1744e2abfdfcca9abd459ea`
- **Patched File Hashes**:
  - `classify/maxent.py`: `60645d1be785066c083f2458153f7e83931ebd8db20d976a8d34dea100f83f3c`
  - `parse/transitionparser.py`: `8dcc54a30557450084858b3ed7f559697f945593f50a2fdc9f4a08e3bbbbdd60`
  - `tag/perceptron.py`: `31d1577b9b04b22aace4fdead2b3f7bcb48864af45bfa5210f1e1d32a3cb81b9`

### Test Suite Execution
Executed focused backport qualification suite with bytecode generation disabled:
```powershell
python -B -m pytest tests/test_nltk_pathsec_backport.py -v --basetemp=_scratch/pytest-run-gemini-repair04
```

**Results**:
```text
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\ecbf6acd-847\gemini
plugins: anyio-4.12.1
collected 28 items

tests/test_nltk_pathsec_backport.py::test_prepare_refuses_preexisting_destination PASSED [  3%]
tests/test_nltk_pathsec_backport.py::test_prepare_refuses_path_traversal_in_destination PASSED [  7%]
tests/test_nltk_pathsec_backport.py::test_prepare_refuses_destination_inside_source PASSED [ 10%]
tests/test_nltk_pathsec_backport.py::test_prepare_refuses_source_inside_destination PASSED [ 14%]
tests/test_nltk_pathsec_backport.py::test_prepare_refuses_receipt_outside_destination PASSED [ 17%]
tests/test_nltk_pathsec_backport.py::test_prepare_refuses_tampered_patch PASSED [ 21%]
tests/test_nltk_pathsec_backport.py::test_prepare_verifies_clean_original_and_exclusive_receipt PASSED [ 25%]
tests/test_nltk_pathsec_backport.py::test_prepare_refuses_tampered_source PASSED [ 28%]
tests/test_nltk_pathsec_backport.py::test_prepare_refuses_wrong_version PASSED [ 32%]
tests/test_nltk_pathsec_backport.py::test_staging_source_original_bytes_unmodified PASSED [ 35%]
tests/test_nltk_pathsec_backport.py::test_scratch_archive_matches_staging PASSED [ 39%]
tests/test_nltk_pathsec_backport.py::test_transition_parser_train_outside_refusal PASSED [ 42%]
tests/test_nltk_pathsec_backport.py::test_transition_parser_train_inside_control PASSED [ 46%]
tests/test_nltk_pathsec_backport.py::test_transition_parser_parse_outside_refusal PASSED [ 50%]
tests/test_nltk_pathsec_backport.py::test_transition_parser_parse_inside_control PASSED [ 53%]
tests/test_nltk_pathsec_backport.py::test_averaged_perceptron_save_outside_refusal PASSED [ 57%]
tests/test_nltk_pathsec_backport.py::test_averaged_perceptron_save_inside_control PASSED [ 60%]
tests/test_nltk_pathsec_backport.py::test_averaged_perceptron_load_outside_refusal PASSED [ 64%]
tests/test_nltk_pathsec_backport.py::test_averaged_perceptron_load_inside_control_mocked_boundary PASSED [ 67%]
tests/test_nltk_pathsec_backport.py::test_perceptron_tagger_save_to_json_outside_refusal PASSED [ 71%]
tests/test_nltk_pathsec_backport.py::test_perceptron_tagger_save_to_json_inside_control PASSED [ 75%]
tests/test_nltk_pathsec_backport.py::test_perceptron_tagger_constructor_lang_traversal_refusal PASSED [ 78%]
tests/test_nltk_pathsec_backport.py::test_perceptron_tagger_save_lang_traversal_refusal PASSED [ 82%]
tests/test_nltk_pathsec_backport.py::test_save_maxent_params_outside_refusal PASSED [ 85%]
tests/test_nltk_pathsec_backport.py::test_save_maxent_params_inside_control_preserves_none_return PASSED [ 89%]
tests/test_nltk_pathsec_backport.py::test_nested_traversal_escape_refusal PASSED [ 92%]
tests/test_nltk_pathsec_backport.py::test_symlink_escape_refusal_or_unprivileged_boundary SKIPPED [ 96%]
tests/test_nltk_pathsec_backport.py::test_no_torch_or_inference_imported PASSED [100%]

================== 27 passed, 1 skipped in 105.16s (0:01:45) ==================
```

**Platform Boundary Assessment**:
- `test_symlink_escape_refusal_or_unprivileged_boundary` correctly skipped because Windows requires `SeCreateSymbolicLinkPrivilege` / Developer Mode (`[WinError 1314] A required privilege is not held by the client`). This is recorded honestly as a stated platform skip rather than counted as verified coverage.
- `test_no_torch_or_inference_imported` confirms zero imports of `torch`, `whisper`, `whisperx`, or `pyannote`.
- All child routing probes run with `-B` to prevent `.pyc` creation in staging or scratch trees.

---

## 5. Security & Advisory Scanner Integrity

- **Scanner Visibility**: As specified in the brief, the raw scanner entry for GHSA-8mgp-746c-j5xp remains visible. Preparing or qualifying this reviewed backport does not falsify OSV audit logs or claim upstream published 3.10.4.
- **Transcription Quality**: No transcription-quality credit is claimed or granted for path routing validation.
- **Separation of Concerns**: Staging tree `E:/AI/projects/uoink/checkouts/Yoink-library/installer/staging/python/Lib/site-packages/nltk` remains strictly unchanged and read-only.
- **No Release-Ready Claim**: This repair delivers a verified source patch and deterministic preparation utility, not an authorized release build.

---

## 6. Exact Remaining Packaging Steps

Before this backport can be incorporated into a production installer build or candidate release, Astra / downstream integration must execute the following bounded sequence:

1. **Explicitly Labelled Local Distribution**:
   - Build a local distribution wheel from the patched source tree with an explicit local version identifier compliant with PEP 440 (e.g. `nltk-3.10.3+uoink.pathsec1-py3-none-any.whl`).
   - Retain explicit local provenance to distinguish it from any official PyPI release.

2. **Lockfile & Wheel-Hash Provenance**:
   - Compute SHA-256 hash of the built local wheel.
   - Update installer wheel manifest / lockfile with the exact local wheel hash and provenance URI.
   - Update `THIRD-PARTY-NOTICES.md` with backport notice and patch reference.

3. **Installed Graph & Decoder Verification**:
   - Install the local wheel into a clean candidate staging environment alongside locked dependencies.
   - Run dependency closure and installed graph validation to ensure no conflicts with existing pins.
   - Execute synthetic decoder and audio import smoke checks without triggering live model downloads.

4. **Candidate Tree Staging**:
   - Stage the validated runtime into the new full candidate tree (`installer/staging`).
   - Run complete end-to-end integration and isolation test suite in the checkout.
