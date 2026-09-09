# Phase 5: retain admission through actual SDK serialization

Worker: Grok. Read the current owner rulings in
`docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md` and section 4 of
`docs/library/CORRECTED-TREE-PRODUCT-REPAIR-BRIEF-2026-09-09.md` first.
The corrected tree's BA-4 test observes successful output after its deadline
and zero admissions during actual SDK serialization. Ryan requires a product
repair, with no further fixture edits. The corrected unary-clock probe passed.

Investigate the original low-level server route exercised by
`tests/library_work_astra/test_phase5_ba4_acceptance.py`, then repair product
registration/serialization integration so supported routes retain admission
through final encoding and refuse expired output. Keep complete packets,
pagination and error envelopes. Prefer a bounded change in `uoink_mcp.py`,
`uoink_mcp_tools.py` or `library_analysis.py`. Do not edit installed third-party
packages, inspect callback closures, simulate serializer activity, or declare
the failing SDK route exempt. Preserve the existing original-entry behavior.

This brief permits one focused baseline diagnostic if needed to establish the
route, followed only by runs with a documented repair. Retain all outcomes.
Run the complete BA-4 file and every `test_phase5*.py` file in
`tests/library_work_astra`, plus `tests/test_library_analysis*.py`,
`tests/test_phase5*.py` and `tests/test_phase4_stdio.py`. Resolve selectors
against the worktree first. Do not edit any existing test, fixture, assertion,
skip or parameter. New independent regression cases may exercise product
boundaries. Part B stays deferred. This is not a new dashboard measurement.

Use disposable fixture data with bytecode/cache disabled. The retained isolated
runner/guard are under `docs/library/proof/ryan-corrected-01-2026-09-09`.
Never touch the live index or port 5179; no model/client subprocess, diarization,
external fetch, paid API, label application, commits, pushes or main merge.
Never set ANTHROPIC_API_KEY or edit another worktree. Write source/report early.

Deliver the source diff and `docs/library/RYAN-PHASE5-SDK-WORKER-2026-09-09.md`
with exact commands, outcomes, environment, repair/retry record and limits.
Astra verifies independently in both roots before integration.
