# Fixed VAD converter: synthetic qualification

2026-09-13. The converter produced deterministic Safetensors bytes for the complete fixed 54-entry plan and passed **82 synthetic cases, 0 failed**, in **2.147786 seconds**. The native process and qualification exits were both **0**, stderr was empty, all five copied input hashes remained unchanged and the audit reported no unexpected file/import/network/native events.

This qualifies the recorded synthetic checks. **No real checkpoint or storage member was read, no model or tensor was constructed, and no real protocol profile is accepted.** The original artifact's strict symbolic cycle refusal is unchanged. The converter's real guard was tested only as an invalid call with its path helper replaced by a trap; it refused before reaching that helper or any filesystem operation.

| Input | SHA-256 |
| --- | --- |
| fixed_converter.py | `b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b` |
| zip_bounds.py | `bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6` |
| fixed-plan.json | `37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf` |
| qualify_converter.py | `11f9addddf9b349c4ee249c000cc60c4986b989de2e11ec990ba940d6b7949a9` |
| reviewed_zip_reader.txt | `67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5` |

The converter accepts immutable bytes only after checking an explicit profile's byte count and SHA-256. The fixed plan has a separate compiled-in digest. It validates stored ZIP central/local records, ZIP64 metadata, supported descriptors, exact names and inventory, nonoverlapping physical spans and every member CRC. Pickle content is opaque. Only the 23 fixed storage members pass through the finite binary32 word check and range copier. The 32 LSTM views remain explicitly associated with shared storage key 16; the output materializes their distinct reviewed ranges without casts or shape/key changes. Both filterbank buffers remain present.

The output has deterministic sorted tensor names, an 8-byte little-endian header length, bounded padded JSON, dense F32 data and complete contiguous offsets. Its format follows the upstream textual reference recorded in FORMAT-REFERENCE.md. This proposal adds finite-value rejection and tighter size limits; it does not use the Safetensors package or qualify that package's native reader.

The 82 cases cover full per-entry byte/header round trips and all shared-storage offsets, determinism, finite edge bit patterns, inert malicious/non-pickle bytes, opaque nonfinite bytes in an unselected member, supported descriptor/ZIP64 variants, the narrow stored-version-zero grammar, padding, wrong profiles/hashes/sizes/versions, fixed-plan mutations, invalid keys/ranges/strides, CRC failures, local/central mismatches, overlapping members with recomputed CRC, duplicate/unlisted/escaping names, wrong storage lengths, infinities/NaNs, archive gaps/trailing bytes, directory and output bounds, final deadline expiry, and mocked ancestor checks. AST comparison verifies the two extracted ZIP-boundary functions against the retained reviewed source. The import check permits only the listed stdlib modules and ZIP helper.

The path cases use synthetic lstat results only. The corrected wrapper checks the full chain from volume anchor to leaf. A quiescent private input/output directory remains necessary; the stdlib checks are not a claim of protection against hostile concurrent Windows path replacement. Its time bound is cooperative and cannot interrupt a blocking filesystem call. An incomplete or overdue output write remains unaccepted and requires a fresh name for a later documented attempt.

## Preserved attempts

| Label | Actual outcome | Reason and subsequent action |
| --- | --- | --- |
| converter-preflight01 | Native exit 1; no cases ran | Import-loader file request was outside the five-file audit allowlist. Keep the refusal. The next setup compiled only the two already-read implementation modules from their known bytes; the file guard stayed closed. |
| converter-preflight02 | Native exit 1; no cases ran | Lazy import of the standard UTF-8 BOM codec hit the closed import allowlist before the case loop. The next setup preloaded that exact stdlib codec. |
| converter-preflight03 | 82 passed / 0 failed, native and qualification exit 0 | Explicit `IG_FORBIDDEN_LIVE` startup binding, `-I -S -B`, scrubbed provider environment, no unexpected audit events. |

The two setup repair notes, all three raw directories, original harness drafts and first converter drafts are preserved. No converter behavior assertion was weakened between attempts. The dormant wrapper's deadline and ancestor checks were repaired under written notes before the first attempt; its source stayed unchanged across all three runs.

The real route remains closed pending pinned archive/version and scalar byte-order evidence, explicit conversion/profile review, an approved storage-sharing bridge, exact new artifact bytes/hash and provenance, and a qualified target runtime/native reader. The metadata mapping and fixed factory remain unchanged. No production, acceptance-test, installed, website or release status changed in this task.
