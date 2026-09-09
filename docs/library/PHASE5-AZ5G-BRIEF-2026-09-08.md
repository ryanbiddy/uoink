# AZ-5g: replace stale measurements with final-reader observations

Engine: Gemini, after AZ-5d2 is integrated. Read the AZ-5 brief, BA-14 in
`PHASE5-ACCEPTANCE-3-2026-09-08.md`, and
`PHASE5-AZ-MEASUREMENTS-2026-09-08.md` completely. The actual measurement
filename contains AZ; the old brief's wildcard is not its literal name.

AZ-5d2 removes the forbidden test-wrapper inspection. Its independent worker
verification has 470 passes and five failures: one unchanged unary/clock
fixture conflict for Ryan, and four measurement-document failures assigned
here. Production repairs changed packet sizes and shedding. The previous
document also misdescribes replay and a hand-built envelope timing. This is
the documented repair and authority for a fresh measurement, not permission
to relabel earlier observations.

1. Preserve the complete pre-refresh document under a dated proof path, marked
   superseded with its source commit and hash. Retain its failed assertions.
2. Run the full existing synthetic cost fixture without editing it. Record
   all dimensions, journal bytes, intervals, coverage, returned/total counts
   for each shed collection, raw JSON bytes, timing and query plans. State
   exactly when tracing or a relaxed diagnostic deadline was used; do not
   compare traced and untraced times as equivalent. Never infer skipped
   replay from an unavailable baseline: observe the executed path.
3. Measure the final shipped stdio handler and MCP JSON-RPC serialization
   through the actual adapter. Record the exact request, complete response,
   byte count, isError and timing boundary. A reader packet passed through
   the actual handler is adapter evidence; a hand-built envelope remains
   labelled hand-built. Identify whether a measurement includes a reader
   invocation or only serialization of an already captured packet. A handler
   call is not a real-client transcript. No model or Claude client is needed.
4. Regenerate the main document with observed figures and limits. Keep the
   legacy table label `Wire Response Payload` readable by the frozen test,
   but explicitly identify that row as raw reader JSON. Distinguish actual
   JSON-RPC wire bytes and the 24,576-byte dashboard target. Remove false
   pruning and replay claims. The `Transport Serialization` row must describe
   its hand-built timing honestly; put actual-adapter results in a separate
   row. Do not repeat stale historical sizes as current measurements.

Run all Phase 5 acceptance, dashboard and measurement generations, all 28
analysis fixtures, AZ-5 adapter/inventory/doc commands, dashboard companions,
source-subscription registry, current-doc references and
`tests/test_phase5_az5d2.py`. Keep the frozen unary/clock failure as a failure
for Ryan. Never edit an existing test/helper, production reader, contract or
adapter to fit the document. New measurement instrumentation may call the
public entry point and actual handler with compatible wrappers; it must not
inspect closures or bypass production work.

Write `docs/library/PHASE5-AZ5G-GEMINI-2026-09-08.md` early. Retain a runnable
measurement script and machine-readable observations, commands, environment,
source SHA and hashes. No estimate may be called measured. If quota, timeout
or a gate fails, preserve the partial result and state exactly what ran.
No paid fallback, API key, live index, port 5179, models, commits, pushes or
subagents. Apply stays false. Use disposable roots and resolved dependencies.
Astra verifies both roots and performs BA-4 after integration.
