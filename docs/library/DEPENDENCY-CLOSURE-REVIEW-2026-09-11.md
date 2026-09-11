# Dependency Closure Review: Remaining Advisories and Feasible Repairs

**Date:** 2026-09-11  
**Author:** gemini (Worker review)  
**Status:** Report-only review. No lockfile, product code, or test files modified. No package installations, model downloads, or inference runs performed.  
**Review Target:** Windows Python 3.13 runtime inventory for Uoink Living Library 3.8.0 release candidate.

---

## 1. Executive Summary

This report completes the follow-up review requested in `docs/library/DEPENDENCY-CLOSURE-REVIEW-BRIEF-2026-09-11.md`. It evaluates the 19 advisory entries (15 distinct alias-connected issues) retained across four runtime packages (`lightning`, `nltk`, `torch`, `transformers`) in the 2026-09-09 candidate baseline (`ASTRA-DEPENDENCY-SECURITY-VERDICT-2026-09-09.md` and `RELEASE-NOTES-LIVING-LIBRARY.md`).

Key findings from primary upstream metadata retrieved on 2026-09-11:

1. **Lightning 2.6.6 is published and provides a feasible compatible repair.**  
   On 2026-09-10T09:41:00Z, upstream published `lightning 2.6.6` and `pytorch-lightning 2.6.6` to PyPI. These releases include PR #21832 and PR #21914, fixing arbitrary code execution in `LightningModule.load_from_checkpoint` via the `_instantiator` hyperparameter and unverified `_class_path` (CVE-2026-58659 / GHSA-qqmf-gpg7-g8gw). Upgrading to `lightning==2.6.6` and `pytorch-lightning==2.6.6` is compatible with Python 3.13, satisfies all peer constraints (including `pyannote-audio>=4.0.0` and `torch==2.8.0`), and resolves this advisory.
2. **NLTK remains unpatched upstream.**  
   NLTK `3.10.3` remains the latest release on PyPI. Advisory CVE-2026-81726 (`GHSA-8mgp-746c-j5xp`, `pathsec` model-artifact bypass) affects all published versions through 3.10.3 (`last_affected: 3.10.3`). Uoink's call path uses `nltk.tokenize.sent_tokenize` via WhisperX, which does not exercise the affected model persistence APIs, but the advisory remains an open audit finding.
3. **Torch remains graph-constrained at 2.8.0.**  
   `whisperx 3.8.6` strictly pins `torch~=2.8.0`. On PyPI, the 2.8 series contains only `2.8.0`; no 2.8.1 or 2.8.2 patch release was ever issued. Upgrading to PyTorch 2.9.x or 2.10.x+ breaks the WhisperX runtime constraint, as well as downstream pins for `torchaudio~=2.8.0`, `torchvision~=0.23.0`, and `torchcodec 0.7.0`. All 8 Torch advisories remain unresolved.
4. **Transformers remains graph-constrained at 4.57.6.**  
   Transformers `4.57.6` is the final release in the 4.x line. Resolving the 5 recorded advisories requires `transformers >= 5.0.0`, which mandates `huggingface-hub >= 1.3.0` (and `5.10.0` mandates `>= 1.5.0`). `whisperx 3.8.6` constrains `huggingface-hub < 1.0.0` (pinned to `0.36.2`). Pre-release `whisperx 3.8.7rc1` relaxes `huggingface-hub` to `>=0.28.1`, but it is an unfinalized candidate from June 2026 and still hard-pins `torch~=2.8.0`.
5. **Packaged checkpoint loading is reachable in ordinary transcription.**  
   `whisper_runner.py` calls `whisperx.load_model()`. By default, WhisperX enables PyAnnote voice activity detection (`vad_method="pyannote"`). This path calls `pyannote.audio.core.model.Model.from_pretrained()`, which executes `pl_load(..., weights_only=False)` and `LightningModule.load_from_checkpoint(..., weights_only=False)` on the bundled file `whisperx/assets/pytorch_model.bin`. Disabling speaker attribution or diarization does **not** bypass this loader.
6. **Audit disposition:**  
   This review does **not** declare a clean audit. If the Lightning 2.6.6 repair is accepted, the package inventory retains **17 advisory entries representing 14 distinct issues across three packages** (NLTK: 1, Torch: 8, Transformers: 5).

