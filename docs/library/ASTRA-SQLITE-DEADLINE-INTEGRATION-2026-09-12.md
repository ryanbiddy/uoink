# SQLite deadline cleanup integration verdict

Accepted for candidate integration at **d812785**. A completed Phase 4 reader
now removes its SQLite progress callback, so a later media export can use the
same connection after that reader's deadline. Active requests still interrupt
SQL after their own deadline, and the reader retains its deadline-exceeded
error mapping. Normal and exceptional exits both clean up.

Gemini c52710a3 changed one production line in library_resources.py and added
five behavioral regressions using real SQLite. Astra reviewed the change and
ran the seven named suites independently: **97 passed / zero failed** in the
worker root, then **97 passed / zero failed** in the checkout after raw Git diff
and three-way apply. The unmodified new tests on old code produced **four
failures / one pass**, including the installed client's storage_error result.
Original acceptance assertions and the P4 fixture remain unchanged.

The [21-payload integration seal](proof/sqlite-deadline-cleanup-2026-09-12/SHA256.json)
contains both-root logs/XML, original-code failures, the exact worker patch and
Control Room report. The initial old-code launcher refused to start because its
guard environment was incomplete; that refusal preceded test collection and
is documented separately. The two failed package-06 client calls remain failed.

This repair changes packaged source. The prior 2,535/1/2 complete tree and
package-06 installation do not qualify d812785. Follow
[the new qualification brief](SQLITE-REPAIRED-CANDIDATE-QUALIFICATION-2026-09-12.md)
for a clean committed full tree, package-07 and fresh installed observations.
Use [the separate production-publication scenario](INSTALLED-PUBLISHED-CHAPTER-SCENARIO-2026-09-12.md)
for a positive chapter export; the incomplete original P4 chapter seed stays
untouched. Release remains held, with no ordinary upgrade or main merge.
