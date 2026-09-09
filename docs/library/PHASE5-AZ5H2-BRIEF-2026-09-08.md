# AZ-5h2: preserve the inbound deadline and bound refusal frames

Engine: Grok. Read AZ-5h, its report and BA-4. AZ-5h is integrated at
`8e3e4f0` after clean three-way apply and **561 passed, six failed** in
both roots (115.63 seconds worker, 113.79 seconds checkout). Its seven
new actual-entry tests pass. Keep that transport boundary and all AZ-5d2
repairs. Existing tests/helpers are frozen.

The new frozen `tests/library_work_astra/test_phase5_ba5_acceptance.py`
contains two independent failed observations:

1. **Original deadline is reset inside activity.** Inbound admission is held,
   then 1.5 seconds of elapsed dispatch time is injected. A real second SQLite
   connection holds BEGIN EXCLUSIVE. `get_library_activity` creates a fresh
   start time and its storage waits outlive the original budget. The response
   uses 4.6680728 seconds from admission (test failed in 7.09 seconds including
   setup, worker scratch `ba5-inbound-clock`). Pass the original scope deadline
   through domain execution and every storage acquisition/lock/initial query,
   not just the final serializer. Refuse before storage where already expired.
   Preserve the direct/HTTP path, nested admission and exact refusal types.
   Inspect initial busy-timeout and restoration paths too; converting the final
   response to a timeout cannot undo an excessive wait.
2. **A refusal can exceed the wire cap.** A string JSON-RPC id of 65,536 ASCII
   characters reaches the actual entry. Success is replaced with an error,
   but that error still has 65,838 bytes (one failure, 1.39 seconds, worker
   scratch `ba5-refusal-wire`). Enforce a bounded inbound protocol envelope
   before echoing an excessive id. Check the completed-frame byte cap on typed
   errors and replacement refusals too. A fixed bounded protocol rejection can
   use a null id when the envelope itself cannot be accepted; preserve normal
   accepted request IDs exactly. Never truncate an accepted id or emit invalid
   JSON. Reject before domain work when the envelope alone cannot fit.

Add focused coverage for remaining-budget SQLite waits, normal accepted IDs,
rate/deadline/refusal frames and admission release. Keep the single shared
two-active/60-per-minute guard. No SDK edits, callback inspection or fixture
branches. The original BA-4 probe still uses the former SDK transport entry;
retain its failed result and describe that route exactly. Actual-entry tests
are independent evidence, not a relabel of that result.

Run the full AZ-5h union, all seven AZ-5h tests, BA-5, all three measurement
generations, the unchanged BA-4 probe, AZ-5d2 tests and Phase 4 resources,
prompts and briefs suites. No measurement-doc edits: four stale assertions
remain AZ-5g2 work. The unary/clock fixture conflict remains Ryan's.

Write `docs/library/PHASE5-AZ5H2-GROK-2026-09-08.md` early, then record exact
commands, results, original deadline propagation and completed-frame limits.
No report means incomplete work. Use short disposable roots and resolved
dependencies. No live index, port 5179, model, API key, paid API, commits,
pushes or subagents. Apply stays false. Astra verifies both roots, then
AZ-5g2 measures the integrated candidate and BA-4 gives its final ruling.
