# Repair the completed reader's SQLite deadline cleanup

Worker: Gemini. No subagents. Write early, use targeted searches, never commit.
Work only in the Control Room worktree. The integrator will verify the raw diff,
apply it with three-way Git apply, repeat the suites and commit.

Package-06's actual installed client returned storage_error twice while reading
a stored range. Read-only installed diagnosis reproduced the sequence:
resources/list, wait 2.1 seconds, export_cited_range. The first operation calls
library_resources.LibraryReader._disarm_sqlite_deadline with
conn.set_progress_handler(None). Python 3.13.15 raises TypeError because the n
argument is required. The catch suppresses that error, leaving the expired
progress callback attached to the shared connection. A later Phase 6 query
then raises SQLITE_INTERRUPT (9), mapped to library_unavailable/storage_error.
The raw result and all diagnostic output remain failed evidence.

Fix cleanup by using the supported SQLite callback-removal signature. Preserve
the active request's deadline enforcement, nested-lock ownership, admission
limits, read-only behavior and exception cleanup. Keep the product change
bounded to this cause. Do not change acceptance tests or existing fixtures.

Add new behavioral regressions using real SQLite connections. They must show
that a completed reader no longer interrupts subsequent SQL when its former
clock deadline has elapsed, that exceptional exits also clear the callback,
and that an active request still interrupts work after its deadline. Include a
cross-consumer media export regression if a current valid published source can
be constructed with existing helpers. Do not bypass revision validation or
change an existing helper to accommodate the test. Use deterministic clocks
where practical; do not assert the implementation's method-call spelling.

Run the new file plus tests/test_phase4_resources.py, tests/test_phase4_stdio.py,
tests/test_phase6_bc2.py, tests/test_phase6_bc3a3.py,
tests/test_phase6_bc3e.py and tests/test_phase6_bc3f.py. If a named file is absent,
report it and use the matching existing resource suite; do not silently omit
coverage. Retain actual counts and exits. Use PYTHONDONTWRITEBYTECODE=1,
PYTHONPATH=the worktree, PHASE3_REQUIRE_IMPLEMENTATION=1, no API-key variables.
An integrator will also demonstrate the new regression failing on old code.

No live index, 5179, paid API, ANTHROPIC_API_KEY assignment, source/media fetch,
speaker inference, model/checkpoint loading, installer execution or Git push.
Apply stays false. Do not edit the original P4 chapter fixture: a separate
diagnosis found missing published media_depth in its sidecar, and that
incomplete setup cannot qualify as a successful chapter-export observation.

Integrator execution note: the native verification environment itself loads
the historical parent guard at interpreter startup. The first old-code test
launch omitted IG_FORBIDDEN_LIVE and stopped with KeyError before loading the
runner or collecting tests. Set the explicit forbidden live path before starting
that interpreter, as the complete-tree runner already does. Keep that refused
launch separate from the subsequent old-code regression result.

Deliver the narrow diff, new tests and a short review explaining behavior,
counts and any remaining concern. The integrator owes a new complete tree,
package and installed qualification after this production repair.
