# Phase 3 acceptance rerun brief (run AS-2, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase3-v1-2026-09-07`.
Astra's first review ([PHASE3-ACCEPTANCE-2026-09-08.md](PHASE3-ACCEPTANCE-2026-09-08.md)) ruled
NOT ACCEPTED on AS-01 to AS-06. The repairs are integrated; this run rules on the integrated
candidate. Base: the commit this brief lands in. No worker runs a model, the resident helper,
or touches port 5179 or the live index. Do not commit.

## What changed since the first review

- **Run AT-2** (Claude worker, integrated at `25e89e1`): the six repairs in
  `source_subscriptions.py`, `server.py` (`_ServerCaptureBackend`: durable publication
  inspection and recovery, per-incarnation process identity, completion proofs, cross-process
  capture lock) and `podcasts.py` (provenance carries the normalized feed URL, GUID and
  capture key; `CorpusIdentityConflict`). The worker's own account of each repair, and the
  assumptions it changed in the existing service tests (bare completions no longer succeed;
  completion requires staged evidence; S16 partial publication yields no outbox), is in the
  commit and in the test diffs.
- **Fable's integration edit**: `_backend_call` in `source_subscriptions.py` resolves the five
  new backend methods (`acquire`, `release`, `verify_proof`, `inspect_publication`,
  `recover_publication`) to the `CaptureBackend` base rules for a duck-typed backend that does
  not define them. Your fake backend defines none, so without it 21 of your tests failed on
  `AttributeError`; with it, 103 of 103 pass. Rule on whether that resolution is sound (the
  base rules use only `published_video_id` and `kind`) or whether your fake should implement
  the new methods instead.
- **Fable's legacy alignment** (`562ac70`): four legacy tests missed by run AP now encode the
  contract (registry count 81; a linked feed archives instead of deleting; the ungated legacy
  poll refuses `managed_by_subscription` with no network I/O).
- Suites on the integrated candidate: your `tests/library_work_astra/test_phase3_*.py` 103
  passed with `PHASE3_REQUIRE_IMPLEMENTATION=1`; service, dashboard, legacy, adapter, podcast
  and packaging suites 313 passed.

## codex (GPT-6 Astra): review and rule

1. Re-run your suite and the suites above yourself; report observed counts, not Fable's.
2. Review each of the six repairs against the exact repair you specified. Where the worker
   chose a narrower form (it requires clips only when transcript citations exist, so a
   caption-less YouTube capture can complete; your fixture requires clips unconditionally),
   rule which form the contract requires.
3. Review the worker's two disclosed limits: rows written before the repair carry the old
   owner identity and probe as `unknown` until their worker reports; per-incarnation files
   are not pruned. Rule whether either blocks acceptance.
4. Rule `PHASE 3 ACCEPTED`, `ACCEPTED WITH CONDITIONS` (named), or `NOT ACCEPTED` (named
   defects with exact repairs) in `docs/library/PHASE3-ACCEPTANCE-2-2026-09-08.md`. Restate
   the S21 procedure Fable must run if anything in it changed with the repairs.

Files you may edit: `tests/library_work_astra/test_phase3_*.py` (only to add tests for a
defect you find; say which), the acceptance document.