---

## 2. Primary Upstream Retrieval Metadata (Observed 2026-09-11)

All package metadata, wheel availabilities, and advisory statuses were queried directly from official PyPI and OSV endpoints on 2026-09-11.

| Package | Locked Version | Upstream Latest (PyPI) | Target ABI Compatibility | Primary Metadata URL | Retrieval Date |
|---|---|---|---|---|---|
| **lightning** | 2.6.5 | 2.6.6 | Pure Python (`py3-none-any.whl`), `requires_python: >=3.10` | `https://pypi.org/pypi/lightning/json` | 2026-09-11 |
| **pytorch-lightning** | 2.6.5 | 2.6.6 | Pure Python (`py3-none-any.whl`), `requires_python: >=3.10` | `https://pypi.org/pypi/pytorch-lightning/json` | 2026-09-11 |
| **nltk** | 3.10.3 | 3.10.3 | Pure Python (`py3-none-any.whl`), `requires_python: >=3.9` | `https://pypi.org/pypi/nltk/json` | 2026-09-11 |
| **torch** | 2.8.0 | 2.14.0 (2.8 line: 2.8.0 only) | Windows x86-64 wheel available for 2.8.0; no 2.8.x patch exists | `https://pypi.org/pypi/torch/json` | 2026-09-11 |
| **transformers** | 4.57.6 | 5.17.0 (4.x line: 4.57.6 only) | Pure Python (`py3-none-any.whl`), `requires_python: >=3.9` | `https://pypi.org/pypi/transformers/json` | 2026-09-11 |
| **whisperx** | 3.8.6 | 3.8.6 (Pre-release: 3.8.7rc1) | Pure Python (`py3-none-any.whl`), `requires_python: <3.14,>=3.10` | `https://pypi.org/pypi/whisperx/json` | 2026-09-11 |
| **pyannote-audio** | 4.0.7 | 4.0.7 | Pure Python (`py3-none-any.whl`), `requires_python: >=3.10,<3.14` | `https://pypi.org/pypi/pyannote-audio/json` | 2026-09-11 |
| **huggingface-hub** | 0.36.2 | 1.8.1 | Pure Python (`py3-none-any.whl`), `requires_python: >=3.9` | `https://pypi.org/pypi/huggingface-hub/json` | 2026-09-11 |

---

## 3. Review of the 15 Retained Issues

### 3.1 Lightning (1 distinct issue)

* **Advisory Details:**
  * **Identifiers:** CVE-2026-58659, `GHSA-qqmf-gpg7-g8gw`, `PYSEC-2026-3624`.
  * **Summary:** Arbitrary code execution in `_load_state` via checkpoint `_instantiator` hyperparameters during `LightningModule.load_from_checkpoint`. Crafted checkpoints bypass `weights_only=True`.
  * **Historical Note:** The advisory database previously recorded an invalid fixed event of `2022.6.15` (a date string erroneously parsed as a PEP 440 version). Upstream commit `d710d68` had merged, but no PyPI release had been cut as of 2026-09-09.
* **Current Status (2026-09-11):**
  * **Resolved Upstream:** `lightning 2.6.6` and `pytorch-lightning 2.6.6` were uploaded to PyPI on 2026-09-10T09:41:00Z and 2026-09-10T09:41:14Z respectively.
  * **Upstream Changes:**
    * PR #21832: Restricts `_instantiator` hyperparameter deserialization to an explicit allowlist of trusted instantiators.
    * PR #21914: Enforces that checkpoint `_class_path` must resolve to an already imported subclass of the target model class.
  * **Release Notes URL:** `https://github.com/Lightning-AI/pytorch-lightning/releases/tag/2.6.6`
