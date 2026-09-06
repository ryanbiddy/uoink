# Phase 2 stage 2 result (2026-09-06)

**Verdict: the stage 2 gate is not met.** The measured pass over all 548 frozen targets with
the approved taxonomy v2 passes coverage in both strata and strict precision in the text-only
stratum, and fails strict precision in the timed stratum (31 of 41 correct, 75.6%, against a
90% target). Receipts validate under contract v2 with `--require-real`; Astra's replay audit
(run AH, `STAGE2-AUDIT-2026-09-06.md`) is the record of what the archive establishes. Apply
stayed disabled; zero labels were applied; the live index was never opened.

This document is Fable's account. Every number below is recomputed from the archived
receipts by the scorer or the validator; Astra's audit is authoritative where they differ.

## Measured quality on hold-out v2 (60 sealed cards)

| Stratum | N | Assigned | Coverage (>= 0.80) | Correct | Strict precision (>= 0.90) | Result |
|---|---:|---:|---:|---:|---:|---|
| timed_evidence | 47 | 41 | 41/47 = 0.872 | 31 | 31/41 = 0.756 | coverage PASS, precision FAIL |
| text_only | 13 | 12 | 12/13 = 0.923 | 11 | 11/12 = 0.917 | PASS |
| overall | 60 | 53 | 53/60 = 0.883 | 42 | 42/53 = 0.792 | FAIL |

Scoring rule `strict-mapped-primary-v2` against the frozen mapping table (verified by the
scorer's `--mapping` check on all 60 rows). Evidence grounding: 53 of 53 accepted primaries
pass every evidence check. Abstentions: 4 unmapped and 3 unsupported.

The eleven errors are boundary calls between neighbouring shelves, not hallucinations:
Developer Tools chosen where the adjudicator held Education (3), the AI and ML parent chosen
where a child was justified (Industry 2, Security 1), a child chosen where the parent was the
honest answer (Frontier Models 1, Industry 1), Industry versus Frontier Models (1), Developer
Tools versus AI Agents (1), Frontier Models versus Education (1).

Comparison with the stage 1 pass (run R, taxonomy v1, old hold-out; a different evaluation
set, so a development regression signal only): coverage 34/60 and strict precision 18/34.

## What ran

| Identity | Value |
|---|---|
| Integrated candidate at execution | `746045dcdb4900bbb7aaf2a78ad7fe58d723409a` (pre-execution record written at `9de497e`) |
| Stage-2 manifest | `docs/library/proof/manifest-stage2-2026-09-05.json`, manifest hash `213ef46f…`, 548 targets, zero exclusions, cards and heads equal to stage 1 |
| Approved taxonomy | `docs/library/taxonomy-v2-2026-09-05.json`, 12,991 bytes, sha256 `015260a4…`, revision `bd9e7f9d…`, parent `taxonomy-v1-2026-09-04` (`2f283053…`); approved by Astra in `INDUCTION-AUDIT-14-2026-09-06.md`; active on the disposable duplicate before and after the run |
| Sealed labels / mapping | `holdout-v2-gold-2026-09-05.json` sha256 `14cd54dc…`; `holdout-v2-mapping-2026-09-05.json` sha256 `9fc2cc9c…`; adjudicated by Astra (run AG) from Gemini and Grok blind labels (packet 12, carried forward under `INDUCTION-AUDIT-13`) |
| Assignment prompt | `scripts/librarian/prompts/assign.md`, file sha256 `92a25e2b…`, rendered-template sha256 `662e8ee8…` |
| Client | Claude Code CLI 2.1.261, `claude-sonnet-5`, subscription, tools disabled, `ANTHROPIC_API_KEY` unset |
| Execution | 71 processes, batch 8, concurrency 4, 557 item attempts, 9 reasoning retries, 11 rejected attempts, 11 transport events, wall 2,628 s (43.8 min), error guard never tripped |
| Usage (CLI counters) | 222 input, 1,034,756 output, 9,260,888 cache-read, 2,478,488 cache-create tokens; CLI estimate USD 23.24 (subscription; not an invoice) |
| Archive | complete: `%LOCALAPPDATA%\AgentControlRoom\proof-archives\run-stage2-2026-09-06\` (525 MB, validates); committed: `docs/library/proof/run-stage2-2026-09-06/` without the six database snapshots, hashed in `SHA256SUMS` |

Outcomes over all 548 targets: 378 accepted, 130 unmapped, 38 unsupported, 2 rejected.
Over the 225 development cards (the induction input): 101 accepted, 109 unmapped, 15
unsupported; their accepted primaries land mostly on the four new shelves (Industry 30,
Agents 21, News 16, Generative Media 14).

## How taxonomy v2 was reached

Induction ran on the 225 terminal-unmapped cards of the stage 1 archive. The path to an
approved revision took ten consolidation attempts and five reviewer-authored decisions, each
audited by Astra:

| Step | Record | Outcome |
|---|---|---|
| Attempt 6 (contract v1.2) | `INDUCTION-AUDIT-2026-09-05.md` | REJECT: six off-subject supports, no operative precedence, gold path in a template example, isolation evidence missing |
| Attempts 7a, 7b | `induction-attempts/attempt7-*` | aborted: low-effort batches find no concepts; model-transcribed ids made key derivation fatal (contract v1.3 makes them non-fatal) |
| Attempt 8, 9 | `INDUCTION-AUDIT-9-2026-09-05.md` | REJECT: disposition keys in node support; Agents and Career at 3/5 |
| Attempt 10 | `induction-run-10-2026-09-05` | valid; auditor-rejected keys excluded; the News parent candidate silently dropped |
| Decisions 1-4 | `INDUCTION-AUDIT-10/11/12/13` | REJECT each time on named, mechanically repairable items; audit 13 reviewed all 91 mapped ledger rows |
| Decision 5 | `INDUCTION-AUDIT-14-2026-09-06.md` | **APPROVE** |

Taxonomy v2: the seven v1 shelves byte-identical, plus `news-and-current-events`,
`ai-agents-and-automation`, `ai-industry-and-business`, `generative-media`, each with five
subject-relevant supports from five distinct cards. Rejected below the five-card floor: two
News subcategories, Sports Highlights, Creator Culture, Career and Entrepreneurship; Product
Launches redistributed and recorded.

## Findings for the next stage

1. **The timed stratum fails on sibling boundaries the taxonomy leaves to judgement.**
   Developer Tools versus Education (tutorials that build agents) is the largest cluster,
   and it is a v1 boundary that stage 2 could not touch. Parent-versus-child choices account
   for four more errors. Precision on the text-only stratum shows the assignment client can
   meet the bar when the boundary is clear.
2. **Coverage is no longer the problem.** 88% of the hold-out was assigned with fully grounded
   evidence, against 57% in stage 1.
3. **Consolidation by a single model call is not a reliable way to finish a taxonomy.** Every
   model rerun introduced a new class of slip. The converging tool was a deterministic
   reviewer composition audited against exact replacement rows.
4. **Byte identity across Windows worktrees needs `-text` attributes** for every hashed
   artifact; three rounds lost time to CRLF materialisation.

## What did not change

No push to `origin/main`. `librarian_apply_enabled` stays false; the preview path refuses
application. The live index and the resident helper on port 5179 were never opened. Ryan's
open items are unchanged: ORCHESTRATION-V1 signature, watchdog install, PR strategy for the
branch, the Claude adapter shell allow-list, and deleting the renamed OneDrive folder.
