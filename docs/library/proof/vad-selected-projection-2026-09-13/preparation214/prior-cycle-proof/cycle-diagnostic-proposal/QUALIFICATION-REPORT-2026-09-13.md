# Reference-cycle diagnostic qualification

The first fresh synthetic run completed 36 passed, 0 failed in 0.066185
seconds, with actual qualification exit 0 and the forbidden-live startup
binding asserted. Source and harness hashes remained unchanged. No actual
checkpoint or real reader input/output path was used by this qualification.

The integrator independently reviewed the full 36-case harness and ran
copies of all five pinned source files in `_scratch/astra-cycle-diagnostic01`.
That run completed 36 passed, 0 failed in 0.063306 seconds, actual
qualification exit 0, with unchanged hashes and explicit startup binding.
Its raw receipts, source copies, wrapper and wrapper generator are included
in the fresh proof. This second run also used synthetic data only.

Source SHA256:
`15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd`.
Harness SHA256:
`f76fa88e58bba46130c2b8d44c7d17543ff46334c73976adb138efa0fa169f6a`.

The 36 cases consist of 23 unchanged prior adapter behavior/boundary checks,
one reporting-scope AST normalization, and 12 focused witness checks. The
old assembly predicate remains historical and is not relabeled as passing.
AST normalization checks code outside the designated diagnostic blocks;
the new blocks rely on independent source review and focused behavior tests.

The witness preserves the exact first gray-edge refusal. It reports only
bounded node IDs/kinds, actual edge occurrence indices, fixed roles, and a
direct active-path entry category where available. Tests cover self-loops,
two-node cycles, parent-field roles, duplicate-occurrence helper behavior,
long-prefix truncation, the byte cap, unavailable entry context, selected
aliases, omitted-name privacy, diagnostic-generation failure, absence of
graph output after refusal, and refusal context in the inert main wrapper.

The 12-node path prefix and separate closing edge do not imply a connection
through omitted prefix nodes. Root-entry categories describe one observed
DFS path and are explicitly nonexclusive: an alias may connect the same
cycle through a different selected root. A root self-loop conservatively
reports unavailable entry context. The witness emits no arbitrary keys,
values, GLOBAL names, object fields or class classifications. A parent-field
role is a literal structural observation, not evaluated object semantics.

The diagnostic alone cannot establish an OmegaConf class, safe model loader,
architecture, configuration, provenance, tensor compatibility or release
acceptance. It preserves whole-graph cycle refusal, all existing grammar
and resource bounds, the fixed hash/path and ZIP/CRC checks, and the final
256-KiB receipt cap. The diagnostic has its own 4,096-byte compact JSON cap;
generation failure or truncation never turns refusal into acceptance.

The earlier integrator `symbolic-run01` remains refused: actual reader and
outer exit 2, `Reference cycle refused`, 0.035824 seconds. Its saved receipt
records 17,719,103 artifact bytes, SHA256
`0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`,
and 131 ZIP members. It produced no accepted symbolic graph. This report
uses the saved receipt only; this agent has not reopened the checkpoint.
The completed 108-payload proof and every earlier failed/refused outcome
remain unchanged. A new actual diagnostic requires the integrator's exact
source review and a fresh labeled run.
