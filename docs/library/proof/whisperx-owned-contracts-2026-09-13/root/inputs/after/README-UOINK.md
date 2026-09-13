# Uoink-owned WhisperX source proposal

This proposed 3.8.6+uoink.owned1 derivative supports only Uoink's owned,
non-speaker ASR integration. It is not an available or qualified runtime.
The process integration port is absent, so model loading refuses.

The owned runtime must supply an admitted local ASR snapshot, a fixed VAD
constructed from approved plain tensor state, a validated 16 kHz mono float32
waveform and admitted 80- or 128-band filter matrices. No model, filter NPZ or
other binary asset is included. Alignment, speaker attribution, Silero Hub,
automatic model loading, file decoding and the upstream CLI are unavailable.

The package metadata preserves the upstream Python range. Actual Uoink runtime
qualification remains limited to the separately reviewed CPython 3.13 Windows
candidate and has not occurred. The changed dependency declarations describe a
proposal; they do not establish binary or model compatibility.

The original README is retained in the source review as upstream reference,
not as a claim that its optional features are supported here. See
UOINK-NOTICE.txt and the unchanged BSD 2-Clause LICENSE for source attribution.
