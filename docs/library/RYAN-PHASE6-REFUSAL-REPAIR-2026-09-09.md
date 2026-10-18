# Phase 6: reconcile stale-publication refusal semantics

Worker: Grok. Read the current owner rulings in
`docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md` and section 5 of
`docs/library/CORRECTED-TREE-PRODUCT-REPAIR-BRIEF-2026-09-09.md` first.
Two corrected-tree tests expect `revision_unavailable` for stale ticketless
publication and receive `invalid_request`. All existing test inputs and
assertions are now frozen. Successful setup already has original build-time
tickets; do not mint authority for an already-built snapshot.

Review `library_media.py` and `index.py` publication/refusal precedence against
every explicit missing, foreign, malformed and stale-ticket test. Repair the
product only if it can truthfully distinguish obsolete committed input from
a malformed new request without permitting stale writes. No caller/test
detection, fresh-ticket fallback, unconditional missing-ticket allowance or
relabeling an unverified snapshot. Preserve transaction/final-replacement
checks and deletion, annotation retention, sidecar and clip identity behavior.

This brief permits a bounded baseline diagnostic of refusal inputs if needed;
retain it, then document each repair before a subsequent run. Verify complete
`tests/test_phase6_bc2.py`, `tests/test_phase6_evaluation.py`,
`tests/test_phase6_bc3f.py`, every other `tests/test_phase6*.py` file, and
`tests/library_work_astra/test_phase6_bd_acceptance.py` and
`tests/library_work_astra/test_phase6_bd2_acceptance.py`. Resolve names first.
Do not edit any existing test, assertion, fixture, skip or parameter. If the
fixed contracts cannot both be satisfied, write the exact conflict rather
than a workaround and continue any independently valid repair.

Use only disposable synthetic data with the retained isolated runner/guard
under `docs/library/proof/ryan-corrected-01-2026-09-09`. Never access the live
index or port 5179; no new fetch, diarization, model/client process, paid API or
label application. Phase 6 release claims are chapters/cited ranges only.
Never set ANTHROPIC_API_KEY. No commits, pushes, main merge or other-worktree
edits. Write source or a concrete conflict report early.

Deliver the source diff and `docs/library/RYAN-PHASE6-REFUSAL-WORKER-2026-09-09.md`
with exact outcomes, commands, repair/retry reasons and limits. Astra verifies
independently in both roots before integrating.
