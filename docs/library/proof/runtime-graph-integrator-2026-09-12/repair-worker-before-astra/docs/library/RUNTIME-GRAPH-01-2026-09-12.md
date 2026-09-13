# Runtime Dependency Graph Evaluation: Windows x64 CPython 3.13

Date: 2026-09-12  
Base: candidate c5d33a4  
Worker: gemini  
Script: `scripts/check_runtime_graph.py`  
Test suite: `tests/test_runtime_graph.py` (13 tests), `tests/test_installer_dependency_lock.py` (5 tests) — 18 passed  
Evidence directory: `docs/library/proof/runtime-graph-01-2026-09-12/` (306 files, verified against `SHA256.json`)  
Fresh review directory: `docs/library/proof/runtime-graph-review-2026-09-12/` (command outputs, proposal selection, exit codes)  
Prior report status: Original db13e13b report archived under `_scratch/runtime-graph-original/` as rejected prior evidence  
Status: Graph evaluation complete. Current locked graph status: **FAIL** (2 unbuilt source distributions in wheel-only verification). Proposed upgrade graph status: **FAIL** (5 rigid WhisperX constraint conflicts). Security release hold remains.

---

## 1. Executive Summary

This report evaluates the PEP 508 dependency graph and wheel packaging constraints for Uoink's Windows x86-64 CPython 3.13 runtime.

Every requirement, marker, and wheel tag was verified offline by the repaired `scripts/check_runtime_graph.py` against official PyPI JSON and wheel METADATA captured on 2026-09-12. No package was imported, no build hook ran, and no model code executed.

Four concrete findings govern the runtime dependency state:

1. **The current locked stack has clean internal closure but lacks two pre-built wheels in a wheel-only scan.**  
   All 140 packages in `requirements-installer-lock.txt` form a closed graph across 283 active edges (including fixed-point propagated extras for `fsspec[http]` and `pyjwt[crypto]`). Zero packages are missing. Zero constraint conflicts exist. However, official PyPI provides only source archives (`.tar.gz`) for `antlr4-python3-runtime==4.9.3` and `proxy-tools==0.1.0`. Because this evaluation requires every selected dependency to have an authentic, pre-built wheel for Windows x64 CPython 3.13, the current locked graph reports **FAIL** (command exit code 1).  
   Crucially, this wheel-only verification failure does **not** invalidate the prior installed graph: those two packages were built from source at staging time under the existing `build.ps1` build process. Documenting this factual build reality requires no new permission.

2. **Upstream WhisperX 3.8.6 blocks proposed security upgrades with five conflicts.**  
   Upstream security advisories for PyTorch extend through 2.13.0, and Transformers through 5.10.0. Testing an upgrade to Torch 2.10.0 and Transformers 5.10.0 creates five hard constraint conflicts against `whisperx==3.8.6`:
   - `whisperx` requires `torch~=2.8.0` (conflicts with `2.10.0`)
   - `whisperx` requires `torchaudio~=2.8.0` (conflicts with `2.10.0`)
   - `whisperx` requires `torchvision~=0.23.0` (conflicts with `0.25.0`)
   - `whisperx` requires `torchcodec<0.8.0,>=0.6.0` (conflicts with `0.9.0`)
   - `whisperx` requires `huggingface-hub<1.0.0` (conflicts with Transformers 5.x, which mandates `huggingface-hub>=1.3.0` or `>=1.5.0`)

3. **Torch 2.10 is not a fully fixed target, and Torchaudio metadata constrains matching releases.**  
   Torch 2.10.0 is not a complete fix when retained security advisories extend through 2.13.0. Furthermore, Torchaudio wheel metadata explicitly constrains matching Torch releases (`torchaudio 2.8.0` requires `torch==2.8.0`, and `torchaudio 2.10.0` requires `torch==2.10.0`). Additionally, official PyPI Torchaudio wheels stop at version 2.11.0. No Torchaudio 2.12, 2.13, or 2.14 wheel exists on PyPI.

4. **NLTK 3.10.4 is absent, not an approved target.**  
   PyPI contains only NLTK up to 3.10.3. NLTK 3.10.4 does not exist upstream and cannot be selected or approved as a target.

---

## 2. Current Locked Graph Result

