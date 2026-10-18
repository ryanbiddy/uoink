# Run AO brief: stage 3 measured-pass audit, guard rule v2 ruling, stage 4 sketch (2026-09-07)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. One section, codex only. You are
GPT-6 Astra, independent auditor and plan owner. No model, no helper, no port 5179, no live
index, no commit. Apply stays disabled. Ryan's 2026-09-07 authorization covers stage 4.

## Part 1: stage 3 audit (C1 to C4 of `STAGE2-AUDIT-PLAN-2026-09-05.md`, applied to stage 3)

Archive: complete at
`C:\Users\hello\AppData\Local\AgentControlRoom\proof-archives\run-stage3-2026-09-07-run2\`
(validates with `--stage3 --require-real`); committed copy
`docs/library/proof/run-stage3-2026-09-07-run2/` without `http/` and `state/`, all hashed in
its `SHA256SUMS`. Aborted run 1 is preserved at
`docs/library/proof/run-stage3-2026-09-07-run1-aborted/` and `proof-archives/...-run1-aborted`.
Result document: `PHASE2-STAGE3-RESULT-2026-09-07.md`. Freeze: `manifest-stage3-2026-09-07.json`
(run 1's as `-run1.json`), `STAGE3-GATE-2026-09-07.md`, hold-out v3, sealed labels
(`holdout-v3-gold-2026-09-07.json`, `holdout-v3-mapping-2026-09-07.json`, adjudicated in run
AK), approved taxonomy v3 (`INDUCTION-AUDIT-16`), execution records
`stage3-execution-record-2026-09-07.json` (run 1) and `-run2.json`.

**Rule on guard rule v2** (contract amendment): the harness now counts each failed completion
once (distinct attempts rejected/errored or with a transport event, plus anonymous transport
events), and the validator's `_check_completion_guard` mirrors it. Run 1's abort at a reported
6/49 with 3 real failures is the reproduction. Accept, amend, or reject; if rejected, say
what the run 2 receipts are under the old rule (they breach it at completion 28).

Write `docs/library/STAGE3-AUDIT-2026-09-07.md` with per-check tables and `P2-7 PASS`,
`P2-7 FAIL`, or `RECEIPTS REJECTED`, plus measurements and replay script under
`docs/library/proof/` (parameterize your run AH script; keep earlier files untouched).

## Part 2: stage 4 sketch (plan owner)

Fable's reading of stage 3 (result document, "What the errors say"): ten timed abstentions
come from a card-contract asymmetry (labellers may use the original prose of prose-eligible
sources; the model may quote only excerpts, and the builder emits the prose excerpt only when
a card has no clips); fourteen wrong primaries are judgement calls the blind labellers get
right more often (Grok 0.91 timed strict precision against the sealed gold).

Sketch stage 4 as you sketched stage 2: what to freeze, who owns which files, gates, and the
audit obligations, for these proposed changes:

1. **Card contract v2** in `library_cards.py`: add the bounded original-prose `text_only`
   excerpt for prose-eligible source types even when timed clips exist, within the existing
   six-excerpt and 8,192-byte budgets; new `selection_version`; card hashes change for the
   affected cards. State how the evidence freeze re-binds (new manifest with cards v2; hold-out
   v3 identities unchanged but card hashes re-bound; labels re-done against the new packet or
   carried forward if you rule the visible content equivalent), what stays shared with stage 1
   (source, heads), and the validator changes you own (`--stage4`, hold-out re-binding).
2. **Assignment model** `claude-opus-5` on the subscription as a declared execution variable,
   with a small measured probe (16 real items through the validator's partial check) before
   the full pass; effort default.
3. Taxonomy v3, the prompt, hold-out v3 identities and the strict rule unchanged.

Also state whether the 0.90 strict precision target should stand for stage 4 given the
labeller ceiling you can verify from the label files, or what evidence would justify a
different target; the target is Ryan's to change, but your recommendation goes to him.

Write `docs/library/PHASE2-STAGE4-SKETCH-2026-09-07.md`. Do not edit runner, prompt, scorer,
card builder, or any archived artifact. Do not commit.
