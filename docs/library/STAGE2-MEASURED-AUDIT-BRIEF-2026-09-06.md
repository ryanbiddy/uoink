# Run AH brief: stage 2 measured-pass audit (2026-09-06)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. One section, codex only. You are
GPT-6 Astra, independent auditor and plan owner. Replay section C (C1 to C4) of
`STAGE2-AUDIT-PLAN-2026-09-05.md` against the archived measured pass and rule on the stage 2
gate (`STAGE2-GATE-2026-09-05.md`). Ground rules of the plan apply: replay from raw
artifacts, never trust `receipts.json` alone, no model, no helper, no live index, no port
5179. Apply stays disabled.

## Archive

- Measured pass: `docs/library/proof/run-stage2-2026-09-06/` (`receipts.json`, `calls/`,
  `http/`, `state/`, `heads/`, `fingerprints/`, `harness.log`, `report.md`). Hashes are in
  `docs/library/proof/run-stage2-2026-09-06/SHA256SUMS` and in the result document.
- Pre-execution record: `docs/library/proof/stage2-execution-record-2026-09-06.json`
  (written at `9de497e`, committed as `746045d`; the harness ran at `746045d`).
- Stage-2 manifest: `docs/library/proof/manifest-stage2-2026-09-05.json`.
- Approved taxonomy: `docs/library/taxonomy-v2-2026-09-05.json` (revision `bd9e7f9d…`,
  approval record `INDUCTION-AUDIT-14-2026-09-06.md`).
- Sealed labels and mapping: `docs/library/proof/labels/holdout-v2-gold-2026-09-05.json`,
  `docs/library/proof/labels/holdout-v2-mapping-2026-09-05.json`, adjudicated from
  `holdout-v2-labels-adjudicated-12-2026-09-06.json` (run AG) with the packet-12 labels
  carried forward under your INDUCTION-AUDIT-13 ruling.
- Validator and scorer outputs: `docs/library/proof/run-stage2-2026-09-06/validation.json`
  and `report.md` (scorer, with `--mapping`).

## What to establish

1. C1: freezes, sealed hashes and timestamps precede execution; one taxonomy revision and one
   prompt hash across all attempts; the service-returned revision equals the expected
   `bd9e7f9d…`; no hold-out v2 card in any prompt example or tuning artifact.
2. C2.1 to C2.9 as written, including the error guard, deadline and concurrency sweep, HTTP
   history, registry export and snapshots, heads, portability, and the four CLI counters.
3. C3: evidence replay on every accepted membership, primaries and secondaries.
4. C4: the strict versioned quality rule per stratum with raw numerators, plus the
   diagnostics and the unchanged old-60 regression, the 225 development outcomes, unmappable
   over-assignment and sibling errors.

Write `docs/library/STAGE2-AUDIT-2026-09-06.md` with per-check tables and one of
`P2-7 PASS`, `P2-7 FAIL` (quality), or `RECEIPTS REJECTED` (record defects), plus the
measurements file and replay script under `docs/library/proof/`. Do not commit. Do not edit
runner, prompt, scorer, or any archived artifact.
