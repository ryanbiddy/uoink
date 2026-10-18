# Static VAD evidence and fixed-loader preparation

The bounded static inventory is complete. It identifies the legacy checkpoint's
archive structure and instruction literals without constructing objects or
tensors. The default VAD security defect remains open; no replacement loader,
converted model or runtime has qualified.

All four inspections concern the same 17,719,103-byte staged artifact, SHA-256
`0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`.
Runs 01 and 02 refused before inventory with reader exit 2; the outer process
reported 1. The reviewed narrow ZIP-version compatibility change allowed run03
to finish with reader and outer exit 0. Run04 added a bounded tail sample and
also finished with both exits 0. Those earlier refusals stay recorded.

The archive has 131 members. Only the 21,882-byte `archive/data.pkl` payload
received separate CRC validation and opcode parsing. Other member bytes were
included in the whole-file hash but were not extracted into tensors. Protocol 2
contains 17 GLOBAL literals, 160 BINPERSID, 327 REDUCE and nine each of NEWOBJ
and BUILD. Those names were recorded as data; no referenced callable ran.

Run04's literal tail names PyanNet and its configuration fields. This supports
a factory hypothesis, not verified metadata associations, tensor shapes or
trusted provenance. The fixed-loader proposal therefore leaves unknown
configuration and schema fields unset and refuses its draft manifest. Its
source-bound route avoids checkpoint-selected classes and unrestricted-load
fallbacks. It is preparation, not an implemented security repair.

The inventory archive retains the original failed 31/2 synthetic run, repaired
36/0, reporting 45/0 and compatibility 89/0 results. Tail qualification records
17 passing checks. Raw readers, briefs, repairs, measured exits and all nested
seals are preserved. No accepted product tests were edited. This documentary
integration copies existing evidence only; it performs no checkpoint read.

Proof directories are `proof/vad-static-inventory-2026-09-13` (80 payloads),
`proof/vad-static-metadata-tail-2026-09-13` (29 payloads) and
`proof/vad-fixed-loader-proposal-2026-09-13` (the original 38-payload proposal
and its immutable seal, run04 addendum and transport wrapper).

The next bounded task is a reviewed symbolic metadata adapter to recover
declared associations and tensor descriptors as inert records. Provenance,
conversion and isolated runtime qualification remain separate decisions.
Nothing here approves model loading, release, website work or marketing.
