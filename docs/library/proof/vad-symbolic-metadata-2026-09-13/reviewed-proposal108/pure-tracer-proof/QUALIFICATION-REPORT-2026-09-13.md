# Pure symbolic tracer qualification

The isolated, synthetic-only `symbolic-preflight03` completed with 57 passed,
0 failed and actual reader exit 0 in 0.007592 seconds. Its launcher set the
forbidden-live environment binding before Python startup; the child asserted
that exact string without accessing the named path. No target side effects,
checkpoint opens or model imports were recorded. This qualifies the tested
pure tracer boundary. It does not qualify an artifact adapter or a model.

Reviewed and executed tracer SHA256:
`f41ce88a2eceee565fcc9116e19f064723bf3339ffe4ca8669ae20bff6033127`.
Final synthetic harness SHA256:
`31f470f73f1712d87084bb319d4f86ae8ec9354be8b62e0d397b0ef73cfee271`.
Both hashes match before and after the final invocation.

| Attempt | Passed | Failed | Actual reader exit | Interpretation |
| --- | ---: | ---: | ---: | --- |
| symbolic-preflight01 | 56 | 1 | 1 | Failed new missing-MARK setup; startup binding not established |
| symbolic-preflight02 | 57 | 0 | 0 | Corrected setup; startup binding not established |
| symbolic-preflight03 | 57 | 0 | 0 | Same tracer and 57 behavior cases; explicit startup binding |

Before the first run, independent review corrected another new synthetic
input that was too short to reach its intended protocol guard. Its original
draft is preserved. The first executed failure then exposed a wrapper MARK
in the missing-MARK fixture; the repair changed only that input and retained
its assertion. The third run added startup instrumentation and one reporting
boolean. Exact drafts, briefs, differences, launchers and raw outcomes remain
available; no failed result has been relabeled.

The cases cover inert GLOBAL/REDUCE/NEWOBJ/BUILD targets, raw configuration
and absent fields, Specifications state, tensor argument references including
hooks and optional metadata, alias mutation, a shared-child DAG depth bound,
whole-graph cycles including omitted training roots, duplicate keys and memo
entries, malformed stack/MARK/STOP structure, unsupported targets and each
resource bound. The source audit limits imports to json, pickletools and
time. These checks support nonexecution and the stated grammar; they do not
establish checkpoint provenance, architecture, configuration semantics,
tensor contents, compatibility, conversion safety or release acceptance.

The output is a final literal-container reference graph with per-object
instruction order. It does not preserve global event order or historical
argument snapshots, and it never evaluates constructor or BUILD semantics.
Only selected literal root associations and their reachable nodes are
emitted. Other root associations are omitted from output but still undergo
graph validation. A cycle or unsupported actual structure must remain a
refusal rather than cause an unreviewed expansion of this grammar.

The existing approved inventory reader and every completed inventory/tail
seal remain unchanged. A later adapter must retain its fixed path, immutable
whole-artifact digest, directory/name/extent bounds, bounded payload decode,
CRC checks and output limit. It may pass only the already validated in-memory
pickle bytes to this exact tracer. That adapter has not been implemented or
executed in this proposal and requires a separate exact-code review before
the integrator performs any actual static trace.
