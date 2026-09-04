# Cost model G4 (evidence cards on the 2026-09-04 index copy)

**Author:** grok · **Run:** 2026-09-04 · **Harness:** `scripts/library/cost_model.py`  
**Index (read-only):** `C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04.db`  
**Live index was not opened.**

## G4

**PASS.** One Librarian pass on this copy, Haiku 4.5 Message Batches API, is **$0.84 per 500 items**. Council estimate was **$1 per 500 on Haiku**. Ratio **0.836×**, inside the 2× gate.

The council number was arithmetic over summaries. This number is measured card *input* from the copy plus the dispatch's stated 400 output tokens per card.

| | |
|---|---|
| Gate | measured full evidence-card pass within 2× of "$1 / 500 items on Haiku" |
| Measured | $0.916 for 548 items = **$0.836 / 500** (Haiku 4.5 **batch**) |
| Estimate | $1.00 / 500 |
| Ratio | 0.836× |
| Verdict | **PASS** |

Haiku **list** (no batch discount) is $1.83 for 548 items = $1.67 / 500, still inside 2×.

## What was measured

Cards built the way `get_evidence_card` does: 10 clips spread across the timeline, plus title, channel, and the ~600-character summary hint from the markdown body. Helpers were copied, not imported (`clips.py` / `index.py` / `uoink_mcp_tools.py` untouched). Summary hints were read from the corpus paths already stored in the copy (`E:\Uoink\…`); 548/548 files opened.

| Quantity | Value | Label |
|---|---|---|
| Items / cards | 548 | MEASURED |
| Clip rows | 3,216 | MEASURED |
| Items with clips | 212 | MEASURED |
| Items with a summary hint | 548 | MEASURED |
| Card text, total | 2,425,715 characters (mean 4,426.5) | MEASURED |
| Chosen-clip text | 2,001,344 characters | MEASURED |
| All-clip text (not sent) | 4,720,482 characters | MEASURED |
| Summary-hint text | 320,874 characters | MEASURED |
| Tokens (chars/4) per card, mean | 1,106.6 | MEASURED |
| Tokens (chars/4) all cards | 606,428.8 | MEASURED |
| Induce input (prompt + 60 stratified cards) | 74,973 tokens | MEASURED |
| Assign prompt (no taxonomy, no cards) | 263 tokens | MEASURED |
| tiktoken | not installed; chars/4 only | — |
| Assign output | 400 × 548 = 219,200 tokens | STATED by dispatch |
| Induce output (taxonomy JSON) | 6,000 tokens | ASSUMED (no model called) |
| Taxonomy stuffed into each assign call | 6,000 tokens | ASSUMED, same figure |

No prompt cache. No thinking tokens. Gemini 3.8 Flash list price *includes* thinking tokens if thinking is on; this pass prices it as non-thinking JSON.

Induce sample: 60 cards, same Uncategorized×2 stratification as `scripts/librarian/dryrun.py` (seed 7).

## Live list prices (verified 2026-09-04)

All USD per million tokens. Batch = 50% of list on every vendor below.

| Model | Input | Output | Batch in/out | Context used for packing | Source · date |
|---|---|---|---|---|---|
| Claude Haiku 4.5 | $1 | $5 | $0.50 / $2.50 | 200K | https://platform.claude.com/docs/en/about-claude/pricing (same table as https://docs.claude.com/en/docs/about-claude/pricing) · 2026-09-04 |
| Claude Sonnet 5 | $2 | $10 | $1 / $5 | 1M | same page · 2026-09-04. $2/$10 is permanent (Anthropic, 10 Aug 2026); the $3/$15 step-up did not happen. |
| Gemini 3.8 Flash | $0.75 | $3.75 | $0.375 / $1.875 | 1,048,576 | https://ai.google.dev/gemini-api/docs/pricing · page "Last updated 2026-09-04 UTC". Introductory through 31 Dec 2026; $1.50 / $7.50 from 1 Jan 2027. |
| GPT-5 nano | $0.05 | $0.40 | $0.025 / $0.20 | 400K | https://platform.openai.com/docs/pricing · 2026-09-04. Nearest small OpenAI model; the model card calls it out for summarization and classification. |
| Local 27B on 16 GB | $0 | $0 | — | 32K packed | Council 7–22 tok/s regime. Not a vendor page. |