* **Dependency & Runtime Compatibility:**
  * Base dependencies of `lightning 2.6.6`: `torch<4.0,>=2.1.0`, `torchmetrics<3.0,>0.7.0`, `lightning-utilities<2.0,>=0.10.0`, `packaging<27.0,>=23.0`, `tqdm<6.0,>=4.57.0`, `typing-extensions<6.0,>4.5.0`, `fsspec[http]<2028.0,>=2022.5.0`, `PyYAML<8.0,>5.4`, `pytorch-lightning`.
  * Every constraint is satisfied by the current lockfile pins: `torch==2.8.0`, `torchmetrics==1.9.0`, `lightning-utilities==0.15.3`, `packaging==26.2`, `tqdm==4.69.0`, `typing_extensions==4.16.0`, `fsspec==2026.6.0`, `PyYAML==6.0.3`.
  * Downstream consumer: `pyannote-audio 4.0.7` specifies `lightning>=2.4`. `2.6.6` satisfies this range.
  * Runtime ABI: Pure Python wheel (`lightning-2.6.6-py3-none-any.whl`, 696,441 bytes, SHA-256 `6e584f94b1a457497d3df19ffcc0567e98f0ef81878d65cf571fead6fbfa2e4d`) requires Python `>=3.10`, fully compatible with Windows CPython 3.13.15.
* **Recommendation:** **Feasible repair.** Upgrade `lightning` to `2.6.6` and `pytorch-lightning` to `2.6.6`.

---

### 3.2 NLTK (1 distinct issue)

* **Advisory Details:**
  * **Identifiers:** CVE-2026-81726, `GHSA-8mgp-746c-j5xp`, `PYSEC-2026-3740`.
  * **Summary:** Model-artifact APIs bypass `pathsec` enforcement and read/write files outside allowed roots.
  * **Affected Components:** `TransitionParser.train`, `TransitionParser.parse`, `AveragedPerceptron.save`, `AveragedPerceptron.load`, `PerceptronTagger.save_to_json`, `save_maxent_params`.
  * **Affected Versions:** All versions through 3.10.3 (`last_affected: 3.10.3`).
  * **OSV Advisory URL:** `https://api.osv.dev/v1/vulns/GHSA-8mgp-746c-j5xp`
* **Current Status (2026-09-11):**
  * **Unpatched Upstream:** NLTK `3.10.3` remains the latest release on PyPI. No 3.10.4 or 3.11 release exists.
* **Reachability & Bounded Risk:**
  * Uoink first-party code contains zero imports of `nltk`.
  * Transitive usage: WhisperX imports `nltk.tokenize.sent_tokenize` for sentence-level segment boundary detection prior to forced phoneme alignment.
  * `sent_tokenize` uses `PunktSentenceTokenizer`, which relies on bundled pickle models loaded via NLTK's data loader. It does not invoke `TransitionParser`, `AveragedPerceptron`, or any of the vulnerable persistence functions.
  * While actual runtime exposure is bounded by the absence of these call sites, the package audit retains the vulnerability until an upstream release patches the library.
* **Recommendation:** **Retain `nltk==3.10.3`.** Document as an unpatched upstream advisory with bounded exposure.

---

### 3.3 Torch (8 distinct issues)

* **Advisory Details:**
  1. **CVE-2025-3001** (`GHSA-qfhq-4f3w-5fph`, `PYSEC-2025-195`): Memory corruption in `torch.lstm_cell`. Fixed in `2.10.0`.
  2. **CVE-2025-3000** (`GHSA-rrmf-rvhw-rf47`, `PYSEC-2025-194`): Memory corruption in `torch.jit.script`. Fixed in `2.13.0`.
  3. **CVE-2025-2999** (`GHSA-vgrw-7cvw-pwgx`, `PYSEC-2025-193`): Memory corruption in `unpack_sequence`. Fixed in `2.9.1`.
  4. **CVE-2025-55551** (`PYSEC-2025-203`): Denial of service in `torch.linalg.lu` slice operation. Fixed in `2.9.0`.
  5. **CVE-2025-55552** (`PYSEC-2025-204`): Unexpected behavior when `torch.rot90` and `torch.randn_like` are combined. Fixed in `2.9.0`.
  6. **CVE-2025-55554** (`PYSEC-2025-206`): Integer overflow in `torch.nan_to_num-.long()`. Fixed in `2.9.0`.
  7. **CVE-2026-4538** (`PYSEC-2026-139`): Deserialization flaw in pt2 Loading Handler. Unfixed upstream (`last_affected: 2.10.0`).
  8. **CVE-2026-24747** (`PYSEC-2026-2286`, `GHSA-63cw-57p8-fm3p`): Memory corruption and remote code execution in `weights_only` unpickler via crafted checkpoint files in `torch.load(..., weights_only=True)`. Fixed in `2.10.0`.
