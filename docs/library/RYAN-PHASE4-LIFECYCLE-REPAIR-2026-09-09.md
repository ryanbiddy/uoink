# Phase 4: repair failed-start and session cleanup

Worker: Grok. Integrator: Astra. Start from the committed candidate supplied
by Control Room. Read the current rulings in
`docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md` and section 2 of
`docs/library/CORRECTED-TREE-PRODUCT-REPAIR-BRIEF-2026-09-09.md` first.
Ryan explicitly asked Astra to continue until release readiness on 2026-09-09.

The corrected full tree on `4a35316` has five failures in
`tests/test_phase4_av5m4b_lifetime.py`: refused job assignment still reports a
foreign worker, followed by four ordinary exports refusing with a dead operation
context. This brief authorizes a focused diagnostic of the complete file in
its original order, with context/session/owner snapshots and actual child
identity/death evidence, to establish the cause. Preserve that result before
repair. Do not interpret a focused pass as closure of the full-tree failure.

Repair production failed-start and originating-operation cleanup in
`library_mirror.py` or its child I/O module. Do not edit existing tests,
reset globals from fixtures, authorize foreign-thread cleanup, drop retention
while launch/assignment is unresolved or grant an expired operation a later
session. Preserve shared Windows exclusion and actual Thread-object authority.
Inspect termination, graceful shutdown and failure paths together. Avoid broad
refactoring. Write an initial implementation or diagnostic report early.

Run these complete files after each documented repair, preserving failed logs:

- `tests/test_phase4_av5m4b_lifetime.py`
- `tests/test_phase4_av5m4b2_lifetime.py`
- `tests/test_phase4_av5m4b3_lifetime.py`
- `tests/test_phase4_av5m4b4_lifetime.py`
- `tests/test_phase4_av5m4b5_lifetime.py`
- `tests/test_phase4_av5m4b6_lifetime.py`
- `tests/test_phase4_av5m4b7_lifetime.py`
- `tests/test_phase4_aw12_termination_owner.py`
- Every `test_phase4_aw*.py` file in `tests/library_work_astra`.
- `tests/test_library_mirror.py`.

Resolve this list before running it. All eight unchanged parent-interception
failures from product brief section 3 must remain visible, not deselected or
declared passing. New independent regressions may be added only for product
behavior; never change an existing fixture, assertion, skip or parameter.

Use a disposable data/profile root and the retained integrator guard/runner
under `docs/library/proof/ryan-corrected-01-2026-09-09`. The integrator may
provide its existing local Python environment by an external command; do not
reference another checkout from worker code. No live index, port 5179, external
source fetch, model/client subprocess, paid API or label application. Never
set ANTHROPIC_API_KEY. No commits, pushes, main merge or other-worktree edits.

Deliver the bounded source diff, full commands/results, documented reasons for
any retry, and `docs/library/RYAN-PHASE4-LIFECYCLE-WORKER-2026-09-09.md`.
State all unresolved findings honestly. Astra independently verifies the worker
tree and checkout before accepting and committing any repair.
