# Review brief, 2026-09-04 (run C): security review + deep review

Base: the merged `cc/living-library` branch after runs A and B (Phase 0 + Phase 1 integrated,
528 tests passing). Read `docs/library/THE-LIVING-LIBRARY-2026-09-04.md`,
`DECISIONS-2026-09-04.md`, and `ORCHESTRATION-2026-09-04.md` first. Then the run A/B
deliverables in `docs/library/`: `D-17-*`, `WORK-QUEUE-CONTRACT-*`, `MCP-REACH-*`,
`DECISION-MEMO-*`, `POLICY-MEMO-*`, `COST-MODEL-*`, `PROMPT-SPECS-*`, `G2-BM25-RESULTS-*`,
`gold-set-*.json`. Find your worker name below and do only that section.

Shared rules: own worktree, commit as you go (if git refuses, leave files in place and say so),
never merge or push, never open the user's live index at `%LOCALAPPDATA%\Uoink\index.db`.
An UPGRADED read-only copy of the live index (schema 25, clips built, source_type repaired,
548 items) is at `C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04-upgraded.db`.
Tests: `PYTHONPATH=. python -m pytest -q tests/ -p no:cacheprovider` (about 36 s).
Cite `file:line` for every claim about code. Never report a number you did not produce.

## gemini: security review across everything

Deliverable: `docs/library/SECURITY-REVIEW-2026-09-04.md`. No code edits. You may add
tests under `tests/security/` that DEMONSTRATE a finding (they may fail; mark them xfail
with the finding id).

Scope is the whole tool, weighted toward what changed today:

1. **Model-context injection.** Every path where third-party content (transcript clips,
   evidence cards, X post text, page text, podcast transcripts, notes) is returned to a
   model: `search_clips`, `get_evidence_card`, `search_uoinks`, `get_uoink_corpus`,
   `scripts/recall_hook.py` (UserPromptSubmit additionalContext), the Librarian prompts in
   `scripts/librarian/`, `dryrun.py`, `bench_local.py`. For each: is the content fenced and
   labeled as data, can a creator's sentence become an instruction, what is the blast radius
   (the hook runs before every prompt Ryan types in Claude Code).
2. **Local attack surface.** The helper's HTTP server (`server.py`): auth on the HTTP/OpenAPI
   registry (`openapi_bridge.py`), CORS, bind address, rate limiters, what an arbitrary
   local process or a malicious web page in the browser could call. The stdio MCP server
   (`uoink_mcp.py`). The 71-tool registry: any tool that writes files, spawns processes,
   opens URLs, or reads outside the corpus root. The new `uoink.cmd` / `uoink` CLI and how
   it authenticates to the helper.
3. **Injection and parsing.** FTS5 query construction (`_fts_query` in `index.py`),
   `clips.py` text handling, slug/path validation (`_SLUG_RE`, `_find_yoink`), markdown
   sidecar reads (`_summary_hint`), `provenance.py` URL classification, the FxTwitter v2
   response parsing in `x_extractor.py`, yt-dlp invocation and argument handling.
4. **Egress inventory.** Every outbound network call in the codebase, as a table: file:line,
   destination, what data leaves (URL, id, text, key), trigger, opt-in or automatic. Include
   the new `api.fxtwitter.com` call, Anthropic calls, yt-dlp, podcast enclosures, syndication.
5. **Secrets and settings.** Where API keys live, how settings are validated
   (`_normalize_settings`), the `obsidian_vault_path` validation, log lines that could leak
   keys or corpus text.
6. **The watchdog and exit-code changes** in `server.py` and `scripts/install-watchdog.ps1`:
   privilege, task-runs-as, restart loops, anything a local user could abuse.
7. **Supply chain.** Pinned dependencies (`mcp==1.27.1` and the rest), vendored binaries,
   the installer build inputs.

Format: findings ranked by severity (Critical / High / Medium / Low / Info), each with id,
file:line, a concrete exploit scenario, and the minimal fix. Then the egress table. Then a
"what I did not check" list. If a claim cannot be verified from the code, do not make it.

## codex (GPT-6 Astra): deep review + recommendations + how the phases get built

Three deliverables, no code edits.

1. **`docs/library/ASTRA-REVIEW-2026-09-04.md`.** A deep, honest review of uoink as it
   stands: the product (does the living-library thesis hold against what the code can
   actually do), the architecture (helper + index + registry + extension + MCP), the code
   quality of today's Phase 0/1 work commit by commit (`git log 3e06c65..HEAD`), the four
   contract docs from the Claude worker, the cost model and gold set. Measure, do not
   estimate: query the upgraded index copy, run the test suite, run `scripts/library/
   bm25_eval.py` and `scripts/library/cost_model.py` against the copy, exercise
   `search_clips` / `get_evidence_card` through the Python tool handlers on real items.
   Say what is strong, what is weak, and what in the direction doc you believe is wrong.
2. **`docs/library/ASTRA-PHASE-PLAN-2026-09-04.md`.** Recommended next steps and how
   Phases 2 through 6 should be built: sequencing (including anything you would reorder or
   cut), a per-phase contract (scope, files, gates, which engine owns what and why), the
   integration strategy for the branch (it sits on the unreleased 3.8.0 line, 7 commits
   ahead of `origin/main`), and the three follow-ups already known: recall-hook hardening,
   the entity-extraction flag (D-17), and reconciling the two evidence-card sizes
   (`get_evidence_card` = 10 untruncated clips; `dryrun.py` = 6 clips at 240 chars).
3. **`docs/library/ORCHESTRATION-ASTRA-RESPONSE-2026-09-04.md`.** Your response to
   `ORCHESTRATION-2026-09-04.md`: what Fable got wrong, what you would own, and the concrete
   first computer-use verification you would run on uoink (the helper, the dashboard at its
   local port, the extension) and what it would prove.

End with the compact handoff. Lead with what you measured.
