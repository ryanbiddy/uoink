# BC-3a2: finish publication ownership and reconstruction repairs

BC-3a (`eb0f138e`, Gemini, base `fc99942`) stopped on its subscription quota.
It is a failed partial run. Its ten-line diff is preserved unapplied in
[bc3a-gemini-partial-2026-09-08.patch](patches/bc3a-gemini-partial-2026-09-08.patch).
Do not treat it as an accepted repair. In particular, it still mints a ticket
inside the publisher under several conditions rather than requiring the
build-time ticket. Start from current `cc/living-library`, keeping BC-3b and
BC-3c; the partial patch is context only, not a required starting implementation.

Integrator verification of the partial worktree found 151 passed and ten failed,
including three BC-2 regressions; all four assigned findings still have open cases.
Grok replaces the quota-blocked engine. No subscription upgrade or paid API is
authorized. This brief documents the repair and route for the new run.

Read [the BC-3 brief](PHASE6-BC3-BRIEF-2026-09-08.md), then BD-01/03/05/06 in
[the BD review](PHASE6-BD-2026-09-08.md). Close the five reproductions:

- BD-01, both raw and Index entry points: reject absent build-time ownership;
  do not allow an old never-published build to mint a new ticket at publication.
- BD-03: reconstruction must use the ledger fence and settle disk/DB coherently,
  so a stale sidecar cannot roll back a newer annotation-only publication.
- BD-05: preserve another owner's unrelated sidecar edit; merge or refuse before
  replacing the full carrier, with a final dependency check.
- BD-06: protect a user-edited legacy corpus on its first materialization,
  including when the caller holds a ticket.

Fix the owning callers where tickets must be passed from build start; do not
weaken the boundary or acceptance tests to preserve a legacy call shape. Keep
all BC-2 compatibility tests and the previously accepted publication/recovery
behavior. Add implementation tests only for necessary behavior beyond the
existing reproductions; never edit acceptance assertions.

Run `tests/library_work_astra/test_phase6_bd_acceptance.py` in full, plus all
companion commands in the BC-3 brief: Phase 6 evaluation and BC-2, podcast corpus
bridge, clips, resources, and the three Phase 3 publication/integration/recovery
files with PHASE3_REQUIRE_IMPLEMENTATION=1. Use disposable profile/output/temp
roots, PYTHONDONTWRITEBYTECODE=1 and worktree/dependency PYTHONPATH. Record exact
commands, counts and failures. Write the implementation early; no subagents.
No models, paid API, API key, live index or port 5179; apply stays false.
No commits or pushes. Astra verifies and integrates before BD-2 review.
