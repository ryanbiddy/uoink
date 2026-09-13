> Retained worker report. Read [Astra's verdict](ASTRA-NLTK-PATHSEC-VERDICT-2026-09-12.md) first; its boundary and test corrections supersede the claims below. Original worker bytes are preserved in the proof archive.

# NLTK Pathsec Preparation Repair Review

**Date**: 2026-09-12
**Worker**: gemini
**Status**: Bounded Repair Complete (Ready for Astra Three-Way Integration & Qualification)
**Advisory**: GHSA-8mgp-746c-j5xp / CVE-2026-81726 / PYSEC-2026-3740
**Target Release**: NLTK 3.10.3 (installed staging candidate)
**Initial Worktree**: `4a939c69-786/gemini` | **Repair Worktree**: `ecbf6acd-847/gemini`

---

## 1. Executive Verdict & Boundary Stance

The bounded source repair required by `NLTK-PATHSEC-PREPARATION-REPAIR-BRIEF-2026-09-12.md` is complete. The original five proposed files from run `4a939c69` were preserved byte-for-byte in `_scratch/nltk-original/` before applying any modifications.

All four defect groups identified in the repair brief have been resolved:
1. **Patch Integrity**: `scripts/prepare_nltk_pathsec_backport.py` now parses and applies the exact unified diff (`vendor/nltk-pathsec/nltk-3.10.3-pathsec.patch`) directly to target files instead of running duplicated, divergent string replacements. It enforces constructor language validation (`_validate_name_component`), eliminates unrelated return-value modifications (`save_maxent_params` strictly returns `None`), and validates patch SHA-256 against expected hash.
2. **Boundary & Receipt Guarantees**: Source, destination, and ancestor paths are verified for symlinks and Windows reparse points *prior* to any resolution or filesystem write. Overlap in either direction (destination inside source or source inside destination) is refused. Copying uses non-following primitives. The receipt is written strictly *inside* the destination directory using exclusive file creation (`open(..., 'x')`). Staging source bytes remain 100% read-only and unmodified.
3. **Import Independence & Process Isolation**: All NLTK routing probes execute in fresh child processes with bytecode disabled (`-B`) and isolated environments, preventing runner global pollution or import order dependencies. Serialization boundaries (`json.dump`, `json.load`, `pickle.dump`, `allowlisted_pickle_load`, `MaxentEncoder`, and SVM classifiers) are mocked upfront—zero synthetic weights or checkpoints are loaded into models.
4. **Guarded Directory Creation & Honest Windows Analysis**: `save_maxent_params` now utilizes existing guarded helper `_open_private_model_dir` on POSIX (atomic `0o700` creation with pinned `O_NOFOLLOW | O_DIRECTORY` descriptors), and re-validates landed paths following `os.makedirs` on Windows. Exaggerated claims of general Windows TOCTOU immunity from static checks have been retracted; unprivileged Windows symlink limitations are recorded as stated skips rather than claimed coverage.

---

## 2. Test Execution & Failure Repair Audit

### Final Suite Results
The repaired suite was executed with bytecode generation disabled (`-B`) under isolated scratch profile `--basetemp=_scratch/pytest-run-gemini-repair04`:
```powershell
python -B -m pytest tests/test_nltk_pathsec_backport.py -v --basetemp=_scratch/pytest-run-gemini-repair04
```
**Outcome**: **28 collected items: 27 passed, 1 skipped, 0 failed** (execution duration: 105.16s).

- **Passed (27)**:
  - 6 fail-closed preparation tests: preexisting destination refusal, path traversal refusal, destination-inside-source overlap refusal, source-inside-destination overlap refusal, receipt-outside-destination refusal, tampered patch refusal.
  - 5 staging/archive integrity tests: clean preparation & exclusive receipt creation, tampered source refusal, unsupported version refusal, staging source byte verification, scratch archive byte verification.
  - 12 paired API routing tests across all six GHSA-8mgp-746c-j5xp routines:
    - `TransitionParser.train`: outside refusal vs inside control (training mocked).
    - `TransitionParser.parse`: outside refusal vs inside control (unpickling mocked).
    - `AveragedPerceptron.save`: outside refusal vs inside control (dump mocked).
    - `AveragedPerceptron.load`: outside refusal vs inside control (load mocked, no synthetic weights).
    - `PerceptronTagger.save_to_json`: outside refusal vs inside control, constructor language traversal refusal, save language traversal refusal.
    - `save_maxent_params`: outside refusal vs inside control (verified `None` return).
  - 3 boundary tests: nested traversal escape refusal, no ML/checkpoint imports (`torch`, `whisper`, `whisperx`, `pyannote`), and clean runner state.
- **Skipped (1)**:
  - `test_symlink_escape_refusal_or_unprivileged_boundary`: Stated skip due to missing Windows `SeCreateSymbolicLinkPrivilege` / Developer Mode (`[WinError 1314]`). Recorded honestly as an un-exercised platform constraint, not counted as test coverage.

### Retained Failures & Diagnostic Repairs
In accordance with standing instructions, earlier run failures were retained and documented:
- **Repair 1 (Attempt 1, 13 failures)**:
  - *Cause A*: Child process probes did not pin `nltk.pathsec._ALLOWED_ROOTS_CACHE`. On Windows, `_get_allowed_roots()` automatically trusts `tempfile.gettempdir()`, causing outside target files inside pytest's `%TEMP%` directory to be treated as authorized roots. *Fix*: Added `make_probe_sandbox_header` pinning `_ALLOWED_ROOTS_CACHE` strictly to `sandbox_dir`.
  - *Cause B*: Portable preparation tests constructed dummy sources with invalid file hashes; `validate_source_tree` failed closed on hash mismatch before reaching destination boundary checks. *Fix*: Added `minimal_valid_source` fixture copying valid original files from `staging_available`.
- **Repair 2 (Attempt 2, 1 failure)**:
  - `test_prepare_refuses_source_inside_destination` failed because `nested_src.mkdir(parents=True)` pre-created `dst_dir` on disk, causing `validate_destination_boundary` to fail with `FileExistsError` before checking directory containment. *Fix*: Re-ordered `validate_destination_boundary` to evaluate source/destination containment and overlap *before* evaluating destination existence.
- **Repair 3 (Attempt 3 / 4)**: All 27 tests passed cleanly; 1 stated skip.

---

## 3. Scope & Hash Provenance

| Artifact | Location | SHA-256 Digest |
|---|---|---|
| **Original maxent.py** | `installer/staging/.../classify/maxent.py` | `11f704cf6cd2a43b51cb13634e9cdbc46b0e8394e1e291e9b66036d6a59c2583` |
| **Original transitionparser.py** | `installer/staging/.../parse/transitionparser.py` | `ed55985d08ed38333d007c5e5c19170a4dc19009e871ab616d198a3da92eea70` |
| **Original perceptron.py** | `installer/staging/.../tag/perceptron.py` | `9d619a5ce7533c7eb388a70fedca8dcf0fb78279e1744e2abfdfcca9abd459ea` |
| **Reviewed Unified Patch** | `vendor/nltk-pathsec/nltk-3.10.3-pathsec.patch` | `56d70eece6711a52d0082b066f79ff1388c1cbe6db19d3eb09bf98b5ae11f71b` |
| **Patched maxent.py** | `<destination>/classify/maxent.py` | `60645d1be785066c083f2458153f7e83931ebd8db20d976a8d34dea100f83f3c` |
| **Patched transitionparser.py** | `<destination>/parse/transitionparser.py` | `8dcc54a30557450084858b3ed7f559697f945593f50a2fdc9f4a08e3bbbbdd60` |
| **Patched perceptron.py** | `<destination>/tag/perceptron.py` | `31d1577b9b04b22aace4fdead2b3f7bcb48864af45bfa5210f1e1d32a3cb81b9` |

---

## 4. Remaining Packaging & Integration Work

This worker has completed the source repair, deterministic preparation utility, and regression qualification. The patch is **not** a release-ready distribution and does not suppress scanner findings. The following remaining steps are reserved for Astra:

1. **Independent Verification**: Astra inspects the unified patch diff, preparation utility, and executes the suite in both worktree and clean checkout.
2. **Three-Way Application**: Apply `vendor/nltk-pathsec/nltk-3.10.3-pathsec.patch` via `git apply --3way`.
3. **Local Packaging**: Build an explicitly labelled local wheel (e.g. `nltk-3.10.3+uoink.pathsec1-py3-none-any.whl`) with recorded provenance in `THIRD-PARTY-NOTICES.md`.
4. **Lockfile & Hash Manifest**: Record the built wheel hash in the installer lock manifest without modifying upstream package metadata or suppressing advisory audit trails.
5. **Candidate Qualification**: Run full runtime dependency closure, decoder smoke checks, and installer staging verification before release qualification.
