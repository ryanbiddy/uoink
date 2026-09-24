# Tokenizer companion B2: first actual package build

The first local wheel build passed its byte checks on 2026-09-13 at checkout
`5d8292c174bc72f97c8656e1107ff68c959a07a7`. It is a packaging result only.
B2 has not been installed or accepted as part of the runtime. Website and
marketing remain paused.

The reviewed builder passes 62 synthetic cases in both the author and root
runs, with zero failures, errors or skips and actual exit zero. Its two prior
61-pass/one-fail attempts remain preserved: the first exposed a Windows ZIP
fixture normalization issue; the corrected fixture then exposed a real parser
gap. The final builder validates original ZIP names before accepting normalized
names. The bounded-read repair and all earlier bytes and reasons are retained.

Root read the real-build brief and complete launchers, bound the 21-payload
preparation seal, and invoked `py314-01` once. Python 3.14.6 ran with isolated,
no-site and no-bytecode flags. Child and outer exits were zero; the import,
network, process and file guard recorded no violations. All preparation inputs
remained unchanged. No package or model was imported, installed or executed.

The resulting `faster_whisper-1.2.1+uoink.localassets1-py3-none-any.whl` is
**1,387,859 bytes**, SHA-256
`d64027be41a352117199ecedfa1e9eed48d323140aa4e2c77065111f288b7883`.
All 16 members match the intended manifest and RECORD. The upstream license
and bundled ONNX asset remain byte-identical. ZIP decompression handled model
content only as opaque package bytes; no ONNX interpretation occurred.

The local artifact remains in `_scratch/b2-real-wheel-py314-01/artifact/`.
The durable proof contains receipts and source, not wheel or model payloads:
`proof/companion-b2-first-build-2026-09-13`. Its 132-payload manifest is
`a553c5264f19c08dd86d98fe56db4d9f19cee5bf471a8c1a79bf45f6c0cff9eb`;
the original 100- and 21-payload seals are preserved inside it.

Python 3.13 reproduction is pending a private stdlib-only runtime. The existing
embedded configuration enables site loading; neither that interpreter nor its
original configuration was used or modified. Quiescent path checks do not
provide atomic isolation from a hostile process with the same user access.

Production source is unchanged. The full-tree result at `56d9d4c` remains
2,796 passed, one failed and three skipped, plus 13 passed subtests. Runtime
compatibility and VAD security, signing, the historical AT6 receipt and verified
client isolation still prevent release acceptance.
