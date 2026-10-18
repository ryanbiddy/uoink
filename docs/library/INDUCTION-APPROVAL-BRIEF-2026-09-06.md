# Run AF brief: approval audit of revision decision 5 (2026-09-06)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. One section, codex only. No model,
no helper, no port 5179, no live index, no commit. Apply stays disabled.

Astra's [decision 4 audit](INDUCTION-AUDIT-13-2026-09-06.md) reviewed all 91 mapped ledger
rows, recorded 20 exact replacements, and set a successor acceptance standard: a successor
composed mechanically from those rows whose canonical proposal hash is
`9863d85647c2fb8781b42993c3eec52255bd68b7bbae240393543906d96cd469` and whose 225-row ledger
hash is `d43012b6f70fbe6ac626e245819343a8456d733995d55845d594549b13d81f70` needs no further
semantic re-review; the final approval must bind the actual successor document and the
integrated candidate SHA.

**Revision decision 5** (`docs/library/proof/taxonomy-v2-revision-decision-5-2026-09-06.json`,
sha256 `f01bd7c2938894211a3efc86c8e08c36f979a737542aecfa29cf45a2578f5ba7`) was built by
`scripts/librarian/compose_revision_decision_n.py --base <decision 4> --measurements docs/library/proof/audit-decision-4-measurements-2026-09-06.json --audit docs/library/INDUCTION-AUDIT-13-2026-09-06.md --expected-counts 44,37,120,24`
(the same command with `--check` reproduces it). Fable measured its canonical proposal hash
and ledger hash: both equal the reviewed values above. Nodes are byte-identical to decisions
3 and 4. The integrated candidate is the commit this brief lands in.

## codex (GPT-6 Astra): confirm and rule

1. Reproduce decision 5 with the composer's `--check`; recompute the canonical proposal and
   ledger hashes (sorted keys, `ensure_ascii=False`, separators `(',', ':')`, no trailing
   newline) and compare with your reviewed values; confirm the 20 edits, unchanged nodes,
   supports, rejections and pin fields, the measurement binding, and full validator success.
   Write `docs/library/proof/audit-decision-5-measurements-2026-09-06.json`.
2. Rule: `APPROVE taxonomy-v2-2026-09-05 (revision decision 5)` or `REJECT` (named). If you
   approve, write in `docs/library/INDUCTION-AUDIT-14-2026-09-06.md` the approval record
   Fable must bind (your run-W list), the projection hashes for this exact document with
   `taxonomy_from_proposal.py --approved-by "Codex / GPT-6 Astra (INDUCTION-AUDIT-14)" --approval-record docs/library/INDUCTION-AUDIT-14-2026-09-06.md`,
   and the fields that must be filled from observation at execution time (service-returned
   revision, disposable database identity, integrated SHA). Fable will then write the
   approved taxonomy file with exactly those arguments, seal the adjudicated labels and
   mapping (run AG), freeze the stage-2 manifest, and record the execution identities before
   the measured pass.

Do not commit. Do not edit runner, prompt, scorer, or any decision file.
