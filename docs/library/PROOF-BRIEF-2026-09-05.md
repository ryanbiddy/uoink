# Product proof dispatch (run P), 2026-09-05: build the P2-7 harness, no model execution yet

Phase 2 stage 1 accepted at `de51277` (run O). Contract `phase2-v1.2`, section "Frozen-copy
product proof, applying no labels". Ryan authorized continuing; the proof itself runs on his
Claude subscription, so this run BUILDS and DRY-TESTS the harness with `--mock` only. The
orchestrator executes the real pass afterwards and Astra audits the receipts (run Q).

## Fable's decisions for the proof

1. **Client and transport:** the harness is the subscription client. It drives the real
   claim -> reason -> submit loop over the HTTP registry (`/tools/claim_library_work`,
   `/tools/submit_library_result`, `/tools/apply_reshelving` in preview mode) against an
   isolated helper, and calls `claude -p --json-schema ... --output-format json --tools ""`
   for the reasoning step with the assign prompt, the frozen taxonomy and one librarian-profile
   card. The model never calls tools; the harness does. State this in the report.
2. **Isolated helper:** a launcher sets `LOCALAPPDATA`, `APPDATA`, `TEMP`, `TMP`,
   `UOINK_OUTPUT_DIR` to a disposable root under `_scratch/proof/`, copies the named index
   copy (sha256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`) to
   `<root>/Uoink/index.db`, imports `server`, sets `server.PORT = 5180`, and runs `main()`
   in a thread. It reads the helper's per-install token from the isolated helper's token
   file (the one `server.TOKEN_PATH` points at under that root). It never touches
   `127.0.0.1:5179` or `%LOCALAPPDATA%\Uoink`. Verify the source hash before copying.
3. **Frozen inputs:** `docs/library/taxonomy-v1-2026-09-04.json` (approve it through
   `approve_taxonomy` and activate), `scripts/librarian/prompts/assign.md`, card profile
   `librarian` (schema 1, `spread-longest-v1`, 6 x 240 chars, 8,192-byte cap), hold-out
   `docs/library/holdout-split-2026-09-04.json`. Record every hash in the receipt. Held-out
   labels never enter any prompt.
4. **Scope and budget:** the whole 548-item manifest, one run, at most one retry per
   rejected model result, wall-time budget 2 hours, concurrency 4 `claude -p` processes,
   `--model claude-sonnet-5` unless `--model` overrides. Subscription only. No paid API key
   in the environment (assert `ANTHROPIC_API_KEY` is unset).
5. **Thresholds:** coverage floor 0.80 and primary-shelf precision 0.90 per stratum on the
   60 held-out items (timed-evidence and text-only strata, remeasured), abstentions excluded
   from precision and counted against coverage. Report numerator, denominator and abstention
   counts. `librarian_apply_enabled` stays false; preview only; zero applied labels asserted
   before and after.

## gemini: `scripts/librarian/proof_run.py` + scorer + tests

Allowed files: `scripts/librarian/proof_run.py` (new), `scripts/librarian/proof_score.py`
(new), `scripts/librarian/prompts/assign.md` (only if a placeholder is missing),
`tests/test_proof_run.py` (new). Requirements:
- `proof_run.py --source <copy> --out <dir> [--mock] [--limit N] [--model M] [--concurrency N]`.
  With `--mock`, the reasoning step returns a deterministic fixture assignment (right label
  for gold items, `unmapped` for others) so the whole loop, helper, HTTP calls and receipts
  are exercised with zero model calls. Without `--mock`, it calls `claude -p` as in decision 1
  and records the CLI's JSON `usage` (input/output/cache tokens, `total_cost_usd` as the
  CLI's estimate, model id) or `usage.status=unavailable`.
- Receipts (`<out>/receipts.json`): every attempt including rejects and transport failures;
  per item: work_id, attempt_token, packet_hash, card bytes, prompt bytes, response bytes,
  wall ms, outcome (accepted/rejected/unmapped/unsupported/pinned/deleted/changed), rejection
  reason, evidence quote and basis. Totals: serialized input bytes, wall time, retries.
- `proof_score.py --receipts <file> --holdout <split>`: precision and coverage per stratum
  with counts, evidence identity/quote checks, and a `report.md` with observed versus the
  thresholds. Never prints PASS from an estimate; usage is labeled measured only when the
  CLI returned it.
- Projection revision, memberships, pins, taxonomy activation recorded before/after; assert
  identical and zero applies.
- Tests: `--mock --limit 12` end to end on a fixture copy in `tmp_path` with the helper on an
  ephemeral port; scorer on a fixture receipts file; refusal to start if `ANTHROPIC_API_KEY`
  is set or port 5179 is targeted.

## codex (Astra): freeze, receipt schema, and the execution plan

Allowed files: `docs/library/PROOF-PLAN-2026-09-05.md` (new), `docs/library/proof/manifest-2026-09-05.json`
(new), `tests/validate_proof_receipts.py` (new). Freeze the target manifest from the named
copy (ordered `(video_id, source_revision)` plus exclusions, `manifest_hash`), the taxonomy
revision hash, prompt and card-profile hashes, and the held-out id list hash. Define the
receipt JSON schema the harness must emit and a validator that Fable runs on the real
receipts. Write the exact command sequence for the orchestrator, the abort conditions
(budget, error rate, any applied label), and the audit checklist for run Q. Review Gemini's
harness design against the contract's proof section as it lands in the integrated tree
(next run), not in this one. No model execution.

Shared rules: own worktree; commit if git allows, else leave files and say so; never merge or
push; never open the live index; `--mock` only. Tests:
`PYTHONPATH=. python -m pytest -q tests/ -p no:cacheprovider` (baseline 931 passed).
Completion packet at the end.