* **Current Status & Compatibility Blockers (2026-09-11):**
  * **Upstream Releases:** PyTorch upstream releases jump from `2.8.0` directly to `2.9.0`, `2.9.1`, `2.10.0`, etc. No `2.8.1` or point release exists on PyPI.
  * **Hard Constraint from WhisperX:** `whisperx 3.8.6` contains `torch~=2.8.0`, which strictly enforces `>= 2.8.0, < 2.9.0`. Even the latest unreleased pre-release (`whisperx 3.8.7rc1`) specifies `torch~=2.8.0`.
  * **Ecosystem Cascades:** Upgrading to `torch >= 2.10.0` would also require:
    * `torchaudio~=2.8.0` and `torchvision~=0.23.0` upgrade to 2.10.x, which violates WhisperX's compatible-release constraints.
    * Re-qualifying `torchcodec 0.7.0` (which is pinned for PyTorch 2.8 and dynamically links to shared FFmpeg 7 DLLs).
* **Reachability & Checkpoint Risk:**
  * Uoink does not call `torch.lstm_cell`, `torch.jit.script`, `torch.linalg.lu`, or `torch.rot90`.
  * However, `CVE-2026-24747` (deserialization in `torch.load`) and general checkpoint unpickling risks intersect directly with the VAD checkpoint loading path detailed in Section 4.
* **Recommendation:** **Retain `torch==2.8.0`.** Upgrading is blocked by the upstream WhisperX dependency graph.

---

### 3.4 Transformers (5 distinct issues)

* **Advisory Details:**
  1. **CVE-2026-4372** (`GHSA-29pf-2h5f-8g72`, `PYSEC-2026-2289`): RCE via `_attn_implementation_internal` repo ID in `config.json` during `AutoModelForCausalLM.from_pretrained()`. Fixed in `5.3.0`.
  2. **CVE-2026-1839** (`GHSA-69w3-r845-3855`, `PYSEC-2026-2288`): Arbitrary code execution in `Trainer` class via training arguments. Fixed in `5.0.0`.
  3. **CVE-2026-5241** (`GHSA-fgcw-684q-jj6r`, `PYSEC-2026-2290`): Arbitrary code execution during LightGlue model loading. Fixed in `5.5.0`.
  4. **CVE-2026-9856** (`GHSA-xrqw-3rrv-vx5w`): Path traversal in `save_pretrained` via chat template names. Fixed in `5.10.0`.
  5. **CVE-2025-14929** (`PYSEC-2025-217`): Deserialization in X-CLIP checkpoint conversion script. Unfixed upstream.
* **Current Status & Compatibility Blockers (2026-09-11):**
  * **Upstream Releases:** In the 4.x lineage, `4.57.6` is the final release on PyPI.
  * **Dependency Graph Conflict:**
    * Patches for these issues require `transformers >= 5.0.0` (or `5.10.0`).
    * `transformers 5.0.0` specifies `huggingface-hub<2.0,>=1.3.0`. `transformers 5.10.0` specifies `huggingface-hub<2.0,>=1.5.0`.
    * `whisperx 3.8.6` strictly specifies `huggingface-hub<1.0.0` (pinned to `0.36.2`).
    * Resolving `transformers >= 5.x` alongside `whisperx 3.8.6` causes an immediate pip solver conflict on `huggingface-hub`.
  * **Status of WhisperX 3.8.7rc1:**
    * `whisperx 3.8.7rc1` relaxed `huggingface-hub` to `>=0.28.1`.
    * However, `3.8.7rc1` has remained an unreleased pre-release candidate since June 26, 2026. Bundling an unreleased RC into a production installer violates release qualification policy. Furthermore, `3.8.7rc1` maintains the hard pin `torch~=2.8.0`, so it does not resolve the underlying Torch constraints.
* **Reachability:**
  * Uoink has zero first-party imports of `transformers`.
  * WhisperX uses `transformers` solely for phoneme alignment (`Wav2Vec2ForCTC`, `Wav2Vec2Processor`). It does not invoke `AutoModelForCausalLM`, `Trainer`, `LightGlue`, or chat template export functions.
* **Recommendation:** **Retain `transformers==4.57.6`.** Upgrading to 5.x is blocked by WhisperX's published dependencies.

