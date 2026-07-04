# Changelog

All notable changes to Uoink are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project follows [semantic versioning](https://semver.org/spec/v2.0.0.html).

> Releases through 2.0.0 shipped under the product's original name, **Yoink**.
> Those historical entries are left unchanged. The product was renamed to
> **Uoink** in 2.1.0; see below.

## [3.2.5] - 2026-07-04

### Added

- **Captions-only retry for long videos.** Activity and detail surfaces can retry a stuck source in lite mode, keeping the transcript path while skipping the fragile extras.
- **Smart Generate inputs.** Topic, channel, hook, target-length, CTA, and style-anchor controls now pull from the local corpus instead of asking for raw values.
- **Source-first recovery actions.** Detail and Evidence now expose Open folder, Open transcript file, Re-capture, Re-transcribe, Evidence, and Run claim scan where those actions help.

### Changed

- **Library state model.** No matches, empty corpus, unavailable Library, invalid dates, and corpus-wide facets now render as distinct states with human copy.
- **Dashboard copy and accessibility pass.** Raw helper/route/config language moved behind advanced disclosures, keyboard card activation works, modals trap focus, and placeholder-led controls have accessible names.
- **Settings polish.** Output folder picking, topic undo, model/key status copy, and transcript checker controls now read like product settings instead of implementation details.

### Fixed

- **Generate workspace validation.** Blank or hidden workspace creation is rejected before anything is written.
- **Activity duplicate failures.** Failed single-video jobs and retry rows dedupe by source so the same source does not double-render.
- **Stop Uoink confirmation.** Stop controls now ask first and avoid the old one-click helper shutdown path.
- **Writing Studio no-op actions.** Blank Copy is disabled, Save waits for a real draft, and stale `Use as-is` behavior is gone.

## [2.1.1] - 2026-05-26

### Added

- **Helper-served `/dashboard` endpoint** (Codex PR <TBD>) — serving a local web interface with connection health status pills and a list of recent uoinks.
- **System tray icon via `pystray`** (CC PR <TBD>) — provides ambient status in the system tray with context menu options to Open Dashboard, Open Uoink Folder, view Recent Uoinks, and Stop Helper.
- **Branded installer bitmaps & startup toast** (CC PR <TBD>) — adds `WizardImageFile` and `WizardSmallImageFile` assets to Inno Setup, and triggers a "Uoink is running ✓" notification balloon on first launch.
- **Brand v3.1 contrast rules doc** (`BRAND-CONTRAST-RULES.md`) — introduces `--rust-bright #F97316` as a canonical token for standard text on dark grounds where `--rust` fails WCAG AA.

### Fixed

- **Orphan Yoink autostart Registry key** (CC PR <TBD>) — sweeps the legacy `Yoink` autostart value in `HKCU\...\Run` under `_is_installed_layout` guards.
- **Stale branding & broken Windows CTA** (AG PR #3) — re-applies direct Windows CTA installer link and renames remaining user-visible "Yoink" setup references in `extension/setup.js` and `extension/setup.html`.

## [2.1.0] - 2026-XX-XX <!-- TODO: fill on tag -->

### The rename

Yoink is Uoink. The magnet logo was always a U — the name finally matches it.
New home: uoink.video. This release is backward-compatible: existing v2.0
installs migrate themselves on first launch, and old MCP tool names keep working.

### Added

- **macOS universal build** (Apple Silicon + Intel) — the `.dmg` pipeline from
  Sprint 19.5 Stage 2.
- **Automatic install migration.** On first launch the helper copies
  `%LOCALAPPDATA%\Yoink\` → `\Uoink\`, migrates the autostart entry, moves the
  Anthropic key in Credential Manager, and leaves a `MIGRATED_TO_UOINK.txt`
  breadcrumb. The old folder is kept for a 7-day grace period, then removed.
- **One-time post-migration notification** confirming the rename and where your
  files went.

### Changed

- **Renamed Yoink → Uoink across the product:** brand strings, install path
  (`%LOCALAPPDATA%\Yoink\` → `\Uoink\`), Start Menu entries, autostart key,
  keyring service name, installer (`Uoink-Setup-2.1.0.exe`), and assets.
- **MCP tools renamed** (`yoink_video` → `uoink_video`, `list_recent_yoinks` →
  `list_recent_uoinks`, `search_yoinks` → `search_uoinks`, `get_yoink_corpus` →
  `get_uoink_corpus`, `get_yoink_health` → `get_uoink_health`, `yoink_playlist` →
  `uoink_playlist`). The 6 brand-neutral tools are unchanged.
- **Domain + support:** `ryanbiddy.com/yoink` → `uoink.video`; support email →
  `hi@uoink.video`.

### Deprecated

- The `yoink_*` MCP tool names. They alias to `uoink_*` and emit a
  `DeprecationWarning` to stderr. They work through v2.5 and are removed in v3.

### Migration notes

- Nothing is lost. The Desktop corpus (`Desktop\Yoink\`) migrates via a separate,
  opt-in prompt because external tools may link to those paths.
- If the keyring migration fails, re-enter your Anthropic key on the setup page;
  `/diagnose` will flag it.

## [2.0.0] - 2026-05-20

The "YouTube layer for any AI agent" release. Three adoption funnels: Chrome extension for creators, MCP server for developers and agents, and the Yoink Operator Skill for clients that support portable skills or system prompts.

### Added

- **macOS native — Stage 1 (cross-platform Python).** Helper code now runs identically on Windows and macOS via cross-platform path resolution. Sprint 19.5 Stage 2 ships the actual `.dmg` build pipeline.
- **/diagnose adds `platform` field** — UIs can render platform-appropriate hints and status checks.
- **Platform-aware extension setup page** — install instructions dynamically adjust based on `chrome.runtime.getPlatformInfo` to show Windows- or macOS-specific commands and files.
- **Entity Extraction disclosures (store listing + README).** Added clear disclosures detailing opt-in Entity Extraction calling the Anthropic API via user-provided API key stored securely in Credential Manager. Touched `docs/store-listing.md` and `README.md`.

- **Rate-limit queue + retry (C4).** YouTube rate limits no longer cause terminal failures. Single-video yoinks queue automatically in a SQLite queue and retry with exponential backoff (60s, scaling up to a 15-minute cap, up to 3 attempts). A popup banner displays active queue counts and offers manual cancel or retry-now actions.
- **Queue management API.** Token-gated endpoints `/queue/status`, `/queue/cancel`, and `/queue/retry-now` power the queue UI.
- **Helper failure diagnosis (C3).** A new public `/diagnose` API endpoint plus a "Helper status" panel in `setup.html` that runs checks (Anthropic key, FFmpeg, yt-dlp, and output path) with context-specific recovery buttons for each failure mode.
- **`LOCALAPPDATA` output fallback.** The helper automatically falls back to writing outputs to `%LOCALAPPDATA%\Yoink\output` if `DESKTOP_ROOT` is read-only or unwritable.
- **`pending_yoinks` schema (migration 0005).** Adds a new table in `index.db` to track rate-limited yoinks, attempts, and errors.

- **MCP server** with 14 tools (`uoink_video`, `uoink_playlist`, `get_job_status`, `cancel_job`, `list_recent_uoinks`, `search_uoinks`, `get_uoink_corpus`, `analyze_comments`, `classify_hook`, `get_taxonomy`, `get_citation_map`, `get_uoink_health`, `find_mentions`, `get_transcript_reliability`). Stdio transport officially tested with Claude Desktop and Cursor. Local HTTP JSON-RPC transport available, marked experimental.
- **Library Index (SQLite FTS5).** `%LOCALAPPDATA%\Yoink\index.db` replaces scan-based search/recent/get-taxonomy code paths where indexed consumers need fast library access. First boot backfills existing corpora; subsequent yoinks update incrementally.
- **Migration framework.** `schema_version` table plus numbered `migrations/NNNN_*.sql` scripts for future schema changes.
- **Yoink Memory page.** New corpus gallery at `chrome-extension://<id>/yoink-memory.html`, opened from the popup's "View all yoinks" link. Filters by search text, channel, topic, Hook Type, and date range, with pagination at 50 results/page.
- **Soft delete with 30-day trash.** Deleting from Yoink Memory marks `yoinks.deleted_at`, moves the folder to `_yoink-trash/`, hides it from normal reads, and keeps it restorable until the scheduled hard purge.
- **Memory HTTP endpoints.** New token-gated `/memory/search`, `/memory/delete`, and `/memory/restore` routes power the Memory page. Sprint 18 adds no MCP tools; the MCP tool count stays at 13.
- **Memory schema migration.** Migration 0004 adds `yoinks.deleted_at` plus `idx_yoinks_deleted_at` to support Memory-page soft delete and trash purge lookups.
- **Citation map.** Pre-computed at extraction/index time; new MCP tool `get_citation_map(slug)` returns transcript and screenshot citations with YouTube deep links.
- **Health score.** Sidecar/index health snapshot for transcript, screenshots, comments, Hook Type, and Comment Intelligence; new MCP tool `get_yoink_health(slug)` returns the dict used by popup Recent health icons.
- **Entity extraction from transcripts.** Optional BYO-Anthropic-key worker extracts people, tools, products, topics, companies, and other named entities from new yoinks when AI features are enabled.
- **Entity graph tables.** Migration 0002 adds `entities` and `entity_mentions` tables to `index.db`, keyed by normalized entity name/type and linked back to `yoinks.video_id`.
- **MCP `find_mentions(entity, limit)` tool.** Agents can ask where a person/tool/product/topic/company appears across the local corpus; results include title, channel, timestamp, context, and YouTube deep link.
- **Yoink Operator Skill** - drop-in `SKILL.md` (agentskills.io open standard) covering identity, default chat, hook-autopsy tweet mode, and citation discipline. Distributed via Claude Code plugin, OpenClaw ClawHub, Hermes URL install, and copyable system prompt for everywhere else.
- **Playlist Mode.** Paste a YouTube playlist URL, yoink up to 10 videos per job. Async job system with live progress, cancellation, and partial-failure tolerance. Combined corpus (text-only) to clipboard; per-video corpora with screenshots on disk.
- **Comment Intelligence.** Optional Anthropic-powered analysis of comment threads. Three structured sections appended per video: top themes, mentioned products/tools, notable disagreements.
- **Hook Type classification.** Optional Anthropic-powered classification of each video's opening style across 9 categories: curiosity gap, question, contrarian, story open, promise/list, demo, authority, stakes, other.
- **Self-calibrating Hook Type classifier (A3).** User corrections are stored in `taxonomy_corrections`; future classifications inject similarity-matched past corrections as few-shot anchors. `classify_hook` now returns `confidence` (1-5) and `similar_corrections_used`.
- **Hook Type correction endpoint.** New token-gated `POST /taxonomy/correct` records user corrections and promotes the corrected category to canonical taxonomy.
- **Hook Type correction UI.** Popup adds a compact `wrong?` affordance with category dropdown; setup.html adds a "Hook Type calibration" list for recent corrections.
- **Smart Screenshot Picker.** Opt-in post-extraction grid for selecting which screenshots make the clipboard.
- **Setup page** (`setup.html`) with BYO Anthropic API key flow, feature toggles, and MCP config snippet generator for Claude Desktop, Cursor, and generic stdio clients.
- **Anthropic API key encryption.** Keys stored via Windows Credential Manager (`keyring` library), never plaintext. Migrates any plaintext anthropic_key from settings.json into Windows Credential Manager on first run.
- **Job persistence across helper restarts.** `/jobs` state survives helper restart via `%LOCALAPPDATA%\Yoink\index.db`. In-flight jobs are marked failed with `error="server restarted"`; users restart them manually.
- **Hook Type taxonomy capture.** Every successful classification upserts into the local `taxonomy` table in `index.db` (deduplicated by video ID) for v2.0 dataset queries via `GET /taxonomy` and the `get_taxonomy` MCP tool.
- **jobs.json / taxonomy.json migration.** Existing file-based persistence is imported into `index.db` on first boot and the old files are renamed with `.migrated` suffixes.
- **Lazy entity backfill policy.** Existing yoinks do not receive retroactive entity rows; re-yoink an older video to populate entities for it.
- **Entity graph scope guard.** Mention sentiment, temporal trends, co-occurrence, and cross-creator citation graph are deferred to Sprint 16.5+.
- **MCP tool count remains 13.** Sprint 17 modifies `classify_hook`; it does not add a new MCP tool.
- **Job recovery on popup reopen.** If you close the popup mid-playlist, reopening it resumes from the running job state via `GET /jobs`.
- **Polling resilience.** Helper-disconnect banner appears after 5 seconds of failed polls. After 30 seconds, the setup guide auto-opens in a new tab (rate-limited to once per 5 minutes across popup sessions). Recovery is automatic when the helper comes back.
- **Active-playlist pill.** When a playlist is running and the user switches to single-video mode, a persistent pill shows playlist progress. Click to return to the playlist view.
- **"Last yoink completed" affordance.** Popup boot surfaces recently completed yoinks (within 30 minutes) with an Open Folder button. Works for both single-video and playlist jobs.
- **`GET /jobs` API** with `?kind=playlist|single` filtering and `updated_at` desc sorting.
- **`/file` endpoint** for sandboxed thumbnail serving to the popup.
- **MCP `yoink_video` job logging.** Agent-triggered single-video yoinks now appear in `/jobs` and the recent-yoinks surface, matching the extension flow.
- **`docs/security.md`** rewritten to cover v2 reality: keyring, token-gated endpoints, `/file` sandbox, MCP HTTP, `index.db` persistence, and the v2 threat model.
- **`docs/v2-smoke-test.md`** - 108-checkpoint pre-launch smoke checklist.
- **Banner-link accessibility.** Disconnect-banner setup link announces "Opens setup guide in a new tab" to screen readers.

### Fixed

- **Windows installer packaging (CC).** Staged `index.py` and `migrations/*` in the Inno Setup script to support fresh database creation and migrations on clean installs. Touched `installer/yoink.iss` and `build.ps1`.
- **Migration atomicity (CC).** Wrapped database migration logic in a transaction block to ensure partial migration failures roll back cleanly. Touched `server.py`.
- **Memory page clickjacking protection (Codex).** Set `Content-Security-Policy: frame-ancestors 'none'` headers to prevent the Yoink Memory tab from being embedded in unauthorized frames. Touched `server.py` and `extension/manifest.json`.
- **Hook Type few-shot prompt injection (CC).** Sanitized corrected Hook Type category strings used in few-shot templates to prevent prompt injection. Touched `server.py`.
- **Privacy policy storage and Mac Keychain disclosures.** Disclosed local SQLite persistence (`index.db`), soft-delete folder retention (`_yoink-trash/`), and Python `keyring` storage on macOS. Touched `docs/privacy-policy.md` and `docs/store-listing.md`.
- **Memory page thumbnail blob URL leak (Codex).** Implemented LRU eviction for generated blob URLs to prevent browser memory leaks during extensive search/scroll sessions. Touched `extension/lib/ui.js` and `extension/yoink-memory.js`.
- **Delete confirm dialog rename (Codex).** Renamed "Delete" confirmation action to "Move to trash" in the delete confirmation dialog to align with the 30-day retention behavior. Touched `extension/yoink-memory.html`.
- **Version verification in build validation.** Fixed script `verify-launch-readiness.py` to correctly parse model version numbers. Touched `scripts/verify-launch-readiness.py`.
- **Popup queue rendering exception.** Fixed reference error in queue status rendering within the extension popup when queue state is empty. Touched `extension/popup.js`.
- **Index batch enrichment optimization.** Optimized `Index.enrich_yoinks(rows)` to fetch taxonomy and health status in batches rather than per-row queries. Touched `server.py`.
- **MCP index lookup path traversal guard.** Ensured `Index.get_by_slug` resolves paths safely and rejects parent directory references. Touched `server.py`.
- **Legacy index regeneration overhead.** Offloaded legacy `_all-yoinks-index.md` regeneration from the hot path to a background worker to prevent server blocking. Touched `server.py`.

### Changed

- **Consolidated extension helpers (Codex).** Unified duplicate storage and formatting helper functions across popup, setup, and memory scripts into `extension/lib/ui.js` to improve maintainability and ensure ESLint compliance. Touched `extension/lib/ui.js`, `extension/popup.js`, `extension/setup.js`, and `extension/yoink-memory.js`.
- **Changelog and backlog version alignment.** Updated roadmap and backlog items to consistently reference minor version `v2.1` instead of legacy `v1.1`. Touched `README.md` and `BACKLOG.md`.
- **Clipboard budget preview in popup (C1).** Shows a dynamic token and screenshot count preview ("N screenshots · ~Nk tokens") adjacent to the Send buttons to help users estimate context window consumption before pasting.
- **Popup progressive disclosure (C2).** Optimizes first-run UI by collapsing advanced settings and secondary panels under a "More options" expander. First-day users see a single clear URL input and Yoink CTA.
- **Confidence display in popup chips.** Hook chips now display the category alongside the model's confidence rating (e.g., "Contrarian · confidence 5/5") rather than just the category name.
- **POST `/extract` response.** Returns `queued: true` along with a `pending_id` and a `retry_after` timestamp when YouTube rate limits are hit instead of returning an application error.
- **`/health` response.** Adds `output_root_fallback: bool` indicating whether the helper has fallen back to writing in `%LOCALAPPDATA%`.
- **MCP tool count remains 13.** (Unchanged — Sprint 19 is HTTP and UI only).

- **Anthropic API key storage moved from plaintext `settings.json` to Windows Credential Manager.** Existing keys are migrated automatically on first v2.0 startup.
- **`get_yoink_corpus` MCP tool** now returns `video_id` and `video_url` alongside `corpus_md` and `folder` for downstream tool composition.
- **HTTP MCP transport reframed as experimental.** Stdio remains the officially tested and supported transport. Setup page and docs updated accordingly.
- **Single-video job records in `/jobs`** no longer persist the multimodal clipboard payload (`corpus_md_paste`), preventing job-table bloat. Full corpus remains available via `get_yoink_corpus` and the on-disk session folder. Legacy bloated records are stripped during migration.
- **Corpus and sidecar writes** now use atomic tmp-then-rename pattern (already used for settings, jobs, taxonomy), eliminating partial-file risk on crash.
- **JSON-RPC `notifications/initialized`** now returns 202 with no body, aligning with HTTP semantics for fire-and-forget notifications.
- **`build.ps1`** SHA256 hash constants are locked. Comments and build-installer.md narrative updated to reflect locked state.

### Security

- **`docs/security.md` rewritten** to accurately describe the v2 threat model. Includes keyring-backed key storage, complete token-gated endpoint inventory, `/file` sandbox semantics, and persistence file locations.
- Chrome Web Store extension ID pinning deferred until the published listing ID is stable (planned for v2.1).

### Documentation

- New: `docs/v2-api.md`, `docs/v2-mcp.md`, `docs/v2-comment-intelligence.md`, `docs/v2-hook-type.md`, `docs/v2-smoke-test.md`, `docs/v2-prelaunch-review.md`, `docs/setup-copy-revisions.md`, `docs/backlog-review-notes.md`, `CHANGELOG.md`.
- Updated: `README.md`, `docs/security.md`, `docs/build-installer.md`, `docs/store-listing.md`, `BACKLOG.md`.

## [1.0.0] — 2026-04-XX (originally shipped before v2 development cycle; baseline)

The first public release. Single-video extraction with creator-research-grade output, local-first, no accounts, fully open source.

### Added

- **One-click "Yoink" button** under every YouTube video.
- **Right-click context menu** to yoink any YouTube thumbnail without opening the video.
- **Full timestamped transcript** with chapter awareness.
- **Timestamped screenshots** throughout the video.
- **Top 50 comments** with author and like count.
- **Full video metadata** (views, likes, tags, description, upload date).
- **Thumbnail image** included in the corpus.
- **Channel context** — subscriber count + recent videos from the same channel.
- **Auto topic-classification** into folders on disk via `topics.json` keyword rules.
- **Built-in prompt library** (11 starter prompts: "Decode the hook," "Outline the structure," etc.).
- **Two destination buttons** — Send to Claude, Send to ChatGPT.
- **Windows installer** (Inno Setup, Python embeddable, ~120 MB) with auto-start on login and clean uninstall.
- **Multimodal clipboard format** — text + up to 12 base64-inlined screenshots, fits in Claude/ChatGPT in one paste.
- **Research sessions** for multi-video corpora (v1.0 manual-session flow; v2.0 introduces Playlist Mode).
- **Local helper server** on `127.0.0.1:5179` with token-based extension auth.
- **Master `_all-yoinks-index.md`** at the Desktop\Yoink root tracking every yoink.

### Notes

- v1.0 was Windows-only. Mac installer is on the v1.1 roadmap.
- v1.0 shipped without telemetry; opt-in install-success telemetry is on the v1.1 roadmap.
