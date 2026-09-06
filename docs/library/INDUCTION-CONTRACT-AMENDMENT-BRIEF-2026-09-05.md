# Induction contract amendment (run U), 2026-09-05: the one-call consolidation cannot be emitted

Measured, on the subscription client (`claude -p`, `claude-sonnet-5`), Fable, 2026-09-05:

| Consolidation input | Result |
|---|---|
| 1 batch (19 KB, 25 cards) with the full `PROPOSAL_SCHEMA` as `--json-schema` | zero bytes after 5 min (schema `pattern` + `uniqueItems` stall the CLI's structured output) |
| 1 batch with those two constraint kinds stripped | 3 min, 21,584 output tokens, 8 nodes, 25 ledger rows |
| 3 batches (bounded-output prompt) | 10 min, 55,272 output tokens, 9 nodes, 75 ledger rows (about 740 tokens per row, mean 1.5 evidence entries per row) |
| 9 batches (206 KB), three attempts, 15 / 50 / 40 min limits | zero bytes every time |

A 225-row ledger with full evidence objects per row is roughly 165,000 output tokens: beyond a
single response. The nine batch calls succeeded and are archived under
`docs/library/proof/induction-attempts/` (attempt receipts) with their raw call artifacts in
the orchestrator's scratch; their prompts and outputs are reusable byte-for-byte.

## codex (Astra): amend `INDUCTION_RECEIPT_SCHEMA` / `PROPOSAL_SCHEMA` minimally

Allowed files: `tests/validate_proof_receipts.py`, `docs/library/STAGE2-GATE-2026-09-05.md`,
`tests/library_work_astra/**`. Proposed amendment (accept, or state a reproducible reason
and propose another that the model can emit in one call):

1. **Ledger evidence by reference.** A mapped `coverage_ledger` row carries
   `evidence: [{"excerpt_id": <64 hex>}]` (one or more references) instead of full support
   objects. The validator resolves each reference against the frozen card of that
   `video_id` (the excerpt must exist in that card) and against the recorded batch
   dispositions (the batch call for that card must contain a support entry for that
   `excerpt_id` with a verbatim 1-24-word quote). Full evidence therefore remains in the
   immutable batch outputs; the consolidation only cites it.
2. **Node evidence unchanged:** `supporting_evidence` on new nodes keeps the full SUPPORT
   objects (five distinct cards), copied from batch candidates; the validator additionally
   checks each against the batch outputs.
3. **Reason length:** ledger `reason` at most 160 characters; the validator enforces it.
4. **Call-time schema:** the consolidation `--json-schema` may omit `pattern` and
   `uniqueItems`; the validator applies the full schema to the recorded output. Record the
   observed CLI stall in the gate document.
5. Keep the single consolidation call, the byte-identity of the proposal with its output,
   and every other rule. Update `--self-test` fixtures and the mock builder expectations in
   `tests/library_work_astra/test_induction_contract.py`; the mock harness output must still
   validate or you must say exactly what Gemini's mock must change.

Own worktree; no model execution; never the live index; commit if git allows, else leave files
and say so. Completion packet at the end.
