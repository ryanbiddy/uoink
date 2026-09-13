# Runtime Dependency Graph Evaluation: Windows x64 CPython 3.13

Date: 2026-09-12  
Base: candidate c5d33a4 (qualification complete at 6a89189 / notices commit f9d9f1f)  
Worker: gemini  
Script: `scripts/check_runtime_graph.py`  
Test suite: `tests/test_runtime_graph.py`  
Evidence directory: `docs/library/proof/runtime-graph-01-2026-09-12/` (304 files, verified against `SHA256.json`)  
Status: Graph evaluation complete. Current locked graph status: **FAIL** (2 unbuilt source distributions). Proposed upgrade graph status: **FAIL** (5 rigid WhisperX constraint conflicts). Release hold remains.

---

## 1. Executive Summary

This report evaluates the PEP 508 dependency graph and wheel packaging constraints for Uoink's Windows x86-64 CPython 3.13 runtime.

Every requirement, marker, and wheel tag was verified offline by `scripts/check_runtime_graph.py` against official PyPI JSON and wheel METADATA captured on 2026-09-12. No package was imported, no build hook ran, and no model code executed.

Three concrete findings govern the runtime dependency state:

1. **The current locked stack has clean internal closure but lacks two pre-built wheels.**  
   All 140 packages in `requirements-installer-lock.txt` form a closed graph across 281 active edges. Zero packages are missing. Zero constraint conflicts exist. However, official PyPI provides only source archives (`.tar.gz`) for `antlr4-python3-runtime==4.9.3` and `proxy-tools==0.1.0`. Because this evaluation requires every selected dependency to have an authentic, pre-built wheel for Windows x64 CPython 3.13, the current locked graph reports **FAIL**.

2. **Upstream WhisperX 3.8.6 blocks the proposed security upgrades with five conflicts.**  
   Upstream security advisories for Torch (8 issues) and Transformers (5 issues) have fixes in Torch 2.9.0+ / 2.10.0+ and Transformers 5.0.0+. Upgrading Torch and Transformers to those releases creates five hard constraint conflicts against `whisperx==3.8.6`:
   - `whisperx` requires `torch~=2.8.0` (conflicts with `2.9.0`+)
   - `whisperx` requires `torchaudio~=2.8.0` (conflicts with `2.9.0`+)
   - `whisperx` requires `torchvision~=0.23.0` (conflicts with `0.24.0`+)
   - `whisperx` requires `torchcodec<0.8.0,>=0.6.0` (conflicts with `0.8.0`+)
   - `whisperx` requires `huggingface-hub<1.0.0` (conflicts with Transformers 5.x, which mandates `huggingface-hub>=1.3.0` or `>=1.5.0`)

3. **Torchaudio availability caps any co-installable Torch upgrade at 2.11.0.**  
   While PyPI hosts Torch releases up to 2.14.0, Torchaudio on PyPI stops at 2.11.0. No Torchaudio 2.12, 2.13, or 2.14 release exists on PyPI. Any future upgrade proposal that attempts to move Torch past 2.11.0 fails immediately on missing upstream Torchaudio wheels.

---

## 2. Current Locked Graph Result

- **Target environment:** Windows x86-64, CPython 3.13.15, `win32`, `AMD64`, `extra=""`
- **Selection input:** `requirements-installer-lock.txt` (140 exact pins)
- **Evaluation tool:** `python scripts/check_runtime_graph.py --selection requirements-installer-lock.txt --evidence-dir docs/library/proof/runtime-graph-01-2026-09-12`
- **Active edges evaluated:** 281
- **Missing packages:** 0
- **Conflicting constraints:** 0
- **Compatible wheels verified:** 138 packages
- **Wheel rejections:** 2 packages
- **Overall status:** **FAIL**

### Active Edge Evaluation Details

PEP 508 markers were evaluated for the target platform. Environment markers correctly excluded non-Windows dependencies:
- `triton>=3.3.0; sys_platform == "linux" and platform_machine == "x86_64"` (from `whisperx`): inactive on Windows.
- `tomli>=1.1.0; python_version < "3.11"`: inactive on Python 3.13.
- `importlib-metadata; python_version < "3.10"`: inactive on Python 3.13.
- Development and test extras (such as `pytest; extra == "dev"`) remained inactive under `extra=""`.

Platform-active markers were verified and included:
- `torchcodec<0.8.0,>=0.6.0; (sys_platform == "linux" and platform_machine == "x86_64") or sys_platform == "darwin" or sys_platform == "win32"`: active on Windows. Target `torchcodec` at `0.7.0` satisfies `<0.8.0,>=0.6.0`.

