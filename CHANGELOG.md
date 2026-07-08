# Changelog

All notable changes to Uoink are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project follows [semantic versioning](https://semver.org/spec/v2.0.0.html).

> Releases through 2.0.0 shipped under the product's original name, **Yoink**.
> Those historical entries are left unchanged. The product was renamed to
> **Uoink** in 2.1.0; see below.

## [3.5.0] - 2026-07-08

A categorization overhaul: X Articles capture from every entry point, and the whole Library is now source-first. The data model was YouTube-shaped, so every non-YouTube capture showed its hostname (x.com, reddit.com) as the "who" and there was no way to filter by platform, source type, or author.

### Added

- **Filter your Library by platform, source type, and author.** The filter row now leads with Platform (YouTube / X / Reddit / Web), Source type (video / post / article / thread / page), and Author, then Topic. The old "channel" picker that listed `x.com` and `reddit.com` next to real creators is gone. The video-only filters (hook, format, performance, length) only show up when you're looking at YouTube, so the row stays clean for everything else.
- **Every uoink shows where it came from.** Each card carries its platform, source type, and the real author (an X post reads "X · post · Boardy (@boardyai)", not "x.com"). A Reddit thread shows "r/<subreddit>"; a YouTube video shows the channel.
- **New captures from X, Reddit, and the web get readable folders** (`X\boardyai-<id>`, `Reddit\r-python-<id>`) instead of opaque hashes, matching how YouTube captures already land on disk.

### Changed

- **The real author is now stored and searchable for every source.** New `platform` and `author` columns on the yoinks table (migration 0020, additive and idempotent) hold the source network and the real "who". A one-time backfill fills them for existing captures from their sidecars and corrects the old hostname values (`x.com` becomes "Boardy (@boardyai)"), also runnable as `python server.py --backfill-authors`. Topics are now classified for X, Reddit, and web captures too, not only videos.

### Fixed

- **Every way you reach an X Article now captures it, instead of some paths saving "Uoink this page."** The right-click menu used to be a static "Uoink this page (article)" that skipped detection and hit the login-walled page fetch; it now detects an X Article, reads it from your logged-in page, and its label reads "Uoink this article" on an article tab. The popup now recognises an article even when you got there via its announcing post, a t.co link, or a still-loading page (it checks the page itself, not just the address bar), so an actual article never quietly falls back to "Uoink this page." Article detection is now a single shared definition, so the label and the capture can't disagree.
- **A blocked X Article capture tells you what happened and what to do, and stays put.** When X blocks a logged-out link fetch, Uoink now shows a persistent, plain message ("X blocks logged-out link fetches; open the article and click Uoink this article on the page") in the popup and as a sticky notification, instead of a toast that vanishes or a generic "Uoink failed." It never saves an empty or junk uoink. A stale-token error on the page path now refreshes the token and retries so it doesn't dead-end.

## [3.4.1] - 2026-07-07

Two UX fixes from using v3.4.0 on a real install.

### Fixed

- **The extension popup's primary action is always reachable.** The popup content used to scroll as one long page inside Chrome's ~600px cap, so with More options open (or a busy Recent/last-uoink state) the "Uoink this ..." button scrolled off the top and every action needed the awkward popup arrow-scroll. The popup now has a pinned header and a single clean scroll region, with the primary "Uoink this ..." button pinned in view; the secondary panels scroll beneath it.
- **Thumbnails in the Generate flow are legible.** The source picker's video thumbnails were a cramped 58px, and text sources (X posts, articles) showed a dead grey square. Source thumbnails are now larger and clearer, text sources get an honest "no preview" tile, and the writing screenshot picker uses larger, better-framed tiles so you can actually recognise what you're picking.

## [3.4.0] - 2026-07-07

Real X Article capture, plus three fixes from using v3.3.2 on a real install.

### Added

- **Capture X (Twitter) Articles.** Open a long-form X Article and click the extension's **Uoink this article** button: the content script reads the rendered Article from your logged-in page and saves it as a proper uoink (`source_type: x_article`) under your output folder, sidestepping X's login wall the same way the Reddit capture does. A pasted Article link still works as a best-effort web-page fetch and reports honestly when X login-walls the logged-out request.

### Fixed

- **X Articles no longer save junk, and now capture for real.** Pasting an X *Article* link (X's long-form format, `x.com/<handle>/article/...`) used to quietly save X's "JavaScript is not available" login wall as an empty, untitled uoink. Uoink now recognises an X Article, captures it properly via the extension's in-page button, and for a pasted link says plainly when X login-walls the fetch rather than pretending it captured something.
- **Clearer Activity copy when an X link has no video.** An X post with no downloadable video no longer shows a confusing failed "download". Activity now says X returned no capturable video and points you at capturing the post or thread as text (and a long-form Article at the extension's article button).
- **Every button on the uoink screen is reachable.** The action buttons (Open folder, transcript, Re-capture, Re-transcribe, Evidence, Write from this) used to crowd into the top-right corner and get cut off on a scaled-up display. They now sit in a full-width row that wraps cleanly, so all of them are reachable at the standard window size and smaller.

## [3.3.2] - 2026-07-07

Tool fixes from testing v3.3.1 on a real install.

### Fixed

- **Captures now save where you told them to.** X, Reddit, and article captures were writing to the app's own folder instead of your configured output folder, so they landed apart from the rest of your library. All capture paths now use your output folder, matching YouTube.
- **The extension popup tells the truth about X.** It now says it captures the post text and the author's thread (plus the video if there is one), matching what the feature actually does.
- **The popup shows the real version** instead of a stale "v2.1" label.
- Developer setup: the site's config snippet now emits the working MCP command (it previously pointed at a file that doesn't exist), the tool count reads a consistent 64 (14 over stdio) everywhere, and the published MCP card reports the current version.

## [3.3.1] - 2026-07-07

A cleanup pass from a full review of the 3.3.0 work.

### Fixed

- **Auto-uoink no longer skips videos it should keep.** The taste scan used to move the shared "already seen" marker past every video it looked at, including the ones it declined. That quietly did two bad things: it burned your current backlog if you scanned before Uoink had learned your taste, and it made the plain "capture everything" watch skip videos it was supposed to grab. The scan now only advances that marker past videos it actually captured.
- **The dashboard's paste box tells the truth about X.** It now captures X post text and threads (the same path the extension uses) instead of claiming text "isn't supported yet."
- The one-click MCP bundle now stamps the real release version at build time, and CI checks it alongside the other version surfaces.
- Playlist watch commits its progress durably; an X post with a video says so when the queue is full instead of hiding it; the discovery digest no longer lists the same item twice.

## [3.3.0] - 2026-07-07

Capture the whole web, and let your corpus surface what's worth writing about. X is no longer video-only.

### Added

- **Uoink an X post's words, not just its video.** "Uoink this post" now captures the tweet's text and the author's own earlier thread, and queues the video too when the post has one. A text-only post finally saves instead of dead-ending. Uses X's public syndication endpoint (no login, no paid API), so it's the same source path the video capture already used.
- **Taste-aware auto-uoink (opt-in, off by default).** Turn it on and Uoink scores new videos from the playlists you already monitor against your local taste, then captures the strong matches for you, clearly labelled. No crawler, no accounts, no AI spend. It only watches sources you already track, and every auto-saved item is an ordinary uoink you can delete.
- **Discovery digest.** A calm "worth your attention" view that blends resurfaced corpus items with fresh taste-matched captures, each one click from a draft. Private, local, yours.
- **One-click MCP bundle.** A `.mcpb` package so you can add Uoink to Claude Desktop without hand-editing config.

### Changed

- The X text/thread capture that shipped dark is now on by default (`x_text_capture_enabled`). One button does it all; the separate "Save post text + thread" button is gone. Turn the setting off and X posts fall back to video-only capture as before.

### Fixed

- When X rate-limits or walls a post, capture says so plainly (deleted, protected, rate-limited, or blocked) and saves nothing, instead of leaving a broken uoink.

## [3.2.8] - 2026-07-06

Capture from anywhere, and a reason to come back.

### Added

- **Uoink any source from the popup.** The extension popup now reads whatever tab you're on and offers one button that fits it: "Uoink this video" on YouTube, "this thread" on Reddit, "this post" on X, "this podcast" on a feed page, "this page" on an article, "this playlist" on a YouTube playlist. No more "open a YouTube tab" when you're somewhere else.
- **Paste a URL to uoink.** A universal capture box in the dashboard: drop any link, it detects the source and captures it. Unsupported links say so plainly.
- **Corpus Digest.** The For You surface now turns idle, high-value uoinks into action. Each resurfaced item has a "Write from this" button that opens Generate with the source already picked, so a video you saved weeks ago is one click from a draft.
- **Resume where you left off.** A card at the top of the app on launch: continue your last draft, or write from your last saved source.

### Changed

- X video capture works from the popup on its own, no longer tied to the text-capture toggle.
- Blocked article captures now offer a one-click "Allow this site and retry."

### Fixed

- Screenshots and thumbnails render again after a moved corpus folder: the app serves files from wherever your output folder points, so the Library, the writing screenshot picker, and Open Folder all show real images.

## [3.2.7] - 2026-07-05

A hotfix for a broken 3.2.6 installer.

### Fixed

- Fixed a startup crash in 3.2.6 where the installer did not bundle the X-capture module, so the helper failed silently on launch. Added the desktop shortcut the installer promised.

## [3.2.6] - 2026-07-05

Two waves in one release. The first is a top-to-bottom UX overhaul: Generate, the source picker, the Library, and the install page all got rebuilt around what you're actually trying to do. The second is the brand-critical trust pass: the headline agentic path (stdio MCP) now works, your corpus is durable and portable, a moved output folder heals itself instead of silently breaking, and the disclosures and developer docs finally say the true thing.

### Added

- **Reddit capture.** The extension now grabs Reddit threads (old and new layouts) the same way it grabs YouTube and X. The helper maps `reddit.com` to a real platform, and capture buttons show up on comment pages.
- **X text and thread capture.** The extension can pull X posts and threads behind a flag, so a source doesn't have to be a video to become a uoink.
- **In-app hooks explainer.** A short, honest walkthrough of what hooks are and which ones fire, reconciled against the actual hook taxonomy instead of a marketing list.
- **Topics overview.** A topics summary sits above the Library grid so you can see what your corpus is made of before you dig in.
- **Write from this.** Every Library card and Uoink detail view now has a direct "Write from this" call to action, so you go from a source to a draft in 1 click.
- **Get the extension, in app.** The dashboard's Sources and empty Library states now include a path to install the browser extension, instead of assuming you already had it.
- **stdio MCP that actually runs.** The agentic path had never worked on a real install: the bundled Python couldn't import `server`, so Claude Desktop logged 22 crashes and 0 successes. `uoink_mcp.py` now pins its own directory onto the path before importing, `--doctor` gains an `mcp_stdio` check that walks a real handshake, and CI runs it so it can't regress.
- **Corpus export and import.** New `--export-corpus` / `--import-corpus` (and `/corpus/export` + `/corpus/import`) back up and restore the SQLite-only tables with a conservative merge. `--rebuild-index` rebuilds from on-disk sidecars and restores the newest export, so a dead index no longer comes back empty.
- **Stale-path heal.** `--heal-paths` and a boot pass relink corpus rows that point at a moved output folder, matching by path tail and only ever relinking files it actually finds.
- **Third-party notices.** `THIRD-PARTY-NOTICES.md` is generated from the real shipped bundle at build time, and a new Disclaimer and Terms of Use section spells out that Uoink is for personal research and that you're responsible for each platform's terms.

### Changed

- **Generate, rebuilt.** One screen with a single Advanced disclosure instead of a wall of fields. The common path is short; the power options are there when you open for them.
- **Source picker, rebuilt.** Picking what you write from is now a real picker with corpus counts, not a raw input you have to guess at.
- **Install page, rebuilt.** The download button leads the hero, a SmartScreen note sits right under it, sideloading steps are laid out above the fold, and the dead release-zip link is gone. Chrome, Edge, and Brave instructions are unified.
- **Navigation hygiene.** Dead and duplicate nav entries are cleaned up so the sidebar and top nav point only at things that exist.
- **License compliance.** Transcript reliability is rebuilt on faster-whisper (MIT), dropping whisper-timestamped (AGPL) and dtw-python (GPL). ffmpeg is now BtbN's win64-LGPL build instead of the GPL essentials build, so the whole bundle is MIT-clean.
- **Honest health.** `/health`, `/diagnose`, and `--doctor` now surface path-integrity failures instead of reporting green while every content action fails.
- **Honest disclosures.** The dashboard's update check now states plainly that "Check now" queries `api.github.com` and sends no telemetry, and the website's privacy and terms pages distinguish basic site analytics from the local app's zero-telemetry status.
- **Accurate developer docs.** The docs drop the fake `uoink_mcp.exe` / "14 tools" claims, list all 64 tools, and give a working stdio config plus the HTTP transport details (`http://localhost:5179/mcp/v1`, `X-Uoink-Token`, token at `%LOCALAPPDATA%\Uoink\token.txt`).
- **First-run polish.** The installer shows the migration note before Ready instead of after Install, and the splash is brand-correct with offline-safe fonts.

### Fixed

- **DNS-rebinding hardening.** A Host-header allowlist is now the first check on every request, so a rebinding attacker's Host is rejected before the token or body is ever read. The bound port is validated too, and `/token` can pin the extension ID once the store listing is live.
- **Durability.** Four writes that never committed (engagement logging, facets, tags, and taste anchors) now commit for real, proven by independent readers that only see committed data, the way a process would after a crash.
- **Stale output folder.** Moving your output folder used to leave every row pointing at a dead root while health stayed green. On one real index that was 31 of 31 dead; the heal pass relinked all 31.

## [3.2.5] - 2026-07-04

This one's about trust. Every surface that used to fake it (silent saves, phantom retries, "0 uoinks" on a failed request) now does the real thing or says plainly that it can't.

### Added

- **Real draft saving.** New `POST /writing/draft` and `GET /writing/draft/<id>` endpoints (migration 0018). Writing Save now stores your draft and a reload gets it back. Before this, Save quietly did nothing.
- **Captions-only retry for long videos.** When a long source keeps failing, "Retry, captions only" runs a lite pass: transcript kept, screenshots capped at roughly 1 per 5 minutes, comments skipped.
- **Smart Generate inputs.** Topic and channel pickers with corpus counts, hook chips, target-length presets with units, CTA and style-anchor pickers. They pull from your actual corpus instead of asking for raw values.
- **`/resurface` and `/taste/anchors` routes.** The dashboard's For You tab and the extension popup/setup called endpoints the helper never served (silent 404 on every load). The helper now serves `GET /resurface`, `/resurface/today`, and `/taste/anchors`.
- **Source-first recovery actions.** Detail and Evidence expose Open folder, Open transcript file, Re-capture, Re-transcribe, and Run claim scan where they help, so dead-end empty states have a way out.
- **Newsletter output mode**, and BYO thread mode now prompts as an actual thread instead of a single tweet.

### Changed

- **Library overhaul.** Fits inside the shipped 1280x800 window with per-tab scroll. No matches, empty corpus, and "Library temporarily unavailable" render as 3 distinct states (a request failure never shows "0 uoinks"). Filters populate from corpus-wide facets, impossible date ranges are rejected, and enum labels read like words (`screen_recording` shows as "Screen recording").
- **Copy overhaul, dashboard + extension.** Contractions across ~45 toasts, machine-voiced errors rewritten plain, jargon tucked behind advanced disclosures, and 50 mojibake strings in the extension popup (double-encoded dashes, dots, check marks) repaired.
- **Accessibility pass.** Keyboard activation on card controls, modal focus traps with Esc to close, real labels on placeholder-only inputs, labeled sidebar count badges, source-card semantics.
- **Stop Uoink asks first.** Stopping the helper now takes a confirmation and shows explicit stopped-state copy. The one-click kill is gone.
- **Settings polish.** Output folder picker instead of a raw path box, topic delete with undo, plain-language model and key status.
- **Chrome Web Store listing rebranded.** Listing copy and promo tiles redone for Uoink's multi-source framing.

### Fixed

- **Picker attribution.** A no-match source search clears the stale hidden pick and disables Generate until you pick for real, so output can't get attributed to the wrong source.
- **Manual drafts count.** Typing or pasting a draft into Generate enables Save and Copy, matching what the placeholder invites you to do.
- **Honest retry exhaustion.** Jobs that burn their last retry say they gave up instead of showing "Retrying..." forever, and the retry worker stops logging a phantom "retry at ..." after the final attempt.
- **Activity dedupe.** Failed single-video jobs coalesce by source URL, so one failure doesn't render as 2 rows with competing states.
- **Workspace validation.** Generate no longer silently POSTs a workspace right after source pick; blank forms are rejected before anything is written.
- **Draft endpoints return 404** for ids beyond SQLite's rowid range (they used to crash with a 500).
- **Facets with zero tagged sources** render a labeled empty state instead of an "all"-only dropdown that looks broken.
- **No-op controls removed.** Blank-draft Copy is disabled, the style-anchor `Keep` dead button is gone, and the fake window chrome (inert traffic-light dots) is off the dashboard.

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
