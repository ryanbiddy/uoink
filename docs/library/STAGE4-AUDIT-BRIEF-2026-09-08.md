# Run AX brief: stage 4 measured-pass audit (2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. One section, codex only. You are
GPT-6 Astra, independent auditor and plan owner. No model, no helper, no port 5179, no live
index, no commit. Apply stays disabled. Ryan's 2026-09-07 authorization covers this audit.

## Stage 4 audit (C1 to C4 of `STAGE2-AUDIT-PLAN-2026-09-05.md`, applied to stage 4)

Archive: complete at
`C:\Users\hello\AppData\Local\AgentControlRoom\proof-archives\run-stage4-2026-09-08-run2\`
(validates with `--stage4 --require-real`); committed copy
`docs/library/proof/run-stage4-2026-09-08-run2/` without `http/` and the `state/` database
snapshots, all hashed in its `SHA256SUMS`. Aborted run 1 is preserved at
`docs/library/proof/run-stage4-2026-09-07-run1-aborted/` and `proof-archives/...-run1-aborted`;
its repair (the result schema became a `oneOf` of two closed shapes, commit `f72786a`) is
documented in the result. The probe (16 items, PROBE_ONLY) is at
`docs/library/proof/run-stage4-probe-2026-09-07/`. Result document:
`PHASE2-STAGE4-RESULT-2026-09-08.md`.

Freeze: `manifest-stage4-2026-09-07.json` (content hash `61855bf8…`),
`STAGE4-GATE-2026-09-07.md`, `STAGE4-BINDINGS-2026-09-07.md`,
`holdout-v3-stage4-bindings-2026-09-07.json`, `holdout-v3-stage4-labelling-packet-2026-09-07.json`,
`card-contract-v2-diff-2026-09-07.json`, labels `holdout-v3-stage4-labels-{gemini,grok,adjudicated}-2026-09-07.json`
(adjudicated in run AR), sealed `holdout-v3-stage4-gold-2026-09-07.json` and
`holdout-v3-stage4-mapping-2026-09-07.json`, approved taxonomy v3 (`INDUCTION-AUDIT-16`),
execution records `stage4-execution-record-2026-09-07.json` (run 1) and
`stage4-execution-record-2026-09-08-run2.json`.

Stage 4 specifics to establish beyond C1 to C4:

1. The bindings, packet, labels, adjudication, gold and mapping graph resolves as
   `check_stage4_references` requires, and the sealed gold's hold-out identities are the
   stage 3 identities with card hashes re-bound to cards v2 (nothing added or dropped).
2. Card contract v2 replays: every classification in the diff ledger reproduces from
   `library_cards.diff_cards` against the frozen stage 3 and stage 4 cards, and no card
   exceeds the six-excerpt and 8,192-byte budgets.
3. The probe's PROBE_ONLY status is not counted as acceptance anywhere in the record.
4. The `oneOf` schema change is a client-side output-shape repair that leaves the service
   contract (`library_work.py` validation of assigned results) unchanged; say so or say what
   changed.
5. The seal timestamp of the gold precedes the probe and run 2; the manifest content hash
   the receipts cite is the committed manifest's.
6. Guard rule v2 and AO-G1 (anonymous transport events) hold on run 2: 0 retries, 0
   rejections, and the validator's `_check_completion_guard` agrees with the harness.
7. The scorer's mapping acceptance by revision hash (commit `2727b45`, `proof_score.py`) is
   sound: the mapping binds the approved taxonomy v3 revision `8a1b1603…` and nothing else.

Also report the diagnostics the result names (descendant-tolerant and any-membership per
stratum) beside the strict rule, and give your recommendation on the three options in the
result's "The decision that is Ryan's" section. The decision itself is his; your
recommendation goes to him unchanged.

Write `docs/library/STAGE4-AUDIT-2026-09-08.md` with per-check tables and `P2-7 PASS`,
`P2-7 FAIL`, or `RECEIPTS REJECTED`, plus measurements and replay script under
`docs/library/proof/` as `audit-ax-2026-09-08.py` and `audit-ax-measurements-2026-09-08.json`
(parameterize your run AO script; keep earlier files untouched). Do not edit runner, prompt,
scorer, card builder, validator, or any archived artifact. Do not commit.
