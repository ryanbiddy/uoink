# Cached dependency wheel verdict — 2026-09-13

Astra accepts the byte inspection of the existing ANTLR 4.9.3 and proxy-tools
0.1.0 wheels. Their whole-file hashes match the retained historical build
records, and all 61 and five members respectively match their RECORD entries.
Root independently verified every member using .NET, without extraction,
installation, package imports or script execution.

| Wheel | Bytes | SHA256 |
|---|---:|---|
| antlr4_python3_runtime-4.9.3-py3-none-any.whl | 144,613 | d50ab331bff062b5e7f74e19fb16a2e891a47e893d805bcdbff8e6e6beb09c37 |
| proxy_tools-0.1.0-py3-none-any.whl | 2,943 | a049f8570f5ce89b723ba282b90291ac3aa1fdcbd7d7100426ff659447400c68 |

Inspection02 takes 0.04581079998752102 seconds inside the inspector. Actual
tool b42903, native interpreter and launcher all exit zero; all 28 preparation
inputs remain unchanged and guards record no denial. Root verifier 4ea139
also exits zero after checking both complete artifacts, all ZIP/RECORD members,
selected text and every preparation input before and after the inspection.

Neither wheel includes a license-text member or declares Requires-Python.
METADATA claims BSD and MIT respectively; complete redistribution notices
remain open. The missing Python field must remain absent in the graph, without
inventing a supported-version claim. ANTLR's retained 6,275-byte pygrun script
intentionally imports a user-selected lexer/parser from the current directory.
It was read as text and has not been admitted as a runtime entry point.

Inspection01 remains REFUSED: unexpected package root, zero accepted results,
native and recorded launcher exit 2, nested outer tool exit 1. The names-only
diagnostic found the exact pygrun member; the documented repair admitted only
that member as text in a fresh inspection02. The historical source claims
and build records do not establish publisher authentication or a reproducible
current build. Both histories and all preparation corrections are retained.

The documentary copy, actual tool 68cbaa exit zero, preserves 72 original text
files. Its 88-payload proof contains 4,641,374 bytes under
`proof/cached-wheel-inspection-2026-09-13`; seal:
8a6a252489696a873db21e45c5abcfa2d1b5dae14548591ca7be58e7370c69c2.
The two-payload `proof/cached-wheel-integrator-2026-09-13` preserves the actual
sealer result. Root index check a52b7c verifies all 90 payloads against disk
and Git. No archived code or test was executed while sealing.

The next step is the exact five-record metadata graph. It must retain null
public URLs and report no artifact verification in that later invocation.
Native compatibility, complete notices, the current installer and market
approval remain open. Website and marketing stay paused.
