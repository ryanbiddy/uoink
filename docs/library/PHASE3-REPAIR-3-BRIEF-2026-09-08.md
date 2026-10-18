# Phase 3 repair brief, round 3 (run AT-4, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Astra's third review
([PHASE3-ACCEPTANCE-3-2026-09-08.md](PHASE3-ACCEPTANCE-3-2026-09-08.md)) is NOT ACCEPTED:
AS-04 and AS-05 stay closed; AS-01, AS-02, AS-03 and AS-06 are each partly closed and each
has a remaining, exactly specified gap with reproducing tests in
`tests/library_work_astra/test_phase3_acceptance3.py` (12 failed, 115 passed on `69c87b6`
with `PHASE3_REQUIRE_IMPLEMENTATION=1`). Base: the commit this brief lands in. No worker
runs a model, the resident helper, or touches port 5179 or the live index. Do not commit;
Fable integrates and runs every test.

Companion-count reconciliation for Astra: Fable's 313 = Astra's 303 plus
`tests/test_heartbeat_semantics.py` (10), which the AT-2 worker listed and Astra's original
selector did not.

## claude (Fable 5.1 worker): close the four remaining gaps

Budget rule: no subagents; targeted searches only (`_evidence_defect`, `inspect_publication`,
`executor_returned`, `claim_execution`, `execute_started`, `_manual_extraction_ownership`,
`already_captured`, `podcast_identity_conflict`); write code early.

- **AS-01, derivation not word sets.** Replace the case-folded word-set check in
  `_evidence_defect` with validation of persisted citations against the publisher's
  artifact projection (text, timing, provenance, not counts) and of clips against the
  deterministic output of `clips.build_clips_for_video` (or an equivalent derivation check
  honouring its de-overlap rules, ordered text, source intervals and links), recognising
  its lossless coarse slicing of a single long token while rejecting invented or reordered
  words and expanded timing. `inspect_publication` in `server.py` compares contents, not
  counts. Absence of timed evidence must be established from agreeing artifacts and index
  data; a lost start value is damage, not an untimed source. Same rule at completion,
  restart and linking; keep the working local-stage recovery; no outbox before validation.
  Tests: six variants of `test_as3_s16_publication_requires_artifact_and_clip_agreement`,
  `test_as3_s16_real_coarse_clip_slices_are_valid_derivation`.
- **AS-02, proof and shared dispatch state.** The `executor_returned` branch must verify an
  observed invocation and its return bound to start, token and incarnation; an empty
  registry with only the label fails. Make the execution claim atomic and shared across
  service instances (persisted, not a service-local set), checked before acquisition,
  after lock waits and before publisher writes; replaying an active start must not
  schedule a second executor; recovery distinguishes unexecuted intent from executing or
  uncertain. Complete the executor/child fencing: `_run_subprocess` persists child
  ownership (pid, start, incarnation) and `probe` cannot treat a dead parent as stopped
  while a recorded child is alive; the final ledger fence alone is insufficient. Tests:
  `test_as3_s13_empty_registry_does_not_verify_executor_returned`,
  `test_as3_s14_two_service_instances_cannot_dispatch_one_start_twice`. Fable will run the
  disposable process-recovery receipt (parent killed, child surviving) after integration;
  say exactly which files record child ownership so that receipt can inspect them.
- **AS-03, consume the recheck.** Manual dispatcher paths must consume the post-lock
  completeness/identity result: a request that waited behind a successful capture reuses
  the completed result (no `_fetch_metadata`, no second acquisition); an identity conflict
  blocks before overwrite; an explicit refresh is a separate user action, never inferred
  from having waited. Both orderings, including podcast work. Test:
  `test_as3_s15_manual_waiter_reuses_standing_completion`.
- **AS-06, every available field.** `podcast_identity_conflict` compares each available
  feed URL, GUID, capture key and episode binding independently; a present contradictory
  field is a conflict even when its partner is absent; an affirmative full-identity
  binding is required before any write. Tests: both variants of
  `test_as3_s15_podcast_publisher_checks_each_available_identity_field`.

Astra's rulings on your three questions stand: no 90 percent threshold; the manual
recheck is not informational; the bounded three-start failure path for caption-less
screenshot-only videos is permitted under v1 with charged starts and no invented timing.

Acceptance target, not to be edited: all of `tests/library_work_astra/test_phase3_*.py`
(127 tests) green, plus the service (111), dashboard (31), legacy, adapter (98, registry
85), podcast and packaging suites. Adjust an existing service test only where a repair
legitimately changes its assumption, and say which. Cite the finding id at each repair.
You cannot run a shell: list the exact pytest commands.
