# Proof harness v2 emission (run T), 2026-09-05: emit the v2 receipt document exactly

Run S integrated at `9df478b`+ (1,039 passed). A real 16-item probe with the repaired
harness (run id `proof-probe-s16b`, kept by the orchestrator outside the repo) wrote `calls/`, `http/` and
`state/` artifacts but the receipts document is still schema v1: `schema_version` 1 and no
top-level `calls`, `completion_order`, `http_history`, `execution`, `state_artifacts`,
`accounting`, or `totals.item_attempts` (81 errors against `V2_RECEIPT_SCHEMA`; attempts
also carry `call_id`, which v1 forbids). The validator's exported schema is committed at
`docs/library/proof/receipt-schema-v2-export.json`; the normative definitions are the
`*_SCHEMA` objects in `tests/validate_proof_receipts.py` and the field table in
`docs/library/STAGE2-GATE-2026-09-05.md`.

## gemini: make `proof_run.py` emit `V2_RECEIPT_SCHEMA` exactly, in both modes, and `induce_run.py` emit `INDUCTION_RECEIPT_SCHEMA`

Allowed files: `scripts/librarian/proof_run.py`, `scripts/librarian/induce_run.py`, `tests/test_proof_run.py`, `tests/test_induce_run.py`.

Second deliverable: the induction receipts. A `--mock` induction run currently produces a
document with 956 errors against `INDUCTION_RECEIPT_SCHEMA` (missing `kind`, `abort_reason`,
`batch_prompt`, `consolidation_prompt`, `taxonomy`, `batches`, `consolidation_call_id`,
`proposal_artifact`, `accounting`, `execution`; forbidden `contract_version`,
`coverage_ledger`, `input_card_ids`, `proposal_file`, `supporting_evidence`, ...; empty
`calls`). Emit that schema exactly, including the `calls[]` records with artifact references
for the batch and consolidation processes, and make the proposal validate under
`PROPOSAL_SCHEMA`. Exit test: `python tests/validate_proof_receipts.py --receipt-kind induction
--receipts <mock receipts> --mock` reports a valid status, or the exact function-level failure. Emit
`schema_version: 2` always. Every section per the gate table: `calls[]` (call_id, ordered
attempt_ids, argv, schema_text + schema_sha256, stdin/stdout/stderr as artifact references
`{path, sha256, bytes}` relative to the receipt directory with forward slashes,
start/end monotonic ns, exit_status, timed_out, cancellation), attempts with `call_id`,
`model_result`, `claim_event_id`, `submit_event_ids`; `completion_order[]`; targets with
`terminal_service_state`; transport events with `http_event_id` and `occurred_monotonic_ns`;
`totals` with `model_calls = len(calls)`, `item_attempts = len(attempts)`, exact stdin /
stdout / stderr / schema byte totals per process; `accounting` exactly as
`call_accounting(calls)` in the validator (import and reuse it, do not reimplement);
`execution` (checkout root, git sha, run start/end monotonic ns, fingerprints of runner,
scorer, validator, service, prompt, card builder, and `cleanup`); `http_history[]` with
request/response artifacts under `http/`, redaction, `resend_of`; `state_artifacts`
(registry export, before/after snapshots and DB images with WAL checkpointed, journal,
source, upgraded, corpus_heads). Mock mode emits the same v2 shape with mock processes.

Exit test, no model execution: a `--mock --limit 12` run whose document passes
`jsonschema.Draft202012Validator(V2_RECEIPT_SCHEMA)` with zero errors AND
`validate_receipts(doc, manifest, require_real=False, artifact_root=out, require_whole_manifest=False)`
if the validator accepts v2 mock documents; otherwise report the exact function-level
failure. Keep the existing tests passing. The orchestrator then runs a real 16-item probe
through `validate_receipts(..., require_real=True, ...)`.

Rules: own worktree; `--mock` only; never port 5179; never the live index; commit if git
allows, else leave files and say so. Completion packet at the end.
