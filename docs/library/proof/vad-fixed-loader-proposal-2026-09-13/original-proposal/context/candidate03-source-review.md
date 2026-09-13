# Candidate03 source compatibility review — 2026-09-13

The proposed stack is not ready for a runtime trial. Source inspection identifies
two incompatible calls in optional paths and confirms that the default VAD still
loads an unrestricted checkpoint. The common Pipeline and PyAnnote decoder
interfaces inspected here remain present. None of these findings is a model,
native-library, security-advisory closure or release acceptance result.

This review covers the candidate02 reference pins: Torch 2.13.0, TorchAudio
2.11.0, torchvision 0.28.0, TorchCodec 0.16.0, Transformers 5.17.0, Hub 1.31.0
and tokenizers 0.23.2. Existing callers are retained WhisperX 3.8.6,
faster-whisper 1.2.1, PyAnnote Audio 4.0.7 and torch-audiomentations 0.12.0.
Candidate02 graph01 remains a failed metadata graph with five WhisperX cap
conflicts; this source review neither replaces that graph nor accepts a
WhisperX derivative.

## Capture and evidence keys

The brief preceded collection. Nineteen public requests succeeded: five release
commit JSON records and fourteen immutable source text files. There were zero
retrieval failures. Thirteen retained files were copied and hash-checked, plus
twelve staged Python source files. No captured code was imported or executed.
Request URLs, UTC times, response hashes, release commits and local source
bindings are in `retrievals.json`, `commit-bindings.json` and
`source-bindings.json`. Raw responses are retained. The source files are data.

All paths below are relative to this directory:
`E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\runtime-candidate03-source`.
Line numbers refer to the captured bytes, not a future modified checkout.

| Key | Captured source path |
| --- | --- |
| RUN | `retained/whisper_runner.py` |
| WX | `retained/installer/staging/python/Lib/site-packages/whisperx/` |
| FW | `retained/installer/staging/python/Lib/site-packages/faster_whisper/transcribe.py` |
| PM | `retained/installer/staging/python/Lib/site-packages/pyannote/audio/core/model.py` |
| LC | `local-current/` |
| HF | `upstream/huggingface--huggingface_hub/src/huggingface_hub/` |
| TF | `upstream/huggingface--transformers/src/transformers/` |
| TA | `upstream/pytorch--audio/src/torchaudio/` |
| TC | `upstream/meta-pytorch--torchcodec/src/torchcodec/` |

## Compatibility matrix

