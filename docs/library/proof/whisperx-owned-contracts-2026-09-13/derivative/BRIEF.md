# Owned WhisperX source repair — 2026-09-13

Prepare a source-only patch for the shipped non-speaker ASR path. The captured
WhisperX loader otherwise constructs its default VAD through unrestricted legacy
checkpoint loading, and the Silero alternative invokes Torch Hub. File audio,
alignment and diarization also expose paths outside the proposed owned runtime.

Use only existing captured text. Preserve exact before bytes and their distinct
provenance: release-commit-bound pyproject.toml versus retained installer Python
source. Inventory the missing distribution and import inputs before calling any
derivative complete. Do not read model, wheel, storage or NPZ contents.

The draft will require a preconstructed owned VAD, a trusted local ASR snapshot
admitted by the separate resolver/lifecycle adapter, and finite bounded mono F32
waveform input. Refuse default VAD construction, remote/fallback loading,
alignment, diarization and automatic decoding. Keep the six Uoink model choices
in the external resolver; do not reduce them to one model. Preserve the existing
Pipeline initializer bypass and its generator route.

Reconcile the five proposed dependency caps and the duplicated TorchCodec uv
override against the captured pyproject. Bind the B3 faster-whisper derivative
in this draft. The local WhisperX version, build recipe, complete asset/member
manifest and final compatible graph remain unresolved; this is not an approved
package or replacement lock.

No imports, tests, builds, execution, downloads, installation, source integration,
frozen-test changes or owner-gate changes are authorized here. Root reviews the
text and chooses any later inert qualification. Record exact remaining interface,
asset, import and native-lifetime gaps rather than asserting runtime acceptance.
