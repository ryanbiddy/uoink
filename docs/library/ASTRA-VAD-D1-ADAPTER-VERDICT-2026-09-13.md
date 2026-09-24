# D1 static inspection adapter review

2026-09-13. Accept the concrete adapter and its synthetic qualification as
preparation for a separate owner decision. Real inspection remains disabled.
Both author and Astra independently passed the same 54 cases, with zero
failures and qualification/native/outer exits 0. Author time was 0.038318 s;
Astra time was 0.037597 s. All eight inputs remained unchanged, stderr was
empty, and no unexpected audit event or trapped conversion call was recorded.

Adapter SHA-256 is
533c8abee9a9eea503e444166edf8acca07fc9d5c01b34626b44f957969c6649.
It uses the unchanged converter's bounded stored-ZIP parser and the unchanged
buffer comparator. It verifies immutable snapshot size/hash before parsing,
all 131 names/sizes/CRCs, and the expected version gate. Only two 500-byte
buffers and two version bytes are interpreted. Other members, including
pickle, remain opaque during whole-file hashing and CRC checks. No conversion,
tensor, checkpoint-selected import or model call is available through D1.

The proposed real input is fixed at 17,719,103 bytes and SHA-256
0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea.
Its inventory comes from the retained safe JSON receipt. No actual artifact
was reopened for this work. ASCII `3\n` remains an expected source prediction,
not a measured version. A mismatch refuses before buffer comparison and
does not report a false observed match. The fixed eight-ULP comparison must
accept exactly one orientation for all 250 words; it does not authenticate
the historical writer or establish the encoding of the other 127 storages.

The 54 cases exercise generated full-schema archives, both byte orders,
malformed profiles and ZIP structure, selected/opaque corruption, overlap,
version mismatch, inconsistent buffers, output/deadline refusal and an
unexpected-error exit. The approved real filesystem branch was not exercised:
the wrapper test stops at absent approval and traps its first path helper.
Source review covers the fixed paths, ancestor checks, bounded snapshot and
exclusive output. Quiescent private paths remain necessary; cooperative clocks
cannot interrupt blocking I/O, and the Python guard is not an OS sandbox.

`D1_OWNER_APPROVAL` and converter `REAL_PROFILE` remain None. A D1 consistency
result would still require review before a separate D2 conversion decision.
Neither orientation activates conversion. Notices, actual converted identity,
native/import/value checks and runtime qualification remain open. The original
symbolic cycle refusal and all earlier failed measurements remain unchanged.

The [proof seal](proof/vad-d1-adapter-2026-09-13/SHA256.json) contains 53
payloads, including both raw runs, original drafts, the pre-test wrapper-clock
repair and the clarification of audit scope. This adds no complete-tree,
installed, market-readiness, website or marketing acceptance.
