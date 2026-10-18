# Phase 3 acceptance brief (run AS, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase3-v1-2026-09-07`
([PHASE3-CONTRACT-2026-09-07.md](PHASE3-CONTRACT-2026-09-07.md)). Base: the commit this brief
lands in. No worker runs a model, the resident helper, or touches port 5179 or the live
index. Do not commit; Fable integrates and runs every test.

## Integrated state

- Run AM integrated at `560c062` (service `source_subscriptions.py`, migration 0028, scheduler
  detection/capture passes in `server.py`, four registry tools, adapter routing in
  `podcasts.py` and `mobile_playlists.py`, dashboard consent UI). Fable's fixes: globally
  unique operation keys in the fixtures (the DDL makes `operation_key` a primary key) and an
  XML-legal control character in S07.
- Run AP (claude worker) aligned the thirteen legacy tests to the contract (`fbc8804`).
- Passing on the integrated candidate: 39 service tests (`tests/test_source_subscriptions_*.py`),
  31 dashboard tests, 38 aligned legacy tests, 22 adapter-registry tests (registry count 81).
- Packaging (S22): `source_subscriptions.py` is in `build.ps1` and `installer/uoink.iss`;
  migrations ship by glob; packaging tests pass. An installed-tree run is not yet done.
- Astra's independent suite (`tests/library_work_astra/test_phase3_*.py`, run AM) errors at
  setup: its harness assumed constructor arguments (`capture_backend=`, `publication=`,
  `crash_hook=`) and adapter keys the implementation does not expose (the service takes
  `index`, `clock` callable, `adapters` dict, `backend`, `instance_id`, `jitter`).

## codex (GPT-6 Astra): align, review, and rule

1. Align your suite to the real interface (`source_subscriptions.py`; read
   `tests/source_subscriptions_fixtures.py` for the fakes the service tests use). Keep your
   gates' semantics; where the implementation offers no seam for a fault injection you need
   (crash between durable steps), add the smallest test-only seam you can justify in the
   service and name it. Every test that then fails is a finding against the implementation,
   not the test: record each with a reproduction.
2. Review the integrated implementation for the contract's deduplication, persisted start
   reservations, restart reconciliation and post-commit handoff sections (your ownership per
   the phase plan), plus the two adapter edits and the scheduler rewrite in `server.py`.
3. Specify S21, the controlled end-to-end capture, as an executable procedure Fable runs on
   a disposable helper: a local fixture feed served from the loopback interface with an
   explicit fixture-only network allowance, a synthetic timed transcript, taxonomy v3 and
   the frozen prompt configured, and the expected observations (one item lands once with
   provenance and clips, an unfiled visible state, one Phase 2 work row created only after
   commit, zero model calls).
4. Rule `PHASE 3 ACCEPTED`, `ACCEPTED WITH CONDITIONS` (named), or `NOT ACCEPTED` (named
   defects with exact repairs), in `docs/library/PHASE3-ACCEPTANCE-2026-09-08.md`. Include the
   exact pytest commands Fable must run.

Files you may edit: `tests/library_work_astra/test_phase3_*.py`, any new test-only seam in
`source_subscriptions.py` (named in the report), the acceptance document.
