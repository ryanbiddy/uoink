# Phase 5 implementation brief, run AZ (2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase5-v1`
([PHASE5-CONTRACT-2026-09-08.md](PHASE5-CONTRACT-2026-09-08.md), Astra) is frozen and governs
every number, clock, population and refusal. Inputs already dispositioned by the contract:
[PHASE5-EVALUATION-2026-09-08.md](PHASE5-EVALUATION-2026-09-08.md) (Gemini) and
[PHASE5-COST-AUDIT-2026-09-08.md](PHASE5-COST-AUDIT-2026-09-08.md) (Grok). Base: the commit
this brief lands in. No worker runs a model, the resident helper, or touches port 5179 or the
live index. Do not commit; Fable integrates and runs every test.

## Ownership change, and why

The phase plan named the Claude worker for `library_analysis.py`. That engine is serving Phase
4 (run AV) and is limited to one session at a time on Ryan's subscription, so Fable assigns
AZ to Gemini, which can run its own tests. Astra's review in run BA is unchanged and is the
independence check. Grok is not dispatched.

## gemini: implement Part A exactly as frozen

Files you own: new `library_analysis.py` (pure aggregation, provenance, invalidation
binding, refusal envelope, reusing Phase 4's budget constants and domain-code shapes from
the contract; no reliance on `library_resources.py` existing yet, since AV-1 is in flight),
additive `TOOL_REGISTRY` entry `get_library_activity` in `uoink_mcp_tools.py` (touch
nothing else in that file), the stdio registration for that one tool in `uoink_mcp.py`
(one `@mcp.tool` block; the canonical stdio count becomes 26 and
`tests/test_c01_mcp_stdio.py` `CANONICAL_STDIO_TOOLS` plus `docs/v2-mcp.md`'s two counts are
yours to update in the same change), `index.py` query helpers if the contract's Q1 to Q8
need them (additive, read-only), the dashboard report surface in
`assets/dashboard/index.html` (read-only panel per the contract's dashboard section), and
the tests: `tests/test_library_analysis_fixtures.py` with every test name in the
contract's acceptance table implemented as named, plus the registry, stdio and dashboard
tests the table calls for.

Rules the contract fixes and you must not soften: half-open UTC intervals with clock
admission; capture time by default and publication time only from the deduplicated
saved-item publication relation; creator hints are never identities; the applied journal
is parsed in full for membership measures with the survivor baseline; recompute on read,
no cache, `stale_report` on any input change; every metric carries provenance; the
2-second deadline, two active reads, 60 admissions per minute shared with Phase 4; 8,192
byte requests and 65,536 byte responses; engagement excluded; no migration (if a budget is
unmet, stop and report the measured plan; do not reserve 0029 yourself).

Measure `test_activity_cost_548_and_10000` on synthetic fixtures and record the numbers in
the test's output and in a short `docs/library/PHASE5-AZ-MEASUREMENTS-2026-09-08.md`
(journal bytes, query plans, elapsed construction and serialization time, peak memory, and
the over-budget refusal case). Label them as synthetic-fixture measurements.

Run everything: your new tests, `tests/test_c01_mcp_stdio.py`, `tests/test_docs_live_contracts.py`,
`tests/test_openapi_bridge.py`, `tests/test_phase0_registry_capture.py`,
`tests/test_podcast_corpus_bridge.py`, and the dashboard suites. Report observed counts
and the exact commands. Do not edit Phase 2, 3 or 4 tests, `library_work.py`,
`library_cards.py`, `source_subscriptions.py`, the proof harness or prompts. The Phase 4
`whats-new` prompt seam stays with its reserved owner; expose the adapter function the
contract names and test it in your own file.
