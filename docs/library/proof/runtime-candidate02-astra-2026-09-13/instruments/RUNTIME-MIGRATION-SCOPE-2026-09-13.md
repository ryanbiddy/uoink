# Runtime migration scope for the release integrator

Prepared against checkout 4b8dc95912ae74fcdcc0dccf5f9d862d08207fb2. This is an
unapplied proposal. No runtime, model, product test, package installation or
dependency build ran. Website and marketing work remains paused.

There is a plausible upgrade route worth completing before asking Ryan for a
model decision. TorchAudio's latest captured version, 2.11.0, does not require
staying on Torch 2.11: its release notes explicitly permit later Torch versions.
The captured Windows wheel METADATA has no exact Torch requirement. Torch
2.13.0, TorchAudio 2.11.0 and torchvision 0.28.0 therefore form a concrete
candidate for source and artifact review. They are not an accepted runtime.
[TorchAudio 2.11 release notes](https://github.com/pytorch/audio/releases/tag/v2.11.0)

The versioned TorchAudio installation document still contains the older
single-version warning and a matrix ending at 2.6; retain that discrepancy.
The current installation document explains the stable ABI, and the release's
own notes support future-version compatibility. Do not infer Windows binary
success from either document.
[Current installation document](https://github.com/pytorch/audio/blob/main/docs/source/installation.rst),
[versioned document](https://github.com/pytorch/audio/blob/v2.11.0/docs/source/installation.rst)

The smallest useful next assignment is a metadata-and-source migration proposal,
not another attempt to install the rejected Torch 2.10 / Transformers 5.10.0
selection. Complete the missing records below, build an offline graph, and
produce the actual compatibility/loader diff. Ryan can then review specific
bytes and a bounded execution protocol.

| Component | Reference selection to investigate | Evidence already present; unresolved qualification |
|---|---|---|
| Python | Existing CPython 3.13 Windows AMD64 | Retain interpreter and platform; no migration is proposed. |
| torch | 2.13.0 | Captured non-yanked cp313 Windows wheel; satisfies the highest explicit fixed-version event in the retained Torch advisories. Native/runtime behavior untested. |
| torchaudio | 2.11.0 | Captured non-yanked cp313 Windows wheel; release notes support later Torch. Removed APIs still need source review. |
| torchvision | 0.28.0 | Captured non-yanked cp313 Windows wheel; its METADATA requires torch==2.13.0. |
| torchcodec | 0.16.0 | Captured non-yanked cp313 Windows wheel. Current upstream matrix says Torch >=2.11; the tagged README omits its own 0.16 row. Review stable-ABI release/build source and the packaged FFmpeg DLL path before accepting the combination. |
| transformers | 5.17.0 | Captured exact METADATA and published wheel record; exceeds all explicit fixed/last-affected boundaries in the retained five advisory groups. Requires tokenizers>=0.23.1,<0.24 and Hub>=1.5,<2. No current advisory clearance or API compatibility is implied. |
| huggingface-hub | 1.31.0 | Captured exact METADATA; requires hf-xet>=1.5.2,<2 on AMD64. WhisperX 3.8.6's <1 cap must be addressed in source packaging. |
| tokenizers | 0.23.2 | Captured non-yanked cp310-abi3 Windows wheel record; exact METADATA is missing. Faster-whisper 1.2.1's captured range permits this version. |
| whisperx | Local derivative of 3.8.6, version not finalized | Four Torch-family constraints and the Hub cap must change together, with source compatibility proved. 3.8.7rc1 removes the Hub cap but retains all four Torch-family constraints; it is not a complete solution. |
| hf-xet, typer | Not selected yet | Absent from the capture and current lock; select exact versions only after their metadata and transitive requirements are captured. |

Keep the remaining current pins initially. Preserve the accepted NLTK local
wheel and the existing Lightning repairs. Do not silently introduce Torch 2.14
or unrelated latest packages while solving this graph.
[TorchCodec compatibility matrix](https://github.com/meta-pytorch/torchcodec/blob/main/README.md#compatibility-with-torch-versions)

Transformers 5.10.4 is a smaller alternative to investigate if 5.17's API review
is materially larger. Its non-yanked wheel record already exists in the capture
(SHA256 8c5b99b141b53619435a76629b0284f04d27ff46d788b463fc0ecb23b8ff130e),
but its exact METADATA and source are missing. Do not reuse the yanked 5.10.0
metadata as a substitute. A web-tool attempt to read the 5.10.4 metadata URL was
refused as a non-retryable URL error; no payload was obtained and no dependency
download was attempted. The direct GitHub 5.10.4 release URL also returned 404;
neither result changes the saved PyPI release record.

The retained advisory comparison is a scope guide, not a new scan. Torch's eight
groups cover lstm_cell (fixed 2.10), jit.script (2.13), unpack_sequence (2.9.1),
three 2.9 fixes, pt2 loading (last affected 2.10), and weights_only (2.10).
Transformers' five groups cover attention configuration (5.3), Trainer RNG
loading (5.0 / rc3 alias discrepancy), LightGlue (5.5 / last affected 5.2),
chat-template paths (5.10), and X-CLIP conversion (last affected 5.0.0-rc0).
An ended affected range without an explicit fix is not independently verified
repair provenance. A local Torch 2.8 backport would need native source/build
provenance for these changes; a Python wrapper or version-label change cannot
establish their removal.

Collect these exact missing inputs next, using public software records only:

1. A fresh, separately sealed PyPI/PEP 691 snapshot for the reference selections;
   retain URL, retrieval time, non-yanked status, size, wheel hash and the
   PEP 658 METADATA hash. Fetch only metadata text. Obtain tokenizers 0.23.2
   METADATA plus hf-xet and typer release/metadata records, then recursively
   capture every newly required target. Preserve failed retrievals. The
   existing 304-file manifest must remain unchanged.
2. Version-bound upstream source for TorchAudio 2.11 stable-ABI/build setup and
   TorchCodec 0.16 loader/build setup, together with their release commit IDs.
   Capture Transformers 5.17 Pipeline, PipelineIterator, Wav2Vec2 processor/model
   loading and Hub 1.31 download/error APIs; compare them with the saved
   WhisperX 3.8.6 call sites. Capture the WhisperX packaging source and the
   3.8.7rc1 Hub change. Source files are sufficient here; no wheel execution or
   model files are needed.
3. Fresh advisory records for the proposed complete graph, with original alias
   groups retained, and upstream fix commits for the eight Torch/five
   Transformers groups. Tie those fixes to the selected release tags. Do not
   replace the raw 19-entry / 15-group historical result with this comparison.
4. A source-only inventory of removed TorchAudio APIs used by WhisperX,
   PyAnnote, torch-audiomentations and their import chains. Review the packaged
   FFmpeg shared-library compatibility and DLL containment against the new
   TorchCodec loader. PEP 508 success cannot cover these native/API contracts.

The implementation proposal must also close the unsafe default VAD load.
The current whisper_runner passes no alternate VAD. Saved PyAnnote source uses
weights_only=False and then selects a class from checkpoint metadata. This
happens before the diarization branch. Upgrading Torch or keeping speakers
disabled does not remove it. The saved Silero alternative uses torch.hub.load
with trust_repo=True and onnx=False, so switching that flag is not an acceptable
shortcut.

Scope the proposed source changes to a fixed, code-selected VAD architecture;
tensor-only weights and separately validated primitive configuration; explicit
local artifact manifests; no checkpoint-selected imports; and no fallback to
pickle or hub code. A conversion proposal may use the already approved model
only after Ryan authorizes that exact isolated operation. Do not assert which
globals or tensor shapes the checkpoint contains before observing them safely.

In the same proposal, replace the current any-file-means-cache logic with
complete required-file/hash checks. Passing local_files_only alone is
insufficient: the saved faster-whisper code separately downloads a missing
tokenizer. Account explicitly for that branch, PyAnnote/VAD files, alignment
downloads and missing Punkt data. Missing, partial, corrupt or substituted
artifacts must refuse before network or deserialization. Tests should use inert
loader/download recorders until model execution is separately authorized.

For Ryan's eventual decision, prepare these reviewable artifacts first:

- One complete exact graph and artifact manifest, with the two current
  source-only distribution exceptions handled explicitly. No unresolved
  dependency, missing target or unexplained yanked artifact.
- The complete source patch and local derivative version/hash, plus negative
  tests for no-consent partial caches, missing tokenizers, bad hashes, forbidden
  checkpoint classes and fallback refusals. No accepted test edit yet.
- An inert diff for the two frozen version assertions in
  tests/test_installer_dependency_lock.py: the current values are WhisperX
  3.8.6 and Torch 2.8.0. The proposed Torch value is 2.13.0; the WhisperX value
  must be the actual reviewed derivative version. Preserve all other behavior,
  notice-inventory and build-verification assertions. An exact final diff is
  premature while the derivative source and graph are incomplete.
- A fresh account/VM protocol using only hashed, explicitly approved synthetic
  audio and model artifacts, blocked runtime network, separate baseline and
  candidate exits, and predefined transcription/segment/chapter criteria.
  Freeze the utterances, expected text, timestamp tolerances and permitted
  deltas before executing either side. No diarization is included. Do not
  rerun the frozen navigation study or change its accepted inputs implicitly.

Independent retained-byte checks in this review: all 304 entries in
proof/runtime-graph-01-2026-09-12/SHA256.json match; all 13 saved source bindings
in proof/security-backport12-astra-review-2026-09-12/review/source-bindings.json
match. These are file-integrity checks, not product passes. The active runtime,
production source, accepted tests and release status are unchanged.
