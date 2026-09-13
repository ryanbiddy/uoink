# VAD publisher identity verified; conversion remains held

2026-09-13. Accept the public metadata association in
`proof/vad-public-provenance-2026-09-13/REPORT.md`. The historical
`pyannote/segmentation` revision `c4c8ceafcbb3a7a280c2d357aee9fbc9b0be7f9b`
(2022.07) advertises the exact size and SHA-256 already recorded for the
bundled VAD model: 17,719,103 bytes and
`0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`.
WhisperX's hash-checking source and unchanged Git blob history corroborate
the distribution association. Astra checked the retained historical API
response and report; all 88 sealed payloads must match disk and Git before
this verdict is committed.

This closes the unknown upstream-model identity item. It does not authorize
conversion or redistribution. The historical API labels the model MIT and
gated `auto`; the complete historical card/notice request returned HTTP 401.
That refusal remains. A separate Astra web-tool open of the historical HTML
card returned a URL-safety/InternalError without content; it is outside the
collector's 24-request receipts and adds no license evidence. No access
condition was accepted and no binary or model payload was downloaded.

The retained PyTorch 1.10 writer source copies raw storage bytes. It does not
establish the original writer's byte order. Its default format predicts
`3\n`, but the artifact's two version bytes have not been read. Keep both
facts separate from measured artifact data. The original symbolic cycle
refusal remains exit 2; selected metadata is still a partial diagnostic.

Next: finish the synthetic converter review, establish an explicit reviewed
byte-order/version basis, and prepare the exact migration protocol. Actual
conversion, a trusted new artifact manifest, native reader/model equivalence,
runtime compatibility and installed acceptance remain open. The complete
tree is still 2,796 passed / 1 failed / 3 skipped, plus 13 passed subtests, at
`56d9d4cf11f20ff4448b21db172dbf217d02c6d6`. Website and marketing remain held.
