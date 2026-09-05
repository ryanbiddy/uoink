# Stage 2 audit plan (run T): induction receipts and the measured pass

**Date:** 2026-09-05 (run S, claude section) · **Auditor:** Claude engine, per
`PHASE2-STAGE2-BRIEF-2026-09-05.md` reservation 6 and the sketch's rule that a different
reviewer inspects anything Astra implements · **Subjects:** the induction receipts and
taxonomy v2 proposal produced by `induce_run.py`, then the measured pass over all 548 targets
produced by the repaired `proof_run.py`, both validated by Astra's repaired
`tests/validate_proof_receipts.py` and scored by `proof_score.py` · **Status:** plan only.
Nothing below has run; the repaired harness, validator, freeze files and receipts did not
exist in this worktree when this was written.

The run R audit (`PROOF-AUDIT-2026-09-05.md`) rejected P2-7 on three findings: the error
guard was recorded but never enforced (R-1), process, byte and cost totals described
reconstructed per-item views rather than the 72 actual CLI processes (R-2), and the archive
lacked the originals needed for independent replay (R-3). It also confirmed that the service
accepted 24, 25 and 26 word quotes alike. This plan says what run T replays so that those
four defects cannot recur unnoticed, and what a PASS on the stage 2 gate must show.

## Ground rules

1. **Never the live index, never port 5179, no model.** Every replay runs on the archived
   artifacts, the hashed source duplicate and the disposable databases named in the receipts.
   The audit script may open the service against a fresh temp copy for probes; it may not
   launch `claude`, the helper, or any network client.
2. **Replay, do not trust.** Every number in a result document is recomputed from the raw
   artifact that produced it. A self-consistent `receipts.json` establishes nothing by
   itself; the call files, HTTP history, registry export and snapshots are the evidence.
3. **One normaliser.** Every quote check in this audit uses the brief's definition: NFC,
   `str.split()`, rejoin with single spaces, count the tokens, 1 to 24 inclusive, case and
   punctuation untouched. The audit script implements it once and applies it to service,
   client, validator and scorer outputs alike. Any surface whose verdict differs from that
   function on any real quote is a finding, whichever direction it errs.
4. **Preserve failures.** An aborted, guard-breached or quality-failing run is the result.
   The audit reports it; it never asks for a subset rerun.
5. **Outputs are per-check tables.** Observed, expected, PASS/FAIL, and for each FAIL a
   reproduction Fable can hand to the owner. No PASS banner without the table.

## A. Word-cap parity across the four surfaces

The rule lives in four places. On the dispatch base they disagree; run T must show they no
longer do.

| Surface | Base behaviour (04cf29c) | Required after run S | Replay |
|---|---|---|---|
| Service `library_work.py:632-635` | NFC + collapse for occurrence; no word cap; 1,000-character schema limit at `library_work.py:1565` | 1 to 24 words after NFC + collapse, field-specific rejection, submission preserved, nothing staged, retry open, secondaries validated, 1,000 characters retained | `tests/test_library_word_cap_audit.py` (this run) against Astra's integrated service; all cases green |
| Client `scripts/librarian/proof_run.py:1045-1051` | Raw `split()` without NFC; `>= 25` becomes a harness `error` result before the service sees the quote | Same normaliser; whichever surface rejects, the receipt must say which one, keeping the model's raw result distinct from the submitted error (run R ruling 3) | Feed the audit's probe quotes through the client's check function in `--mock`; compare verdicts with the shared function |
| Validator `tests/validate_proof_receipts.py:376` | Raw `split() < 25` and a raw substring test with no NFC or collapse; stricter than the service on tabs and decomposed text | Same normaliser for count and occurrence; negative fixtures for 25 and 26 words and for a quote that only matches after NFC | `--self-test`; then the same probe set as receipts fixtures |
| Scorer `scripts/librarian/proof_score.py:169-170` | `<= 25` | Requires validated real receipts, verifies every membership itself with the shared rule; negative fixtures for 25 words, foreign card, missing source, modified batch, invented usage | Scorer fixtures plus a replay of every accepted membership from the real receipts |