| Used call and reachability | Exact source evidence | Candidate result and necessary change |
| --- | --- | --- |
| `snapshot_download(..., local_dir_use_symlinks=False)`. Optional faster-whisper `output_dir` branch. | `LC/faster_whisper/utils.py:106–116`; `HF/_snapshot_download.py:120–142`. Uoink uses `download_root`, which becomes `cache_dir` at `FW:681–686`. | **Incompatible keyword:** Hub's implementation has no such parameter or catch-all kwargs. Remove that keyword if this download helper is retained. Preserve local-directory containment and integrity checks separately. This is not evidence of a default-transcribe failure. An exact one-line proposal is saved as inert text. |
| `torchaudio.info(path)` in file-based augmentation. | `LC/torch_audiomentations/utils/io.py:90–102,121–125,207–208`; complete candidate `TA/__init__.py:1–205` contains no `info` definition or export. PyAnnote imports the package at `LC/pyannote/audio/core/task.py:50–51`; its default augmentation is Identity at line 305. | **Missing API:** file metadata calls cannot work against this entry point. If file augmentation is retained, give it a reviewed decoder adapter that obtains actual sample counts, or explicitly isolate this unused training capability from the shipped inference path. Do not calculate exact frame counts from approximate header duration. Default WhisperX VAD passes a waveform dict (`WX/asr.py:229`); no default call to this metadata function was established. |
| File augmentation `torchaudio.load(path, frame_offset=..., num_frames=...)`. | `LC/torch_audiomentations/utils/io.py:225–231`; candidate `TA/_torchcodec.py:114–147`. | Keywords still exist, but the candidate implementation decodes the whole file at line 128 before slicing. A requested small crop does not bound decode memory. If retained, use a bounded decoder adapter and qualify sample rounding, channels and limits. No memory failure was observed. |
| WhisperX `Pipeline`, inherited `__call__`/`forward`, and `PipelineIterator`. Default batched ASR. | `WX/asr.py:114–195,213–218`; candidate `TF/pipelines/pt_utils.py:23–24`, `TF/pipelines/base.py:1180–1215,1217–1273`. | Inspected signatures and required attributes remain. The candidate call path peeks at generators for chat detection. WhisperX overrides `get_iterator`, so the base iterator's feature-extractor lookup does not prove a defect here. Preserve WhisperX's deliberate base-initializer bypass at `asr.py:149`; changing it to ordinary `super().__init__()` would invoke assumptions about a Transformers model. Require focused batch, empty-generator and device/output contracts before accepting the cap change; no speculative rewrite is justified by these sources. |
| PyAnnote `AudioDecoder`, `AudioStreamMetadata`, metadata and sample-range calls. File paths optional; waveform input bypasses decoding. | `LC/pyannote/audio/core/io.py:43–45,101,290,341–342,427–429,458–463`; candidate `TC/decoders/__init__.py:7–8`, `TC/decoders/_audio_decoder.py:59–100`, `TC/_core/_metadata.py:27,156–161`. | Inspected decoder exports and methods remain. Header duration and sample rate may be null, while callers perform arithmetic. Add explicit rejection for missing/invalid metadata where arithmetic requires it. The decoder accepts URL strings (`_audio_decoder.py:37–38`); constrain Uoink input to approved local files before this API. Windows DLL/FFmpeg behavior and exact sample boundaries remain unproved. |
| PyAnnote `hf_hub_download` and `HfHubHTTPError`. Optional remote model/pipeline path. | `LC/pyannote/audio/utils/hf_hub.py:27–28,44–51,80–91`; candidate `HF/file_download.py:845–865`, `HF/utils/__init__.py:27`. | The used parameters and error export remain. PyAnnote's helper does not accept or forward `local_files_only`, although Hub does. Route supported assets through a separate approved resolver and pass validated local paths; if the helper remains reachable, add and propagate the policy explicitly. A cache directory alone does not disable downloading. |
| Alignment bundles and Wav2Vec2 processor loading. Uoink invokes alignment only inside `if diarize`. | `RUN:357–375`; `WX/alignment.py:32–38,93–110`; candidate `TA/pipelines/__init__.py:22–29`, `TF/models/wav2vec2/processing_wav2vec2.py:28–30`, `TF/processing_utils.py:1688–1696,1726–1737`. | All five named TorchAudio bundle exports and the inspected processor loading interface remain. The TorchAudio branch ignores `model_cache_only`; the HF branch forwards it. Keep the speaker gate blocked. Before any later alignment trial, make both branches use approved local artifacts. Wav2Vec2ForCTC's target implementation and native bundle execution were not inspected or qualified. |
| Default PyAnnote VAD, even when diarization is off. | `RUN:346–348`; `WX/asr.py:322–328,418–430`; `WX/vads/pyannote.py:21–41`; `PM:602–625,640–644`. | **Existing release blocker:** the bundled local checkpoint reaches `pl_load(..., weights_only=False)`, then a checkpoint-selected module/class and a second unrestricted load. Neither newer Torch nor the speaker gate removes this explicit path. Provide a reviewed VAD implementation using a validated artifact and fixed architecture before enabling the default route. Checkpoint contents, classes and conversion viability remain unknown. |

## Minimal derivative and guard work

The next implementation brief should cover these concrete changes together:

