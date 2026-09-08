# Phase 3 implementation brief (run AM, 2026-09-07)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract: `phase3-v1-2026-09-07`
([PHASE3-CONTRACT-2026-09-07.md](PHASE3-CONTRACT-2026-09-07.md), Astra). Adapter limits:
[PHASE3-ADAPTER-LIMITS-2026-09-07.md](PHASE3-ADAPTER-LIMITS-2026-09-07.md) (Grok). UI plan:
[PHASE3-UI-TEST-PLAN-2026-09-07.md](PHASE3-UI-TEST-PLAN-2026-09-07.md) (Gemini). Base: the
commit this brief lands in. No worker runs a model, the resident helper, or touches port
5179 or the live index; tests use temporary databases and fake adapters, clocks and queue
workers. No paid spend. Do not commit; Fable integrates in dependency order.

## Reconciliation (Fable's rulings)

1. **Detector** = Grok's frozen rule 1 and the contract agree: HTTP GET of YouTube's Atom
   `feeds/videos.xml?channel_id=` or `?playlist_id=`; identity = bare video id; no Data API,
   no PubSubHubbub, no handle resolver, no yt-dlp listing for detection. Podcasts keep RSS
   entry ids. Capture stays the existing caption-first yt-dlp path and only after consent and
   an atomic start reservation.
2. **Back catalog** = ceiling 25; the Atom window (about 15) is adapter coverage, reported,
   never backfilled (contract S03, Grok rule 4).
3. **Consent surface** = the contract's registry tools and their capability requirement
   govern. Gemini's plan names `/api/sources/subscriptions/consent` and an integer
   `source_id`; the implementation exposes exactly the tool names, argument schemas and
   dashboard endpoints the contract's "Registry and dashboard contract" section defines, and
   Gemini's tests target those. Where the plan and the contract differ, the contract wins;
   Gemini records each such adaptation in its test file header.
4. **Adapter edits**: Claude owns the required edits in `podcasts.py` and
   `mobile_playlists.py` so the old paths cannot bypass the contract (Astra's explicit ask),
   plus `server.py`, `uoink_mcp_tools.py`, the new `source_subscriptions.py`, and
   `migrations/0028_source_subscriptions.sql`. Gemini owns `assets/dashboard/index.html`
   and dashboard/API tests only. Astra owns independent service tests. Nobody edits
   `library_work.py`, `library_cards.py`, prompts, the proof harness, or Phase 2 tests.
5. **Packaging** (S22) is deferred to run AN with Fable as owner of `build.ps1` and
   `installer/uoink.iss` edits; workers list what must be packaged.

## claude (Fable 5.1 worker): service, migration, scheduler, registry, adapters

Implement the contract. Files: `source_subscriptions.py` (new),
`migrations/0028_source_subscriptions.sql` (the contract's DDL; the number is reserved),
`server.py` (replace the standing-work coordinator with separate detection and capture
passes; dashboard endpoints; keep heartbeat, poll-success, poll-failure and ingest
distinct), `uoink_mcp_tools.py` (the four registry tools with the contract's JSON schemas
and capability check), `podcasts.py` and `mobile_playlists.py` (route standing capture
through the reservation; never capture from detection), and tests
`tests/test_source_subscriptions*.py` covering gates S01 to S19 that a service test can
cover with fixtures (S20 is Gemini's, S21 and S22 are AN). You cannot run a shell in this
harness: write the tests so Fable can run `python -m pytest -q tests/test_source_subscriptions*.py`,
and list in your final message every command Fable must run and every assumption you
could not verify. Keep each function small and the state machine explicit; cite the
contract section in a comment at each transition and ledger operation.

## gemini: dashboard consent flows and their tests

Implement the Sources UI per your plan against the contract's endpoints and payloads
(`assets/dashboard/index.html` only), and write the dashboard/API tests under
`tests/test_dashboard_sources*.py` with fixtures under `tests/fixtures/phase3/`. Tests that
depend on the service (endpoints) will run after Fable integrates the claude section; mark
them so they skip cleanly when the endpoint module is absent, and state which ones those
are. Do not edit `server.py`; list the endpoint behaviours you rely on so Fable can verify
them against the contract.

## codex (GPT-6 Astra): independent acceptance tests

Write independent tests for the contract's concurrency, reservation, restart and
deduplication gates (S04, S05, S09, S10, S12, S13, S14, S15, S16, S17) under
`tests/library_work_astra/test_phase3_*.py`, driven only by the contract's public interface
(module `source_subscriptions`, the tool names and schemas, the ledger tables in 0028) with
fake adapters, clocks and two-connection fixtures, in the style of your Phase 2 tests. The
implementation does not exist in your worktree; write against the contract and say which
interface details you had to assume so Fable can align them at integration. Include a
migration replay test that runs 0028 twice through the real runner (S01). Do not edit any
other file.