Probe set, applied to every surface: 1, 23, 24, 25, 26 words; composed excerpt with a
decomposed quote and the reverse; tab, double-space, newline and mixed separators around 24
and 25 words; leading and trailing whitespace; a valid primary with a 25-word secondary;
whitespace-only; one word of 1,000 and of 1,001 characters. A probe that no surface can
reach (the client never sees a validator fixture, for example) is recorded as not
applicable, not as a pass.

Two decisions the audit needs recorded before it runs, because the probe set cannot settle
them: whether a non-breaking space (U+00A0) is a separator (Python `str.split()` says yes,
so the service's current normaliser says yes; the other surfaces must match or the decision
must be written down), and whether the field in a secondary rejection carries the
membership index. The tests accept either index convention but require the index to be
right when present.

## B. Induction receipts replay

Astra defines the `induction-receipts` schema; these checks apply whatever its field names.

| # | Check | Expected |
|---|---|---|
| B1 | Manifest binding | `induction-manifest-2026-09-05.json` lists exactly the 225 IDs whose last attempt in the archived `receipts.json` (sha256 `2b4e824e...469c`, rehashed first) has terminal outcome `unmapped`; each ID carries the archived packet's `source_revision` and `card_hash`; the manifest names the archived receipt hash; the 23 IDs that were old hold-out members are marked. Recomputed from the archive, not read from the gate document. |
| B2 | Call records | One record per `claude -p` process: call ID, ordered attempt or batch IDs, exact argv, output schema hash, `stdin`/`stdout`/`stderr` files under `calls/` whose sha256 match the record, monotonic start and end, exit status. Batches hold at most 25 librarian-profile cards. The consolidation call is a call record like any other. Process count in totals equals the number of records equals the number of stdin files. |
| B3 | Prompt containment | Rebuild each stdin from `prompts/induce.md` plus the frozen cards and compare bytes. Then grep every stdin for anything that must be absent: archived outcomes and abstention reasons, gold paths from `gold-set-2026-09-04.json`, the old split, score tables, any hold-out v2 ID or its excerpts. No forced shelf count and no miscellaneous shelf in the template. |
| B4 | Supporting evidence | For every new concept: at least five distinct `video_id`s, each with source, card and excerpt IDs present in the manifest cards at the bound revision, and a quote that passes the shared normaliser (1 to 24 words) and occurs in that one excerpt's text after NFC and collapse. Excerpt IDs must belong to `card["excerpts"]`; `summary_hint`, `hint`, `title` and topic cannot support. Repeated excerpts from one item count once; recount distinct items after deduplication. |
| B5 | Coverage ledger | Exactly 225 entries, one per manifest ID, no extras, each in {proposed concept, existing concept, still unmapped, unsupported} with evidence or a reason. "Proposed" entries cross-reference a concept whose support includes that card or state why not. |
| B6 | Taxonomy shape and diff | Stable shelf IDs where definition and cues are unchanged from `taxonomy-v1-2026-09-04.json`; 1 to 3 level paths; every include cue paired with a confusing alternative and the evidence that chooses it, at least for Developer Tools, Education, Security and Frontier Models against general AI coverage; every v1 ID accounted for as preserved, renamed, merged, split or retired with explicit mappings; a pin-impact report that states zero pins explicitly; rejected proposals retained. |
| B7 | Accounting | Tokens and CLI cost estimates deduplicated per call; every model in `modelUsage` preserved (run R saw Haiku entries beside Sonnet); estimates labelled as estimates; no invoice claim. |
| B8 | No writes, no egress | Before and after snapshots of the disposable duplicate are identical; no service call other than reads if any; every path in the receipts is below the dispatched worktree or its named `_scratch` root; no port 5179; API key unset assertion present. |
| B9 | Validator agreement | Astra's validator on these receipts exits 0 with the induction result code; the audit's independent counts for B2, B4, B5 and B7 equal the validator's on every field. A disagreement is a finding against whichever is wrong, and both are reported. |

## C. Measured pass replay (548 targets, taxonomy v2, one frozen prompt)

### C1. Freeze verification before anything else