Every active target is present in `requirements-installer-lock.txt` and satisfies its caller's specifier.

### Wheel Availability Failures

The two wheel rejections are upstream release limitations on PyPI:

| Package | Locked Version | Required By | Upstream PyPI Artifacts | Result |
|---|---|---|---|---|
| `antlr4-python3-runtime` | `4.9.3` | `omegaconf==2.3.1` | `antlr4-python3-runtime-4.9.3.tar.gz` (sdist only) | `NO_WHEELS` |
| `proxy-tools` | `0.1.0` | `pywebview==5.4` | `proxy_tools-0.1.0.tar.gz` (sdist only) | `NO_WHEELS` |

In previous installer builds (`build.ps1`), pip built wheels for these two packages from source at staging time. In an offline wheel-only qualification that rejects incomplete evidence and missing wheel tags, both packages fail.

---

## 3. Proposed Fixed Graph Result

To address the open security advisories identified in `ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md`, candidate upgrades were evaluated against the proof metadata:

### Candidate Upgrade Targets

| Package | Locked Version | Advisory Target | Upstream State on PyPI |
|---|---|---|---|
| `torch` | `2.8.0` | `2.10.0` or `2.13.0` | `2.8.0` is the only 2.8.x release. Patches exist in `2.9.0`+, `2.10.0`+, `2.13.0`+, `2.14.0`. |
| `torchaudio` | `2.8.0` | Match Torch | `2.8.0`, `2.9.0`, `2.9.1`, `2.10.0`, `2.11.0` exist. No `2.12`+ exists. |
| `torchvision` | `0.23.0` | Match Torch | `0.23.0` (Torch 2.8), `0.24.0` (Torch 2.9), `0.25.0` (Torch 2.10), `0.29.0` (Torch 2.14). |
| `torchcodec` | `0.7.0` | Match Torch | `0.7.0` (Torch 2.8), `0.8.0` (Torch 2.9), `0.9.0` (Torch 2.10), `0.16.0` (Torch 2.14). |
| `transformers` | `4.57.6` | `5.10.0` | `4.57.6` is final 4.x release. `5.0.0` through `5.17.0` exist. |
| `huggingface-hub` | `0.36.2` | Match Transformers | `0.36.2` locked. `1.0.0` through `1.31.0` exist. |
| `nltk` | `3.10.3` | `3.10.4` | `3.10.3` remains the latest release on PyPI. No `3.10.4` exists. |
| `lightning` | `2.6.6` | Verified fix | PR #21832 fix verified in `2.6.6`. Scanner fixed event `2022.6.15` is an OSV error. |

### Evaluation of Proposal A: Fixed Stack with Torch 2.10.0 and Transformers 5.10.0

A selection JSON was constructed setting:
- `torch==2.10.0`
- `torchaudio==2.10.0`
- `torchvision==0.25.0`
- `torchcodec==0.9.0`
- `transformers==5.10.0`
- `huggingface-hub==1.5.0`

Running `scripts/check_runtime_graph.py` on this selection produces:
- **Status:** **FAIL**
- **Conflicting constraints:** 5 direct violations

```text
[!] CONFLICTING CONSTRAINTS (5):
  - whisperx requires 'huggingface-hub<1.0.0', but selected version is 1.5.0
  - whisperx requires 'torch~=2.8.0', but selected version is 2.10.0
  - whisperx requires 'torchaudio~=2.8.0', but selected version is 2.10.0
  - whisperx requires 'torchvision~=0.23.0', but selected version is 0.25.0
  - whisperx requires 'torchcodec<0.8.0,>=0.6.0', but selected version is 0.9.0
```

WhisperX 3.8.6 is the single constraint bottleneck. It hard-pins Torch 2.8, Torchaudio 2.8, Torchvision 0.23, Torchcodec 0.7, and Hugging Face Hub below 1.0.0.

### Evaluation of Proposal B: WhisperX 3.8.7rc1 Candidate

PyPI has pre-release `whisperx==3.8.7rc1`. Inspecting its wheel metadata reveals:
```text
Requires-Dist: huggingface-hub>=0.28.1
Requires-Dist: torch~=2.8.0
Requires-Dist: torchaudio~=2.8.0
Requires-Dist: torchvision~=0.23.0
Requires-Dist: torchcodec<0.8.0,>=0.6.0; (sys_platform == "linux" and platform_machine == "x86_64") or sys_platform == "darwin" or sys_platform == "win32"
```

WhisperX 3.8.7rc1 relaxes `huggingface-hub`, allowing `transformers 5.10.0` and `huggingface-hub 1.5.0` to co-install. However, it preserves the exact `torch~=2.8.0`, `torchaudio~=2.8.0`, `torchvision~=0.23.0`, and `torchcodec<0.8.0,>=0.6.0` constraints. It does not resolve the Torch conflicts.

