# Phase 2 stage 3 brief: boundary repair, hold-out v3, and the measured pass (2026-09-07)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Ryan's standing authorization
(2026-09-07: "do it all and keep it going, don't stop until all phases done") covers the
subscription execution of stage 3 and the phases after it; the main-merge gate stays his.
Apply stays disabled throughout. No worker runs a model, the helper, or touches port 5179
or the live index.

## Why stage 3

Stage 2 ([result](PHASE2-STAGE2-RESULT-2026-09-06.md), [audit](STAGE2-AUDIT-2026-09-06.md))
met coverage in both strata and strict precision in the text-only stratum, and failed timed
strict precision 31/41. Astra reproduced the numbers and rejected the receipts as a record on
two tooling defects (AH-R1 redaction, AH-R2 scorer refusal), both repaired in `e76a484`. The
eleven errors are boundary calls: Education versus Developer Tools for teaching content (4),
parent versus child (5), Industry versus Frontier Models (1), Developer Tools versus Agents
(1). Hold-out v2 and its adjudicated labels are therefore **development data** from now on.

## Fable's reservations and decisions

1. **Base:** the commit this brief lands in (parent `7559120`).
2. **Taxonomy v3 candidate** (`docs/library/taxonomy-v3-2026-09-07.json`, status `candidate`,
   revision `f0a2d533…`, parent `taxonomy-v2-2026-09-05` revision `bd9e7f9d…`) is a
   reviewer-authored revision built by `scripts/librarian/compose_taxonomy_v3.py` from the
   approved v2: same eleven shelves, ids and paths; twelve recorded edits to definitions and
   cues of six shelves, each naming its development cases
   (`docs/library/proof/taxonomy-v3-revision-decision-2026-09-07.json`). Rules R1-R5 are in
   the script header. The service accepts the v1 -> v2 -> v3 lineage (dry run on a temp
   index); the harness now approves the whole bound lineage before activation.
3. **Assignment prompt** (`scripts/librarian/prompts/assign.md`): rules 4 and 5 rewritten as
   explicit parent-versus-child and dominant-subject procedures (Fable, rule 1; Gemini is the
   prompt owner and may amend in a later run). Frozen for stage 3 at the stage-3 freeze.
4. **Hold-out v3:** 60 identities, 47 timed and 13 text-only, drawn from the pool that
   excludes the 225 induction ids, the old 60 and hold-out v2's 60 (expected 226 eligible),
   seeded from the first 16 hex characters of the stage 2 archive receipts sha256
   (`docs/library/proof/run-stage2-2026-09-06/receipts.json`), same algorithm as v2. If the
   timed pool is short of 47, draw all timed identities and record the shortfall; the gate's
   minimum counts scale with the actual denominators.
5. **Execution variables** for the measured pass: `claude-sonnet-5`, batch 8, concurrency 4,
   `--effort high` for assignment calls (declared change from stage 2's default effort;
   recorded in every call's argv), otherwise identical to stage 2. One pass, no reruns.
6. **Owners this run:** Astra = `tests/validate_proof_receipts.py` (`stage3_freezes`,
   `--freeze-stage3`, `--verify-stage3-freezes`), `docs/library/proof/holdout-v3-2026-09-07.json`,
   `docs/library/STAGE3-GATE-2026-09-07.md`, the audit of the v3 decision and prompt
   amendment. Nobody else edits this run.
7. **After this run (Fable):** build the v3 labelling packet from the frozen hold-out v3 and
   the v3 candidate; Gemini and Grok label blind; Astra adjudicates; seal; `--stage3 --freeze`;
   execution record; one measured pass; validator; scorer; Astra C-audit; result document.

## codex (GPT-6 Astra): freeze, gate, and rule on the v3 revision

1. Implement `stage3_freezes()` and the `--freeze-stage3` / `--verify-stage3-freezes` flags in
   your validator, mirroring stage 2 (reservation 4 above), and write
   `docs/library/proof/holdout-v3-2026-09-07.json` with `labels_status: sealed-labels-pending`,
   the seed, pool hash, counts, source revisions and card hashes, and the feasibility bound.
   Verify that no v3 identity appears in the 225, the old 60, or hold-out v2.
2. Write `docs/library/STAGE3-GATE-2026-09-07.md`: the same table as the stage 2 gate with the
   actual v3 denominators, the frozen identities and hashes, the declared execution variables,
   and the "Before execution" list.
3. Audit the v3 revision decision and the prompt amendment as you audited the v2 decisions:
   every edit reproduces (`compose_taxonomy_v3.py --check`), ids/paths/node set unchanged,
   definitions and cues agree, precedence survives projection in both directions for every
   boundary named in rules R1-R5, no development-case text or hold-out v3 content leaks into
   cues or the prompt, and the service revision reproduces. Rule `APPROVE taxonomy-v3-2026-09-07`,
   `APPROVE WITH CONDITIONS`, or `REJECT` with exact edits. If you approve, give the exact
   `compose_taxonomy_v3.py --approved-by ... --approval-record ...` arguments and the expected
   approved-file hash and revision hash.

Write `docs/library/INDUCTION-AUDIT-15-2026-09-07.md` for the ruling. Do not commit; Fable
collects your files. Do not edit runner, prompt, scorer, or the decision file.