- `holdout-v2-2026-09-05.json` and `induction-manifest-2026-09-05.json` rehash to the values
  in `STAGE2-GATE-2026-09-05.md`.
- Recompute the hold-out v2 selection: eligible pool from the archived cards excluding the
  225 and the old 60, expected 286 (105 timed, 181 text-only), sorted by `video_id`, sampled
  with seed `0x2b4e824ea9f93999` per the recorded algorithm, 47 timed and 13 text-only. The
  recomputed ID list must equal the frozen one. Any pool count that differs from 286/105/181
  stops the audit until the difference is explained.
- The sealed adjudicated labels and mapping table have a recorded hash and a timestamp or
  commit that precedes execution start; the labeller had no predictions. The feasibility bound
  (text-only items with `source_type=video` and no timed evidence) was reported before
  execution and none of those items was dropped.
- One `taxonomy_revision` and one `prompt_hash` across all attempts; the taxonomy is the
  approved v2 revision on the disposable duplicate; the prompt equals the frozen `assign.md`.
- No hold-out v2 card, excerpt or ID appears in any prompt's example section, in
  `induce.md`, or in any tuning artifact.

### C2. Execution record (the run R findings, replayed)

| # | Check | Expected |
|---|---|---|
| C2.1 | Calls versus processes (R-2) | `totals.model_calls` equals the number of call records equals the number of `calls/<id>.stdin` files; every attempt references one call ID; per-item views are labelled as views and never summed as process input. |
| C2.2 | Bytes at the call boundary (R-2) | For each call, `len(stdin bytes)` equals the recorded input bytes and equals the rebuilt prompt plus schema bytes; `len(stdout bytes)` equals the recorded response bytes; totals are sums over calls. Rebuilt batch prompts equal the archived stdin byte for byte. |
| C2.3 | Usage and cost (R-2) | Four CLI counters reconciled once per call; every `modelUsage` model preserved and reported separately; `total_cost_usd` summed once per distinct CLI session from the raw envelope and labelled an estimate; invoice field null unless evidence is attached. |
| C2.4 | Error guard (R-1) | From the archived completion order with timestamps, recompute `(rejections + transport events) / completed attempts` after every completion once N >= 20. Exactly 10% does not stop; the first strict excess stops: no call starts after that instant, owned children and the helper are terminated, partial receipts carry `abort_reason`. If the run completed, the ratio never exceeded 10% at any completion boundary, not only at the end. |
| C2.5 | Deadline and concurrency | No call starts after two hours from process start; at no instant are more than four calls open (sweep the start/end intervals); at most one reasoning retry per item; an identical-payload resend is a transport event, not a reasoning attempt. |
| C2.6 | HTTP history (R-3) | Every claim, submit, release, cancel and preview exchange is under `http/` with request and response; the helper token appears nowhere in the archive (grep the token pattern and `Authorization`); schema-invalid replies, third claims and cancel receipts are present; model disposition and terminal service state are separate fields. |
| C2.7 | Registry export and snapshots (R-3) | `state/` holds the work, attempts, submissions and proposals export plus before and after database snapshots and the journal copy. Every attempt token in the receipts exists in the export with a matching state; every submission key exists with a matching outcome; counts agree in both directions. Before and after snapshots are identical in memberships, pins, item policies, activation and projection revision; zero applies; apply flag false; the preview refuses application. |
| C2.8 | Source and heads | The named copy rehashes to `2765cc35...4dfc` before and after; the upgraded duplicate's hash and schema pair are recorded; bounded heads are archived privately and their hashes match `corpus_head_hashes`. |
| C2.9 | Portability | The validator's path-containment check passes on this checkout without reading any historical path; `--require-real` exits 0. |

### C3. Evidence replay on every accepted membership

For all accepted attempts, primaries and secondaries alike: identity (video, source
revision, card hash, packet hash, excerpt ID) against the frozen card; shelf ID and path in
the approved v2 revision; confidence at least 0.60; basis `packet`; evidence kind matches
the excerpt; quote passes the shared normaliser and occurs in that one excerpt; text-only
evidence only from the eligible source types; no quote spanning two excerpts. Every quote's
word count is tabulated; the maximum must be 24. Any 25+ word quote in the archive must sit
in a rejected attempt whose rejection names the service's cap reason, with the model's raw
result preserved beside it.

