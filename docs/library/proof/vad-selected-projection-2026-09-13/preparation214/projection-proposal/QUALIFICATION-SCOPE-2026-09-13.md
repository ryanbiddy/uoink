# Projection synthetic scope and fixture signatures

Preserve the previous 36-case cycle harness unchanged in `before` and its
sealed proof. Reuse its 35 behavioral/boundary cases and assertions. Its
one reporting-only AST equality predicate is specific to the previous
diagnostic change; retain it as unregistered historical code and replace
it with an AST comparison for this separate projection scope. Do not claim
the old predicate passes against an intentionally changed instrument.

The fixed reader now passes explicit project_selected/projection_deadline
keywords to the tracer. Existing synthetic traced/forbidden seams must
accept those keywords; the traced seam forwards them and forbidden seams
still record and reject any attempted call. Preserve all existing assertions.
This narrow signature adaptation is new synthetic setup, not an acceptance
fixture or product change. The previous bytes remain available for review.

New tests use only small literal pickle bytes, synthetic ZIPs and existing
inert receipt fixtures. They check selected-closure cycles/aliases, every
symbolic edge family, shared-DAG depth including the root, missing roots,
selected descriptor rules, omitted data/descriptor exclusion, both output
caps, expired budgets, serialization crossing the original deadline, and
strict cycle refusal/exit 2 regardless of projection outcome. The AST check
proves unchanged code outside the designated projection blocks; those new
blocks still require independent source and behavior review.

The planned run contains 63 cases: 35 inherited behavioral/boundary cases,
one projection-scope AST normalization and 27 new projection cases. The
final-cap case serializes the combined cycle witness and projection through
the inert main receipt path, then verifies that the complete graph is
discarded under a tightened 512-byte receipt limit. The serialization-time
case advances a synthetic clock only when full receipt JSON is produced,
so it checks the post-serialization deadline repair directly.

Independent pre-run review added focused selected-node and selected-edge
limit cases. Tightening the parser limits before parsing would test an
earlier guard, so these explicitly labeled inert seams tighten only the
per-instance limits when selected_projection is called after the strict
cycle refusal. They assert the exact projection-refused marker with no
values and the unchanged overall cycle reason. The first unexecuted
61-case harness is preserved in `draft01`; no assertion was removed.
