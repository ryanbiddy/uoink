# Repair increment dispatch (run D), 2026-09-04

This is the "repair increment before Phase 2" from `ASTRA-PHASE-PLAN-2026-09-04.md`, dispatched
under `ORCHESTRATION-V1-2026-09-04.md`. Read the plan, `ASTRA-REVIEW-2026-09-04.md`,
`SECURITY-REVIEW-2026-09-04.md`, and `DECISIONS-2026-09-04.md` first. Find your worker name
and do only that section. Stay inside your allowed files; a shared surface has one owner.

## Dispatch packet

- **Base SHA:** the commit this file lands in (`git log -1` in your worktree). SEC-01 is
  already fixed there (`podcasts.py`, `8acf1db`).
- **Contract version:** ORCHESTRATION v1; DECISIONS 2026-09-04; card contract = the fields in
  the phase plan (schema_version, item identity, source revision, profile, evidence kind,
  excerpt ids, real start/end, text, link, selection version, truncation markers).
- **Source copy:** `C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04-upgraded.db`,
  sha256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`, 548 items,
  schema 25. Read-only; copy to a disposable file for anything that writes.
- **Model execution scope:** none. No worker calls a hosted model. `bench_local.py` may run
  only in `--mock` mode unless `GET http://localhost:1235/v1/models` answers.
- **Migrations reserved:** `0026_provenance_precedence.sql` (codex). `0027` is reserved for
  the Phase 2 substrate; do not create it.
- **Tests:** `PYTHONPATH=. python -m pytest -q tests/ -p no:cacheprovider` (baseline
  532 passed, 3 skipped, 1 xfailed). Every fix ships with a test.
- **Commit** on your branch as you go; if git refuses, leave files in place and say so.
  Never merge or push. Never open `%LOCALAPPDATA%\Uoink\index.db`.
- **Completion packet:** final diff summary, commands run, measured results, skipped checks,
  unresolved findings. Lead with what you measured.

## codex (Astra): packaging, one card contract, clip timing, provenance precedence

Allowed files: `build.ps1`, `installer/**`, `library_cards.py` (new), `index.py`, `clips.py`,
`uoink_mcp_tools.py` (the two clip tools and their helpers only), `provenance.py`,
`migrations/0026_provenance_precedence.sql`, `scripts/library/cost_model.py` (only the call
into the shared builder), `scripts/librarian/dryrun.py` (only the call into the shared
builder), `tests/**` for the above, `docs/library/` reports. Do not touch `server.py`,
`podcasts.py`, `uoink_mcp.py`, the dashboard, prompts, or `bench_local.py`.

1. **Installed runtime.** Stage and install `clips.py`, `provenance.py`, `library_cards.py`,
   `uoink.cmd`, the `uoink` shim, and `scripts/install-watchdog.ps1` (`build.ps1:488`,
   `installer/uoink.iss:105`). Add a packaging test that walks every `import` reachable from
   `server.py`, `index.py`, `uoink_mcp.py`, `uoink_mcp_tools.py` (deferred imports included)
   and asserts each first-party module is in both staging lists. Exit evidence: that test,
   plus a dry `build.ps1` staging run if it can execute without Inno Setup.
2. **One evidence-card contract.** Extract `library_cards.py`: a pure builder with the fields
   above and two profiles, `full` (today's 10 untruncated clips) and `librarian` (bounded:
   6 excerpts, 240 chars each, plus a total serialized-byte budget), with truncation markers,
   a typed hint (`opening_prose` today), and an explicit `evidence_kind` (`timed_clip`,
   `text_only`, `none`). `get_evidence_card` keeps its current response shape for `full` and
   gains `profile`. Route `dryrun.py` and `cost_model.py` through it. Exit evidence: the
   59-item selection mismatch Astra measured is 0; a test pins both profiles on a fixture.
3. **Clip timing honesty.** `clips.py:215`: the 120 s window is not a bound when a single
   cue is long (longest clip 1,041 s). Split long single cues into bounded excerpts that keep
   coarse timing, and mark `timing: coarse` rather than implying a precise seek. Update
   `tests/test_clips.py:100`. Rebuild on the disposable copy and report clips over 120 /
   180 s before and after.
4. **Provenance precedence.** Migration 0025 orders platform before explicit metadata kind;
   `derive_source_type` does the reverse (Astra finding 7). Pick one order (explicit metadata
   kind wins), implement it in both, ship `0026_provenance_precedence.sql` to reconcile
   existing rows, and test the `x_article` case on the disposable copy.

