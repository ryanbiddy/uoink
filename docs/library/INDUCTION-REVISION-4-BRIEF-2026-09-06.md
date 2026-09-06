# Run AE brief: revision decision 4 audit with a full mapped-ledger review (2026-09-06)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. One section, codex only. No model,
no helper, no port 5179, no live index. Apply stays disabled.

## What changed since run AD

Astra's [decision 3 audit](INDUCTION-AUDIT-12-2026-09-06.md) found all eleven requested
edits correct, resolved B6-S-Agents-Security and B5-R2, and rejected on B5-R3 (three further
sampled ledger destinations: c078, c150, c186, with exact replacement rows in
`docs/library/proof/audit-decision-3-measurements-2026-09-06.json`) and C3-EOL (the bound
decision-2 measurements materialised with CRLF in a fresh worktree, so the composer's
`--check` failed there).

Repairs:

- `.gitattributes` now marks `docs/library/proof/audit-*-measurements-*.json` byte-exact
  (`-text`) and the four existing measurement files were re-staged; a fresh worktree now
  materialises the LF bytes whose hashes the decisions bind. Verify with
  `python -B scripts/librarian/compose_revision_decision_3.py --check` (must exit 0 now).
- **Revision decision 4** (`docs/library/proof/taxonomy-v2-revision-decision-4-2026-09-06.json`,
  sha256 `44702821492c0e27082bafe9dec6e430cc9ce01e0194ade089a1d61a7e90d32a`, built by the
  generic `scripts/librarian/compose_revision_decision_n.py` from decision 3 plus exactly the
  three `exact_proposed_replacement` rows of your decision-3 measurements; `--check` with the
  same arguments reproduces it; the complete proposal validator passes; ledger counts are
  your predicted 60/31/110/24). **Its eleven nodes are byte-identical to decision 3's**; only
  three ledger rows changed.

## Why this brief asks for a full mapped-ledger review

Each audit recalculates a first/middle/last sample per shelf, and each round has surfaced
two or three new failing rows among the ~90 mapped rows while the nodes stayed fixed. That
loop does not converge on its own. This run therefore asks you to review **every mapped
ledger row** (all `existing_concept` and `proposed_concept` rows, 91 in decision 4) against
its cited excerpt and destination definition in one pass, and to record an
`exact_proposed_replacement` for every row that fails, so that the next successor (built
mechanically from your rows by `compose_revision_decision_n.py`) can be the last. Unmapped
and unsupported rows need only the check that no shelf or evidence is claimed. If you judge
the full review out of proportion for the plan, say so and state the sampling standard you
will accept as final.

## Labels

The run AD blind labels (`docs/library/proof/labels/holdout-v2-labels-12-gemini-2026-09-06.json`,
`...-12-grok-...`, packet 12, sha256
`e571d4d82a5e80b67adef14d4fa336693bce41d2da724a92d0ac4ddfead926e0`) were produced against
decision 3's nodes. Decision 4's nodes are byte-identical, and labels depend only on the
nodes and the cards. Fable proposes to carry those labels forward to adjudication against
decision 4 (or a ledger-only successor) rather than relabel. Packet 13
(`docs/library/proof/holdout-v2-labelling-packet-13-2026-09-06.json`, sha256
`5610d5a663550e04735e1ed47dd5ec791f9c585b7296fd7b92eb19341d8b137c`) exists for the record;
its `taxonomy_candidate.nodes` equal packet 12's. Confirm or reject that carry-forward; do
not open the label files.

## codex (GPT-6 Astra): audit revision decision 4 and rule on approval

1. `python -B scripts/librarian/compose_revision_decision_3.py --check` and
   `python -B scripts/librarian/compose_revision_decision_n.py --base <decision 3> --measurements <decision-3 measurements> --audit docs/library/INDUCTION-AUDIT-12-2026-09-06.md --expected-counts 60,31,110,24 --out <decision 4> --check`
   must both exit 0. Verify the three edits and that nothing else changed.
2. Replay your decision audit for decision 4 (write
   `docs/library/proof/audit-decision-4-measurements-2026-09-06.json`): B4 (20 supports),
   B6 (all boundaries; nodes unchanged), and B5 as the full mapped-ledger review above.
3. Rule: `APPROVE taxonomy-v2-2026-09-05 (revision decision 4)`, `APPROVE WITH CONDITIONS`
   (named, and whether they block the measured pass), or `REJECT` with the complete set of
   exact replacements so the successor is final. If you approve, write the approval record
   contents Fable must bind and confirm the projection hashes for this exact document with
   `taxonomy_from_proposal.py --approved-by "Codex / GPT-6 Astra (INDUCTION-AUDIT-13)" --approval-record docs/library/INDUCTION-AUDIT-13-2026-09-06.md`.
   State explicitly whether the packet-12 labels may be carried forward.

Write `docs/library/INDUCTION-AUDIT-13-2026-09-06.md`. Do not commit. Do not edit runner,
prompt, scorer, or any decision file.
