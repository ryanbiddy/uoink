# Cost model G4 (evidence cards on the 2026-09-04 index copy)

**Author:** grok · **Repair increment:** run D, 2026-09-04 · **Harness:** `scripts/library/cost_model.py`  
**Index (read-only source):** `C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04-upgraded.db`  
**sha256:** `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`  
**Disposable duplicate:** worktree `_scratch/uoink-index-copy-2026-09-04-upgraded.db` (WAL checkpointed to DELETE; not committed).  
**Live index was not opened.**

## G4

**G4 forecast: within 2x of estimate; operational G4 pending measured usage.**

This is an arithmetic forecast over estimated tokens. `reported_usage` is null. `paid_cost` is null. No model was called. The printed verdict is not PASS.

| | |
|---|---|
| Gate | one Librarian pass within 2× of "$1 / 500 items on Haiku" |
| Forecast (Haiku 4.5 batch, first-fit packed) | $0.920521 for 548 items = **$0.839891 / 500** |
| Council estimate | $1.00 / 500 |
| Ratio | 0.8399× |
| `estimated_tokens` | chars/4 (tiktoken not installed) |
| `reported_usage` | null |
| `paid_cost` | null |
| Operational G4 | pending measured request/response usage, retries, coverage, quality, wall time |

Haiku **list** (no batch discount) is $1.841041 for 548 items = $1.679782 / 500, still inside 2× as a forecast only.

The previous run printed PASS from this same arithmetic and packed by global average. Astra reproduced a first batch of 277,503.75 input proxy tokens against a 200,000 context. That packer is gone. First-fit packing on this copy yields **5 Haiku assign calls**, batch sizes **52 / 160 / 146 / 152 / 38**, largest request **199,834** tokens (input + reserved output), under 200,000. The 160-card batch is the Haiku 64k `max_output` cap (160 × 400).

## Prompts used

Regenerated against **this worktree's** files:

- `scripts/librarian/prompts/induce.md`
- `scripts/librarian/prompts/assign.md`

`{{CARDS}}` is still unfenced in this tree. Gemini's run D SEC-03 fencing had not landed here. Induce input is **75,222** proxy tokens; assign prompt (no taxonomy, no cards) is **569.5**. Those match Astra's post-run-C prompt figures, not the earlier memo's 74,973 / 263.

## What was counted

Cards built the way `get_evidence_card` does: 10 clips spread across the timeline, plus title, channel, and the ~600-character summary hint from the markdown body. Helpers were copied, not imported (`clips.py` / `index.py` / `uoink_mcp_tools.py` untouched; Codex owns any later call into `library_cards.py`). Summary hints were read from the corpus paths already stored in the copy; 548/548 files opened.

Character counts are observed from the copy. Token counts are **estimated**. Output tokens are **stated/assumed**. Nothing here is reported model usage.

| Quantity | Value | Label |
|---|---|---|
| Items / cards | 548 | observed from copy |
| Clip rows | 3,216 | observed from copy |
| Items with clips | 212 | observed from copy |
| Items with a summary hint | 548 | observed from copy |
| Card text, total | 2,425,715 characters (mean 4,426.5) | observed from copy |
| Chosen-clip text | 2,001,344 characters | observed from copy |
| All-clip text (not sent) | 4,720,482 characters | observed from copy |
| Summary-hint text | 320,874 characters | observed from copy |
| Tokens (chars/4) per card, mean | 1,106.6 | ESTIMATED |
| Tokens (chars/4) all cards | 606,428.8 | ESTIMATED |
| Induce input (prompt + 60 stratified cards) | 75,222 tokens | ESTIMATED |
| Assign prompt (no taxonomy, no cards) | 569.5 tokens | ESTIMATED |
| tiktoken | not installed; chars/4 only | — |
| Assign output | 400 × 548 = 219,200 tokens | STATED by dispatch |
| Induce output (taxonomy JSON) | 6,000 tokens | ASSUMED (no model called) |
| Taxonomy stuffed into each assign call | 6,000 tokens | ASSUMED, same figure |
| `reported_usage` | null | no inference |
| `paid_cost` | null | no inference |

No prompt cache. No thinking tokens. Gemini 3.8 Flash list price *includes* thinking tokens if thinking is on; this pass prices it as non-thinking JSON.

Induce sample: 60 cards, same Uncategorized×2 stratification as `scripts/librarian/dryrun.py` (seed 7).

## Live list prices (verified 2026-09-04)

All USD per million tokens. Batch = 50% of list on every vendor below.

| Model | Input | Output | Batch in/out | Context | Max output | Source · date |
|---|---|---|---|---|---|---|
| Claude Haiku 4.5 | $1 | $5 | $0.50 / $2.50 | 200K | 64K | https://platform.claude.com/docs/en/about-claude/pricing · 2026-09-04. Max output: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude/haiku-4-5 |
| Claude Sonnet 5 | $2 | $10 | $1 / $5 | 1M | 128K | same Anthropic pricing page · 2026-09-04. $2/$10 is permanent (Anthropic, 10 Aug 2026). |
| Gemini 3.8 Flash | $0.75 | $3.75 | $0.375 / $1.875 | 1,048,576 | 65,536 | https://ai.google.dev/gemini-api/docs/pricing and https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash · 2026-09-04. Introductory through 31 Dec 2026; $1.50 / $7.50 from 1 Jan 2027. |
| GPT-5 nano | $0.05 | $0.40 | $0.025 / $0.20 | 400K | 128K | https://platform.openai.com/docs/pricing and https://developers.openai.com/api/docs/models/gpt-5-nano · 2026-09-04. |
| Local 27B on 16 GB | $0 | $0 | — | 32K packed | (none published) | Council 7–22 tok/s regime. Not a vendor page. |

