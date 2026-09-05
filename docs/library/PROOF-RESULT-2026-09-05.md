# Product proof result (P2-7), 2026-09-05: measured, applying nothing

**Verdict on the quality gate: FAIL, honestly measured.** The Librarian ran the real claim,
reason, submit loop over the whole 548-item frozen copy through the HTTP registry on an
isolated helper, with Claude Code (`claude -p`, model `claude-sonnet-5`) as the reasoning
client on Ryan's subscription. Zero labels were applied; preview refused apply; the library
state was identical before and after. The receipts validate under Astra's contract
(`RECEIPTS_VALID_AUDIT_REQUIRED`). The quality thresholds (0.80 coverage, 0.90 precision)
were not met, and the reasons are diagnostic, not mysterious.

## The run

| Measure | Value |
|---|---|
| Run id | `proof-subscription-2026-09-05` (fourth full pass; runs 1-3 invalid for harness reasons below) |
| Wall time | 06:14 to 06:52, 2,334,799 ms measured |
| Model calls | 72 (8 cards per call, 4 workers) |
| Attempts | 559 over 548 targets; 11 retries; 12 rejected attempts; 12 transport failures |
| Targets | 290 accepted, 225 unmapped, 32 unsupported, 1 rejected after its one retry |
| Usage (CLI-reported on all 72 calls) | 214 input, 908,541 output, 8,315,787 cache-read, 1,938,051 cache-write tokens |
| Paid cost | none (subscription; `ANTHROPIC_API_KEY` asserted unset) |
| Receipts | `docs/library/proof/run-2026-09-05/receipts.json`, sha256 `2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c` |
| Validator | `python tests/validate_proof_receipts.py --receipts ... --require-real` -> RECEIPTS_VALID_AUDIT_REQUIRED, 548 targets, 559 attempts |

## The score (60 held-out gold items)

| Stratum | Coverage | Precision (mapped rule) | Abstentions |
|---|---|---|---|
| Timed evidence (47) | 30/47 = 63.8% | 15/30 = 50.0% | 17 |
| Text-only (13) | 4/13 = 30.8% | 3/4 = 75.0% | 9 |
| Overall (60) | 34/60 = 56.7% | 18/34 = 52.9% | 26 |

Evidence grounding: 34/34 accepted held-out assignments carry a verbatim quote inside one
excerpt. Exact-path precision is 0/34 by construction (see scoring rule). Applied labels: 0.

## What the confusion table says

| Case | Count | Reading |
|---|---|---|
| Gold shelf absent from taxonomy v1, model abstained (`unmapped`) | 20 | Correct behavior; counts against coverage because the taxonomy lacks the shelf |
| Gold shelf absent from taxonomy v1, model assigned an AI shelf anyway | 7 | Over-assignment; the prompt's refusal rule is not strong enough |
| Gold at a top shelf, model chose a child shelf | 6 | Over-specific; wrong under the strict mapped rule, right under an ancestor-tolerant rule |
| Sibling confusion under AI and ML (Education/Security -> Developer Tools) | 2 | Thin shelf definitions |
| Right | 18 | |
| Other abstentions (unsupported/rejected on gold items with a shelf) | 6 | 3 are the video-description items the hold-out brief predicted |

Twenty-seven of the 60 held-out items have no shelf in the frozen taxonomy at all: seven top
shelves were induced from a 60-item gold set with a five-item floor. On the 33 items whose
gold label does map: coverage 27/33 = 81.8%, precision 18/27 = 66.7% (strict) or 24/27 =
88.9% (ancestor-tolerant). These are reported for the audit; the gate stands on the frozen
rule.

## Rulings made by the orchestrator during the proof (for Astra to accept or contest)

1. **Scoring rule:** a gold label is compared at its deepest ancestor present in the frozen
   taxonomy (`proof_score.py: map_gold_to_taxonomy`). Exact-path is reported alongside.
2. **Batching:** 8 cards per `claude -p` call (contract: a lease may return several
   single-item rows). Per-attempt `wall_ms` is the call wall divided by batch size; full call
   timings and usage live in `audit_extensions.calls`. Per-attempt `response_text` is the
   CLI envelope intact with `structured_output` narrowed to the item and the batch output
   retained as `batch_structured_output`.
3. **Over-length quotes:** the prompt and the receipt validator require under 25 words; the
   service caps at 1,000 characters. The harness treats a longer quote as invalid model
   output (rejected, retried). **Service gap for Astra:** `library_work.py` evidence
   validation should enforce the word cap.
4. **Third attempts:** a rejected attempt cannot be cancelled and the row becomes claimable
   again; the harness cancels any third claim without a model call.
5. **Service outcome `error` -> receipt outcome `rejected`** per the receipt contract.

## Why runs 1-3 were invalid (all harness, all fixed, all committed)

Run 1 aborted at 322/548 on a stray `reason` field in an assigned result (treated as harness
fault; now a released rejection). Run 2 completed but had two third attempts and a wall-time
total equal to the budget. Run 3 completed but one attempt kept the raw `error` label and the
per-attempt envelope lacked model provenance. Each full pass cost about 40 minutes and about
10 million cache-read tokens of subscription usage.

## What this proves and what it does not

Proven: the whole Phase 2 stage 1 substrate works end to end under a real client with real
model output, including retries, rejections, releases, preview, and zero-apply. Measured: with
taxonomy v1 and Sonnet 5 on librarian cards, the Librarian is right about half the time on
items it assigns and abstains on most of the library. Not proven: any installed-client or
computer-use behavior (P2-6 second half).

## Recommended next step (Fable's view, for Astra's plan)

Not more proof runs on this taxonomy. Induce a wider taxonomy from the 225 unmapped cards
(the contract's induction task), strengthen the refusal rule against over-assignment, and
give sibling shelves real include/exclude cues; then one more measured pass. That is Phase 2
stage 2 work, and it is exactly what the proof was meant to tell us.
