# Phase 2 stage 4 result (2026-09-08)

**Verdict: the stage 4 gate is not met, and the record is clean.** With card contract v2
(prose excerpts beside clips) and `claude-opus-5` as the assigner, the measured pass over all
548 targets validates with zero retries and zero rejections. On the sealed, relabelled
hold-out v3 it passes coverage in both strata and fails strict primary precision in both:
timed 39 of 46 (0.848 against 0.90), text-only 6 of 11 (0.545). Astra's replay audit (run
AX) is the record. Apply stayed disabled; zero labels were applied; the live index was never
opened.

| Stratum | N | Assigned | Coverage (>= 0.80) | Strict precision (>= 0.90) | Descendant-tolerant | Any membership |
|---|---:|---:|---:|---:|---:|---:|
| timed_evidence | 47 | 46 | 46/47 = 0.979 PASS | 39/46 = 0.848 FAIL | 41/46 | 43/46 |
| text_only | 13 | 11 | 11/13 = 0.846 PASS | 6/11 = 0.545 FAIL | 7/11 | 6/11 |
| overall | 60 | 57 | 57/60 = 0.950 | 45/57 = 0.789 | 48/57 | 49/57 |

The last two columns are diagnostics the gate does not credit: descendant-tolerant counts
a correct child under a gold parent; any-membership counts the gold shelf appearing as a
secondary. Evidence grounding 57/57. Abstentions 3.

## Two runs

- **Run 1 aborted at completion 542 of 548**: 55 distinct failed completions (10.1%). 79 of
  81 rejections were the service refusing a `reason` field that Opus attaches to assigned
  results and that the CLI output schema permitted; two were quote mismatches. Repair in
  `f72786a`: the result schema is a `oneOf` of two closed shapes, which the CLI's structured
  output honours (probed). Archived at `docs/library/proof/run-stage4-2026-09-07-run1-aborted/`.
- **Run 2 completed**: 69 processes, 548 attempts, 0 retries, 0 rejections, 2,430 s, 720,141
  output tokens, CLI estimate USD 41.31 (subscription; not invoiced), git `861b17a…` at
  execution. Archive: complete at
  `%LOCALAPPDATA%\AgentControlRoom\proof-archives\run-stage4-2026-09-08-run2\` (validates);
  committed copy `docs/library/proof/run-stage4-2026-09-08-run2/` without `http/` and the
  database snapshots, hashed in `SHA256SUMS`.

## What stage 4 established

1. **The card-contract asymmetry was real and is fixed.** Timed coverage rose from 37/47 to
   46/47 once the assigner could cite the same prose the labellers read. The stage 3
   abstentions were a card problem, not a model problem.
2. **A stronger reader closes most of the judgement gap, not all of it.** Timed strict
   precision rose from 28/37 to 39/46 (0.757 to 0.848). Four of the seven timed misses put
   the gold shelf second (Industry twice, Education, the parent); three are parent versus
   Frontier Models calls the adjudicator itself had to "resolve".
3. **Text-only is eleven items.** Five misses, each a single-excerpt judgement (Developer
   Tools versus Frontier Models twice, parent versus child three times). The stratum cannot
   support a 0.90 threshold at this size: one error moves it 9 points.
4. **The labeller ceiling on this rule** (stage 3 measurement, same identities): Grok 0.91,
   Gemini 0.83 on timed; 0.64 and 0.82 on text-only. The assigner now sits inside that band
   on timed and below it on text-only.

## Four measured stages in one table

| Stage | Taxonomy | Cards | Model | Hold-out | Timed coverage | Timed strict precision | Text-only |
|---|---|---|---|---|---:|---:|---|
| 1 (run R) | v1 | v1 | sonnet-5 | old 60 | 34/60 overall | 18/34 overall | (not stratified) |
| 2 | v2 | v1 | sonnet-5 | v2 | 41/47 | 31/41 = 0.756 | 12/13, 11/12 |
| 3 | v3 | v1 | sonnet-5, effort high | v3 | 37/47 | 28/37 = 0.757 | 12/13, 7/12 |
| 4 | v3 | v2 | opus-5 | v3 (relabelled) | 46/47 | 39/46 = 0.848 | 11/13, 6/11 |

## The decision that is Ryan's

The 0.90 strict-primary target was proposed in the phase plan and adopted in the stage 2
gate; Astra recommended keeping it for stage 4. Four stages have not met it, and the last
one sits at the labeller-agreement ceiling. Three honest options:

1. **Keep 0.90 strict** and keep iterating (larger hold-out, more boundary work, a
   third-model adjudicator). Diminishing returns; each stage costs a day and a relabel.
2. **Change the rule** to credit a correct secondary or a correct child (the diagnostics
   above give 43/46 and 41/46 timed). This must be decided before it is measured again, on
   a fresh hold-out, or it is tuning.
3. **Ship with review.** The Librarian was designed as a reversible proposer: preview, apply,
   undo, pins. At 0.85 timed precision and 0.95 coverage with every assignment grounded in a
   verbatim quote, the product can file the library and let the owner correct one in seven.
   The gate then governs *activation on the live library*, which is Ryan's call in any case.

Phases 3 to 6 do not depend on this decision and continue. Nothing is applied to the live
library until Ryan decides.

## What did not change

No push to `origin/main`. `librarian_apply_enabled` stays false. The live index and the
resident helper on port 5179 were never opened.
