# B3 packaging evidence verdict — 2026-09-13

The recorded B3 builds qualify the exact local wheel's byte construction and
reproduction. Python 3.14.6 and the existing private Python 3.13.15 each produced
`faster_whisper-1.2.1+uoink.localassets2-py3-none-any.whl`, **1,388,022 bytes**,
SHA-256 `97bdde2d33fe71660b4cf8a318853e2e1b647ad900918e7e24397990162f29e4`.
Both child exits, launcher return codes and independently recorded outer exits
are 0. Guards are valid, inputs unchanged, and the second run records the private
34-file runtime unchanged and exact byte equality to the first output.

This review read source protocols and text receipts only. It did not open or
rehash a wheel/runtime/model, repeat either build or independently execute the
model package. The reviewed protocols bind the exact upstream wheel, the
16,660-byte builder `f25530a3…b81892` and all five B3 recipes. The first command
records its measured output. The second requires that measured hash/size,
verifies the first receipt/preparation seal, and compares actual output bytes.
The runs used fresh directories and epochs 1 and 2000000000, respectively.

Both receipts and provenance records report all 16 output members and complete
RECORD/manifest validation, deterministic ZIP metadata, unchanged opaque asset
and MIT license bytes, no heavy imports and no guard violations. Their member
identities match the sealed B3 recipe. The wheel contains the unchanged B2
tokenizer constructor repair plus the reviewed one-line Hub keyword removal.
The combined synthetic proof preserves worker and root runs of the same
**68 cases each**, all passing with zero failures/errors/skips.

The first actual receipt still says `PENDING_B3_REPRODUCTION`, exactly as recorded
before the second run. The separate second receipt says `BYTE_IDENTICAL`; that
later measurement resolves the packaging comparison without rewriting history.
Recipe member rows also retain their original proposal-era `basis` descriptions
inside provenance; those describe the input recipe's origin. The subsequent
build status, member validation and comparison are recorded separately.

The archive preserves the original combined95 and preparation32 seals unchanged,
root's decision, both raw result/command/console/provenance/outer-exit sets and
this text-only consistency review. It contains no wheel, model or runtime binary.
Older B2/Hub archives remain separate immutable references, not nested payload
trees. No production, handoff, dependency, frozen-test or staging file changed.

This accepts the packaging evidence for root integration. It does not establish
full-module/model-stack compatibility, actual Hub I/O, advisory clearance,
installation safety, distribution/migration approval or market readiness.
The bounded reads and file identities require quiescent paths and do not form
an operating-system security boundary. Those runtime and release decisions
remain separate from successful wheel construction.
