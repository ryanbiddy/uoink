# Induction contract amendment 2 (run V), 2026-09-05: reference by short key, not by hash

Under contract v1.1 (run U) the consolidation ran twice more on the reused batches at low
effort with the by-reference ledger prompt:

| Attempt | Result |
|---|---|
| 4 | completed in 12 min, 14 nodes (7 preserved + 7 new, each with 5+ distinct cards), 224 ledger rows, dispositions 105 proposed / 36 existing / 75 unmapped / 8 unsupported. Validator: INVALID. Exactly 3 transcription defects in about 350 hand-copied identifiers: one node support `card_hash` off by characters, one ledger `video_id` mistyped, one ledger id dropped. `docs/library/proof/induction-attempts/attempt4-*.json` |
| 5 | same prompt plus a mandatory identifier self-check paragraph: zero bytes after 40 min (the check pushed deliberation past the budget). |

The taxonomy the model induced is sound and grounded; what fails is asking a language model
to retype 19-digit ids and 64-hex hashes verbatim hundreds of times. The proposal must stay
byte-identical to the consolidation output, so the fix must be in what the model is asked
to write.

## codex (Astra): amend the induction contract so references are short keys

Allowed files: `tests/validate_proof_receipts.py`, `tests/library_work_astra/**`,
`docs/library/STAGE2-GATE-2026-09-05.md`. Proposed amendment (accept or propose a
reproducible alternative the model can emit reliably):

1. **Key assignment is deterministic and recorded.** The consolidation prompt template gains
   a `{{KEYS}}` slot (exactly one) that the harness fills with a key table derived from the
   batch outputs: every card gets `card_key` = `c` + 3-digit index in manifest order; every
   support entry in a batch candidate or disposition gets `support_key` = `card_key` + `-` +
   index within that card's evidence in batch order. The table maps keys to the full
   identifiers. The validator re-derives the table from the recorded batch outputs and
   requires the consolidation stdin to equal the template with `{{KEYS}}` and
   `{{PROPOSALS}}` filled.
2. **The proposal references keys.** `coverage_ledger` rows: `card_key` instead of
   `video_id`, `evidence: [{"support_key": ...}]`. Node `supporting_evidence`:
   `[{"support_key": ...}]`. The validator expands every key against its re-derived table;
   an unknown key is a validation failure; the expanded document is what
   `validate_induction_proposal` checks (five distinct cards, quotes verbatim, 24 words,
   evidence belongs to the row's card, etc.). The receipt's `proposal` stays the exact
   consolidation output; add `proposal_expanded` (validator-computed, recorded for the
   audit) or document that expansion is recomputed at validation time.
3. Keep every other rule from v1.1, the single consolidation call, and the 160-character
   reasons. Update `--self-test`, the contract fixture in
   `tests/library_work_astra/test_induction_contract.py`, and state the exact mock builder
   changes Gemini must make. Do not edit the runner or prompts.

Own worktree; no model execution; never the live index; commit if git allows, else leave files
and say so. Completion packet at the end.
