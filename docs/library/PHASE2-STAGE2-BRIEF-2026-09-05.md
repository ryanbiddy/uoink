# Phase 2 stage 2 dispatch (run S), 2026-09-05: repairs, freeze, induction harness

Ryan: "stage 2 go, don't stop until done." Contract: `PHASE2-STAGE2-SKETCH-2026-09-05.md`
(Astra, plan owner) under `ORCHESTRATION-V1-2026-09-04.md`. This brief is Fable's dispatch
packet with the reservations the sketch asked for. Find your worker name and do only that
section. No model execution in this run. Never the live index. Never port 5179.

## Fable's reservations and decisions

1. **Base SHA:** the commit this file lands in (parent `1373017`: run R audit merged, 935
   passed, 3 skipped, 1 xfailed).
2. **Source:** the named copy `C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04-upgraded.db`
   (sha256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`), corpus heads
   readable with `--allow-install-corpus`. Duplicate for anything that writes.
3. **Archived proof:** `docs/library/proof/run-2026-09-05/receipts.json` (sha256
   `2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c`) is the induction
   source: the 225 targets whose terminal outcome is `unmapped`.
4. **New hold-out seed:** deterministic selection seeded with the integer value of the first
   16 hex characters of that receipts sha256 (`0x2b4e824ea9f93999`), 47 timed and 13
   text-only from the 286 eligible identities (outside the 225 and the old 60), sorted by
   `video_id` before sampling. Old 60 becomes development data; keep its historical result.
5. **Quote cap:** 24 words maximum, NFC-normalized, whitespace-collapsed, case and
   punctuation preserved, identical in service, client, validator and scorer; validate every
   membership including secondaries.
6. **Owners this run (one per shared surface):** Astra = `library_work.py` (word cap),
   `tests/validate_proof_receipts.py`, `docs/library/proof/holdout-v2-2026-09-05.json`,
   `docs/library/proof/induction-manifest-2026-09-05.json`, `docs/library/STAGE2-GATE-2026-09-05.md`,
   `tests/library_work_astra/**`. Gemini = `scripts/librarian/proof_run.py`,
   `scripts/librarian/proof_score.py`, `scripts/librarian/induce_run.py` (new),
   `scripts/librarian/prompts/*.md`, `tests/test_proof_run.py`, `tests/test_induce_run.py`
   (new). Claude engine = `tests/test_library_word_cap_audit.py` (new),
   `docs/library/STAGE2-AUDIT-PLAN-2026-09-05.md` (new). Nobody touches `library_cards.py`,
   `index.py`, adapters, or migrations. No migration number is allocated.
7. **Execution plan after this run (Fable):** integrate; validate a small real run through the
   validator's function with only the whole-manifest rule skipped; run the induction harness
   on the 225 cards through `claude -p` (`claude-sonnet-5`, subscription); review the proposal
   against the gate; approve and activate taxonomy v2 on a fresh disposable duplicate only;
   one measured pass over all 548 with the repaired harness; validator; scorer; Astra audit.
   Apply stays disabled throughout; nothing touches the live library.

## codex (Astra): service cap, freeze, validator, gate

1. **Word cap in `library_work.py`.** Every membership quote: 1 to 24 words after NFC and
   whitespace collapse; reject 25+ with a field-specific reason; preserve the rejected
   submission; stage nothing from it; the planned single retry remains available. Checks in
   `tests/library_work_astra/`.
2. **Freeze** `docs/library/proof/holdout-v2-2026-09-05.json` (reservation 4: ids, stratum,
   source revision, card hash, selection algorithm and seed, pool counts) and
   `docs/library/proof/induction-manifest-2026-09-05.json` (the 225 ids bound to source
   revision, card hash, and the archived receipt hash; the 23 that were old hold-out ids
   marked). Record both hashes in `STAGE2-GATE-2026-09-05.md` together with the exact gate
   from the sketch: all 548 targets, one taxonomy revision, one frozen prompt, coverage
   >= 0.80 and strict mapped primary precision >= 0.90 per stratum on hold-out v2, every
   accepted membership evidence-checked, receipts valid, zero applies.
3. **Validator repair** per the sketch's "Call receipts" and "Accounting" rows: one immutable
   record per CLI process (call id, ordered attempt ids, argv, schema hash, raw stdin/stdout/
   stderr bytes or private artifact hashes, monotonic start/end, exit status); attempts
   reference calls; `model_calls` equals processes; batch bytes measured at the call boundary;
   tokens and CLI estimates deduplicated per call with every `modelUsage` model preserved;
   the error guard checked from the archived completion order (stop above 10% after 20
   completed attempts, counting rejections plus linked transport events); HTTP history
   retained with secrets redacted; registry export and before/after snapshots required.
   Keep `--self-test` and add negative fixtures for each new rule. Define the receipt schema
   for the induction run too (`induction-receipts`): calls, proposal, coverage ledger,
   supporting evidence per new concept (>= 5 distinct cards, quotes of 1 to 24 words).

## gemini: harness repairs, induction harness, prompts, scorer

1. **`proof_run.py` repairs** to satisfy Astra's repaired validator exactly: immutable call
   records with raw bytes written to `<out>/calls/<call_id>.{stdin,stdout,stderr}` and their
   sha256 in the record; monotonic start/end per call; attempts reference `call_id`;
   accounting per the sketch; the error guard as a shared coordinator in the batched loop
   (2 h deadline, at most 4 active processes, one reasoning retry per item, check
   `(rejections + transport events) / completed attempts > 0.10` after every completion
   once N >= 20, stop launching, terminate owned children and the helper, save partial
   receipts with `abort_reason`); every HTTP request/response retained under
   `<out>/http/` with the token redacted; registry export (work, attempts, submissions,
   proposals) and before/after DB snapshots plus journal copy under `<out>/state/`. Keep
   `--batch`, `--mock`, and the subprocess-based tests; add a guard-breach test with a mock
   that rejects 3 of the first 20.
2. **`induce_run.py`** (new): client-run induction over the 225 frozen cards. Batches of
   at most 25 librarian-profile cards per `claude -p` call with `scripts/librarian/prompts/induce.md`,
   then one consolidation call over the batch proposals; output a taxonomy proposal that
   meets the sketch: stable shelf ids (preserve v1 ids for unchanged concepts), 1 to 3 level
   paths, definitions, include and exclude cues with a confusing alternative for each
   sibling, for every new concept at least five distinct supporting cards with source, card
   and excerpt ids and a verbatim 1 to 24 word quote each (titles and summaries cannot
   support), a coverage ledger for all 225 ids, a diff against v1, rejected proposals, and
   the induction receipts in Astra's schema. `--mock` mode for tests. Output
   `docs/library/proof/taxonomy-v2-proposal-2026-09-05.json` plus receipts.
3. **Prompts.** `induce.md`: no forced shelf counts, no miscellaneous shelf, evidence
   requirements as above. `assign.md`: the refusal rules from the sketch (valid excerpt that
   fits no concept -> `unmapped`; absent or ineligible evidence -> `unsupported`; primary
   shelf must match the subject the excerpt establishes; confidence >= 0.60; quotes 1 to 24
   words; every membership evidenced), sibling cues rendered from the taxonomy.
4. **`proof_score.py`**: the strict versioned rule (NFC, trim, frozen case convention,
   deepest unambiguous approved ancestor, equality), require validated real receipts before
   any verdict, verify every membership, exact frozen taxonomy and split hashes, nonempty
   strata, no fallback taxonomy; negative fixtures for 25-word, foreign-card, missing-source,
   modified-batch and invented-usage cases.

## claude: word-cap audit tests and the audit plan

`tests/test_library_word_cap_audit.py`: 23, 24, 25, 26 words; NFC composed versus decomposed;
tabs and double spaces; secondary membership over the cap; rejected submission preserved
and nothing staged; retry still permitted. Written from this brief, not from Astra's diff
(you cannot run them; the orchestrator does). `STAGE2-AUDIT-PLAN-2026-09-05.md`: what the
run T audit must replay on the induction receipts and on the measured pass.

Shared rules: own worktree; commit if git allows, else leave files and say so; never merge
or push. Tests: `PYTHONPATH=. python -m pytest -q tests/ -p no:cacheprovider` (baseline 935
passed). Completion packet at the end.
