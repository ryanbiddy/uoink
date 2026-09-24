# Protected constructor source review: failed

Gemini run `e6133b1f-fc8e-4f78-b252-1fae0659ef5e` completed its transport at
`ba1e30/exit0`; its source is not accepted. The 13 proposed tests were not run.
The worker used `gemini-3.8-flash-high/high` through the existing Antigravity
subscription, from base `793fe12`. No production source changed.

Astra reviewed the six delivered deltas, new engine, complete proposed tests
and report against the selected baselines. These findings prevent admission:

| Finding | Consequence and required repair |
| --- | --- |
| `owned_asr_engine.py` checks VAD/namespace ownership before entering the required serial engine operation. | Ordinary construction refuses; wrapping it in an existing operation makes its later nested operation refuse. Put all checks and construction inside one owner operation. |
| `connect_engine_before_construction` retains only an attempted flag; registration occurs after fallible constructors. Quarantine retains namespace/VAD/error, and retirement clears the engine record without confirmed retirement. | Partial model/pipeline ownership can be lost. Retain an attempt and every returned object before the next fallible step; preserve them through revocation and uncertain cleanup. |
| Namespace issuance accepts duck-typed adoption/namespace objects and caller-supplied digest text. The unchanged adoption validator still supports only the generated five-file fixture. | No authenticated real-model namespace connection exists. Keep that path closed; exact retained adoption and bootstrap issuance must precede any later constructor authority. |
| The private WhisperX entry accepts an arbitrary runtime/files map, does not require the fixed VAD type, and permits empty preprocessor bytes. | Runtime substitution and the companion's path fallback remain possible. Bind the fixed private entry and immutable namespace; prove no-path construction separately. Four-file refusal itself is honest partial behavior. |
| `build_factory_product` replaces its unconditional generated-namespace check with an `if/elif` lacking an `else`. | With neither namespace, factory work starts before later registration refuses. Preserve refusal before any constructor activity. |
| New tests use incorrect Win32 fake argument offsets, an incompatible fake factory type and an unregistered VAD. One negative fixture fails before its intended assertion; the positive bypasses the new private WhisperX entry. | They cannot establish the claimed boundaries. They also import a heavy module directly, so they are not admissible under the guarded loader as written. Repair new fixtures without changing accepted tests or weakening behavior assertions. |
| Input map and prose overstate the delivered implementation. | Passive audit `e13803/0` finds 5 incorrect rows among 32: two byte counts and three missing paths. Passive `e82f70/0` finds invalid hunk counts in 5 of 6 diffs. The report's token, VAD and early-ownership claims do not match source. Generate maps/diffs mechanically from actual files. |

The suggested B3 `files` conditional is also outside that method's scope. Do
not apply it or modify the accepted companion. Fixed CPU/int8 policy, bounded
options, four-file feature handling and actual constructor closure remain open.

The original 22 delivered files, source pins, input-map audit, diff-header audit,
full Control Room database record and recorded command events are preserved.
The final outer tool output was truncated; its exact truncated object remains,
alongside the separate original database export. It was not reconstructed.
Eight recorded commands inspect source, hashes or Git; none starts Python or a
candidate/native/model operation. This run does not inherit the earlier run's
ambient-Python violation.

Follow `PROTECTED-ENGINE-OWNERSHIP-REPAIR-BRIEF-2026-09-14.md` for the first
smaller repair. Caller and completion-info work proceeds independently. D1/D2
remain complete; no checkpoint/output reread, runtime, release or market
authority follows from this source review.
