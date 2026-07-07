# Uoink

[![License: MIT](https://img.shields.io/badge/License-MIT-C2410C.svg)](./LICENSE)
[![Release](https://img.shields.io/github/v/release/ryanbiddy/uoink?color=C2410C&label=release)](https://github.com/ryanbiddy/uoink/releases/latest)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0A0A0A.svg)](https://uoink.app/install)
[![MCP server](https://img.shields.io/badge/MCP-server-FF3D00.svg)](https://uoink.app/mcp)
[![Website: uoink.app](https://img.shields.io/badge/web-uoink.app-C2410C.svg)](https://uoink.app)

**Uoink keeps the videos, podcasts, and articles creators and AI developers study on their own disk, then hands them to Claude, ChatGPT, Cursor, or a local MCP agent as a cited corpus.**

Free, open source (MIT), and local-first: no account, no Uoink cloud, no required telemetry. One click saves a source — full transcript, timestamped screenshots, comments, and metadata — as a structured Markdown corpus on *your* machine, then makes it available to your AI three ways: the clipboard, a local MCP server, and an OpenAPI bridge.

![Uoink: the rust U button under a YouTube video](assets/readme-hero-v3.1.png)

- **Website:** https://uoink.app · **Install:** https://uoink.app/install · **Developers:** https://uoink.app/developers
- **Status:** Windows 10/11 today; Mac build queued after Windows stabilizes. Chrome Web Store listing pending — for now the extension sideloads from the release.

## Why Uoink

You see a video that's clearly working and you want to know why. So you paste the YouTube link into Claude and hope it can "watch" it. It can't — it hallucinates the quotes, invents the title, and gives up past the first paragraph. You end up watching the whole thing on 2x, taking notes by hand.

Uoink fixes that. Click the **Uoink** button under any video (or right-click a link, or press `Alt+U`) and you get the full transcript, timestamped screenshots, top comments, channel context, and metadata — copied to your clipboard and saved on disk, ready for Claude, ChatGPT, or your notes app. Or tell your AI agent *"uoink that video and decode the hook"* and it does both, with no clipboard step.

The corpus compounds. Every source you save lands in one local library your AI can search, cite, and write from — in your voice.

## What you can capture

| Source | Captured |
|---|---|
| **YouTube** (flagship) | Timestamped transcript, screenshots, top comments, channel context, full metadata, JSON sidecar |
| **X / Twitter video + text** | Video transcript and post text, author credit, thread context |
| **Podcasts** | RSS feeds and episodes, local Whisper transcription, speaker diarization |
| **Web pages / articles** | Readable text extraction into the same corpus format |
| **Reddit** | Thread + top comments as Markdown |

Everything files into one local library, auto-sorted into topic folders under your Uoink output folder (default `Desktop\Uoink\`).

## Three ways your AI reads the corpus

**1. Clipboard (the creator path)** — Click Uoink, paste into Claude / ChatGPT. Transcript plus a paste-safe subset of screenshots inlined as images so the model sees text *and* frames in one paste.

**2. MCP server (the agent path)** — A local Model Context Protocol server, tested with **Claude Desktop, Cursor, Cline, and Continue**, and usable from any MCP-capable client. Two surfaces, on purpose:
- **stdio** exposes a curated everyday set of 14 tools most agents need (`uoink_video`, `uoink_playlist`, `list_recent_uoinks`, `search_uoinks`, `get_uoink_corpus`, `analyze_comments`, `classify_hook`, `get_citation_map`, `get_uoink_health`, `find_mentions`, and more).
- **HTTP JSON-RPC** at `/mcp/v1` exposes the full local tool registry (Writing Studio, workspaces, podcasts, monitored playlists, taste/engagement memory, source capture) — the same handlers, same auth token.

**3. OpenAPI bridge (for agents that don't speak MCP)** — Gemini, Grok, Perplexity, and scripts can drive the same tools over an OpenAPI 3.1 surface at `/openapi/v1/spec.json` + `POST /tools/<name>`.

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

Uoink ships a portable Skill at `skills/uoink/SKILL.md` (installed to `%LOCALAPPDATA%\Uoink\skills\uoink\`) that gives MCP-capable agents the operating frame for Uoink corpora: timestamp-citation discipline, decode-don't-dunk analysis, and the Uoink Hook Type taxonomy. It works across Claude, Cursor, OpenClaw, Hermes, and other clients via the agentskills.io open standard.

## Install

1. **Download the installer.** Grab `Uoink-Setup-3.2.8.exe` from the [latest release](https://github.com/ryanbiddy/uoink/releases/latest). Windows 10/11 is available now; the Mac `.dmg` is queued after Windows stabilizes.
2. **Run it.** Defaults install to `%LOCALAPPDATA%\Uoink\` (no admin required). The finish page can launch the helper immediately, and an autostart entry runs it on each login.
3. **Load the bundled extension.** On first launch, Uoink opens `chrome://extensions/` and shows the extension folder so you can enable Developer mode, click **Load unpacked**, and select `%LOCALAPPDATA%\Uoink\extension`. (The Chrome Web Store listing is pending; sideload is the current path.)

For developers running from source, see [REQUIREMENTS.md](./REQUIREMENTS.md). Build the installer locally with `./build.ps1` (see [docs/build-installer.md](./docs/build-installer.md)).

## How it works

**Extension flow:** click Uoink under a video → Uoink extracts transcript, screenshots, comments, metadata → Markdown corpus lands on your clipboard (screenshots embedded) and the full set saves to disk → paste, run a prompt, get analysis.

**Agent flow (MCP):** your agent has the Uoink tools after setup → ask *"uoink this video and decode the hook"* → the agent calls `uoink_video` → `classify_hook` → analysis, no clipboard step.

## Optional AI features and privacy

Core capture works with **no API key**. Comment Intelligence, Hook Type classification, Entity Extraction, and the agent-callable `analyze_comments` / `classify_hook` tools call the Anthropic API and are **off by default**. When you enable them you supply your own Anthropic API key on the setup page; it's stored in the OS credential store (encrypted at rest) and used only for those calls. Uoink itself collects nothing — the core extraction stays local except the source fetch. Revoke the key any time via the setup page.

## Disclaimer & Terms of Use

Uoink is designed and built for personal research, study, and original creator drafting. Users are solely responsible for ensuring that their use of captured media (transcript text, screenshots, and comments) complies with the Terms of Service, copyright policies, and API guidelines of YouTube, Reddit, X (Twitter), and any other source platforms. Uoink does not host, share, or claim ownership over third-party media.

## License

MIT. See [LICENSE](./LICENSE). Third-party components and their licenses are listed in [THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md).

## Changelog & roadmap

See [CHANGELOG.md](./CHANGELOG.md) for version history and [ROADMAP.md](./ROADMAP.md) for what's next.

---

*Uoink is part of the [ReplayRyan](https://replayryan.com) family of tools.*