1. Replace both the cache-readiness predicate (`RUN:154–158`) and transcription
   consent check (`RUN:325–334`) with validation of a complete, versioned asset
   manifest. An arbitrary file currently makes the directory look populated.
   Require approved IDs/revisions, required files, sizes/hashes and resolved
   path containment. Fetch consent must authorize an explicit asset plan, and
   incomplete caches must fail before constructors or download helpers run.
2. Split resolution from execution. `WX/asr.py:357–364` already permits an
   injected `WhisperModel`; `FW:678–679` accepts a local model directory.
   The execution path should receive a validated local directory and explicit
   local-only policy. `FW:688–708` currently constructs CTranslate2 before
   checking `tokenizer.json`, and falls back to
   `Tokenizer.from_pretrained` when that file is missing. Check the complete
   asset set before any constructor, and reject that fallback in the shipped
   offline execution path. Merely adding `local_files_only=True` to WhisperX
   would not guard this independent fallback.
3. Supply a reviewed VAD through WhisperX's `vad_model` hook; it takes priority
   at `WX/asr.py:418–421`. Keep the unsafe default unavailable until its
   replacement is reviewed. The present loader also creates Torch's global
   cache directory (`WX/vads/pyannote.py:22–26`), so it cannot serve as a
   data-root-only implementation. Switching to the current Silero wrapper is
   not a repair: `WX/vads/silero.py:26–30` invokes remote `torch.hub.load` with
   `trust_repo=True`. Do not guess a checkpoint architecture or blanket-allow
   pickle globals. A separately authorized, isolated checkpoint inventory is
   still required before drafting a safe conversion or exact fixed loader.
4. Keep alignment and speaker attribution unavailable under the existing
   gate. In a later authorized alignment scope, remove the unapproved missing
   `punkt_tab` download (`WX/alignment.py:192–195`) and give the TorchAudio and
   HF branches the same explicit asset policy. The `.pickle` spelling here
   does not establish arbitrary pickle loading: the retained NLTK route uses
   a pickle-free compatibility loader for this resource.

The five packaging caps are explicit in upstream WhisperX 3.8.6
`upstream/m-bain--whisperX/pyproject.toml:19–23`. A proposed derivative must
update those declarations only with the reviewed implementation and evidence.
WhisperX packaging changes cannot remove faster-whisper's obsolete keyword or
torch-audiomentations' missing API: those need separately reviewed source
changes or explicit exclusion of the unsupported optional paths. The proposed
one-line diff does not by itself qualify either package or the full stack.

Before a runtime trial, new focused guard tests should establish: arbitrary or
partial cache contents do not bypass consent; a missing tokenizer fails before
CTranslate2 construction and any network helper; a validated local manifest
requires no fetch; VAD cannot fall back to unrestricted loads or remote Hub
code; optional file adapters reject invalid metadata and enforce limits; and
the retained Pipeline contracts handle empty and batched inputs. Existing
behavior assertions must remain unchanged. No such tests were run in this
source-only task.

## Bound release references

| Repository tag | Commit used for every captured raw file |
| --- | --- |
| `huggingface/transformers` v5.17.0 | `856157a2f3e9594954310df18fdccc31ffddebe9` |
| `huggingface/huggingface_hub` v1.31.0 | `495b17c8529614759ae0f1ccf1ebe9a61c148b7c` |
| `pytorch/audio` v2.11.0 | `34c52a67e8941bbd8e6adaca0eb0b9eabec11d78` |
| `meta-pytorch/torchcodec` v0.16.0 | `ce046a849e8a4054d7fee8879b7d574eb0e931c5` |
| `m-bain/whisperX` v3.8.6 | `3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0` |

Collector SHA-256:
`ce8cb6ec33fa2c7451ac134b1b0797d4b11c3e6156d892e14e2509f8d3d9dd1c`.
No model, media, wheel, binary or archive was retrieved. No product source,
accepted test, dependency installation, runtime state or sealed candidate02
evidence was changed. This task made no commit, push or release claim.
