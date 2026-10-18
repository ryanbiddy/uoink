# Proof harness conformance (run Q), 2026-09-05: receipts must match Astra's contract

Run P integrated at `27432ef`+: Gemini's `scripts/librarian/proof_run.py` (with the
orchestrator's batching addition, commit `3e086f7`) and Astra's `tests/validate_proof_receipts.py`
plus `PROOF-PLAN-2026-09-05.md`. The freeze is complete (548/548, manifest hash
`213ef46f6853ba2512f584dd202227bb86ccc18691dacd0f76fb0ca636ed8d35`). The mock pass over all
548 items runs, but the validator rejects its receipts: the harness emits its own document
shape while the plan's "Receipt JSON contract" section is normative (Astra owns the
contract under ORCHESTRATION-V1).

## gemini: conform `proof_run.py` output to the receipt contract

Allowed files: `scripts/librarian/proof_run.py`, `scripts/librarian/proof_score.py`,
`tests/test_proof_run.py`. Read `docs/library/PROOF-PLAN-2026-09-05.md` sections "Receipt
JSON contract", "Frozen inputs and hash definitions", "Abort conditions", and the fixture
document built inside `tests/validate_proof_receipts.py` (`--self-test`) as the worked
example. Emit exactly that document: `mode` ("mock" | "subscription"), `status`,
`abort_reason`, `inputs` (every frozen hash as defined), `target_ids`,
`target_manifest_hash`, `config` (client, transport, model, base_url, isolation root,
index/token paths, environment, `anthropic_api_key_unset`, tools, concurrency, max_retries,
wall budget, error-rate limits, output schema text + sha256), `database` (copy sha256
before/after upgrade, source sha256 after, schema before/after), `before`/`after` state,
`attempts` (per attempt, contract fields), `transport_failures`, `targets` (one row per
manifest target with disposition), `preview` (request + response), `totals` with the
contract's keys, `audit_extensions` (put the batching `calls` list and `usage_totals`
here). Keep batching (`--batch`) working: attempts share a call id; totals over calls.
Keep the scorer consistent with the new shape. Exit evidence: `python
tests/validate_proof_receipts.py --receipts <mock-all receipts> --mock` returns
`FIXTURE_VALID`; `--limit 12` and the full mock pass both validate; your tests pass.
Do not edit the validator or the plan; if the contract is ambiguous, say exactly where and
choose the reading the validator accepts.

Rules: own worktree; `--mock` only; never port 5179; never the live index; commit if git
allows, else leave files and say so. Completion packet at the end.
