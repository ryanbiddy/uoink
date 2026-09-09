# AZ-5h: charge the actual final transport serialization

Engine: Grok, after AZ-5g's current run is retained and its result reviewed.
Read `PHASE5-BA4-2026-09-08.md`, BA-11 in BA-3, AZ-5d2 and the Phase 5
budget contract. AZ5d2's intermediate adapter checks pass; the actual SDK
serialization happens later and is still uncharged. Preserve its repairs.

Close BA4-01. The new frozen test in
`tests/library_work_astra/test_phase5_ba4_acceptance.py` drives the current
registered server through the SDK stdio transport. Delayed final protocol
serialization emits success with active admission zero (one failure,
1.19 s in integrator scratch `ba4-sdk`). The product must carry the original
request's admission and deadline through complete serialized UTF-8 response
construction, including the actual request ID/envelope, check the byte and
time budgets after that construction, and release on success, typed error,
cancellation and broken transport. No extra admission for the same request.

Use a supported, explicit application transport boundary. Do not patch the
installed SDK files, inspect test callbacks, or add test-specific monkeypatch
handling. Preserve request IDs, strict duplicate-key rejection, normal
notifications, resource/prompt/tool inventory and text fallback behavior.
An application-owned outbound stream/message wrapper can retain a request's
scope while delegating serialization to its real SDK message, then check the
completed bytes before delivery. The original SDK stdio route may remain
usable this way. Choose and document the actual lifetime; do not replace
serialization with a second estimate or depend on a particular test hook.
Do not relabel a successful expired packet as a generic internal error.
Keep a bounded retryable deadline refusal and the existing wire cap.
Inspect the Phase 4 bounded read/resource/prompt paths, which use the same
shared service budget and also return through the SDK writer. Apply the
shared transport lifetime consistently where required; add focused actual
transport coverage and run their existing suites. Do not grant new write,
fetch, approval or model authority.

The current frozen probe is bound to the existing SDK transport route. If
a correct repair replaces the shipped transport entry, add an independent
actual-entry test with equivalent final-serialization delay, cancellation
and admission-release checks. Report the old probe's exact result and route
limitation; never edit it or claim it exercised a route it did not. The
integrator will review actual-entry behavior before ruling. A handler-only
size estimate is insufficient.

Run the full AZ-5d2 union, all three measurement generations, BA-4's new
probe and your new actual-entry tests. Existing tests/helpers and acceptance
assertions stay unchanged. Keep the unary/clock setup failure for Ryan.
Record any now-stale measurement assertions for a briefed AZ-5g2 refresh;
do not change measurement documents in this implementation run.

Write `docs/library/PHASE5-AZ5H-GROK-2026-09-08.md` early with exact commands,
results, the request/response lifetime, cancellation/flush limits and SDK
compatibility (installed 1.28.1, package pin 1.27.1). No live index, port
5179, models, API key, paid API, installed SDK edits, commits, pushes or
subagents. Apply false; disposable roots and resolved dependencies only.
Astra verifies both roots, then briefs refreshed measurement on the final SHA.
