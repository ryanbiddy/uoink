# Phase 3 brief: standing capture with durable consent and limits (2026-09-07)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`, from `ASTRA-PHASE-PLAN-2026-09-04.md`
("Phase 3: standing capture with durable consent and limits") and Ryan's decisions 1, 4, 5
and 9 (`DECISIONS-2026-09-04.md`). Ryan's 2026-09-07 authorization covers this phase. No
worker runs a model, the helper, or touches port 5179 or the live index. No paid spend.
Phase 2's assignment work continues in parallel (stage 3 measured pass); this run must not
touch `library_work.py`, `library_cards.py`, the proof harness, prompts, or Phase 2 tests.

## Scope (from the phase plan, frozen here)

One subscription abstraction over the existing podcast feeds and a YouTube channel/playlist
detector, with detection independent from capture. X watching stays out; Twitch stays
notify-only. Decision 5 holds: per-source opt-in, default off; 25-item back catalog per
source; 10 starts per source per UTC day. A scheduler tick may scan frequently; network
polling uses the source's due time. The watcher does no model reasoning. A successful ingest
enqueues classification (Phase 2 work rows) only after the corpus/index commit; a stopped
client leaves a visible unfiled item.

Existing places to integrate, not proof the watcher exists: `server.py:7245`
(`_podcast_feed_scheduler_tick`), `podcasts.py:504` (`poll_feed`), `mobile_playlists.py`,
the Sources UI in `assets/dashboard/index.html`. The current daily count infers starts from
download/transcript/job timestamps (`podcasts.py`, near the daily cap); replace that
inference with an atomic start ledger before relying on it under concurrency.

## Fable's reservations

1. **Base:** the commit this brief lands in.
2. **Migration number:** `0028_source_subscriptions.sql` is reserved for this phase (one
   migration: subscriptions, consent state, start ledger, detection cursor, reservation
   rows). Nobody else allocates 0028.
3. **Owners:** Astra = `docs/library/PHASE3-CONTRACT-2026-09-07.md` (state machine, schema,
   scheduler and ledger semantics, registry tool contract, acceptance gates) and later the
   review of deduplication, persisted start reservations and restart behavior. Claude
   worker = `source_subscriptions.py` (new), the 0028 migration, scheduler adaptation in
   `server.py`, registry tools in `uoink_mcp_tools.py`, and tests under
   `tests/test_source_subscriptions*.py`, after the contract is frozen. Gemini = real UI
   consent flows and failure-case tests (`assets/dashboard/index.html`, dashboard tests).
   Grok = `docs/library/PHASE3-ADAPTER-LIMITS-2026-09-07.md`: the chosen YouTube detection
   adapter's documented limits and any source-specific policy changes since the decisions,
   without reopening accepted defaults.
4. **Sequence:** this run (AL) freezes the contract and the adapter-limits note. Run AM
   implements against the frozen contract (Claude worker + Gemini), with Astra reviewing
   the shared surfaces. Run AN is acceptance on the integrated candidate, including one
   controlled end-to-end run on a disposable helper with a local fixture feed.

## Gates (acceptance requirements, not achieved measurements)

Initial enrollment obeys the 25-item cap; off/on/off transitions are explicit and durable;
repeated discovery does not duplicate capture; concurrent schedulers cannot overspend a
daily allowance (atomic reservation, tested with two schedulers); a reservation survives
restart; failed downloads and retries have defined accounting; UTC-day boundaries are
tested; a newly detected source item lands once with valid provenance, clips where
available, an unfiled visible state, and a Phase 2 work row created only after commit.

## codex (GPT-6 Astra): the Phase 3 contract

Write `docs/library/PHASE3-CONTRACT-2026-09-07.md` after inspecting the current scheduler,
podcast polling, playlist code and the 0027 substrate. Freeze: the subscription row and
its consent state machine (off -> on with back-catalog enrollment -> off, with what happens
to in-flight reservations); the start ledger (row per reserved start, UTC-day key, atomic
claim, release on failure with retry accounting, survives restart); detection cursor per
source (RSS entry ids for podcasts; the YouTube adapter's id per Grok's note) independent
of capture; scheduler tick versus due-time polling; the 0028 migration DDL; registry tools
(`list_sources`, `set_source_consent`, `source_status`, plus any needed by the UI) with
JSON schemas in the style of `docs/library/phase2-contract/tool-schemas.json`; the
post-commit enqueue into Phase 2 work rows; and the acceptance gates as tests to write.
Name every ambiguity you resolve. Do not write code. Do not commit.

## grok: adapter limits note

Write `docs/library/PHASE3-ADAPTER-LIMITS-2026-09-07.md`: for YouTube channel/playlist
detection without capture, the documented limits of the adapter already in the repo
(`yt_extract.py`, `mobile_playlists.py`, yt-dlp usage) and of RSS-based detection (YouTube
channel feeds), rate posture consistent with decision 4, and any policy change since
2026-09-04 that affects podcasts or YouTube detection. Cite the source of every limit. Do
not reopen accepted defaults. Do not write code. Do not commit.

## gemini: UI consent and failure test plan

Write `docs/library/PHASE3-UI-TEST-PLAN-2026-09-07.md`: the real consent flows in the
Sources UI (default off, explicit on, back-catalog enrollment shown, daily allowance shown,
off again with in-flight state visible), failure cases (feed unreachable, download failure,
allowance exhausted, restart mid-reservation), and the malformed and adversarial inputs the
UI and registry tools must reject. List the tests you will write in run AM with their
fixtures. Do not write code. Do not commit.
