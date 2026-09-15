# Phase 2 stage 3 result (2026-09-07)

**Verdict: the stage 3 gate is not met.** On the fresh sealed hold-out v3, the measured pass
with the approved taxonomy v3 (`--effort high`) fails coverage in the timed stratum and
strict precision in both strata. Receipts validate under `--require-real` with the guard
rule amended (below). Astra's replay audit (run AO) is the record; the stage 4 sketch in
the same brief carries the two structural findings forward. Apply stayed disabled; zero
labels were applied; the live index was never opened.

| Stratum | N | Assigned | Coverage (>= 0.80) | Correct | Strict precision (>= 0.90) |
|---|---:|---:|---:|---:|---:|
| timed_evidence | 47 | 37 | 37/47 = 0.787 FAIL | 28 | 28/37 = 0.757 FAIL |
| text_only | 13 | 12 | 12/13 = 0.923 PASS | 7 | 7/12 = 0.583 FAIL |
| overall | 60 | 49 | 49/60 = 0.817 | 35 | 35/49 = 0.714 |

Evidence grounding 49/49. Abstentions: 8 unmapped, 2 unsupported, 1 rejected (26-word
quote). Stage 2 on hold-out v2 was 41/47 and 31/41 timed, 12/13 and 11/12 text-only; the
two hold-outs are different draws and are not directly comparable.

## Two runs

- **Run 1 aborted** at 49 completions: the error guard reported 6/49 where only 3
  completions had failed (one curly-apostrophe quote, one paraphrased quote, one text
  evidence on a video-origin card). The guard summed rejected attempts and transport events,
  and every rejected submission is recorded as both. The abort then refused 24 in-flight
  submits. Archived unmodified at `docs/library/proof/run-stage3-2026-09-07-run1-aborted/`
  (complete copy under `proof-archives`). Repairs in `169a711`: the guard counts distinct
  failed completions (guard rule v2, mirrored in the validator's replay as a contract
  amendment for Astra's ruling); the assignment prompt asks for character-exact quotes.
  Stage 3 was re-frozen (`manifest-stage3-2026-09-07.json`; run 1's manifest kept as
  `-run1.json`).
- **Run 2 completed**: 71 processes, 563 attempts, 15 retries, 17 rejections (3.0%; worst
  point 8% at completion 50 under rule v2, 16% under the old sum), 2,136 s, 799,989 output
  tokens, CLI estimate USD 19.72 (subscription, not invoiced), git `d78e3140…` at execution.
  Archive: complete at `%LOCALAPPDATA%\AgentControlRoom\proof-archives\run-stage3-2026-09-07-run2\`
  (validates); committed copy `docs/library/proof/run-stage3-2026-09-07-run2/` without `http/`
  and `state/`, hashed in `SHA256SUMS`.

## What the errors say

**Ten timed abstentions are a card-contract asymmetry, not judgement.** The model may quote
only card `excerpts`; for an X post with a video, the excerpts are transcript clips, which on
these cards are near-empty ("She is the angel of love.", "🎵", "Now this is breakfast", a
comedy skit). The labellers were allowed to read the post's original prose (`summary_hint`,
eligible for `x_thread`) and assigned shelves the model could not cite. The card builder
adds a text-only prose excerpt only when a card has no clips (`library_cards.py`, "if not
excerpts and prose"). The phase plan already asked for the opposite: "absence of transcript
clips does not imply absence of textual evidence."

**Fourteen wrong primaries are again parent-versus-child and sibling calls**, in both
directions (Frontier Models versus the parent 3, Agents versus Generative Media 2, parent
versus Industry 3, Education 2, Agents 1, Developer Tools 2). Effort high did not move them.

**The labellers set the ceiling.** Scored blind against the same sealed gold under the same
strict rule: Grok 42/46 timed (0.91) and 7/11 text-only; Gemini 39/47 (0.83) and 9/11. A
strong reader of the same cards reaches the bar on the timed stratum; the model does not.

## Stage 4 direction (for Astra's sketch)

1. Card contract v2: emit the bounded original-prose excerpt as `text_only` evidence for
   prose-eligible sources (page, x_article, x_thread, reddit_thread, note) even when timed
   clips exist, within the six-excerpt and byte budgets; bump the selection version. This
   changes card hashes, so it is a new evidence freeze (manifest, hold-out re-binding) and a
   relabel against the new packet.
2. Assignment model: `claude-opus-5` on the subscription as a declared execution variable,
   after a small measured probe, since the errors are judgement errors a stronger reader
   avoids.
3. Everything else fixed: taxonomy v3, the prompt, hold-out v3 identities, the strict rule.

## Guard rule v2 (contract amendment for ruling)

Numerator = distinct completed attempts that were rejected or errored or had any transport
event by that completion, plus transport events with no attempt id; denominator = completed
attempts; strict `> 10%` after 20 completions. Stage 2's archive passes both rules (worst
4.49% under the old sum). Implemented in `proof_run.py` and mirrored in
`validate_proof_receipts.py` (`_check_completion_guard`).

## What did not change

No push to `origin/main`. `librarian_apply_enabled` stays false. The live index and the
resident helper on port 5179 were never opened.
