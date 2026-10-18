# Phase 3 acceptance brief, third round (run AS-3, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase3-v1-2026-09-07`.
Astra's second review ([PHASE3-ACCEPTANCE-2-2026-09-08.md](PHASE3-ACCEPTANCE-2-2026-09-08.md))
left AS-01, AS-02, AS-03 and AS-06 open with twelve reproducing tests. Base: the commit
this brief lands in. No worker runs a model, the resident helper, or touches port 5179 or
the live index. Do not commit.

## What changed since AS-2

- **Run AT-3** (Claude worker, integrated at `d479899`): the four open repairs in
  `source_subscriptions.py`, `server.py` and `podcasts.py`, implementing your clips ruling
  (missing clips only without timed evidence) and your proof-default ruling (base
  `verify_proof` returns `False`; `_backend_call` retained for the other four methods). Your
  suite: 115 of 115 with `PHASE3_REQUIRE_IMPLEMENTATION=1`, including all twelve round-2
  reproductions; companions 313 passed. The worker disclosed three open questions in its
  report (a 90 percent cited-word threshold for clip derivation to tolerate the coarse
  mid-word cut in `clips.py`; the manual-path corpus recheck being informational; a
  caption-less video with screenshots consuming three charged starts before blocking).
- **S21** executed by Fable twice: on `61eeb07` with a diagnostic launcher copy, then on
  `d479899` with your repaired launcher (`AUTOMATED PASS`, 0 model calls, 0 forbidden
  attempts); dashboard observation screenshots from the first run.
  [PHASE3-S21-RECEIPT-2026-09-08.md](PHASE3-S21-RECEIPT-2026-09-08.md),
  `docs/library/proof/s21-2026-09-08/`.
- **S22** staged-tree receipt: [PHASE3-S22-RECEIPT-2026-09-08.md](PHASE3-S22-RECEIPT-2026-09-08.md)
  (source-only staging, imports with the checkout absent, real stdio session in an isolated
  profile). The installed Inno package run is still owed and needs Ryan.
- Later commits on the branch touch Phase 4 and Phase 5 files, not the Phase 3 modules;
  confirm from `git log -- source_subscriptions.py server.py podcasts.py`.

## codex (GPT-6 Astra): review and rule

1. Re-run your suite and the companion suites yourself; report observed counts.
2. Review the four repairs against your exact specifications; rule on the worker's three
   disclosed questions.
3. Weigh the S21 and S22 receipts against gates S20 to S22; say what remains owed for an
   installed-build receipt and whether it blocks acceptance or is a named condition.
4. Rule `PHASE 3 ACCEPTED`, `ACCEPTED WITH CONDITIONS` (named), or `NOT ACCEPTED` (named
   defects with exact repairs and reproducing tests) in
   `docs/library/PHASE3-ACCEPTANCE-3-2026-09-08.md`.

Files you may edit: `tests/library_work_astra/test_phase3_*.py` (only to add tests for a
defect you find), the acceptance document.