Haiku 4.5 **rates did not change** since the 2026-05-12 comment in `server.py`. Cache hits remain 0.1× input ($0.10 / MTok). This memo does not assume cache hits.

Sonnet 4.6 is still $3 / $15 on the same Anthropic table; it is not the model this pass prices.

## One induce-60 + assign-all pass (first-fit)

Each assign request is packed per card: prompt + taxonomy + serialized cards + reserved output (400 tokens/card) must fit the context, and reserved output must fit `max_output`. A card that cannot fit alone raises `CardDoesNotFitError`. No single card on this copy failed that check.

| Model | Assign calls | Batch sizes | Max request tokens | List USD (548) | List / 500 | Batch USD (548) | Batch / 500 |
|---|---|---|---|---|---|---|---|
| Claude Haiku 4.5 | 5 | 52, 160, 146, 152, 38 | 199,834 | $1.84 | $1.68 | **$0.92** | **$0.84** |
| Claude Sonnet 5 | 2 | 320, 228 | 543,206 | $3.64 | $3.32 | $1.82 | $1.66 |
| Gemini 3.8 Flash (intro) | 4 | 163, 163, 163, 59 | 337,101 | $1.38 | $1.26 | $0.69 | $0.63 |
| GPT-5 nano | 3 | 217, 304, 27 | 399,639 | $0.13 | $0.11 | $0.06 | $0.06 |
| Local 27B / 16 GB | 35 | 3–32 | 31,972 | $0 | $0 | — | — |

Haiku's 160-card batch is the 64k output cap. Sonnet's 320-card batch is the 128k output cap. Gemini's 163-card batches are the 65,536 output cap. GPT-5 nano is bound by the 400k context. Local 32k context packs 3–32 cards; **the 60-card induce does not fit** (75,222 + 6,000 assumed output > 32,000). Hours below still include that unpackable induce in the token total so the intended pass is priced; they are not a runnable local schedule.

Local hours at 7–22 tok/s, **output tokens only** (generation-bound): **2.84–8.94 h** for 225,200 output tokens. If prefill of input is billed at the same tok/s (worst case, it is not), 14.4–45.1 h.

Client-loop shape (`dryrun.py --batch 12`, 46 assign calls, last batch 8 cards, taxonomy repeated): Haiku **list $2.11** ($1.93 / 500). Still inside 2× as a forecast. That is the option-iii path if the calling client cannot pack to the model's cap.

## Vs the council "$1 per 500 on Haiku"

The council figure was "full re-shelve over summaries," Haiku, ~$1 / 500. This pass is **cards**, which are larger than a 300–500 token summary, plus a 60-card induce.

The forecast still lands **under** $1 / 500 on Haiku batch because output (400 tokens × 548 × $2.50 / MTok batch) is $0.563 of the $0.921, and input is $0.358. Extra assign calls from honest packing add a small amount of repeated taxonomy versus the old illegal 4-call pack ($0.917). A summary-only pass would be cheaper still.

| Comparison | USD / 500 | × council | Kind |
|---|---|---|---|
| Council Haiku (summaries, arithmetic) | $1.00 | 1.00× | estimate |
| **Haiku 4.5 batch, cards, first-fit packed** | **$0.84** | **0.84×** | forecast (`estimated_tokens`) |
| Haiku 4.5 list, cards, first-fit packed | $1.68 | 1.68× | forecast |
| Haiku 4.5 list, 12-card client batches | $1.93 | 1.93× | forecast |
| Sonnet 5 batch, first-fit packed | $1.66 | 1.66× | forecast |
| Gemini 3.8 Flash batch, first-fit packed | $0.63 | 0.63× | forecast |
| GPT-5 nano batch, first-fit packed | $0.06 | 0.06× | forecast |

Operational G4 is not this table. It needs measured usage on the chosen client.

## What this does not measure

- Assignment *quality* (Gemini's gold set / local bench).
- Thinking / reasoning tokens (Gemini list price includes them when thinking is on; this pass assumes non-thinking JSON, matching the Librarian spec).
- Prompt-cache hits (would cut Haiku input toward $0.10 / MTok on the taxonomy).
- A real induce output. 6,000 tokens is a filled 40–80 node taxonomy, not a model run.
- The live 551-item index. The copy is 548 items, 3,216 clips.
- Request/response `usage`, retries, successful-item coverage, or wall time.

Re-run: `python scripts/library/cost_model.py --index <copy.db>` from the worktree root. Prints the forecast tables plus JSON with `estimated_tokens`, `reported_usage: null`, `paid_cost: null`. Opens the file `?mode=ro`. Copy a WAL-mode source to a writable disposable file first.
