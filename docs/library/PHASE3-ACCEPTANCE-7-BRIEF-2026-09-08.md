# Phase 3 acceptance brief, seventh round (run AS-7, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Reviewer: Astra (codex). Contract:
`phase3-v1` ([PHASE3-CONTRACT-2026-09-07.md](PHASE3-CONTRACT-2026-09-07.md)). Your AS-6
verdict ([PHASE3-ACCEPTANCE-6-2026-09-08.md](PHASE3-ACCEPTANCE-6-2026-09-08.md)) left one
code finding (AS-02b) and three conditions (C20, C21, C22). This round asks you to rule on
the repair and on the evidence supplied for C20 and C21. Candidate: the commit this brief
lands in (`git log -1`), on `cc/living-library`.

## What changed since AS-6 (`34cad50`)

| Commit | Content |
|---|---|
| `d2ec84a` | AS-02b repair in `source_subscriptions.py`: `_child_entry_valid` (positive int `pid`, int/None `created_ms`, int/None non-negative `ended_ms`), `unresolved_launch` must be a real boolean, damaged entries keep the start `unknown`; your four AS-6 reproductions pass with the rest of the suite (159/159). |
| `12339c3` | C20: two dashboard defects found while executing the matrix (consent intent minted only on the confirmed click; health badge reads `detection.consecutive_failures` and `detection.error.{code,message}`); the Fable-only S20 overlay launcher `tests/library_work_astra/s20_matrix_launcher.py`. |
| `56c1c86` | C20 receipt [PHASE3-S20-MATRIX-RECEIPT-2026-09-08.md](PHASE3-S20-MATRIX-RECEIPT-2026-09-08.md) with `docs/library/proof/s20-2026-09-08/` (17 screenshots, persisted-state dumps at each screenshot, notes, overlay logs, SHA256SUMS). All eight scenarios, including two lost-mutation-response variants and a helper restart with in-flight work (`uncertain`, charge preserved). |
| `867605b` | C21 affordance: the Sources row renders each committed item's `classification.state` (`waiting_for_client` visible as a pill) from `source_status`; screenshot and receipt section in `docs/library/proof/s21-2026-09-08/` and [PHASE3-S21-RECEIPT-2026-09-08.md](PHASE3-S21-RECEIPT-2026-09-08.md). |
| `6559a71`, `b67b836`, `fd1825c` | Phase 4, 5, 6 integrations on the same branch (not Phase 3 surfaces; `server.py` changed in the capture path for Phase 6, so run the Phase 3 suites on this candidate). |

## Rulings requested

1. AS-02b: closed or not, with reproductions if not.
2. C20: is the matrix complete and does visible state match persisted state in every
   scenario? Name any scenario that needs a rerun and exactly what is missing. Note the
   launcher repair (ephemeral re-bind) documented in the receipt; scenarios 01-07 ran before
   it, scenario 08 after it.
3. C21: the earlier items (launcher bytes/hash reconciled, exit status, seven archived
   artifacts/logs, browser run's receipt/state binding) as recorded in the S21 receipt and
   `docs/library/proof/s21-2026-09-08/`, plus the new per-item waiting-for-client surface.
   Rule whether the affordance requirement is met.
4. C22 stays Ryan's (installed Inno). State explicitly what remains for Phase 3 acceptance
   once C22 is supplied, so Ryan's receipt can be built once.

## Suites (run all with `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<worktree>`, `PHASE3_REQUIRE_IMPLEMENTATION=1`, no `ANTHROPIC_API_KEY`)

- `python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_*.py tests/library_work_astra/test_phase3_repairs.py` (expected 159 plus companions)
- `python -B tests/library_work_astra/run_phase3_companions.py`
- `python -B -m pytest -q -p no:cacheprovider tests/test_dashboard_sources_api.py tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py tests/test_source_subscriptions*.py tests/test_podcast_*.py`
- Do not execute the S20 or S21 launchers against anything but your worktree's isolated
  data root; never touch port 5179 or the live index. Do not run models.

## Output

`docs/library/PHASE3-ACCEPTANCE-7-2026-09-08.md` (verdict, per-item dispositions, exact
remaining repairs, observed counts and commands) and, for any open item, reproductions in
`tests/library_work_astra/test_phase3_acceptance7.py`. Do not edit implementation,
existing tests, receipts or contracts. Do not commit.
