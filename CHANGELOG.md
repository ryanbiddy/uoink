# Changelog

All notable changes to Uoink are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project follows [semantic versioning](https://semver.org/spec/v2.0.0.html).

> Releases through 2.0.0 shipped under the product's original name, **Yoink**.
> Those historical entries are left unchanged. The product was renamed to
> **Uoink** in 2.1.0; see below.

## [Unreleased]

## [3.12.0] - 2026-10-30

### Added

- A Raycast extension in `integrations/raycast` for macOS and Windows.
  Search Library copies a Markdown citation that links to the timestamp,
  Uoink This URL saves the copied link (or the active browser tab on macOS),
  Recent Saves lists the last 20 items, and Save Note saves text. With a
  Raycast plan that includes AI, Raycast AI gets `@uoink` tools for search,
  item excerpts, recent captures and confirmed saves, and AI Chat can mention
  a saved item. The extension runs the installed `uoink` CLI with argument
  arrays and no shell; on Windows it starts the bundled Python directly
  instead of `uoink.cmd`. It is not in the Raycast Store yet.
- A Flow Launcher plugin (`integrations/flow-launcher`, Windows), an Alfred
  workflow (`integrations/alfred`, macOS) and an Obsidian plugin
  (`integrations/obsidian`, desktop) with the same no-shell CLI approach.
  Flow and Alfred search the library with `uk`, open results at their
  timestamp, copy citations and uoink pasted links; Obsidian inserts
  timestamped citations into notes. None is in its store yet. All four quote
  saved transcript and article text, mark a cut-short quote with "…", and
  cite title or metadata matches as a plain link.
- winget manifests and a Homebrew cask for 3.12.0 in `packaging/`, and a
  submission kit with paste-ready text for each directory and store in
  `docs/submissions/`.
- The agent-kit plugin folder has the README and license that the Claude
  plugin directory requires.
- Every download ships the Whisper transcription model, so a fresh install
  transcribes videos that have no captions with no download step. The
  Windows installer and the Mac app carry the default **base** model (OpenAI
  Whisper, MIT, in SYSTRAN's faster-whisper conversion), pinned to one
  Hugging Face revision and SHA-256 checked when the installer is built.
  The Windows installer grows by about 129 MB. A model you downloaded
  yourself still takes precedence, and other sizes still download only when
  you ask. Podcast transcription uses the same copy.
- Settings > App > **Appearance**: Match Windows (Match system on a Mac),
  Light or Dark. The helper keeps the choice, so the Uoink window and a
  browser tab agree, and the page opens in the chosen theme with no flash.
- The needs-attention badge names the problem (`No transcript`,
  `Comments failed`, `2 issues`...). Clicking it opens a drawer that says
  why for each item and offers **Re-uoink**, which refreshes the item in
  place.
- A page the site allowlist turned away gets **Allow <site>** on its Library
  row. One click adds the site and saves the page.

### Changed

- Health checks only count what a source can have. Web pages, X and Reddit
  text posts and images are no longer flagged for a missing transcript,
  screenshots or comments, and comments the uploader turned off no longer
  count as missing. X and Reddit posts with a video keep their transcript
  and screenshot checks. Existing items are corrected on the next Library
  load, with no re-capture.
- A row reads **Done** only when nothing is outstanding. A row with a badge
  reads **Saved**.
- The sidebar's Generate and Sources counts now count saved drafts and
  subscribed sources, and hide at zero. **Clear filters** shows only while a
  filter, search or type is on.
- Videos with nothing to transcribe are not problems. A video with no audio
  reads "no audio", and one where Whisper heard no speech (music, silence)
  reads **Done · no speech found**. The note says "No transcript: captions
  unavailable, and Whisper found no speech" instead of reporting missing
  captions.
- Video posts on X and Reddit say how their transcript came out ("transcript
  by Whisper", "no captions") instead of "post and thread".
- Reading an item, the Back row stays at the top while you scroll. Esc
  closes the reader, and Back (the button, the browser's or the mouse's)
  returns to the same place in the Library.
- Settings no longer offers to download a model that is already on the
  device. Items saved before the model was there say to Re-uoink instead
  of to download it, and when a model really is missing, the
  needs-attention drawer's "Download it in Settings" opens Settings at the
  transcription-model control.
- Settings > "Sites Uoink works on": Enter adds the site, and a pasted link
  saves its host instead of the whole URL, which could never match.
- The dashboard and setup splash are fetched fresh on every load, so a tab
  left open across an upgrade shows the new version instead of the old one
  for up to five minutes.
- From a source checkout, `./uoink status`, `./uoink tools` and the other
  agent subcommands run the agent CLI instead of starting the helper.
  `doctor`, `rebuild-index`, `search` and `clips` still go to the helper.
- The agent skill no longer calls the Mac build private, and says Claude
  Code passed Mac acceptance.

### Fixed

- Screenshots are taken at the times their labels say. Each one used to be
  half an interval late (the `[00:00:00]` shot was about 15 s in), and a
  clip shorter than half the interval got no screenshots at all, so
  re-capturing a short X clip failed with "Screenshot generation produced no
  images".
- Linux: an exited process that hasn't been reaped yet (a zombie) no longer
  counts as running in the liveness checks for subscriptions, the library
  mirror, writer peers and install receipts.
- The one-time usage-sharing card leaves a gap above the content that
  scrolls under it.

### Compatibility and testing

- The MCP server still exposes 91 tools by default and 35 with
  `UOINK_MCP_TOOLSET=core`.
- The Windows installer is about 519 MB (390 MB in 3.11.2) and the Mac DMG
  about 709 MB (580 MB), because both now carry the Whisper base model.
- The IPv6 refusal test skips on machines that cannot bind `[::1]`, and says
  why.

## [3.11.2] - 2026-10-25

### Added

- A Mac build for Apple Silicon (macOS 15 or later), released as a preview.
  `Uoink-3.11.2-macos-arm64.dmg` is signed with a Developer ID, and Apple has
  notarized both the app and the DMG, with tickets stapled. It opens after
  macOS's standard "downloaded from the internet" prompt, with no security
  override. The setup page offers **Download for Mac** and the steps to drag
  Uoink to Applications.
- macOS: opening Uoink.app while Uoink is running shows the dashboard.
  Before, a second open did nothing, and the menu-bar icon (which the
  MacBook notch can hide) was the only way back in.
- macOS: the dashboard and the setup splash open on the display under the
  pointer instead of the main display.
- macOS: the Desktop access prompt says why Uoink asks ("Uoink saves your
  captures in the Uoink folder on your Desktop.").
- Chrome Web Store build. `scripts/build_cws.py` writes an allowlisted store
  zip with no manifest key, mock API or source maps. The helper trusts the
  store item ID from `extension/store-config.json` (exact origin match) next
  to the pinned developer ID. Setup keeps the unpacked-extension flow until
  the listing is approved; `scripts/sync_store_links.py` then switches the
  splash, setup page and README to "Add to Chrome".

### Changed

- Extension onboarding knows which OS it's on. On a Mac, the dashboard's
  "Get the extension" card shows `~/Library/Application Support/Uoink/extension`
  (then the real path once the helper answers), and **Open extension folder**
  reveals it in Finder and copies the path. Chrome's **Load unpacked** picker
  hides `~/Library`, so the card explains pressing ⌘⇧G and pasting. The setup
  page, dashboard and extension popup no longer say Windows-only things on a
  Mac; when Uoink isn't running, the popup says to open it from Applications
  or Spotlight.
- The extension no longer requests the unused youtu.be, mobile.twitter.com
  and localhost:5179 host permissions.
- macOS: desktop alerts are kept for capture results and helper failures
  only. The "Uoink is ready" banner is gone, because a launch already opens a
  window. A notifier app of Uoink's own is planned for 3.12; until then macOS
  credits these alerts to Script Editor.
- macOS: dashboard copy says "this Mac" instead of "this PC".
- Setup splash: Chrome is listed first and Comet is detected. When a browser
  won't open its extensions page from the splash (Comet ignores it), Uoink
  copies the address and the steps say to paste it in the address bar.

### Fixed

- YouTube captures save their transcript again. Uoink asked for every
  caption track starting with "en", which includes YouTube's
  auto-translated tracks (en-de, en-ja...). YouTube rate-limits those
  separately, and one refusal there stopped the whole caption download, so
  captures said "YouTube refused captions". Uoink now asks for en, en-US,
  en-GB and en-orig by name, and prefers uploaded English captions over
  auto-captions.
- A failed index write no longer wedges the helper. A write that raised
  (for example a duplicate folder name during the startup backfill) left its
  SQLite transaction open, and every later save on that helper failed until a
  restart. Upserts, deletes and the other 22 older write paths now roll back
  their own failures. `write_transaction()` and `read_snapshot()` still refuse
  to start over an open transaction instead of committing or discarding it.
- Re-capturing an item saved by an older version refreshes it in place
  instead of creating a second folder. Duplicate folder names no longer fail
  the startup backfill; each is skipped with one warning and `uoink doctor`
  lists them. The backfill stays incremental: known items are not re-indexed
  on each start.
- An MCP stdio request over 64 KiB (for example a long `uoink_note`) is
  refused with its own request ID instead of `id: null`, so the client no
  longer waits forever.
- Captions longer than the video are cut at the video's end, and YouTube's
  `\h` hard spaces and `[\h__\h]` censor markers are cleaned out of
  transcripts.
- The supervisor writes the helper's output to `helper-output.log` as it
  arrives. Before, short output sat in the pipe until 4 KiB had built up or
  the helper exited.
- Setup splash: no white corners, the bottom button is no longer clipped,
  and the footnote no longer overlaps a button.
- macOS: if the menu-bar icon can't be loaded, the menu bar shows "Uoink" as
  text instead of failing to start.

### Compatibility and testing

- The MCP server still exposes 91 tools by default and 35 with
  `UOINK_MCP_TOOLSET=core`.
- macOS qualification signs with Developer ID, notarizes and staples the app
  and DMG in CI, then launches the quarantined DMG without an override and
  collects an installed receipt from the final signed bytes. It also checks
  the real LaunchAgent contract (`--helper --startup`,
  `KeepAlive.SuccessfulExit=false`, `ThrottleInterval` 30) and no longer
  depends on reverse DNS on CI runners.

## [3.11.1] - 2026-10-25

### Added

- Web articles are extracted by a built-in port of Mozilla Readability's
  main-content algorithm (Apache-2.0). Saved Markdown keeps headings, lists,
  quotes, code, simple tables and links, and reads the title, author, date and
  site from JSON-LD, OpenGraph and meta tags. Crawl4AI, where installed, and
  the old regex path remain fallbacks, and the engine used is recorded.
- Saved X posts keep quote posts, media descriptors (photo alt text, video and
  GIF variants, posters), expanded links and real counts. Every capture says
  whether its text is complete, truncated or unknown, and which provider
  supplied it. Missing thread parents and tombstoned quotes are disclosed.
- A per-user supervisor restarts the helper after a crash (3 restarts per 10
  minutes, with backoff), honors Quit until the next login or a manual start,
  and reports crash loops. On Windows it is a per-user Scheduled Task that
  replaces the Run entry. A port conflict stops after one launch.

### Changed

- Tool, server, `.mcpb`, extension and agent-kit descriptions were rewritten
  for search and for agents. All 91 tool definitions were rewritten against
  Glama's tool-definition rubric, and a Linux container build was added for
  directory listings.

### Fixed

- Caption-less X videos now get a local Whisper transcript. The fallback was
  handed the screenshot download, which on X is a video-only stream, so every
  attempt failed with "tuple index out of range" and the note said "No
  captions available." Uoink now checks the captured media for audio and,
  when there is none, downloads the source audio once (cut to the same ranges
  for long videos). When no audio exists, the note says so and the library
  labels it "no audio". Model loading stays cache-only.
- Paywalls, login walls and empty JavaScript pages are labeled failed
  captures instead of saved as successful articles.
- 22 helper write paths never committed. Saving claims, style anchors,
  writing pieces and drafts, workspaces, channels, allowed sites, scripts,
  tags and playlist poll failures returned success, kept the SQLite write
  lock, and lost the row when the process exited. Meanwhile other processes
  got "database is locked", and later transactions on the helper failed.
  Every one now goes through `Index.write_transaction()`, which commits, or
  rolls back on error. Return values and errors are unchanged.
- Opening the bare helper address (`http://127.0.0.1:5179/`) in a browser
  redirects to `/dashboard` instead of returning "missing or invalid token".
  The Host check still runs first.

### Compatibility and testing

- The MCP server still exposes 91 tools by default and 35 with
  `UOINK_MCP_TOOLSET=core`. This is a Windows release; the Mac preview is
  not part of 3.11.1.

## [3.11.0] - 2026-10-22

### Added

- Forgiving keyword search is the default. Search drops common English words,
  matches any remaining word and ranks results in groups: an exact title first
  (ignoring case and punctuation), then results with every useful word, then
  partial matches, with BM25 ordering inside each group. `match: "strict"`
  keeps the previous every-word search; the dashboard calls it **Exact words**.
  This covers `search_library`, `search_uoinks`, `search_clips`,
  `find_mentions`, `/memory/search`, `/api/corpus/v1/search`, `uoink search`
  and the dashboard, which selects **Best match** order when a query starts.
- Optional local semantic search in Settings > Semantic search. After the user
  accepts the Gemma Terms of Use and Prohibited Use Policy, Uoink downloads
  EmbeddingGemma from Hugging Face once (about 330 MB, pinned and hash
  checked), builds a vector index in the background, keeps it current as
  captures change and works offline after that. Settings has Pause, Resume and
  Remove; Remove deletes the model, its vectors and the acceptance record.
  The model is not bundled in the installer, `.mcpb` or DMG, and a build check
  fails if it is. No MCP tool can accept the terms or start the download.
  The installer includes the EmbeddingGemma notice and both Gemma documents.
- `search_uoinks`, `search_clips` and `search_library` take an optional `mode`:
  `auto` (default; hybrid when the semantic index is ready, keyword
  otherwise), `keyword`, `semantic` or `hybrid` (reciprocal rank fusion, k=60,
  over the top 100 of each). Responses name the mode that ran in
  `search_mode` and give a `fallback_reason` when search fell back to keywords.
- Quotable citations. Search results carry the source ID and, only when the
  passage really contains the match, the passage text with its clip ID and
  start and end seconds or its character span, plus the timestamp where one
  exists. Otherwise `passage_verified` is false and `citation_reason` says
  why. `find_mentions` keeps its stored `timestamp` and `deep_link` and adds
  verified timing in `timestamp_seconds` and `passage`. `/api/corpus/v1/search`
  keeps its exact v1 response unless the caller sends `search_details=true`.
- **Share anonymous usage counts** in Settings > App > Usage sharing, off by
  default, with a one-time dashboard card whose default is **No thanks**. When
  on, the helper sends at most one report a day to `usage.uoink.app`: counts
  of tool calls by tool name, stdio and HTTP calls, AI apps from a fixed list
  (others count as `other`), captures by source and result, and searches, plus
  a random install ID, a report ID, app version, operating system and major
  version, processor type, install type and hours covered. Reports never
  include content, URLs, titles, paths, search text, usernames, IP addresses
  or account details. **See what is sent** shows the next report and the last
  ten sent. Turning sharing off deletes the install ID, counts and sent
  history. Isolated installs and tests never send, and `UOINK_USAGE_SHARING=0`
  set for the helper stops sending. See [usage sharing](docs/usage-sharing.md).
  Release notes before 3.11.0 that say Uoink has no telemetry describe those
  releases.
- `uoink connect` adds 10 clients: Kiro, Copilot CLI, Auggie, Factory Droid,
  Qwen Code, Crush, Antigravity, Chatbox, Dive and Perplexity (Mac). It now
  has 48 recipes. 45 are checked against each client's official documentation,
  with sources and check dates in `docs/integrations-verification-2026-10-21.md`,
  and `uoink connect` prints each recipe's verification status.
- Linux in the client tables. Recipes carry a Linux location where the client
  has one, and the tables in `docs/connect-your-agent.md` and the agent kit
  list Linux. A Linux location without its own Linux doc source is labeled as
  reusing the POSIX spelling. Clients with no Linux build (Claude Desktop,
  Raycast, AnythingLLM, Obsidian) refuse on Linux instead of printing a macOS
  path, and Mac-only recipes refuse on Windows.
- The dashboard detects Continue. It reads Continue's `config.yaml` (and the
  legacy `config.json`) read-only and shows Continue as connected when an MCP
  entry launches this install.

### Changed

- The MCP server moved from the Python SDK 1.28.1 to the official SDK 2.3.0,
  which implements the stateless 2026-07-28 protocol. Stdio serves both eras:
  clients that send a legacy `initialize` (protocol versions 2024-11-05,
  2025-03-26, 2025-06-18 and 2025-11-25) connect as before, and 2026-07-28
  clients can use `server/discover` or an inline first request. HTTP
  `/mcp/v1` keeps its existing contract and is not advertised as 2026-07-28
  HTTP. The SDK move changes no tool names or schemas.
- Installer dependencies: `mcp` 2.3.0, `mcp-types` 2.3.0, `httpx2` 2.16.0,
  `httpcore2` 2.16.0 and `truststore` 0.10.5 join; `httpx`, `httpcore`,
  `httpx-sse`, `pydantic-settings` and `python-dotenv` leave. The locked graph
  has 139 packages, with about 172 KB more wheels.
- Dashboard connection status for Claude Desktop, Cursor and Cline now checks
  whether any MCP entry launches this install, not whether a key named
  `uoink` exists. An entry that points at an old or moved install, or at a dev
  checkout, now shows **Connect**, which rewrites it and keeps a backup. A
  renamed entry that launches this install counts as connected. A bundle
  missing its launcher reads as not connected instead of failing the scan.
- Continue is manual only. Its current config is YAML, so the dashboard's
  Connect returns 409 with instructions and writes nothing;
  `uoink connect continue` prints a standalone
  `.continue/mcpServers/uoink.yaml` entry.
- Third-party notices prefer a package's PEP 639 `License-Expression` over its
  license classifier.
- Library search uses separate read connections with per-request deadlines,
  so up to four library reads run at once (previously two). The two-second
  deadline and rate limit are unchanged. Large forgiving clip searches rank a
  bounded shortlist of sources (`max(32, limit)`) before ranking their clips,
  so clip results are a ranked selection, not an exhaustive listing.

### Fixed

- MCP stdio error replies follow the specification: an unknown method returns
  -32601, malformed JSON returns -32700 with a null id, a request with a null
  id returns -32600, and an accepted cancellation gets no response.

### Compatibility and testing

- The MCP server exposes 91 tools by default and 35 with
  `UOINK_MCP_TOOLSET=core`. No tool is added or removed, and consent gates
  are unchanged.
- Search schema changes are additive optional parameters (`match`, `mode`,
  and `search_details` on corpus v1).
- Upgrading keeps the library and saved captures. Migration 0031 adds a clip
  metadata index, and migration 0032 rebuilds the derived keyword search
  indexes once on first start. On a 3,000-source test library with 180,000
  clips, the rebuild took 2.8 seconds and the index file grew from 154 MB to
  231 MB, 34 MB of it reusable free space. Source, clip and mention data were
  unchanged (hashes compared).
- Frozen 30-query benchmark on a copy of a 693-source library, top 5:
  strict (the previous behavior) 10/30, forgiving keyword 24/30, semantic
  27/30 and hybrid 28/30. All 10 keyword queries were found in every mode.
  p95 latency was 7 ms, 46-52 ms, 106 ms and 333 ms. Exact titles came first
  for 692 of 693 sources; the miss is two captures with the same title. The
  first semantic index build took about 40 minutes for 693 sources on CPU,
  in the background.
- On a synthetic 3,000-source library with 180,000 clips, every measured
  search call stayed within 1.5 times the previous search code's time or
  under 150 ms, and batches of two and four concurrent library searches all
  succeeded.
- Real clients against the SDK 2 server, run from source with an isolated
  profile: Claude Code 2.1.307 listed 91 tools (35 in core mode) and called a
  tool, also with `MCP_PROTOCOL_NEGOTIATION=auto`; Codex 0.153.4 called a tool
  with its default settings and with `CODEX_MCP_PROTOCOL_VERSION=2026-07-28`.
  The installed 3.11.0 build, in an isolated profile: Claude Code 2.1.308
  listed 91 tools and called one; Codex 0.153.4 called two tools.
  Characterization recordings from SDK 1 cover all
  four legacy protocol versions, and 66 adversarial cases pass in both eras.
- Client recipes: 45 of 48 are checked against official docs. The connect
  docs still mark client acceptance as "not yet tested" for every recipe.
- No usage report was sent during verification; tests mock the request.

## [3.10.0] - 2026-10-19

### Added

- The `uoink` command lets agents search saved sources, read evidence, capture
  URLs, save notes, and call registry tools from a shell. For example:
  `uoink search "working memory" --limit 5`, `uoink recent --limit 10`, and
  `uoink note "A useful thought" --title "Research note"`. Local reads work
  without a running helper. Capture and paid tools keep their existing gates.
  The installer adds the command to User PATH by default through the checked
  **Add the uoink command to PATH for AI agents** checkbox. Open a new terminal
  after installation, then run `uoink status`.
- A portable Uoink skill for Claude Code, Codex, pi, Hermes Agent, and OpenClaw
  covers finding evidence, citing sources, and using MCP tools or the CLI.
  `uoink skill path` locates it; `uoink skill install --to <skills-directory>`
  copies the skill and its references into the agent's skills directory.
- The Claude Code plugin marketplace at `ryanbiddy/uoink-agent-kit` is
  published with this release. It bundles the skill and MCP connection for a default install.
- `uoink connect` provides setup recipes for 38 clients and integrations.
  Run `uoink connect --list`, then `uoink connect <client>` for config or
  instructions and where to put them. It does not edit client settings.
  The dashboard has **Add to Cursor** and **Add to VS Code** buttons that open
  the client's review flow.
- [Connect your agent](docs/connect-your-agent.md) documents the CLI, skill
  paths, client recipes, and known limits. [Agent installation](llms-install.md)
  gives Windows download, checksum, silent install, and connection steps.

### Compatibility and testing

- The MCP server exposes 91 tools by default. Consent gates are unchanged.
- No data or settings changes besides the optional PATH entry. No index or
  migration is added; existing libraries and saved captures stay in place.
- Tested on a clean isolated install: Claude Code 2.1.302 (MCP: 91 tools, a note
  saved and listed; skill plus `uoink` command with no MCP: note saved and listed),
  Codex CLI 0.153.4 (MCP: note saved and listed), and the `uoink` command itself
  (`status`, `note`, `recent`, `connect`). The Claude Code plugin loads its skill
  and starts its MCP server; its tool calls were not run end to end because the
  test install is isolated. Gemini CLI and pi were not tested (no sign-in on the
  test machine). Every other recipe is marked "not yet tested".

## [3.9.3] - 2026-10-19

### Added

- Uoink is listed in the official MCP registry as `io.github.ryanbiddy/uoink`.
  Each published release updates the listing through a GitHub Actions job
  (`.github/workflows/mcp-registry.yml`) that first checks `server.json`
  against the tag and the release checksums.

### Fixed

- The three tool schemas with a top-level `oneOf` (`claim_library_work`,
  `apply_reshelving`, `set_source_consent`) are now flattened on the HTTP MCP
  connection too. HTTP MCP clients that pass tool schemas to a model no longer
  drop Uoink's tools because of those schemas. The server still checks the
  exact frozen schema for every call. The MCP server exposes 91 tools by default
  on both transports.
- Activity and Phase 5 measurement reads are faster on large libraries. In
  seven local runs per size, median read time fell from 40.3 to 30.8 ms for
  548 items (23% less time), and from 461.4 to 285.5 ms for 10,000 items
  (38% less time). Responses are byte-identical; the 2-second deadline stays.
- No data or settings changes. No new index or migration. Installing over
  3.9.2 keeps your library and saved captures.

## [3.9.2] - 2026-10-18

### Changed

- The MCP server exposes 91 tools over the standard connection used by Claude
  Desktop (.mcpb), Claude Code and Cursor, up from 35. Every Uoink tool is included.
- `UOINK_MCP_TOOLSET=core` keeps the previous 35-tool set for clients that cap
  tool counts. Full mode keeps those tools first in their original order.
- Consent gates are unchanged.
- Three tools whose input schemas used a top-level `oneOf` (`claim_library_work`,
  `apply_reshelving`, `set_source_consent`) are advertised over stdio as one object
  with the variants' fields, so Claude Code and Claude Desktop load every tool.
  The server still validates the exact schema.

## [3.9.1] - 2026-10-18

The MCP server still exposes 35 tools over stdio.

### Changed

- Writing warnings now use "canned-phrase" wording. Voice DNA remains the
  voice spec's name.

### Fixed

- Fixed the Windows/Ubuntu CI test baseline. Windows-only Library mirror
  and installer-receipt tests skip on other systems, and portable tests
  now pass on both. A few timing-sensitive measurement tests can still
  miss their budget on slow CI runners.
- Linux isolated-install stop recognizes exited processes, including
  unreaped children, instead of reporting their liveness as unknown.
- Made the YouTube pacing test deterministic by checking process event order
  independently of the operating system's clock resolution.

## [3.9.0] - 2026-10-18

### Added

- Settings → Connected services and Sources → Discover: write-only
  ScrapeCreators key controls, the disclosure gate, credit plans, balance
  testing, daily caps and separate agent consent. Each Run and queue click
  obtains a fresh intent; results sort by lift and up to ten picks can be
  queued without loading third-party thumbnails.
  Failed local saves retain paid results and offer a save-only retry.
  Local library or ledger errors also preserve fetched candidates.
  Deleted, unavailable and cancelled captures have distinct states; real
  failed capture attempts remain failed.
- Generate → Research: five playbooks with creator, capture, or topic scopes,
  cited reports, inline citation warnings, draft saving, and Tweet/Thread
  follow-ups. Runs use a connected agent first, then your Anthropic key, or
  prepare a free prompt to copy into Claude. Run stays disabled until the
  request settles; provider and library errors never trigger a paid retry.
  Packet refusals show the server's message, reason, and recovery step.
- Discovery tools on stdio and HTTP: `discover_candidates` plans and spends
  confirmed credits; `queue_discovered` sends up to ten picks through the
  existing capture queue, with intent/agent gates and duplicate protection.
  The MCP server now exposes 35 tools over stdio, with 91 HTTP registry tools
  and nine prompts.
  Token-gated `GET /discovery/runs/<run_id>` reconciles capture state without
  spending or queueing. Picks are due immediately in the retry worker's local
  clock. Local playbooks use the target-filtered 24-file reader and newest
  snapshots, including YouTube channel IDs from saved channel URLs and keyword
  Shorts. Playbook authors remain local display names. Late key errors cannot
  invalidate a replacement key.
  Source, privacy, security and MCP docs describe these flows.
  A newer rerun that failed or was refused before keeping any row does not
  replace an older snapshot or block keyword fallback; partial runs and
  successful empty runs still count as the newest snapshot.
  Creator snapshots take precedence over newer keyword hits. Mixed YouTube
  results report baselines per content group. Failed or cancelled picks can
  be explicitly queued again without duplicating active captures.
  Empty failed receipts now carry a filename marker so repeated failures
  cannot consume the 24-file packet budget or hide keyword fallback. SQLite
  makes active-URL deduplication exclusive across helper and stdio processes;
  both run receipts reconcile to the same pending capture. Argument errors on
  `/tools/discover_candidates`, `/tools/queue_discovered` and
  `/tools/get_playbook_input` return HTTP 400 with the standard error envelope.
  Storage docs now disclose the submitted query, handle or channel_id, run
  identity, accounting, coverage and error envelopes, including failed runs,
  alongside candidates, metrics and queue state. The daily purge removes all
  these run records once older than 90 days. Intent docs clarify that an HTTP
  client holding the helper token can omit Origin and fetch metadata to mint
  an intent; browser checks do not prove a human click. No MCP tool can mint an intent.
- ScrapeCreators discovery adapter with default-off settings, profile-scoped
  keyring storage, five-minute dashboard intents, a 25-credit daily default cap,
  and a UTC credit ledger. Requests use a pinned host, refuse redirects, and
  stop on errors without retrying. Normalized runs retain at most 60 candidates
  and expire after 90 days. The installer stages and includes the adapter.
  Endpoint paths and fields are pinned to the OpenAPI examples fetched October 16,
  including `/v1/youtube/channel-videos` and `/v1/credit-balance` (`creditCount`).
  Run records and filenames identify the requested mode, platform and target.
  TikTok picks use the row's video ID, correcting URLs that point to another post.
  The bounded reader filters by target before its 24-file limit.
- Token-gated `POST /playbooks/run` for explicit research generation with a
  saved Anthropic key, metered per playbook, with citation warnings and refs.
  Reports save through the existing draft route. Privacy and security docs
  describe the library text sent to Anthropic; dashboard controls are pending.
- Shared core transcript chapter limits for prompts, MCP tools and HTTP runs.
  Overflowed metric medians become null so extreme data remains renderable.
- Five local research playbooks on MCP as prompts and a shared
  `get_playbook_input` tool: 9 prompts, 33 stdio tools and 89 HTTP registry
  tools. The tool returns cited packets without model or network calls;
  unexpected adapter failures return a structured `internal_error`. Transcript
  packets cap chapters per capture and count omissions before response trimming.
- Local research packet builders for outlier posts, transcript intelligence,
  comment mining, creator teardowns and repurposing, with deterministic metrics,
  citation checks and bounded reads of saved discovery snapshots. Adapted
  ScrapeCreators documentation carries its MIT attribution and license.
  Mixed-platform reports exclude X from metrics, topic selection keeps search
  relevance order, and author matching accepts Unicode joiners. Unsafe comment
  and clip text is omitted and counted in packet coverage.
  The installer includes the playbook module and the MIT license linked from
  the generated notices.
- Video captures now retain comment and follower counts in their sidecars and
  index metadata. Generic captures also index views, likes and upload dates;
  shaped comments retain yt-dlp IDs and timestamps.
- Existing captures gain missing engagement fields from local sidecars and
  cached metadata in batches of up to 25 rows and 32 MB per tick. The backfill
  updates only index metadata and preserves existing values and source files.

### Changed

- Merged the dashboard and extension re-haul into 3.9. Offline regressions now
  load the live-capture wrapper, supply the setup worker's sender identity,
  exercise the current diagnostic renderer and derived article-button label,
  and read the stdio tool inventory without opening a Windows event-loop socket.
  Phase 3 acceptance fixtures keep their scratch files in the OS temp directory.
- To import a backup with `POST /corpus/import` or CLI `--import-corpus <file>`,
  copy it into the active output folder's `_exports` directory first and supply
  its absolute path. Both reject relative paths and files outside `_exports`.
  Invalid, missing or unreadable imports return HTTP 400 (or CLI JSON with
  `ok: false`) without exposing local paths.
  Local index rebuilds still restore exports from their explicitly selected root.
- Dashboard and extension error details now show `<path>`, `<url>` and `[redacted]`
  placeholders. Spaces and tabs within each line are compacted; line breaks stay
  intact so extension notifications can still show the last tool error.
  Ordinary diagnostics such as "This video requires a GVS PO Token which was not
  provided." remain readable. Redaction happens before the existing detail length
  limits, with input capped at 65,536 characters before regex processing to keep
  oversized tool output from stalling error handling. Timeout details show separate
  `Command:` and `Timeout:` lines. Unquoted paths keep separate placeholders,
  and retry diagnostics keep their trailing text within the existing
  200-character limit.
  Full diagnostics remain in the local `server.log`.
- A failed podcast transcription's job error and episode transcript error, and a
  deferred podcast publish error, now read like `CalledProcessError: exit status 1`
  or `TimeoutExpired: timed out after 30 seconds` for subprocess failures; other
  exceptions keep their sanitized message. For subprocess errors the podcast job's
  `error_detail` still carries the redacted command line (and a failed
  subprocess's redacted output).
- Local, intranet and IP-address sources now fail through these fetch paths;
  blocked thumbnails are omitted. Existing downloaded podcast audio remains
  usable. Podcast downloads and generic yt-dlp extraction make an additional
  checked GET before starting, using the podcast or page fetcher's User-Agent
  on every redirect hop. Hosts that reject it cannot be captured through
  these paths. These fetches connect directly and no longer use system or
  environment proxy settings. `/extract/any` reports admission refusals and preflight failures,
  including response timeouts and HTTP protocol errors, as HTTP 400 errors.
  Fixed YouTube hosts, including YouTube Music, and strict
  X/Twitter, TikTok and Instagram capture retain their existing yt-dlp flow;
  other URLs on those hosts, such as relaxed `/live/status` probes, take the
  checked GET. YouTube keeps its original URL and shared rate limiter without
  an extra GET.
  See [the network policy and its limits](docs/security.md#url-and-identifier-validation).
- Existing unpacked-extension users must reload the extension once after this
  update. If the old ID differs from `bkcapfidedhfcjpmjabeopfbcjcbmdmi`, extension
  storage starts fresh under the new ID: reapply extension preferences as needed;
  the helper token is fetched again. The helper's library and captures stay in
  place. See [the security model](docs/security.md) for additional trusted IDs.
- The setup page's Helper status panel and the dashboard's Settings > Local app
  status line no longer show Anthropic key checks; key status stays in the
  dashboard's own key section. The tray no longer reports Degraded only for an
  invalid key. The setup page's Installation folder row shows the standard
  `%LOCALAPPDATA%\Uoink` location instead of the real path, and its Open folder
  button no longer opens the folder.

### Security

- Restrict `POST /corpus/import` and CLI `--import-corpus` to resolved files inside
  the active output folder's `_exports` directory. Reject relative paths, parent
  traversal and symlinks or junctions that escape that directory before reading a file.
- Sanitize machine error details before returning them or saving them in jobs:
  redact local paths, URL credentials, API keys and labelled credentials.
  A credential's whole value is redacted, including commas, escaped quotes and
  apostrophes inside it, for prefixed flags such as `--video-password`, the
  `--flag=value` form and argument lists such as `'--token', 'value'`.
  Failed and timed-out subprocesses redact whole credential arguments before
  quoting them, including values containing spaces or line breaks.
  Preserve full path redaction for apostrophes, colons and repeated separators,
  including doubled backslashes, while supporting spaces in directory names.
  Quoted paths also redact names such as `James' O'Brien`; unquoted spaced
  directory names can include colons, as in `james' smith:family`.
  Quoted paths redact through the end of their line unless the last closing
  quote follows a filename with an extension and a complete diagnostic phrase
  follows it, such as `wasn't found`. Ambiguous words after an apostrophe are
  removed even without separators or dots, along with later paths on that line.
  This applies to POSIX, Windows drive and UNC paths, including paths cut off
  by the input cap. It can hide the rest of a command or diagnostic line after
  a quoted path. Redaction never crosses a line break.
  Whole URLs become `<url>`; words such as "download/network" are not paths.
  The failure handlers that record these details (extraction, playlists,
  sessions, the retry queue and podcast transcription) write the raw command
  line and tool output only to `server.log` and log fixed or sanitized text to
  the console; podcast failures no longer store raw exception text in the job
  or episode. A podcast transcription or deferred publish error that comes from
  a subprocess is stored and logged to the console as its type and exit status
  (or timeout) only, never its command line. Other helper log lines still go to
  both the console and `server.log`.
- Optional subtitle-fetch and comments-worker failures now send raw exceptions
  and yt-dlp output only to `server.log`. The console shows sanitized summaries;
  comments failures no longer print yt-dlp's last stderr line. Subtitle-refusal
  detection and comments status updates are unchanged.
- Apply the standing-source public-network checks to podcast feed polls,
  stdlib page fetches and thumbnail downloads, and to the redirect chain
  checked before podcast enclosures and generic URLs reach yt-dlp. Reject
  IP literals and non-public DNS answers on the initial URL and every
  redirect hop, including when a saved feed's destination changes. IPv6
  answers that carry a non-public IPv4 (IPv4-mapped, NAT64 or 6to4) and
  hostnames that cannot be IDNA-encoded are refused too. Percent-encoded
  hosts are refused on the initial URL and every redirect, and DNS is checked
  for the exact host name the connection is made for. Each connection then
  dials only the addresses that passed that hop's check and never resolves
  the name again, so DNS rebinding cannot move it; the Host header, SNI and
  certificate checks keep the host name. Requests made inside yt-dlp and the
  Crawl4AI renderer resolve names themselves and are not covered.
- Check the initial page URL and DNS answers before starting Crawl4AI,
  including Writing Studio captures that bypass the site allowlist. This
  check does not cover redirects or subresources inside the browser renderer.
- Pin the extension's Chromium ID to `bkcapfidedhfcjpmjabeopfbcjcbmdmi` with a
  public manifest key. The helper now grants extension token bootstrap and CORS
  only to this ID and IDs explicitly added through `UOINK_EXTENSION_IDS` or
  `settings.extension_ids`. Previously, a nonempty environment variable replaced
  the settings list; now both sources are unioned with the pinned ID.
- Use a bodyless `POST /token` in the extension so Chromium sends its extension
  Origin and the helper checks the pinned or explicitly configured ID.
  Keep the client header, omitted credentials and `no-store` fetch policy.
  Without Origin, `/token` now requires `Sec-Fetch-Site: same-origin` and a
  present, allowed loopback Host. `Sec-Fetch-Site: none` and missing fetch
  metadata receive HTTP 403, closing the extension-worker GET bypass.
  Helper-served dashboard and WebView pages keep their same-origin GET path;
  update/reload the extension with the helper so token refresh uses POST.
  Older WKWebView clients that send neither header remain unable to bootstrap;
  open the dashboard in a browser that sends same-origin fetch metadata.
- Drop extension runtime messages whose sender ID differs from Uoink's own ID.
- Public `/diagnose` responses no longer include local paths, raw tool output
  or credential-store errors. Saved-key flags are omitted except for
  `anthropic_key_valid`: clients passing the existing splash metadata check receive
  it without a token, because the first-run splash needs it. The field is `true`
  for a saved key not marked invalid, `false` whenever `anthropic_key_invalid`
  is set, even if a 401 cleared the saved key, and absent only when no key is
  saved and the invalid flag is off.
  This diagnostic-only check requires no Origin header, `Sec-Fetch-Site:
  same-origin` or `none`, and a present loopback Host allowed on the helper's
  port. It does not authorize token bootstrap. `/health` and `/ping`
  carry none of these details; the console doctor keeps the full detail.
  The dashboard and splash cannot be framed by other pages
  (`frame-ancestors 'none'`, `X-Frame-Options: DENY`).
- In-page Uoink buttons on YouTube, Reddit and X articles ignore scripted clicks,
  so other extensions, userscripts or page scripts cannot start a capture.
  YouTube in-page copy goes only through the extension's offscreen document
  (no page clipboard call, no DOM textarea); a failed copy shows "Copy blocked"
  with a Try again notification. Content-script `openTab` requests open only
  Uoink pages, claude.ai, chatgpt.com and the local dashboard.
- Check dashboard external links by kind: remote/server URLs require HTTPS
  on `uoink.app` or its subdomains; fixed GitHub, Claude, X intent, and
  YouTube actions use an exact allowlist; captured source links require
  HTTP(S) and reject IP literals, local hosts, credentials, and non-default
  ports. Keep the exact local Startup URL working. Route Open YouTube
  through this check without a helper-side browser open. Block malformed
  links and keep blocked-link messages visible after copying Markdown.
- Document that the dashboard makes no features-manifest request. Add
  regression checks for the removed loader and catalogue, dashboard startup,
  and the URL allowlist in both browser and native-shell paths.

### Fixed

- Recover a corrupt library index by preserving the damaged database and
  sidecars before rebuilding from saved captures. Other storage errors stop
  recovery without deleting files.
- Give video capture folders a source-specific suffix and verify ownership
  before reusing a folder, so matching titles cannot overwrite another capture.
- Keep live-stream captures waiting for the recording by default and honor cancellation
  while waiting or running.
- Rotate `server.log` at 5 MB and keep three backups.
- Handle YouTube caption HTTP 429 refusals separately from video rate limits,
  allowing local transcription fallback with a visible caption-refusal note.

## [3.8.1] - Not released (these changes ship in 3.9.0)

### Added

- Titles and explicit read-only, destructive, idempotent and open-world hints
  for all 32 stdio tools, with matching HTTP metadata and a documented
  per-tool audit. The real stdio handshake test verifies the advertised hints.
- The privacy-policy link in the MCPB manifest and a README Privacy section
  covering local storage, source fetches, feed polling, FxTwitter and optional
  Anthropic calls.

### Fixed

- Updated bundled yt-dlp from 2026.07.04 to 2026.08.19.
- On a fresh install the dashboard's Library activity panel collapses to one
  line ("Library activity appears here after your first few captures.")
  instead of a wall of "Unavailable" tiles; with history it is unchanged.
- The `.mcpb` packer writes the bundled manifest without a UTF-8 BOM. Windows
  PowerShell 5.1 added one, and the official `mcpb validate` rejected the
  bundle as invalid JSON (the 3.8.0 bundle is affected).
- Windows-only process-authority tests are skipped on other platforms before
  they can change `os.name` and break pytest's path handling.
- Model-readiness fixtures resolve temporary paths, including Windows runner
  paths using `RUNNER~1`, before testing cache containment.
- Source version fields advance to 3.8.1; the setup page and install instructions
  point to the published 3.8.0 installer.

## [3.8.0] - 2026-09-15

### Added

- **Living Library media depth (Phase 6, contract `phase6-v1`).**
  The MCP server now exposes 32 tools over stdio (31 → 32: the read-only
  `export_cited_range`, which quotes stored cues with speaker labels,
  provenance, chapters and revision pins after validating every original
  artifact by bytes); the HTTP/OpenAPI registry grows to 88. Publication is
  fenced by a per-item ownership ledger, commits one coherent snapshot with
  Phase 2 invalidation, prunes obsolete owned `.media-inputs` artifacts after
  settlement, and podcast items record `seek_kind: "none"` until a player
  path exists.
- **Living Library reach, activity and standing capture (Phases 3 to 5).** The
  stdio surface grew from 25 to 31 at this point (`search_library`,
  `get_library_item`, `read_library_resource`, `get_library_activity`, and the
  client-run brief pair `get_library_brief_input` / `publish_library_brief`,
  the latter a local write under `reach/briefs`), five `uoink://library/v1/`
  resource templates and four prompts; the HTTP/OpenAPI registry grows to 87
  with the four source-subscription tools and the same additions.
  Contracts `phase3-v1`, `phase4-v1` and `phase5-v1` under `docs/library/`.
- **`search_clips` and `get_evidence_card` on stdio.** The two Phase 1 clip
  tools join the curated stdio MCP surface (23 → 25 tools); they call the
  same handlers as the HTTP/OpenAPI registry and return the same shapes.
- **Real model-usage meter.** Every Anthropic response's `usage` block is
  now accumulated per feature, model, and month into the local index
  (`usage.anthropic.<feature>.<model>.<YYYY-MM>`); `GET /settings/pricing`
  gains an `actual` block beside the estimate (D-17 "metered").
- **Scheduler heartbeat.** `/health` and `uoink doctor` gain a `heartbeat`
  block that separates tick completion, last successful poll, last ingest
  completion, and freshness. A failed feed poll no longer advances the
  success timestamp; a stale scheduler fails `doctor`.

### Changed

- **Captures notify instead of opening Explorer.** Finishing a uoink (and
  closing a session) now shows a branded toast with the title and destination
  folder instead of popping a File Explorer window per capture — batch grabs
  no longer bury the desktop in open folders. Opening the folder stays one
  click away via the tray menu, the Recent list, and the dashboard.

- **Entity extraction is now opt-in (D-17).** The background entity
  extraction call gets a named `entity_extraction_enabled` setting, default
  off, beside Comment Intelligence and Hook Type. A saved Anthropic key alone
  no longer starts it; turn it on under Settings → Entity extraction.
  Existing installs start with it off.

### Security

- **Recall hook hardening (SEC-02).** `scripts/recall_hook.py` now wraps
  library text in an explicit untrusted-data boundary with a
  data-not-instructions preface, strips control characters, neutralises
  fence-breaking markup, bounds its output, opens the index read-only with a
  1 s timeout under a 1.5 s wall-clock budget, de-duplicates hits per
  session, honours `UOINK_RECALL_DISABLED=1`, and never prints file paths.


Podcast subscriptions can now keep themselves current and publish selected
episodes into the local corpus. The helper also gained controls for keeping
background work quiet without losing its history.

### Added

- **Podcast episodes can enter the shared corpus.** After an on-demand local
  transcription completes, `episode_to_corpus` writes deterministic Markdown
  and a sidecar, indexes the transcript for search, adds source-aware timestamp
  citations, and links the episode to its stable `episode_<hash>` corpus ID.
- **Podcast transcription now runs as durable background work.** One local
  worker processes jobs sequentially at below-normal priority on Windows;
  `get_job_status` reports progress, and interrupted jobs queue again when the
  helper restarts. Model downloads still require explicit consent.
- **Podcast feeds update automatically.** A lightweight scheduler checks due
  RSS and Atom subscriptions for new episode metadata. Audio stays off by
  default; each feed has a separate Auto-ingest switch for downloading,
  transcribing, and publishing one new episode at a time.
- **Desktop notifications can be silenced.** A Local app setting disables
  balloons without discarding the event from Activity. Uoink also suppresses
  notifications while a foreground window covers its monitor, including
  borderless and exclusive-fullscreen apps.

### Changed

- **The stdio MCP surface now has 23 tools.** Podcast feed, episode, WhisperX,
  transcription-job, and corpus-publishing operations join the curated stdio
  surface. The full HTTP/OpenAPI registry now has 65 tools.
- **Citations are source-aware.** Podcast citations use the retained episode
  page URL with `#t=<seconds>` instead of inventing YouTube watch URLs. Legacy
  YouTube citation fields remain available for compatibility.
- **Podcast state survives helper restarts.** Feed polling, downloads,
  transcription progress, and corpus links are committed as state changes
  happen. Interrupted transcription jobs return to the queue, and completed
  transcripts are reused instead of running again.
- **Background captures stay in the background.** Successful unattended work
  remains available from the dashboard and tray menu instead of opening File
  Explorer.

### Fixed

- **Interrupted podcast publishing can be repaired without retranscription.**
  Startup recovery finishes pending corpus publication, `--doctor` reports
  incomplete episode links, and `--reconcile-podcast-corpus` repairs them
  through the deterministic bridge.

## [3.7.0] - 2026-07-24

A hardening and polish release. The Library and Sources surfaces got quieter and
easier to scan, video extraction picked up current site fixes, and a focused
security pass tightened every place Uoink accepts a URL or hands one to another
product in the suite.

### Changed

- **Refreshed video extraction.** The bundled yt-dlp moved from 2026.03.17 to 2026.07.04, picking up current Instagram and YouTube extractor fixes.
- **Quieter Library health.** Healthy cards no longer carry five status dots. A card now shows a labeled "Still working" or "Needs attention" exception only when extraction has unfinished or missing sections.
- **Capture-ready Sources first.** The Sources page now leads with source types Uoink can save today. Planned integrations stay available as a collapsed reference list instead of receiving equal card weight.
- **One clear detail action.** A saved uoink now keeps "Write from this" primary and moves folder, transcript, retry, transcription, and evidence controls into a More actions menu.
- **Reading stays primary on Library cards.** "Write from this" remains available as a compact secondary action instead of filling the card width.
- **A shorter Library filter row.** Search, source, author, topic, and sort stay visible. Video-analysis and date controls now sit behind Filters, and every applied filter appears as a removable chip.
- **The stdio MCP surface is exactly 14 canonical tools.** The six deprecated
  `yoink_*` aliases reached the removal point announced for Uoink v3 and are
  no longer listed or accepted. Clients must use the corresponding `uoink_*`
  names.

### Fixed

- **OpenAPI calls now enforce their published input schemas.** Missing required
  fields, unknown fields, wrong types, and out-of-range values return HTTP 400
  before a tool runs. Human-readable errors now say "uoink"; the legacy
  response keys `yoinks` and `yoinked_at` remain unchanged for compatibility.
- **Engagement from Writer and Zing now ages correctly.** Their RFC 3339 UTC
  timestamps follow the same 30-day half-life as Uoink's native engagement
  events instead of remaining at full weight forever.
- **Cross-product source links now enforce the suite contract.** Corpus and
  kept-media responses reject file URLs, filesystem paths, and non-HTTP
  schemes instead of passing them to Writer or Zing.
- **Capture URLs are checked against their real authority.** Generic page,
  article, and podcast-feed captures now reject malformed or ambiguous URL
  authorities instead of trusting the string they were handed, closing a class
  of requests that could point a capture somewhere other than where it looked.
- **Peer UI paths must be same-origin.** Writer UI paths offered by a peer are
  rejected when they cross origin, so a misconfigured or hostile peer cannot
  steer Uoink's UI at another host.
- **MCP slug handling no longer accepts traversal.** Corpus slugs that try to
  escape their directory are refused at the boundary.
- **The health surface stops over-sharing.** Public health output and the docs
  that describe it now agree, and the response no longer discloses more about
  the local environment than the endpoint is meant to expose.
- **MCP clients can see what they're talking to.** The stdio server now reports
  the Uoink version in its `initialize` response.
- **Setup points at the published installer.** The extension's setup page
  resolves the installer version that actually exists publicly, separated from
  the in-repo source version, so it can never link at a draft or missing asset.

### Documentation

- **macOS status is stated honestly.** The fictional macOS install guide and
  the imaginary macOS security posture are gone. `mac-install.md` now records
  the real status: there is no working macOS build or `.dmg`, and
  `MAC-BUILD-PLAN.md` records the verified gaps and remaining work.

## [3.6.0] - 2026-07-08

Three new kinds of things you can save, all first-class uoinks in the same corpus: your own notes, short videos (TikTok / Reels / Shorts), and images. The first steps of the context-layer vision, so more of what you want to remember lives in one place your AI can read.

### Added

- **Jot a note.** A new "Jot a note" compose box on the Sources tab (title optional, markdown body, Ctrl/Cmd+Enter to save) writes a note straight into your corpus as a first-class uoink: source type "note", author "You", with a classified topic. It shows up in your Library right away and filters by platform / source type = Note, like anything else. Notes are queryable by your AI over MCP and by you via search, with no special-casing. Behind it: `POST /notes` (token-gated) and a standalone `notes.py` module, persisting under your output root at `Notes/<slug>/`. First step of the context-layer vision (musings you write to yourself).
- **Save short videos from TikTok, Instagram Reels, and YouTube Shorts.** Paste a TikTok (including `vm.`/`vt.` short links), an Instagram Reel, or a YouTube Short, or use the extension, and it captures as a first-class uoink: source type "short video" on platform TikTok / Instagram / YouTube, the creator as author, video plus thumbnail plus caption and transcript when available, with a classified topic. It filters by platform and source type like everything else, and when a platform blocks the fetch, nothing half-saves. Reuses the same yt-dlp pipeline as YouTube. Second step of the context-layer vision.
- **Save an image.** A new "Save an image" surface on the Sources tab lets you drop, paste, or pick a meme, screenshot, or diagram. It lands in your corpus as a first-class uoink: source type "image", author "You", with a classified topic and a real preview on its Library card. It filters by platform / source type = Image and is searchable by its caption, filename, and source. Your AI reads the image itself when you ask about it: `get_uoink_corpus` hands a vision-capable MCP client the image path and a `/file` URL. Everything stays local, so there is no cloud vision and no cloud OCR (text-inside-image OCR is deferred until a local path ships). Behind it: `POST /images` (token-gated, raw bytes) and a standalone `images.py` module, persisting under your output root at `Images/<slug>/`. Third step of the context-layer vision.

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

- **macOS packaging remains planned, not shipped.** Sprint 19.5 Stage 2 added
  scaffolding only; no `.dmg` pipeline or macOS artifact shipped in this
  release.
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

- **macOS Stage 1 portability prep only.** Helper code gained cross-platform
  path resolution, but Stage 2 remained planned; no `.dmg` pipeline or macOS
  artifact shipped.
- **/diagnose adds `platform` field** — UIs can render platform-appropriate hints and status checks.
- **Platform-aware extension setup page** — install instructions dynamically adjust based on `chrome.runtime.getPlatformInfo` to show Windows- or macOS-specific commands and files.
- **Entity Extraction disclosures (store listing + README).** Added clear disclosures detailing opt-in Entity Extraction calling the Anthropic API via user-provided API key stored securely in Credential Manager. Touched `docs/store-listing.md` and `README.md`.

- **Rate-limit queue + retry (C4).** YouTube rate limits no longer cause terminal failures. Single-video yoinks queue automatically in a SQLite queue and retry with exponential backoff (60s, scaling up to a 15-minute cap, up to 3 attempts). A popup banner displays active queue counts and offers manual cancel or retry-now actions.
- **Queue management API.** Token-gated endpoints `/queue/status`, `/queue/cancel`, and `/queue/retry-now` power the queue UI.
- **Helper failure diagnosis (C3).** A new public `/diagnose` API endpoint plus a "Helper status" panel in `setup.html` that runs checks (Anthropic key, FFmpeg, yt-dlp, and output path) with context-specific recovery buttons for each failure mode.
- **`LOCALAPPDATA` output fallback.** The helper automatically falls back to writing outputs to `%LOCALAPPDATA%\Yoink\output` if `DESKTOP_ROOT` is read-only or unwritable.
- **`pending_yoinks` schema (migration 0005).** Adds a new table in `index.db` to track rate-limited yoinks, attempts, and errors.

- **MCP server** with 32 tools. The current curated surface includes the original video/library tools plus clip search, evidence cards, library search, activity, briefs, cited-range export, podcast feed, episode, local transcription, and corpus-publishing operations. Stdio transport is officially tested with Claude Desktop and Cursor. Local HTTP JSON-RPC transport is available and marked experimental.
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
