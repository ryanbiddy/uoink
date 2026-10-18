# Phase 5 repair brief (run AZ-3, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Astra's acceptance
([PHASE5-ACCEPTANCE-2026-09-08.md](PHASE5-ACCEPTANCE-2026-09-08.md)) is NOT ACCEPTED on
fourteen defects BA-01 to BA-14, each with file and line, an exact repair and reproducing
tests in `tests/library_work_astra/test_phase5_acceptance.py` (66),
`test_phase5_dashboard.py` (8) and `test_phase5_measurements.py` (1): 74 failed, 1 passed
on the integrated checkout `44fb7c1`. Contract `phase5-v1` governs. Base: the commit this
brief lands in. No worker runs a model, the resident helper, or touches port 5179 or the
live index. Do not commit; Fable integrates and runs every test.

## gemini: close BA-01 to BA-14

Read the defect table in the acceptance report; it is the specification. Implement exactly
the repairs Astra names, in `library_analysis.py`, the `get_library_activity` adapters in
`uoink_mcp_tools.py` and `uoink_mcp.py` (BA-09: shared validation and error semantics on
HTTP and actual stdio `tools/call`, `isError` on domain errors, read-only/idempotent
annotations, duplicate-key rejection at the raw transport boundary where bytes exist), the
Index read boundary (BA-08: one coherent snapshot under the Index lock; refuse an inherited
write transaction; connection nonce), the dashboard panel in `assets/dashboard/index.html`
(BA-12), and `docs/library/PHASE5-AZ-MEASUREMENTS-2026-09-08.md` (BA-14: correct the 548
journal figure from captured output, measure the omitted paths Astra lists: proved baseline
replay, error and refusal paths, actual transport serialization, three memberships per
item, a multi-operation journal, the 100k-observation case; keep Astra's distinctions about
tracemalloc versus process memory and about what each timing includes).

Hard points the contract fixes and Astra's tests enforce; do not soften them:

- Every displayed number carries provenance and resolves to exact evidence rows; unknown
  metric ids are `not_found` (BA-01).
- Platform and field keys are never case-folded; original observations survive (BA-02).
- Publication precedence falls back only when the higher tier has no admissible instant;
  lower-tier disagreement is disclosed (BA-03).
- Null historical values with `recorded_count: 0` when no history exists; `partial`
  coverage when any record is excluded; integer source milliseconds; decimal half-up
  rounding (BA-04).
- Full delta validation including primary and receipt bindings; invalid shape is
  `invalid_source_data`; invalid dates are labelled exclusions (BA-05).
- Current counts filter through live saved ids; initial filing counts live survivors only
  (BA-06). Capture spans and unlinked hint rows per Astra (BA-07).
- The complete serialized protocol response stays within 65,536 bytes on every path (Astra
  measured 86,357 on actual stdio); Phase 4's untrusted fence wraps model-facing text;
  whole-row shedding recomputes counts and continuation (BA-10).
- Phase 4's process-wide admission guard is shared; one deadline covers lock, query,
  aggregation and serialization with checks between bounded units; journal bytes are
  measured before materialization and replay streams (BA-11).
- The faithfulness evaluator must not pass number reuse or unlisted topics; it stays a
  static assertion-level check bound to metric id, population, clock, interval and
  revisions (BA-13).

Astra's 75 tests plus the existing 28 in `tests/test_library_analysis_fixtures.py` are the
acceptance target and must not be edited (the 28 may be strengthened where Astra's
assertion audit says a pass proves only a subset, and you must say which). Keep
`tests/test_c01_mcp_stdio.py`, `tests/test_phase4_stdio.py`, `tests/test_stdio_clip_tools.py`,
`tests/test_docs_live_contracts.py`, the dashboard suites and the Phase 4 test files green.
Run everything and report observed counts and exact commands. Two sessions are acceptable:
if you must stop, leave the tree importable and say exactly which BA items are closed.