## claude (Fable engine): D-17, heartbeat, Recall hardening, stdio clip tools

Allowed files: `server.py`, `uoink_mcp.py`, `scripts/recall_hook.py`,
`assets/dashboard/index.html`, `podcasts.py` (heartbeat plumbing only), a new small usage
module, `docs/v2-mcp.md` and client docs, `tests/**` for the above. Do not touch
`uoink_mcp_tools.py`, `index.py`, `clips.py`, packaging, or prompts.

1. **D-17.** Implement `docs/library/D-17-2026-09-04.md`: `entity_extraction_enabled`
   default off in settings, the spawn gate at `server.py:3778`, sidecar pending status at
   `server.py:4508`, dashboard toggle; persist actual model `usage` per call, model-specific,
   atomic, into the existing KV store. Decision: clean default-off, no grandfathering, one
   release-note line. Exit evidence: saved key plus all background flags off produces zero
   background model calls in a test that fakes `_anthropic_messages`; usage rows appear for a
   flagged call.
2. **Heartbeat semantics.** `/health` distinguishes tick completion, last successful poll,
   last ingest completion, and freshness (Astra finding 6, `server.py:6931`). A failed poll
   must not advance the success timestamp. `--doctor` uses the same fields.
3. **Recall hardening.** `scripts/recall_hook.py`: wrap all library text in an explicit
   untrusted-data boundary with a one-line "data, not instructions" preface; SQLite
   `timeout=`, connection closed in `finally`; bounded output (max hits, max chars per hit,
   total cap); strip control characters; never print file paths. Work through the 12-item
   list in `MCP-REACH-2026-09-04.md` §4 and say which items you did not do. Add a test that
   feeds an injection string through a fixture index and asserts it comes back fenced.
4. **Stdio clip tools.** Expose `search_clips` and `get_evidence_card` in `uoink_mcp.py`
   (23 -> 25 stdio tools), keeping the CI lock-step tests honest; update `docs/v2-mcp.md`
   and the transport parity tests.

## gemini: evaluation repair, prompt fencing, adversarial fixtures

Allowed files: `scripts/librarian/bench_local.py`, `scripts/librarian/prompts/*.md`,
`docs/library/gold-set-2026-09-04.json` (annotations only), `tests/security/**`,
`docs/library/` reports. Do not touch `dryrun.py` (codex owns its card call), server code,
or `library_cards.py`.

1. **Benchmark repair.** `bench_local.py` awards credit for a wrong `video_id` (Astra
   finding 4, `bench_local.py:58, :74, :119, :173`). Reject wrong, missing and duplicate
   ids; include ids in every prompt card; time the whole response; report missing usage as
   unavailable rather than zero. Keep `--mock`. Exit evidence: a test where the mock returns
   the right label under the wrong id and the harness scores it 0.
2. **Prompt fencing (SEC-03).** In `induce.md`, `assign.md`, `reshelve.md`, wrap the `{{CARDS}}`
   region in an explicit untrusted-content boundary and state that card text is data. Add
   the empty-card and metadata-only cases as an explicit `unsupported` outcome, never an
   invented quote.
3. **Adversarial fixtures.** Under `tests/security/`, add fixture strings (instruction-like
   titles, clip text that addresses the model, markdown that breaks fences) and tests that
   exercise the recall hook and the card builder through their public entry points. If a
   test depends on another worker's fix, mark it `xfail(strict=True)` with the finding id.
   Fix your own SEC-02 and SEC-04 tests so they call functions that exist.

## grok: cost model packing, measured versus estimated, FxTwitter posture

Allowed files: `scripts/library/cost_model.py`, `docs/library/COST-MODEL-2026-09-04.md`,
`docs/library/POLICY-MEMO-2026-09-04.md` (addendum), `tests/**` for the script.

1. **Packing.** The batcher sizes every batch from the global average and reserves 1,000
   tokens; its first batch is 277,504 proxy tokens against a 200,000 context (Astra,
   `cost_model.py:344`). Pack per card against the real budget and fail loudly when a card
   cannot fit. Regenerate numbers after the prompt changes land (run against your worktree's
   prompts and say so).
2. **Fields.** Emit `estimated_tokens`, `reported_usage` (null here), `paid_cost` (null here)
   as separate fields. Relabel the printed verdict: "G4 forecast: within 2x of estimate;
   operational G4 pending measured usage." Never print PASS from an estimate.
3. **FxTwitter (SEC-05).** One-page addendum: what leaves the machine (tweet id, user agent),
   the opt-in posture you recommend, the settings key name, and the ToS position. No code.