---

## 4. Concrete Minimum Compatibility Patch

Because upstream WhisperX has not released a version supporting Torch 2.9+, a concrete minimum patch to `pyproject.toml` is required if Uoink forks or vendored-patches WhisperX:

### Upstream Reference

File: `whisperx/pyproject.toml` at release `v3.8.6` (commit `69e9d6d`)

```diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -28,8 +28,8 @@ dependencies = [
     "pandas>=2.2.3",
     "pyannote-audio>=4.0.0",
-    "huggingface-hub<1.0.0",
-    "torch~=2.8.0",
-    "torchaudio~=2.8.0",
-    "torchvision~=0.23.0",
-    "torchcodec<0.8.0,>=0.6.0; (sys_platform == \"linux\" and platform_machine == \"x86_64\") or sys_platform == \"darwin\" or sys_platform == \"win32\"",
+    "huggingface-hub>=0.28.1",
+    "torch>=2.8.0,<2.12.0",
+    "torchaudio>=2.8.0,<2.12.0",
+    "torchvision>=0.23.0,<0.28.0",
+    "torchcodec>=0.7.0,<0.12.0; (sys_platform == \"linux\" and platform_machine == \"x86_64\") or sys_platform == \"darwin\" or sys_platform == \"win32\"",
     "transformers>=4.48.0",
```

### Rationale for the Upper Bounds

- **Torch and Torchaudio `<2.12.0`:** PyPI has Torchaudio wheels only through version 2.11.0 (`torchaudio-2.11.0-cp313-cp313-win_amd64.whl`). Bumping Torch to 2.12, 2.13, or 2.14 leaves Torchaudio unsatisfied on PyPI.
- **Torchvision `<0.28.0`:** Torchvision 0.25.0 pairs with Torch 2.10.0, and 0.26.0 pairs with Torch 2.11.0.
- **Torchcodec `<0.12.0`:** Torchcodec 0.9.0 pairs with Torch 2.10.0, and 0.10.0 pairs with Torch 2.11.0.

### Capability Preservation

The three core audio processing capabilities are preserved under this constraint adjustment:
1. **Transcription:** `faster-whisper 1.2.1` uses `ctranslate2 4.8.1`, which executes transcription via its own native C++ inference engine. It does not depend on Torch runtime execution.
2. **Alignment:** WhisperX's forced alignment loads wav2vec2 models through `transformers` and `torchaudio.functional`. Both libraries remain operational within the 2.10/2.11 lineage.
3. **Voice Activity Detection (VAD):** `pyannote-audio 4.0.7` specifies `torch>=2.8.0`, `torchaudio>=2.8.0`, `torchcodec>=0.7.0`, and `lightning>=2.4`. It accepts Torch 2.10.0 and Torchaudio 2.10.0 without modification.

### Strict Separation Notice

This minimum patch is a **metadata-only proposal**. It establishes PEP 508 co-installability on paper. It does not certify:
- That Torch 2.10+ native Windows C++ extensions load cleanly alongside Uoink's bundled FFmpeg 7 DLLs.
- That PyAnnote checkpoint deserialization behaves safely without arbitrary class execution.
- That wav2vec2 alignment or word timestamps remain accurate.
- That transcription inference quality matches existing acceptance measurements.

No edits to production pins or WhisperX were committed in this run.

---

## 5. Unsatisfied Constraints and Remaining Gaps

No complete, clean, security-cleared runtime graph exists today. Six hard blockers remain:

1. **Wheel availability gap:** `antlr4-python3-runtime` and `proxy-tools` have no pre-built wheels on official PyPI. A wheel-only offline packaging verification fails on these two packages.
2. **WhisperX constraint ceiling:** Upstream `whisperx 3.8.6` refuses any Torch release outside `2.8.x` and any Hugging Face Hub release at `1.0.0` or higher.
3. **Missing point release for Torch 2.8:** PyPI contains only `2.8.0`. No backported security patch (such as a hypothetical `2.8.1`) was ever released by the PyTorch team.
4. **Missing patch for NLTK:** `nltk==3.10.3` is the latest release on PyPI. Advisory GHSA-8mgp-746c-j5xp remains unpatched upstream.
5. **Torchaudio PyPI truncation:** Upstream Torchaudio wheels stop at `2.11.0`, preventing any move to Torch 2.12, 2.13, or 2.14 on Windows.
6. **Authorization boundaries:** Bumping production dependency pins, modifying WhisperX, or running model conversion and inference tests requires explicit authorization from Ryan.

The candidate remains on security hold.