- **Target environment:** Windows x86-64, CPython 3.13.15, `win32`, `AMD64`, `extra=""`
- **Selection input:** `requirements-installer-lock.txt` (140 exact pins)
- **Evaluation tool:** `python scripts/check_runtime_graph.py --selection requirements-installer-lock.txt --evidence-dir docs/library/proof/runtime-graph-01-2026-09-12 --output-json docs/library/proof/runtime-graph-review-2026-09-12/current_runtime_graph.json`
- **Command exit code:** `1`
- **Active edges evaluated:** 283 (clean closure across all 140 packages)
- **Active extras propagated:** `fsspec: ['http']`, `pyjwt: ['crypto']`
- **Missing packages:** 0
- **Conflicting constraints:** 0
- **Marker errors:** 0
- **Direct-URL requirement errors:** 0
- **Compatible wheels verified:** 138 packages
- **Wheel rejections:** 2 packages (`antlr4-python3-runtime==4.9.3`, `proxy-tools==0.1.0`)
- **Overall status:** **FAIL**

### Active Edge and Extras Details

PEP 508 markers were evaluated for the target platform. Environment markers correctly excluded non-Windows dependencies:
- `triton>=3.3.0; sys_platform == "linux" and platform_machine == "x86_64"` (from `whisperx`): inactive on Windows.
- `tomli>=1.1.0; python_version < "3.11"`: inactive on Python 3.13.
- `importlib-metadata; python_version < "3.10"`: inactive on Python 3.13.
- Development extras (such as `pytest; extra == "dev"`) remained inactive under base selection.

Fixed-point extras propagation activated two required optional dependency sets:
- `lightning==2.6.6` requires `fsspec[http]<2028.0,>=2022.5.0` -> activates `fsspec` extra `http`, pulling in `aiohttp` and `requests`.
- `mcp==1.28.1` requires `pyjwt[crypto]>=2.10.1` -> activates `pyjwt` extra `crypto`, pulling in `cryptography`.

All activated targets are present in `requirements-installer-lock.txt` and satisfy their callers' version specifiers.

### Wheel Availability Failures in Wheel-Only Scan

The two wheel rejections reflect upstream PyPI artifact limitations:

| Package | Locked Version | Required By | Upstream PyPI Artifacts | Result |
|---|---|---|---|---|
| `antlr4-python3-runtime` | `4.9.3` | `omegaconf==2.3.1` | `antlr4-python3-runtime-4.9.3.tar.gz` (sdist only) | `NO_WHEELS` |
| `proxy-tools` | `0.1.0` | `pywebview==5.4` | `proxy_tools-0.1.0.tar.gz` (sdist only) | `NO_WHEELS` |

In previous installer builds (`build.ps1`), pip built wheels for these two packages from source at staging time. In this offline wheel-only qualification that strictly requires authentic pre-built wheels, both packages fail. This does not invalidate the prior installed runtime where they were built from source.

---

## 3. Proposed Upgrade Graph Result

Candidate upgrades were evaluated against captured proof metadata under `docs/library/proof/runtime-graph-review-2026-09-12/proposal_selection.json`:

### Upstream State Comparison

| Package | Locked Version | Proposed Version | Upstream State on PyPI | Status / Limitations |
|---|---|---|---|---|
| `torch` | `2.8.0` | `2.10.0` | Releases exist up to `2.14.0`. | Retained advisories extend through `2.13.0`. `2.10.0` is not a fully fixed target. |
| `torchaudio` | `2.8.0` | `2.10.0` | Releases stop at `2.11.0`. | Metadata constrains matching Torch version (`torch==2.10.0`). No 2.12+ exists on PyPI. |
| `torchvision` | `0.23.0` | `0.25.0` | Pairs with Torch 2.10.0. | Upstream wheels available. |
| `torchcodec` | `0.7.0` | `0.9.0` | Pairs with Torch 2.10.0. | Upstream wheels available. |
| `transformers` | `4.57.6` | `5.10.0` | Releases exist through `5.17.0`. | Upstream wheels available. Mandates `huggingface-hub>=1.3.0`. |
| `huggingface-hub` | `0.36.2` | `1.5.0` | Releases exist through `1.31.0`. | Upstream wheels available. |
| `nltk` | `3.10.3` | `3.10.3` | Latest release on PyPI is `3.10.3`. | `3.10.4` is absent upstream, not an approved target. |
| `lightning` | `2.6.6` | `2.6.6` | `2.6.6` locked. | Retained metadata verified. |

