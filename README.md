# Uoink
*The missing layer between YouTube and your AI.*

Uoink any YouTube video into Claude, ChatGPT, or your AI agent — full transcript,
screenshots, comments, and metadata in one structured corpus. Works as a Chrome
extension (one click) or as a local MCP server your agent can call directly.

> The magnet logo was always a U. We just renamed the product to match.
> New home: **uoink.video**

![Uoink — the rust U button under a YouTube video](assets/readme-hero-v3.1.png)

## Why Uoink

You see a video that's clearly working. You want to know why. So you paste the
YouTube link into Claude and hope it can "watch" it. It can't. It hallucinates.
You give up and watch the whole thing on 2x while taking notes by hand.

Uoink fixes that. Click the button under any YouTube video and you get the full
transcript, timestamped screenshots, top comments, channel context, and video
metadata — automatically copied to your clipboard, ready for Claude, ChatGPT, or
your notes app of choice. Or, in v2, tell your AI agent "uoink that video and
decode the hook" and it does both — no clipboard step.

## What's new in v2.1

- **Renamed Yoink → Uoink.** The magnet logo is the U. New domain: uoink.video.
- **Your install moves itself.** Existing v2.0 data, settings, and saved API key
  migrate automatically from `\Yoink\` to `\Uoink\` on first launch — nothing lost.
- **MCP tools renamed** (`yoink_*` → `uoink_*`); the old names keep working
  through v2.5.
- **Mac universal build** (Apple Silicon + Intel).

## What's new in v2

v2 ships three adoption paths:

- **Chrome extension** (the creator path): one-click uoinks, plus Playlist Mode,
  Hook Type classification, Comment Intelligence (AI-powered, BYO key), and Smart
  Screenshot Picker (local).
- **MCP server** (the agent path): 14 tools your AI can call directly. Officially
  tested with Claude Desktop and Cursor; works with most MCP-compatible clients.
- **Operator Skill**: drop-in `SKILL.md` that turns Claude / OpenClaw / Hermes /
  Cursor / etc into a YouTube research analyst. Works across 8+ clients via the
  agentskills.io open standard.

AI-powered features are opt-in and BYO Anthropic API key (stored securely in
Windows Credential Manager). The core extraction flow remains fully local —
nothing leaves your machine except the YouTube fetch.

## Uoink Operator Skill

Uoink v2 bundles a portable Skill at `skills/uoink/SKILL.md` and installs it to `%LOCALAPPDATA%\Uoink\skills\uoink\`. It gives MCP-capable agents the operating frame for Uoink corpora: timestamp citation discipline, decode-don't-dunk analysis, hook-autopsy tweet mode, and the Uoink Hook Type taxonomy. Open the [setup page's Skill section](extension/setup.html#skill-settings) for client install commands and a copyable fallback system prompt.

## Features

**Core extraction (v1, no API key needed)**
- One-click "Uoink" button under every YouTube video
- Right-click any thumbnail to uoink without opening the video
- Full timestamped transcript with chapter awareness
- Timestamped screenshots throughout the video, with 4 embedded in the clipboard by default to keep long videos pasteable
- Top 50 comments with author and like count
- Full video metadata (views, likes, tags, description, upload date)
- Thumbnail image and channel context (subscriber count, recent videos)
- Auto topic-classification into folders on disk
- Built-in prompt library (11 starter prompts) for fast follow-up analysis
- Two destination buttons: Send to Claude, Send to ChatGPT

**Multi-video (v2)**
- **Playlist Mode** — paste any YouTube playlist URL, uoink up to 10 videos. Async with live progress, cancel mid-flight, partial-failure tolerance. Combined corpus to clipboard, per-video files on disk.

**AI-powered analysis (v2, BYO Anthropic key)**
- **Comment Intelligence** — clusters comment themes, extracts mentioned products/tools, flags notable disagreements. Three structured sections appended per video.
- **Hook Type classification** — classifies each video's opening style across 9 hook categories (curiosity gap, question, contrarian, story open, promise/list, demo, authority, stakes, other) with brief explanation.
- **Entity Extraction** — pulls entities from each video's transcript into a local queryable graph. Agents call `find_mentions(entity)` to find every video that mentioned a specific person, tool, product, or topic across the user's library.

**Local transcript reliability (v2.5)**
- **Transcript Reliability** — optional local Whisper check that flags low-confidence transcript spans, especially around proper nouns, homophones, accents, and technical terms. The `whisper-timestamped` library ships with the helper; the Whisper `tiny` model is not bundled and downloads only after user consent (~150 MB) into `%LOCALAPPDATA%\Uoink\models\whisper`.

### Local feature: Smart Screenshot Picker

Opt-in grid that shows the screenshots embedded in your clipboard paste so you can pick which to keep. Embed count is configurable on the setup page (default 4, max 12). Fully local — no API key, no network calls.
**For agent developers (v2)**
- **MCP server** with 14 tools: `uoink_video`, `uoink_playlist`, `get_job_status`, `cancel_job`, `list_recent_uoinks`, `search_uoinks`, `get_uoink_corpus`, `analyze_comments`, `classify_hook`, `get_taxonomy`, `get_citation_map`, `get_uoink_health`, `find_mentions`, `get_transcript_reliability`. The old `yoink_*` names keep working as deprecated aliases through v2.5.
- Stdio transport (officially tested with Claude Desktop + Cursor).
- Local HTTP JSON-RPC transport (experimental).
- Setup page generates copy-pasteable config snippets for each major client.

**Everywhere**
- Local-first, no cloud, no accounts, no required telemetry
- API key encryption via Windows Credential Manager
- Job persistence across helper restarts
- Fully open source (MIT)

## Install

1. **Download the installer** — grab `Uoink-Setup-2.1.0.exe` from the [latest release](https://github.com/ryanbiddy/uoink/releases/latest). Windows + macOS (universal) as of v2.1.
2. **Run it.** Defaults install to `%LOCALAPPDATA%\Uoink\` (no admin required). The "Launch Uoink now" checkbox on the finish page starts the helper immediately, and an autostart entry runs it on every Windows login.
3. **Install the extension** from the Chrome Web Store. The first time you launch the popup it'll detect the helper and the indicator will go green within a couple of seconds.

**For MCP users:** open the Uoink setup page from the extension popup's Settings link. Copy the stdio config snippet, paste into Claude Desktop's MCP config, restart Claude. Uoink tools appear automatically.

If the popup indicator stays orange, open the Start Menu, search "Uoink", and click **Uoink**. Stop it the same way via **Stop Uoink**. Uninstall removes everything including the autostart entry.

For developers running from source, see [REQUIREMENTS.md](./REQUIREMENTS.md). Build the installer locally with `./build.ps1` — see [docs/build-installer.md](./docs/build-installer.md).

## How it works

**Extension flow:**
1. Click "Uoink" under any YouTube video
2. Uoink extracts transcript, screenshots, comments, metadata
3. Markdown corpus copied to clipboard, with 4 screenshots embedded by default and the full screenshot set saved on disk
4. Paste, run a prompt, get analysis

**Agent flow (MCP):**
1. Your AI agent has access to Uoink's MCP tools after setup
2. Ask it "uoink this video and decode the hook"
3. Agent calls `uoink_video` → `classify_hook` → produces analysis
4. No clipboard step, no context switching

## Optional AI features — privacy

Comment Intelligence, Hook Type classification, and the agent-callable `analyze_comments` / `classify_hook` tools all call the Anthropic API. They're off by default. When you enable any of them, you provide your own Anthropic API key on the setup page. The key is stored in Windows Credential Manager (encrypted at rest by the OS) and used only for the API calls those features make. Uoink itself collects nothing. You can revoke a key at any time via the setup page's Clear button.

## Prompt library

The Uoink popup ships with 11 starter prompts ("Decode the hook", "Outline the structure", "Format as Twitter thread", and so on). For v1/v2 the prompts are baked into the extension package and aren't user-editable from the UI — a v2.1 task adds an inline editor that persists user prompts via `chrome.storage.local`.

If you're running from source, the file lives at `extension/prompts.json` and changes take effect the next time you open the popup:

```json
[
  { "id": "my-prompt", "label": "Short button label", "prompt": "The full prompt body..." }
]
```

## Topic folders

Videos are auto-sorted into topic folders under `Desktop\Uoink\` based on keyword matches in an internal `topics.json` config that ships with the install. The topic list is fixed in v1/v2; user-editable topics with persistence are on the v2.1 backlog so user edits won't get overwritten by the next installer release.

## Roadmap

See [BACKLOG.md](./BACKLOG.md) for v2.1 / v2.5 / v3 plans. Highlights:

- **v2.1** (post-launch polish): Mac installer, system tray status, keyboard shortcut, auto-update check, editable prompts library, crash report opt-in, Hook taxonomy query surface, jobs.json compaction
- **v2.5**: Channel Decoder mode, Niche Corpus mode, Critique-against-corpus
- **v3**: Send to Project, Podcast extraction, multi-platform video support
- **v4+**: Hosted version, public HTTPS API, most-uoinked leaderboard

## License

MIT. See LICENSE.

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for the full version history.

---

*Uoink is part of the [ReplayRyan](https://replayryan.com) family of tools.*
