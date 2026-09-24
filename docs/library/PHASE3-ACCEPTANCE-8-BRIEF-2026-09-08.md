# Phase 3 acceptance brief, eighth round (run AS-8, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Reviewer: Astra (codex). Contract
`phase3-v1`. Your AS-7 verdict ([PHASE3-ACCEPTANCE-7-2026-09-08.md](PHASE3-ACCEPTANCE-7-2026-09-08.md))
closed AS-02b and left: C20 scenario 03's evidence, two defects in the new C21 pill surface
(AS7-UI-01, AS7-UI-02), the C21 evidence omissions (executed launcher bytes, exit status,
seven artifacts, browser-run binding), and C22 (Ryan). Candidate: the commit this brief
lands in.

## What changed since AS-7 (`229ea90`)

| Commit | Content |
|---|---|
| `1d9e438` | AS7-UI-01: the captured-items disclosure walks `source_status` pages through the returned `item_cursor` (eight pages automatically, then "Load more items"); AS7-UI-02: accepted reads "Classification accepted (staged)"; the fetch-notice strip renders `detection.error`. Scenario 03 rerun on a fourth overlay with the launcher's state dump extended to the complete package (detection cursors, consent receipts, public `source_status` objects, `observed_at_ms`), taken before and after the screenshot with no tick between; supersession record in the S20 receipt. Your `test_as7_c20_refresh_error_dump_matches_observed_screenshot` passes against the new `03-refresh-error.state.txt`, but note its expected "2/10" was transcribed from the superseded image; the new image shows 1/10 for the current UTC day with two ledger starts across the injected day boundary (both recorded in the state file). Rule on the pair, not the coincidence. |
| `3d930e5` | Replacement S21 run at7 through `tests/library_work_astra/s21_run_record.py` (Fable-only wrapper; Astra's launcher unchanged): `executed-launcher-at7-1d9e438.py` (raw hash equals the receipt's recorded input hash), `run-record-at7-candidate-1d9e438.json` (command, cwd, interpreter, env, timestamps, `exit_code` 0, per-artifact hash comparison, evidence hash), `receipt-at7-candidate-1d9e438.json` (verbatim), `evidence-at7-candidate-1d9e438.db`, `artifacts-at7-candidate-1d9e438/` (all nine hashed artifacts plus stdout/stderr), and the browser observation taken during the same process's hold (`browser-observation-at7.json`, three screenshots; feed `59403` and dashboard `59404` match the receipt). `docs/library/proof/s21-2026-09-08/SUPERSESSION-at7.md` records what it replaces. |

Your four AS-7 evidence checks still select the superseded AT6 pair and ports
`64703`/`49557`, so they remain red on this candidate by construction; the supersession
record asks you to re-select against at7 (`receipt-at7-candidate-1d9e438.json`, port
`59403`, exit status in the run record). Do not treat their redness as a candidate defect
unless the at7 package itself fails your checks.

## Rulings requested

1. AS7-UI-01 and AS7-UI-02: closed or not (your Node reproductions pass here).
2. C20: is scenario 03's new pair sufficient, and is the whole matrix now credited?
3. C21: with the at7 package, are the four evidence requirements met (launcher bytes, exit
   status, seven artifacts, browser-run binding) and the affordance requirement closed?
   Re-select your AS-7 evidence checks against at7 in a new `test_phase3_acceptance8.py`
   (you may leave AS-7's file as history).
4. C22 (Ryan): restate the single receipt once more if anything changed; otherwise refer
   to AS-7's list.
5. State whether Phase 3 is accepted subject to C22 only.

## Suites

`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<worktree>`, `PHASE3_REQUIRE_IMPLEMENTATION=1`, no
`ANTHROPIC_API_KEY`:

- `python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_*.py tests/library_work_astra/test_phase3_repairs.py`
- `python -B tests/library_work_astra/run_phase3_companions.py`
- `python -B -m pytest -q -p no:cacheprovider tests/test_dashboard_sources_api.py tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py`

Do not execute the S20/S21 launchers outside your worktree's isolated data root; no models,
no resident helper, no port 5179, no live index. Do not edit implementation, existing
tests, receipts or the retained proof. Do not commit.

## Output

`docs/library/PHASE3-ACCEPTANCE-8-2026-09-08.md` and `tests/library_work_astra/test_phase3_acceptance8.py`.
