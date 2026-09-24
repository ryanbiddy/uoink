# AV-5m3: repair mirror ownership without test-specific cancellation

AV-5m2 (Grok `6b5e5f1e`, base `633eb99`) is rejected. Its complete diff/report
is retained in `patches/av5m2-grok-rejected-2026-09-08.patch`. Independent worker
verification reproduced **210 passes** across AW/AW-2/AW-3 and the seven named
unit/stdio files in 47.97 s. That count does not accept the implementation.
Logs and XML are under that worktree's `_scratch/ig-av5m2-w`.

The final source still reads the replacement callback's closure and checks the
literal `observe == "user_edit"`. Its report's proposed bytecode heuristic would
be equally unacceptable. `PyThreadState_SetAsyncExc` cannot cancel a hung OS
replacement before it publishes, and an in-flight list on one Mirror instance
does not retain destination exclusion across another instance or process.

Read `INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md`, AV-5 and AW-3 completely.
Start from current `cc/living-library`; use only the production portion of the
retained patch as a starting point, applying with three-way integration.
Preserve the accepted AV-5r and AV-5m1 repairs. Never change existing tests.

Finish D12-D15 as general product behavior:

1. Retain every outstanding temp generation until cleanup succeeds. Bind a temp
   allocation to its content and file identity; a recorded path alone is not
   deletion authority. Do not swallow failure to persist allocation ownership
   and then publish anyway. Preserve replacements and retain failed cleanup.
2. Replace the D13 workaround with actual cancellable, isolated vault I/O and
   destination exclusion that survives the caller returning a timeout. No
   callback/code/closure inspection, async Python exception injection, or
   rollback over destination bytes. A terminated worker must be unable to
   mutate that destination or erase a newer acknowledged sync. A child process
   is authorized here; the old module's claim that the brief forbids one does
   not apply. Avoid a new interpreter for every file: use one isolated worker
   per operation or another bounded design. Preserve source/dependency checks
   against authoritative storage immediately before publication.
3. Persist the exact final `Library.md` intent bytes/hash before replacement.
4. Make destination-binding persistence atomic and durable before granting
   initialization/export authority. Missing or corrupt binding after prior
   consent/export requires reconciliation; do not infer fresh authority merely
   from an empty file/dictionary. Retain evidence of failed persistence and
   refuse instead of acknowledging. Preserve explicit destination changes.

The contradictory D13 fixture setup is recorded for Ryan; do not attempt to
make it green by recognizing the test. Run the unchanged cases and report their
actual results. Add focused new tests of the chosen I/O boundary with an
independent user editor, actual worker termination, and a second Mirror/process.
Keep publication/cancellation timings measured separately from process startup.
A new test supplements the frozen failures; it cannot relabel or replace them.

Also inspect AV-5m1's `BriefStore._sqlite_writer_exclusion`: it currently rolls
back an already-active caller transaction. Refuse or otherwise preserve that
transaction rather than discard authoritative caller work. Keep the independent
SQLite-writer exclusion and brief receipt/retry semantics.

Run all commands in AV-5: AW, AW-2, full AW-3, resources, prompts, briefs, mirror,
mirror wiring, Phase 4 stdio and C01 stdio, plus new implementation tests. Use
short fixture paths as documented in the integrator verification brief. Report
exact commands, failures and limitations. Astra verifies before AW-4; do not
claim Phase 4 accepted yourself.

No existing test edits, subagents, model calls, API key, paid API, live index,
port 5179, commits or pushes. Apply remains false. Use disposable profile/temp
roots and resolved dependencies. Write the implementation/report early.
