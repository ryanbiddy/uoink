# Loki (Libr-AI/OpenFactVerification) — vendored design reference

This directory pins the **design** that Uoink v3 A2 (claim extraction +
verification) draws from. Loki's 5-step pipeline is the structural
ancestor of our `claims.py` module + `/claims/*` endpoints.

## Upstream

- Repository: <https://github.com/Libr-AI/OpenFactVerification>
- License: MIT
- Pinned commit reference: see `PINNED-COMMIT` below.

## What is vendored here

A **design-only** pin -- we do NOT vendor the running Python package in
this directory. Reasons:

1. **Compute policy alignment.** Uoink's locked compute policy is
   *model-agnostic by default; the calling agent does the LLM work via
   MCP*. Loki's runtime code calls OpenAI/Anthropic directly with its
   own API client + key. Importing the package as a Python dep would
   bypass our policy and the BYO-key consent path. Our implementation
   instead routes the LLM work through MCP (the agent calls
   `extract_claims` + `verify_claim` with structured payloads it
   produced; the helper persists the structure).

2. **Dependency surface.** Loki's transitive deps (openai, requests,
   bert-score, langchain) would expand the embeddable Python install
   we ship. We keep the surface tight by importing only what our
   helper actually needs (stdlib + the existing SQLite layer).

3. **Attribution + lineage.** This VENDOR.md is the credit + lineage
   record. The structural design is Libr-AI's; the helper-side
   persistence + MCP tool surface is Uoink's. If the licensing requires
   us to ship a copy of the LICENSE file alongside the inspired code,
   that file lives at `vendor/loki/LICENSE`.

## PINNED-COMMIT

Pinned to the HEAD of <https://github.com/Libr-AI/OpenFactVerification>
as of 2026-05-29. To re-pin, update this line + bump the date and
re-record the LICENSE if it changed upstream.

## The 5-step pipeline (Loki -> Uoink mapping)

| Loki step | Uoink surface | Notes |
|---|---|---|
| 1. Decompose transcript into claims | `extract_claims(video_id, claims=[...])` MCP tool. Agent extracts; helper persists. | Calling agent uses its own model. |
| 2. Assess check-worthiness per claim | `check_worthiness` field (0.0-1.0) on each claim row. Optional -- agent supplies. | Helper does not score. |
| 3. Generate verification queries | Agent-side. Uoink does not store these (transient working data). | -- |
| 4. Retrieve evidence | Agent-side (web search via its own tools, opt-in per claim). Uoink stores the evidence rows. | First outbound surface in A2; opt-in. |
| 5. Surface evidence + claim | `verify_claim(claim_id, evidence=[...])` writes the structured evidence; dashboard renders. **alignment_signal** is restricted to `supports / contradicts / mixed / inconclusive`. NEVER auto-asserts a verdict. | Locked vocabulary -- see `claims.py:_ALIGNMENTS`. |

## License attribution

Loki is MIT-licensed. Per MIT terms, attribution + the license text
must accompany the derivative work. The LICENSE file in this directory
is a copy of Loki's at the pinned commit. Distribute Uoink builds with
this directory intact.