### Evaluation of Proposal Selection

Running `scripts/check_runtime_graph.py` on `proposal_selection.json`:
- **Tool invocation:** `python scripts/check_runtime_graph.py --selection docs/library/proof/runtime-graph-review-2026-09-12/proposal_selection.json --evidence-dir docs/library/proof/runtime-graph-01-2026-09-12 --output-json docs/library/proof/runtime-graph-review-2026-09-12/proposal_runtime_graph.json`
- **Command exit code:** `1`
- **Status:** **FAIL**
- **Conflicting constraints:** 5 direct violations against `whisperx==3.8.6`

```text
[!] CONFLICTING CONSTRAINTS (5):
  - whisperx requires 'huggingface-hub<1.0.0', but selected version is 1.5.0
  - whisperx requires 'torch~=2.8.0', but selected version is 2.10.0
  - whisperx requires 'torchaudio~=2.8.0', but selected version is 2.10.0
  - whisperx requires 'torchvision~=0.23.0', but selected version is 0.25.0
  - whisperx requires 'torchcodec<0.8.0,>=0.6.0', but selected version is 0.9.0
```

WhisperX 3.8.6 hard-pins Torch 2.8, Torchaudio 2.8, Torchvision 0.23, Torchcodec 0.7, and Hugging Face Hub below 1.0.0.

### Pre-release WhisperX 3.8.7rc1 Inspection

Inspecting `whisperx==3.8.7rc1` wheel metadata shows:
```text
Requires-Dist: huggingface-hub>=0.28.1
Requires-Dist: torch~=2.8.0
Requires-Dist: torchaudio~=2.8.0
Requires-Dist: torchvision~=0.23.0
Requires-Dist: torchcodec<0.8.0,>=0.6.0; (sys_platform == "linux" and platform_machine == "x86_64") or sys_platform == "darwin" or sys_platform == "win32"
```

While `3.8.7rc1` relaxes `huggingface-hub`, it maintains identical constraints on `torch`, `torchaudio`, `torchvision`, and `torchcodec`. It does not resolve the Torch constraint conflicts.

---

## 4. Metadata Compatibility vs Source Migration Realities

A hypothetical patch to WhisperX dependency metadata (e.g. widening specifiers to `torch>=2.8.0,<2.12.0`) demonstrates paper co-installability only.

**Relaxed constraints must not be called capability preservation or working alignment.**  
No source-level migration has been implemented, and no runtime verification has been conducted. Specifically:
- **No source migration implemented:** Changing version bounds in package metadata does not establish that WhisperX or PyAnnote source code correctly interacts with Torch 2.10+ internal C++ APIs.
- **Torchaudio coupling:** Torchaudio metadata constrains a matching release. It cannot be arbitrarily separated from the underlying Torch runtime.
- **Inference and model safety unverified:** In accordance with standing rules, no model loading, checkpoint deserialization, or audio inference was executed. Whether wav2vec2 alignment or PyAnnote VAD functions correctly under a migrated stack remains unknown.
- **DLL integration:** Co-existence of Torch 2.10+ native binaries with Uoink's bundled FFmpeg 7 shared libraries is untested.

---

## 5. Unresolved Constraints and Security Hold

No complete, clean, security-cleared runtime graph exists today. Five concrete blockers remain:

1. **Wheel availability gap:** `antlr4-python3-runtime` and `proxy-tools` lack pre-built wheels on official PyPI and fail a wheel-only packaging verifier.
2. **WhisperX constraint ceiling:** Upstream `whisperx 3.8.6` strictly requires Torch 2.8.x, Torchaudio 2.8.x, Torchvision 0.23.x, Torchcodec 0.7.x, and Hugging Face Hub <1.0.0.
3. **Torch advisory scope:** Torch 2.10.0 does not resolve retained advisories that extend through 2.13.0. No 2.8.x security point release exists on PyPI.
4. **Torchaudio PyPI truncation:** Upstream Torchaudio wheels stop at 2.11.0, bounding any co-installable Torch upgrade on Windows at 2.11.0.
5. **NLTK unpatched:** NLTK 3.10.4 is absent on PyPI; NLTK 3.10.3 remains the latest available release with an unpatched advisory.

The candidate remains on security hold. No production pins were modified.
