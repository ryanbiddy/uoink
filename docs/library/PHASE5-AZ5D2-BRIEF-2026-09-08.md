# AZ-5d2: remove test-wrapper introspection from the adapter

AZ-5d (Grok `e739a5ec`, base `79f6961`) is rejected. Its complete diff and report
are retained in `patches/az5d-grok-rejected-2026-09-08.patch`. Independent worktree
verification produced **393 passed, four failed**, 109.07 seconds, across all
Phase 5 acceptance, dashboard, measurement, fixture and named companion files.
The four failures are measurement-document work for AZ-5g. Logs and command:
worker-local `_scratch/az5d-w`. The green BA-3 count does not accept the diff.

The new `_read_activity` in `uoink_mcp.py` catches a TypeError, traverses the
reader's closure and calls a hidden function to accommodate test wrappers.
Its comment explicitly names the stdio tests and BA-3 probe. This is forbidden
test-specific production code. No part has been integrated.

Start from current `cc/living-library`. Read the AZ-5 brief and BA-09/10/11 in
BA-3. Apply only production portions of the retained patch with three-way apply.
Keep the legitimate interval, retryability, row-shedding, label-bounding,
admission and busy-timeout repairs. Then:

1. Remove `_read_activity` and its closure/TypeError fallback. Call the public
   `library_analysis.get_library_activity(args)` normally. No callable inspection,
   test imports, test-name branches, fake success or exception relabelling.
2. Preserve a single admission and deadline through the actual final stdio
   response serialization. Check nested admission state cannot discard another
   active scope. Retain busy_timeout restoration before releasing shared storage.
3. Add a new independent implementation test that calls the actual stdio handler
   directly with a compatible reader wrapper and injects elapsed time in final
   wire serialization. Verify a retryable deadline refusal and admission release.
   This supplements the unchanged frozen case; it cannot replace its result.

The frozen case `test_phase5_ba3_final_wire_serialization_is_inside_deadline`
installs `read(args)`, then its `stdio_result` helper at acceptance.py:427-431
wraps that function as `real_read(arguments, clock=NOW)`. That call raises
TypeError before the intended deadline probe. Ryan must authorize compatible
fixture setup. Keep the failure unchanged and report it. Never inspect or unwrap
the callback in production to repair the fixture.

No existing test edits, including helpers. Run the full AZ-5 commands, full
BA-3, all three dashboard/measurement generations, 28 fixtures, dashboard
companions and the new implementation test. Record exact observed counts and
each failure. Astra independently verifies and integrates; AZ-5g follows on
the final implementation and BA-4 follows the measurement refresh.

Use disposable profile/output/temp roots and resolved Python dependencies.
No live index, port 5179, models, API key, paid API, commits, pushes or subagents.
Apply remains false. Write production changes and the report early.
