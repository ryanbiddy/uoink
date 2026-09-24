# Runtime security scope review — 2026-09-13

The proposed runtime remains blocked for release. The new OSV audit narrows the advisory matches for the uninstalled reference versions, while the source review identifies work still needed in asset validation, VAD loading and optional APIs. Neither collection establishes a compatible or safe installed runtime.

| Retained evidence | Exact result | Limit |
| --- | --- | --- |
| Candidate02 OSV audit | 144/144 pins queried; **1 raw advisory / 1 alias group**. Four HTTP 200 responses, zero failures, retries or returned pagination tokens. | Lightning 2.6.6 still matches inconsistent advisory metadata. Retain the raw match. |
| Separate upstream NLTK comparison | NLTK 3.10.3: **1 advisory / 1 group**. | Local 3.10.3+uoink.pathsec1 returned zero matches but has no PyPI release identity; this is no security clearance. |
| Candidate03 source capture | **39 source bindings:** 13 historical retained files, 12 local staged files, 14 upstream files. **19 successful requests**, five release commit bindings, zero retrieval failures or hash mismatches. | The local files are bound by hash, not newly verified release artifacts. Source inspection cannot qualify checkpoints or native behavior. |

The original audit remains **19 raw entries / 15 alias groups**. The new candidate counts do not revise it. Candidate02 graph01 remains failed with five WhisperX cap conflicts; candidate03 did not produce or accept a replacement graph. Its name identifies the source-review evidence, not an installed successor candidate.

The source review records these runtime release blockers:

1. **Replace unrestricted default VAD loading.** The captured default route reaches `pl_load(..., weights_only=False)`, checkpoint-selected code and another unrestricted load even when diarization is off. It needs a reviewed loader with a validated artifact and fixed architecture. Switching to the captured Silero wrapper would invoke remote `torch.hub.load(..., trust_repo=True)` and does not resolve the issue. Checkpoint contents and conversion viability remain unknown.
2. **Validate the complete asset set before execution.** An arbitrary cache file can currently satisfy readiness. Require a versioned manifest, approved revisions, hashes and contained local paths before constructors or download helpers. In particular, missing tokenizer files must fail before CTranslate2 construction and the separate `Tokenizer.from_pretrained` fallback. Cache-directory selection alone does not enforce offline use.
3. **Repair or exclude incompatible optional paths, then qualify the dependency changes.** The inspected faster-whisper `output_dir` branch passes a removed Hub keyword; file augmentation calls the absent `torchaudio.info`. These observations do not prove default transcription fails. Any retained decoder adapter also needs metadata, sample-boundary and resource-limit checks. Common Pipeline and PyAnnote decoder interfaces remain present in the inspected text, but focused contracts and native checks are still required.

The speaker gate stays blocked. Alignment branches need one explicit approved-asset policy before any later authorized trial. No diarization, model execution, runtime trial, product tests or installation occurred in these two evidence tasks. No changed dependency declarations or inert source proposal is accepted by this review.

Evidence is materialized in [the runtime security proof directory](proof/runtime-security-scope-2026-09-13/README.md). It retains **31 OSV payloads and 68 source payloads**, their original manifests under distinct names, both detailed review reports, collectors, read-only verification inputs and results. [The OSV review](proof/runtime-security-scope-2026-09-13/reviews/RUNTIME-CANDIDATE02-OSV-REVIEW-2026-09-13.md) explains the Lightning metadata disagreement and local NLTK uncertainty. [The source review](proof/runtime-security-scope-2026-09-13/candidate03-source/REVIEW.md) gives captured paths and line numbers for each finding.

The original OSV manifest SHA-256 is `f6378453d1bc9ea432793b33ea6e2aa108b5ce868a740f9df9e79c3d79e29bf5`; the source manifest is `00dee8e9ecbbc0b187c3884349e2374ae90447f88c28bcd1a01fba10fdec32f3`. The new root manifest binds the documentary copies. Hash verification establishes byte preservation; parent review and the required repairs remain prerequisites for release.
