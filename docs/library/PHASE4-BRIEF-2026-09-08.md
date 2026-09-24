# Phase 4 brief: reachability that a supported client actually uses (2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`, from `ASTRA-PHASE-PLAN-2026-09-04.md`
("Phase 4") and the research memo `MCP-REACH-2026-09-04.md`. Ryan's 2026-09-07 authorization
covers this phase. No worker runs a model, the resident helper, or touches port 5179 or the
live index. No paid spend. Phase 2 stage 4 and Phase 3 repairs continue in parallel; this run
must not touch `library_work.py`, `library_cards.py`, `source_subscriptions.py`, the proof
harness, prompts, or Phase 2/3 tests.

## Scope (from the phase plan, frozen here)

The early repair increment already hardened Recall and the clip read tools. Remaining:
bounded resource reads and resource templates, user-invoked prompts, generated briefs,
client installation/configuration, and an opt-in corpus mirror. Support **one concrete
client/transport pair end to end** before multiplying connectors: Claude Code over stdio MCP
(`uoink_mcp.py`), because it is installed on this machine and can be verified without a
tunnel. Do not put the local helper on a public tunnel. Keep old clients operational while
testing any SDK migration; the official 2026-07-28 MCP release includes Python support and
its migration path is the starting point, not a rewrite.

Existing surfaces: `uoink_mcp.py` (377 lines, stdio), `server.py` (HTTP registry and
`/tools/*`), `scripts/recall_hook.py` (413 lines), `memory_layer.py` (355 lines),
`skills/uoink/SKILL.md`, the `.mcpb` assets and `source_manifest.py`. The memo's sections 2
(resources: URI scheme with stable item identity plus source/selection revision or a stable
excerpt key; templates instead of a 548-item list; honest sizes; capability wiring), 3
(prompts), 4 (recall hook hardening list) and 5 (Basic Memory vault mirror rules) are the
design inputs; the contract freezes them.

## Fable's reservations

1. **Base:** the commit this brief lands in. No migration is expected; if one is needed,
   `0029` is reserved and must be named in the contract.
2. **Owners:** Astra = `docs/library/PHASE4-CONTRACT-2026-09-08.md` (resource URI scheme and
   templates, read tools and their bounds, prompts, brief generation as client-run work,
   mirror contract, client verification gates) and later the browser/client acceptance and
   resource-contract review. Claude worker = transport adapters and client configuration
   (`uoink_mcp.py`, shared resource rendering module, `skills/uoink/SKILL.md`, client
   configuration docs, `.mcpb` assets) after the contract freezes. Gemini = malformed
   requests, untrusted text, deletion behaviour and mirror tests. Grok =
   `docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md`: what the current MCP specification
   and the installed Claude Code client actually support for resources, templates, prompts,
   notifications and the `.mcpb` bundle format, with citations, and any change since
   2026-07-28.
3. **Sequence:** this run (AU) freezes the contract, the protocol-limits note and the test
   plan. Run AV implements. Run AW is acceptance including a real Claude Code stdio session
   that discovers the read tools, retrieves the same item/quote/revision, follows a real link,
   survives a helper restart and reports a bounded failure when the helper is down.

## Gates (acceptance requirements)

Resource URIs carry stable item identity plus source/selection revision or a stable excerpt
key; a sequence number alone never identifies text. Only advertised capabilities are
implemented. Mirror: sanitized deterministic paths, collision handling, user-edited generated
files preserved, atomic writes, stale-output detection, tombstones, hard deletion, and a
disconnected vault; the authoritative correction store stays separate; the mirror must not
silently expand corpus egress through another indexing tool. Resource and hook quotations
pass the same trust-boundary tests as the tool path. Old clients keep working.

## codex (GPT-6 Astra): the Phase 4 contract

Write `docs/library/PHASE4-CONTRACT-2026-09-08.md` after inspecting `uoink_mcp.py`,
`server.py`'s tool registry, `scripts/recall_hook.py`, `memory_layer.py` and the memo. Freeze:
the resource URI grammar and the template set; the bounded read contract (byte and excerpt
limits, revision binding, refusal shapes); the prompt set (names, arguments, what each
returns, no server-side model reasoning); brief generation as a client-run job over the
Phase 2 work queue (no new server cognition); the mirror contract (paths, atomicity, stale
detection, tombstones, deletion, disconnected vault, correction store separation); the
capability advertisement rules; the client configuration artifacts; acceptance gates as
tests to write, and the real-client verification procedure. Name every ambiguity you
resolve. Do not write code. Do not commit.

## grok: protocol and client limits note

Write `docs/library/PHASE4-PROTOCOL-LIMITS-2026-09-08.md`: the MCP specification's current
resource, template, prompt, notification and capability rules; what the installed Claude
Code CLI (2.1.261) supports as an MCP client over stdio; the `.mcpb` bundle format's current
requirements; sizes and rate limits that bound resource reads; any specification or client
change since 2026-07-28. Cite the source of every limit. Do not write code. Do not commit.

## gemini: adversarial and mirror test plan

Write `docs/library/PHASE4-TEST-PLAN-2026-09-08.md`: malformed resource requests, untrusted
text in resources and prompts (prompt-injection fences identical to the tool path), deletion
and tombstone behaviour, mirror edge cases (collisions, user edits, atomic writes, stale
output, disconnected vault), helper-down failure shapes, and the tests you will write in run
AV with their fixtures. Do not write code. Do not commit.
