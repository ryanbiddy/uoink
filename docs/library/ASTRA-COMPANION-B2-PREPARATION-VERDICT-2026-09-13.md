# Tokenizer companion preparation: B2 review

B2 qualifies the selected constructor behavior in ten synthetic contracts.
It remains an unapplied source derivative. No complete dependency module,
tokenizer parser, CTranslate2 model or wheel ran in this qualification.

B1 moves local-file and supplied-buffer tokenizer parsing ahead of native model
allocation, and refuses missing local-only tokenizer files before allocation.
The explicit nonlocal fallback remains. Its first protocol had one baseline
pass and five failures; the derivative passed six cases in author and Astra
runs. Those results and exact inputs are preserved.

Gemini's later empty-buffer finding exposed a B1 boundary: `b''` was treated as
absent. B2 changes that condition to `is not None`. The four new cases cross
local-only true/false with ambient tokenizer-file presence. B1 now records six
passes and four failures on the expanded protocol. Both B2 runs pass all ten
with zero failures, errors or skips and actual exit 0. Their case IDs, source
and protocol hashes match. These are two runs of ten distinct contracts.
Original six assertions and all accepted product tests are unchanged.

The exact B2 source SHA-256 is
`bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d`.
The aggregate raw patch retains its line-ending difference; a separately
labeled normalized patch shows the logical changes. Neither was applied to
the checkout, staging or an installed runtime.

The distribution plan binds the locally captured upstream faster-whisper 1.2.1
wheel and MIT license, proposes version `1.2.1+uoink.localassets1`, and specifies
exact changed members, notice, metadata and RECORD. Its original plan and B2
addendum remain separate and immutable. The bundled ONNX member's declaration
comes from captured RECORD metadata; this preparation does not establish its
decoded payload or model behavior.

The archive includes the 67-payload original review, 52-payload distribution
plan and 70-payload B2 review with their original seals. The next task is a
reviewed deterministic builder with synthetic ZIP tests, then the exact
runtime and compatibility proposal. This verdict approves no wheel build,
installation, model execution, dependency-test change or market release.
