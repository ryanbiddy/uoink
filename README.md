# Uoink

[![License: MIT](https://img.shields.io/badge/License-MIT-C2410C.svg)](./LICENSE)
[![Release](https://img.shields.io/github/v/release/ryanbiddy/uoink?color=C2410C&label=release)](https://github.com/ryanbiddy/uoink/releases/latest)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0A0A0A.svg)](https://uoink.app/install)
[![MCP server](https://img.shields.io/badge/MCP-server-FF3D00.svg)](https://uoink.app/mcp)
[![Website: uoink.app](https://img.shields.io/badge/web-uoink.app-C2410C.svg)](https://uoink.app)

**Uoink keeps the videos, podcasts, and articles creators and AI developers study on their own disk, then hands them to Claude, ChatGPT, Cursor, or a local MCP agent as a cited corpus.**

Free, open source (MIT), and local-first: no account, no Uoink cloud, no required telemetry. Uoink saves supported sources as structured Markdown on *your* machine, then makes the corpus available to your AI through the clipboard, a local MCP server, and an OpenAPI bridge. YouTube capture includes the transcript, timestamped screenshots, comments, and metadata; other source types keep the material their publishers expose.

- **Website:** https://uoink.app · **Install:** https://uoink.app/install · **Developers:** https://uoink.app/developers
- **Status:** Windows 10/11 only. There is no Mac build. The extension sideloads from the release — it is not on the Chrome Web Store. The installer is unsigned, so Windows SmartScreen will warn on first run.

## Why Uoink

You see a video that's clearly working and you want to know why. So you paste the YouTube link into Claude and hope it can "watch" it. It can't — it hallucinates the quotes, invents the title, and gives up past the first paragraph. You end up watching the whole thing on 2x, taking notes by hand.

Uoink fixes that. Click the **Uoink** button under any video (or right-click a link, or press `Alt+U`) and you get the full transcript, timestamped screenshots, top comments, channel context, and metadata — copied to your clipboard and saved on disk, ready for Claude, ChatGPT, or your notes app. Or tell your AI agent *"uoink that video and decode the hook"* and it does both, with no clipboard step.

The corpus compounds. Every source you save lands in one local library your AI can search, cite, and write from — in your voice.

## What you can capture

| Source | Captured |
|---|---|
| **YouTube** (flagship) | Timestamped transcript, screenshots, top comments, channel context, full metadata, JSON sidecar |
| **X / Twitter video + text** | Video transcript and post text, author credit, thread context |
| **Podcasts** | Automatic RSS/Atom metadata watching; optional per-feed Auto-ingest for local MP3 download, WhisperX transcription, and corpus publishing |
| **Web pages / articles** | Readable text extraction into the same corpus format |
| **Reddit** | Thread + top comments as Markdown |

Published sources are indexed in one local library. Podcast audio and transcripts stay under Uoink's local data folder; publishing an episode adds its Markdown and sidecar to that same searchable index.

## Three ways your AI reads the corpus

**1. Clipboard (the creator path)** — Click Uoink, paste into Claude / ChatGPT. Transcript plus a paste-safe subset of screenshots inlined as images so the model sees text *and* frames in one paste.

**2. MCP server (the agent path)**: A local MCP server exposing 91 tools over stdio, five library resource templates and nine prompts. Claude Desktop (.mcpb), Claude Code and Cursor get the full capture, research, writing and Library tool set through the standard connection. Consent gates are unchanged.

The stdio transport is tested with **Claude Desktop and Cursor**. Cline and Continue are standard-stdio compatibility paths, not individually smoke-tested.

- **stdio** defaults to all 91 registry tools. Set `UOINK_MCP_TOOLSET=core` in the client's environment for the previous 35 tools. Cursor and other clients with tool caps may need this setting. Restart the connection after changing it.
- **HTTP JSON-RPC** at `/mcp/v1` exposes the same 91-tool registry through the token-authenticated local helper. Both MCP transports share handlers and flatten the same three top-level `oneOf` input schemas for client compatibility. The server still validates the exact frozen schemas.

**3. OpenAPI bridge (for local agents that don't speak MCP)** — Local OpenAPI-capable agents and scripts can drive the same tools over an OpenAPI 3.1 surface at `/openapi/v1/spec.json` + `POST /tools/<name>`.

### Use Uoink from any AI agent

After installing, open a new terminal and run `uoink status` or
`uoink search "working memory" --limit 5`. The installer's checked PATH option
makes `uoink` available to agents with a local shell. `uoink connect <client>`
prints connection instructions for MCP clients.

The [portable skill](skills/uoink/SKILL.md) supports Claude Code, Codex, pi,
Hermes Agent, and OpenClaw through MCP or the CLI. The Claude Code marketplace
at [ryanbiddy/uoink-agent-kit](https://github.com/ryanbiddy/uoink-agent-kit),
published with this release, bundles the skill and MCP config. See
[Connect your agent](docs/connect-your-agent.md) for commands and client limits,
or [agent installation steps](llms-install.md) for installation from a shell.

### MCP setup (Claude Desktop, Cursor, Cline)

After installing Uoink, open the setup page from the extension popup's **Settings** link and copy the generated snippet — or paste this into your client's MCP config. The stdio server runs the bundled Python against the installed `uoink_mcp.py` (the C-01 fix pins the app dir onto `sys.path`, so this command works on every install):

```json
{
  "mcpServers": {
    "uoink": {
      "command": "%LOCALAPPDATA%\\Uoink\\python\\python.exe",
      "args": ["%LOCALAPPDATA%\\Uoink\\uoink_mcp.py"]
    }
  }
}
```

> Claude Desktop does not expand `%LOCALAPPDATA%` — use the full absolute path (e.g. `C:\\Users\\<you>\\AppData\\Local\\Uoink\\python\\python.exe`). Restart the client after saving; Uoink's tools appear automatically.

**One-click install:** a Claude Desktop [`.mcpb` bundle](./docs/mcpb-bundle.md) installs the stdio server without hand-editing config. See [docs/mcpb-bundle.md](./docs/mcpb-bundle.md).

**HTTP transport:** point an HTTP MCP client at `http://127.0.0.1:5179/mcp/v1` and send the header `X-Uoink-Token` (read the token from `%LOCALAPPDATA%\Uoink\token.txt`).

### Uoink Operator Skill

Uoink ships a portable Skill at `skills/uoink/SKILL.md` (installed to `%LOCALAPPDATA%\Uoink\skills\uoink\`) for finding saved evidence, citing timestamps, capturing URLs, saving notes, and writing from the user's sources and voice. Clients that support Agent Skills can load the same file alongside Uoink's MCP tools or use its exact CLI commands. See [Connect your agent](docs/connect-your-agent.md) for install paths and the small Claude Code plugin kit.

## Install

1. **Download the installer.** Download `Uoink-Setup-3.10.0.exe` from the [v3.10.0 release](https://github.com/ryanbiddy/uoink/releases/tag/v3.10.0). Windows 10/11 only. There is no Mac build today. The installer is unsigned: if SmartScreen shows "Windows protected your PC", choose **More info -> Run anyway**, and check the file against the SHA-256 listed on the release page.
2. **Run it.** Defaults install to `%LOCALAPPDATA%\Uoink\` (no admin required). The finish page can launch the helper immediately, and an autostart entry runs it on each login.
3. **Load the bundled extension.** On first launch, Uoink shows a one-time setup splash. Use it to open your browser's extensions page and copy the installed extension path; then enable Developer mode, click **Load unpacked**, and select that folder. (The Chrome Web Store listing is pending; sideload is the current path.)

For developers running from source, see [REQUIREMENTS.md](./REQUIREMENTS.md). Build the installer locally with `./build.ps1` (see [docs/build-installer.md](./docs/build-installer.md)).

### Quiet desktop notifications

Desktop notifications are on by default. To keep background feed watches and
captures invisible, open **Dashboard → Settings → Local app** and turn off
**Show desktop notifications**. Uoink keeps suppressed updates in the
dashboard's **Activity** view, so silence does not discard the event. Uoink
also applies the same courtesy automatically while a foreground app covers its
monitor, including borderless and exclusive-fullscreen games.

The persisted setting is `notifications_enabled` in `settings.json`. Local
clients can read it through `GET /settings` or update it with an authenticated
`POST /settings` body such as `{"notifications_enabled": false}`. Restart is
not required.

## How it works

**Extension flow:** click Uoink under a video → Uoink extracts transcript, screenshots, comments, metadata → Markdown corpus lands on your clipboard (screenshots embedded) and the full set saves to disk → paste, run a prompt, get analysis.

**Agent flow (MCP):** your agent has the Uoink tools after setup → ask *"uoink this video and decode the hook"* → the agent calls `uoink_video` → `classify_hook` → analysis, no clipboard step.

Five research playbooks work over saved captures: `outlier-posts`, `transcript-intel`, `comment-mining`, `creator-teardown` and `repurpose-pack`. Use their stdio prompts or `get_playbook_input` on either transport. Uoink computes the metrics and supplies cited evidence; your client writes the report. These reads need no API key and make no network calls. See [arguments and examples](docs/v2-mcp.md#get_playbook_input).

Optional ScrapeCreators discovery adds `discover_candidates` and
`queue_discovered` on both transports. It is off by default and uses your own
key, explicit credit confirmation and a daily credit cap (25 by default). Connected
agents need a separate opt-in; dashboard calls use a short-lived intent from
each click. Pick up to ten results to send through the normal capture queue.
Saved metric snapshots can supplement local playbooks without another paid
call. No ScrapeCreators thumbnails are loaded. The dashboard controls are
pending; see the [discovery tool contract](docs/v2-mcp.md#discover_candidates).

## Privacy

Your saved corpora, screenshots, podcast audio, transcripts, library index and
diagnostic logs stay on your computer. Uoink has no account, cloud library or
telemetry.

Capture fetches the source you ask for. Podcast watches poll feeds you enable;
Auto-ingest can also download new episodes. Truncated X posts may use the
FxTwitter fallback to retrieve full text. Transcription can download models with
your consent, and **Check now** contacts GitHub for release information.

Optional AI features send relevant source text to Anthropic only with your own
API key. Comment Intelligence, Hook Type classification and entity extraction
are off by default; agent-requested analysis also requires your key. The key is
stored in the OS credential store. Content you pass to an AI client is handled
under that client's policy.

Read the [Uoink privacy policy](https://uoink.app/privacy).

## Disclaimer & Terms of Use

Uoink is designed and built for personal research, study, and original creator drafting. Users are solely responsible for ensuring that their use of captured media (transcript text, screenshots, and comments) complies with the Terms of Service, copyright policies, and API guidelines of YouTube, Reddit, X (Twitter), and any other source platforms. Uoink does not host, share, or claim ownership over third-party media.

## License

MIT. See [LICENSE](./LICENSE). Third-party components and their licenses are listed in [THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md).

## Changelog & roadmap

See [CHANGELOG.md](./CHANGELOG.md) for version history and [ROADMAP.md](./ROADMAP.md) for what's next.

---

*Built by [Ryan Biddy](https://github.com/ryanbiddy).*
