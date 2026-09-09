# AZ-5g2: complete and seal the final measurement record

Engine: Grok, only after AZ-5h's transport repair is integrated. Read the
AZ-5g brief and BA-4. AZ-5g Gemini `5e9baea5` ended without its required
report. Its partial proposed refresh is retained in
`patches/az5g-gemini-partial-rejected-2026-09-08.patch`; do not treat those
numbers or its completed Control Room status as acceptance.

The partial script hardcodes `git_tree_hash` to the old measurement document's
blob ID, not a git tree. Its `totals` uses returned sample lengths and null
for event totals. It omits complete response packets and wire bytes, records
only summary sizes, and leaves timing ranges/heap figures without a complete
retained execution record. This is the documented repair for a new run.
AZ-5h also changes the actual transport boundary, so fresh measurements must
name the final source SHA and the path they actually execute.

Start from the AZ-5g brief's requirements, using the old patch as reference
only. Do not blindly copy its metadata, totals or claims. Write a runnable
measurement harness and report early. Derive commit/tree IDs and hashes from
the actual checkout and artifacts, not constants. Record package versions,
interpreter, exact requests, complete reader packets and final serialized
JSON-RPC bytes (raw or lossless encoding), SHA-256, isError, and each time
boundary. Include actual shipped transport observations after AZ-5h; label
separate handler-only and hand-built measurements by their real scope.

For the full existing cost fixture, record every population dimension and
true total/returned/omitted count from the packet's pagination and metrics.
Never call a sample length a population total. Include refusal paths, replay,
large journals, dense memberships, ten operations and 100k observations.
Retain query plans. Measure error-path heap where feasible in separately
labelled diagnostic tracing passes; record tracing state and any changed
diagnostic deadline. Keep normal deadline/timing results separate. Do not
claim an unmeasured path passes. Retain complete stdout and machine-readable
records so every published number has a source.

Archive the original measurement document's exact bytes and hash before
replacing it. Preserve the rejected AZ-5g artifact separately. Regenerate
`PHASE5-AZ-MEASUREMENTS-2026-09-08.md` from the new observations, keeping the
raw-JSON legacy table label required by its test but labelling it honestly.
State the missed dashboard target and the distinction between fixed limits
and measured guarantees. Freeze artifacts with a SHA-256 manifest.

Run the full AZ-5d2 union, all three measurement generations, the BA-4
transport probe and AZ-5h's new tests. No existing test/helper, production,
adapter or contract edits. Keep the unary/clock conflict failed for Ryan.
Write `docs/library/PHASE5-AZ5G2-GROK-2026-09-08.md` with exact commands,
results and limits. No live index, port 5179, model, API key, paid API,
commits, pushes or subagents. Apply remains false. Disposable roots only.
Astra verifies both roots and completes BA-4 on the integrated result.
