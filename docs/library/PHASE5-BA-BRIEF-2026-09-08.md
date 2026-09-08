# Phase 5 acceptance brief (run BA, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase5-v1`
([PHASE5-CONTRACT-2026-09-08.md](PHASE5-CONTRACT-2026-09-08.md)). Base: the commit this brief
lands in. No worker runs a model, the resident helper, or touches port 5179 or the live
index. Do not commit.

## Integrated candidate

- `47660ed`: Gemini's first AZ session timed out after writing `library_analysis.py`, the
  `get_library_activity` registry tool (85 with Phase 4) and stdio registration (29 with
  Phase 4), and the dashboard report panel; Fable added the module to the build and
  installer inventories and committed it as labelled work in progress.
- `619766b`: Gemini's AZ-2 session delivered `tests/test_library_analysis_fixtures.py` with
  all 28 test names from your acceptance table (28 passed on the integrated checkout), the
  `library_analysis.py` repairs those tests found, and
  `PHASE5-AZ-MEASUREMENTS-2026-09-08.md` (synthetic 548 and 10,000-item fixtures; labelled
  as such).
- Ownership note: the phase plan named the Claude worker for the aggregation module; Fable
  reassigned AZ to Gemini because that engine was serving Phase 4 and is limited to one
  session at a time. Your review is the independence check.

## codex (GPT-6 Astra): review and rule

1. Re-run `tests/test_library_analysis_fixtures.py` and the registry, stdio, docs and
   dashboard suites yourself; report observed counts.
2. Review provenance and statistical meaning (your ownership per the phase plan): every
   displayed total, ratio, group, bucket and mutation resolves to query, population, clock,
   interval, revisions and paged evidence; creator hints are never identities; the applied
   journal is parsed in full with the survivor baseline; recompute on read with
   `stale_report`; half-open UTC intervals with clock admission; engagement absent; Part B
   absent. Check that each named test actually asserts the gate it is named for, not a
   weaker form.
3. Review the measurements document: are the numbers what the test recorded, are they
   labelled as synthetic, and does any budget rest on an unmeasured path (error path,
   over-budget refusal)?
4. Rule `PHASE 5 PART A ACCEPTED`, `ACCEPTED WITH CONDITIONS` (named), or `NOT ACCEPTED`
   (named defects with exact repairs and reproducing tests you add to
   `tests/library_work_astra/test_phase5_*.py`), in `docs/library/PHASE5-ACCEPTANCE-2026-09-08.md`.
   Include the exact commands Fable must run.

Files you may edit: `tests/library_work_astra/test_phase5_*.py` (new), the acceptance
document.