---

## 4. Transcription Call Path & Packaged Checkpoint Loader Audit

### 4.1 The Complete Execution Path

Inspection of the actual execution trace reveals that checkpoint loading is active during ordinary audio transcription, even when speaker attribution is disabled.

```text
whisper_runner.transcribe_audio(audio_path, ..., diarize=False)
  │
  ├──> whisperx.load_model(model_size, device=device, ...)  [whisperx/asr.py:load_model]
  │      │
  │      ├──> vad_method defaults to "pyannote"
  │      │
  │      └──> whisperx.vads.pyannote.load_vad_model(device, ...)  [whisperx/vads/pyannote.py]
  │             │
  │             ├──> model_fp = os.path.join(main_dir, "assets", "pytorch_model.bin")
  │             │
  │             └──> Model.from_pretrained(model_fp)  [pyannote/audio/core/model.py]
  │                    │
  │                    ├──> pl_load(model_fp, weights_only=False)  [lightning.fabric.utilities.cloud_io._load]
  │                    │
  │                    └──> Klass.load_from_checkpoint(model_fp, weights_only=False)
  │                           [pytorch_lightning.core.module.LightningModule.load_from_checkpoint]
```

### 4.2 Detailed Call Site Analysis

1. **`whisper_runner.py` Lines 346–350:**
   ```python
   model = whisperx.load_model(model_size, device=device,
                               compute_type=_compute_type(device),
                               download_root=str(model_path))
   result = model.transcribe(str(audio_path), language=language)
   ```
   The call passes `model_size` to `whisperx.load_model`. It does not pass `vad_method` or `vad_model`.

2. **`whisperx/asr.py` Line 139:**
   `load_model()` declares default parameters:
   ```python
   def load_model(
       whisper_arch: str,
       device: str,
       ...
       vad_model: Optional[Vad] = None,
       vad_method: Optional[str] = "pyannote",
       ...
   ):
   ```
   When `vad_model` is `None` and `vad_method` is `"pyannote"`, execution calls:
   ```python
   vad_model = Pyannote(device=device_vad, **default_vad_options)
   ```
   which invokes `whisperx.vads.pyannote.load_vad_model`.

3. **`whisperx/vads/pyannote.py` Lines 25–40:**
   ```python
   if model_fp is None:
       model_fp = os.path.join(main_dir, "assets", "pytorch_model.bin")
       model_fp = os.path.abspath(model_fp)

   vad_model = Model.from_pretrained(model_fp, token=token)
   ```
   This resolves to the bundled checkpoint file shipped inside the installer payload.

4. **`pyannote/audio/core/model.py` Lines 540–560:**
   ```python
   loaded_checkpoint = pl_load(
       path_to_model_checkpoint, map_location=map_location, weights_only=False
   )
   ...
   model = Klass.load_from_checkpoint(
       path_to_model_checkpoint,
       map_location=map_location,
       strict=strict,
       weights_only=False,
       **kwargs,
   )
   ```
   Here, `pl_load` is imported directly from `lightning.fabric.utilities.cloud_io._load`. Notice that `weights_only=False` is hardcoded in both calls.

### 4.3 Packaged Artifact Metadata

* **Relative Path:** `Lib\site-packages\whisperx\assets\pytorch_model.bin`
* **Size:** 17,719,103 bytes
* **SHA-256 Digest:** `0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`
* **Origin:** Shipped statically within the Inno Setup payload (Package-05 compiler input seal).
* **Integrity Context:** The installer deploys this file into `%LOCALAPPDATA%\Programs\Uoink\Lib\site-packages\whisperx\assets\`. Because Uoink installs in per-user mode without administrator elevation, any process executing under the same user security context can modify this file.

### 4.4 Implications for Speaker Attribution Claims

Disabling speaker attribution (`diarize=False` in `transcribe_audio`) only prevents the separate execution of `whisperx.DiarizationPipeline` and `pyannote/speaker-diarization-community-1`. It has **zero effect** on the VAD pipeline. VAD is a mandatory pre-processing step for WhisperX's batched transcription to segment speech audio before passing it to CTranslate2.

Therefore, claims that checkpoint loaders are unreachable when diarization is disabled are factually false. Checkpoint deserialization via `LightningModule.load_from_checkpoint(..., weights_only=False)` occurs on every cold audio transcription.

---

## 5. First-Party Code Mitigation Analysis

Because `torch` cannot be upgraded without breaking `whisperx`, and `pyannote.audio` hardcodes `weights_only=False`, we evaluate potential first-party code repairs in `whisper_runner.py`.

### 5.1 Proposed Bounded Fix: Pre-flight Artifact Integrity Verification

`whisper_runner.py` can enforce an explicit integrity check before allowing WhisperX to load the VAD model:

```python
# Bounded mitigation for packaged VAD checkpoint verification
_PACKAGED_VAD_SHA256 = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
_PACKAGED_VAD_SIZE = 17719103

