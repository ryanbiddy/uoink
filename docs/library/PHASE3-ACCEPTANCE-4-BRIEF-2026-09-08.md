# Phase 3 acceptance brief, fourth round (run AS-4, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase3-v1-2026-09-07`.
Astra's third review ([PHASE3-ACCEPTANCE-3-2026-09-08.md](PHASE3-ACCEPTANCE-3-2026-09-08.md))
left AS-01, AS-02, AS-03 and AS-06 open with twelve reproductions. Base: the commit this
brief lands in. No worker runs a model, the resident helper, or touches port 5179 or the
live index. Do not commit.

## What changed since AS-3

- **Run AT-4** (Claude worker, integrated at `0bb97c8`): AS-01 citations validated against
  the publisher's artifact projection and clips against the deterministic derivation of
  `clips.build_clips_for_video` (lossless coarse slicing recognised, invented or reordered
  words and expanded timing rejected; contents not counts; a lost start value is damage);
  AS-02 `executor_returned` proof requires an observed invocation bound to start, token and
  incarnation; a persisted O_EXCL execution claim under `DATA_ROOT/source_claims` shared
  across service instances (`claim_execution`, `adopt_execution`, `holds_execution`); child
  ownership persisted by `_run_subprocess` under `DATA_ROOT/source_children` and honoured by
  `probe`; AS-03 manual dispatchers consume the post-lock completeness/identity result;
  AS-06 every identity field compared independently. Your suite: 127 of 127 with
  `PHASE3_REQUIRE_IMPLEMENTATION=1`; companions 365 passed (Fable aligned one legacy test,
  `test_podcast_watch.py`, to claim execution before `run`, since AS-02 changed that
  assumption). The worker disclosed: recovery runs the idempotent publisher under the
  capture lock without taking the execution claim (executor proven stopped, no acquisition);
  the file-based claim is not transactional with the ledger, so a crash between the started
  commit and the claim file leaves an unexecuted intent that reconciliation keeps uncertain.
- **S21** rerun on `0bb97c8` with your launcher: `AUTOMATED PASS`, 0 model calls
  (`docs/library/proof/s21-2026-09-08/receipt-at4-candidate-0bb97c8.json`).
- **Process-recovery receipt** (your AS-2/AS-3 request): a real parent process claimed a
  start, spawned and recorded a real child, and was killed while the child survived; the
  production `probe` (compiled from this checkout's `server.py` as your integration harness
  does) reported `running` while the child lived and `stopped` only after it was killed.
  Launcher `tests/library_work_astra/process_recovery_receipt.py`, receipt
  `docs/library/proof/procrec-2026-09-08/receipt.json`.
- Your AS-3 requests inside the S21 launcher (real incarnation instead of
  `instance_id='s21-disposable'`, capture-lock ownership assertions, full provenance fields)
  are in your own file; Fable did not edit it. Extend it in this run if you want those
  observations before ruling, and Fable will rerun it.
- Companion-count reconciliation: 313 = your 303 plus `tests/test_heartbeat_semantics.py` (10).

## codex (GPT-6 Astra): review and rule

1. Re-run your suite and the companions yourself; report observed counts.
2. Review the four repairs against your AS-3 specifications; rule on the worker's two
   disclosures above.
3. Weigh the S21 rerun and the process-recovery receipt against S13 to S16 and S20 to S22.
4. Rule `PHASE 3 ACCEPTED`, `ACCEPTED WITH CONDITIONS` (named), or `NOT ACCEPTED` (named
   defects with exact repairs and reproducing tests) in
   `docs/library/PHASE3-ACCEPTANCE-4-2026-09-08.md`.

Files you may edit: `tests/library_work_astra/test_phase3_*.py` and the S21 launcher, the
acceptance document.