Haiku 4.5 **rates did not change** since the 2026-05-12 comment in `server.py`. Cache hits remain 0.1× input ($0.10 / MTok). This memo does not assume cache hits.

Sonnet 4.6 is still $3 / $15 on the same Anthropic table; it is not the model this pass prices.

## One induce-60 + assign-all pass

Packed to each model's context. Haiku needs 4 assign calls of 174 cards. Sonnet 5 and Gemini 3.8 Flash take all 548 in one assign call.

| Model | Assign calls | List USD (548) | List / 500 | Batch USD (548) | Batch / 500 |
|---|---|---|---|---|---|
| Claude Haiku 4.5 | 4 | $1.83 | $1.67 | **$0.92** | **$0.84** |
| Claude Sonnet 5 | 1 | $3.63 | $3.31 | $1.81 | $1.65 |
| Gemini 3.8 Flash (intro) | 1 | $1.36 | $1.24 | $0.68 | $0.62 |
| GPT-5 nano | 2 | $0.12 | $0.11 | $0.06 | $0.06 |
| Local 27B / 16 GB | 25 | $0 | $0 | — | — |

Local hours at 7–22 tok/s, **output tokens only** (generation-bound): **2.84–8.94 h** for 225,200 output tokens. If prefill of ~838k input tokens is billed at the same tok/s (worst case, it is not), 13.4–42.2 h. Resident-summary 1.5 h / 500 in the council doc was summaries, not these cards.

Client-loop shape (`dryrun.py --batch 12`, 46 assign calls, taxonomy repeated): Haiku **list $2.10** ($1.91 / 500). Still inside 2×. That is the option-iii path if the calling client cannot pack 174 cards.

## Vs the council "$1 per 500 on Haiku"

The council figure was "full re-shelve over summaries," Haiku, ~$1 / 500. This pass is **cards**, which are larger than a 300–500 token summary, plus a 60-card induce.

It still lands **under** $1 / 500 on Haiku batch because output (400 tokens × 548 × $2.50 / MTok batch) is $0.56 of the $0.92, and input is $0.35. A summary-only pass would be cheaper still.

| Comparison | USD / 500 | × council |
|---|---|---|
| Council Haiku (summaries, arithmetic) | $1.00 | 1.00× |
| **Haiku 4.5 batch, cards, packed (G4)** | **$0.84** | **0.84×** |
| Haiku 4.5 list, cards, packed | $1.67 | 1.67× |
| Haiku 4.5 list, 12-card client batches | $1.91 | 1.91× |
| Sonnet 5 batch, packed | $1.65 | 1.65× |
| Gemini 3.8 Flash batch, packed | $0.62 | 0.62× |
| GPT-5 nano batch, packed | $0.06 | 0.06× |

G4 fails only if the Haiku-batch packed pass exceeds $2.00 / 500. It does not.

## What this does not measure

- Assignment *quality* (Gemini's gold set / local bench).
- Thinking / reasoning tokens (Gemini list price includes them when thinking is on; this pass assumes non-thinking JSON, matching the Librarian spec).
- Prompt-cache hits (would cut Haiku input toward $0.10 / MTok on the taxonomy).
- A real induce output. 6,000 tokens is a filled 40–80 node taxonomy, not a model run.
- The live 551-item index. The copy is 548 items, 3,216 clips.

Re-run: `python scripts/library/cost_model.py --index <copy.db>` from the worktree root. Prints the same tables plus JSON. Opens the file `?mode=ro`.