def _verify_packaged_vad_checkpoint() -> None:
    """Verify origin, bounds, and integrity of the bundled PyAnnote VAD checkpoint."""
    try:
        import whisperx
    except ImportError:
        return
    assets_dir = Path(whisperx.__file__).resolve().parent / "assets"
    checkpoint_path = assets_dir / "pytorch_model.bin"

    if not checkpoint_path.is_file() or checkpoint_path.is_symlink():
        raise RuntimeError("Packaged VAD checkpoint is missing or redirected")

    stat = checkpoint_path.stat()
    if stat.st_size != _PACKAGED_VAD_SIZE:
        raise RuntimeError(
            f"VAD checkpoint size mismatch: expected {_PACKAGED_VAD_SIZE}, got {stat.st_size}"
        )

    import hashlib
    digest = hashlib.sha256()
    with open(checkpoint_path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != _PACKAGED_VAD_SHA256:
        raise RuntimeError("Packaged VAD checkpoint integrity verification failed")
```

#### Meaningful Trade-offs & Regressions
* **What it fixes:** Neutralizes local tampering. If malware on the user's system alters `pytorch_model.bin` to exploit `load_from_checkpoint` or `torch.load`, `transcribe_audio` refuses execution immediately and logs an integrity failure.
* **What it does not fix:** It does not protect against vulnerabilities inherent to the legitimate binary itself, nor does it eliminate the unpickling code path in memory.
* **Maintenance impact:** Any legitimate future update to WhisperX's bundled checkpoint will require updating the pinned size and digest constants in `whisper_runner.py`.

### 5.2 Evaluated Alternatives (Rejected)

1. **Switching to Silero VAD (`vad_method="silero"`):**  
   * **Rejected.** Inspecting `whisperx/vads/silero.py` shows:
     ```python
     self.vad_pipeline, vad_utils = torch.hub.load(
         repo_or_dir='snakers4/silero-vad', model='silero_vad',
         force_reload=False, onnx=False, trust_repo=True
     )
     ```
     Silero downloads code and models dynamically from GitHub via `torch.hub.load` with `trust_repo=True`. This introduces uncontrolled runtime internet fetching and remote code execution, violating Uoink's offline, local-first packaged architecture.
2. **Forcing `weights_only=True` via Monkeypatching:**  
   * **Rejected.** `pyannote.audio` checkpoints serialize custom model architectures and configuration dictionaries alongside weights. Testing PyAnnote models under `weights_only=True` fails with `UnsupportedClassException` unless complex, fragile allowlists are injected into PyTorch's internal unpickler. This risks breaking audio segmentation across various audio sample rates.

---

## 6. Exact Version Change Proposals

We propose the following precise version changes for Astra's independent verification.

### 6.1 Feasible Upgrades Ready for Integration

| Distribution | Current Pin | Proposed Pin | Wheel Name | Wheel Size | SHA-256 Digest |
|---|---|---|---|---:|---|
| `lightning` | `2.6.5` | `2.6.6` | `lightning-2.6.6-py3-none-any.whl` | 696,441 | `6e584f94b1a457497d3df19ffcc0567e98f0ef81878d65cf571fead6fbfa2e4d` |
| `pytorch-lightning` | `2.6.5` | `2.6.6` | `pytorch_lightning-2.6.6-py3-none-any.whl` | 815,223 | `2d46e3ea4062e73a3df54f76263b6555ddf3eb65c4004cf85c635c43d7890b1c` |

* **Verification of `requirements-installer-lock.txt` Parity:**
  Both distributions are pure Python wheels compatible with Python `>=3.10` on Windows x86-64. Upgrading them increments the version while preserving all other 137 locked distributions unchanged.

### 6.2 Distributions Retained Unchanged

| Distribution | Locked Pin | Rationale for Retention |
|---|---|---|
| `nltk` | `3.10.3` | Upstream unpatched (`last_affected: 3.10.3`). WhisperX uses `sent_tokenize` only; model-artifact path APIs are not called. |
| `torch` | `2.8.0` | Graph-constrained by `whisperx 3.8.6 -> torch~=2.8.0`. No 2.8.x patch release exists on PyPI. |
| `torchaudio` | `2.8.0` | Paired with `torch 2.8.0`. |
| `torchvision` | `0.23.0` | Paired with `torch 2.8.0`. |
| `torchcodec` | `0.7.0` | Bound to `torch 2.8.0` and app-relative FFmpeg 7 LGPL shared runtime (`n7.1.5`). |
| `transformers` | `4.57.6` | Graph-constrained. Patched 5.x requires `huggingface-hub >= 1.3.0`, conflicting with `whisperx 3.8.6 -> huggingface-hub < 1.0.0`. |
| `whisperx` | `3.8.6` | Retained stable release. 3.8.7rc1 is an unfinalized candidate and retains `torch~=2.8.0`. |

---

## 7. Residual Advisories & Audit Disposition

Integrating the proposed Lightning 2.6.6 update reduces the retained advisory count from 19 entries / 15 issues across 4 packages to **17 entries / 14 issues across 3 packages**.

| Package | Pinned Version | Active OSV Entries | Distinct Issues | Primary CVE Identifiers | Upstream Status | Runtime Exposure in Uoink |
|---|---|---:|---:|---|---|---|
| **nltk** | 3.10.3 | 1 | 1 | CVE-2026-81726 | Unpatched on PyPI | Low (only `sent_tokenize` called) |
| **torch** | 2.8.0 | 8 | 8 | CVE-2025-3001, CVE-2025-3000, CVE-2025-2999, CVE-2025-55551, CVE-2025-55552, CVE-2025-55554, CVE-2026-4538, CVE-2026-24747 | Patched in 2.9+/2.10+; blocked by WhisperX | High on checkpoint loading; Low on unused tensor math ops |
| **transformers** | 4.57.6 | 8 | 5 | CVE-2026-4372, CVE-2026-1839, CVE-2026-5241, CVE-2026-9856, CVE-2025-14929 | Patched in 5.x; blocked by huggingface-hub | Low (only Wav2Vec2 alignment used) |
| **Total** | | **17** | **14** | | | |

This candidate release **cannot be certified as having a clean dependency security audit**. Release notes must continue to disclose these 14 issues, the architectural blockers in WhisperX, and the residual risk associated with PyAnnote checkpoint deserialization.

---

## 8. Verification Steps Owed Prior to Lock Update

Before Astra applies the version updates to `requirements-installer-lock.txt` and `THIRD-PARTY-NOTICES.md`, the following verification steps are owed:

1. **Resolver Parity Check:**  
   Execute `scripts/verify_installer_lock.py` with `lightning==2.6.6` and `pytorch-lightning==2.6.6` to confirm that the 139-package runtime graph remains closed with zero unmet peer dependencies.
2. **First-Party VAD Smoke Verification:**  
   In a Python 3.13 verification environment with the updated wheels installed, verify that:
   ```python
   import lightning
   import pytorch_lightning
   assert lightning.__version__ == "2.6.6"
   assert pytorch_lightning.__version__ == "2.6.6"
   import whisperx
   from whisperx.vads.pyannote import load_vad_model
   vad = load_vad_model("cpu")
   assert vad is not None
   ```
   Confirm that `load_vad_model` succeeds with the new instantiator allowlist in Lightning 2.6.6.
3. **Third-Party Notices Generation:**  
   Run `scripts/gen_third_party_notices.py` to confirm that `pip-licenses` extracts the Apache 2.0 license text cleanly for both updated wheels without formatting anomalies.
4. **Installer Build & Asset Scan:**  
   Rebuild `Uoink-Setup-3.8.0.exe` using `build.ps1`, verify that compiler input digests match, and submit the executable to Microsoft Defender scan verification.
