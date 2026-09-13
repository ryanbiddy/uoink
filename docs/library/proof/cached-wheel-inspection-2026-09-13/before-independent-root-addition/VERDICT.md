# Existing ANTLR and proxy-tools wheel inspection — 2026-09-13

Inspection02 verified both existing wheels against their historical complete-file hashes. ANTLR 4.9.3 has 61 members and 479,266 expanded bytes; proxy-tools 0.1.0 has 5 members and 7,432 expanded bytes. Every member matched RECORD. The inspection took 0.04581079998752102 seconds, with native, launcher and actual outer exits 0, no audit denials and all 28 preparation inputs unchanged.

| Artifact | Wheel bytes | Observed SHA256 |
|---|---:|---|
| `antlr4_python3_runtime-4.9.3-py3-none-any.whl` | 144,613 | `d50ab331bff062b5e7f74e19fb16a2e891a47e893d805bcdbff8e6e6beb09c37` |
| `proxy_tools-0.1.0-py3-none-any.whl` | 2,943 | `a049f8570f5ce89b723ba282b90291ac3aa1fdcbd7d7100426ff659447400c68` |

The observed METADATA is 418 bytes / `d1de5c7416841a56a3d73795e7f30587c2b8f3ba01fbbff68c094e308c629e7d` for ANTLR and 527 bytes / `34f8db57e46ca03c6185c649a15cc52a0c9120f4f781e9b64701044b22a7fc86` for proxy-tools. Neither supplies a Requires-Python field. Retain that absence; it is not a declared compatibility guarantee. The metadata claims BSD and MIT respectively, but neither wheel includes a license-text member. Complete redistribution notices remain open.

ANTLR includes exactly one script outside its package/dist-info roots: `antlr4_python3_runtime-4.9.3.data/scripts/pygrun`, 6,275 bytes, SHA256 `19e5db997a20d119517c06c855cf5a09e0edce61268d81faa5c26f50cc844868`. The receipt retains its text. Root read it and identified intentional dynamic imports of a user-named lexer/parser from the current directory. No execution or installation was approved by this inspection. It is not evidence that arbitrary CLI invocation is safe.

Inspection01 remains REFUSED with `Unexpected package root`, zero accepted wheel results, native/recorded launcher 2 and nested outer tool 1. The separate names-only diagnostic identified the exact script; inspection02 then admitted only that path as inert UTF-8 text. Both raw histories, the narrow repair and the outer-exit correction remain preserved. No failure was relabeled as a pass.

Historical origin and build records match the exact selected sdists and observed wheel pins. Those records are distinct from publisher authentication or a reproducible build. The new byte result can support a separately reviewed five-local-record metadata graph. A later graph invocation must report no artifact verification in that invocation and must not invent public wheel URLs. No new download, build, installation, package import or model execution occurred during these inspections or this documentary copy.
