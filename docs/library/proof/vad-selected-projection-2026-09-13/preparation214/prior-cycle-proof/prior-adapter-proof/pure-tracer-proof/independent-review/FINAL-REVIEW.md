# Independent review: pure symbolic metadata tracer

2026-09-13. Astra read-only source and receipt review. **No remaining blocking defect found for the bounded, synthetic-qualified bytes-to-symbols function.** This verdict does not approve an artifact adapter, an actual checkpoint trace, conversion, model loading or inference. The reviewer ran no tests and opened no checkpoint.

Reviewed tracer SHA-256: `f41ce88a2eceee565fcc9116e19f064723bf3339ffe4ca8669ae20bff6033127`. The executable logic matches the initial reviewed draft; the sole tracer revision makes its interpretation limit explicit. It preserves a final literal-container reference graph and per-object tagged operation order. It cannot reconstruct historical argument snapshots or evaluated constructor/BUILD state. No GLOBAL resolution, reducer call, class construction, persistent-storage resolution, file/network access or tensor operation was found in the tracer source.

The implementation retains the specified 31-opcode grammar, exact protocol/STOP/root/stack conditions, duplicate memo/key refusal, bounded primitive types, full-graph cycle/depth checks and resource limits. Tagged reducer/new-object mutations remain instruction records. Whole-graph validation includes omitted training nodes. Tensor descriptors preserve storage, offset, size, stride, requires-grad, hooks and optional metadata references while explicitly declining tensor/storage validation. These support review of declared static structure, not trusted architecture, interpreted legacy object semantics or runtime compatibility.

| Actual worker attempt | Independently checked raw outcome | Qualification interpretation |
| --- | --- | --- |
| `symbolic-preflight01` | 56 passed, 1 failed; reader exit 1; 0.007994 s | Failed synthetic run retained. The missing-MARK fixture inherited a wrapper MARK and reached a different valid refusal. The required startup environment binding was also absent. |
| `symbolic-preflight02` | 57 distinct passed cases, 0 failed; reader exit 0; 0.007474 s; empty stderr | Corrected fixture result retained. It still lacked the required explicit native-startup environment binding and does not establish that condition. |
| `symbolic-preflight03` | 57 distinct passed cases, 0 failed; reader exit 0; 0.007592 s; empty stderr; zero target side effects | Fresh launcher sets `IG_FORBIDDEN_LIVE` before Python; the child asserts exact string equality without reading the path. The raw assertion flag is true. All 57 behavioral cases and tracer logic are unchanged. This is the qualifying synthetic attempt for the stated startup condition. |

The PowerShell launchers return the captured reader exit. Preflight03 records matching source and harness hashes before and after execution. It uses `-I -S -B`, scrubs provider variables, and installs an in-harness audit hook before importing the tracer. This establishes the recorded test setup; it is not a general OS sandbox or native-runtime security qualification.

The author preserved three review-driven corrections with before bytes and reasons: the original two-byte missing-PROTO input was separated from the protocol test before execution; the missing-MARK wrapper was corrected after preflight01 without changing its assertion; and the startup binding was added after preflight02. No failed result was relabeled. The tracer was not broadened to satisfy these cases.

Preflight03 harness SHA-256: `31f470f73f1712d87084bb319d4f86ae8ec9354be8b62e0d397b0ef73cfee271`.

Preflight03 raw result SHA-256: `f4d9d050b38c16cb7cff7a6416d8f8dd0bdec2d3b6b5c6e20e56a61fd995c4f1`.

Preflight03 launch receipt SHA-256: `a41f280d59b61afb413b408b40d3de351b4a6eeb5d2cc8b8715881093f01d700`.

The separate adapter must still receive exact source review for fixed path/hash, ZIP/member extent, payload size/CRC, bounded read, fresh output and honest refusal behavior before root considers any actual trace. A real-input cycle or unsupported form must remain a refusal under this grammar. Static declared values still need a source/provenance review before becoming fixed loader constants.

The original fixed-loader proposal's 38 payload hashes were rechecked with zero mismatches. Its manifest remains `129773fb33e4ec94a4e217373064d6d55de68d1db71f299a2372a91be1a76403`; the run04 addendum remains `7fb48cbd57d479d24e127374edc834baf4a91b149a0889110adeb12b3b6e18b8`. This review changed neither original evidence set, product source, accepted tests nor git state.
