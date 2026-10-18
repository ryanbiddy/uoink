# Acceptance brief (run F), 2026-09-04: Astra on the repair-increment candidate

Under `ORCHESTRATION-V1-2026-09-04.md` rule 4, Astra owns the acceptance run on the integrated
candidate. This worktree IS the candidate: the commit this file lands in, on top of `c36c85a`.

## What was integrated since your review base `a4a2e6b`

- `8acf1db` SEC-01 fix (orchestrator; `podcasts.py`, real tests replacing Gemini's).
- Run D: your repair commit `d43e934`, Grok `43b45f7`, Gemini three commits; merged with no
  conflicts (`277a0e9`, `78f7a51`, `ce6d529`).
- Run E: the claude section `133e191` (D-17 flag + `usage_meter.py`, heartbeat, Recall
  hardening, stdio clip tools 23 -> 25), merged at `c36c85a`. The claude worker could not run
  any shell command, so the orchestrator ran its suite and made three fixes inside that
  commit: `tests/test_recall_hook.py:349` expectation (fixture links carry `#t=10`),
  `build.ps1` and `installer/uoink.iss` staging `usage_meter.py` (your packaging test caught
  the omission). Review those three edits as conflict resolutions.
- Integrator receipt: full suite on `c36c85a` = **648 passed, 3 skipped, 2 xfailed**. Fresh
  live-index copy (2026-09-04 evening, 548 items, schema 23) opened with the candidate:
  schema 26, 0 NULL `source_type`, 3,705 clips across 212/548 items, 1.7 s; clips over 120 s
  = 435, over 180 s = 271 (coarse-timed excerpts of long cues carry the parent range).

## Deliverable 1: `docs/library/ACCEPTANCE-REPORT-2026-09-04.md`

For every gate in the repair increment (`ASTRA-PHASE-PLAN-2026-09-04.md`, "Repair increment
before Phase 2", all six rows) and for SEC-01 through SEC-05: observed versus expected on THIS
tree, with the command you ran and the number you saw. Rules:
- Rerun, do not trust: the suite, `tests/repair_run_d_measure.py` against the named copy
  (`uoink-index-copy-2026-09-04-upgraded.db`, sha256
  `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`), and the two clip tools
  through the Python handlers on the same items you used in run C.
- Judge the coarse-timing decision: is a 271-clip tail over 180 s acceptable under "retain
  coarse timing rather than an invented seek point", or should those excerpts carry a
  duration marker the client can see? Say which and why.
- The two remaining strict xfails: `test_card_builder_librarian_profile_bounds_adversarial_payloads`
  (Gemini's adversarial test against `library_cards.py`, your module) and SEC-06 (non-ASCII
  dropped by `_fts_query`). For the first, either fix it in `library_cards.py` with the test
  flipped to pass, or state the reproducible reason it should stay open. For SEC-06, scope
  the fix and its risk; do not implement.
- Review the claude worker's server changes as an independent reviewer: the spawn gate,
  `usage_meter.py` transaction semantics, the heartbeat state machine, the Recall fence.
  Reproducible failing cases only; otherwise accept.
- List explicitly what remains unverified (installer build, watchdog recovery, installed
  client, media seek) and what would close each.
- End with one of: ACCEPT / ACCEPT WITH LISTED EXCEPTIONS / REJECT, and the candidate SHA.

## Deliverable 2: `docs/library/PHASE2-CONTRACT-2026-09-04.md`

The Phase 2 dispatch contract you own under the protocol, written so Fable can dispatch it as
the next brief: scope, the frozen semantics from your phase plan (one work row per item,
attempt tokens, apply keys, inverse journal, pins, churn), `0027_library_substrate.sql`
draft, `library_work.py` service surface, the five registry tools plus `undo_library_apply`
with JSON schemas, per-worker ownership and allowed files, gates with exit evidence, and the
dry-run product proof over the frozen copy with no labels applied. Name what Fable must
reserve or decide before dispatch.

Rules: own worktree; commit if git allows, else leave files and say so; never merge or push;
never open the live index. Tests: `PYTHONPATH=. python -m pytest -q tests/ -p no:cacheprovider`.