### C4. Quality gate, strict versioned rule

- Strata recomputed from the frozen hold-out v2 cards, not from a summary.
- Gold paths mapped to the deepest unambiguous approved v2 ancestor using the sealed table;
  strict equality to that path is the only gate rule. Exact-path and descendant-tolerant
  numbers are reported as diagnostics with denominators.
- Per stratum, raw numerators and ratios: coverage >= 0.80 and precision >= 0.90, at
  minimum 38 of 47 assigned with 35 correct and 11 of 13 assigned with 10 correct, or the
  ceiling of 0.90 times the actual assigned count when larger. Every selected item stays in
  the denominator.
- Also published, never substituted: the unchanged old-60 regression score, all 225
  development outcomes, unmappable over-assignment counts and sibling errors.
- The scorer must have refused to run on unvalidated or mock receipts and must not have
  fallen back to another taxonomy; the audit repeats the refusal with a mock file.

### C5. Verdict logic

P2-7 can be re-established only if C1, C2 and C3 have no FAIL and C4 passes in both strata.
A run with a clean quality result but any FAIL in C2 is rejected exactly as run R was; a run
with a clean record and a failing gate is a valid measurement of a FAIL and is preserved as
the result.

## D. Commands the audit will run (no model, no helper)

```powershell
$env:PYTHONPATH = "."
python -m pytest -q tests/test_library_word_cap_audit.py tests/library_work_astra tests/test_proof_run.py tests/test_induce_run.py -p no:cacheprovider
python tests/validate_proof_receipts.py --self-test --mock
python tests/validate_proof_receipts.py --receipts docs/library/proof/<induction-out>/receipts.json --require-real
python tests/validate_proof_receipts.py --receipts docs/library/proof/<pass-out>/receipts.json --require-real
python scripts/librarian/proof_score.py --receipts docs/library/proof/<pass-out>/receipts.json --holdout docs/library/proof/holdout-v2-2026-09-05.json --out _scratch/proof/audit-t/scorer
python docs/library/proof/audit-t-2026-09-05.py   # written in run T; emits audit-t-measurements-2026-09-05.json
```

The audit script follows `audit-r-2026-09-05.py`: it rehashes every input it reads, records
code fingerprints of runner, scorer, validator, service, prompts and cards, and exits 0 when
the audit completed, which is not a PASS.

## E. Outputs

`docs/library/STAGE2-AUDIT-2026-09-05.md` with sections A to C as tables of observed,
expected and verdict, every FAIL with a reproduction, the verdict from C5, and the exact
candidate SHA. `docs/library/proof/audit-t-measurements-2026-09-05.json` with every
recomputed count, the per-call byte and usage table, the guard ratio at each completion
boundary, the 60 scoring decisions, and all artifact hashes. Disposable working files under
`_scratch/proof/audit-t/`, not committed.

## F. Open questions for the owners before run T

1. **Astra:** the rejection code and message for the cap, and whether the field carries the
   membership index. The tests tolerate either, but the audit script wants the exact strings
   for the C3 tabulation.
2. **Astra and Gemini:** where the shared normaliser lives. Four copies of a lambda will
   drift again; one importable function used by service, client, validator and scorer is what
   "identical" should mean. If it stays inline, the audit's probe set is the only guard.
3. **Gemini:** whether the client still pre-checks quote length before submitting. If it
   does, the receipt must show the service's own rejection for at least one over-length
   case, or the audit cannot confirm the service enforces the cap in production paths.
4. **Astra:** the `induction-receipts` schema and the result code the validator emits for
   it, so B9 can be scripted.
5. **Fable:** the exact `_scratch` root and output directories for the induction run and the
   measured pass, so C2.8 and C2.9 name real paths.
6. **Whoever owns the decision:** U+00A0 and other Unicode separators (section A). The
   service's current `str.split()` treats them as whitespace; decide and record it before
   the client and validator are frozen.
